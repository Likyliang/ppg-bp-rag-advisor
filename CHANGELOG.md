# Changelog

## v0.2.0-kb-governance-baseline - 2026-05-10

- Established FastAPI + Streamlit MVP for PPG blood pressure estimate explanations.
- Added governed knowledge base with source catalog, screening, generated notes, ingest, audit, retrieval evaluation, and report evaluation.
- Baseline metrics: 30 tests passing, 35 included sources, 140 chunks, retrieval match rate 1.0, mean precision@5 0.887, unsafe source leakage 0.

## Unreleased

- Calibrated RAG trust evaluation by separating query-only retrieval quality from metadata-filter safety checks; strict gate now uses `calibrated_query_only` as the primary retrieval metric.
- Added recommendation-level evidence binding to reports with per-advice required uses, evidence ids, sensitive high-trust checks, and grounding-rate citation quality.
- Expanded report evaluation with explicit case expectations, required-use coverage, recommendation grounding, sensitive high-trust evidence, and emergency consistency metrics.
- Added `knowledge_base/processed/rag_trust_calibration_report.json` as a machine-readable audit summary for this calibration iteration.
- Current strict quality gate: 220 tests, 93 included sources, 396 chunks, calibrated query-only match rate 0.97, precision@5 0.86, topic hit rate 0.97, unsafe-source leakage 0, Rule+RAG+Safety recommendation grounding 1.0.
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
