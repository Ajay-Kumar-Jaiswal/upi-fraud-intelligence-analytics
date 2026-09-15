# DATA_AUDIT.md — Track 1: UPI Fraud Ring & Merchant Analytics
Generated from direct inspection of the uploaded files. All numbers below were computed against the actual data (see companion `reports/data_quality_before.csv` and `reports/relationship_quality.csv`).

## 1. Files discovered
| File | Type | Rows (excl. header) | Columns |
|---|---|---|---|
| track1_upi_transactions.csv | CSV | 20,400 | 8 |
| track1_kyc_records.csv | CSV | 36,400 | 12 |
| track1_merchants_master.csv | CSV | 6,210 | 11 |
| track1_chargebacks.json | JSON (flat list of objects) | 2,884 | 13 |
| track1_dataset_notes.txt | Notes | — | — |

The notes file explicitly documents intended join keys and the messy-data patterns to expect — this was read in full and used to guide the audit (not invented).

## 2. Columns present (actual, not assumed)

**transactions**: `txn_id, timestamp, user_id, merchant_id, amount, utr, mcc, status`

**kyc_records**: `user_id, full_name, pan, aadhaar, date_of_birth, city, state, monthly_income, occupation, signup_timestamp, kyc_status, risk_segment`

**merchants_master**: `merchant_id, merchant_name, mcc, merchant_category, business_type, city, state, onboarding_date, settlement_account, merchant_status, declared_avg_ticket_size`

**chargebacks**: `complaint_id, txn_id, user_id, merchant_id, transaction_timestamp, reported_timestamp, disputed_amount, reason_code, complaint_text, resolution_status, bank_response_timestamp, severity, channel`

## 3. Data-quality findings by file

### 3.1 transactions (20,400 rows)
- **Exact duplicate rows**: 400 rows are byte-for-byte duplicates of another row (200 pairs → 400 rows, `duplicated()=400`). Duplicate `txn_id` count also = 400, and **every** duplicate-`txn_id` group is a full exact duplicate (0 conflicting/near-duplicate cases) — safe to drop via simple exact-dedup.
- **`amount`**: contains `₹`, `Rs.`, `INR`, thousands separators, and plain numbers. After stripping symbols, **100% parse to numeric** (0 unparseable in this file). **429 rows (2.1%) have negative amounts.** Negative rate is ~2–3% and statistically flat across every transaction status (FAILED, SUCCESS, PENDING all ≈2%) — i.e., negativity does **not** correlate with failed/reversed transactions, so it does not look like a meaningful refund/reversal signal. Magnitude distribution of negatives mirrors positives (mean |amount| ≈ ₹12,500 either way). **This needs a decision — see Open Question #2 below.**
- **`timestamp`**: mixed formats — `YYYY-MM-DD HH:MM:SS`, `DD/MM/YYYY HH:MM:SS`, `MM-DD-YYYY HH:MM:SS AM/PM`, and **1,012 rows (5.0%) are raw Unix epoch seconds** (e.g. `1770063471`). A fuzzy-parse pass with epoch-detection resolved 300/300 in a random sample — full parse will need day-first/month-first disambiguation rules per detected pattern (documented, not guessed row-by-row).
- **`utr`**: 1,024 rows (5.0%) missing. Of the non-missing, 1,881 have a stray space after `UTR` (`UTR 1234567890` vs `UTR1234567890`) — a formatting issue, not a validity issue. No UTRs are fabricated or reconstructed.
- **`mcc`**: 2,926 rows (14.3%) missing. Only 6 raw values exist: `5411/05411, 4131, 5812, 5912, 7011` — i.e. some codes carry a leading zero. Trivial, defensible normalization (strip leading zeros).
- **`status`**: 14 raw spellings collapse into 4 real states — Success (`S, Success, SUCCESS, TXN_SUCCESS, COMPLETED`), Failed (`F, Fail, FAILED, TXN_FAILED, Declined`), Pending (`Pending, PENDING, Initiated`), Processing (`PROCESSING`). Mapping is unambiguous from the value set itself.
- **`user_id` / `merchant_id`**: in this file specifically, formats are **already clean** — 100% match `USR#####` / `MCH####` with no case/hyphen/space variants. (The messy-ID formats described in the dataset notes show up in the KYC and merchant master files, not here — confirmed empirically, not assumed.)

### 3.2 kyc_records (36,400 rows)
- **Exact duplicate rows**: 278.
- **`user_id` formats**: 6 distinct format families found — `USR12345` (23,490), lowercase `usr12345` (3,708), `USR 12345` (3,329), `USR-12345` (2,575), `USR_12345` (1,804), bare `12345` (1,494). All normalize cleanly to a canonical `USR#####` by stripping non-digits.
- **Critical finding — `user_id` is not a reliable identity key, even before normalization**: 3,818 *exact-string-identical* `user_id` values appear more than once, and **2,634 of those 3,818 groups (69%) contain different `full_name`/`PAN` values** — i.e. the same literal ID string is assigned to clearly different people. After normalization, duplicate-key groups rise to 6,288, of which **5,341 (85%) contain conflicting names/PAN**. This is not a formatting artifact; it means `user_id` cannot be treated as a unique person-key in this dataset without further rules. **See Open Question #1.**
- **`pan`**: 1,896 missing (5.2%). Of populated values, only ~67% (23,191/34,504) match the real PAN structure `AAAAA9999A` after case/space/hyphen normalization — remainder have OCR-style corruption (missing digit, wrong length) that should be flagged `invalid` rather than silently coerced.
- **`aadhaar`**: 2,664 missing (7.3%). Mixed formats: plain 12-digit, spaced `9999 9999 9999`, hyphenated, and **partially masked `XXXX-XXXX-9999`** values already present in the raw source — these masked values must be preserved as masked, never "unmasked" or fabricated.
- **`date_of_birth`**: 2,944 missing (8.1%). Formats mixed (`DD-MM-YYYY`, `MM/DD/YYYY`, `YYYY/MM/DD`, `DD-Mon-YYYY`, epoch, datetime-with-time). No DOB values were invented; missing stays missing.
- **`monthly_income`**: 2,933 missing (8.1%). Mixed currency symbols/commas, `21.0k`-style shorthand, and literal text `"Not Available"` (which is a disguised-null, not a numeric value — must be coerced to null, not to 0).
- **`city`**: 41 raw distinct labels for what is a much smaller real set of cities — case variants, abbreviations (`LDH`→Ludhiana, `Hyd`→Hyderabad, `LKO`→Lucknow, `JPR`→Jaipur), and colonial/alternate names (`Bombay`→Mumbai, `Poona`→Pune, `Calcutta`→Kolkata, `Jalandar`→Jalandhar typo). A mapping table is proposed but **not yet applied** — needs sign-off since some (Bombay/Mumbai) are legally/politically sensitive renamings, not just typos.
- **`kyc_status`**: 16 raw spellings across what looks like 4 real states (Verified/Done/Approved-family, Pending/In-Progress-family, Rejected/Reject/Failed-family, plus single-letter codes `V/P/R`).
- **`risk_segment`**: case variants of Low/Medium/High/Unknown only — trivial normalization.

### 3.3 merchants_master (6,210 rows)
- **Exact duplicate rows**: 12.
- **`merchant_id`**: same collision pattern as KYC — 1,127 raw exact-string duplicates; after normalization, 1,412 duplicate-key groups, of which **1,310 (93%) have different `merchant_name` values**, i.e. distinct merchants sharing one ID. **See Open Question #1 (same root cause as KYC).**
- **`mcc`**: 514 missing (8.3%), plus free-text `misc`/`UNKNOWN` and leading-zero/float-string variants (`05699`, `5311.0`) of the same numeric codes.
- **`merchant_category`**: **82 distinct raw labels** for what is clearly a small set of real categories (case, underscore/space, singular/plural variants of e.g. "grocery stores"/"grocery_store"/"Grocery Store"). Needs a canonical category map before any "chargeback ratio by merchant category" metric is meaningful.
- **`business_type`**: 14 raw labels, all case/separator variants of 4 real types (Individual, Partnership, Sole Proprietor, Private Limited).
- **`merchant_status`**: 15 raw labels including single-letter codes (`A/I/S`) mapping to Active/Inactive/Suspended plus close synonyms (Enabled/Live/Closed/Disabled/Hold/Blocked) that need a documented, defensible collapse — some of these (Hold vs Suspended vs Blocked) are not obviously identical and will be flagged rather than silently merged.
- **`settlement_account`**: 2,451 missing (39.5%) — high missingness; some values are partially masked (`XXXX4409`). This is sensitive financial data and will be masked in any dashboard/log regardless of source formatting.
- **`declared_avg_ticket_size`**: same currency-symbol/comma mess as transaction `amount`, plus some negative values (371 missing separately).

### 3.4 chargebacks.json (2,884 records)
- Flat JSON array of objects — no nested structures needing flattening.
- **Exact duplicate records**: 84 (by `complaint_id` and full-row).
- **302 transactions have more than one chargeback record** — needs a rule (multiple genuine disputes vs. duplicate submissions vs. status-update re-records); complaint text was spot-checked and looks like genuine distinct complaints in most sampled cases, not simple duplicates.
- **`txn_id`**: 81 blank (2.8%). Populated values include 3 format families: standard `TXN00012345` (2,577), unpadded `TXN12345` (120), and lowercase-hyphenated `txn-00012345` (106). Matching on the **numeric part only** raises the match rate against transactions from 89.4% → 93.0% — this is a formatting problem, not a missing-relationship problem, for this particular key.
- **`disputed_amount`**: 183 blank (6.3%), rest mixed currency-symbol/comma text like `amount`; also contains negative values (same profile/question as transaction `amount`).
- **`reason_code`**: **34 raw values** that are clearly case/phrasing variants of ~10–12 real reasons (e.g. `DUP_DEBIT` / `Duplicate Debit` / `charged twice` / `double debit` all mean the same thing; `ATO` / `Account Takeover` / `account hacked` / `login compromised` cluster together). A reason-code taxonomy will be proposed for review before use in any "chargeback reason distribution" chart.
- **`severity`**: 16 raw values mixing 3 different coding schemes simultaneously — word (`Low/Medium/High/Critical`), single-letter (`L/M/H`), and priority-code (`P1–P4`). The **mapping between the priority codes and the word/letter scale is not stated anywhere in the source data or notes** — e.g. is `P1` "Critical" or "High"? This is inferred, not given. **See Open Question #3.**
- **`resolution_status`**: 13 raw values, case + snake_case variants of ~6 real states (Open, In Progress/WIP, Pending Bank, Resolved, Rejected, Closed).
- **`channel`**: 8 raw values, case variants of 4 real channels (Email, Branch, IVR, Chatbot, App, Call Center) — note "IVR"/"Call Center" are somewhat distinct channels also, will confirm collapsing rule.
- **`bank_response_timestamp`**: 718 blank (24.9%) — plausible (not every case has received a bank response yet); will *not* be treated as a data-quality defect, just a valid missing state tied to `resolution_status`.

## 4. Relationship / join findings — **the most important result of this audit**

Full numbers in `reports/relationship_quality.csv`. Summary:

| Relationship | Match rate | Verdict |
|---|---|---|
| transactions.user_id → kyc_records.user_id | **32.4%** (6,617 / 20,400 txns) | ⚠️ See below |
| transactions.merchant_id → merchants_master.merchant_id | **48.1%** (9,809 / 20,400 txns) | ⚠️ See below |
| chargebacks.txn_id → transactions.txn_id (numeric match) | 93.0% (2,683 / 2,884) | ✅ Usable |
| chargebacks.user_id → kyc_records.user_id | 31.8% | ⚠️ Same pattern as above |
| chargebacks.merchant_id → merchants_master.merchant_id | 46.3% | ⚠️ Same pattern as above |

**I tested whether the low user/merchant match rates are a real (if partial) relationship, or statistical noise, by comparing the observed intersection to what pure-random ID overlap would produce given the ID ranges in each file:**
- Users: transactions touch 17,878 distinct user IDs, KYC has 28,920 distinct user IDs, both drawn from the same `10001–99999` numeric range. **Observed overlap: 5,799. Expected overlap under pure random assignment: 5,745.** These are statistically indistinguishable.
- Merchants: transactions touch 8,051 distinct merchant IDs, merchant master has 4,343, both drawn from `1000–9999`. **Observed overlap: 3,893. Expected under pure random assignment: 3,885.** Again statistically indistinguishable.

**In plain terms: at the individual-transaction level, `user_id`/`merchant_id` do not reliably link a transaction to a specific, correct KYC/merchant record — the match rate we see is almost exactly what coincidence alone would produce.** This is compounded by the finding in §3.2/3.3 that the same ID string is independently reused for different real-world people/merchants within the KYC and merchant files themselves. Root cause looks like the ID fields were generated independently per file (not from one shared entity table) rather than there being a genuine broken-but-recoverable relationship. **See Open Question #1 — this blocks any per-transaction "join to KYC/merchant to get true identity" analysis until we agree on how to handle it.**

The chargeback→transaction link is comparatively solid (93%) once txn_id formatting is normalized, and does not show this problem.

## 5. Important ambiguities — I need your decision before building the pipeline

**Open Question #1 — User/merchant identity join is unreliable (highest priority).**
`user_id`/`merchant_id` match KYC/merchant master at roughly the rate pure chance would produce, and the same ID is reused for different real people/merchants within KYC/merchants_master itself. Options, none of which I'll pick silently:
  - **(a)** Treat this as intentional — the datathon is testing whether we notice and report a broken relationship, rather than actually fixing it. We'd build `fact_transactions` with `user_id`/`merchant_id` as raw attributes (not enforced foreign keys), document the match-rate ceiling explicitly in every KYC-joined or merchant-master-joined metric, and clearly caveat any dashboard page that depends on that join (e.g., "KYC Risk" page, "synthetic identity" analysis).
  - **(b)** Attempt best-effort disambiguation (e.g., prefer the most recent KYC record per ID, or use additional weak signals) — but this would need a defensible, documented rule and would still only be a heuristic, not a true fix, given the underlying join field is not selective.
  - **(c)** Something else you have in mind about how this dataset was generated.
  I recommend (a) as the analytically honest default, and will proceed that way unless you tell me otherwise, but wanted to flag it explicitly since it materially limits Layer 2/3 (KYC risk pages, synthetic-identity network analysis) — those sections will need to be framed around aggregate/file-level patterns rather than "this specific flagged user."

**Open Question #2 — Negative `amount` / `disputed_amount` values (~2% of rows).**
No status correlation, no notes-file explanation, magnitude distribution mirrors positive values. My read: this looks like injected data-entry noise (sign corruption), not a refund/reversal semantic. Proposed rule: take `abs(amount)` into the canonical numeric field, keep the original signed value in an audit column (`amount_raw`), and add a boolean `had_negative_sign` flag so it's visible/filterable rather than silently discarded. Will implement this unless you specify a different interpretation.

**Open Question #3 — Chargeback `severity` mixes three incompatible coding schemes (word / letter / P-code) with no documented mapping.**
Proposed mapping based on typical BFSI severity conventions (P1=Critical, P2=High, P3=Medium, P4=Low) — but this is an assumption I'm making explicit, not something the data states. I'll implement it as a documented, reviewable rule (with the original value preserved) rather than hide it — flag if you want a different mapping.

**Minor items I'll resolve with a documented default (not blocking, but noting):** city-name canonicalization (Bombay→Mumbai etc.), merchant_status collapsing (Hold vs Suspended vs Blocked), and the 302 transactions with multiple chargeback records (default: keep all, model `fact_chargebacks` at complaint grain, let `fact_transactions` be joined 1-to-many).

## 6. Proposed architecture (for your confirmation — not yet built)

- **Modeling approach**: Pandas + DuckDB, Parquet intermediates. No heavier infra needed for this data volume (~66K rows across all files).
- **Data model**: `fact_transactions`, `fact_chargebacks`, `dim_users` (from KYC, grain = one row per raw KYC record, since user_id is not a safe dedup key — see Q1), `dim_merchants` (same caveat), plus a `bridge`/audit table documenting join-match rates so every dashboard page can show its own data-completeness caveat.
- **Cleaning pipeline**: modular `src/cleaning/{transactions,kyc,merchants,chargebacks}.py`, each emitting a before/after row-level audit trail as specified in your brief (raw_rows, duplicates, missing_handled, invalid, removed, retained, repaired).
- **Validation**: `src/validation/` with schema, dtype, dedup, and FK-match-rate checks; pipeline fails loudly (raises) on critical assumption breaks (e.g. amount not numeric after cleaning), but *does not* fail on the known-low user/merchant match rate — that's an expected, documented characteristic of this dataset, not a pipeline bug.
- **Analytics layer**: KPIs computable without the broken join (transaction volume/value/success-failure rates, chargeback-to-transaction ratio by merchant *category* using `merchants_master` and `transactions.merchant_id` directly with the match-rate caveat surfaced in the UI, chargeback reason/severity/channel distributions) computed first; KYC-dependent metrics computed second, always labeled with their join-coverage percentage.
- **Risk engine**: explainable, rule-based (chargeback ratio, duplicate-key identity collisions, cycle detection in the transaction graph) — no black-box scoring, per your brief.
- **Network analysis**: NetworkX graph of user_id/merchant_id/txn edges; cycle/high-degree/dense-cluster detection; explicit heuristic thresholds documented; explicitly notes where the identity-join limitation constrains interpretation (e.g., "high-degree user_id" ≠ confirmed same real person, since IDs collide).
- **Dashboard**: Streamlit + Plotly, structured per your Section 18 page plan, each page with a visible data-completeness badge where relevant.
- **AI agent**: schema-aware controlled query generation (allow-listed tables/columns, no arbitrary code exec), chart-type selection by question pattern, explicit "I cannot answer this reliably" fallback, LLM-provider abstraction (env-var based, no hardcoded keys) — using the Anthropic API by default with a pluggable interface.

## 7. Risks / blockers
1. **Open Question #1 is the main blocker** — it changes what several dashboard pages and the "synthetic identity" analysis can honestly claim. I'd like your sign-off before building those specific pages so I don't build something analytically misleading.
2. Merchant-category taxonomy (82→~15 raw labels) needs a mapping table — I'll draft one for your review rather than freeze it silently, since it directly drives the bonus business question (chargeback-to-transaction ratio by category).
3. Everything else (amount/date/ID/status cleaning) is mechanical and low-risk; I don't anticipate needing further input there beyond Q2/Q3 above.

## 8. Staged implementation plan (unchanged from your brief, sequenced against what I now know)
1. ✅ Stage 1 — Dataset reconnaissance (this document) — **done, awaiting your confirmation/answers to Q1–Q3**
2. Stage 2 — Architecture proposal sign-off (§6 above)
3. Stage 3 — Cleaning pipeline per file, with audit trail
4. Stage 4 — Validation suite
5. Stage 5 — Analytics layer (KPIs, chargeback ratio, merchant/category performance)
6. Stage 6 — Fraud/risk scoring engine (explainable)
7. Stage 7 — Transaction network analysis
8. Stage 8 — Streamlit dashboard (6 pages)
9. Stage 9 — AI agent (controlled NL→chart)
10. Stage 10 — Tests (pytest)
11. Stage 11 — Deployment prep (Streamlit Community Cloud)
12. Stage 12 — Documentation (README draft, data dictionary)
13. Stage 13 — Rubric audit + demo script + presentation content

**Waiting for your go-ahead and answers to Open Questions #1–#3 before Stage 2/3.**
