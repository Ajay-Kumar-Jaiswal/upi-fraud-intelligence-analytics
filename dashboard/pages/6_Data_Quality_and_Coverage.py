import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from src.config import REPORTS_DIR
from data_loader import data_available, get_kyc_join_coverage
from data_loader import get_merchant_category_performance as _  # ensures merchant_category import path works

st.set_page_config(page_title="Data Quality & Coverage", page_icon="✅", layout="wide")
st.title("Data Quality & Coverage")
# st.caption(
#     "This page exists because the brief for this project explicitly requires transparency "
#     "about data-quality limitations rather than hiding them. Every number here is generated "
#     "by the pipeline, not hand-written."
# )

if not data_available():
    st.error("No cleaned data found.")
    st.stop()

cleaning_path = REPORTS_DIR / "cleaning_report.csv"
coverage_path = REPORTS_DIR / "join_coverage_report.csv"
dq_after_path = REPORTS_DIR / "data_quality_after.csv"

st.markdown("### Cleaning summary (raw → cleaned)")
if cleaning_path.exists():
    cleaning_df = pd.read_csv(cleaning_path)
    st.dataframe(cleaning_df, width='stretch')
    retention = (cleaning_df["rows_retained"] / cleaning_df["raw_rows"] * 100).round(2)
    fig = px.bar(x=cleaning_df["dataset"], y=retention, title="Row retention rate after cleaning (%)",
                 labels={"x": "Dataset", "y": "Retention %"})
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(fig, width='stretch')
else:
    st.caption("Cleaning report is not available.")

st.markdown("---")
st.markdown("### Identity-join coverage (the central data-quality limitation of this dataset)")
st.caption(
    "Identity-join coverage is limited. KYC- and merchant-master-enriched "
    "figures reflect only the matched transaction population shown below."
)
if coverage_path.exists():
    cov_df = pd.read_csv(coverage_path)
    fig2 = px.bar(cov_df, x="relationship", y="match_rate_pct", title="Join match rate by relationship (%)",
                  labels={"match_rate_pct": "Match rate (%)", "relationship": ""})
    fig2.update_layout(xaxis_tickangle=-30)
    fig2.update_yaxes(range=[0, 100])
    st.plotly_chart(fig2, width='stretch')
    st.dataframe(cov_df, width='stretch')
else:
    st.caption("Join coverage report is not available.")

st.markdown("---")
st.markdown("### Null / completeness by column (post-cleaning)")
if dq_after_path.exists():
    dq_df = pd.read_csv(dq_after_path)
    dataset_choice = st.selectbox("Dataset", sorted(dq_df["dataset"].unique()))
    sub = dq_df[dq_df["dataset"] == dataset_choice].sort_values("null_pct", ascending=False)
    fig3 = px.bar(sub, x="column", y="null_pct", title=f"Null % by column — {dataset_choice}")
    fig3.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig3, width='stretch')
    st.dataframe(sub, width='stretch')
else:
    st.caption("Data-quality report is not available.")

st.markdown("---")
st.markdown("### Full audit trail")
# st.markdown(
#     "For the complete narrative write-up of every data-quality finding, open "
#     "`reports/DATA_AUDIT.md` and `reports/analytics_validation.md` in the project repository."
# )
