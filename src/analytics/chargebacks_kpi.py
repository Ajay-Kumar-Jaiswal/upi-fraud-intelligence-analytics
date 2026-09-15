"""
Chargeback analytics.

Source tables: fact_chargebacks (cleaned), fact_transactions (cleaned).
Join key: chargebacks.txn_id -> transactions.txn_id (normalized format,
verified in DATA_AUDIT.md to reach ~93% match rate - this is the ONE
identity join in this dataset that is NOT statistically indistinguishable
from random, so chargeback-to-transaction linkage is treated as usable,
unlike the user_id/merchant_id joins).
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_chargebacks
from src.analytics.coverage import compute_join_coverage


def chargeback_txn_join_coverage() -> dict:
    """
    Reports how many chargeback records have a txn_id that matches a
    transaction in fact_transactions. txn_id is blank/missing for some
    chargebacks (never fabricated) - those are unmatched by definition.
    """
    cb = load_chargebacks()
    txn = load_transactions()
    txn_ids = set(txn["txn_id"].dropna())
    cov = compute_join_coverage(
        cb["txn_id"], txn_ids,
        relationship="chargebacks.txn_id -> transactions.txn_id",
        caveat="",  # this join is NOT the low-coverage identity join; no caveat needed at >=90%
    )
    return cov.as_dict()


def chargeback_core_kpis() -> dict:
    """
    chargeback_count                    = COUNT(*) FROM fact_chargebacks
    total_disputed_amount                = SUM(disputed_amount)  [nulls excluded, never imputed]
    chargeback_to_transaction_ratio      = chargeback_count_matched_to_txn / total_transactions
    chargeback_rate_pct                  = chargeback_to_transaction_ratio * 100

    IMPORTANT: chargeback_to_transaction_ratio uses only chargebacks whose
    txn_id matches a real transaction (see chargeback_txn_join_coverage),
    since an unmatched chargeback cannot be attributed to a transaction
    in this dataset without fabricating a link.
    """
    cb = load_chargebacks()
    txn = load_transactions()
    txn_ids = set(txn["txn_id"].dropna())
    total_transactions = len(txn)

    matched_cb = cb[cb["txn_id"].isin(txn_ids)]
    chargeback_count = len(cb)
    matched_chargeback_count = len(matched_cb)

    total_disputed = float(cb["disputed_amount"].dropna().sum())

    ratio = matched_chargeback_count / total_transactions if total_transactions else 0.0
    return {
        "chargeback_count_total": chargeback_count,
        "chargeback_count_matched_to_transaction": matched_chargeback_count,
        "chargeback_count_unmatched_or_missing_txn_id": chargeback_count - matched_chargeback_count,
        "total_disputed_amount": round(total_disputed, 2),
        "disputed_amount_records_with_value": int(cb["disputed_amount"].notnull().sum()),
        "disputed_amount_records_missing": int(cb["disputed_amount"].isnull().sum()),
        "total_transactions": total_transactions,
        "chargeback_to_transaction_ratio": round(ratio, 6),
        "chargeback_rate_pct": round(ratio * 100, 4),
        "methodology_note": (
            "Ratio = chargebacks with a txn_id matched to a real transaction / "
            "total transactions. Unmatched/blank-txn_id chargebacks are excluded "
            "from the numerator (see chargeback_txn_join_coverage) rather than "
            "assumed to belong to some transaction."
        ),
    }


def chargebacks_by(dimension: str) -> pd.DataFrame:
    """Generic breakdown by a controlled-vocabulary chargeback dimension:
    'reason_code', 'severity', 'resolution_status', or 'channel'."""
    allowed = {"reason_code", "severity", "resolution_status", "channel"}
    if dimension not in allowed:
        raise ValueError(f"dimension must be one of {allowed}")
    cb = load_chargebacks()
    out = (
        cb.groupby(dimension, dropna=False)
        .agg(chargeback_count=("complaint_id", "count"),
             total_disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)))
        .reset_index()
        .sort_values("chargeback_count", ascending=False)
    )
    return out


def chargebacks_by_merchant(top_n: int = 20) -> pd.DataFrame:
    """
    Chargeback count and disputed amount per raw merchant_id AS IT APPEARS
    ON THE CHARGEBACK RECORD ITSELF (not resolved via txn_id).

    WARNING: do not combine this directly with a transaction-count-by-
    merchant_id table to compute a ratio - the chargeback record's own
    merchant_id and the transaction's merchant_id are independently
    generated fields (see DATA_AUDIT.md Open Question #1) and are NOT
    guaranteed to refer to the same merchant for a given chargeback. For
    a defensible chargeback-ratio-by-merchant calculation, see
    src/fraud/risk_engine.py::merchant_risk_scores(), which resolves each
    chargeback's merchant via the high-coverage txn_id link instead.
    """
    cb = load_chargebacks()
    out = (
        cb.groupby("merchant_id", dropna=False)
        .agg(chargeback_count=("complaint_id", "count"),
             total_disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)))
        .reset_index()
        .sort_values("chargeback_count", ascending=False)
    )
    return out.head(top_n) if top_n else out


def top_users_by_disputed_amount(top_n: int = 10) -> pd.DataFrame:
    """Per dataset notes example question: 'Show top 10 users by disputed amount.'"""
    cb = load_chargebacks()
    out = (
        cb.groupby("user_id", dropna=False)
        .agg(chargeback_count=("complaint_id", "count"),
             total_disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)))
        .reset_index()
        .sort_values("total_disputed_amount", ascending=False)
    )
    return out.head(top_n)


def dispute_reporting_delay_kpis() -> dict:
    """
    report_delay_days = reported_timestamp - transaction_timestamp (computed
    in the cleaning stage; NaT-safe). Reported here only over non-null delays.
    'Disputes reported after 7 days' is an explicit example question in the
    dataset notes.
    """
    cb = load_chargebacks()
    delays = cb["report_delay_days"].dropna()
    delays = delays[delays >= 0]  # negative delay (reported before txn) is a data-quality flag, not a real delay
    negative_delay_count = int((cb["report_delay_days"].dropna() < 0).sum())
    over_7_days = int((delays > 7).sum())
    return {
        "records_with_valid_delay": int(len(delays)),
        "records_with_negative_delay_flagged": negative_delay_count,
        "average_delay_days": round(float(delays.mean()), 2) if len(delays) else None,
        "median_delay_days": round(float(delays.median()), 2) if len(delays) else None,
        "disputes_reported_after_7_days": over_7_days,
        "disputes_reported_after_7_days_pct_of_valid": round(over_7_days / len(delays) * 100, 2) if len(delays) else 0.0,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(chargeback_txn_join_coverage(), indent=2))
    print(json.dumps(chargeback_core_kpis(), indent=2))
    print(chargebacks_by("reason_code"))
    print(chargebacks_by("severity"))
    print(chargebacks_by_merchant(5))
    print(top_users_by_disputed_amount(5))
    print(json.dumps(dispute_reporting_delay_kpis(), indent=2))
