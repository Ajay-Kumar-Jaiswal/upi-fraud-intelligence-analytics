"""
Timestamp parsing utilities.

Handles the formats found in DATA_AUDIT.md:
- 'YYYY-MM-DD HH:MM:SS'
- 'DD/MM/YYYY HH:MM:SS' or 'DD/MM/YYYY'
- 'MM-DD-YYYY HH:MM:SS AM/PM' or 'MM-DD-YYYY'
- 'DD-Mon-YYYY' (e.g. '28-Nov-1960')
- 'YYYY/MM/DD'
- raw Unix epoch seconds (7-12 digit strings, optionally negative for
  pre-1970 dates of birth - confirmed present in KYC data, e.g.
  '-160078671' correctly resolves to 1964-12-05)

Timezone assumption:
All naive datetimes in this dataset are assumed IST (Asia/Kolkata),
since this is an Indian UPI/BFSI dataset with no timezone information
supplied in the source files or notes.

Epoch values are interpreted as UTC seconds-since-epoch and converted
to IST for consistency with the rest of the pipeline.

Day-first vs month-first ambiguity:
Formats using '/' are treated as day-first (DD/MM/YYYY), while formats
using '-' with numeric-only tokens are treated as month-first
(MM-DD-YYYY), based on inspection of the dataset.
"""

import re
import pandas as pd
from datetime import datetime, timezone, timedelta


IST = timezone(timedelta(hours=5, minutes=30))

# Unix epoch seconds.
# Supports both positive and negative timestamps.
_EPOCH_RE = re.compile(r"^-?\d{7,12}$")

_MONTH_NAME_RE = re.compile(r"[A-Za-z]{3,}")


# Explicit format list, tried in order.
_CANDIDATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y",
    "%m-%d-%Y %H:%M:%S",
    "%m-%d-%Y %I:%M %p",
    "%m-%d-%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %I:%M %p",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%b-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
]


def parse_timestamp(value):
    """
    Parse a single timestamp value.

    Returns:
        {
            "clean": pd.Timestamp or pd.NaT,
            "raw": original value,
            "was_epoch": bool,
            "is_invalid": bool
        }

    All valid timestamps are returned as timezone-aware IST timestamps.
    """

    result = {
        "clean": pd.NaT,
        "raw": value,
        "was_epoch": False,
        "is_invalid": False,
    }

    # Missing value
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return result

    s = str(value).strip()

    # Empty string
    if s == "":
        return result

    # ------------------------------------------------------------------
    # Unix epoch timestamp
    # ------------------------------------------------------------------
    if _EPOCH_RE.match(s):
        try:
            epoch_seconds = int(s)

            # Do NOT use datetime.fromtimestamp() here.
            #
            # On Windows, datetime.fromtimestamp() can raise:
            # OSError: [Errno 22] Invalid argument
            # for valid negative Unix timestamps.
            #
            # Arithmetic from the Unix epoch works correctly for both
            # positive and negative timestamps.
            dt = (
                datetime(1970, 1, 1, tzinfo=timezone.utc)
                + timedelta(seconds=epoch_seconds)
            ).astimezone(IST)

            result["clean"] = pd.Timestamp(dt)
            result["was_epoch"] = True
            return result

        except (ValueError, OSError, OverflowError):
            result["is_invalid"] = True
            return result

    # ------------------------------------------------------------------
    # Explicit timestamp formats
    # ------------------------------------------------------------------
    for fmt in _CANDIDATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            result["clean"] = pd.Timestamp(dt, tz=IST)
            return result

        except ValueError:
            continue

    # ------------------------------------------------------------------
    # Last-resort fuzzy parse
    # ------------------------------------------------------------------
    try:
        dt = pd.to_datetime(s, errors="raise")

        if dt.tzinfo is None:
            result["clean"] = dt.tz_localize(IST)
        else:
            result["clean"] = dt.tz_convert(IST)

        return result

    except Exception:
        result["is_invalid"] = True
        return result


def parse_timestamp_series(series: pd.Series) -> pd.DataFrame:
    """
    Parse a pandas Series of timestamps.

    Returns a DataFrame containing:
        clean
        raw
        was_epoch
        is_invalid
    """

    parsed = series.apply(parse_timestamp)

    return pd.DataFrame(
        list(parsed),
        index=series.index,
    )