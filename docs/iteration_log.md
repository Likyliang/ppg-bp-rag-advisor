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

## Iteration 20: Release Candidate

- Fixed citation coverage for ordinary elevated reports by supplementing retrieval results for missing allowed uses.
- Verified FastAPI health and report generation endpoint manually.
- Final strict quality gate passes all stop criteria.
- Release candidate tag target: `v1.0.0-rc1`.

## Special Iteration: Full-text Candidate Intake

- Goal: create a repeatable workflow for full-text candidate selection, institution/browser download, and summary-only knowledge-base intake.
- Added `knowledge_base/sources/fulltext_candidates.yaml` with 9 prioritized candidates, including AHA cuffless BP statement, Chinese 2024 hypertension guideline, AHA/ACC 2025, ESC 2024, NICE NG136, ISH 2020, ESH 2023, STRIDE BP, and ISO 81060-2.
- Added scripts for candidate validation, public PDF download, tracked summary generation, and queue reporting.
- Downloaded the public ISH 2020 guideline PDF into ignored local storage; generated tracked Chinese summaries for NICE NG136, ISH 2020, and STRIDE BP.
- Institution-required candidates remain queued; no credentials, cookies, tokens, or browser sessions are saved.
- Strict quality gate passes after summary ingest: 105 tests, 63 included sources, 255 chunks, 100 golden queries, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
- Next risk: AHA Journals, SciOpen, ESC, and ESH may require browser or institution access; after legal download, manually read and promote summaries by changing `include_in_summary` and `summary_status`.

## Special Iteration: Institution/Browser Full-text Access

- Goal: use the user's current browser session for legal full-text access, then commit only citation records and Chinese summary notes.
- Downloaded valid PDFs into ignored local storage:
  - `aha_cuffless_bp_scientific_statement.pdf`
  - `chinese_hypertension_guideline_2024_catalog.pdf`
  - `acc_aha_2025_full_guideline_record.pdf`
- Promoted those three candidates to `summary_status: ready` and generated tracked summaries under `knowledge_base/sources/fulltext_summaries/`.
- Updated source metadata for AHA cuffless DOI `10.1161/HYP.0000000000000254` and AHA/ACC 2025 DOI `10.1161/CIR.0000000000001356`.
- ESC 2024 official PDF access attempt was blocked by Cloudflare; no non-official mirror was used.
- ESH 2023 LWW full-text access reached Cloudflare human verification and remains `awaiting_human_verification`.
- Strict quality gate passed: 105 tests, 63 included sources, 261 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0144s.
- Next risk: if the user completes ESH/LWW human verification or institution login later, add a summary-only intake for that PDF and rerun the strict quality gate.
