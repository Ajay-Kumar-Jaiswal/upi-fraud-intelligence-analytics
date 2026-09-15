"""
Stage 8 — Advanced business insights.

Ties together Stage 5 (analytics), Stage 6 (risk engine), and Stage 7
(graph) outputs into decision-useful, reusable functions (not
dashboard-only calculations - the dashboard imports these same
functions). Every number here traces back to a Stage 5/6/7 function;
nothing new is invented at this layer.
"""
import pandas as pd
from src.analytics.transactions_kpi import transaction_kpis
from src.analytics.chargebacks_kpi import chargeback_core_kpis
from src.analytics.merchant_category import bonus_question_highest_chargeback_ratio_category, merchant_category_performance
from src.analytics.kyc_analytics import transaction_behavior_by_kyc_status, kyc_join_coverage
from src.fraud.risk_engine import user_risk_scores, merchant_risk_scores
from src.graph.network_analysis import graph_summary_stats, connected_components_summary


def executive_summary() -> dict:
    """One-call summary powering the dashboard's Executive Overview page."""
    txn_k = transaction_kpis()
    cb_k = chargeback_core_kpis()
    ur = user_risk_scores()
    mr = merchant_risk_scores()
    g = graph_summary_stats()

    return {
        "total_transactions": txn_k["total_transactions"],
        "total_transaction_value": txn_k["total_transaction_value"],
        "success_rate_pct": txn_k["success_rate_pct"],
        "failed_rate_pct": txn_k["failed_rate_pct"],
        "chargeback_count": cb_k["chargeback_count_total"],
        "chargeback_ratio_pct": cb_k["chargeback_rate_pct"],
        "total_disputed_amount": cb_k["total_disputed_amount"],
        "high_or_critical_risk_users": int((ur["risk_level"].isin(["HIGH", "CRITICAL"])).sum()),
        "high_or_critical_risk_merchants": int((mr["risk_level"].isin(["HIGH", "CRITICAL"])).sum()),
        "graph_total_nodes": g["total_nodes"],
        "graph_total_edges": g["total_edges"],
    }


def top_strategic_insights(n: int = 5) -> list[dict]:
    """
    Returns the N most decision-useful, DATA-BACKED findings for a
    business/authority audience, each with the number(s) behind it.
    This is a fixed, hand-curated selection of Stage 5/6/7 results
    (not a ranking algorithm) - chosen because they are the highest-
    confidence, most actionable results this dataset actually supports.
    """
    bonus = bonus_question_highest_chargeback_ratio_category()
    cb_k = chargeback_core_kpis()
    kyc_behavior = transaction_behavior_by_kyc_status()
    mr = merchant_risk_scores()
    kyc_cov = kyc_join_coverage()

    highest_risk_kyc_row = kyc_behavior.sort_values("chargeback_to_transaction_ratio", ascending=False).iloc[0] if len(kyc_behavior) else None
    critical_merchants = mr[mr["risk_level"] == "CRITICAL"]

    insights = [
        {
            "title": "Overall dispute exposure",
            "finding": f"{cb_k['chargeback_rate_pct']}% of transactions resolve to a chargeback (₹{cb_k['total_disputed_amount']:,.0f} disputed total).",
            "source": "src/analytics/chargebacks_kpi.chargeback_core_kpis()",
        },
        {
            "title": "Highest-risk merchant category this quarter",
            "finding": f"'{bonus['answer_merchant_category']}' has the highest chargeback-to-transaction ratio ({bonus['answer_chargeback_to_transaction_ratio']:.1%}), though on a modest, {bonus['category_coverage_pct_of_quarter_transactions']}%-coverage sample — see caveat.",
            "source": "src/analytics/merchant_category.bonus_question_highest_chargeback_ratio_category()",
        },
        {
            "title": "KYC status and dispute behavior",
            "finding": (
                f"Among the matched subset, '{highest_risk_kyc_row['kyc_status']}' users show the highest chargeback ratio "
                f"({highest_risk_kyc_row['chargeback_to_transaction_ratio']:.1%}) — computed over only "
                f"{kyc_cov['step_2_unambiguous_kyc_status_match']['match_rate_pct']}% of transactions due to the documented identity-join limitation."
                if highest_risk_kyc_row is not None else "Not enough matched data to compute this."
            ),
            "source": "src/analytics/kyc_analytics.transaction_behavior_by_kyc_status()",
        },
        {
            "title": "Concentration of merchant risk",
            "finding": f"{len(critical_merchants)} merchants (out of {len(mr)} with sufficient transaction volume) are flagged CRITICAL risk by the explainable scoring engine.",
            "source": "src/fraud/risk_engine.merchant_risk_scores()",
        },
        {
            "title": "Network structure limitation",
            "finding": "The user-merchant transaction graph is extremely sparse in this dataset window — no user transacts with the same merchant twice, and no two merchants share even 2 common users, so classic 'repeated relationship' or 'dense cluster' fraud signals are not present in this data slice.",
            "source": "src/graph/network_analysis.repeated_relationship_pairs(), dense_merchant_clusters()",
        },
    ]
    return insights[:n]


if __name__ == "__main__":
    import json
    print(json.dumps(executive_summary(), indent=2))
    print()
    for insight in top_strategic_insights():
        print(f"- {insight['title']}: {insight['finding']}")
