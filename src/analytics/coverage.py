"""
Join-coverage utilities.

Per DATA_AUDIT.md Open Question #1: transactions.user_id -> dim_users.user_id
and transactions.merchant_id -> dim_merchants.merchant_id match at rates
statistically indistinguishable from random ID overlap (~32% and ~48%
respectively, verified in reports/relationship_quality.csv). Per the
project's own decision documented in src/config.py
(ENFORCE_USER_MERCHANT_FK = False), these are NOT treated as reliable
foreign keys.

Every analytics function in this package that joins fact_transactions or
fact_chargebacks to dim_users or dim_merchants MUST report its join
coverage using compute_join_coverage() and attach the result to its
output, so no KPI can be consumed as if it represents 100% of the
population when it does not.
"""
from dataclasses import dataclass
import pandas as pd


@dataclass
class JoinCoverage:
    relationship: str
    total_left_rows: int
    matched_rows: int
    unmatched_rows: int
    match_rate_pct: float
    caveat: str

    def as_dict(self):
        return {
            "relationship": self.relationship,
            "total_left_rows": self.total_left_rows,
            "matched_rows": self.matched_rows,
            "unmatched_rows": self.unmatched_rows,
            "match_rate_pct": self.match_rate_pct,
            "caveat": self.caveat,
        }


DEFAULT_CAVEAT = (
    "This join key matches at a rate statistically indistinguishable from "
    "random ID overlap in the raw data (see DATA_AUDIT.md Open Question #1). "
    "Any metric built on this join reflects only the matched subset, NOT the "
    "full transaction/chargeback population, and must not be read as a "
    "population-level result."
)


def compute_join_coverage(left_key: pd.Series, right_keys: set, relationship: str, caveat: str = DEFAULT_CAVEAT) -> JoinCoverage:
    total = len(left_key)
    matched_mask = left_key.isin(right_keys)
    matched = int(matched_mask.sum())
    unmatched = total - matched
    rate = round(matched / total * 100, 2) if total else 0.0
    return JoinCoverage(
        relationship=relationship,
        total_left_rows=total,
        matched_rows=matched,
        unmatched_rows=unmatched,
        match_rate_pct=rate,
        caveat=caveat if rate < 90 else "",  # only attach the strong caveat when coverage is genuinely low
    )
