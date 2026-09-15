"""
Cached wrappers around the analytics/fraud/graph layer for the dashboard.

IMPORTANT: this file contains NO business logic of its own - every
function here just calls the already-tested Stage 5/6/7/8 functions and
adds Streamlit caching. This guarantees the dashboard can never disagree
with the underlying analytics (same code path, same source of truth:
data/processed/*.parquet).
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd

from src.config import CLEAN_TRANSACTIONS
from src.analytics.loaders import load_transactions, load_users, load_merchants, load_chargebacks
from src.analytics.transactions_kpi import transaction_kpis, utr_quality_kpis
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
from src.analytics.business_insights import executive_summary, top_strategic_insights
from src.fraud.risk_engine import user_risk_scores, merchant_risk_scores, kyc_inconsistency_risk
from src.graph.network_analysis import (
    build_transaction_graph, graph_summary_stats, high_degree_nodes,
    repeated_relationship_pairs, connected_components_summary, dense_merchant_clusters, cycle_detection,
)


def data_available() -> bool:
    """Checked at the top of every page so the app degrades gracefully
    (per brief §34) if the pipeline hasn't been run yet, instead of a
    raw stack trace."""
    return CLEAN_TRANSACTIONS.exists()


@st.cache_data(show_spinner="Loading transactions...")
def get_transactions() -> pd.DataFrame:
    return load_transactions()


@st.cache_data(show_spinner="Loading KYC records...")
def get_users() -> pd.DataFrame:
    return load_users()


@st.cache_data(show_spinner="Loading merchant master...")
def get_merchants() -> pd.DataFrame:
    return load_merchants()


@st.cache_data(show_spinner="Loading chargebacks...")
def get_chargebacks() -> pd.DataFrame:
    return load_chargebacks()


@st.cache_data(show_spinner=False)
def get_executive_summary():
    return executive_summary()


@st.cache_data(show_spinner=False)
def get_top_insights(n: int = 5):
    return top_strategic_insights(n)


@st.cache_data(show_spinner=False)
def get_transaction_kpis():
    return transaction_kpis()


@st.cache_data(show_spinner=False)
def get_utr_quality():
    return utr_quality_kpis()


@st.cache_data(show_spinner=False)
def get_chargeback_kpis():
    return chargeback_core_kpis(), chargeback_txn_join_coverage()


@st.cache_data(show_spinner=False)
def get_chargebacks_by(dimension: str):
    return chargebacks_by(dimension)


@st.cache_data(show_spinner=False)
def get_chargebacks_by_merchant(top_n: int = 20):
    return chargebacks_by_merchant(top_n)


@st.cache_data(show_spinner=False)
def get_top_disputed_users(top_n: int = 10):
    return top_users_by_disputed_amount(top_n)


@st.cache_data(show_spinner=False)
def get_dispute_delay_kpis():
    return dispute_reporting_delay_kpis()


@st.cache_data(show_spinner="Resolving merchant categories (join-coverage limited)...")
def get_merchant_category_performance():
    return merchant_category_performance(), merchant_category_join_coverage()


@st.cache_data(show_spinner=False)
def get_bonus_answer():
    return bonus_question_highest_chargeback_ratio_category()


@st.cache_data(show_spinner="Resolving merchant-master join...")
def get_merchant_ranking(top_n: int = 50):
    return merchant_master_enriched_ranking(top_n), merchant_master_join_coverage()


@st.cache_data(show_spinner=False)
def get_top_risky_merchants(min_txn: int = 5, top_n: int = 20):
    return top_merchants_by_chargeback_ratio(min_txn, top_n)


@st.cache_data(show_spinner="Resolving KYC join...")
def get_kyc_population():
    return kyc_population_kpis()


@st.cache_data(show_spinner=False)
def get_kyc_join_coverage():
    return kyc_join_coverage()


@st.cache_data(show_spinner=False)
def get_kyc_behavior():
    return transaction_behavior_by_kyc_status()


@st.cache_data(show_spinner=False)
def get_synthetic_identity_check():
    return suspicious_identity_indicators()


@st.cache_data(show_spinner=False)
def get_daily_trend():
    return daily_transaction_trend()


@st.cache_data(show_spinner=False)
def get_monthly_trend():
    return monthly_transaction_trend()


@st.cache_data(show_spinner=False)
def get_failed_by_hour():
    return failed_transaction_trend_by_hour()


@st.cache_data(show_spinner=False)
def get_daily_chargeback_trend():
    return daily_chargeback_trend()


@st.cache_data(show_spinner=False)
def get_date_range_summary():
    return data_date_range_summary()


@st.cache_data(show_spinner=False)
def get_advanced_insights():
    return {
        "utr_vs_status": utr_missing_vs_status(),
        "concentration": chargeback_concentration(),
        "negative_amount": negative_amount_status_correlation(),
        "repeat_users": repeated_chargeback_users(),
    }


@st.cache_data(show_spinner="Scoring user risk (explainable rules engine)...")
def get_user_risk():
    return user_risk_scores()


@st.cache_data(show_spinner="Scoring merchant risk (explainable rules engine)...")
def get_merchant_risk():
    return merchant_risk_scores()


@st.cache_data(show_spinner=False)
def get_kyc_inconsistency():
    return kyc_inconsistency_risk()


@st.cache_resource(show_spinner="Building transaction graph...")
def get_graph():
    return build_transaction_graph()


@st.cache_data(show_spinner=False)
def get_graph_stats():
    return graph_summary_stats(get_graph())


@st.cache_data(show_spinner=False)
def get_high_degree_nodes(top_n: int = 20):
    return high_degree_nodes(get_graph(), top_n)


@st.cache_data(show_spinner=False)
def get_repeated_relationships(min_txn: int = 2, top_n: int = 20):
    return repeated_relationship_pairs(min_txn, top_n)


@st.cache_data(show_spinner=False)
def get_connected_components():
    return connected_components_summary(get_graph())


@st.cache_data(show_spinner=False)
def get_dense_clusters(min_shared: int = 2, top_n: int = 15):
    return dense_merchant_clusters(min_shared, top_n)


@st.cache_data(show_spinner=False)
def get_cycle_detection():
    return cycle_detection()
