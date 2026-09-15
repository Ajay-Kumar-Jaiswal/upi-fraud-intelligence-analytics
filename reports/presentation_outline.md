# Presentation Content Outline
For a 12-slide deck. Content only (not designed slides) — pull numbers from
`reports/analytics_validation.md` at presentation time in case the pipeline is re-run and
numbers shift slightly with new data.

1. **Title** — UPI Fraud Ring & Merchant Analytics | TransOrg AgentIQ Datathon, Track 1
2. **Business Problem** — messy micro-transaction data, 3 fraud patterns to find, 1 bonus question
3. **Dataset & Data Quality** — 4 files, ~66K rows, headline data-quality issues found (see `reports/DATA_AUDIT.md` §3)
4. **Data Rescue Pipeline** — cleaning approach, before/after retention table (`reports/DATA_QUALITY_EVIDENCE.md` §1)
5. **Analytics/Data Model** — fact/dim structure, KPI list, the identity-join finding and how it's handled (Open Question #1)
6. **Fraud Risk Methodology** — explainable rule engine, thresholds, risk-level bands, example flagged merchant with reasons
7. **Key Business Insights** — chargeback ratio 13.04%, bonus-question answer + margin caveat, category performance ranking
8. **Dashboard** — 8-page walkthrough screenshots (Executive Overview, Merchant Intelligence, Data Quality & Coverage)
9. **Fraud Network Analysis** — graph structure, sparse-graph finding, why no cycle detection was fabricated
10. **AI Graph Agent** — architecture (deterministic router → query engine → optional LLM polish), 12 supported intents, live example
11. **Architecture** — end-to-end diagram (raw → cleaning → analytics/fraud/graph → dashboard/agent), tech stack, test coverage (121 tests)
12. **Business Impact & Conclusion** — what's reliable vs not in this dataset, recommended next steps (see README §18), closing ask
