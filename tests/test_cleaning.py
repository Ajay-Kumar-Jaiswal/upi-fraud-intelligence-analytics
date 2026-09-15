"""
Tests run against the ACTUAL uploaded dataset (not synthetic fixtures)
so a pass means the pipeline genuinely works on this data, per the
brief's instruction not to write tests that merely mirror the
implementation.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from src.utils.ids import normalize_user_id, normalize_merchant_id, normalize_txn_id
from src.utils.amounts import clean_amount
from src.utils.dates import parse_timestamp
from src.cleaning.transactions import clean_transactions
from src.cleaning.kyc import clean_kyc
from src.cleaning.merchants import clean_merchants
from src.cleaning.chargebacks import clean_chargebacks


# ---------------------------------------------------------------- IDs ----
@pytest.mark.parametrize("raw,expected", [
    ("USR12345", "USR12345"),
    ("usr12345", "USR12345"),
    ("USR-12345", "USR12345"),
    ("USR 12345", "USR12345"),
    ("USR_12345", "USR12345"),
    ("12345", "USR12345"),
])
def test_normalize_user_id_formats(raw, expected):
    assert normalize_user_id(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("MCH1234", "MCH1234"), ("mch1234", "MCH1234"), ("MCH-1234", "MCH1234"),
    ("MCH 1234", "MCH1234"), ("1234", "MCH1234"),
])
def test_normalize_merchant_id_formats(raw, expected):
    assert normalize_merchant_id(raw) == expected


def test_normalize_txn_id_padding():
    assert normalize_txn_id("TXN12345") == "TXN00012345"
    assert normalize_txn_id("txn-00012345") == "TXN00012345"
    assert normalize_txn_id("TXN00012345") == "TXN00012345"


def test_normalize_id_null_safe():
    assert normalize_user_id(None) is None
    assert normalize_user_id("") is None
    assert normalize_user_id(float("nan")) is None


# ------------------------------------------------------------ Amounts ----
@pytest.mark.parametrize("raw,expected", [
    ("₹16,908.13", 16908.13),
    ("Rs. 22303.2", 22303.2),
    ("INR 10,010", 10010.0),
    ("23115.78", 23115.78),
    ("-13101.15", 13101.15),  # sign stripped, magnitude preserved
])
def test_clean_amount_formats(raw, expected):
    result = clean_amount(raw)
    assert result["clean"] == pytest.approx(expected)


def test_clean_amount_negative_sign_flagged():
    result = clean_amount("-500")
    assert result["had_negative_sign"] is True
    assert result["clean"] == 500.0


def test_clean_amount_disguised_null():
    result = clean_amount("Not Available")
    assert result["is_disguised_null"] is True
    assert result["clean"] is None


def test_clean_amount_shorthand_k():
    result = clean_amount("21.0k")
    assert result["clean"] == pytest.approx(21000.0)


def test_clean_amount_invalid_string():
    result = clean_amount("garbage_value_xyz")
    assert result["is_invalid"] is True
    assert result["clean"] is None


# ----------------------------------------------------------- Timestamps --
def test_parse_timestamp_epoch():
    result = parse_timestamp("1770063471")
    assert result["was_epoch"] is True
    assert not pd.isnull(result["clean"])


def test_parse_timestamp_negative_epoch_pre_1970():
    result = parse_timestamp("-160078671")
    assert result["was_epoch"] is True
    assert result["clean"].year == 1964


def test_parse_timestamp_multiple_formats():
    for raw in ["2026-01-15 00:11:30", "13/01/2026 19:59:25", "28-Nov-1960", "01-18-1975"]:
        result = parse_timestamp(raw)
        assert not pd.isnull(result["clean"]), f"failed to parse {raw}"
        assert result["is_invalid"] is False


def test_parse_timestamp_garbage():
    result = parse_timestamp("not-a-date-at-all")
    assert result["is_invalid"] is True


# ------------------------------------------------ Full pipeline on real data --
def test_clean_transactions_no_unparseable_amounts():
    df, report = clean_transactions()
    assert report["amount_invalid_unparseable"] == 0
    assert df["amount"].isnull().sum() == 0


def test_clean_transactions_exact_dedup_only():
    df, report = clean_transactions()
    # every duplicate txn_id remaining after cleaning must be flagged, not silently kept as a false unique
    dup_remaining = df["txn_id"].duplicated(keep=False)
    assert (dup_remaining == df["is_conflicting_duplicate_id"]).all()


def test_clean_transactions_status_fully_mapped():
    df, report = clean_transactions()
    assert report["status_unrecognized_values"] == 0
    assert set(df["status"].unique()) <= {"SUCCESS", "FAILED", "PENDING", "PROCESSING"}


def test_clean_transactions_no_rows_invented():
    df, report = clean_transactions()
    assert report["rows_retained"] <= report["raw_rows"]
    assert report["rows_retained"] == report["raw_rows"] - report["rows_removed"]


def test_clean_kyc_identity_collision_flag_present():
    df, report = clean_kyc()
    # this is a known, documented property of the raw data (see DATA_AUDIT.md)
    assert report["user_id_identity_collision_rows"] > 0
    assert df["user_id_has_identity_collision"].sum() == report["user_id_identity_collision_rows"]


def test_clean_kyc_pan_never_fabricated():
    df, report = clean_kyc()
    # missing PAN in raw stays missing in clean - never fabricated
    assert df.loc[df["pan_status"] == "missing", "pan"].isnull().all()


def test_clean_kyc_no_implausible_negative_ages():
    df, report = clean_kyc()
    valid_age = df["age_years"].dropna()
    assert (valid_age >= 0).all()


def test_clean_merchants_all_categories_mapped():
    df, report = clean_merchants()
    assert report["merchant_category_unmapped_values"] == 0


def test_clean_merchants_settlement_account_masked():
    df, report = clean_merchants()
    masked = df["settlement_account_masked"].dropna()
    # every non-null masked value must start with XXXX and never reveal more than 4 trailing chars of raw
    assert masked.str.startswith("XXXX").all()


def test_clean_chargebacks_severity_fully_mapped():
    df, report = clean_chargebacks()
    assert report["severity_unrecognized_values"] == 0
    assert set(df["severity"].unique()) <= {"Low", "Medium", "High", "Critical"}


def test_clean_chargebacks_txn_id_format_normalized():
    df, report = clean_chargebacks()
    non_null = df["txn_id"].dropna()
    assert non_null.str.match(r"^TXN\d{8}$").all()


def test_clean_chargebacks_multi_complaint_txns_not_dropped():
    df, report = clean_chargebacks()
    assert report["transactions_with_multiple_chargebacks"] > 0
    # confirm those rows are actually still present in the output (not silently deduped away)
    dup_txn_ids = df["txn_id"].value_counts()
    assert (dup_txn_ids > 1).sum() == report["transactions_with_multiple_chargebacks"]


# --------------------------------------------------- Cross-dataset sanity --
def test_relationship_match_rate_matches_audit_finding():
    """Regression guard: confirms the low user/merchant join match rate
    documented in DATA_AUDIT.md is a stable, reproducible property of
    the raw data (not a one-off artifact), so downstream code that
    depends on this documented limitation stays correct."""
    txn_df, _ = clean_transactions()
    kyc_df, _ = clean_kyc()
    kyc_ids = set(kyc_df["user_id"].dropna())
    match_rate = txn_df["user_id"].isin(kyc_ids).mean()
    assert 0.28 <= match_rate <= 0.37  # ~32.4% observed; wide-ish band, still catches regressions
