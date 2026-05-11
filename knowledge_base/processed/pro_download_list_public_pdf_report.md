# Pro Download List Public PDF Intake

- Source workbook: `PPG血压估算_RAG知识库下载清单.xlsx`
- Selection rule: rows where `获取方式` contains `PDF开放下载`
- Candidates: 22
- Downloaded now: 15
- Already existed: 2
- Failed direct download: 5
- PDF validation failures: 0

## Downloaded Or Existing

| Row | Priority | Category | Title | Status | File | Pages |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | P0 必须 | 中国基层管理 | 基层医疗卫生机构高血压防治管理标准（WS/T 872—2025） | downloaded | `nhc_2025_primary_care_hypertension_standard_ws_t_872.pdf` | 8 |
| 7 | P0 必须 | 血压测量规范 | 中国血压测量指南 | downloaded | `chinese_2011_bp_measurement_guideline.pdf` | 15 |
| 8 | P1 建议 | 患者教育 | 中国高血压患者教育指南 | downloaded | `chinese_2013_hypertension_patient_education_guideline.pdf` | 77 |
| 9 | P1 建议 | 特殊人群 | 中国老年高血压管理指南2023 | downloaded | `chinese_2023_elderly_hypertension_management_guideline.pdf` | 31 |
| 10 | P2 可选 | 特殊病因/转诊 | 继发性高血压筛查和诊断中国专家共识 | downloaded | `chinese_2025_secondary_hypertension_screening_consensus.pdf` | 15 |
| 11 | P0 必须 | 国际核心指南 | 2025 AHA/ACC/AANP/AAPA/ABC/ACCP/ACPM/AGS/AMA/ASPC/NMA/PCNA/SGIM Guideline for the Prevention, Detection, Evaluation, and Management of High Blood Pressure in Adults | existing | `acc_aha_2025_full_guideline_record.pdf` | 105 |
| 15 | P1 建议 | 国际核心指南 | Guideline for the pharmacological treatment of hypertension in adults | downloaded | `who_2021_hypertension_pharmacological_treatment_guideline.pdf` | 61 |
| 16 | P1 建议 | 国际核心指南 | Hypertension in adults: diagnosis and management (NICE guideline NG136) | downloaded | `nice_ng136_hypertension.pdf` | 52 |
| 18 | P0 必须 | 家庭监测/复测 | Home Blood Pressure Measurement Instructions | downloaded | `aha_home_bp_measurement_instructions.pdf` | 1 |
| 24 | P0 必须 | PPG/无袖带局限 | Cuffless Devices for the Measurement of Blood Pressure: A Scientific Statement From the American Heart Association | existing | `aha_cuffless_bp_scientific_statement.pdf` | 11 |
| 25 | P0 必须 | PPG/无袖带局限 | Cuffless Non-invasive Blood Pressure Measuring Devices: Clinical Performance Testing and Evaluation | downloaded | `fda_cuffless_nibp_draft_guidance.pdf` | 11 |
| 32 | P0 必须 | 生活方式建议 | Your Guide to Lowering Your Blood Pressure with DASH | downloaded | `nhlbi_dash_lowering_blood_pressure_guide.pdf` | 64 |
| 33 | P0 必须 | 生活方式建议 | How Can I Lower High Blood Pressure? | downloaded | `aha_reduce_high_blood_pressure_answers_by_heart.pdf` | 2 |
| 34 | P0 必须 | 生活方式建议 | Simple Steps to Improve Your High Blood Pressure | downloaded | `aha_steps_to_improve_high_bp.pdf` | 1 |
| 35 | P1 建议 | 生活方式建议 | Life's Essential 8: How to Manage Blood Pressure | downloaded | `aha_life_essential_8_manage_blood_pressure.pdf` | 1 |
| 37 | P1 建议 | 生活方式建议 | Managing My Blood Pressure: Questions to Ask My Doctor | downloaded | `cdc_managing_my_blood_pressure_questions.pdf` | 1 |
| 42 | P1 建议 | 特殊人群 | Blood Pressure Categories for Individuals who are Pregnant | downloaded | `aha_pregnancy_blood_pressure_categories.pdf` | 1 |

## Direct Download Failures

| Row | Category | Title | URL | Reason |
| --- | --- | --- | --- | --- |
| 2 | 中国核心指南 | 中国高血压防治指南（2024年修订版） | https://www.chl-bha.org.cn/Public/ueditor/php/upload/20240815/17236841017752.pdf | <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1010)> |
| 6 | 家庭血压监测 | 2019中国家庭血压监测指南 | https://zhgxyzz.xml-journal.net/cn/article/pdf/preview/10.16439/j.cnki.1673-7245.2019.08.005.pdf | <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'zhgxyzz.xml-journal.net'. (_ssl.c:1010)> |
| 12 | 国际核心指南 | 2024 ESC Guidelines for the management of elevated blood pressure and hypertension | https://academic.oup.com/eurheartj/article-pdf/45/38/3912/59633218/ehae178.pdf | HTTP Error 403: Forbidden |
| 19 | 家庭监测/复测 | Self-Measured Blood Pressure Monitoring at Home: A Joint Policy Statement From the American Heart Association and American Medical Association | https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000000803 | HTTP Error 403: Forbidden |
| 44 | 心血管风险评估 | Development and Validation of the American Heart Association Predicting Risk of Cardiovascular Disease EVENTs (PREVENT) Equations | https://www.ahajournals.org/doi/pdf/10.1161/circulationaha.123.067626 | HTTP Error 403: Forbidden |

## Notes

- Downloaded PDF files are stored under `knowledge_base/sources/downloads/`, which is intentionally Git-ignored.
- This report and the JSON manifest are safe to commit because they contain only metadata, file names, hashes, and failure reasons.
- Failed rows were not bypassed with credentials or institutional access; they remain candidates for browser/manual download or alternative official mirrors.
