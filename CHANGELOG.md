# Changelog

## v0.2.0-kb-governance-baseline - 2026-05-10

- Established FastAPI + Streamlit MVP for PPG blood pressure estimate explanations.
- Added governed knowledge base with source catalog, screening, generated notes, ingest, audit, retrieval evaluation, and report evaluation.
- Baseline metrics: 30 tests passing, 35 included sources, 140 chunks, retrieval match rate 1.0, mean precision@5 0.887, unsafe source leakage 0.

## Unreleased

- (2026-06-10) Made OpenAI embeddings the preferred retrieval vector backend (`retrieval.embedding_backend: auto`): with `OPENAI_EMBEDDING_API_KEY` set and the index built via `scripts/ingest_openai_embeddings.py`, report and advisor retrieval score against `text-embedding-3-small` vectors (cached query embeddings, 5-minute failure backoff); stale indexes are skipped by both id-coverage and chunks-vs-index mtime checks; without a key the offline hashing index serves, and keyword-only remains the final fallback.
- (2026-06-10) Upgraded the system from a one-shot structured-input report into a post-measurement advisor application: new `POST /api/v1/advisor/sessions`, `POST /api/v1/advisor/sessions/{id}/messages`, `GET /api/v1/advisor/sessions/{id}` endpoints, session/profile models, and a Streamlit「随访对话」chat tab.
- (2026-06-10) Added a staged, non-offensive intake question bank (`config/advisor_questions.yaml`): every question explains why it is asked and is skippable; sensitivity rises stage by stage (measurement context -> recheck conditions -> lifestyle -> history/medication -> goals); emergency sessions suppress all questions and lead with the 120/ER banner; each newly volunteered fact maps to a tailored, evidence-cited follow-up suggestion via field-targeted retrieval.
- (2026-06-10) Advisor replies are LLM-written when `LLM_PROVIDER` is configured (compact safety prompt, numbered evidence) and fall back to curated template copy otherwise; both paths share the citation registry, the medical-copy sanitizer, and the forbidden-pattern safety review.
- (2026-06-10) Rebuilt knowledge-base chunking (`app/services/chunking.py`): markdown-structure-aware parsing, zh/en sentence-boundary-safe splitting with sentence-level overlap, substantive sections merged per source, and `section_role: governance` tagging for per-source boilerplate (kept for audit, excluded from report retrieval). Old store: 629 chunks with 486 under 100 chars; new store: 342 chunks (206 content chunks, median ~500 chars, zero sub-100 fragments).
- (2026-06-10) Upgraded retrieval to hybrid scoring: shared zh-bigram/en-word tokenizer, keyword cosine fused with an offline hashing-vector index built at ingest (`processed_hashing_vectors.npz`), per-source diversification caps, and optional merge of locally ingested PDF passages into report evidence (`retrieval.include_fulltext: auto`) — automatically skipped for sensitive (emergency/medication/special-population) requests, which also enforce high-trust-only sources.
- (2026-06-10) Made citations academic: source-level dedup (one number per source), inline `[n]` renumbered by first appearance with uncited references pruned, page locators for fulltext passages (`DOI: … (p.7)`), structured `references` entries on reports and advisor replies, sentence-level citation prompts, and citation injection placed before sentence-ending punctuation.
- Refined the Canva weekly presentation again to enlarge fonts while restoring the key workload and governance narrative: literature counts, included sources, chunks, source catalog workflow, question-set design, fixtures, tests, and API metrics.
- Enriched the Canva weekly presentation with testing-system details, including structured input examples, golden query and fixture construction, non-circular retrieval-evaluation snippets, API metrics, and the max-concurrency cap.
- Revised the Canva weekly presentation into a content-rich version after review, adding the mini-program input boundary, literature/chunk counts, source catalog workflow, evaluation metrics, API experiment details, and concurrency limit.
- Created a 5-page Canva weekly presentation deck for the high-blood-pressure PPG RAG-Agent progress update and recorded the editable/viewable links under `outputs/weekly_reports/`.
- Reworked the practical weekly report into a neutral presentation-ready version while keeping the literature workload, source catalog workflow, evaluation results, concurrency limit, and next-week report/Demo scope explicit.
- Added an exploratory API-level experiment runner that exercises existing FastAPI routes for rule preview, report generation, and KB search with capped concurrency; outputs JSON/CSV/Markdown under `outputs/experiments/` without replacing the calibrated retrieval quality gate.
- Clarified the weekly-report application boundary as mini-program structured PPG-estimate input rather than open-ended clinical questioning, preserved PPG signal context in report `input_summary`, and added capped parallel experiment execution with `evaluation.max_concurrency=5` for report evaluation and benchmarking.
- Processed Batch 3 user-downloaded PDFs into the governed RAG workflow: 11 newly archived PDFs, 11 source catalog records, 11 full-text summary notes, refreshed chunks/evaluations, and a current unresolved-download list with 6 remaining access-blocked/institution-required items.
- Refreshed the Obsidian literature library after Batch 3: 62 PDF links, 48 sources with summary notes, 14 PDF-archived but summary-pending notes, and 6 unresolved full-text/access items.
- Current strict quality gate after Batch 3, input-boundary/concurrency update, and exploratory API experiment: 224 tests, 114 included sources, 524 chunks, calibrated query-only match rate 1.0, precision@5 1.0, topic hit rate 1.0, unsafe-source leakage 0, Rule+RAG+Safety recommendation grounding 1.0, report evaluation max concurrency 5, benchmark max concurrency 5, report P95 0.212s.
- Prepared Batch 3 legal full-text search request focused on non-duplicative cuffless BP validation/calibration and PPG optical signal-quality gaps, while excluding all locally archived Batch 1/2 PDFs and the current unresolved retry list.
- Cleaned the Obsidian literature graph: PDFs now use external file links instead of wiki-links, noisy topic tags were removed, 10 topic hub notes were generated, and the graph structure is now `MOC -> Topic Hub -> Literature Note`.
- Ingested Batch 2 user-downloaded PDFs into the governed RAG workflow: 10 newly archived PDFs, 10 source catalog records, 10 full-text summary notes, refreshed chunks/evaluations, and a current unresolved-download list with 3 remaining access-blocked items.
- Refreshed the Obsidian literature library after Batch 2: 51 PDF links, 37 sources with summary notes, 14 PDF-archived but summary-pending notes, and 3 unresolved full-text/access items.
- Added an Obsidian literature maintenance workflow with `scripts/sync_obsidian_literature.py`, creating a project literature library in the local Obsidian Vault with PDF symlinks, per-source notes, a master index, unresolved-download tracking, and a machine-readable sync manifest; no PDF full text is committed.
- Promoted 8 newly downloaded public full-text PDFs into summary-only governed notes: WHO cuffed BP device specifications, USPSTF hypertension screening, NHC 2024 nutrition/exercise guidance, KDIGO 2024 CKD guideline, and four PPG signal-quality sources from IOP, MDPI, and PLOS; no PDF full text was committed.
- Current strict quality gate after public full-text expansion: 220 tests, 93 included sources, 406 chunks, calibrated query-only match rate 1.0, precision@5 1.0, unsafe-source leakage 0, Rule+RAG+Safety recommendation grounding 1.0.
- Calibrated RAG trust evaluation by separating query-only retrieval quality from metadata-filter safety checks; strict gate now uses `calibrated_query_only` as the primary retrieval metric.
- Added recommendation-level evidence binding to reports with per-advice required uses, evidence ids, sensitive high-trust checks, and grounding-rate citation quality.
- Expanded report evaluation with explicit case expectations, required-use coverage, recommendation grounding, sensitive high-trust evidence, and emergency consistency metrics.
- Added `knowledge_base/processed/rag_trust_calibration_report.json` as a machine-readable audit summary for this calibration iteration.
- Improved honest query-only retrieval quality with a transparent intent planner for PPG/cuffless limitations, optical signal quality, BP categories, medication safety, special populations, home monitoring, and lifestyle queries.
- Current strict quality gate: 220 tests, 93 included sources, 396 chunks, calibrated query-only match rate 1.0, precision@5 1.0, topic hit rate 1.0, unsafe-source leakage 0, Rule+RAG+Safety recommendation grounding 1.0.
- Added a full quality-gate runner that regenerates knowledge artifacts, runs evaluations and tests, and writes a stop-criteria report.
- Expanded the governed knowledge base to 63 included sources and 252 chunks through a supplemental source catalog.
- Upgraded retrieval with rule-derived allowed uses, lightweight reranking, chunk caching, citation quality checks, and UI summary fields.
- Expanded retrieval and report evaluation datasets to 100 golden queries and 50 fixtures; expanded tests to 105.
- Added evaluation CSV exports, report benchmark, OpenAPI examples, and Streamlit fixture/report download support.
- Prepared `v1.0.0-rc1` release candidate after strict quality gate and API smoke checks passed.
- Added full-text candidate governance with a safe public-download path, institution/browser queue, tracked Chinese summary notes, and quality-gate validation; current KB is 63 included sources and 255 chunks.
- Promoted institution/browser-assisted full-text summaries for the AHA cuffless BP statement, Chinese 2024 hypertension guideline, and AHA/ACC 2025 full guideline; current KB is 63 included sources and 261 chunks.
- Added a targeted official-source expansion with FDA cuffless NIBP draft guidance, WHO cuffed BP device specifications, USPSTF screening, Chinese NHC lifestyle guidance, KDIGO 2024 CKD, and ADA 2026 diabetes standards; current KB is 70 included sources and 289 chunks.
- Added detailed PPG/optical signal-quality evidence for motion, skin tone/ambient light, contact pressure, acquisition duration, and sensor position; current KB is 80 included sources and 329 chunks.
- Processed the Pro workbook download list and downloaded/validated 15 additional public PDFs into ignored local storage, with 2 existing PDFs reused and 5 direct-download failures recorded for manual/browser handling.
- Promoted the downloaded public PDFs into governed source catalog records and summary-only full-text notes; current KB is 93 included sources and 396 chunks.

## v1.0.0-rc6-pro-pdf-summary-ingest - 2026-05-11

- Added 13 governed source records from the Pro PDF intake, including Chinese primary-care/measurement/patient-education/elderly/secondary-hypertension materials, WHO pharmacological treatment guidance, AHA home BP/pregnancy/lifestyle sheets, CDC doctor-question prompts, and NHLBI DASH guidance.
- Generated 14 new summary-only full-text notes and refreshed existing NICE/FDA full-text notes; no PDF full text was committed.
- Expanded golden retrieval coverage for Chinese primary care, Chinese measurement guidance, elderly users, WHO medication safety, pregnancy emergency categories, DASH lifestyle, and AHA home BP instructions.
- Strict quality gate passes: 105 tests, 93 included sources, 396 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0244s.

## v1.0.0-rc1 - 2026-05-10

- Meets current stop criteria for local usability.
- Quality gate: 101 tests, 63 included sources, 252 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
- FastAPI health and report generation smoke checks pass.

## v1.0.0-rc3-fulltext-access - 2026-05-10

- Downloaded and validated three legal browser-session PDFs into ignored local storage: AHA cuffless BP scientific statement, Chinese hypertension guideline 2024 revision, and AHA/ACC 2025 full guideline.
- Added tracked Chinese summary notes and citation/access records only; no PDF full text, credentials, cookies, or tokens are committed.
- Recorded ESC 2024 official PDF as access blocked by Cloudflare and ESH 2023 LWW full text as awaiting user human verification.
- Strict quality gate passes: 105 tests, 63 included sources, 261 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0144s.

## v1.0.0-rc4-official-source-expansion - 2026-05-10

- Added 7 selected official/high-trust sources for weak spots: FDA cuffless NIBP draft guidance, WHO cuffed BP device specifications, USPSTF hypertension screening, Chinese NHC 2024 hypertension nutrition/exercise guidance, NHC hypertension day key messages, KDIGO 2024 CKD guideline, and ADA 2026 diabetes cardiovascular risk guidance.
- Added manual download/full-text candidate URLs for FDA, WHO, USPSTF, NHC 2024 guidance, KDIGO 2024, and ADA 2026; no PDFs were downloaded in this iteration.
- Expanded golden retrieval coverage for FDA cuffless, WHO validated devices, USPSTF out-of-office confirmation, Chinese lifestyle guidance, CKD, and diabetes scenarios.
- Strict quality gate passes: 105 tests, 70 included sources, 289 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0174s.

## v1.0.0-rc5-ppg-signal-quality - 2026-05-10

- Added 10 selected PPG/optical signal-quality sources covering PPG acquisition best practices, wearable PPG cardiovascular monitoring, quality assessment, wrist sensor position, contact force/contact pressure, ambient light, skin tone, and motion/activity effects.
- Added manual full-text/download URLs for those sources; no new PDFs were downloaded in this iteration.
- Expanded golden retrieval coverage for motion artifacts, contact pressure, ambient light, skin tone, acquisition duration, sensor position, and wearable optical sensor error scenarios.
- Strict quality gate passes: 105 tests, 80 included sources, 329 chunks, 100 golden queries, 50 report fixtures, retrieval match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0170s.
