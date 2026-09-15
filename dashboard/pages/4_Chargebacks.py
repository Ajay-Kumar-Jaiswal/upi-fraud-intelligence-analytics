import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import (
    data_available, get_chargeback_kpis, get_chargebacks_by, get_chargebacks_by_merchant,
    get_top_disputed_users, get_dispute_delay_kpis, get_daily_chargeback_trend,
)
from components.filters import coverage_badge, empty_state

st.set_page_config(page_title="Chargebacks", page_icon="💳", layout="wide")
st.title("Chargeback Intelligence")

if not data_available():
    st.error("No cleaned data found. Run `python scripts/run_pipeline.py` first.")
    st.stop()

cb_k, cb_cov = get_chargeback_kpis()
coverage_badge(cb_cov["match_rate_pct"], "Chargeback → transaction join")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Chargebacks", f"{cb_k['chargeback_count_total']:,}")
c2.metric("Disputed Amount", f"₹{cb_k['total_disputed_amount']:,.0f}")
c3.metric("Chargeback Ratio", f"{cb_k['chargeback_rate_pct']}%")
c4.metric("Unmatched/Missing txn_id", f"{cb_k['chargeback_count_unmatched_or_missing_txn_id']:,}")

st.markdown("---")
tab1, tab2, tab3, tab4 = st.tabs(["By Reason", "By Severity", "By Status/Channel", "Top Disputed Users"])

with tab1:
    by_reason = get_chargebacks_by("reason_code")
    fig = px.bar(by_reason, x="reason_code", y="chargeback_count", title="Chargebacks by reason code",
                 labels={"reason_code": "Reason", "chargeback_count": "Count"})
    st.plotly_chart(fig, width='stretch')
    st.dataframe(by_reason, width='stretch')

with tab2:
    by_sev = get_chargebacks_by("severity")
    order = ["Low", "Medium", "High", "Critical"]
    by_sev["severity"] = by_sev["severity"].astype("category").cat.set_categories(order)
    by_sev = by_sev.sort_values("severity")
    fig2 = px.bar(by_sev, x="severity", y="chargeback_count", title="Chargebacks by severity",
                  color="severity", color_discrete_map={"Low": "#2ca02c", "Medium": "#ff7f0e", "High": "#d62728", "Critical": "#8b0000"})
    st.plotly_chart(fig2, width='stretch')
    st.caption("Severity P-code mapping (P1–P4) is a documented assumption — see src/config.SEVERITY_MAP and DATA_AUDIT.md.")

with tab3:
    col1, col2 = st.columns(2)
    with col1:
        by_status = get_chargebacks_by("resolution_status")
        fig3 = px.bar(by_status, x="resolution_status", y="chargeback_count", title="By resolution status")
        st.plotly_chart(fig3, width='stretch')
    with col2:
        by_channel = get_chargebacks_by("channel")
        fig4 = px.pie(by_channel, names="channel", values="chargeback_count", title="By reporting channel", hole=0.4)
        st.plotly_chart(fig4, width='stretch')

with tab4:
    top_users = get_top_disputed_users(15)
    if top_users.empty:
        empty_state()
    else:
        fig5 = px.bar(top_users, x="user_id", y="total_disputed_amount", title="Top 15 users by disputed amount (₹)")
        st.plotly_chart(fig5, width='stretch')
        st.dataframe(top_users, width='stretch')

st.markdown("---")
st.markdown("### Dispute reporting delay")
delay_k = get_dispute_delay_kpis()
c1, c2, c3 = st.columns(3)
c1.metric("Average delay", f"{delay_k['average_delay_days']} days")
c2.metric("Median delay", f"{delay_k['median_delay_days']} days")
c3.metric("Reported after 7+ days", f"{delay_k['disputes_reported_after_7_days']:,} ({delay_k['disputes_reported_after_7_days_pct_of_valid']}%)")

st.markdown("### Chargeback trend (by report date)")
trend = get_daily_chargeback_trend()
fig6 = px.line(trend, x="date", y="chargeback_count", title="Daily chargeback filings")
st.plotly_chart(fig6, width='stretch')
