# 给网页版的文献下载链接检索任务 - Batch 3

请按下面清单逐条查找**合法公开下载链接**或**官方落地页链接**。这一批用于补强当前高血压 RAG 的两个薄弱环节：

- 无袖带 / PTT / PPG 血压估算的验证、校准、设备边界。
- PPG 光学信号质量的运动、测量部位、光源/光路、肤色公平性和伪差识别。

请不要提供 Sci-Hub、盗版镜像、需要账号密码/cookie/token 的链接，也不要提供 Silverchair、Cloudflare 等带一次性 token 的临时 PDF URL。

## 返回格式要求

请对每条文献返回：

1. `item_id`
2. `title`
3. `best_pdf_url`：如果能找到直接 PDF 链接就填；如果没有，填 `not_found`
4. `landing_url`：出版社页、PubMed、PMC、机构仓储页、指南组织官网等
5. `access_type`：open_pdf / official_page_only / institution_required / blocked / not_found
6. `source_confidence`：high / medium / low
7. `reason`：说明为什么这个链接可信，或为什么找不到
8. `save_as`：保持我给出的文件名

请特别注意：

- 优先官方页面、PubMed/PMC、出版社页面、大学/机构开放仓储、指南组织官网、MDPI/Frontiers/Springer/PLOS/BMJ 等正式开放页面。
- 如果只有 HTML 全文、没有 PDF，也请给 HTML 落地页并标记 `official_page_only`。
- 如果页面被 Cloudflare、recaptcha、403、402、出版社机器人保护或超时挡住，请标记 `blocked` 或 `institution_required`，不要绕过限制。
- 每条只需给 1-3 个最可信链接，不要给泛泛搜索结果页。
- 研究性 PPG 文献只用于 `signal_quality` / `cuffless_ppg_limitations` / `research_background`，不要当成临床诊断、治疗、开药、停药或设备替代规范血压测量的依据。

## Batch 3A：无袖带 BP 验证、校准与设备边界

| item_id | priority | exact_title | DOI / PMID / PMCID | why_needed | desired_save_as | suggested_queries |
| --- | --- | --- | --- | --- | --- | --- |
| stergiou_2023_esh_cuffless_validation_recommendations | P1 | European Society of Hypertension recommendations for the validation of cuffless blood pressure measuring devices: European Society of Hypertension Working Group on Blood Pressure Monitoring and Cardiovascular Variability | DOI: 10.1097/HJH.0000000000003483; PMID: 37303198 | 高优先级。补强无袖带 BP 设备验证流程、位置测试、运动/运动后测试、校准稳定性测试；只能用于 validation/cuffless limitation。 | `knowledge_base/sources/downloads/stergiou_2023_esh_cuffless_validation_recommendations.pdf` | `"European Society of Hypertension recommendations for the validation of cuffless blood pressure measuring devices" pdf`; `"10.1097/HJH.0000000000003483" pdf`; `"PMID 37303198" cuffless validation` |
| mukkamala_2015_ptt_bp_monitoring_theory_practice | P1 | Toward Ubiquitous Blood Pressure Monitoring via Pulse Transit Time: Theory and Practice | DOI: 10.1109/TBME.2015.2441951; PMID: 26057530 | PTT/PPG 血压估算经典综述，支持“理论可行但受校准、个体差异、生理干扰限制”的边界。 | `knowledge_base/sources/downloads/mukkamala_2015_ptt_bp_monitoring_theory_practice.pdf` | `"Toward Ubiquitous Blood Pressure Monitoring via Pulse Transit Time" pdf`; `"10.1109/TBME.2015.2441951" pdf`; `"PMID 26057530"` |
| mukkamala_2017_ptt_calibration_error_limits | P1 | Toward Ubiquitous Blood Pressure Monitoring via Pulse Transit Time: Predictions on Maximum Calibration Period and Acceptable Error Limits | DOI: 10.1109/TBME.2017.2756018; PMID: 28952930 | 支撑“PTT-based 系统需要校准且校准有效期有限”，适合报告中解释不能把单次 PPG 估算当作诊断依据。 | `knowledge_base/sources/downloads/mukkamala_2017_ptt_calibration_error_limits.pdf` | `"Predictions on Maximum Calibration Period and Acceptable Error Limits" pdf`; `"10.1109/TBME.2017.2756018" pdf`; `"PMID 28952930"` |
| bradley_2022_cuffless_bp_devices_review | P2 | Cuffless Blood Pressure Devices | DOI: 10.1093/ajh/hpac017 | 综述无袖带 BP 技术路径、验证难点、落地障碍；只用于研究背景和设备边界，不用于患者级临床建议。 | `knowledge_base/sources/downloads/bradley_2022_cuffless_bp_devices_review.pdf` | `"Cuffless Blood Pressure Devices" "hpac017" pdf`; `"10.1093/ajh/hpac017" pdf`; `"Cuffless Blood Pressure Devices" "American Journal of Hypertension"` |
| parati_2026_esc_cuffless_bp_monitoring_statement | P2 | Cuffless Blood Pressure Monitoring Devices: Technical Foundations and Clinical Implications: Scientific Statement of the European Society of Cardiology (ESC) Working Group on e-Cardiology, the ESC Council on Hypertension, and the European Association of Preventive Cardiology of the ESC | DOI: 10.1093/eurjpc/zwag058 | 新近 ESC 科学声明，适合补充 cuffless BP 的技术基础、临床解释边界、校准和验证问题。 | `knowledge_base/sources/downloads/parati_2026_esc_cuffless_bp_monitoring_statement.pdf` | `"Cuffless Blood Pressure Monitoring Devices: Technical Foundations and Clinical Implications" pdf`; `"10.1093/eurjpc/zwag058" pdf`; `"European Society of Cardiology" cuffless blood pressure monitoring devices` |
| ode_2020_continuous_ambulatory_bp_ptt_data_acquisition | P3 | Towards Continuous and Ambulatory Blood Pressure Monitoring: Methods for Efficient Data Acquisition for Pulse Transit Time Estimation | DOI: 10.3390/s20247106; PMCID: PMC7764444 | 补充 PTT 数据采集、传感器组合和动态监测背景；只用于 research_background/signal_quality。 | `knowledge_base/sources/downloads/ode_2020_continuous_ambulatory_bp_ptt_data_acquisition.pdf` | `"Towards Continuous and Ambulatory Blood Pressure Monitoring" "Pulse Transit Time" pdf`; `"10.3390/s20247106" pdf`; `"PMC7764444"` |

## Batch 3B：PPG 光学信号质量、运动伪差、肤色与公平性

| item_id | priority | exact_title | DOI / PMID / PMCID | why_needed | desired_save_as | suggested_queries |
| --- | --- | --- | --- | --- | --- | --- |
| park_2022_ppg_analysis_applications_integrative_review | P1 | Photoplethysmogram Analysis and Applications: An Integrative Review | DOI: 10.3389/fphys.2021.808451; PMID: 35300400; PMCID: PMC8920970 | 补 PPG 波形分析、噪声、质量评估、特征提取和应用边界。 | `knowledge_base/sources/downloads/park_2022_ppg_analysis_applications_integrative_review.pdf` | `"Photoplethysmogram Analysis and Applications: An Integrative Review" pdf`; `"10.3389/fphys.2021.808451" pdf`; `"PMC8920970"` |
| arguello_prada_2024_ppg_motion_artifact_detection_review | P1 | Machine Learning Applied to Reference Signal-Less Detection of Motion Artifacts in Photoplethysmographic Signals: A Review | DOI: 10.3390/s24227193 | 直接补运动伪差检测、无参考信号质量判断、实时适用性限制；只用于 signal_quality/research_background。 | `knowledge_base/sources/downloads/arguello_prada_2024_ppg_motion_artifact_detection_review.pdf` | `"Machine Learning Applied to Reference Signal-Less Detection of Motion Artifacts in Photoplethysmographic Signals" pdf`; `"10.3390/s24227193" pdf`; `site:mdpi.com "s24227193" pdf` |
| maeda_2011_measurement_site_motion_artifacts_ppg | P1 | Relationship between measurement site and motion artifacts in wearable reflected photoplethysmography | DOI: 10.1007/s10916-010-9505-0; PMID: 20703691 | 支撑“运动和测量部位会显著影响 PPG 质量”，适合 sensor_position/motion_artifact 解释。 | `knowledge_base/sources/downloads/maeda_2011_measurement_site_motion_artifacts_ppg.pdf` | `"Relationship between measurement site and motion artifacts in wearable reflected photoplethysmography" pdf`; `"10.1007/s10916-010-9505-0" pdf`; `"PMID 20703691"` |
| lee_2013_rgb_reflection_ppg_motion_hr | P2 | Comparison between red, green and blue light reflection photoplethysmography for heart rate monitoring during motion | DOI: 10.1109/EMBC.2013.6609852; PMID: 24110039 | 补不同波长在运动状态下的 PPG 稳定性差异；只用于光源/运动伪差背景。 | `knowledge_base/sources/downloads/lee_2013_rgb_reflection_ppg_motion_hr.pdf` | `"Comparison between red, green and blue light reflection photoplethysmography" pdf`; `"10.1109/EMBC.2013.6609852" pdf`; `"PMID 24110039"` |
| sjoding_2020_racial_bias_pulse_oximetry | P2 | Racial Bias in Pulse Oximetry Measurement | DOI: 10.1056/NEJMc2029240; PMID: 33326721; PMCID: PMC7808260 | 补光学传感器在肤色/人群差异方面的安全边界；只用于 skin_tone/fairness 背景，不外推为 PPG 血压准确性结论。 | `knowledge_base/sources/downloads/sjoding_2020_racial_bias_pulse_oximetry.pdf` | `"Racial Bias in Pulse Oximetry Measurement" pdf`; `"10.1056/NEJMc2029240" pdf`; `"PMC7808260"` |
| shi_2022_skin_pigmentation_pulse_oximetry_systematic_review | P2 | The accuracy of pulse oximetry in measuring oxygen saturation by levels of skin pigmentation: a systematic review and meta-analysis | DOI: 10.1186/s12916-022-02452-8; PMCID: PMC9377806 | 系统综述层面补肤色对光学测量准确性的影响；只用于 fairness/signal_quality 背景。 | `knowledge_base/sources/downloads/shi_2022_skin_pigmentation_pulse_oximetry_systematic_review.pdf` | `"The accuracy of pulse oximetry in measuring oxygen saturation by levels of skin pigmentation" pdf`; `"10.1186/s12916-022-02452-8" pdf`; `"PMC9377806"` |
| cabanas_2022_skin_pigmentation_pulse_oximetry_bibliometric | P3 | Skin Pigmentation Influence on Pulse Oximetry Accuracy: A Systematic Review and Bibliometric Analysis | DOI: 10.3390/s22093402 | 可作为肤色/光学传感误差背景的补充来源；如和 Shi 2022 重复，可标记为 optional。 | `knowledge_base/sources/downloads/cabanas_2022_skin_pigmentation_pulse_oximetry_bibliometric.pdf` | `"Skin Pigmentation Influence on Pulse Oximetry Accuracy" pdf`; `"10.3390/s22093402" pdf`; `site:mdpi.com "s22093402" pdf` |
| sole_morillo_2024_led_viewing_angle_optical_window_ppg_signal_quality | P3 | Evaluation of the impact of LED viewing angle and optical window choice on photoplethysmography signal quality | DOI: 10.1117/12.3001707 | 补传感器硬件/光路因素对 PPG 信号质量的影响；如果只能找到 SPIE 官方落地页，也可标记 institution_required。 | `knowledge_base/sources/downloads/sole_morillo_2024_led_viewing_angle_optical_window_ppg_signal_quality.pdf` | `"Evaluation of the impact of LED viewing angle and optical window choice on photoplethysmography signal quality" pdf`; `"10.1117/12.3001707" pdf`; `"photoplethysmography signal quality" "LED viewing angle"` |

## 本批不要重复查找

Batch 1、Batch 2 和本地已归档 PDF 中已经处理过的条目请不要重复。尤其不要重复：

- `aha_ama_2020_smbp_policy_statement`
- `chandrasekhar_2020_contact_pressure_cuffless_bp`
- `shirbani_2020_ambient_light_skin_tone_vpg`
- `teng_2004_contact_force_ppg`
- `muntner_2019_aha_bp_measurement_scientific_statement`
- `aami_esh_iso_2018_universal_validation_standard`
- `esh_2021_home_bp_monitoring_position_paper`
- `fine_2021_ppg_sources_of_inaccuracy`
- `tamura_2014_wearable_ppg_sensors_past_present`
- `sun_2016_ppg_revisited_contact_noncontact_imaging`
- `frontiers_2019_ppg_measurement_site_waveform`
- `tamura_2019_current_progress_ppg_spo2`
- `lee_2021_skin_compatible_wearable_ppg`
- `electronics_2023_ppg_wearable_devices_review`
- `desquins_2022_ppg_quality_assessment_survey`
- `charlton_2025_wrist_ppg_signal_quality`
- `charlton_2023_wearable_ppg_roadmap`
- `charlton_2022_ppg_best_practices`
- `charlton_2022_wearable_ppg_cardiovascular_review`
- `allen_2007_ppg_clinical_measurement_review`
- `bent_2020_wearable_optical_hr_inaccuracy`

下面 3 个是当前维护中的未下载/访问受限清单，本批也先不要重复，除非专门做失败项 retry：

- `esc_2024_bp_guideline_key_points`
- `chinese_hypertension_guideline_2024_revision_chl_bha`
- `esh_2010_international_protocol_validation`

## 下载后我会如何入库

你返回下载链接后，我会逐条维护：

- `outputs/literature_download_tracker/web_batch3_results_2026-05-21.json`
- `outputs/literature_download_tracker/unavailable_fulltext_list_current_2026-05-21.md`
- `knowledge_base/sources/fulltext_candidates.yaml`
- `knowledge_base/sources/source_catalog_extra.yaml`
- `knowledge_base/sources/fulltext_summaries/*.summary.md`
- Obsidian 文献库的 PDF 链接、source note、topic hub 和 unresolved list

PDF 全文仍只放在本地 ignored 目录，不提交到 Git；RAG 只入中文摘要、citation、访问记录和 allowed uses。
