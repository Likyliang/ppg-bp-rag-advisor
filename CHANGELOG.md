# Changelog

## v0.2.0-kb-governance-baseline - 2026-05-10

- Established FastAPI + Streamlit MVP for PPG blood pressure estimate explanations.
- Added governed knowledge base with source catalog, screening, generated notes, ingest, audit, retrieval evaluation, and report evaluation.
- Baseline metrics: 30 tests passing, 35 included sources, 140 chunks, retrieval match rate 1.0, mean precision@5 0.887, unsafe source leakage 0.

## Unreleased

- Added a full quality-gate runner that regenerates knowledge artifacts, runs evaluations and tests, and writes a stop-criteria report.
- Expanded the governed knowledge base to 63 included sources and 252 chunks through a supplemental source catalog.
- Upgraded retrieval with rule-derived allowed uses, lightweight reranking, chunk caching, citation quality checks, and UI summary fields.
- Expanded retrieval and report evaluation datasets to 100 golden queries and 50 fixtures; expanded tests to 105.
- Added evaluation CSV exports, report benchmark, OpenAPI examples, and Streamlit fixture/report download support.
- Prepared `v1.0.0-rc1` release candidate after strict quality gate and API smoke checks passed.
- Added full-text candidate governance with a safe public-download path, institution/browser queue, tracked Chinese summary notes, and quality-gate validation; current KB is 63 included sources and 255 chunks.
- Promoted institution/browser-assisted full-text summaries for the AHA cuffless BP statement, Chinese 2024 hypertension guideline, and AHA/ACC 2025 full guideline; current KB is 63 included sources and 261 chunks.

## v1.0.0-rc1 - 2026-05-10

- Meets current stop criteria for local usability.
- Quality gate: 101 tests, 63 included sources, 252 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
- FastAPI health and report generation smoke checks pass.

## v1.0.0-rc3-fulltext-access - 2026-05-10

- Downloaded and validated three legal browser-session PDFs into ignored local storage: AHA cuffless BP scientific statement, Chinese hypertension guideline 2024 revision, and AHA/ACC 2025 full guideline.
- Added tracked Chinese summary notes and citation/access records only; no PDF full text, credentials, cookies, or tokens are committed.
- Recorded ESC 2024 official PDF as access blocked by Cloudflare and ESH 2023 LWW full text as awaiting user human verification.
- Strict quality gate passes: 105 tests, 63 included sources, 261 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0144s.
