"""
Loads ONLY the cleaned/validated Parquet output produced by
scripts/run_pipeline.py. Analytics code must never read raw CSV/JSON
directly - that would bypass the cleaning and validation logic already
built and tested in Stage 3/4.
"""
import pandas as pd
from src.config import CLEAN_TRANSACTIONS, CLEAN_KYC, CLEAN_MERCHANTS, CLEAN_CHARGEBACKS


def load_transactions() -> pd.DataFrame:
    return pd.read_parquet(CLEAN_TRANSACTIONS)


def load_users() -> pd.DataFrame:
    return pd.read_parquet(CLEAN_KYC)


def load_merchants() -> pd.DataFrame:
    return pd.read_parquet(CLEAN_MERCHANTS)


def load_chargebacks() -> pd.DataFrame:
    return pd.read_parquet(CLEAN_CHARGEBACKS)
