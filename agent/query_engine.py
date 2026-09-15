"""
Deterministic query execution layer. Each function here calls ONE
already-tested Stage 5/6/7/8 function and packages the result for the
response generator. No number here is computed ad hoc inside the
agent - everything traces back to a tested function, so the agent's
answers can never disagree with the dashboard.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from agent.router import Intent, extract_merchant_id
from src.analytics.transactions_kpi import transaction_kpis
from src.analytics.chargebacks_kpi import chargebacks_by, top_users_by_disputed_amount, chargebacks_by_merchant
from src.analytics.merchant_category import merchant_category_performance, bonus_question_highest_chargeback_ratio_category
from src.analytics.time_analytics import monthly_transaction_trend, daily_transaction_trend
from src.analytics.business_insights import executive_summary
from src.fraud.risk_engine import merchant_risk_scores, user_risk_scores
from src.graph.network_analysis import dense_merchant_clusters, connected_components_summary


class AgentAnswer:
    def __init__(self, text: str, table: pd.DataFrame = None, chart_type: str = "text",
                 chart_x: str = None, chart_y: str = None, methodology: str = ""):
        self.text = text
        self.table = table
        self.chart_type = chart_type
        self.chart_x = chart_x
        self.chart_y = chart_y
        self.methodology = methodology


def execute(intent: Intent, question: str) -> AgentAnswer:
    handler = _HANDLERS.get(intent.name)
    if handler is None:
        return AgentAnswer(
            "I cannot answer this reliably because the required information is not available "
            "in the dataset, or this question type is not yet supported by the deterministic "
            "query layer.",
        )
    return handler(question)


def _bonus_chargeback_ratio_by_category(question: str) -> AgentAnswer:
    result = bonus_question_highest_chargeback_ratio_category()
    if "error" in result:
        return AgentAnswer(result["error"])
    df = pd.DataFrame(result["full_ranking"])
    text = (
        f"**{result['answer_merchant_category']}** has the highest chargeback-to-transaction ratio "
        f"({result['answer_chargeback_to_transaction_ratio']:.2%}) in {result['quarter_used']} "
        f"({result['answer_chargeback_count']} chargebacks / {result['answer_transaction_count']} transactions). "
        f"{result['caveat']}"
    )
    return AgentAnswer(text, table=df, chart_type="bar", chart_x="merchant_category", chart_y="chargeback_to_transaction_ratio",
                        methodology=result["quarter_definition"])


def _riskiest_merchants(question: str) -> AgentAnswer:
    df = merchant_risk_scores()
    top = df.head(10).copy()
    top["risk_reasons"] = top["risk_reasons"].apply(lambda r: "; ".join(r))
    n_high = int((df["risk_level"].isin(["HIGH", "CRITICAL"])).sum())
    text = (
        f"{n_high} merchants (of {len(df)} with sufficient transaction volume) are flagged "
        f"HIGH or CRITICAL risk by the explainable rule-based engine. Top result: "
        f"**{top.iloc[0]['merchant_id']}** (score {top.iloc[0]['risk_score']}, {top.iloc[0]['risk_level']})."
        if len(top) else "No merchants met the minimum transaction-volume threshold for risk scoring."
    )
    return AgentAnswer(text, table=top, chart_type="bar", chart_x="merchant_id", chart_y="risk_score",
                        methodology="src/fraud/risk_engine.merchant_risk_scores() - see risk_reasons column for the explainable rule breakdown.")


def _suspicious_users(question: str) -> AgentAnswer:
    df = user_risk_scores()
    flagged = df[df["risk_score"] > 0].head(15).copy()
    flagged["risk_reasons"] = flagged["risk_reasons"].apply(lambda r: "; ".join(r))
    n_flagged = int((df["risk_score"] > 0).sum())
    text = (
        f"{n_flagged:,} of {len(df):,} users are flagged by at least one risk signal "
        f"(unusual amount, high velocity, rapid repeat transactions, repeated chargebacks, "
        f"or high personal failure rate). None reached HIGH/CRITICAL in this dataset - "
        f"the highest observed level is {df['risk_level'].iloc[0] if len(df) else 'N/A'}."
    )
    return AgentAnswer(text, table=flagged, chart_type="table",
                        methodology="src/fraud/risk_engine.user_risk_scores()")


def _chargeback_reasons(question: str) -> AgentAnswer:
    df = chargebacks_by("reason_code")
    top = df.iloc[0]
    text = f"The largest chargeback reason category is **{top['reason_code']}** with {top['chargeback_count']:,} cases (₹{top['total_disputed_amount']:,.0f} disputed)."
    return AgentAnswer(text, table=df, chart_type="bar", chart_x="reason_code", chart_y="chargeback_count",
                        methodology="src/analytics/chargebacks_kpi.chargebacks_by('reason_code')")


def _network_clusters(question: str) -> AgentAnswer:
    dc = dense_merchant_clusters(min_shared_users=2, top_n=15)
    cc = connected_components_summary()
    if dc.empty:
        text = (
            "No dense merchant clusters were found: no two merchants share 2 or more common "
            "users in this dataset - the transaction graph is very sparse "
            f"({cc['total_components']:,} connected components, largest is only "
            f"{cc['largest_component_size']} nodes / {cc['largest_component_pct_of_nodes']}% of the graph)."
        )
    else:
        text = f"Found {len(dc)} merchant pairs sharing 2+ common users. Top pair: {dc.iloc[0]['merchant_id_a']} & {dc.iloc[0]['merchant_id_b']} ({dc.iloc[0]['shared_user_count']} shared users)."
    return AgentAnswer(text, table=dc if not dc.empty else None, chart_type="network",
                        methodology="src/graph/network_analysis.dense_merchant_clusters(), connected_components_summary()")


def _explain_merchant_risk(question: str) -> AgentAnswer:
    mid = extract_merchant_id(question)
    if not mid:
        return AgentAnswer("Please include a merchant ID (e.g. MCH1234) in your question so I can look it up.")
    df = merchant_risk_scores()
    row = df[df["merchant_id"] == mid]
    if row.empty:
        return AgentAnswer(
            f"{mid} either doesn't appear in the transaction data, or has fewer than the minimum "
            "transaction count required for risk scoring - I cannot answer this reliably."
        )
    r = row.iloc[0]
    if r["risk_score"] == 0:
        text = f"{mid} has a risk score of 0 (LOW) - none of the explainable risk rules were triggered."
    else:
        reasons = "; ".join(r["risk_reasons"])
        text = f"{mid} has risk score {r['risk_score']} ({r['risk_level']}) because: {reasons}."
    return AgentAnswer(text, table=row, methodology="src/fraud/risk_engine.merchant_risk_scores()")


def _transaction_volume_trend(question: str) -> AgentAnswer:
    df = monthly_transaction_trend()
    text = f"Transaction volume by month: " + ", ".join(f"{r['month']}: {r['transaction_count']:,}" for _, r in df.iterrows())
    return AgentAnswer(text, table=df, chart_type="bar", chart_x="month", chart_y="transaction_count",
                        methodology="src/analytics/time_analytics.monthly_transaction_trend()")


def _success_failure_comparison(question: str) -> AgentAnswer:
    daily = daily_transaction_trend()
    cols = [c for c in ["date", "SUCCESS", "FAILED"] if c in daily.columns]
    df = daily[cols]
    text = f"Total SUCCESS: {daily['SUCCESS'].sum():,} vs total FAILED: {daily['FAILED'].sum():,} across the full data window."
    return AgentAnswer(text, table=df, chart_type="line", chart_x="date", chart_y="SUCCESS",
                        methodology="src/analytics/time_analytics.daily_transaction_trend()")


def _average_value_by_category(question: str) -> AgentAnswer:
    df = merchant_category_performance()
    df = df.copy()
    df["average_transaction_value"] = (df["transaction_value"] / df["transaction_count"]).round(2)
    top = df.sort_values("average_transaction_value", ascending=False).iloc[0]
    text = f"**{top['merchant_category']}** has the highest average transaction value (₹{top['average_transaction_value']:,.2f})."
    return AgentAnswer(text, table=df[["merchant_category", "average_transaction_value"]], chart_type="bar",
                        chart_x="merchant_category", chart_y="average_transaction_value",
                        methodology="src/analytics/merchant_category.merchant_category_performance() (join-coverage limited, see Data Quality page)")


def _top_merchant_disputed_amount(question: str) -> AgentAnswer:
    df = chargebacks_by_merchant(top_n=10)
    top = df.iloc[0]
    text = f"Merchant **{top['merchant_id']}** has the highest disputed amount (₹{top['total_disputed_amount']:,.0f} across {top['chargeback_count']} chargebacks), based on the chargeback record's own merchant_id field."
    return AgentAnswer(text, table=df, chart_type="bar", chart_x="merchant_id", chart_y="total_disputed_amount",
                        methodology="src/analytics/chargebacks_kpi.chargebacks_by_merchant()")


def _top_disputed_users(question: str) -> AgentAnswer:
    df = top_users_by_disputed_amount(10)
    q = question.lower()
    if "number of chargeback" in q or "how many chargeback" in q:
        by_count = df.sort_values("chargeback_count", ascending=False)
        top = by_count.iloc[0]
        text = f"User **{top['user_id']}** has filed the most chargebacks ({top['chargeback_count']}, totaling ₹{top['total_disputed_amount']:,.0f} disputed)."
        return AgentAnswer(text, table=by_count, chart_type="bar", chart_x="user_id", chart_y="chargeback_count",
                            methodology="src/analytics/chargebacks_kpi.top_users_by_disputed_amount(), re-sorted by chargeback_count")
    top = df.iloc[0]
    text = f"User **{top['user_id']}** has the highest disputed amount (₹{top['total_disputed_amount']:,.0f} across {top['chargeback_count']} chargebacks)."
    return AgentAnswer(text, table=df, chart_type="bar", chart_x="user_id", chart_y="total_disputed_amount",
                        methodology="src/analytics/chargebacks_kpi.top_users_by_disputed_amount()")


def _kpi_overview(question: str) -> AgentAnswer:
    s = executive_summary()
    text = (
        f"{s['total_transactions']:,} transactions totaling ₹{s['total_transaction_value']:,.0f}. "
        f"Success rate {s['success_rate_pct']}%, failed {s['failed_rate_pct']}%. "
        f"{s['chargeback_count']:,} chargebacks ({s['chargeback_ratio_pct']}% ratio), "
        f"₹{s['total_disputed_amount']:,.0f} disputed. "
        f"{s['high_or_critical_risk_merchants']} merchants flagged HIGH/CRITICAL risk."
    )
    return AgentAnswer(text, methodology="src/analytics/business_insights.executive_summary()")


_HANDLERS = {
    "bonus_chargeback_ratio_by_category": _bonus_chargeback_ratio_by_category,
    "riskiest_merchants": _riskiest_merchants,
    "suspicious_users": _suspicious_users,
    "chargeback_reasons": _chargeback_reasons,
    "network_clusters": _network_clusters,
    "explain_merchant_risk": _explain_merchant_risk,
    "transaction_volume_trend": _transaction_volume_trend,
    "success_failure_comparison": _success_failure_comparison,
    "average_value_by_category": _average_value_by_category,
    "top_merchant_disputed_amount": _top_merchant_disputed_amount,
    "top_disputed_users": _top_disputed_users,
    "kpi_overview": _kpi_overview,
}
