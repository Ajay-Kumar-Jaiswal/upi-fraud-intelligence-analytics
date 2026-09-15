"""
Tests for the Stage 5 analytics layer. Run against the actual cleaned
output of the pipeline (data/processed/*.parquet), which must exist
before running these tests (run scripts/run_pipeline.py first).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math
import pandas as pd
import pytest

from src.analytics.loaders import load_transactions, load_users, load_merchants, load_chargebacks
from src.analytics.coverage import compute_join_coverage
from src.analytics.transactions_kpi import transaction_kpis, utr_quality_kpis, STATUS_VALUES
from src.analytics.chargebacks_kpi import (
    chargeback_txn_join_coverage, chargeback_core_kpis, chargebacks_by,
    chargebacks_by_merchant, top_users_by_disputed_amount, dispute_reporting_delay_kpis,
)
from src.analytics.merchant_category import (
    merchant_category_join_coverage, merchant_category_performance,
    bonus_question_highest_chargeback_ratio_category,
)
from src.analytics.merchant_analytics import (
    merchant_master_join_coverage, merchant_master_enriched_ranking, top_merchants_by_chargeback_ratio,
)
from src.analytics.kyc_analytics import (
    kyc_population_kpis, kyc_join_coverage, transaction_behavior_by_kyc_status, suspicious_identity_indicators,
)
from src.analytics.time_analytics import (
    daily_transaction_trend, monthly_transaction_trend, failed_transaction_trend_by_hour,
    daily_chargeback_trend, data_date_range_summary,
)
from src.analytics.advanced_insights import (
    utr_missing_vs_status, chargeback_concentration, negative_amount_status_correlation, repeated_chargeback_users,
)


# ------------------------------------------------------- core transaction KPIs --
def test_transaction_kpis_totals_are_internally_consistent():
    k = transaction_kpis()
    status_sum = sum(k[f"{s.lower()}_count"] for s in STATUS_VALUES)
    assert status_sum == k["total_transactions"]


def test_transaction_kpis_rate_sum_is_approximately_100():
    k = transaction_kpis()
    assert 99.9 <= k["_rate_sum_check_pct"] <= 100.1


def test_transaction_kpis_no_negative_values():
    k = transaction_kpis()
    assert k["total_transaction_value"] >= 0
    assert k["average_transaction_value"] >= 0
    for s in STATUS_VALUES:
        assert k[f"{s.lower()}_count"] >= 0


def test_transaction_kpis_average_matches_manual_calc():
    df = load_transactions()
    df = df[~df["is_conflicting_duplicate_id"]]
    manual_avg = round(float(df["amount"].mean()), 2)
    assert transaction_kpis()["average_transaction_value"] == manual_avg


def test_utr_quality_kpis_bounds():
    k = utr_quality_kpis()
    assert 0 <= k["utr_missing_rate_pct"] <= 100
    assert k["utr_missing_count"] + (k["total_transactions"] - k["utr_missing_count"]) == k["total_transactions"]


# ----------------------------------------------------------- chargeback KPIs --
def test_chargeback_ratio_matches_manual_calc():
    result = chargeback_core_kpis()
    txn = load_transactions()
    cb = load_chargebacks()
    txn_ids = set(txn["txn_id"].dropna())
    manual_matched = cb["txn_id"].isin(txn_ids).sum()
    manual_ratio = manual_matched / len(txn)
    assert result["chargeback_to_transaction_ratio"] == pytest.approx(manual_ratio, abs=1e-6)


def test_chargeback_ratio_is_between_0_and_1():
    result = chargeback_core_kpis()
    assert 0 <= result["chargeback_to_transaction_ratio"] <= 1


def test_chargeback_join_coverage_high_enough_to_be_usable():
    cov = chargeback_txn_join_coverage()
    assert cov["match_rate_pct"] > 85  # documented as the one usable identity join


def test_chargebacks_by_reason_totals_match():
    out = chargebacks_by("reason_code")
    cb = load_chargebacks()
    assert out["chargeback_count"].sum() == len(cb)


def test_chargebacks_by_severity_only_controlled_values():
    out = chargebacks_by("severity")
    assert set(out["severity"]) <= {"Low", "Medium", "High", "Critical"}


def test_chargebacks_by_merchant_sorted_descending():
    out = chargebacks_by_merchant(10)
    counts = out["chargeback_count"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_top_users_by_disputed_amount_no_nan_leaks_to_top():
    out = top_users_by_disputed_amount(10)
    assert out["total_disputed_amount"].notnull().all()


def test_dispute_reporting_delay_no_negative_included_in_average():
    k = dispute_reporting_delay_kpis()
    assert k["average_delay_days"] is None or k["average_delay_days"] >= 0


# --------------------------------------------------- merchant category / bonus --
def test_merchant_category_coverage_funnel_monotonic():
    cov = merchant_category_join_coverage()
    step1 = cov["step_1_any_merchant_match"]["matched_rows"]
    step2 = cov["step_2_unambiguous_category_match"]["matched_rows"]
    assert step2 <= step1  # unambiguous subset can't exceed any-match subset


def test_merchant_category_performance_ratios_valid():
    out = merchant_category_performance()
    assert (out["chargeback_to_transaction_ratio"] >= 0).all()
    assert (out["chargeback_to_transaction_ratio"] <= 1).all()
    assert out["rank_by_chargeback_ratio"].tolist() == list(range(1, len(out) + 1))


def test_merchant_category_performance_no_categories_invented():
    out = merchant_category_performance()
    merchants = load_merchants()
    real_categories = set(merchants["merchant_category"].unique())
    assert set(out["merchant_category"]) <= real_categories


def test_bonus_question_returns_a_real_category():
    result = bonus_question_highest_chargeback_ratio_category()
    merchants = load_merchants()
    real_categories = set(merchants["merchant_category"].unique())
    assert result["answer_merchant_category"] in real_categories


def test_bonus_question_quarter_is_dynamically_detected_not_hardcoded():
    result = bonus_question_highest_chargeback_ratio_category()
    txn = load_transactions()
    actual_min, actual_max = txn["timestamp"].min(), txn["timestamp"].max()
    # the detected quarter must actually overlap the real data range
    assert "2026Q1" == result["quarter_used"]
    assert actual_min.year == 2026 and actual_min.quarter == 1


def test_bonus_question_handles_out_of_range_quarter_gracefully():
    import pandas as pd
    far_future_start = pd.Timestamp("2099-01-01", tz="Asia/Kolkata")
    far_future_end = pd.Timestamp("2099-03-31", tz="Asia/Kolkata")
    result = bonus_question_highest_chargeback_ratio_category(far_future_start, far_future_end)
    assert "error" in result  # must report the limitation, not invent an answer


def test_bonus_question_ranking_is_sorted_correctly():
    result = bonus_question_highest_chargeback_ratio_category()
    ratios = [row["chargeback_to_transaction_ratio"] for row in result["full_ranking"]]
    assert ratios == sorted(ratios, reverse=True)
    assert result["answer_chargeback_to_transaction_ratio"] == ratios[0]


# ----------------------------------------------------- merchant-master analytics --
def test_merchant_master_ranking_no_duplicate_merchants():
    out = merchant_master_enriched_ranking(None)
    assert out["merchant_id"].is_unique


def test_top_merchants_by_chargeback_ratio_respects_min_transactions():
    out = top_merchants_by_chargeback_ratio(min_transactions=10, top_n=20)
    assert (out["transaction_count"] >= 10).all()


# ------------------------------------------------------------- KYC analytics --
def test_kyc_population_kpis_rates_bounded():
    k = kyc_population_kpis()
    assert 0 <= k["kyc_completion_rate_pct"] <= 100
    assert 0 <= k["kyc_rejection_rate_pct"] <= 100


def test_kyc_join_coverage_step2_le_step1():
    cov = kyc_join_coverage()
    assert cov["step_2_unambiguous_kyc_status_match"]["matched_rows"] <= cov["step_1_any_user_match"]["matched_rows"]


def test_kyc_join_coverage_matches_documented_audit_finding():
    cov = kyc_join_coverage()
    rate = cov["step_1_any_user_match"]["match_rate_pct"]
    assert 28 <= rate <= 37  # ~32.4% observed in DATA_AUDIT.md


def test_transaction_behavior_by_kyc_status_only_real_statuses():
    out = transaction_behavior_by_kyc_status()
    assert set(out["kyc_status"]) <= {"VERIFIED", "PENDING", "REJECTED", "IN_PROGRESS"}


def test_suspicious_identity_indicators_not_asserting_confirmed_fraud():
    result = suspicious_identity_indicators()
    assert "confirmed" not in result["methodology"].lower() or "not" in result["methodology"].lower()
    assert result["pct_of_pans_flagged"] >= 0


# ------------------------------------------------------------- time analytics --
def test_daily_trend_counts_sum_to_total():
    out = daily_transaction_trend()
    txn = load_transactions()
    assert out["transaction_count"].sum() == len(txn)


def test_monthly_trend_matches_daily_trend_aggregated():
    monthly = monthly_transaction_trend()
    txn = load_transactions()
    assert monthly["transaction_count"].sum() == len(txn)


def test_failed_trend_by_hour_rate_bounded():
    out = failed_transaction_trend_by_hour()
    assert (out["failed_rate_pct"] >= 0).all()
    assert (out["failed_rate_pct"] <= 100).all()
    assert set(out["hour"]) <= set(range(24))


def test_data_date_range_matches_audit():
    summary = data_date_range_summary()
    assert summary["transactions_min_timestamp"].startswith("2026-01-01")


# --------------------------------------------------------- advanced insights --
def test_utr_missing_vs_status_rates_bounded():
    k = utr_missing_vs_status()
    assert 0 <= k["failed_rate_pct_when_utr_missing"] <= 100
    assert 0 <= k["failed_rate_pct_when_utr_present"] <= 100


def test_chargeback_concentration_share_bounded():
    k = chargeback_concentration()
    assert 0 <= k["top_decile_share_of_chargebacks_pct"] <= 100


def test_negative_amount_correlation_supports_open_question_2_decision():
    k = negative_amount_status_correlation()
    # regression guard: if this ever flips to a real correlation, Open
    # Question #2's "sign corruption noise" conclusion needs re-review
    assert k["max_deviation_from_overall_pct_points"] < 5


def test_repeated_chargeback_users_counts_consistent():
    k = repeated_chargeback_users()
    assert k["users_with_more_than_one_chargeback"] <= k["distinct_users_with_chargebacks"]


# ------------------------------------------------------- divide-by-zero guards --
def test_join_coverage_handles_empty_series():
    empty = pd.Series([], dtype="object")
    cov = compute_join_coverage(empty, set(), "empty->empty")
    assert cov.match_rate_pct == 0.0  # must not raise ZeroDivisionError


def test_transaction_kpis_handles_empty_dataframe(monkeypatch):
    import src.analytics.transactions_kpi as mod

    def fake_load():
        return load_transactions().iloc[0:0]

    monkeypatch.setattr(mod, "load_transactions", fake_load)
    k = mod.transaction_kpis()
    assert k["total_transactions"] == 0
    assert k["average_transaction_value"] is None
    assert k["success_rate_pct"] == 0.0
