"""
Central configuration for the Track 1 pipeline.
No hardcoded secrets. Paths are relative to the project root so the
pipeline runs the same on any machine / judge's laptop.
"""
from pathlib import Path

# ---- Paths -----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"

RAW_TRANSACTIONS = DATA_RAW / "track1_upi_transactions.csv"
RAW_KYC = DATA_RAW / "track1_kyc_records.csv"
RAW_MERCHANTS = DATA_RAW / "track1_merchants_master.csv"
RAW_CHARGEBACKS = DATA_RAW / "track1_chargebacks.json"
RAW_NOTES = DATA_RAW / "track1_dataset_notes.txt"

CLEAN_TRANSACTIONS = DATA_PROCESSED / "fact_transactions.parquet"
CLEAN_KYC = DATA_PROCESSED / "dim_users.parquet"
CLEAN_MERCHANTS = DATA_PROCESSED / "dim_merchants.parquet"
CLEAN_CHARGEBACKS = DATA_PROCESSED / "fact_chargebacks.parquet"

# ---- Documented business rules (see reports/DATA_AUDIT.md for rationale) --

# Open Question #1 (identity join reliability): user_id / merchant_id are
# kept as descriptive attributes on fact_transactions / fact_chargebacks,
# NOT enforced as validated foreign keys, because empirical match rates
# (~32% users, ~48% merchants) are statistically indistinguishable from
# random ID overlap (see relationship_quality.csv). Every KYC-joined or
# merchant-master-joined metric must surface its join-coverage percentage.
ENFORCE_USER_MERCHANT_FK = False

# Open Question #2 (negative amounts): no status correlation and no
# notes-file semantics found -> treated as sign-corruption noise, not
# refunds/reversals. Canonical amount = abs(value); original signed
# value and a flag are preserved for audit / filtering.
NEGATIVE_AMOUNT_RULE = "abs_with_audit_flag"

# Open Question #3 (chargeback severity code mapping): P-codes are not
# defined anywhere in the source data or notes. This mapping is an
# explicit, documented ASSUMPTION using common BFSI severity convention,
# not a fact derived from the data. Flagged in DATA_AUDIT.md.
SEVERITY_MAP = {
    # word family
    "low": "Low", "medium": "Medium", "high": "High", "critical": "Critical",
    # single-letter family
    "l": "Low", "m": "Medium", "h": "High",
    # priority-code family (ASSUMPTION - see note above)
    "p4": "Low", "p3": "Medium", "p2": "High", "p1": "Critical", "crit": "Critical",
}

STATUS_MAP = {
    # success family
    "s": "SUCCESS", "success": "SUCCESS", "txn_success": "SUCCESS", "completed": "SUCCESS",
    # failed family
    "f": "FAILED", "fail": "FAILED", "failed": "FAILED", "txn_failed": "FAILED", "declined": "FAILED",
    # pending family
    "pending": "PENDING", "initiated": "PENDING",
    # processing (kept distinct from pending - dataset notes list them separately)
    "processing": "PROCESSING",
}

KYC_STATUS_MAP = {
    "verified": "VERIFIED", "approved": "VERIFIED", "kyc_done": "VERIFIED", "v": "VERIFIED", "done": "VERIFIED",
    "pending": "PENDING", "p": "PENDING",
    "in_progress": "IN_PROGRESS", "under review": "IN_PROGRESS",
    "rejected": "REJECTED", "r": "REJECTED", "reject": "REJECTED", "failed": "REJECTED",
}

RISK_SEGMENT_MAP = {
    "low": "LOW", "medium": "MEDIUM", "high": "HIGH", "unknown": "UNKNOWN",
}

MERCHANT_STATUS_MAP = {
    "active": "ACTIVE", "enabled": "ACTIVE", "live": "ACTIVE", "a": "ACTIVE",
    "inactive": "INACTIVE", "disabled": "INACTIVE", "i": "INACTIVE", "closed": "INACTIVE",
    "suspended": "SUSPENDED", "s": "SUSPENDED", "hold": "SUSPENDED",
    "blocked": "BLOCKED",
}

BUSINESS_TYPE_MAP = {
    "individual": "Individual",
    "sole proprietor": "Sole Proprietor", "sole_proprietor": "Sole Proprietor", "sole-proprietor": "Sole Proprietor",
    "partnership": "Partnership",
    "private limited": "Private Limited", "private_limited": "Private Limited", "private-limited": "Private Limited",
}

RESOLUTION_STATUS_MAP = {
    "open": "OPEN",
    "in_progress": "IN_PROGRESS", "wip": "IN_PROGRESS",
    "pending_bank": "PENDING_BANK", "pending bank": "PENDING_BANK",
    "resolved": "RESOLVED",
    "rejected": "REJECTED",
    "closed": "CLOSED",
}

CHANNEL_MAP = {
    "email": "Email", "branch": "Branch", "ivr": "IVR", "chatbot": "Chatbot",
    "app": "App", "call center": "Call Center",
}

# City canonicalization (documented, minor item from DATA_AUDIT.md #5).
# NOTE: Bombay->Mumbai / Poona->Pune / Calcutta->Kolkata are the modern
# official names; kept as a documented mapping rather than silently
# applied without a paper trail.
CITY_MAP = {
    "bombay": "Mumbai", "mumbai": "Mumbai",
    "poona": "Pune", "pune": "Pune",
    "calcutta": "Kolkata", "kolkata": "Kolkata",
    "ldh": "Ludhiana", "ludhiana": "Ludhiana",
    "hyd": "Hyderabad", "hyderabad": "Hyderabad",
    "lko": "Lucknow", "lucknow": "Lucknow",
    "jpr": "Jaipur", "jaipur": "Jaipur",
    "jalandar": "Jalandhar", "jalandhar": "Jalandhar",
    "amritsar": "Amritsar", "chennai": "Chennai",
}

REASON_CODE_MAP = {
    # duplicate / double debit family
    "charged twice": "Duplicate Debit", "duplicate debit": "Duplicate Debit",
    "dup_debit": "Duplicate Debit", "double debit": "Duplicate Debit",
    "extra amount deducted": "Duplicate Debit",
    # unauthorized / account takeover family
    "account hacked": "Unauthorized Transaction", "login compromised": "Unauthorized Transaction",
    "ato": "Unauthorized Transaction", "account takeover": "Unauthorized Transaction",
    "unauthorized transaction": "Unauthorized Transaction", "unauth txn": "Unauthorized Transaction",
    "unauthorized_transaction": "Unauthorized Transaction", "unauthorised": "Unauthorized Transaction",
    "not done by me": "Unauthorized Transaction",
    # fraud family
    "fraud": "Fraud Suspected", "fraud suspected": "Fraud Suspected", "scam": "Fraud Suspected",
    "suspicious transaction": "Fraud Suspected",
    # merchant service / delivery family
    "delivery issue": "Service Not Delivered", "item not received": "Service Not Delivered",
    "no service": "Service Not Delivered", "merchant not delivered": "Service Not Delivered",
    "not delivered": "Service Not Delivered", "merchant service issue": "Service Not Delivered",
    "service failed": "Service Not Delivered", "service not provided": "Service Not Delivered",
    # amount mismatch family
    "amount mismatch": "Incorrect Amount", "wrong amount": "Incorrect Amount",
    "incorrect amount": "Incorrect Amount",
    # generic / customer dispute family
    "customer issue": "Customer Dispute", "dispute raised": "Customer Dispute",
    "customer dispute": "Customer Dispute", "complaint": "Customer Dispute",
}

RANDOM_SEED = 42
