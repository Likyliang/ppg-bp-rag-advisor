# 给网页版的文献下载链接检索任务 - Batch 2

请按下面清单逐条查找**合法公开下载链接**或**官方落地页链接**。这一批和上一份 `web_download_link_request_2026-05-21.md` **不要重复**。目标是让我手动逐篇下载 PDF，然后放入本地 RAG 项目。请不要提供 Sci-Hub、盗版镜像、需要账号密码/cookie/token 的链接。

## 返回格式要求

请对每条文献返回：

1. `item_id`
2. `title`
3. `best_pdf_url`：如果能找到直接 PDF 链接就填；如果没有，填 `not_found`
4. `landing_url`：出版社页、PubMed、PMC、机构仓储页、指南页等
5. `access_type`：open_pdf / official_page_only / institution_required / blocked / not_found
6. `source_confidence`：high / medium / low
7. `reason`：说明为什么这个链接可信，或为什么找不到
8. `save_as`：保持我给出的文件名

请特别注意：

- 优先官方页面、PubMed/PMC、出版社页面、大学/机构开放仓储、指南组织官网、MDPI/Frontiers/Springer 等正式开放页面。
- 如果只有 HTML 全文、没有 PDF，也请给 HTML 落地页并标记 `official_page_only`。
- 如果页面被 Cloudflare、recaptcha、403、出版社机器人保护挡住，请标记 `blocked` 或 `institution_required`，不要绕过限制。
- 每条只需给 1-3 个最可信链接，不要给泛泛搜索结果页。
- 研究性 PPG 文献只用于 `signal_quality` / `research_background`，不要当成临床诊断或治疗依据。

## Batch 2 必找清单

| item_id | priority | exact_title | DOI / PMID / PMCID | why_needed | desired_save_as | suggested_queries |
| --- | --- | --- | --- | --- | --- | --- |
| muntner_2019_aha_bp_measurement_scientific_statement | P1 | Measurement of Blood Pressure in Humans: A Scientific Statement From the American Heart Association | DOI: 10.1161/HYP.0000000000000087 | 强化规范血压测量、设备/袖带、姿势、测量误差来源，是解释“PPG 不能替代规范测量”的高可信补充。 | `knowledge_base/sources/downloads/muntner_2019_aha_bp_measurement_scientific_statement.pdf` | `"Measurement of Blood Pressure in Humans" "HYP.0000000000000087" pdf`; `"Measurement of Blood Pressure in Humans" "American Heart Association" "Scientific Statement"` |
| aami_esh_iso_2018_universal_validation_standard | P1 | A universal standard for the validation of blood pressure measuring devices: Association for the Advancement of Medical Instrumentation/European Society of Hypertension/International Organization for Standardization (AAMI/ESH/ISO) Collaboration Statement | DOI: 10.1097/HJH.0000000000001634; PMID: 29384983; PMCID: PMC5796427 | 支撑“应使用经过验证的血压设备”和设备验证原则；可作为 validation_standard。 | `knowledge_base/sources/downloads/aami_esh_iso_2018_universal_validation_standard.pdf` | `"A universal standard for the validation of blood pressure measuring devices" pdf`; `"10.1097/HJH.0000000000001634" pdf`; `PMCID PMC5796427` |
| esh_2021_home_bp_monitoring_position_paper | P1 | Home blood pressure monitoring: methodology, clinical relevance and practical application: a 2021 position paper by the Working Group on Blood Pressure Monitoring and Cardiovascular Variability of the European Society of Hypertension | DOI: 10.1097/HJH.0000000000002922; PMID: 34269334 | 强化家庭血压监测方法、频率、记录、临床沟通和复测建议。 | `knowledge_base/sources/downloads/esh_2021_home_bp_monitoring_position_paper.pdf` | `"Home blood pressure monitoring: methodology, clinical relevance and practical application" pdf`; `"10.1097/HJH.0000000000002922" pdf`; `"European Society of Hypertension" "home blood pressure monitoring" "2021 position paper"` |
| esh_2010_international_protocol_validation | P2 | European Society of Hypertension International Protocol revision 2010 for the validation of blood pressure measuring devices in adults | DOI: 10.1097/MBP.0b013e3283360e98 | 设备验证历史协议，可补充 validated devices/validation standard 背景。 | `knowledge_base/sources/downloads/esh_2010_international_protocol_validation.pdf` | `"European Society of Hypertension International Protocol revision 2010" pdf`; `"10.1097/MBP.0b013e3283360e98" pdf`; `"validation of blood pressure measuring devices in adults"` |

## Batch 2 PPG / 光学信号质量补充清单

| item_id | priority | exact_title | DOI / PMID / PMCID | why_needed | desired_save_as | suggested_queries |
| --- | --- | --- | --- | --- | --- | --- |
| fine_2021_ppg_sources_of_inaccuracy | P1 | Sources of Inaccuracy in Photoplethysmography for Continuous Cardiovascular Monitoring | DOI: 10.3390/bios11040126 | 直接覆盖肤色、肥胖、年龄、性别、体温、运动伪影、环境光、接触压力等 PPG 误差来源；非常适合补 signal_quality。 | `knowledge_base/sources/downloads/fine_2021_ppg_sources_of_inaccuracy.pdf` | `"Sources of Inaccuracy in Photoplethysmography for Continuous Cardiovascular Monitoring" pdf`; `"10.3390/bios11040126" pdf`; `site:mdpi.com "bios11040126" pdf` |
| tamura_2014_wearable_ppg_sensors_past_present | P2 | Wearable Photoplethysmographic Sensors—Past and Present | DOI: 10.3390/electronics3020282 | 补可穿戴 PPG 传感器类型、佩戴位置、应用与限制的经典开放综述。 | `knowledge_base/sources/downloads/tamura_2014_wearable_ppg_sensors_past_present.pdf` | `"Wearable Photoplethysmographic Sensors—Past and Present" pdf`; `"10.3390/electronics3020282" pdf`; `site:mdpi.com "electronics3020282" pdf` |
| sun_2016_ppg_revisited_contact_noncontact_imaging | P2 | Photoplethysmography Revisited: From Contact to Noncontact, From Point to Imaging | DOI: 10.1109/TBME.2015.2476337; PMID: 26390439 | 支撑接触式/非接触式/iPPG 的基本差异，适合解释摄像头 PPG 对光照、运动和成像条件敏感。 | `knowledge_base/sources/downloads/sun_2016_ppg_revisited_contact_noncontact_imaging.pdf` | `"Photoplethysmography Revisited: From Contact to Noncontact, From Point to Imaging" pdf`; `"10.1109/TBME.2015.2476337" pdf`; `"Sun Thakor Photoplethysmography Revisited"` |
| frontiers_2019_ppg_measurement_site_waveform | P2 | Quantitative Comparison of Photoplethysmographic Waveform Characteristics: Effect of Measurement Site | DOI: 10.3389/fphys.2019.00198; PMID: 30890959 | 支撑“测量部位/传感器位置会影响 PPG 波形特征”，适合 sensor_position 解释。 | `knowledge_base/sources/downloads/frontiers_2019_ppg_measurement_site_waveform.pdf` | `"Quantitative Comparison of Photoplethysmographic Waveform Characteristics" pdf`; `"10.3389/fphys.2019.00198" pdf`; `site:frontiersin.org "fphys.2019.00198" pdf` |
| tamura_2019_current_progress_ppg_spo2 | P3 | Current progress of photoplethysmography and SpO2 for health monitoring | DOI: 10.1007/s13534-019-00097-w; PMID: 30956878; PMCID: PMC6431353 | 补 PPG/SpO2、可穿戴与成像 PPG 进展和局限的开放综述。 | `knowledge_base/sources/downloads/tamura_2019_current_progress_ppg_spo2.pdf` | `"Current progress of photoplethysmography and SpO2 for health monitoring" pdf`; `"10.1007/s13534-019-00097-w" pdf`; `PMCID PMC6431353` |
| lee_2021_skin_compatible_wearable_ppg | P3 | Systematic Review on Human Skin-Compatible Wearable Photoplethysmography Sensors | DOI: 10.3390/app11052313 | 补皮肤贴合、柔性传感器、皮肤兼容性和长期佩戴稳定性；只用于 research_background/signal_quality。 | `knowledge_base/sources/downloads/lee_2021_skin_compatible_wearable_ppg.pdf` | `"Systematic Review on Human Skin-Compatible Wearable Photoplethysmography Sensors" pdf`; `"10.3390/app11052313" pdf`; `site:mdpi.com "app11052313" pdf` |
| electronics_2023_ppg_wearable_devices_review | P3 | Photoplethysmography in Wearable Devices: A Comprehensive Review of Technological Advances, Current Challenges, and Future Directions | DOI: 10.3390/electronics12132923 | 较新的可穿戴 PPG 综合综述，补当前挑战和未来方向；只用于背景和局限。 | `knowledge_base/sources/downloads/electronics_2023_ppg_wearable_devices_review.pdf` | `"Photoplethysmography in Wearable Devices" "Comprehensive Review" pdf`; `"10.3390/electronics12132923" pdf`; `site:mdpi.com "electronics12132923" pdf` |

## 不要重复查找

上一批已经要求查找，或本地已经下载归档；请不要在本批重复：

- `aha_ama_2020_smbp_policy_statement`
- `chandrasekhar_2020_contact_pressure_cuffless_bp`
- `shirbani_2020_ambient_light_skin_tone_vpg`
- `teng_2004_contact_force_ppg`
- `esc_2024_bp_guideline_key_points`
- `chinese_hypertension_guideline_2024_revision_chl_bha`
- `ada_2026_standards_cvd_bp`
- `esh_2023_hypertension_guideline`
- `esc_2024_elevated_bp_hypertension_guideline`
- `chinese_2019_home_bp_monitoring_guideline`
- `charlton_2022_wearable_ppg_cardiovascular_review`
- `allen_2007_ppg_clinical_measurement_review`
- `bent_2020_wearable_optical_hr_inaccuracy`
- `aha_prevent_equations_circulation_2024`

