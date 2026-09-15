"""Reusable sidebar filters shared across dashboard pages."""
import streamlit as st
import pandas as pd


def render_global_filters(txn: pd.DataFrame) -> dict:
    st.sidebar.markdown("### Filters")
    min_date = txn["timestamp"].min().date()
    max_date = txn["timestamp"].max().date()

    date_range = st.sidebar.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date,
        key="global_date_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    status_options = sorted(txn["status"].unique().tolist())
    statuses = st.sidebar.multiselect("Transaction status", status_options, default=status_options, key="global_status")

    if st.sidebar.button("Reset filters", key="global_reset"):
        st.session_state["global_date_range"] = (min_date, max_date)
        st.session_state["global_status"] = status_options
        st.rerun()

    return {"start_date": start_date, "end_date": end_date, "statuses": statuses or status_options}


def apply_txn_filters(txn: pd.DataFrame, filters: dict) -> pd.DataFrame:
    out = txn[
        (txn["timestamp"].dt.date >= filters["start_date"])
        & (txn["timestamp"].dt.date <= filters["end_date"])
        & (txn["status"].isin(filters["statuses"]))
    ]
    return out


def coverage_badge(match_rate_pct: float, label: str):
    """Renders a small colored badge communicating join-coverage honestly,
    per the standing Open Question #1 requirement that no chart implies
    100% population coverage when it does not have it."""
    if match_rate_pct >= 90:
        color = "green"
    elif match_rate_pct >= 60:
        color = "orange"
    else:
        color = "red"
    st.caption(f":{color}[●] **{label}**: {match_rate_pct}% join coverage — see Data Quality & Coverage page for full detail.")


def empty_state(message: str = "No data matches the current filters."):
    st.info(f"ℹ️ {message} Try widening the date range or clearing some filters.")
