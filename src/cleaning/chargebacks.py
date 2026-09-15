"""
Cleaning pipeline for track1_chargebacks.json.

Per DATA_AUDIT.md: txn_id in this file appears in 3 formats (TXN00012345,
TXN12345, txn-00012345); normalizing to the zero-padded canonical form
(via normalize_txn_id, width=8) raises the match rate against
transactions from 89.4% to 93.0%. The severity P-code mapping in
config.SEVERITY_MAP is an explicit, documented ASSUMPTION (not stated
anywhere in the source data) - flagged again here at the point of use.
"""
import json
import pandas as pd
from src.config import SEVERITY_MAP, RESOLUTION_STATUS_MAP, CHANNEL_MAP, REASON_CODE_MAP, RAW_CHARGEBACKS
from src.utils.ids import normalize_user_id, normalize_merchant_id, normalize_txn_id
from src.utils.amounts import clean_amount_series
from src.utils.dates import parse_timestamp_series


def normalize_severity(value):
    key = str(value).strip().lower()
    return SEVERITY_MAP.get(key, f"UNKNOWN:{value}")


def normalize_resolution_status(value):
    key = str(value).strip().lower().replace("_", " ")
    return RESOLUTION_STATUS_MAP.get(key, f"UNKNOWN:{value}")


def normalize_channel(value):
    key = str(value).strip().lower()
    return CHANNEL_MAP.get(key, str(value).strip().title())


def normalize_reason_code(value):
    key = str(value).strip().lower()
    return REASON_CODE_MAP.get(key, str(value).strip().title())


def clean_chargebacks(raw_path=RAW_CHARGEBACKS):
    report = {"dataset": "chargebacks"}
    with open(raw_path) as f:
        raw = json.load(f)
    df = pd.DataFrame(raw)
    df = df.replace("", pd.NA)
    report["raw_rows"] = len(df)

    exact_dup_mask = df.duplicated(keep="first")
    report["exact_duplicate_rows_removed"] = int(exact_dup_mask.sum())
    df = df[~exact_dup_mask].copy()

    df["complaint_id"] = df["complaint_id"].str.strip()

    df["txn_id_raw"] = df["txn_id"]
    df["txn_id"] = df["txn_id"].apply(lambda v: normalize_txn_id(v) if pd.notnull(v) else None)
    report["txn_id_missing_blank"] = int(df["txn_id"].isnull().sum())

    # multiple complaints for the same (normalized) txn_id are NOT
    # deduplicated - spot-checked in DATA_AUDIT.md as genuine distinct
    # complaint records. Computed AFTER normalization so txn_id format
    # variants (TXN12345 vs TXN00012345 vs txn-00012345) that refer to
    # the same transaction are correctly counted together.
    multi_per_txn = df["txn_id"].notnull() & df.duplicated(subset="txn_id", keep=False)
    report["transactions_with_multiple_chargebacks"] = int(df.loc[multi_per_txn, "txn_id"].nunique())

    df["user_id_raw"] = df["user_id"]
    df["user_id"] = df["user_id"].apply(normalize_user_id)

    df["merchant_id_raw"] = df["merchant_id"]
    df["merchant_id"] = df["merchant_id"].apply(normalize_merchant_id)

    tt = parse_timestamp_series(df["transaction_timestamp"])
    df["transaction_timestamp_raw"] = df["transaction_timestamp"]
    df["transaction_timestamp"] = tt["clean"]
    report["transaction_timestamp_missing"] = int(df["transaction_timestamp_raw"].isnull().sum())
    report["transaction_timestamp_invalid"] = int(tt["is_invalid"].sum())

    rt = parse_timestamp_series(df["reported_timestamp"])
    df["reported_timestamp_raw"] = df["reported_timestamp"]
    df["reported_timestamp"] = rt["clean"]
    report["reported_timestamp_missing"] = int(df["reported_timestamp_raw"].isnull().sum())
    report["reported_timestamp_invalid"] = int(rt["is_invalid"].sum())

    br = parse_timestamp_series(df["bank_response_timestamp"])
    df["bank_response_timestamp_raw"] = df["bank_response_timestamp"]
    df["bank_response_timestamp"] = br["clean"]
    report["bank_response_timestamp_missing"] = int(df["bank_response_timestamp_raw"].isnull().sum())

    # reporting delay in days (transaction -> reported) — used later for
    # "disputes reported after long delays" insight. NaT-safe.
    df["report_delay_days"] = (df["reported_timestamp"] - df["transaction_timestamp"]).dt.total_seconds() / 86400.0

    da = clean_amount_series(df["disputed_amount"])
    df["disputed_amount_raw"] = df["disputed_amount"]
    df["disputed_amount"] = da["clean"]
    df["disputed_amount_had_negative_sign"] = da["had_negative_sign"]
    report["disputed_amount_missing_blank"] = int(df["disputed_amount_raw"].isnull().sum())
    report["disputed_amount_negative_flagged"] = int(da["had_negative_sign"].sum())

    df["reason_code_raw"] = df["reason_code"]
    df["reason_code"] = df["reason_code"].apply(normalize_reason_code)
    report["reason_code_distinct_after_cleaning"] = int(df["reason_code"].nunique())

    df["complaint_text"] = df["complaint_text"].str.strip()

    df["resolution_status_raw"] = df["resolution_status"]
    df["resolution_status"] = df["resolution_status"].apply(normalize_resolution_status)

    df["severity_raw"] = df["severity"]
    df["severity"] = df["severity"].apply(normalize_severity)
    unknown_sev = df["severity"].str.startswith("UNKNOWN:")
    report["severity_unrecognized_values"] = int(unknown_sev.sum())

    df["channel_raw"] = df["channel"]
    df["channel"] = df["channel"].apply(normalize_channel)

    report["rows_retained"] = len(df)
    report["rows_removed"] = report["raw_rows"] - report["rows_retained"]
    return df, report


if __name__ == "__main__":
    df, report = clean_chargebacks()
    print(report)
    print(df.head())
