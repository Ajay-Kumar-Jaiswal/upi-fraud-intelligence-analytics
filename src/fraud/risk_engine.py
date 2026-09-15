"""
Stage 6 — Explainable fraud/risk engine.

Design principle (per the brief): NO black-box scoring. Every risk point
is a named, documented rule with a concrete threshold, computed from
the actual cleaned/validated data. Scores are additive and bounded, and
every flagged entity carries a `risk_reasons` list explaining exactly
why. Terminology is deliberately cautious throughout ("potential risk",
"anomaly", "requires investigation") - nothing here is a confirmed
fraud/money-laundering label, because the dataset contains no ground-
truth fraud label.

All thresholds are named module-level constants (configurable) rather
than magic numbers buried in logic, and every join to dim_users /
dim_merchants carries the same coverage caveat established in Stage 5
(src/analytics/coverage.py) - risk scores computed on identity-joined
attributes only cover the matched subset, never the full population.
"""
import pandas as pd
from src.analytics.loaders import load_transactions, load_users, load_merchants, load_chargebacks
from src.analytics.merchant_category import _unambiguous_merchant_category_map
from src.analytics.kyc_analytics import _unambiguous_user_attribute_map

# ---- Configurable thresholds (documented, not magic numbers) --------------
HIGH_VELOCITY_TXN_COUNT_PER_DAY = 5          # transactions by the same user_id on the same calendar day
HIGH_AMOUNT_ZSCORE = 3.0                      # standard deviations above the population mean
MIN_TRANSACTIONS_FOR_MERCHANT_RISK = 5        # floor to avoid tiny-sample noise dominating merchant ranking
HIGH_CHARGEBACK_RATIO_MERCHANT = 0.30         # merchant chargeback-to-txn ratio considered high-risk
HIGH_FAILURE_RATE_MERCHANT = 0.40             # merchant transaction-failure rate considered high-risk
REPEATED_CHARGEBACK_USER_THRESHOLD = 3        # chargebacks filed by one user_id considered high-risk
RAPID_REPEAT_MINUTES = 5                      # 2+ transactions by same user_id within this window, same merchant

RISK_LEVEL_BANDS = {"LOW": (0, 24), "MEDIUM": (25, 49), "HIGH": (50, 74), "CRITICAL": (75, 10_000)}


def _risk_level(score: int) -> str:
    for level, (lo, hi) in RISK_LEVEL_BANDS.items():
        if lo <= score <= hi:
            return level
    return "CRITICAL"


# ============================================================ USER RISK ===
def user_risk_scores() -> pd.DataFrame:
    """
    Per-user_id (raw transaction-fact user_id - 100% coverage by
    definition, no identity-collision dependency) explainable risk score.

    Signals (each worth documented points, capped at 100 total):
      +20  unusual_amount_zscore   : >=1 transaction with amount z-score > HIGH_AMOUNT_ZSCORE
      +20  high_daily_velocity     : >=1 calendar day with > HIGH_VELOCITY_TXN_COUNT_PER_DAY transactions
      +15  rapid_repeat_same_merchant : >=1 pair of transactions to the same merchant within RAPID_REPEAT_MINUTES
      +25  repeated_chargebacks    : >= REPEATED_CHARGEBACK_USER_THRESHOLD chargebacks filed
      +20  high_failure_rate       : failure rate > 50% AND >= 5 transactions (avoids 1-txn noise)
    """
    txn = load_transactions().copy()
    cb = load_chargebacks()

    mean_amt, std_amt = txn["amount"].mean(), txn["amount"].std()
    txn["amount_zscore"] = (txn["amount"] - mean_amt) / std_amt if std_amt else 0.0

    scores = {}
    reasons = {}

    def add(user_id, points, reason):
        scores[user_id] = scores.get(user_id, 0) + points
        reasons.setdefault(user_id, []).append(reason)

    # Signal 1: unusual amount
    for uid in txn.loc[txn["amount_zscore"] > HIGH_AMOUNT_ZSCORE, "user_id"].unique():
        add(uid, 20, f"Transaction amount > {HIGH_AMOUNT_ZSCORE} standard deviations above the population mean")

    # Signal 2: high daily velocity
    txn["date"] = txn["timestamp"].dt.date
    daily_counts = txn.groupby(["user_id", "date"]).size()
    velocity_flagged = daily_counts[daily_counts > HIGH_VELOCITY_TXN_COUNT_PER_DAY].reset_index()["user_id"].unique()
    for uid in velocity_flagged:
        add(uid, 20, f"More than {HIGH_VELOCITY_TXN_COUNT_PER_DAY} transactions in a single calendar day")

    # Signal 3: rapid repeat to same merchant within a short window
    ordered = txn.sort_values(["user_id", "merchant_id", "timestamp"])
    ordered["prev_ts"] = ordered.groupby(["user_id", "merchant_id"])["timestamp"].shift(1)
    ordered["gap_minutes"] = (ordered["timestamp"] - ordered["prev_ts"]).dt.total_seconds() / 60.0
    rapid = ordered[(ordered["gap_minutes"].notnull()) & (ordered["gap_minutes"] <= RAPID_REPEAT_MINUTES)]
    for uid in rapid["user_id"].unique():
        add(uid, 15, f"Two or more transactions to the same merchant within {RAPID_REPEAT_MINUTES} minutes")

    # Signal 4: repeated chargebacks
    cb_counts = cb.groupby("user_id")["complaint_id"].count()
    for uid in cb_counts[cb_counts >= REPEATED_CHARGEBACK_USER_THRESHOLD].index:
        if pd.notnull(uid):
            add(uid, 25, f">= {REPEATED_CHARGEBACK_USER_THRESHOLD} chargebacks filed by this user")

    # Signal 5: high personal failure rate (min 5 txns to avoid noise)
    per_user = txn.groupby("user_id").agg(n=("txn_id", "count"), failed=("status", lambda s: (s == "FAILED").sum()))
    per_user["failure_rate"] = per_user["failed"] / per_user["n"]
    high_fail = per_user[(per_user["n"] >= 5) & (per_user["failure_rate"] > 0.5)]
    for uid in high_fail.index:
        add(uid, 20, f"Transaction failure rate > 50% across >= 5 transactions")

    all_users = txn["user_id"].unique()
    rows = []
    for uid in all_users:
        score = min(scores.get(uid, 0), 100)
        rows.append({
            "user_id": uid,
            "risk_score": score,
            "risk_level": _risk_level(score),
            "risk_reasons": reasons.get(uid, []),
        })
    out = pd.DataFrame(rows).sort_values("risk_score", ascending=False).reset_index(drop=True)
    return out


# ======================================================== MERCHANT RISK ===
def merchant_risk_scores() -> pd.DataFrame:
    """
    Per raw merchant_id (transaction-fact grain, 100% coverage - no
    dependency on the low-coverage merchant-master join for the score
    itself; master attributes like name/category are attached afterward
    on a best-effort, coverage-labeled basis for display only).

    Signals (capped at 100):
      +35  high_chargeback_ratio  : chargeback/txn ratio > HIGH_CHARGEBACK_RATIO_MERCHANT (min txns enforced)
      +25  high_failure_rate      : txn failure rate > HIGH_FAILURE_RATE_MERCHANT (min txns enforced)
      +20  chargeback_concentration : among top-decile chargeback-count merchants (see advanced_insights.py)
      +20  disputed_amount_share  : merchant's disputed amount is in the top 5% of all merchants with chargebacks
    """
    txn = load_transactions()
    cb = load_chargebacks()
    merchants = load_merchants()

    per_merchant = txn.groupby("merchant_id").agg(
        transaction_count=("txn_id", "count"),
        failed_count=("status", lambda s: (s == "FAILED").sum()),
    )
    per_merchant["failure_rate"] = per_merchant["failed_count"] / per_merchant["transaction_count"]

    # IMPORTANT: chargebacks are resolved to a merchant via the HIGH-coverage
    # txn_id -> transaction link (93% match, see Stage 5), NOT via the
    # chargeback record's own raw merchant_id field. The two merchant_id
    # fields are independently-sourced (see DATA_AUDIT.md Open Question #1)
    # and combining transaction-count-by-merchant_id with chargeback-count-
    # by-the-CHARGEBACK's-own-merchant_id produced nonsensical ratios above
    # 1.0 during testing (e.g. 34 chargebacks / 6 transactions) - this is
    # the correct, defensible resolution.
    txn_id_to_merchant = txn.set_index("txn_id")["merchant_id"]
    cb = cb.copy()
    cb["resolved_merchant_id"] = cb["txn_id"].map(txn_id_to_merchant)
    cb_resolved = cb[cb["resolved_merchant_id"].notnull()]

    cb_agg = cb_resolved.groupby("resolved_merchant_id").agg(
        chargeback_count=("complaint_id", "count"),
        disputed_amount=("disputed_amount", lambda s: round(float(s.dropna().sum()), 2)),
    )
    cb_agg.index.name = "merchant_id"

    merged = per_merchant.join(cb_agg, how="left").fillna({"chargeback_count": 0, "disputed_amount": 0.0})
    merged["chargeback_count"] = merged["chargeback_count"].astype(int)
    eligible = merged[merged["transaction_count"] >= MIN_TRANSACTIONS_FOR_MERCHANT_RISK].copy()
    eligible["chargeback_ratio"] = eligible["chargeback_count"] / eligible["transaction_count"]

    scores = {m: 0 for m in eligible.index}
    reasons = {m: [] for m in eligible.index}

    high_cb = eligible[eligible["chargeback_ratio"] > HIGH_CHARGEBACK_RATIO_MERCHANT].index
    for m in high_cb:
        scores[m] += 35
        reasons[m].append(f"Chargeback-to-transaction ratio > {HIGH_CHARGEBACK_RATIO_MERCHANT:.0%} (min {MIN_TRANSACTIONS_FOR_MERCHANT_RISK} transactions)")

    high_fail = eligible[eligible["failure_rate"] > HIGH_FAILURE_RATE_MERCHANT].index
    for m in high_fail:
        scores[m] += 25
        reasons[m].append(f"Transaction failure rate > {HIGH_FAILURE_RATE_MERCHANT:.0%}")

    cb_only = eligible[eligible["chargeback_count"] > 0]
    if len(cb_only):
        decile_n = max(1, len(cb_only) // 10)
        top_decile = cb_only.sort_values("chargeback_count", ascending=False).head(decile_n).index
        for m in top_decile:
            scores[m] += 20
            reasons[m].append("Among the top 10% of merchants by chargeback count")

        top5pct_n = max(1, len(cb_only) // 20)
        top_disputed = cb_only.sort_values("disputed_amount", ascending=False).head(top5pct_n).index
        for m in top_disputed:
            scores[m] += 20
            reasons[m].append("Among the top 5% of merchants by total disputed amount")

    cat_lookup = _unambiguous_merchant_category_map(merchants)
    name_map = (
        merchants.groupby("merchant_id")["merchant_name"].nunique().pipe(lambda s: s[s == 1].index)
    )
    name_lookup = merchants[merchants["merchant_id"].isin(name_map)].drop_duplicates("merchant_id").set_index("merchant_id")["merchant_name"]

    rows = []
    for m in eligible.index:
        score = min(scores.get(m, 0), 100)
        rows.append({
            "merchant_id": m,
            "merchant_name": name_lookup.get(m),
            "merchant_category": cat_lookup.get(m),
            "transaction_count": int(eligible.loc[m, "transaction_count"]),
            "chargeback_count": int(eligible.loc[m, "chargeback_count"]),
            "chargeback_ratio": round(float(eligible.loc[m, "chargeback_ratio"]), 4),
            "failure_rate": round(float(eligible.loc[m, "failure_rate"]), 4),
            "disputed_amount": float(eligible.loc[m, "disputed_amount"]),
            "risk_score": score,
            "risk_level": _risk_level(score),
            "risk_reasons": reasons.get(m, []),
        })
    out = pd.DataFrame(rows).sort_values("risk_score", ascending=False).reset_index(drop=True)
    out.attrs["coverage_note"] = (
        f"merchant_name/category attached on a best-effort basis (unambiguous dim_merchants matches only); "
        f"the risk SCORE itself uses only fact_transactions/fact_chargebacks (100% coverage, no master-join dependency)."
    )
    return out


def kyc_inconsistency_risk() -> pd.DataFrame:
    """
    Per DATA_AUDIT.md / brief §15: identity-collision and invalid-format
    KYC signals, reported as a POTENTIAL indicator, never a confirmed
    finding. Computed directly from dim_users (no transaction join
    needed for this particular signal).
    """
    users = load_users()
    per_user = users.groupby("user_id").agg(
        record_count=("pan", "count"),
        distinct_names=("full_name", "nunique"),
        distinct_pans=("pan", "nunique"),
        any_invalid_pan=("pan_status", lambda s: (s == "invalid_format").any()),
        any_rejected=("kyc_status", lambda s: (s == "REJECTED").any()),
    ).reset_index()
    per_user["identity_collision_flag"] = per_user["distinct_names"] > 1
    flagged = per_user[per_user["identity_collision_flag"] | per_user["any_invalid_pan"]]
    return flagged.sort_values("distinct_names", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    print("=== USER RISK (top 10) ===")
    ur = user_risk_scores()
    print(ur.head(10).to_string(index=False))
    print("\nrisk_level distribution:", ur["risk_level"].value_counts().to_dict())

    print("\n=== MERCHANT RISK (top 10) ===")
    mr = merchant_risk_scores()
    print(mr.head(10).drop(columns=["risk_reasons"]).to_string(index=False))
    print("\nrisk_level distribution:", mr["risk_level"].value_counts().to_dict())

    print("\n=== KYC INCONSISTENCY (sample) ===")
    print(kyc_inconsistency_risk().head(5).to_string(index=False))
