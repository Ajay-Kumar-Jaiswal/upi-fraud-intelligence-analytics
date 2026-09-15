import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.fraud.risk_engine import (
    user_risk_scores, merchant_risk_scores, kyc_inconsistency_risk, _risk_level, RISK_LEVEL_BANDS,
)


def test_risk_level_bands_cover_0_to_100_with_no_gaps():
    for score in range(0, 101):
        level = _risk_level(score)
        assert level in RISK_LEVEL_BANDS


def test_user_risk_scores_bounded_0_to_100():
    df = user_risk_scores()
    assert (df["risk_score"] >= 0).all()
    assert (df["risk_score"] <= 100).all()


def test_user_risk_scores_every_flagged_user_has_reasons():
    df = user_risk_scores()
    flagged = df[df["risk_score"] > 0]
    assert (flagged["risk_reasons"].apply(len) > 0).all()


def test_user_risk_scores_zero_score_users_have_no_reasons():
    df = user_risk_scores()
    unflagged = df[df["risk_score"] == 0]
    assert (unflagged["risk_reasons"].apply(len) == 0).all()


def test_merchant_risk_scores_ratio_never_exceeds_1():
    """Regression guard for the bug found during Stage 6 testing: chargeback
    ratio must never exceed 1.0 - would indicate merchant_id was resolved
    incorrectly (mixing two independently-sourced merchant_id fields)."""
    df = merchant_risk_scores()
    assert (df["chargeback_ratio"] <= 1.0).all()
    assert (df["chargeback_ratio"] >= 0.0).all()


def test_merchant_risk_scores_respects_min_transaction_floor():
    from src.fraud.risk_engine import MIN_TRANSACTIONS_FOR_MERCHANT_RISK
    df = merchant_risk_scores()
    assert (df["transaction_count"] >= MIN_TRANSACTIONS_FOR_MERCHANT_RISK).all()


def test_merchant_risk_scores_bounded():
    df = merchant_risk_scores()
    assert (df["risk_score"] >= 0).all()
    assert (df["risk_score"] <= 100).all()


def test_merchant_risk_high_ratio_merchants_are_flagged():
    df = merchant_risk_scores()
    from src.fraud.risk_engine import HIGH_CHARGEBACK_RATIO_MERCHANT
    high_ratio = df[df["chargeback_ratio"] > HIGH_CHARGEBACK_RATIO_MERCHANT]
    if len(high_ratio):
        assert (high_ratio["risk_score"] > 0).all()


def test_kyc_inconsistency_risk_no_crash_and_flags_present():
    df = kyc_inconsistency_risk()
    assert "identity_collision_flag" in df.columns
    # this dataset is documented to have widespread identity collisions
    assert df["identity_collision_flag"].sum() > 0


def test_user_risk_no_duplicate_user_ids():
    df = user_risk_scores()
    assert df["user_id"].is_unique


def test_merchant_risk_no_duplicate_merchant_ids():
    df = merchant_risk_scores()
    assert df["merchant_id"].is_unique
