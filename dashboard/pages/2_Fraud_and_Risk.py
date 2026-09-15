import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import plotly.express as px

from data_loader import data_available, get_transactions, get_user_risk, get_merchant_risk, get_kyc_inconsistency
from components.filters import empty_state

st.set_page_config(page_title="Fraud & Risk", page_icon="🛡️", layout="wide")
st.title("Fraud & Risk — Explainable Scoring Engine")
# st.caption(
#     "Every score below is rule-based and fully explainable — no black-box model. "
#     "Scores use cautious terminology ('potential risk', 'requires investigation') "
#     "because this dataset contains no confirmed fraud ground-truth label."
# )

if not data_available():
    st.error("No cleaned data found.")
    st.stop()

user_risk = get_user_risk()
merchant_risk = get_merchant_risk()

tab1, tab2, tab3 = st.tabs(["User Risk", "Merchant Risk", "KYC Inconsistencies"])

with tab1:
    st.subheader("User risk distribution")
    level_counts = user_risk["risk_level"].value_counts().reindex(["LOW", "MEDIUM", "HIGH", "CRITICAL"]).fillna(0).reset_index()
    level_counts.columns = ["risk_level", "count"]
    fig = px.bar(level_counts, x="risk_level", y="count", title="Users by risk level",
                 color="risk_level", color_discrete_map={"LOW": "#2ca02c", "MEDIUM": "#ff7f0e", "HIGH": "#d62728", "CRITICAL": "#8b0000"})
    st.plotly_chart(fig, width='stretch')

    level_filter = st.multiselect("Filter by risk level", ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                                   default=["MEDIUM", "HIGH", "CRITICAL"], key="user_risk_level_filter")
    flagged_users = user_risk[user_risk["risk_level"].isin(level_filter)] if level_filter else user_risk
    if flagged_users.empty:
        empty_state("No users match the selected risk levels.")
    else:
        st.markdown(f"**{len(flagged_users):,} users** match the selected risk level(s).")
        display = flagged_users.copy()
        display["risk_reasons"] = display["risk_reasons"].apply(lambda r: "; ".join(r) if r else "")
        st.dataframe(display.head(200), width='stretch')

with tab2:
    st.subheader("Merchant risk distribution")
    level_counts_m = merchant_risk["risk_level"].value_counts().reindex(["LOW", "MEDIUM", "HIGH", "CRITICAL"]).fillna(0).reset_index()
    level_counts_m.columns = ["risk_level", "count"]
    fig2 = px.bar(level_counts_m, x="risk_level", y="count", title="Merchants by risk level (min. 5 transactions)",
                  color="risk_level", color_discrete_map={"LOW": "#2ca02c", "MEDIUM": "#ff7f0e", "HIGH": "#d62728", "CRITICAL": "#8b0000"})
    st.plotly_chart(fig2, width='stretch')

    high_risk_m = merchant_risk[merchant_risk["risk_level"].isin(["HIGH", "CRITICAL"])]
    st.markdown(f"**{len(high_risk_m):,} merchants** flagged HIGH or CRITICAL.")
    if high_risk_m.empty:
        empty_state("No merchants currently flagged HIGH/CRITICAL.")
    else:
        for _, row in high_risk_m.head(15).iterrows():
            with st.expander(f"{row['merchant_id']} — {row['merchant_name'] or 'name unresolved (join coverage)'} — score {row['risk_score']} ({row['risk_level']})"):
                st.write(f"**Category**: {row['merchant_category'] or 'unresolved'}")
                st.write(f"**Transactions**: {row['transaction_count']} | **Chargebacks**: {row['chargeback_count']} | **Chargeback ratio**: {row['chargeback_ratio']:.1%} | **Failure rate**: {row['failure_rate']:.1%}")
                st.write("**Why flagged:**")
                for reason in row["risk_reasons"]:
                    st.write(f"- {reason}")

with tab3:
    st.subheader("KYC identity inconsistency indicators")
    # st.caption(
    #     "Potential synthetic-identity / data-quality indicators only — NOT a confirmed finding. "
    #     "Flags where a single normalized user_id maps to more than one distinct name/PAN, or "
    #     "where the PAN fails format validation."
    # )
    kyc_inc = get_kyc_inconsistency()
    if kyc_inc.empty:
        empty_state("No KYC inconsistencies flagged.")
    else:
        st.metric("Flagged user_id values", f"{len(kyc_inc):,}")
        st.dataframe(kyc_inc.head(200), width='stretch')
