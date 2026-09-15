import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import (
    data_available, get_merchant_category_performance, get_bonus_answer,
    get_merchant_ranking, get_top_risky_merchants,
)
from components.filters import coverage_badge, empty_state

st.set_page_config(page_title="Merchant Intelligence", page_icon="🏪", layout="wide")
st.title("Merchant Intelligence")

if not data_available():
    st.error("No cleaned data found.")
    st.stop()

cat_perf, cat_cov = get_merchant_category_performance()
coverage_badge(cat_cov["step_2_unambiguous_category_match"]["match_rate_pct"], "Merchant-category join")

st.markdown("### 🎯 Bonus question: highest chargeback-to-transaction ratio by category, this quarter")
bonus = get_bonus_answer()
c1, c2, c3 = st.columns(3)
c1.metric("Answer", bonus["answer_merchant_category"])
c2.metric("Chargeback ratio", f"{bonus['answer_chargeback_to_transaction_ratio']:.2%}")
c3.metric("Quarter", bonus["quarter_used"])
st.caption(bonus["caveat"])

st.markdown("### Merchant category performance")
if cat_perf.empty:
    empty_state()
else:
    fig = px.bar(cat_perf.sort_values("chargeback_to_transaction_ratio"), x="chargeback_to_transaction_ratio",
                 y="merchant_category", orientation="h", title="Chargeback-to-transaction ratio by category",
                 labels={"chargeback_to_transaction_ratio": "Chargeback ratio", "merchant_category": "Category"})
    st.plotly_chart(fig, width='stretch')

    fig2 = px.bar(cat_perf.sort_values("transaction_value", ascending=False), x="merchant_category", y="transaction_value",
                  title="Transaction value by category (₹)", labels={"merchant_category": "Category", "transaction_value": "Value (₹)"})
    st.plotly_chart(fig2, width='stretch')

    st.dataframe(cat_perf, width='stretch')

st.markdown("---")
st.markdown("### Merchant ranking (master-enriched)")
ranking, mm_cov = get_merchant_ranking(50)
coverage_badge(mm_cov["match_rate_pct"], "Merchant-master join (any attribute)")
if ranking.empty:
    empty_state()
else:
    st.dataframe(ranking, width='stretch')

st.markdown("---")
st.markdown("### Top merchants by chargeback ratio (min. 5 transactions)")
top_risky = get_top_risky_merchants(5, 20)
if top_risky.empty:
    empty_state()
else:
    fig3 = px.bar(top_risky.head(15), x="merchant_id", y="chargeback_to_transaction_ratio",
                  hover_data=["merchant_name", "transaction_count"],
                  title="Top 15 merchants by chargeback ratio", labels={"chargeback_to_transaction_ratio": "Chargeback ratio"})
    st.plotly_chart(fig3, width='stretch')
    st.dataframe(top_risky, width='stretch')
