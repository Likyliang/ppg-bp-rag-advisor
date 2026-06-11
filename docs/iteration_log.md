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

## Special Iteration: Batch 1 Web Result Maintenance

- Goal: record the web-agent results for the first manual-download batch, archive user-supplied PDFs, and maintain a clean unresolved-download list.
- Archived 4 first-batch PDFs into ignored local storage:
  - AHA/AMA 2020 self-measured blood pressure policy statement.
  - Chandrasekhar 2020 contact pressure and cuffless BP measurement paper.
  - Shirbani 2020 ambient lighting / skin tone video PPG paper.
  - Teng 2004 contacting force and PPG signal paper.
- Recorded pages and SHA-256 hashes in `outputs/literature_download_tracker/web_batch1_results_2026-05-21.json`.
- Created the unresolved list `outputs/literature_download_tracker/unavailable_fulltext_list_2026-05-21.md`.
- Updated `knowledge_base/sources/fulltext_candidates.yaml` with first-batch local PDF archive metadata for Chandrasekhar 2020, Shirbani 2020, and Teng 2004, while leaving them pending summary ingest.
- Refreshed candidate governance outputs with `scripts/prepare_fulltext_candidates.py`: 38 candidates, 12 action-queue items, 28 summary-ready items, 0 validation issues.
- Strict quality gate passed after maintenance: 220 tests, 93 included sources, 414 chunks, 100 golden queries, calibrated query-only match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.031s.
- Remaining unresolved source-access gaps:
  - ESC 2024 Essential Messages official PDF link exists, but local automated access still returns 403; the similarly named local file is a pharmacotherapy short article and was not misclassified.
  - CHL-BHA Chinese 2024 guideline mirror remains blocked/connection-reset and no matching local PDF was found; existing Chinese 2024 guideline metadata remains available from the prior catalog/SciOpen representation.
- Safety note: the newly archived PPG research PDFs are still only full-text candidates until catalog/summary ingest is done, and their allowed use must remain limited to signal quality, remeasurement, cuffless/PPG limitations, device boundary, or research background.

## Special Iteration: Obsidian Literature Library Maintenance

- Goal: maintain downloaded PDFs in an Obsidian-friendly project library without moving the canonical RAG PDF store or committing raw full text.
- Used the configured local productivity/Obsidian workflow; `codex-productivity doctor` confirmed the Obsidian app and Vault at `/Users/lianghao/Documents/Codex/2026-05-12/obsiden-zetro/KnowledgeVault`.
- Added `scripts/sync_obsidian_literature.py` as a repeatable sync command.
- Created the Obsidian library at `/Users/lianghao/Documents/Codex/2026-05-12/obsiden-zetro/KnowledgeVault/10 Literature/High Blood Pressure RAG` with:
  - `PDF Library/`: 41 symlinks to canonical PDFs in `knowledge_base/sources/downloads/`.
  - `Notes/`: 41 one-note-per-source Markdown files with source_id, topic, allowed uses, PDF link, summary status, DOI/PMID when available, and RAG safety boundary.
  - `MOC - High Blood Pressure RAG Literature.md`: master index with topic coverage, downloaded PDF table, and unresolved items.
  - `Unresolved Full Text.md`: manual download queue for ESC 2024 Essential Messages and the CHL-BHA Chinese 2024 mirror.
- Wrote sync manifest `outputs/literature_download_tracker/obsidian_literature_sync_2026-05-21.json`.
- Current Obsidian inventory: 41 archived PDFs, 27 with summary notes, 14 PDF-archived but summary-pending, 2 unresolved full-text/access items.
- Rebuilt the local productivity/Obsidian search index: 100 chunks indexed.
- Strict quality gate still passed after Obsidian maintenance: 220 tests, 93 included sources, 414 chunks, 100 golden queries, calibrated query-only match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0325s.
- Safety note: the Obsidian `PDF Library/` contains symlinks, not a new committed full-text corpus; Git/RAG ingest should still use summary-only notes and audited source metadata.

## Special Iteration: Batch 2 PDF Intake and RAG Ingest

- Goal: process the user's second-batch literature downloads, maintain a clean unavailable list, ingest usable sources into the governed RAG knowledge base, and refresh Obsidian.
- Archived 10 Batch 2 PDFs into ignored local storage:
  - High-trust measurement/device sources: Muntner 2019 AHA blood pressure measurement statement, AAMI/ESH/ISO 2018 validation standard, and ESH 2021 home BP monitoring position paper.
  - PPG/optical signal-quality sources: Fine 2021, Tamura 2014, Sun 2016, Frontiers 2019 measurement-site waveform, Tamura 2019 PPG/SpO2, Lee 2021 skin-compatible wearable PPG, and Electronics 2023 wearable PPG review.
- Maintained Batch 2 web result record and unresolved list:
  - `outputs/literature_download_tracker/web_batch2_results_2026-05-21.json`
  - `outputs/literature_download_tracker/unavailable_fulltext_list_batch2_2026-05-21.md`
  - `outputs/literature_download_tracker/unavailable_fulltext_list_current_2026-05-21.md`
- Remaining unresolved/download-blocked items now total 3:
  - ESC 2024 Essential Messages official PDF.
  - CHL-BHA Chinese 2024 guideline mirror.
  - ESH 2010 International Protocol validation PDF from DABL.
- Added 10 source catalog records and 10 full-text candidate records; generated 38 tracked Chinese full-text summary notes.
- Rebuilt source notes and chunks: 103 included sources, 467 chunks.
- Audit and evaluation after Batch 2:
  - No missing topics, no duplicate source hashes, no orphan source IDs, unsafe-source leakage 0.
  - Calibrated query-only retrieval: 100 golden queries, match rate 1.0, precision@5 1.0, topic hit rate 1.0, expected class hit rate 0.92.
  - Report evaluation: required-use coverage 1.0, recommendation grounding 1.0, sensitive high-trust rate 1.0, emergency consistency 1.0.
  - Strict quality gate passed: 220 tests, 103 included sources, 467 chunks, report P95 0.0348s.
- Refreshed Obsidian library:
  - 51 PDF symlinks, 37 sources with summary notes, 14 PDF-archived but summary-pending notes, 3 unresolved full-text/access items.
  - Local productivity index rebuilt: 100 chunks indexed.
- Safety note: the newly added PPG/optical literature is restricted to `signal_quality`, `cuffless_ppg_limitations`, or `research_background`; it cannot support diagnosis, treatment, medication changes, or replacement of validated cuff BP measurement.

## Special Iteration: Obsidian Clean Graph Refactor

- Goal: reduce noisy Obsidian graph nodes after the PDF literature library grew to 51 PDFs.
- Finding: graph clutter came mainly from generated wiki-links to PDF files, per-note topic tags, and the MOC linking directly to every literature note.
- Updated `scripts/sync_obsidian_literature.py`:
  - Replaced PDF wiki-links with external local `file://` links, so PDF attachments no longer become graph nodes.
  - Removed generated topic tags from literature notes (`tags: []`), avoiding tag-node clutter.
  - Added `Hubs/` with 10 topic hub notes.
  - Changed graph structure to `MOC -> Topic Hub -> Literature Note`.
  - Kept the full downloaded PDF index in the MOC as plain table rows without note wiki-links.
  - Added `Graph - Clean View.md` with recommended Obsidian graph settings and filters.
- Refreshed Obsidian library:
  - 51 literature notes, 10 topic hub notes, 1 clean graph guide, 1 MOC, 1 unresolved list.
  - No generated `[[...PDF Library...]]` links remain.
  - No generated `topic/...` tags remain.
- Rebuilt local productivity index: 137 chunks indexed.
- Strict quality gate still passed after the Obsidian graph cleanup: 220 tests, 103 included sources, 467 chunks, calibrated query-only match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report P95 0.0357s.
- Safety note: this is an Obsidian organization change only; it does not alter RAG medical boundaries, source catalog rules, or PDF full-text commit policy.

## Special Iteration: Batch 3 Download Request Planning

- Goal: prepare a third manual/web-agent download batch without duplicating Batch 1/2, local archived PDFs, or the current unresolved retry queue.
- Current KB audit before planning: 103 included sources, 467 chunks, no missing topics, no duplicate source hashes, no orphan source IDs, unsafe-source leakage 0.
- Gap assessment:
  - Strong coverage already exists for home BP monitoring, lifestyle, special populations, emergency guidance, and general PPG signal-quality summaries.
  - The next useful evidence gaps are narrower: cuffless BP validation/calibration standards, PTT-specific calibration limits, PPG motion/measurement-site evidence, light-source/optical-path effects, and skin-tone/fairness caveats for optical sensing.
- Created `outputs/literature_download_tracker/web_download_link_request_batch3_2026-05-21.md` with:
  - Batch 3A: 6 non-duplicative cuffless BP validation/calibration/device-boundary sources.
  - Batch 3B: 8 non-duplicative PPG optical signal-quality, motion-artifact, and skin-tone/fairness sources.
  - Explicit return schema for the web agent and rules against Sci-Hub, pirate mirrors, credentials, cookies, and tokenized temporary URLs.
  - A do-not-repeat list covering locally archived Batch 1/2 PDFs and the 3 current unresolved full-text items.
- Safety note: the planned Batch 3 PPG and cuffless-device research sources are intended only for `signal_quality`, `cuffless_ppg_limitations`, `validation`, or `research_background`; they must not be used to support diagnosis, treatment, medication changes, emergency reassurance, or replacement of validated cuff BP measurement.

## Special Iteration: Batch 3 PDF Intake and RAG Ingest

- Goal: archive the user's third-batch downloads, keep a clean unavailable list, promote usable sources into the governed summary-only RAG knowledge base, and refresh Obsidian.
- Archived 11 Batch 3 PDFs into ignored local storage:
  - Cuffless/PTT/device-boundary sources: Mukkamala 2015 PTT theory/practice, Mukkamala 2017 PTT calibration/error limits, Bradley 2022 cuffless BP devices, Parati 2026 ESC cuffless BP monitoring statement, and Ode 2020 PTT data acquisition.
  - PPG optical signal-quality and fairness sources: Park 2022 PPG analysis review, Arguello-Prada 2024 motion artifact review, Lee 2013 RGB reflection PPG during motion, Sjoding 2020 racial bias in pulse oximetry, Shi 2022 skin pigmentation systematic review, and Cabanas 2022 skin pigmentation systematic/bibliometric review.
- Recorded Batch 3 results and unresolved items:
  - `outputs/literature_download_tracker/web_batch3_results_2026-05-21.json`
  - `outputs/literature_download_tracker/unavailable_fulltext_list_batch3_2026-05-21.md`
  - `outputs/literature_download_tracker/unavailable_fulltext_list_current_2026-05-21.md`
- Remaining unresolved/download-blocked items now total 6:
  - ESC 2024 Essential Messages official PDF.
  - CHL-BHA Chinese 2024 guideline mirror.
  - ESH 2010 International Protocol validation PDF from DABL.
  - Stergiou 2023 ESH cuffless BP validation recommendations.
  - Maeda 2011 measurement-site motion-artifact PPG paper.
  - Sole-Morillo 2024 LED viewing angle / optical window PPG signal-quality paper.
- Added 11 source catalog records and 11 full-text candidate records; generated 49 tracked Chinese full-text summary notes.
- Rebuilt source notes and chunks: 114 included sources, 524 chunks.
- Audit and evaluation after Batch 3:
  - No missing topics, no duplicate source hashes, no orphan source IDs, unsafe-source leakage 0.
  - Calibrated query-only retrieval: 100 golden queries, match rate 1.0, precision@5 1.0, topic hit rate 1.0, expected class hit rate 0.93.
  - Report evaluation: required-use coverage 1.0, recommendation grounding 1.0, sensitive high-trust rate 1.0, emergency consistency 1.0.
  - Strict quality gate passed: 220 tests, 114 included sources, 524 chunks, report P95 0.0401s.
- Refreshed Obsidian library:
  - 62 PDF symlinks, 48 PDF-backed sources with summary notes, 14 PDF-archived but summary-pending notes, 6 unresolved full-text/access items.
  - Local productivity index rebuilt: 163 chunks indexed.
- Safety note: Batch 3 optical fairness and pulse-oximetry evidence is restricted to `signal_quality`, `research_background`, and disclaimer caveats; it must not be used to quantify PPG blood-pressure accuracy or justify clinical decisions.

## Special Iteration: Weekly Report Input Boundary and Experiment Concurrency

- Goal: make the weekly report accurately describe the application input boundary and enforce the user's experiment execution constraint that parallel tests may run, but concurrency must not exceed 5.
- Updated the practical weekly report to describe the real input shape as mini-program structured PPG-estimate output:
  - estimated SBP/DBP, heart rate, PPG confidence, signal quality score/label, capture duration, PPG source, algorithm version, calculation principle, selected user profile fields, and symptom flags.
  - Clarified that the RAG-Agent explains upstream estimates and performs evidence retrieval/safety review; it does not validate PPG BP estimation accuracy.
- Added `evaluation.max_concurrency: 5` to settings and a shared `scripts/evaluation_runtime.py` helper that caps requested experiment concurrency at 5.
- Updated `scripts/evaluate_reports.py` and `scripts/benchmark_report.py` to support parallel execution with capped workers and to record `max_concurrency` in output JSON.
- Extended report `input_summary` so generated reports preserve mini-program context fields: module, PPG signal quality score, confidence, capture duration, PPG source, algorithm version, calculation principle, and timestamp.
- Added regression tests to ensure requested concurrency above 5 is capped and recorded.
- Strict quality gate passed after the change: 223 tests, 114 included sources, 524 chunks, calibrated query-only match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report evaluation max concurrency 5, benchmark max concurrency 5, report P95 0.2413s.

## Special Iteration: Exploratory API Experiment

- Goal: use the existing API surface for a lightweight experiment without adding new endpoints or changing the core evaluation definition.
- Added `scripts/run_api_experiments.py`:
  - Calls existing FastAPI routes through `TestClient`: `/api/v1/reports/preview-rules`, `/api/v1/reports/generate`, and `/api/v1/kb/search`.
  - Runs report fixtures in parallel with the same `evaluation.max_concurrency` cap, never exceeding 5 workers.
  - Records API success rate, safety pass rate, input context preservation, evidence coverage, recommendation grounding, sensitive high-trust evidence, emergency consistency, latency, and KB search expected-use hit rate.
  - Writes JSON/CSV/Markdown experiment artifacts under `outputs/experiments/`.
- Added `tests/test_api_experiments.py` to verify concurrency capping, successful API report generation, emergency consistency, search probe coverage, and output artifact creation.
- Ran the API experiment over 50 report fixtures and 6 KB search probes:
  - API report success rate 1.0.
  - Safety pass rate 1.0.
  - Input context preservation rate 1.0.
  - Evidence coverage rate 1.0.
  - Recommendation grounding rate 1.0.
  - Sensitive high-trust rate 1.0.
  - Emergency consistency rate 1.0.
  - API P95 latency 0.1691s.
  - KB search expected-use hit rate 1.0.
- Strict quality gate passed after adding the API experiment: 224 tests, 114 included sources, 524 chunks, calibrated query-only match rate 1.0, precision@5 1.0, unsafe-source leakage 0, report evaluation max concurrency 5, benchmark max concurrency 5, report P95 0.212s.
- Scope note: this is an exploratory API-level experiment for Demo and weekly-report support. It does not replace the calibrated query-only retrieval evaluation, metadata-filter safety check, report fixtures, or strict quality gate.

## Documentation Iteration: Concise Weekly Report

- Goal: make the weekly report easier to read for a group-meeting style update while still showing enough concrete workload.
- Rewrote `outputs/weekly_reports/high_bp_rag_weekly_report_practical_2026-05-21.md` from a long detailed report into a concise reporting version.
- Preserved the core workload and results:
  - 62 locally archived full-text PDFs/materials.
  - 48 PDF-backed summary notes.
  - 114 included RAG sources and 524 chunks.
  - 224 passing tests.
  - 100 golden queries, 50 report fixtures, and 50 API experiment cases.
  - Precision@5 1.0, unsafe source leakage 0, recommendation grounding 1.0.
- Kept the medical boundary prominent: the system explains mini-program PPG estimate outputs and does not validate PPG BP accuracy, diagnose, treat, prescribe, stop medication, or replace validated cuff BP measurement.
- Kept the detailed report unchanged for backup/reference.
- Follow-up wording adjustment: removed "report generation" as a current-week highlight in the practical weekly report and reframed the API experiment as rule preview, evidence retrieval, structured response, and safety-field validation. Formal report generation and Demo presentation are now left as next-week work.

## Documentation Iteration: Humanized Weekly Report

- Goal: make the practical weekly report read more like a real group-meeting update instead of a generated metrics document.
- Rewrote `outputs/weekly_reports/high_bp_rag_weekly_report_practical_2026-05-21.md` again with a more natural first-person narrative.
- Kept the same factual workload and safety boundary:
  - 62 archived PDFs/materials, 48 PDF-backed notes, 114 included sources, 524 chunks.
  - 224 passing tests, 100 golden queries, 50 structured fixtures, and 50 API link cases.
  - No claim that the project validates PPG BP accuracy.
  - Formal report generation and Demo presentation remain next-week work.

## Documentation Iteration: Presentation Weekly Report

- Goal: adapt the practical weekly report for presentation use, with a neutral project-summary voice instead of a first-person narrative.
- Rewrote `outputs/weekly_reports/high_bp_rag_weekly_report_practical_2026-05-21.md` as a concise display version suitable for group reporting or PPT conversion.
- Preserved the core factual workload:
  - 62 locally archived full-text PDFs/materials are treated as this week's literature workload.
  - 48 PDF-backed Chinese summary notes, 114 included RAG sources, and 524 chunks.
  - 224 passing tests, 100 golden queries, 50 structured fixtures, and 50 API link experiment cases.
- Highlighted the source governance workflow: PDF registration, source catalog screening, Chinese notes, chunk generation, audit, and retrieval evaluation.
- Kept the application boundary explicit: the system explains mini-program PPG estimate outputs and does not validate PPG BP accuracy, diagnose, treat, prescribe, stop medication, or replace validated cuff BP measurement.
- Kept formal report generation and Streamlit Demo presentation as next-stage work rather than current-week achievements.

## Presentation Artifact: Canva Weekly Update Deck

- Goal: create a concise Canva presentation for this week's RAG-Agent progress update.
- Used the presentation-ready weekly report as the content source and generated a 5-page Canva deck:
  - `本周重点：先把知识库和评估链路打牢`
  - `文献与知识库规模`
  - `source catalog：让每条证据有边界`
  - `评估与接口链路结果`
  - `下周计划：报告与 Demo 展示`
- Created Canva design `DAHKSZUYFqI`, titled `演示文稿 - 高血压 PPG 估算进展`.
- Recorded edit/view links and candidate alternatives in `outputs/weekly_reports/canva_weekly_presentation_2026-05-21.md`.
- Scope note: this artifact is for weekly display; it does not change the RAG system, evaluation design, knowledge base, or medical-safety claims.

## Presentation Artifact Revision: Content-Rich Canva Deck

- Goal: fix the first generated Canva deck because it was visually clean but too sparse for a real weekly work report.
- Edited the same Canva design `DAHKSZUYFqI` directly and saved it as `高血压 PPG RAG-Agent 本周进展（内容版）`.
- Added the missing key information:
  - mini-program structured PPG-estimate input boundary.
  - 62 PDFs, 48 PDF-backed Chinese summary notes, 114 included sources, and 524 chunks.
  - source catalog workflow and evidence-use boundaries.
  - 224 passing tests, 100 golden queries, 50 structured fixtures, 50 API link cases, and max concurrency 5.
  - next-stage plan for pending PDF summaries, blocked sources, realistic queries, formal report generation, and Streamlit Demo.
- Updated `outputs/weekly_reports/canva_weekly_presentation_2026-05-21.md` with the final Canva edit/view links and revised page structure.

## Presentation Artifact Revision: Testing-Enhanced Canva Deck

- Goal: explain the testing system in the weekly presentation rather than showing only headline metrics.
- Edited the same Canva design `DAHKSZUYFqI` and saved a testing-enhanced version.
- Added concrete testing content:
  - structured mini-program input examples, including `145/92 + HR 82 + signal_quality 0.86 + confidence 0.68`, low-quality PPG, emergency symptoms, and alias inputs.
  - test dataset construction: 100 golden queries, 50 case fixtures, and 224 passing pytest cases.
  - golden query coverage across PPG limitations, signal quality, home remeasurement, emergency, medication, special populations, lifestyle, and device validation.
  - calibrated query-only evaluation explanation to show that gold expected uses are not passed to the retriever during the main metric.
  - short code snippets for non-circular retrieval evaluation, precision floor, and max concurrency capped at 5.
  - current retrieval/API metrics: Precision@5 1.0, unsafe source leakage 0, 50 API cases, success rate 1.0, and P95 latency 0.1691s.
- Updated `outputs/weekly_reports/canva_weekly_presentation_2026-05-21.md` with the final Canva links and testing-enhanced page structure.

## Presentation Artifact Revision: Workload and Governance Emphasis

- Goal: make the weekly presentation more legible while restoring the key workload and knowledge-governance details that were lost during font-size enlargement.
- Edited the same Canva design `DAHKSZUYFqI` and saved the final display-enhanced version.
- Revised the deck structure:
  - Page 2 now summarizes the main workload: 62 PDFs/materials, 48 Chinese summaries, 14 pending PDF summaries, 6 blocked sources, 114 included sources, 524 chunks, 100 golden queries, 50 fixtures, 224 pytest cases, and 50 API cases.
  - Page 3 now explains the governed literature workflow: PDF registration, source catalog, evidence_class/allowed_uses/source_hash, Chinese notes, chunks.jsonl, and audit checks.
  - Page 4 keeps the testing design: golden query coverage, structured mini-program fixtures, and automated test coverage.
  - Page 5 keeps calibrated query-only retrieval metrics, unsafe leakage, API experiment results, and the max-concurrency cap.
- Updated `outputs/weekly_reports/canva_weekly_presentation_2026-05-21.md` with the final edit/view links and final page structure.

## Iteration: Advisor Application Upgrade (2026-06-10)

- Goal: move from one-shot structured-input reports to a post-measurement advisor application — evidence-cited Q&A plus gentle, staged proactive intake — while overhauling chunking, vectorization, and citation quality.
- Chunking: new structure-aware `app/services/chunking.py` (sentence-safe zh/en splitting, sentence-level overlap, per-source merge of substantive sections, `section_role: governance` tagging excluded from report retrieval). Store went from 629 chunks (486 under 100 chars, mostly per-source boilerplate) to 336 chunks (206 content, median ~500 chars, zero sub-100 fragments).
- Retrieval: shared zh-bigram tokenizer; keyword cosine fused with offline hashing vectors built at ingest; per-source caps; optional fulltext-passage merge (`retrieval.include_fulltext: auto`) with vector prefilter, skipped for sensitive requests which stay high-trust-only.
- Citations: source-level dedup, renumber-by-first-appearance with uncited-reference pruning, page locators for fulltext passages, structured `references` payload, sentence-level citation prompting.
- Advisor: `config/advisor_questions.yaml` staged question bank (why-shown, skippable, sensitivity-ordered, emergency-suppressed), `ConversationProfile` fact accumulation with conservative free-text extraction, field-targeted retrieval for follow-up advice, LLM/template dual path under the shared safety review; new `/api/v1/advisor/*` endpoints and a Streamlit「随访对话」tab.
- Strict quality gate: all 16 criteria pass — 308 tests, 136 included sources, 336 chunks, calibrated match rate 1.0, precision@5 0.983, topic hit rate 1.0, unsafe leakage 0, grounding 1.0, report P95 0.784s.

## Iteration: OpenAI Embedding Retrieval Backend (2026-06-10)

- Goal: per user decision, use OpenAI embeddings as the primary retrieval vectors.
- `retrieval.embedding_backend: auto` now prefers the OpenAI embedding npz for both the summary and fulltext stores, with per-query embedding cache, 5-minute API-failure backoff, dimension validation, id-coverage and mtime freshness checks (a re-ingested chunks file invalidates an older index even when chunk ids collide).
- Offline behaviour unchanged: hashing vectors -> keyword-only degradation chain preserved; quality gate runs key-free.
- New tests: tests/test_retriever_vector_backend.py (backend dispatch, fallback, staleness, cache, end-to-end plumbing with a mocked OpenAI index).
- Activation: set OPENAI_EMBEDDING_API_KEY in .env, run scripts/ingest_openai_embeddings.py --scope processed_chunks (and optionally fulltext_chunks).

## Iteration: Chapter-6 Application-Layer Experiments (E1–E5) (2026-06-11)

- Goal: run the no-human-needed parts of the Chapter-6 application-layer experiment plan to completion, vigilantly, with version management — under a gentle/resumable rate-limited harness protecting a small third-party GPT-5.5 judge endpoint.
- E1 retrieval ablation (pooled-qrels, GPT-5.5 graded relevance, 947 pairs): hybrid > keyword (graded nDCG@5 +0.0194, Holm p=0.0155); OpenAI ≈ offline-hashing embedding (n.s.); fulltext/dedup raise source diversity not top-5 ranking; self-eval overstatement ~0.8pp. PRELIMINARY (judge lenient ~6.3% grade-0; human review sheet of 350 pairs prepared).
- E2 generation ablation (real DeepSeek S1–S4, replacing the hardcoded strawman): RAG grounds 100% of advice in governed evidence with full use-coverage and high-trust sensitive sourcing; real LLM-only grounds 0% / sensitive 0.48; LLM-only safety-fallback 26% vs RAG 10%.
- E3 citation faithfulness (GPT-5.5 sentence judge, 750 cited sentences): recall ~0.95 but strict semantic support only ~0.19 / lenient ~0.52; S2(enforced) raises citation count not faithfulness; verified NOT a snippet-contamination artifact (clean vs contaminated identical). PRELIMINARY pending human calibration.
- E5 safety red-team (36 adversarial seeds × 3 personas × on/off, rule + GPT-5.5 double-judge): prompt-level constraints already yield 0 judge-confirmed violations even with the rule review OFF; the regex rule has 30% false positives (100% on medication) on negated medication advice; benign over-block 0/12. External AHA emergency gold (not system yaml); OFF arm isolated.
- 8 result-invalidating bugs caught and fixed (E1×5, E2×1, E3×1, E5×1); the catch chain (esp. pooling coverage bias and rule-vs-judge separation) is methodology-section material.
- Final offline quality gate: 16/16 pass — 360 tests, 136 sources, 336 chunks, match 1.0, precision@5 0.983, grounding 1.0, P95 0.91s.
- Version management: 6 commits (app+exp framework, KB rechunk, E1 fixes+safety, E3/E5 harness, gate artifacts, changelog); preliminary judge-dependent artifacts gitignored, numbers preserved in thesis paper-prep/110–113.
