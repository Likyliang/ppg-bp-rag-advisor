# Changelog

## v0.2.0-kb-governance-baseline - 2026-05-10

- Established FastAPI + Streamlit MVP for PPG blood pressure estimate explanations.
- Added governed knowledge base with source catalog, screening, generated notes, ingest, audit, retrieval evaluation, and report evaluation.
- Baseline metrics: 30 tests passing, 35 included sources, 140 chunks, retrieval match rate 1.0, mean precision@5 0.887, unsafe source leakage 0.

## Unreleased

- Added a full quality-gate runner that regenerates knowledge artifacts, runs evaluations and tests, and writes a stop-criteria report.
- Expanded the governed knowledge base to 63 included sources and 252 chunks through a supplemental source catalog.
- Upgraded retrieval with rule-derived allowed uses, lightweight reranking, chunk caching, citation quality checks, and UI summary fields.
- Expanded retrieval and report evaluation datasets to 100 golden queries and 50 fixtures; expanded tests to 101.
- Added evaluation CSV exports, report benchmark, OpenAPI examples, and Streamlit fixture/report download support.
