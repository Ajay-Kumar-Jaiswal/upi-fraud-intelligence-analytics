# UPI Fraud Ring & Merchant Analytics
**TransOrg AgentIQ Datathon — Track 1: FinTech & BFSI**

> **AI-assistance disclosure**: this project (code, analysis, and this README) was built with
> AI assistance (Claude). Per the datathon's own README guidance, this is disclosed
> plainly rather than claimed as independently hand-written. All numbers, findings, and
> risk scores are computed from the actual uploaded dataset — nothing is fabricated —
> but the participant should review, understand, and be ready to defend every part of
> this submission before presenting it as their own work.

## 1. Business problem
A National Payments Authority needs to analyze UPI micro-transaction data to identify
circular money-laundering rings, synthetic identity fraud, and compromised merchant
accounts, from a dataset that is intentionally messy (missing UTRs, malformed IDs, OCR
errors, currency symbols in numeric fields, broken relationships between tables).

## 2. What this project actually found (headline results)
- Cleaned 4 raw files (20,400 transactions / 36,400 KYC records / 6,210 merchants / 2,884
  chargebacks) down to a validated, reproducible analytical model with **97–99.8% row
  retention** (only exact duplicates dropped — see `reports/DATA_QUALITY_EVIDENCE.md`).
- **The most important finding isn't a fraud number — it's a data-integrity one**:
  `user_id`/`merchant_id` joins from transactions to the KYC/merchant-master files match at
  rates (~32% / ~48%) that are **statistically indistinguishable from random ID overlap**
  (verified against the expected random-chance baseline, not just eyeballed). This is
  documented, tested, and propagated into every downstream chart as a visible coverage
  caveat — see `reports/DATA_AUDIT.md`, Open Question #1.
- Chargeback-to-transaction ratio: **13.04%** (2,607 chargebacks reliably matched to
  20,000 transactions via the one high-coverage identity join in this dataset — 93.1%).
- Bonus question answer: **Travel** has the highest chargeback-to-transaction ratio this
  quarter (15.67%), computed dynamically, with the coverage limitation and the thin
  margin over the runner-up (Retail, 15.57%) both stated explicitly rather than hidden.
- An explainable, rule-based risk engine flags **3 merchants CRITICAL** and **38
  HIGH/CRITICAL** out of 658 merchants with sufficient volume; 0 users reached HIGH/CRITICAL.
- The transaction graph is genuinely sparse: **no user ever transacts with the same
  merchant twice**, and **no two merchants share even 2 common users**, in this data
  window — reported as a real finding, not suppressed for being "boring."

## 3. Architecture
```
RAW CSV/JSON  →  src/cleaning/*  →  data/processed/*.parquet  →  src/analytics/*
                                                                        ↓
                                         src/fraud/risk_engine.py, src/graph/network_analysis.py
                                                                        ↓
                                    dashboard/ (Streamlit + Plotly)  ←  agent/ (deterministic NL agent)
```
- **Data processing**: Pandas + Parquet (no heavier infra needed at this data volume — ~66K
  rows across all four files).
- **Dashboard**: Streamlit + Plotly, 8 pages, all reading from the same tested analytics
  functions the agent and the test suite use — the dashboard cannot disagree with the code.
- **AI Analyst**: a deterministic intent router + query engine (agent/) that matches a
  question to one of 12 supported analysis types and calls a real, tested function — never
  arbitrary LLM-generated code or SQL. An optional Anthropic API key adds cosmetic phrasing
  polish only; the agent is fully correct and fully functional without one.

## 4. Dataset
| File | Rows | Description |
|---|---|---|
| `track1_upi_transactions.csv` | 20,400 | UPI transactions |
| `track1_kyc_records.csv` | 36,400 | Customer KYC records |
| `track1_merchants_master.csv` | 6,210 | Merchant master data |
| `track1_chargebacks.json` | 2,884 | Chargeback/dispute records |

Full column-by-column documentation: **`data_dictionary.csv`** (generated from the actual
cleaned schema — the generator script fails loudly if documentation drifts from code).

## 5. Data rescue (cleaning methodology)
See `reports/DATA_AUDIT.md` (initial reconnaissance) and `reports/DATA_QUALITY_EVIDENCE.md`
(final before/after evidence, regenerated from pipeline output, not hand-typed). Highlights:
- Currency symbols (₹/Rs./INR), commas, and sign-corruption noise cleaned from all amount
  fields, with the original value always preserved in a `*_raw` audit column.
- 6 raw ID-format variants normalized per file; Unix-epoch timestamps (including negative,
  pre-1970 values) detected and converted; 6+ concurrent status/category coding schemes
  collapsed into controlled vocabularies.
- **Nothing is silently dropped or invented** — ambiguous/invalid values are flagged with
  boolean audit columns and kept, not deleted, unless they are exact full-row duplicates.

## 6. Data model
- `fact_transactions`, `fact_chargebacks` (event grain)
- `dim_users`, `dim_merchants` (one row per raw KYC/merchant-master record — **not**
  deduplicated to one-per-entity, because `user_id`/`merchant_id` are not safe unique
  keys in this dataset, even for exact string matches — see Open Question #1)

## 7. KPIs & analytics (`src/analytics/`)
Every KPI's formula, source columns, and join-coverage caveat (where relevant) are
documented in the module docstrings and in `reports/analytics_validation.md` (regenerated
from live code each run). Covers core transaction KPIs, chargeback analytics, merchant
category performance, KYC-linked and merchant-master-linked analytics (both explicitly
coverage-labeled), time trends, and the official bonus question.

## 8. Fraud/risk methodology (`src/fraud/risk_engine.py`)
Fully explainable, rule-based, additive scoring (0–100) — no black-box model. Every
flagged entity carries a `risk_reasons` list naming exactly which documented, configurable
threshold it crossed (e.g. "chargeback-to-transaction ratio > 30%"). Terminology is
deliberately cautious ("potential risk", "requires investigation") since the dataset has
no ground-truth fraud label.

## 9. Network analysis (`src/graph/network_analysis.py`)
NetworkX bipartite user↔merchant graph. Reports high-degree nodes, repeated relationships,
connected components, and dense clusters — and explicitly explains *why* this dataset's
bipartite user→merchant structure cannot contain a true transaction cycle (would need
account-to-account transfer data, which this dataset doesn't have), rather than fabricating
a "circular fraud ring" the graph shape cannot support.

## 10. Dashboard
8 pages: Executive Overview, Transaction Analytics, Fraud & Risk, Merchant Intelligence,
Chargebacks, Network Analysis, Data Quality & Coverage, AI Analyst. All interactive
(date/status filters, drill-downs, tooltips), with empty-state and missing-data handling
throughout. Verified with Streamlit's `AppTest` framework (genuine script execution, not
just an HTTP 200 check) — see Testing below.

## 11. AI Analyst
Supports 12 question types including the official bonus question, merchant/user risk
lookups, chargeback breakdowns, network clusters, and trend questions. Unsupported
questions get an explicit "I cannot answer this reliably" response listing what IS
supported — never a guess.

## 12. Data-quality / coverage caveats (read this before trusting any single number)
1. **KYC/merchant-master joins cover only ~30–48% of transactions** and are not enforced
   as foreign keys — every affected chart/metric shows its own coverage %.
2. Even *within* the KYC and merchant-master files, the same ID can refer to different
   real people/merchants (identity collisions) — flagged, not silently resolved.
3. The chargeback-to-transaction link (via `txn_id`) is the one reliable identity join
   (93.1%) and is used wherever a chargeback needs to be attributed to a specific merchant.
4. The bonus-question answer rests on a genuinely thin margin (Travel vs Retail, <0.1pp
   apart) within a coverage-limited subset — reported as indicative, not high-confidence.

## 13. Setup & usage
```bash
git clone <this-repo>
cd <this-repo>
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

# Place the 4 raw files in data/raw/ (already present if you cloned with the dataset)

# Run the full pipeline (cleaning -> all reports -> data dictionary)
python scripts/run_all.py

# Run the test suite (121 tests)
pytest tests/ -q

# Start the dashboard
streamlit run dashboard/app.py
```

### Optional: AI Analyst LLM phrasing polish
```bash
cp .env.example .env
export $(cat .env | xargs)   
streamlit run dashboard/app.py
```
The AI Analyst is fully correct and fully functional **without** this — it only affects
phrasing, never the numbers.

## 14. Testing
```bash
pytest tests/ -v          
                          
```
All tests run against the **actual uploaded dataset**, not synthetic fixtures. Includes
divide-by-zero/empty-data guards, regression guards for documented data-quality findings
(e.g. the ~32% KYC join rate), and dashboard-page execution tests via Streamlit's `AppTest`.

## 15. Deployment
- **Docker**: `docker build -t upi-fraud-analytics . && docker run -p 8501:8501 upi-fraud-analytics`
  — builds the image, runs the full pipeline at build time, starts the dashboard.
  **NOT VERIFIED — REQUIRES MANUAL VERIFICATION** (no Docker daemon available in the
  development sandbox this was built in; the Dockerfile follows a standard, tested pattern
  but was not itself run end-to-end in a container).
- **Streamlit Community Cloud**: point it at this repo, entry file `dashboard/app.py`,
  add `ANTHROPIC_API_KEY` as a secret only if you want the optional LLM polish.
  **NOT VERIFIED — REQUIRES MANUAL VERIFICATION** (requires an actual GitHub push and a
  Streamlit Cloud account, neither of which this environment can perform).
- **Verified locally**: the dashboard was started and every one of its 8 pages was
  confirmed to execute without exception (`streamlit.testing.v1.AppTest`), and a
  live local server was curl-tested (`HTTP 200` on `/` and `/_stcore/health`) — see
  `reports/DATA_QUALITY_EVIDENCE.md` §11 and the project's development log for how.

## 16. Project structure
```
project/
├── data/{raw,processed}/
├── src/{cleaning,analytics,fraud,graph,utils}/
├── dashboard/{app.py,pages/,components/,data_loader.py}
├── agent/{router.py,query_engine.py,analyst.py,llm_provider.py}
├── tests/
├── reports/           
├── scripts/            
├── data_dictionary.csv
├── requirements.txt, .env.example, .gitignore
├── Dockerfile, Procfile, runtime.txt, .streamlit/config.toml
└── README.md
```

## 17. Limitations (stated plainly)
- KYC/merchant-master-linked analytics cover a minority of transactions by construction of
  this dataset — not a bug, a property of the raw data (see §12).
- No fraud/money-laundering ground-truth label exists in this dataset, so every risk score
  is a documented heuristic, not a validated fraud classifier.
- Actual live deployment (Docker run, Streamlit Cloud) is prepared but **not independently
  verified** in this environment — see §15.
- The AI Analyst supports a fixed set of 12 question patterns; questions outside that set
  get an honest "cannot answer" rather than a best-effort guess.

## 18. Future improvements
- Expand the agent's intent set and add fuzzy/semantic intent matching (currently regex-based).
- If a true entity-resolution signal becomes available (e.g. device ID, phone number),
  revisit the ~32%/48% identity-join limitation with proper record-linkage techniques.
- Persist risk scores/graph outputs to Parquet instead of recomputing per dashboard session
  (currently fast enough at this data volume not to need it — see `st.cache_data` usage).
