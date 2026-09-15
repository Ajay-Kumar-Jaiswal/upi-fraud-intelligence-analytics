"""
Merchant-master-linked analytics.

Distinguishes two layers, per the brief's requirement:
  (a) transaction-level facts keyed by raw merchant_id (no master join,
      100% coverage by definition - see chargebacks_by_merchant() in
      chargebacks_kpi.py for the transaction-fact version), and
  (b) merchant-master-ENRICHED metrics (name, category, status, business
      type) which inherit the ~48% join-coverage ceiling documented in
      DATA_AUDIT.md Open Question #1 and are explicitly labeled as such.
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_merchants, load_chargebacks
from src.analytics.coverage import compute_join_coverage
from src.analytics.merchant_category import _unambiguous_merchant_category_map


def _unambiguous_merchant_attribute_map(merchants: pd.DataFrame, attribute: str) -> pd.Series:
    """Same unambiguous-only resolution rule as merchant category (see
    merchant_category.py) applied generically to any dim_merchants
    attribute (merchant_name, merchant_status, business_type, city)."""
    counts = merchants.groupby("merchant_id")[attribute].nunique()
    unambiguous_ids = counts[counts == 1].index
    return (
        merchants[merchants["merchant_id"].isin(unambiguous_ids)]
        .drop_duplicates("merchant_id")
        .set_index("merchant_id")[attribute]
    )


def merchant_master_join_coverage() -> dict:
    txn = load_transactions()
    merchants = load_merchants()
    any_ids = set(merchants["merchant_id"].dropna())
    cov = compute_join_coverage(
        txn["merchant_id"], any_ids,
        relationship="transactions.merchant_id -> dim_merchants.merchant_id (any record, any attribute)",
    )
    return cov.as_dict()


def merchant_master_enriched_ranking(top_n: int = 20) -> pd.DataFrame:
    """
    Merchant-level ranking ENRICHED with master data (name, category,
    status). Built only from transactions whose merchant_id resolves to
    an unambiguous merchant_name (same defensible-subset rule as
    category). Ranked by transaction value, with chargeback ratio shown
    alongside. This is explicitly the enriched, coverage-limited view -
    NOT a population-complete merchant ranking.
    """
    txn = load_transactions()
    merchants = load_merchants()
    cb = load_chargebacks()

    name_lookup = _unambiguous_merchant_attribute_map(merchants, "merchant_name")
    cat_lookup = _unambiguous_merchant_category_map(merchants)
    status_lookup = _unambiguous_merchant_attribute_map(merchants, "merchant_status")

    txn = txn.copy()
    txn["merchant_name"] = txn["merchant_id"].map(name_lookup)
    txn_named = txn[txn["merchant_name"].notnull()]

    base = (
        txn_named.groupby(["merchant_id", "merchant_name"])
        .agg(transaction_count=("txn_id", "count"), transaction_value=("amount", "sum"))
        .reset_index()
    )
    base["merchant_category"] = base["merchant_id"].map(cat_lookup).fillna("Ambiguous/Unresolved")
    base["merchant_status"] = base["merchant_id"].map(status_lookup).fillna("Ambiguous/Unresolved")

    txn_id_to_merchant = txn_named.set_index("txn_id")["merchant_id"]
    cb = cb.copy()
    cb["merchant_id_resolved"] = cb["txn_id"].map(txn_id_to_merchant)
    cb_named = cb[cb["merchant_id_resolved"].notnull()]
    cb_agg = (
        cb_named.groupby("merchant_id_resolved")
        .agg(chargeback_count=("complaint_id", "count"),
             disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)))
        .reset_index()
        .rename(columns={"merchant_id_resolved": "merchant_id"})
    )
    out = base.merge(cb_agg, on="merchant_id", how="left")
    out["chargeback_count"] = out["chargeback_count"].fillna(0).astype(int)
    out["disputed_amount"] = out["disputed_amount"].fillna(0.0)
    out["chargeback_to_transaction_ratio"] = (out["chargeback_count"] / out["transaction_count"]).round(6)
    out["transaction_value"] = out["transaction_value"].round(2)
    out = out.sort_values("transaction_value", ascending=False).reset_index(drop=True)
    return out.head(top_n) if top_n else out


def top_merchants_by_chargeback_ratio(min_transactions: int = 10, top_n: int = 20) -> pd.DataFrame:
    """
    'High-risk merchants' style ranking. min_transactions is a documented
    floor to avoid a merchant with 1 transaction and 1 chargeback (ratio
    1.0) dominating the ranking on statistically meaningless volume -
    this is a defensible methodological choice, flagged as such, not a
    data fact.
    """
    full = merchant_master_enriched_ranking(top_n=None)
    eligible = full[full["transaction_count"] >= min_transactions]
    return eligible.sort_values("chargeback_to_transaction_ratio", ascending=False).head(top_n).reset_index(drop=True)


if __name__ == "__main__":
    import json
    print(json.dumps(merchant_master_join_coverage(), indent=2))
    print(merchant_master_enriched_ranking(10).to_string(index=False))
    print(top_merchants_by_chargeback_ratio(10, 10).to_string(index=False))
