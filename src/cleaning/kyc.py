"""
Cleaning pipeline for track1_kyc_records.csv.

Per DATA_AUDIT.md Open Question #1: user_id is NOT a safe unique key in
this dataset even for exact-string duplicates (85% of duplicate-key
groups contain rows with different name/PAN). This cleaner therefore:
  - does NOT deduplicate down to one-row-per-user_id (that would
    silently discard distinct real people),
  - keeps the grain at one row per raw KYC record,
  - adds an explicit `user_id_has_identity_collision` flag so any
    downstream join can see when a user_id is not a safe join key,
  - only drops rows that are 100% exact duplicates (same value in
    every column - a true re-submission of the same record).
"""
import re
import pandas as pd
from src.config import KYC_STATUS_MAP, RISK_SEGMENT_MAP, CITY_MAP, RAW_KYC
from src.utils.ids import normalize_user_id
from src.utils.amounts import clean_amount_series
from src.utils.dates import parse_timestamp_series

PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


def normalize_pan(value):
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None, "missing"
    s = str(value).strip().upper().replace(" ", "").replace("-", "")
    if s == "":
        return None, "missing"
    if PAN_RE.match(s):
        return s, "valid"
    return s, "invalid_format"


def normalize_aadhaar(value):
    """Preserve masked values (XXXX-XXXX-9999) as masked; normalize digit-only forms."""
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None, "missing"
    s = str(value).strip()
    if s == "":
        return None, "missing"
    if "X" in s.upper():
        return s.upper().replace(" ", ""), "masked"
    digits = re.sub(r"\D", "", s)
    if len(digits) == 12:
        return digits, "valid"
    return digits, "invalid_length"


def normalize_city(value):
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None
    key = str(value).strip().lower()
    return CITY_MAP.get(key, str(value).strip().title())


def normalize_kyc_status(value):
    key = str(value).strip().lower()
    return KYC_STATUS_MAP.get(key, f"UNKNOWN:{value}")


def normalize_risk_segment(value):
    key = str(value).strip().lower()
    return RISK_SEGMENT_MAP.get(key, f"UNKNOWN:{value}")


def clean_kyc(raw_path=RAW_KYC):
    report = {"dataset": "kyc_records"}
    df = pd.read_csv(raw_path, dtype=str)
    report["raw_rows"] = len(df)

    exact_dup_mask = df.duplicated(keep="first")
    report["exact_duplicate_rows_removed"] = int(exact_dup_mask.sum())
    df = df[~exact_dup_mask].copy()

    # --- user_id -------------------------------------------------------
    df["user_id_raw"] = df["user_id"]
    df["user_id"] = df["user_id"].apply(normalize_user_id)
    collision = df["user_id"].duplicated(keep=False)
    df["user_id_has_identity_collision"] = collision
    report["user_id_identity_collision_rows"] = int(collision.sum())

    # --- PAN -------------------------------------------------------------
    pan_parsed = df["pan"].apply(normalize_pan)
    df["pan_raw"] = df["pan"]
    df["pan"] = pan_parsed.apply(lambda t: t[0])
    df["pan_status"] = pan_parsed.apply(lambda t: t[1])
    report["pan_missing"] = int((df["pan_status"] == "missing").sum())
    report["pan_invalid_format"] = int((df["pan_status"] == "invalid_format").sum())

    # --- Aadhaar --------------------------------------------------------
    aad_parsed = df["aadhaar"].apply(normalize_aadhaar)
    df["aadhaar_raw"] = df["aadhaar"]
    df["aadhaar"] = aad_parsed.apply(lambda t: t[0])
    df["aadhaar_status"] = aad_parsed.apply(lambda t: t[1])
    report["aadhaar_missing"] = int((df["aadhaar_status"] == "missing").sum())
    report["aadhaar_masked"] = int((df["aadhaar_status"] == "masked").sum())
    report["aadhaar_invalid_length"] = int((df["aadhaar_status"] == "invalid_length").sum())

    # --- date_of_birth ----------------------------------------------------
    dob = parse_timestamp_series(df["date_of_birth"])
    df["date_of_birth_raw"] = df["date_of_birth"]
    df["date_of_birth"] = dob["clean"].dt.date.astype("string")
    report["dob_missing"] = int(df["date_of_birth"].isnull().sum() - dob["is_invalid"].sum())
    report["dob_invalid_unparseable"] = int(dob["is_invalid"].sum())
    # impossible-age flag (age<13 or age>100 at "now") — flagged, not silently dropped
    now = pd.Timestamp.now(tz="Asia/Kolkata")
    age_years = (now - dob["clean"]).dt.days / 365.25
    df["age_years"] = age_years.round(1)
    implausible_age = (age_years < 13) | (age_years > 100)
    df["dob_implausible_age_flag"] = implausible_age.fillna(False)
    report["dob_implausible_age_flagged"] = int(implausible_age.fillna(False).sum())

    # --- monthly_income -----------------------------------------------
    inc = clean_amount_series(df["monthly_income"])
    df["monthly_income_raw"] = df["monthly_income"]
    df["monthly_income"] = inc["clean"]
    report["income_missing_blank"] = int((df["monthly_income_raw"].isnull()).sum())
    report["income_disguised_null"] = int(inc["is_disguised_null"].sum())
    report["income_invalid_unparseable"] = int(inc["is_invalid"].sum())

    # --- city / state ------------------------------------------------------
    df["city_raw"] = df["city"]
    df["city"] = df["city"].apply(normalize_city)
    df["state"] = df["state"].str.strip().str.title()

    # --- occupation --------------------------------------------------------
    df["occupation"] = df["occupation"].str.strip().str.title()

    # --- signup_timestamp -------------------------------------------------
    su = parse_timestamp_series(df["signup_timestamp"])
    df["signup_timestamp_raw"] = df["signup_timestamp"]
    df["signup_timestamp"] = su["clean"]
    report["signup_missing"] = int(df["signup_timestamp_raw"].isnull().sum())
    report["signup_invalid_unparseable"] = int(su["is_invalid"].sum())

    # --- kyc_status / risk_segment -----------------------------------
    df["kyc_status_raw"] = df["kyc_status"]
    df["kyc_status"] = df["kyc_status"].apply(normalize_kyc_status)
    df["risk_segment_raw"] = df["risk_segment"]
    df["risk_segment"] = df["risk_segment"].apply(normalize_risk_segment)

    report["rows_retained"] = len(df)
    report["rows_removed"] = report["raw_rows"] - report["rows_retained"]
    return df, report


if __name__ == "__main__":
    df, report = clean_kyc()
    print(report)
    print(df.head())
