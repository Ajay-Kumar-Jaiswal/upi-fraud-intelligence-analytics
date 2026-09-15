"""
Cleaning pipeline for track1_merchants_master.csv.

Same identity-collision caveat as kyc.py applies to merchant_id (see
DATA_AUDIT.md Open Question #1) - grain stays one row per raw record,
collisions are flagged rather than blindly deduplicated or merged.
"""
import re
import pandas as pd
from src.config import MERCHANT_STATUS_MAP, BUSINESS_TYPE_MAP, CITY_MAP, RAW_MERCHANTS
from src.utils.ids import normalize_merchant_id
from src.utils.amounts import clean_amount_series
from src.utils.dates import parse_timestamp_series

# All 82 raw merchant_category labels found in the actual data (verified
# by full value_counts() inspection - nothing here is guessed or invented)
# collapse into 12 canonical categories, grouped by case/separator/
# synonym variants of the same underlying concept. Documented for
# review, not silently frozen. Any raw value NOT in this map falls
# through to a title-cased version of itself plus an UNMAPPED flag so
# nothing is silently discarded or miscategorized.
MERCHANT_CATEGORY_MAP = {
    # Department Store family
    "department store": "Department Store", "dept_store": "Department Store",
    "department stores": "Department Store",
    # Hotel/Lodging family
    "hotel_lodging": "Hotel/Lodging", "hotel": "Hotel/Lodging", "hotels": "Hotel/Lodging",
    "hospitality": "Hotel/Lodging",
    # Retail family
    "retail": "Retail", "retail other": "Retail", "misc retail": "Retail",
    # Telecom family
    "phone service": "Telecom", "telecom": "Telecom", "mobile recharge": "Telecom",
    # Books & Stationery family
    "stationery": "Books & Stationery", "books": "Books & Stationery",
    "book store": "Books & Stationery", "books_stationery": "Books & Stationery",
    # Apparel family
    "cloths": "Apparel", "garments": "Apparel", "apparel": "Apparel",
    "clothing": "Apparel", "fashion": "Apparel",
    # Transportation family
    "transport": "Transportation", "transprt": "Transportation",
    "transportation": "Transportation", "bus/taxi": "Transportation",
    # Pharmacy / Medical family
    "medical": "Pharmacy/Medical", "medical_store": "Pharmacy/Medical",
    "pharmacy": "Pharmacy/Medical", "pharmacies": "Pharmacy/Medical", "chemist": "Pharmacy/Medical",
    # Restaurant / Food family
    "food": "Restaurant/Food", "eating place": "Restaurant/Food",
    "restaurants": "Restaurant/Food", "restaurant": "Restaurant/Food",
    "food_services": "Restaurant/Food",
    # Grocery family
    "kirana": "Grocery", "grocery": "Grocery", "grocery stores": "Grocery",
    "groceries": "Grocery", "grocery_store": "Grocery",
    # Travel family
    "travel": "Travel",
    # Miscellaneous / Other family
    "miscellaneous": "Miscellaneous", "other": "Miscellaneous",
}


def normalize_mcc(value):
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    if s.lower() in ("misc", "unknown"):
        return None
    s = re.sub(r"^MCC-?", "", s, flags=re.IGNORECASE)
    s = s.split(".")[0]  # drop float-string suffix like '5311.0'
    digits = s.lstrip("0")
    return digits if digits else "0"


def normalize_category(value):
    key = str(value).strip().lower()
    if key in MERCHANT_CATEGORY_MAP:
        return MERCHANT_CATEGORY_MAP[key], True
    return str(value).strip().title(), False


def normalize_business_type(value):
    key = str(value).strip().lower().replace("_", " ").replace("-", " ")
    return BUSINESS_TYPE_MAP.get(key, f"UNKNOWN:{value}")


def normalize_merchant_status(value):
    key = str(value).strip().lower()
    return MERCHANT_STATUS_MAP.get(key, f"UNKNOWN:{value}")


def normalize_city(value):
    key = str(value).strip().lower()
    return CITY_MAP.get(key, str(value).strip().title())


def mask_settlement_account(value):
    """Never expose a full settlement account number - mask all but last 4 chars."""
    if value is None or (isinstance(value, float) and pd.isnull(value)):
        return None
    s = str(value).strip()
    if s == "" or s.upper() == "NA":
        return None
    if s.upper().startswith("XXXX"):
        return s.upper()  # already masked in source
    tail = s[-4:] if len(s) >= 4 else s
    return f"XXXX{tail}"


def clean_merchants(raw_path=RAW_MERCHANTS):
    report = {"dataset": "merchants_master"}
    df = pd.read_csv(raw_path, dtype=str)
    report["raw_rows"] = len(df)

    exact_dup_mask = df.duplicated(keep="first")
    report["exact_duplicate_rows_removed"] = int(exact_dup_mask.sum())
    df = df[~exact_dup_mask].copy()

    df["merchant_id_raw"] = df["merchant_id"]
    df["merchant_id"] = df["merchant_id"].apply(normalize_merchant_id)
    collision = df["merchant_id"].duplicated(keep=False)
    df["merchant_id_has_identity_collision"] = collision
    report["merchant_id_identity_collision_rows"] = int(collision.sum())

    df["merchant_name"] = df["merchant_name"].str.strip().str.replace(r"\s+", " ", regex=True)

    df["mcc_raw"] = df["mcc"]
    df["mcc"] = df["mcc"].apply(normalize_mcc)
    report["mcc_missing"] = int(df["mcc"].isnull().sum())

    df["merchant_category_raw"] = df["merchant_category"]
    cat_parsed = df["merchant_category"].apply(normalize_category)
    df["merchant_category"] = cat_parsed.apply(lambda t: t[0])
    df["merchant_category_was_mapped"] = cat_parsed.apply(lambda t: t[1])
    report["merchant_category_unmapped_values"] = int((~df["merchant_category_was_mapped"]).sum())
    report["merchant_category_distinct_after_cleaning"] = int(df["merchant_category"].nunique())

    df["business_type_raw"] = df["business_type"]
    df["business_type"] = df["business_type"].apply(normalize_business_type)

    df["city_raw"] = df["city"]
    df["city"] = df["city"].apply(normalize_city)
    df["state"] = df["state"].str.strip().str.title()

    ob = parse_timestamp_series(df["onboarding_date"])
    df["onboarding_date_raw"] = df["onboarding_date"]
    df["onboarding_date"] = ob["clean"]
    report["onboarding_date_missing"] = int(df["onboarding_date_raw"].isnull().sum())
    report["onboarding_date_invalid"] = int(ob["is_invalid"].sum())

    df["settlement_account_raw_present"] = df["settlement_account"].notnull()
    df["settlement_account_masked"] = df["settlement_account"].apply(mask_settlement_account)
    df = df.drop(columns=["settlement_account"])
    report["settlement_account_missing"] = int((~df["settlement_account_raw_present"]).sum())

    df["merchant_status_raw"] = df["merchant_status"]
    df["merchant_status"] = df["merchant_status"].apply(normalize_merchant_status)

    tix = clean_amount_series(df["declared_avg_ticket_size"])
    df["declared_avg_ticket_size_raw"] = df["declared_avg_ticket_size"]
    df["declared_avg_ticket_size"] = tix["clean"]
    df["declared_avg_ticket_size_had_negative_sign"] = tix["had_negative_sign"]
    report["ticket_size_missing"] = int(df["declared_avg_ticket_size_raw"].isnull().sum())
    report["ticket_size_negative_flagged"] = int(tix["had_negative_sign"].sum())

    report["rows_retained"] = len(df)
    report["rows_removed"] = report["raw_rows"] - report["rows_retained"]
    return df, report


if __name__ == "__main__":
    df, report = clean_merchants()
    print(report)
    print(df.head())
