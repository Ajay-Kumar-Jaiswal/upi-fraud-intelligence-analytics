"""
Cleaning pipeline for track1_upi_transactions.csv.

Every transformation is logged into a cleaning-report dict so the
before/after audit trail required by the brief is reproducible, not
just eyeballed once during development.
"""
import pandas as pd
from src.config import STATUS_MAP, RAW_TRANSACTIONS
from src.utils.ids import normalize_user_id, normalize_merchant_id, normalize_txn_id
from src.utils.amounts import clean_amount_series
from src.utils.dates import parse_timestamp_series


def normalize_mcc(value):
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    digits = s.lstrip("0")
    return digits if digits else "0"


def normalize_status(value):
    if value is None:
        return None
    key = str(value).strip().lower()
    return STATUS_MAP.get(key, f"UNKNOWN:{value}")


def clean_transactions(raw_path=RAW_TRANSACTIONS):
    report = {"dataset": "transactions"}
    df = pd.read_csv(raw_path, dtype=str)
    report["raw_rows"] = len(df)

    # --- exact duplicate rows -------------------------------------------------
    exact_dup_mask = df.duplicated(keep="first")
    report["exact_duplicate_rows_removed"] = int(exact_dup_mask.sum())
    df = df[~exact_dup_mask].copy()

    # --- IDs --------------------------------------------------------------
    df["txn_id"] = df["txn_id"].apply(normalize_txn_id)
    df["user_id"] = df["user_id"].apply(normalize_user_id)
    df["merchant_id"] = df["merchant_id"].apply(normalize_merchant_id)

    # any txn_id collision remaining after exact-dup removal is a genuine
    # conflicting-duplicate and must NOT be silently dropped -> flag it.
    remaining_dup_ids = df["txn_id"].duplicated(keep=False)
    report["conflicting_duplicate_txn_id_rows"] = int(remaining_dup_ids.sum())
    df["is_conflicting_duplicate_id"] = remaining_dup_ids

    # --- amount -------------------------------------------------------------
    amt = clean_amount_series(df["amount"])
    df["amount_raw"] = df["amount"]
    df["amount"] = amt["clean"]
    df["amount_had_negative_sign"] = amt["had_negative_sign"]
    report["amount_invalid_unparseable"] = int(amt["is_invalid"].sum())
    report["amount_negative_sign_flagged"] = int(amt["had_negative_sign"].sum())

    # --- timestamp ----------------------------------------------------------
    ts = parse_timestamp_series(df["timestamp"])
    df["timestamp_raw"] = df["timestamp"]
    df["timestamp"] = ts["clean"]
    df["timestamp_was_epoch"] = ts["was_epoch"]
    report["timestamp_invalid_unparseable"] = int(ts["is_invalid"].sum())
    report["timestamp_epoch_converted"] = int(ts["was_epoch"].sum())

    # --- utr ------------------------------------------------------------
    df["utr_raw"] = df["utr"]
    df["utr"] = df["utr"].apply(
        lambda v: None if pd.isnull(v) or str(v).strip() == "" else str(v).replace(" ", "").replace("-", "").upper()
    )
    report["utr_missing"] = int(df["utr"].isnull().sum())
    invalid_utr = df["utr"].notnull() & ~df["utr"].str.match(r"^UTR\d+$", na=False)
    df["utr_is_invalid_format"] = invalid_utr
    report["utr_invalid_format"] = int(invalid_utr.sum())

    # --- mcc ------------------------------------------------------------
    df["mcc_raw"] = df["mcc"]
    df["mcc"] = df["mcc"].apply(normalize_mcc)
    report["mcc_missing"] = int(df["mcc"].isnull().sum())

    # --- status -----------------------------------------------------------
    df["status_raw"] = df["status"]
    df["status"] = df["status"].apply(normalize_status)
    unknown_status = df["status"].str.startswith("UNKNOWN:")
    report["status_unrecognized_values"] = int(unknown_status.sum())

    # --- validation-ready output -------------------------------------
    df = df[[
        "txn_id", "timestamp", "user_id", "merchant_id", "amount", "utr", "mcc", "status",
        "amount_raw", "amount_had_negative_sign",
        "timestamp_raw", "timestamp_was_epoch",
        "utr_raw", "utr_is_invalid_format",
        "mcc_raw",
        "status_raw",
        "is_conflicting_duplicate_id",
    ]]

    report["rows_retained"] = len(df)
    report["rows_removed"] = report["raw_rows"] - report["rows_retained"]
    return df, report


if __name__ == "__main__":
    df, report = clean_transactions()
    print(report)
    print(df.head())
