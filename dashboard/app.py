import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import (
    data_available, get_transactions, get_executive_summary, get_top_insights,
    get_daily_trend, get_date_range_summary,
)
from components.filters import render_global_filters, apply_txn_filters, empty_state

st.set_page_config(page_title="UPI Fraud & Merchant Analytics — Executive Overview", page_icon="💳", layout="wide")

st.title("💳 UPI Fraud Ring & Merchant Analytics")
st.caption("TransOrg AgentIQ Datathon — Track 1: FinTech & BFSI — National Payments Authority view")

if not data_available():
    st.error(
        "No cleaned data found. Run `python scripts/run_pipeline.py` from the project root first, "
        "then restart this dashboard."
    )
    st.stop()

txn = get_transactions()
filters = render_global_filters(txn)
filtered = apply_txn_filters(txn, filters)

# st.sidebar.markdown("---")
# st.sidebar.markdown(
#     "**⚠️ Data completeness note**: user_id/merchant_id identity joins to KYC and "
#     "merchant-master cover only ~30–48% of transactions (verified, documented in "
#     "`reports/DATA_AUDIT.md`). Every KYC- or merchant-master-linked figure in this "
#     "dashboard displays its own coverage percentage — see the **Data Quality & "
#     "Coverage** page for the full picture."
# )

if filtered.empty:
    empty_state()
    st.stop()

summary = get_executive_summary()
date_range = get_date_range_summary()

st.subheader("Key Performance Indicators")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Transactions", f"{summary['total_transactions']:,}")
c2.metric("Total Transaction Value", f"₹{summary['total_transaction_value']:,.0f}")
c3.metric("Success Rate", f"{summary['success_rate_pct']}%")
c4.metric("Failed Rate", f"{summary['failed_rate_pct']}%")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Chargebacks", f"{summary['chargeback_count']:,}")
c6.metric("Chargeback Ratio", f"{summary['chargeback_ratio_pct']}%")
c7.metric("Disputed Amount", f"₹{summary['total_disputed_amount']:,.0f}")
c8.metric("High/Critical-Risk Merchants", f"{summary['high_or_critical_risk_merchants']:,}",
          help="From the explainable rule-based risk engine (Stage 6) — see Fraud & Risk page.")

st.markdown("---")
st.subheader("Transaction Trend (filtered)")
daily = get_daily_trend()
daily_f = daily[(daily["date"] >= filters["start_date"]) & (daily["date"] <= filters["end_date"])]
if daily_f.empty:
    empty_state()
else:
    fig = px.line(
        daily_f, x="date", y="transaction_count",
        title="Daily transaction count", labels={"date": "Date", "transaction_count": "Transactions"},
    )
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, width='stretch')

    fig2 = px.line(
        daily_f, x="date", y="transaction_value",
        title="Daily transaction value (₹)", labels={"date": "Date", "transaction_value": "Value (₹)"},
    )
    st.plotly_chart(fig2, width='stretch')

st.markdown("---")
st.subheader("Top Strategic Insights")
st.caption("Each insight below is directly computed from the cleaned data — click the source to see the exact function.")
for insight in get_top_insights(5):
    with st.expander(f"{insight['title']}"):
        st.write(insight["finding"])
        # st.code(insight["source"], language="text")

st.markdown("---")
st.caption(
    f"Data window: {date_range['transactions_min_timestamp']} → {date_range['transactions_max_timestamp']} "
    f"({txn['timestamp'].dt.date.nunique()} distinct days). "
    "Navigate using the sidebar pages for Transaction Analytics, Fraud & Risk, Merchant Intelligence, "
    "Chargebacks, Network Analysis, Data Quality & Coverage, and the AI Analyst."
)
