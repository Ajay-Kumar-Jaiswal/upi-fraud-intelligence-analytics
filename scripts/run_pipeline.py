#!/usr/bin/env python3
"""
Reproducible end-to-end cleaning pipeline.

Run from the project root:
    python scripts/run_pipeline.py

Reads RAW data only (never reads previously-processed output as source
of truth), cleans each dataset, writes Parquet to data/processed/, and
generates:
    reports/cleaning_report.csv   (per DATA_AUDIT.md §5 format)
    reports/data_quality_after.csv
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.config import DATA_PROCESSED, REPORTS_DIR, CLEAN_TRANSACTIONS, CLEAN_KYC, CLEAN_MERCHANTS, CLEAN_CHARGEBACKS
from src.cleaning.transactions import clean_transactions
from src.cleaning.kyc import clean_kyc
from src.cleaning.merchants import clean_merchants
from src.cleaning.chargebacks import clean_chargebacks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pipeline")


def _parquet_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Parquet/pyarrow requires a single type per column. Raw-value audit
    columns in this pipeline intentionally preserve the original source
    value (e.g. `disputed_amount_raw`), which for JSON-sourced data can
    legitimately mix numeric and string types (e.g. 4825.86 vs 'Rs. 860').
    Cast such object columns to string for storage, preserving nulls -
    the parsed/clean columns (not these _raw ones) are what downstream
    analytics actually use, so no information used for calculations is
    lost."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            types_seen = df[col].dropna().map(type).unique()
            if len(types_seen) > 1:
                df[col] = df[col].apply(lambda v: None if pd.isnull(v) else str(v))
    return df


def build_cleaning_report_row(report: dict) -> dict:
    """Maps a cleaner's raw report dict onto the standard audit-trail
    columns required by the brief: dataset, raw_rows, duplicates,
    missing_values_handled, invalid_values, rows_removed, rows_retained,
    rows_repaired."""
    missing_keys = [k for k in report if "missing" in k or "disguised_null" in k]
    invalid_keys = [k for k in report if "invalid" in k or "unrecognized" in k or "unmapped" in k]
    repaired_keys = [k for k in report if ("negative" in k and "flagged" in k) or "epoch_converted" in k or "masked" in k]
    return {
        "dataset": report["dataset"],
        "raw_rows": report["raw_rows"],
        "duplicates_removed": report.get("exact_duplicate_rows_removed", 0),
        "missing_values_handled": sum(report.get(k, 0) for k in missing_keys),
        "invalid_values_flagged": sum(report.get(k, 0) for k in invalid_keys),
        "rows_removed": report["rows_removed"],
        "rows_retained": report["rows_retained"],
        "rows_repaired_or_flagged": sum(report.get(k, 0) for k in repaired_keys),
    }


def main():
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    cleaning_rows = []

    log.info("Cleaning transactions from RAW csv...")
    txn_df, txn_report = clean_transactions()
    log.info("transactions: raw=%d retained=%d removed=%d", txn_report["raw_rows"], txn_report["rows_retained"], txn_report["rows_removed"])
    _parquet_safe(txn_df).to_parquet(CLEAN_TRANSACTIONS, index=False)
    cleaning_rows.append(build_cleaning_report_row(txn_report))

    log.info("Cleaning KYC records from RAW csv...")
    kyc_df, kyc_report = clean_kyc()
    log.info("kyc_records: raw=%d retained=%d removed=%d identity_collisions=%d",
              kyc_report["raw_rows"], kyc_report["rows_retained"], kyc_report["rows_removed"],
              kyc_report["user_id_identity_collision_rows"])
    _parquet_safe(kyc_df).to_parquet(CLEAN_KYC, index=False)
    cleaning_rows.append(build_cleaning_report_row(kyc_report))

    log.info("Cleaning merchant master from RAW csv...")
    mer_df, mer_report = clean_merchants()
    log.info("merchants_master: raw=%d retained=%d removed=%d identity_collisions=%d",
              mer_report["raw_rows"], mer_report["rows_retained"], mer_report["rows_removed"],
              mer_report["merchant_id_identity_collision_rows"])
    _parquet_safe(mer_df).to_parquet(CLEAN_MERCHANTS, index=False)
    cleaning_rows.append(build_cleaning_report_row(mer_report))

    log.info("Cleaning chargebacks from RAW json...")
    cb_df, cb_report = clean_chargebacks()
    log.info("chargebacks: raw=%d retained=%d removed=%d", cb_report["raw_rows"], cb_report["rows_retained"], cb_report["rows_removed"])
    _parquet_safe(cb_df).to_parquet(CLEAN_CHARGEBACKS, index=False)
    cleaning_rows.append(build_cleaning_report_row(cb_report))

    cleaning_report_df = pd.DataFrame(cleaning_rows)
    cleaning_report_path = REPORTS_DIR / "cleaning_report.csv"
    cleaning_report_df.to_csv(cleaning_report_path, index=False)
    log.info("Wrote %s", cleaning_report_path)

    # Detailed per-field report (superset of the summary above)
    detail_rows = []
    for report in (txn_report, kyc_report, mer_report, cb_report):
        for k, v in report.items():
            if k == "dataset":
                continue
            detail_rows.append({"dataset": report["dataset"], "metric": k, "value": v})
    pd.DataFrame(detail_rows).to_csv(REPORTS_DIR / "cleaning_report_detail.csv", index=False)

    # data_quality_after.csv - same shape as data_quality_before.csv but on cleaned data
    dq_rows = []
    for name, df in [("transactions", txn_df), ("kyc_records", kyc_df), ("merchants_master", mer_df), ("chargebacks", cb_df)]:
        dup_rows = df.duplicated().sum()
        for col in df.columns:
            null_ct = df[col].isnull().sum()
            dq_rows.append({
                "dataset": name, "column": col, "row_count": len(df),
                "null_count": int(null_ct), "null_pct": round(null_ct / len(df) * 100, 2),
                "unique_count": int(df[col].nunique(dropna=True)),
                "duplicate_full_rows_in_dataset": int(dup_rows),
            })
    pd.DataFrame(dq_rows).to_csv(REPORTS_DIR / "data_quality_after.csv", index=False)
    log.info("Wrote %s", REPORTS_DIR / "data_quality_after.csv")

    print("\n=== CLEANING SUMMARY ===")
    print(cleaning_report_df.to_string(index=False))
    log.info("Pipeline complete.")


if __name__ == "__main__":
    main()
