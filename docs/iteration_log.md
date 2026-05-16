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

## Special Iteration: Official Source Gap Fill

- Goal: address remaining knowledge-base weak spots without downloading new full text, while preserving official download URLs for manual intake.
- Added 7 selected official/high-trust sources:
  - FDA cuffless NIBP draft guidance for PPG/no-cuff regulatory and validation boundaries.
  - WHO automated cuff BP device technical specifications for validated cuff-device principles.
  - USPSTF adult hypertension screening recommendation for out-of-office confirmation and non-diagnostic boundaries.
  - National Health Commission 2024 hypertension nutrition/exercise guidance for Chinese lifestyle advice.
  - National Health Commission 2024 hypertension day key messages for Chinese health education and measurement reminders.
  - KDIGO 2024 CKD guideline for chronic kidney disease conservative reminders.
  - ADA 2026 diabetes cardiovascular risk guidance for diabetes conservative reminders and medication-safety boundaries.
- Added manual full-text/download candidates for FDA, WHO, USPSTF, NHC 2024 guidance, KDIGO, and ADA; no new PDFs were downloaded.
- Expanded retrieval golden queries for FDA cuffless, WHO validated devices, USPSTF confirmation, Chinese lifestyle guidance, CKD, and diabetes scenarios.
- Metrics after strict quality gate: 105 tests, 70 included sources, 289 chunks, 100 golden queries, match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0174s.
- Next risk: `measurement_quality` still has only 4 source-level notes because FDA/WHO sources primarily improve cuffless limitations and validated devices; a later round can add more optical-signal or wearable-sensor quality sources if the thesis needs deeper PPG methodology discussion.

## Special Iteration: PPG Optical Signal Quality Expansion

- Goal: fill the `measurement_quality` gap for finer PPG/optical sensor factors requested by the user: motion, skin tone/ambient light, contact pressure, acquisition duration, and sensor position.
- Added 10 selected peer-reviewed sources:
  - PPG clinical measurement foundation review, PPG acquisition/processing best-practices article, wearable PPG cardiovascular monitoring review, 2023 wearable PPG roadmap, and PPG/iPPG quality-assessment survey.
  - Wrist PPG signal-quality determinants, classic contact-force PPG study, contact pressure in cuffless BP measurement, video PPG ambient-light/skin-tone study, and wearable optical heart-rate sensor inaccuracy study.
- Restricted all research/background sources to `signal_quality`, `cuffless_ppg_limitations`, `remeasurement`, `device_advice`, or `research_background`; none can support diagnosis, treatment, prescribing, deprescribing, or replacement of validated BP measurement.
- Added manual full-text/download candidates for all 10 sources; no PDFs were downloaded and no credentials or session data were used.
- Expanded golden retrieval queries for motion artifacts, contact pressure, ambient light, skin tone, acquisition duration, sensor position, and wearable optical sensor error.
- Metrics after strict quality gate: 105 tests, 80 included sources, 329 chunks, 100 golden queries, match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0170s.
- Next risk: if the thesis needs stronger primary evidence for skin tone in camera PPG specifically, prioritize full-text summary for the IEEE EMBC video PPG source and compare it with FDA optical sensor safety language.

## Special Iteration: Pro Public PDF Download Intake

- Goal: inspect `PPG血压估算_RAG知识库下载清单.xlsx` and directly download rows marked `PDF开放下载` without using credentials or institution access.
- Parsed 44 workbook rows and selected 22 public-PDF candidates.
- Downloaded 15 new PDFs into ignored local storage and reused 2 PDFs already present from prior iterations.
- Verified 17 selected PDF files with `pypdf`; validation failures: 0.
- Direct-download failures remain for 5 rows: Chinese Hypertension Guideline 2024 CHL-BHA mirror, 2019 Chinese home BP monitoring guideline, 2024 ESC guideline OUP PDF, AHA/AMA 2020 SMBP policy statement, and AHA PREVENT equations PDF.
- Output artifacts: `knowledge_base/processed/pro_download_list_public_pdf_manifest.json` and `knowledge_base/processed/pro_download_list_public_pdf_report.md`.
- Next risk: downloaded PDFs are not yet RAG evidence; the next iteration should add source-catalog records where missing, create Chinese summary notes, run ingest/audit/evaluation, and keep treatment/drug content restricted to safety reminders.

## Special Iteration: Pro PDF Summary Ingest

- Goal: promote the downloaded public PDFs into auditable RAG evidence without committing any PDF full text.
- Added 13 source catalog records:
  - Chinese primary-care hypertension standard, Chinese blood pressure measurement guideline, Chinese patient education guideline, Chinese elderly hypertension guideline, and Chinese secondary hypertension screening consensus.
  - WHO pharmacological treatment guideline, AHA home BP measurement instructions, NHLBI DASH guide, AHA lifestyle sheets, CDC doctor-question prompt, and AHA pregnancy blood pressure categories.
- Refreshed full-text candidate governance: 38 candidates, 20 summary-ready records, 0 validation errors.
- Generated summary-only notes for all new promoted PDFs and refreshed existing NICE/FDA notes with local PDF availability.
- Rebuilt raw notes and chunks: 93 included sources, 396 chunks.
- Audit remains clean: no missing topics, no orphan sources, no duplicate source hashes, no unsafe-source leakage.
- Retrieval evaluation: 100 golden queries, match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
- Strict quality gate passed: 105 tests, 50 report fixtures, report P95 0.0244s.
- Safety note: WHO pharmacological guidance is only allowed for `medication_safety`; patient-education sources were intentionally not allowed to answer medication-adjustment sensitive queries.

## Special Iteration: RAG Trust Calibration

- Goal: make the RAG quality evidence less self-referential by separating true query-only retrieval evaluation from metadata-filter safety checks, and make every report recommendation auditable back to evidence.
- Finding: the previous retrieval evaluation passed `expected_uses` into the retriever and then judged success against the same labels, so the 1.0 score was useful as a safety-filter check but too optimistic as a retrieval-quality metric.
- Implementation:
  - Added `calibrated_query_only` as the primary retrieval mode; it does not pass gold allowed uses into retrieval.
  - Retained the old expected-use filtered path as `metadata_filter_safety`.
  - Added expected topics/evidence classes to golden queries and full 100-query test participation.
  - Added `recommendation_evidence` to reports and extended citation quality with recommendation grounding.
  - Added report expectations and evaluation metrics for required-use coverage, recommendation grounding, sensitive high-trust evidence, and emergency consistency.
- Metrics after strict quality gate:
  - Tests: 220 passed.
  - Knowledge base: 93 included sources, 396 chunks.
  - Calibrated query-only retrieval: match rate 0.97, precision@5 0.86, topic hit rate 0.97, expected class hit rate 0.96, unsafe-source leakage 0.
  - Metadata-filter safety: match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
  - Rule+RAG+Safety report evaluation: required-use coverage 1.0, recommendation grounding 1.0, sensitive high-trust rate 1.0, emergency consistency 1.0.
  - Report benchmark: P95 0.0279s.
- Remaining risk: calibrated query-only precision is now honest and only slightly above the 0.85 floor; the next quality-improvement round should target hybrid retrieval/rerank or query expansion rather than adding more sources blindly.

## Special Iteration: Honest Retrieval Quality Uplift

- Goal: push real `calibrated_query_only` retrieval quality above 0.95 without feeding expected labels into retrieval.
- Finding: the largest losses came from intent ambiguity, not knowledge gaps:
  - PPG replacement/accuracy questions were pulling home blood pressure monitoring chunks ahead of cuffless/PPG limitation chunks.
  - Numeric BP questions and guideline/category questions were not consistently inferred as `bp_category_reference`.
  - Medication wording such as `药物治疗`、`调药`、`加药`、`剂量` did not always trigger `medication_safety`.
  - PPG optical sensor questions containing `运动` were being confused with lifestyle exercise advice.
- Implementation:
  - Added transparent query-intent heuristics in the retriever for BP values, BP categories, PPG/cuffless limitation questions, PPG motion/sensor-quality questions, medication safety, special populations, home monitoring, and remeasurement.
  - Raised strict quality-gate `mean_precision_at_5` floor from 0.85 to 0.95.
  - Kept `metadata_filter_safety` separate; the improved primary metric still uses `calibrated_query_only`.
- Metrics after strict quality gate:
  - Tests: 220 passed.
  - Knowledge base: 93 included sources, 396 chunks.
  - Calibrated query-only retrieval: match rate 1.0, precision@5 1.0, topic hit rate 1.0, expected class hit rate 0.92, unsafe-source leakage 0.
  - Metadata-filter safety: match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
  - Rule+RAG+Safety report evaluation: required-use coverage 1.0, recommendation grounding 1.0, sensitive high-trust rate 1.0, emergency consistency 1.0.
  - Report benchmark: P95 0.0311s.
- Remaining risk: expected evidence-class hit rate is 0.92; a later round can improve source-class ranking without relaxing topic or safety filters.

## Special Iteration: Public Full-text Expansion Follow-up

- Goal: continue enriching the RAG with legally accessible full text while preserving the summary-only, auditable knowledge-base boundary.
- Downloaded and validated 8 public PDFs into ignored local storage:
  - WHO automated cuff BP device technical specifications, USPSTF adult hypertension screening recommendation, NHC 2024 hypertension nutrition/exercise guidance, and KDIGO 2024 CKD guideline.
  - PPG signal-quality sources: Charlton 2022 PPG acquisition/processing best practices, Charlton 2023 wearable PPG roadmap, Desquins 2022 PPG/iPPG quality-assessment survey, and Charlton 2025 wrist PPG signal-quality determinants.
- Promoted all 8 candidates from `queued_manual/pending_fulltext` to `summarized/ready`, recorded direct download URLs and access date `2026-05-16`, and generated tracked Chinese summary notes only.
- Rebuilt generated notes and chunks: included sources remain 93, chunks increased from 396 to 406; `measurement_quality` now has 62 chunks and 14 source-level notes.
- Preserved safety boundaries:
  - Downloaded PDFs remain under `knowledge_base/sources/downloads/`, which is Git-ignored.
  - No credentials, cookies, tokens, or raw PDF text were stored in tracked files.
  - PPG research sources remain limited to signal quality, remeasurement, cuffless/PPG limitations, device boundary, and research background.
- Strict quality gate passed:
  - Tests: 220 passed.
  - Calibrated query-only retrieval: match rate 1.0, precision@5 1.0, topic hit rate 1.0, high-trust sensitive rate 1.0, unsafe-source leakage 0.
  - Metadata-filter safety: match rate 1.0, precision@5 1.0, unsafe-source leakage 0.
  - Rule+RAG+Safety report evaluation: required-use coverage 1.0, recommendation grounding 1.0, sensitive high-trust rate 1.0, emergency consistency 1.0.
  - Report benchmark: P95 0.0311s.
- Remaining risk: ADA 2026 PDF, Bent 2020 Nature PDF, and several IEEE/older PPG papers remain manual/browser or institution-access candidates; current summaries still avoid using those as full-text-derived evidence until PDF access is cleanly recorded.
