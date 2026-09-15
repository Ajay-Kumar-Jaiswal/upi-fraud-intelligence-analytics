import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import (
    data_available, get_transactions, get_transaction_kpis, get_utr_quality,
    get_monthly_trend, get_failed_by_hour,
)
from components.filters import render_global_filters, apply_txn_filters, empty_state

st.set_page_config(page_title="Transaction Analytics", page_icon="📊", layout="wide")
st.title("Transaction Analytics")

if not data_available():
    st.error("No cleaned data found. Run `python scripts/run_pipeline.py` first.")
    st.stop()

txn = get_transactions()
filters = render_global_filters(txn)
filtered = apply_txn_filters(txn, filters)

if filtered.empty:
    empty_state()
    st.stop()

k = get_transaction_kpis()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Transactions", f"{k['total_transactions']:,}")
c2.metric("Average Value", f"₹{k['average_transaction_value']:,.0f}")
c3.metric("Median Value", f"₹{k['median_transaction_value']:,.0f}")
c4.metric("Total Value", f"₹{k['total_transaction_value']:,.0f}")

st.markdown("### Status breakdown (filtered view)")
status_counts = filtered["status"].value_counts().reset_index()
status_counts.columns = ["status", "count"]
col1, col2 = st.columns([1, 1])
with col1:
    fig = px.bar(status_counts, x="status", y="count", title="Transactions by status",
                 labels={"status": "Status", "count": "Count"}, color="status")
    st.plotly_chart(fig, width='stretch')
with col2:
    fig2 = px.pie(status_counts, names="status", values="count", title="Status share", hole=0.4)
    st.plotly_chart(fig2, width='stretch')

st.markdown("### Amount distribution (filtered)")
fig3 = px.histogram(filtered, x="amount", nbins=50, title="Transaction amount distribution (₹)",
                     labels={"amount": "Amount (₹)"})
st.plotly_chart(fig3, width='stretch')

st.markdown("### Monthly trend (full dataset, not filter-limited — monthly granularity)")
monthly = get_monthly_trend()
fig4 = px.bar(monthly, x="month", y="transaction_count", title="Transactions per month",
              labels={"month": "Month", "transaction_count": "Transactions"})
st.plotly_chart(fig4, width='stretch')

st.markdown("### Failed-transaction rate by hour of day")
st.caption("Per dataset notes example question: 'Failed transaction trend by hour.'")
hourly = get_failed_by_hour()
fig5 = px.bar(hourly, x="hour", y="failed_rate_pct", title="Failure rate by hour (0–23, IST)",
              labels={"hour": "Hour of day", "failed_rate_pct": "Failure rate (%)"})
st.plotly_chart(fig5, width='stretch')

st.markdown("### Data quality: UTR completeness")
utr = get_utr_quality()
c1, c2 = st.columns(2)
c1.metric("UTR missing", f"{utr['utr_missing_count']:,} ({utr['utr_missing_rate_pct']}%)")
c2.metric("UTR invalid format", f"{utr['utr_invalid_format_count']:,} ({utr['utr_invalid_format_rate_pct']}%)")

with st.expander("Show filtered raw transaction sample (PII-safe columns only)"):
    safe_cols = ["txn_id", "timestamp", "user_id", "merchant_id", "amount", "status", "mcc"]
    st.dataframe(filtered[safe_cols].head(200), width='stretch')
