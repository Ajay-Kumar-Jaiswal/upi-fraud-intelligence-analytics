"""
Advanced insights - each one directly computed from the actual cleaned
data, with the underlying statistic shown so it can be verified. Nothing
here is asserted without the number backing it, per the brief's
instruction not to manufacture "interesting insights."
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_chargebacks


def utr_missing_vs_status() -> dict:
    """
    Dataset notes explicit example insight: 'Missing UTRs may correlate
    with failed or disputed transactions.' Tested directly: failure rate
    among transactions with a missing UTR vs. transactions with a present UTR.
    """
    txn = load_transactions()
    missing = txn[txn["utr"].isnull()]
    present = txn[txn["utr"].notnull()]
    failed_rate_missing = round((missing["status"] == "FAILED").mean() * 100, 2) if len(missing) else None
    failed_rate_present = round((present["status"] == "FAILED").mean() * 100, 2) if len(present) else None
    return {
        "transactions_with_missing_utr": len(missing),
        "transactions_with_present_utr": len(present),
        "failed_rate_pct_when_utr_missing": failed_rate_missing,
        "failed_rate_pct_when_utr_present": failed_rate_present,
        "finding": (
            "No meaningful difference found - missing-UTR failure rate is close to "
            "the present-UTR failure rate in this dataset."
            if failed_rate_missing is not None and abs(failed_rate_missing - failed_rate_present) < 2
            else "A difference was found - see the two rates above."
        ),
    }


def chargeback_concentration() -> dict:
    """
    Concentration/Pareto check: what share of ALL chargebacks come from
    the top decile of merchant_ids (by chargeback count), using the raw
    transaction-fact merchant_id (100% coverage, no master-join
    dependency, unlike category-level metrics).
    """
    cb = load_chargebacks()
    by_merchant = cb.groupby("merchant_id")["complaint_id"].count().sort_values(ascending=False)
    n_merchants = len(by_merchant)
    top_decile_n = max(1, n_merchants // 10)
    top_decile_share = round(by_merchant.head(top_decile_n).sum() / by_merchant.sum() * 100, 2) if by_merchant.sum() else 0.0
    return {
        "distinct_merchant_ids_with_chargebacks": n_merchants,
        "total_chargebacks": int(by_merchant.sum()),
        "top_decile_merchant_count": top_decile_n,
        "top_decile_share_of_chargebacks_pct": top_decile_share,
    }


def negative_amount_status_correlation() -> dict:
    """
    Regression check backing the DATA_AUDIT.md Open Question #2 decision
    (negative-amount rows treated as sign-corruption noise, not
    refund/reversal semantics): confirms negative-sign rate is flat
    across transaction status, i.e. not concentrated in FAILED/reversed
    transactions as a true refund signal would be.
    """
    txn = load_transactions()
    rate_by_status = (txn.groupby("status")["amount_had_negative_sign"].mean() * 100).round(2)
    overall_rate = round(txn["amount_had_negative_sign"].mean() * 100, 2)
    max_dev = round((rate_by_status - overall_rate).abs().max(), 2)
    return {
        "overall_negative_sign_rate_pct": overall_rate,
        "negative_sign_rate_by_status_pct": rate_by_status.to_dict(),
        "max_deviation_from_overall_pct_points": max_dev,
        "finding": (
            "Negative-sign rate is statistically flat across all transaction "
            "statuses (max deviation "
            f"{max_dev} percentage points) - consistent with the Open Question #2 "
            "conclusion that this is sign-corruption noise, not a refund/reversal signal."
            if max_dev < 3 else
            "A meaningful difference by status was found - re-examine the Open "
            "Question #2 conclusion."
        ),
    }


def repeated_chargeback_users() -> dict:
    """Per dataset notes: 'Some users may appear repeatedly in disputes.'"""
    cb = load_chargebacks()
    by_user = cb.groupby("user_id")["complaint_id"].count().sort_values(ascending=False)
    repeat_users = by_user[by_user > 1]
    return {
        "distinct_users_with_chargebacks": int(len(by_user)),
        "users_with_more_than_one_chargeback": int(len(repeat_users)),
        "pct_of_disputing_users_with_repeats": round(len(repeat_users) / len(by_user) * 100, 2) if len(by_user) else 0.0,
        "max_chargebacks_by_single_user": int(by_user.max()) if len(by_user) else 0,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(utr_missing_vs_status(), indent=2))
    print(json.dumps(chargeback_concentration(), indent=2))
    print(json.dumps(negative_amount_status_correlation(), indent=2))
    print(json.dumps(repeated_chargeback_users(), indent=2))
