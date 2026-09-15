"""
ID normalization utilities.

Handles the format variants documented in DATA_AUDIT.md:
USR12345, usr12345, USR-12345, USR 12345, usr_12345, 12345 (and MCH/TXN
equivalents). Normalization strips everything but digits and re-applies
a canonical prefix + zero-padding where the source uses fixed-width IDs.

IMPORTANT: normalization does NOT resolve the identity-collision problem
documented as Open Question #1 in DATA_AUDIT.md (the same normalized ID
can legitimately refer to different real people/merchants in this
dataset). Downstream code must not assume normalized-ID uniqueness.
"""
import re
import pandas as pd


def normalize_id(value, prefix: str, width: int = 0) -> str | None:
    """Strip all non-digit characters and re-apply a canonical prefix.

    width=0 means no zero-padding (used for user_id/merchant_id, whose
    raw digit strings are of varying natural length, e.g. 10001..99999).
    width=8 is used for txn_id (TXN00012345 style, 8-digit body).
    """
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    digits = re.sub(r"\D", "", s)
    if digits == "":
        return None
    if width:
        digits = digits.zfill(width)
    else:
        digits = str(int(digits))  # drop any accidental leading zeros
    return f"{prefix}{digits}"


def normalize_user_id(value):
    return normalize_id(value, "USR", width=0)


def normalize_merchant_id(value):
    return normalize_id(value, "MCH", width=0)


def normalize_txn_id(value):
    return normalize_id(value, "TXN", width=8)


def id_format_family(value: str, prefix: str) -> str:
    """Classify the raw formatting family of an ID string (for audit reporting)."""
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return "null"
    s = str(value).strip()
    if re.match(rf"^{prefix}\d+$", s):
        return "clean_upper_no_sep"
    if re.match(rf"^{prefix.lower()}\d+$", s):
        return "lower_no_sep"
    if re.match(rf"^{prefix}-\d+$", s, re.I):
        return "hyphen"
    if re.match(rf"^{prefix} \d+$", s, re.I):
        return "space"
    if re.match(rf"^{prefix}_\d+$", s, re.I):
        return "underscore"
    if re.match(r"^\d+$", s):
        return "digits_only"
    return "other"
