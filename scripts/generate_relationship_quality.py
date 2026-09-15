#!/usr/bin/env python3
"""Regenerates reports/relationship_quality.csv from the CLEANED data,
so it's a reproducible pipeline output rather than a one-off manual
artifact from the Stage 1 exploration. Numbers should match the
original raw-data exploration in DATA_AUDIT.md within rounding, since
normalization does not change which underlying entity an ID refers to."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.config import REPORTS_DIR
from src.analytics.loaders import load_transactions, load_users, load_merchants, load_chargebacks


def main():
    txn = load_transactions()
    users = load_users()
    merchants = load_merchants()
    cb = load_chargebacks()

    rows = []

    def add(rel, total, matched, note):
        rows.append({"relationship": rel, "total_records": total, "matched": matched,
                      "unmatched": total - matched, "match_pct": round(matched / total * 100, 2) if total else 0.0,
                      "note": note})

    user_ids = set(users["user_id"].dropna())
    merchant_ids = set(merchants["merchant_id"].dropna())
    txn_ids = set(txn["txn_id"].dropna())

    m = txn["user_id"].isin(user_ids).sum()
    add("transactions.user_id -> kyc_records.user_id", len(txn), int(m),
        "Match rate statistically consistent with random ID overlap (see DATA_AUDIT.md Open Question #1).")

    m = txn["merchant_id"].isin(merchant_ids).sum()
    add("transactions.merchant_id -> merchants_master.merchant_id", len(txn), int(m),
        "Match rate statistically consistent with random ID overlap (see DATA_AUDIT.md Open Question #1).")

    m = cb["txn_id"].isin(txn_ids).sum()
    add("chargebacks.txn_id -> transactions.txn_id", len(cb), int(m),
        "The one reliable identity join in this dataset (normalized format).")

    m = cb["user_id"].isin(user_ids).sum()
    add("chargebacks.user_id -> kyc_records.user_id", len(cb), int(m), "Same low-match pattern as transactions->KYC.")

    m = cb["merchant_id"].isin(merchant_ids).sum()
    add("chargebacks.merchant_id -> merchants_master.merchant_id", len(cb), int(m), "Same low-match pattern as transactions->Merchants.")

    dupgroups_kyc = users[users.duplicated("user_id", keep=False)].groupby("user_id")["full_name"].nunique()
    conflict_kyc = (dupgroups_kyc > 1).sum()
    rows.append({"relationship": "kyc_records.user_id normalized-key collisions", "total_records": len(users),
                 "matched": int(users["user_id"].duplicated().sum()), "unmatched": None, "match_pct": None,
                 "note": f"{conflict_kyc} of {len(dupgroups_kyc)} duplicate-key groups contain rows with DIFFERENT full_name (distinct people sharing one ID)."})

    dupgroups_mer = merchants[merchants.duplicated("merchant_id", keep=False)].groupby("merchant_id")["merchant_name"].nunique()
    conflict_mer = (dupgroups_mer > 1).sum()
    rows.append({"relationship": "merchants_master.merchant_id normalized-key collisions", "total_records": len(merchants),
                 "matched": int(merchants["merchant_id"].duplicated().sum()), "unmatched": None, "match_pct": None,
                 "note": f"{conflict_mer} of {len(dupgroups_mer)} duplicate-key groups contain rows with DIFFERENT merchant_name."})

    pd.DataFrame(rows).to_csv(REPORTS_DIR / "relationship_quality.csv", index=False)
    print(f"Wrote {REPORTS_DIR / 'relationship_quality.csv'}")


if __name__ == "__main__":
    main()
