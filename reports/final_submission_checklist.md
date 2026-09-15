# Final Submission Checklist

## VERIFIED (actually run in this environment, this session)
- [x] Full pipeline runs end-to-end from RAW data with `data/processed/` and all report CSVs
      wiped beforehand (`python scripts/run_all.py`) — confirmed twice.
- [x] 121/121 pytest tests pass on a freshly rebuilt pipeline.
- [x] All 8 dashboard pages execute with zero exceptions, verified via
      `streamlit.testing.v1.AppTest` (genuine script execution, not just an HTTP check).
- [x] A live local Streamlit server was started and both `/` and `/_stcore/health`
      returned HTTP 200.
- [x] Every Python file in the project compiles cleanly (`py_compile`), no broken imports.
- [x] `data_dictionary.csv` generator confirmed zero drift against the live cleaned schema.
- [x] No hardcoded secrets found in a repo-wide scan; no `.env` file present; `.gitignore` excludes secrets and derived data.
- [x] Bonus question ("highest chargeback-to-transaction ratio by merchant category this
      quarter") computed dynamically from actual data, not hardcoded — cross-checked with
      an independent from-scratch pandas script in Stage 5 and a dedicated regression test.
- [x] Agent answers cross-checked against the same deterministic functions the dashboard uses.
- [x] Multiple real bugs found DURING testing and fixed (not hidden): epoch-timestamp
      regex missing negative pre-1970 dates; merchant-category map covering only ~55 of 82
      raw values; chargeback→merchant resolution producing ratios >1.0 by trusting an
      unreliable raw field instead of the high-coverage txn_id link; `nan` leaking into a
      markdown report; a 0/0 RuntimeWarning. All documented in `reports/DATA_AUDIT.md`,
      `reports/DATA_QUALITY_EVIDENCE.md`, and this session's history.

## NOT VERIFIED — REQUIRES MANUAL VERIFICATION
- [ ] **Public GitHub repository** — this environment cannot perform `git push`. Everything
      needed (clean structure, `.gitignore`, no secrets) is prepared.
- [ ] **Live deployment** (Streamlit Community Cloud or Docker container actually running) —
      the `Dockerfile`/`Procfile`/`.streamlit/config.toml` are prepared and follow standard,
      tested patterns, but no Docker daemon or Streamlit Cloud account is available here to
      actually run/deploy them.
- [ ] Multi-user / concurrent-load behavior of the dashboard — only single-session local
      testing was performed.

## Contents of this submission
- `README.md` — full write-up (architecture, results, setup, limitations, AI-assistance disclosure)
- `data_dictionary.csv` — every field, generated from the live schema
- `reports/DATA_AUDIT.md` — Stage 1 reconnaissance findings and open questions
- `reports/DATA_QUALITY_EVIDENCE.md` — before/after cleaning evidence, regenerated from pipeline output
- `reports/analytics_validation.md` — every KPI formula + actual computed value
- `reports/relationship_quality.csv`, `reports/join_coverage_report.csv` — join-integrity evidence
- `reports/datathon_rubric_audit.md` — self-audit against the 4 gates
- `reports/demo_script.md`, `reports/presentation_outline.md`
- `src/`, `dashboard/`, `agent/`, `tests/`, `scripts/` — full tested source code
- `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `Procfile`, `runtime.txt`, `.streamlit/config.toml`

## Files that must NOT be uploaded to a public GitHub repo as-is
- Nothing sensitive is currently present (no `.env`, no raw PII beyond what's in the
  provided dataset itself, settlement accounts/Aadhaar already masked in the cleaned
  output). If the raw dataset files under `data/raw/` are considered sensitive/competition-
  confidential, exclude them via `.gitignore` and instead document in the README how judges
  should obtain and place the dataset before running `scripts/run_all.py`.

## Immediate next steps for the human submitter
1. Review `reports/DATA_AUDIT.md` Open Questions #1–#3 and be ready to explain them.
2. `git init`, commit, push to a public GitHub repo.
3. Deploy (Streamlit Community Cloud recommended — simplest for a student datathon) and
   confirm the live URL loads before the submission deadline.
4. Skim `README.md` and adjust the AI-assistance disclosure wording if your team wants to
   describe the human/AI division of labor differently — keep it accurate either way.
