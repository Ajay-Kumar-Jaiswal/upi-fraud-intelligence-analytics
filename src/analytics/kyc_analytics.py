"""
KYC-linked analytics.

Two distinct layers, per the brief:
  (a) KYC POPULATION statistics - computed directly from dim_users, no
      join needed, 100% coverage of the KYC file by definition.
  (b) TRANSACTION-BEHAVIOR-BY-KYC-STATUS - requires joining
      transactions.user_id -> dim_users.user_id, which is the low-coverage
      identity join documented in DATA_AUDIT.md Open Question #1 (~32%
      match rate, and among matches ~10% resolve to more than one
      distinct kyc_status due to identity collisions). Computed only over
      the unambiguous, matched subset - coverage reported explicitly.
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_users, load_chargebacks
from src.analytics.coverage import compute_join_coverage


def kyc_population_kpis() -> dict:
    """
    Source: dim_users only (no join). Grain = one row per raw KYC record
    (NOT one row per unique person - see DATA_AUDIT.md on identity
    collisions - so these are RECORD-level, not person-level, statistics
    and are labeled as such).
    kyc_status_distribution = COUNT(*) GROUP BY kyc_status
    kyc_completion_rate_pct = VERIFIED-family records / total records
    kyc_rejection_rate_pct  = REJECTED-family records / total records
    """
    users = load_users()
    total = len(users)
    status_counts = users["kyc_status"].value_counts()
    verified = int(status_counts.get("VERIFIED", 0))
    rejected = int(status_counts.get("REJECTED", 0))
    return {
        "grain_note": "One row per raw KYC record, not per unique person (see DATA_AUDIT.md identity-collision finding).",
        "total_kyc_records": total,
        "kyc_status_distribution": status_counts.to_dict(),
        "kyc_completion_rate_pct": round(verified / total * 100, 2) if total else 0.0,
        "kyc_rejection_rate_pct": round(rejected / total * 100, 2) if total else 0.0,
        "risk_segment_distribution": users["risk_segment"].value_counts().to_dict(),
    }


def _unambiguous_user_attribute_map(users: pd.DataFrame, attribute: str) -> pd.Series:
    counts = users.groupby("user_id")[attribute].nunique()
    unambiguous_ids = counts[counts == 1].index
    return (
        users[users["user_id"].isin(unambiguous_ids)]
        .drop_duplicates("user_id")
        .set_index("user_id")[attribute]
    )


def kyc_join_coverage() -> dict:
    txn = load_transactions()
    users = load_users()
    any_ids = set(users["user_id"].dropna())
    any_cov = compute_join_coverage(
        txn["user_id"], any_ids,
        relationship="transactions.user_id -> dim_users.user_id (any record)",
    )
    status_lookup = _unambiguous_user_attribute_map(users, "kyc_status")
    unambiguous_cov = compute_join_coverage(
        txn["user_id"], set(status_lookup.index),
        relationship="transactions.user_id -> dim_users.user_id (unambiguous kyc_status only)",
    )
    return {
        "step_1_any_user_match": any_cov.as_dict(),
        "step_2_unambiguous_kyc_status_match": unambiguous_cov.as_dict(),
        "note": (
            f"{any_cov.matched_rows - unambiguous_cov.matched_rows} transactions matched a user_id "
            "present in dim_users but that id maps to more than one distinct kyc_status across "
            "colliding identity records, so status cannot be safely assigned."
        ),
    }


def transaction_behavior_by_kyc_status() -> pd.DataFrame:
    """
    transaction_count, transaction_value, chargeback_count, chargeback_ratio
    grouped by kyc_status, computed ONLY over transactions whose user_id
    resolves to an unambiguous kyc_status (see kyc_join_coverage for the
    excluded fraction). This directly supports the dataset notes'
    example insight: 'Unverified or rejected KYC users may show higher
    fraud/dispute risk' and example question: 'Which KYC status has the
    highest transaction amount?'
    """
    txn = load_transactions()
    users = load_users()
    cb = load_chargebacks()

    status_lookup = _unambiguous_user_attribute_map(users, "kyc_status")
    txn = txn.copy()
    txn["kyc_status"] = txn["user_id"].map(status_lookup)
    txn_matched = txn[txn["kyc_status"].notnull()]

    base = (
        txn_matched.groupby("kyc_status")
        .agg(transaction_count=("txn_id", "count"), transaction_value=("amount", "sum"))
        .reset_index()
    )
    txn_id_to_status = txn_matched.set_index("txn_id")["kyc_status"]
    cb = cb.copy()
    cb["kyc_status"] = cb["txn_id"].map(txn_id_to_status)
    cb_matched = cb[cb["kyc_status"].notnull()]
    cb_agg = cb_matched.groupby("kyc_status").agg(chargeback_count=("complaint_id", "count")).reset_index()

    out = base.merge(cb_agg, on="kyc_status", how="left")
    out["chargeback_count"] = out["chargeback_count"].fillna(0).astype(int)
    out["transaction_value"] = out["transaction_value"].round(2)
    out["chargeback_to_transaction_ratio"] = (out["chargeback_count"] / out["transaction_count"]).round(6)
    return out.sort_values("transaction_value", ascending=False).reset_index(drop=True)


def suspicious_identity_indicators() -> dict:
    """
    Per dataset notes / brief §15: 'potential synthetic identity
    indicator', never 'confirmed'. Signal used: the SAME normalized PAN
    (valid-format only, to avoid conflating OCR-corrupted values) appears
    across MULTIPLE DIFFERENT normalized user_id values in dim_users.
    This is a count of a pattern, not an accusation - reported plainly.
    """
    users = load_users()
    valid_pan = users[users["pan_status"] == "valid"]
    pan_to_users = valid_pan.groupby("pan")["user_id"].nunique()
    shared_pan = pan_to_users[pan_to_users > 1]
    return {
        "methodology": (
            "Count of valid-format PAN values that appear against more than one "
            "distinct normalized user_id in dim_users. This is a POTENTIAL "
            "synthetic-identity INDICATOR only - not a confirmed finding, and not a "
            "fraud label (the dataset contains no fraud/synthetic-identity ground "
            "truth label)."
        ),
        "valid_format_pan_records_examined": len(valid_pan),
        "distinct_valid_pans": int(pan_to_users.shape[0]),
        "pans_linked_to_multiple_user_ids": int(len(shared_pan)),
        "pct_of_pans_flagged": round(len(shared_pan) / pan_to_users.shape[0] * 100, 2) if len(pan_to_users) else 0.0,
        "max_user_ids_sharing_one_pan": int(shared_pan.max()) if len(shared_pan) else 0,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(kyc_population_kpis(), indent=2, default=str))
    print(json.dumps(kyc_join_coverage(), indent=2))
    print(transaction_behavior_by_kyc_status().to_string(index=False))
    print(json.dumps(suspicious_identity_indicators(), indent=2))
