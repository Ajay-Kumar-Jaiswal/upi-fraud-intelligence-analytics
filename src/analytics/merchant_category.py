"""
Merchant-category performance analytics.

Merchant category is only available in dim_merchants (merchants_master),
NOT on fact_transactions directly. So computing "chargeback-to-transaction
ratio by merchant category" REQUIRES joining transactions.merchant_id ->
dim_merchants.merchant_id, which is the low-coverage identity join
documented in DATA_AUDIT.md Open Question #1 (~48% match rate, and even
among matches, ~28% of merchant_ids resolve to more than one distinct
category in dim_merchants due to identity collisions).

This module therefore computes the metric ONLY over the defensible,
unambiguous subset and reports coverage at every step, per the
project's standing rule: never imply population-level coverage when it
does not exist.
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_merchants, load_chargebacks
from src.analytics.coverage import compute_join_coverage


def _unambiguous_merchant_category_map(merchants: pd.DataFrame) -> pd.Series:
    """
    dim_merchants can have multiple raw records per normalized merchant_id
    (identity collisions - see DATA_AUDIT.md). A merchant_id is usable for
    category lookup ONLY if every record sharing that id agrees on
    merchant_category (unambiguous). Ambiguous ids are dropped from the
    lookup entirely (not resolved by picking "the first" or "the most
    recent" - there is no data-driven basis for that pick).
    Returns: Series indexed by merchant_id -> merchant_category, unambiguous only.
    """
    cat_counts = merchants.groupby("merchant_id")["merchant_category"].nunique()
    unambiguous_ids = cat_counts[cat_counts == 1].index
    lookup = (
        merchants[merchants["merchant_id"].isin(unambiguous_ids)]
        .drop_duplicates("merchant_id")
        .set_index("merchant_id")["merchant_category"]
    )
    return lookup


def merchant_category_join_coverage() -> dict:
    """
    Full funnel: transactions -> merchant_id found in dim_merchants at all
    -> merchant_id resolves to an UNAMBIGUOUS category. Both steps'
    attrition are reported separately so nothing is hidden inside a
    single aggregate percentage.
    """
    txn = load_transactions()
    merchants = load_merchants()
    total = len(txn)

    any_match_ids = set(merchants["merchant_id"].dropna())
    any_match_cov = compute_join_coverage(
        txn["merchant_id"], any_match_ids,
        relationship="transactions.merchant_id -> dim_merchants.merchant_id (any record)",
    )

    cat_lookup = _unambiguous_merchant_category_map(merchants)
    unambiguous_cov = compute_join_coverage(
        txn["merchant_id"], set(cat_lookup.index),
        relationship="transactions.merchant_id -> dim_merchants.merchant_id (unambiguous category only)",
    )

    return {
        "step_1_any_merchant_match": any_match_cov.as_dict(),
        "step_2_unambiguous_category_match": unambiguous_cov.as_dict(),
        "note": (
            "step_2 is the subset actually usable for category-level analytics. "
            f"{any_match_cov.matched_rows - unambiguous_cov.matched_rows} transactions matched a "
            "merchant_id that exists in dim_merchants but that id maps to more than one "
            "distinct category across colliding records, so category cannot be safely assigned."
        ),
    }


def merchant_category_performance() -> pd.DataFrame:
    """
    Per unambiguous merchant category:
    transaction_count       = COUNT(txn) WHERE merchant_id resolves to this category
    transaction_value       = SUM(amount)
    chargeback_count        = COUNT(chargebacks) whose txn_id is one of this category's transactions
    disputed_amount         = SUM(disputed_amount) for those chargebacks
    chargeback_to_txn_ratio = chargeback_count / transaction_count

    Source: fact_transactions JOIN dim_merchants (unambiguous only) JOIN
    fact_chargebacks (via txn_id, the high-coverage join).
    Rows that don't resolve to an unambiguous category are excluded and
    reported in merchant_category_join_coverage() - NOT silently folded
    into any category bucket.
    """
    txn = load_transactions()
    merchants = load_merchants()
    cb = load_chargebacks()

    cat_lookup = _unambiguous_merchant_category_map(merchants)
    txn = txn.copy()
    txn["merchant_category"] = txn["merchant_id"].map(cat_lookup)
    txn_categorized = txn[txn["merchant_category"].notnull()]

    txn_id_to_category = txn_categorized.set_index("txn_id")["merchant_category"]
    cb = cb.copy()
    cb["merchant_category"] = cb["txn_id"].map(txn_id_to_category)
    cb_categorized = cb[cb["merchant_category"].notnull()]

    base = (
        txn_categorized.groupby("merchant_category")
        .agg(transaction_count=("txn_id", "count"),
             transaction_value=("amount", "sum"))
        .reset_index()
    )
    cb_agg = (
        cb_categorized.groupby("merchant_category")
        .agg(chargeback_count=("complaint_id", "count"),
             disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)))
        .reset_index()
    )
    out = base.merge(cb_agg, on="merchant_category", how="left")
    out["chargeback_count"] = out["chargeback_count"].fillna(0).astype(int)
    out["disputed_amount"] = out["disputed_amount"].fillna(0.0)
    out["transaction_value"] = out["transaction_value"].round(2)
    out["chargeback_to_transaction_ratio"] = (out["chargeback_count"] / out["transaction_count"]).round(6)
    out["chargeback_rate_pct"] = (out["chargeback_to_transaction_ratio"] * 100).round(4)
    out = out.sort_values("chargeback_to_transaction_ratio", ascending=False).reset_index(drop=True)
    out.insert(0, "rank_by_chargeback_ratio", range(1, len(out) + 1))
    return out


def bonus_question_highest_chargeback_ratio_category(quarter_start=None, quarter_end=None) -> dict:
    """
    Official bonus business question:
    "Which merchant category has the highest chargeback-to-transaction
    ratio this quarter?"

    Quarter definition: standard calendar quarter (Jan-Mar / Apr-Jun /
    Jul-Sep / Oct-Dec), IST. Determined dynamically from the actual data
    range in fact_transactions - NOT hard-coded. If quarter_start/end are
    not supplied, the function inspects the data, finds which calendar
    quarter contains the most transaction volume, and uses that quarter.
    If the dataset spans more than one quarter with materially split
    volume, that is reported explicitly rather than silently picking one.
    """
    txn = load_transactions()
    if len(txn) == 0:
        return {"error": "No transaction data available - cannot compute."}

    ts = txn["timestamp"]
    tz = ts.dt.tz
    quarters = ts.dt.tz_localize(None).dt.to_period("Q")
    quarter_counts = quarters.value_counts().sort_index()
    dominant_quarter = quarter_counts.idxmax()
    dominant_share_pct = round(quarter_counts.max() / len(txn) * 100, 2)

    if quarter_start is None or quarter_end is None:
        q_period = dominant_quarter
        q_start = q_period.start_time.tz_localize(tz)
        q_end = q_period.end_time.tz_localize(tz)
    else:
        q_start, q_end = quarter_start, quarter_end
        q_period = None

    txn_q = txn[(txn["timestamp"] >= q_start) & (txn["timestamp"] <= q_end)]

    if len(txn_q) == 0:
        return {
            "error": (
                f"No transactions fall within the requested quarter window "
                f"({q_start} to {q_end}). Dataset's actual range is "
                f"{ts.min()} to {ts.max()}. Cannot compute this metric for "
                f"the requested period - reporting limitation rather than "
                f"inventing a result."
            )
        }

    merchants = load_merchants()
    cb = load_chargebacks()
    cat_lookup = _unambiguous_merchant_category_map(merchants)

    txn_q = txn_q.copy()
    txn_q["merchant_category"] = txn_q["merchant_id"].map(cat_lookup)
    txn_q_cat = txn_q[txn_q["merchant_category"].notnull()]

    if len(txn_q_cat) == 0:
        return {"error": "No transactions in this quarter resolved to an unambiguous merchant category. Cannot compute."}

    txn_id_to_cat = txn_q_cat.set_index("txn_id")["merchant_category"]
    cb_q = cb[cb["txn_id"].isin(txn_q_cat["txn_id"])].copy()
    cb_q["merchant_category"] = cb_q["txn_id"].map(txn_id_to_cat)

    base = txn_q_cat.groupby("merchant_category").agg(transaction_count=("txn_id", "count")).reset_index()
    cb_agg = cb_q.groupby("merchant_category").agg(chargeback_count=("complaint_id", "count")).reset_index()
    out = base.merge(cb_agg, on="merchant_category", how="left")
    out["chargeback_count"] = out["chargeback_count"].fillna(0).astype(int)
    out["chargeback_to_transaction_ratio"] = (out["chargeback_count"] / out["transaction_count"]).round(6)
    out = out.sort_values("chargeback_to_transaction_ratio", ascending=False).reset_index(drop=True)

    top = out.iloc[0]
    return {
        "quarter_used": str(q_period) if q_period is not None else f"{q_start} to {q_end}",
        "quarter_definition": "Standard calendar quarter (Jan-Mar/Apr-Jun/Jul-Sep/Oct-Dec), IST timezone.",
        "quarter_selection_method": (
            f"Dominant quarter by transaction volume in the actual data "
            f"({dominant_share_pct}% of all {len(txn)} transactions fall in {dominant_quarter})."
            if q_period is not None else "Explicit quarter window supplied by caller."
        ),
        "transactions_in_quarter": len(txn_q),
        "transactions_in_quarter_with_unambiguous_category": len(txn_q_cat),
        "category_coverage_pct_of_quarter_transactions": round(len(txn_q_cat) / len(txn_q) * 100, 2),
        "answer_merchant_category": top["merchant_category"],
        "answer_chargeback_to_transaction_ratio": float(top["chargeback_to_transaction_ratio"]),
        "answer_chargeback_count": int(top["chargeback_count"]),
        "answer_transaction_count": int(top["transaction_count"]),
        "full_ranking": out.to_dict(orient="records"),
        "caveat": (
            "Computed only over the subset of quarter transactions whose merchant_id "
            "resolves to an unambiguous category in dim_merchants (see "
            "merchant_category_join_coverage() for the full funnel). This is NOT a "
            "population-complete result - see category_coverage_pct_of_quarter_transactions."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(merchant_category_join_coverage(), indent=2))
    print(merchant_category_performance().to_string(index=False))
    print(json.dumps(bonus_question_highest_chargeback_ratio_category(), indent=2, default=str))
