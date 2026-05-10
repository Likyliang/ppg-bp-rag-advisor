# Iteration Log

## Baseline: v0.2.0-kb-governance-baseline

- Date: 2026-05-10
- Branch: main
- Tests: `30 passed`
- Knowledge base: 35 included sources, 140 chunks
- Retrieval evaluation: match_rate 1.0, mean_precision_at_5 0.887, unsafe_source_leakage_count 0
- Audit: all expected topics covered; no orphan sources; no duplicate source hashes; no unsafe-source leakage
- Risk: no Git history existed before this baseline; long-run quality gate and stop-criteria enforcement still need to be added

## Iteration 02: Quality Gate

- Goal: add one-command verification for tests, source screening, note generation, ingest, audit, retrieval evaluation, and report evaluation.
- Expected artifact: `knowledge_base/processed/quality_gate_report.json`.
- Stop criteria are intentionally stricter than the current baseline so the report can show remaining gaps during the 20-round run.

## Iterations 03-09: Knowledge Base Expansion and Audit

- Added supplemental source catalog loading.
- Expanded governed sources from 35 to 63 included sources.
- Expanded governed chunks from 140 to 252.
- Topic coverage now has at least 3 source-level notes in every expected topic.
- Audit remains clean: no orphan sources, no duplicate source hashes, no unsafe-source leakage.

## Iterations 10-14: Retrieval, Rerank, Citation Quality, Report Safety

- Rule engine now emits `retrieval_allowed_uses` so retrieval is driven by rule outcome, not only query text.
- Retriever now caches chunks, filters by allowed use and evidence class, and reranks by source quality, use overlap, trust class, and region.
- Reports now include citation quality and a small-program-friendly UI summary.
- Report references now show source id and evidence class for traceability.

## Iterations 15-16: Evaluation Set Expansion and Experiment Outputs

- Golden retrieval queries expanded from 30 to 100.
- Demo/report fixtures expanded from 10 to 50.
- Test suite expanded from 30 tests to 101 tests.
- Strict quality gate now passes all stop criteria.

## Iterations 17-19: API, Demo, Performance and Reliability

- Added OpenAPI request examples for report generation and rule preview.
- Exported retrieval and report evaluations as JSON and CSV for thesis tables.
- Added report generation benchmark with P95 threshold under 3 seconds.
- Streamlit demo now supports fixture selection and Markdown/JSON report downloads.
- Strict quality gate passes with report P95 under 0.02 seconds on local fixtures.

