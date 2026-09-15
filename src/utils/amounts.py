"""
Currency/amount cleaning utilities.

Handles: '₹16,908.13', 'Rs. 22303.2', 'INR 10,010', '23115.78',
'-13101.15', '21.0k' (income shorthand), 'Not Available' / '' (disguised
nulls), and returns (clean_float_or_None, had_negative_sign, was_disguised_null).

Per DATA_AUDIT.md Open Question #2: negative sign shows no correlation
with transaction status and no semantic explanation exists in the
dataset notes -> canonical value is abs(x); original sign is preserved
via a separate boolean flag rather than silently discarded or
reinterpreted as a refund.
"""
import re
import pandas as pd

DISGUISED_NULL_TOKENS = {"not available", "n/a", "na", "none", "null", "-"}
_CURRENCY_STRIP_RE = re.compile(r"(₹|rs\.?|inr)", re.IGNORECASE)
_SHORTHAND_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*k\s*$", re.IGNORECASE)


def clean_amount(value):
    """Returns dict: {clean, raw, had_negative_sign, is_disguised_null, is_invalid}."""
    result = {
        "clean": None,
        "raw": value,
        "had_negative_sign": False,
        "is_disguised_null": False,
        "is_invalid": False,
    }
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return result
    s = str(value).strip()
    if s == "":
        return result
    if s.lower() in DISGUISED_NULL_TOKENS:
        result["is_disguised_null"] = True
        return result

    m = _SHORTHAND_RE.match(s)
    if m:
        num = float(m.group(1)) * 1000.0
    else:
        stripped = _CURRENCY_STRIP_RE.sub("", s)
        stripped = stripped.replace(",", "").strip()
        try:
            num = float(stripped)
        except ValueError:
            result["is_invalid"] = True
            return result

    if num < 0:
        result["had_negative_sign"] = True
        num = abs(num)
    result["clean"] = num
    return result


def clean_amount_series(series: pd.Series) -> pd.DataFrame:
    parsed = series.apply(clean_amount)
    return pd.DataFrame(list(parsed), index=series.index)
