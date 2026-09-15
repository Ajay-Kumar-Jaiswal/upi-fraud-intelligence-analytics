"""
Time-based analytics.

Source: fact_transactions.timestamp, fact_chargebacks.reported_timestamp.
Dataset's actual date range (verified from cleaned data): 2026-01-01 to
2026-04-01 IST, i.e. essentially the full first calendar quarter of 2026
plus 2 transactions that land just after midnight on Apr 1 (timezone
conversion boundary, not a data error - see test coverage). Daily
granularity is used (not hourly) since the brief's dashboard section
asks for daily trend by default; an hourly failed-transaction breakdown
is also provided since the dataset notes explicitly mention it.
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_chargebacks


def daily_transaction_trend() -> pd.DataFrame:
    """
    date, transaction_count, transaction_value, success_count,
    failed_count, pending_count, processing_count
    """
    txn = load_transactions()
    txn = txn.copy()
    txn["date"] = txn["timestamp"].dt.date
    base = txn.groupby("date").agg(
        transaction_count=("txn_id", "count"),
        transaction_value=("amount", "sum"),
    ).reset_index()
    pivot = txn.pivot_table(index="date", columns="status", values="txn_id", aggfunc="count", fill_value=0)
    out = base.merge(pivot, on="date", how="left").sort_values("date").reset_index(drop=True)
    out["transaction_value"] = out["transaction_value"].round(2)
    return out


def monthly_transaction_trend() -> pd.DataFrame:
    txn = load_transactions()
    txn = txn.copy()
    txn["month"] = txn["timestamp"].dt.tz_localize(None).dt.to_period("M").astype(str)
    out = txn.groupby("month").agg(
        transaction_count=("txn_id", "count"),
        transaction_value=("amount", "sum"),
        average_transaction_value=("amount", "mean"),
    ).reset_index().sort_values("month")
    out["transaction_value"] = out["transaction_value"].round(2)
    out["average_transaction_value"] = out["average_transaction_value"].round(2)
    return out


def failed_transaction_trend_by_hour() -> pd.DataFrame:
    """Per dataset notes example question: 'Failed transaction trend by day/hour.'"""
    txn = load_transactions()
    txn = txn.copy()
    txn["hour"] = txn["timestamp"].dt.hour
    total_by_hour = txn.groupby("hour")["txn_id"].count().rename("total_count")
    failed_by_hour = txn[txn["status"] == "FAILED"].groupby("hour")["txn_id"].count().rename("failed_count")
    out = pd.concat([total_by_hour, failed_by_hour], axis=1).fillna(0).reset_index()
    out["failed_count"] = out["failed_count"].astype(int)
    out["failed_rate_pct"] = (out["failed_count"] / out["total_count"] * 100).round(2)
    return out.sort_values("hour").reset_index(drop=True)


def daily_chargeback_trend() -> pd.DataFrame:
    """Based on reported_timestamp (when the dispute was filed), not the
    underlying transaction_timestamp, since 'chargeback trend' in the
    brief's dashboard section refers to dispute activity over time."""
    cb = load_chargebacks()
    cb = cb.copy()
    valid = cb[cb["reported_timestamp"].notnull()].copy()
    valid["date"] = valid["reported_timestamp"].dt.date
    out = valid.groupby("date").agg(
        chargeback_count=("complaint_id", "count"),
        disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)),
    ).reset_index().sort_values("date")
    return out


def data_date_range_summary() -> dict:
    txn = load_transactions()
    cb = load_chargebacks()
    return {
        "transactions_min_timestamp": str(txn["timestamp"].min()),
        "transactions_max_timestamp": str(txn["timestamp"].max()),
        "transactions_distinct_dates": int(txn["timestamp"].dt.date.nunique()),
        "chargebacks_reported_min_timestamp": str(cb["reported_timestamp"].min()),
        "chargebacks_reported_max_timestamp": str(cb["reported_timestamp"].max()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(data_date_range_summary(), indent=2))
    print(daily_transaction_trend().head())
    print(monthly_transaction_trend())
    print(failed_transaction_trend_by_hour().head())
    print(daily_chargeback_trend().head())
