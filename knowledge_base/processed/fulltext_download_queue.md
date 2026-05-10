# Full-text Candidate Download Queue

- Updated: 2026-05-10
- Candidates: 9
- Public auto-download: 1
- Institution/browser queue: 5

## Safe Access Rules

- 不记录、不保存、不复用机构账号、密码、cookie 或 token。
- 需要机构身份时，只使用用户当前浏览器会话完成下载。
- 下载的 PDF 放入 `knowledge_base/sources/downloads/`；该目录被 Git 忽略。
- 只有中文摘要和 citation 进入可提交知识库，不复制受版权保护全文。

## Public Auto-download

### P4 ISH 2020 global hypertension practice guideline public PDF

- candidate_id: `ish_2020_public_pdf`
- source_id: `ish_2020_global_guideline`
- access_mode: `public_pdf`
- status: `downloadable`
- landing_url: https://ish-world.com/global-hypertension-practice-guidelines/
- pdf_url: https://www.pascar.org/uploads/files/International_Society_of_Hypertension_Global_Guidelines_2020.pdf
- save_as: `knowledge_base/sources/downloads/ish_2020_global_guideline.pdf`
- purpose: home_bp_monitoring; remeasurement; lifestyle; special_population

## Needs Browser Or Institution

### P1 AHA cuffless blood pressure scientific statement full text

- candidate_id: `aha_cuffless_bp_statement_fulltext`
- source_id: `aha_cuffless_bp_scientific_statement`
- access_mode: `institution_or_browser`
- status: `summarized`
- landing_url: https://professional.heart.org/en/science-news/cuffless-devices-for-the-measurement-of-blood-pressure
- pdf_url: https://www.ahajournals.org/doi/pdf/10.1161/HYP.0000000000000254
- save_as: `knowledge_base/sources/downloads/aha_cuffless_bp_scientific_statement.pdf`
- purpose: cuffless_ppg_limitations; device_advice; signal_quality; research_background

### P1 Chinese Guidelines for the Prevention and Treatment of Hypertension 2024 revision full text

- candidate_id: `chinese_hypertension_2024_fulltext`
- source_id: `chinese_hypertension_guideline_2024_catalog`
- access_mode: `institution_or_browser`
- status: `summarized`
- landing_url: https://www.sciopen.com/article/10.26599/1671-5411.2025.01.008
- pdf_url: https://www.sciopen.com/article/pdf/10.26599/1671-5411.2025.01.008
- save_as: `knowledge_base/sources/downloads/chinese_hypertension_guideline_2024_catalog.pdf`
- purpose: bp_category_reference; home_bp_monitoring; remeasurement; lifestyle; special_population

### P4 ESH 2023 arterial hypertension guideline full text

- candidate_id: `esh_2023_guideline_fulltext`
- source_id: `esh_2023_hypertension_guideline`
- access_mode: `institution_or_browser`
- status: `awaiting_human_verification`
- landing_url: https://www.eshonline.org/guidelines/
- pdf_url: n/a
- save_as: `knowledge_base/sources/downloads/esh_2023_hypertension_guideline.pdf`
- purpose: home_bp_monitoring; remeasurement; special_population

## Metadata Only

### P6 ISO 81060-2 validation standard metadata record

- candidate_id: `iso_81060_2_record_only`
- source_id: `iso_81060_2_validation_standard`
- access_mode: `metadata_only_paid_standard`
- status: `metadata_only`
- landing_url: https://www.iso.org/standard/73339.html
- pdf_url: n/a
- save_as: `knowledge_base/sources/downloads/iso_81060_2_validation_standard.pdf`
- purpose: device_advice; research_background
