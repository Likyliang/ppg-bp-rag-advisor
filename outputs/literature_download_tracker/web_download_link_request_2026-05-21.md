# 给网页版的文献下载链接检索任务

请按下面清单逐条查找**合法公开下载链接**或**官方落地页链接**。目标是让我手动逐篇下载 PDF，然后放入本地 RAG 项目。请不要提供 Sci-Hub、盗版镜像、需要账号密码/cookie/token 的链接。

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

- 优先官方页面、PubMed/PMC、出版社页面、大学/机构开放仓储、指南组织官网。
- 如果只有 HTML 全文、没有 PDF，也请给 HTML 落地页并标记 `official_page_only`。
- 如果页面被 Cloudflare、recaptcha、403、出版社机器人保护挡住，请标记 `blocked` 或 `institution_required`，不要绕过限制。
- 如果找到的是评论、新闻、DOI 利益声明、摘要页、药物治疗短文，而不是目标全文，请不要当作完成。
- 每条只需给 1-3 个最可信链接，不要给泛泛搜索结果页。

## 必找清单

| item_id | priority | exact_title | DOI / PMID | why_needed | known_failed_reason | desired_save_as | suggested_queries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aha_ama_2020_smbp_policy_statement | P1 | Self-Measured Blood Pressure Monitoring at Home: A Joint Policy Statement From the American Heart Association and American Medical Association | DOI: 10.1161/CIR.0000000000000803 | 家庭自测血压流程、复测建议、医生沟通建议。 | AHA Journals PDF and ePDF returned HTTP 403 in curl. | `knowledge_base/sources/downloads/aha_ama_2020_smbp_policy_statement.pdf` | `"Self-Measured Blood Pressure Monitoring at Home" "CIR.0000000000000803" pdf`; `"Self-Measured Blood Pressure Monitoring at Home" "American Heart Association" "American Medical Association"` |
| chandrasekhar_2020_contact_pressure_cuffless_bp | P1 | PPG Sensor Contact Pressure Should Be Taken Into Account for Cuff-Less Blood Pressure Measurement | DOI: 10.1109/TBME.2020.2976989; PMID: 32142414 | 支撑 PPG 传感器接触压力会影响无袖带血压估算。 | IEEE stamp page returned bot-protection HTML; DOI attempt had SSL/connect failure. | `knowledge_base/sources/downloads/chandrasekhar_2020_contact_pressure_cuffless_bp.pdf` | `"PPG Sensor Contact Pressure Should Be Taken Into Account" pdf`; `"10.1109/TBME.2020.2976989" pdf`; `"Chandrasekhar" "contact pressure" "cuff-less blood pressure"` |
| shirbani_2020_ambient_light_skin_tone_vpg | P2 | Effect of Ambient Lighting and Skin Tone on Estimation of Heart Rate and Pulse Transit Time from Video Plethysmography | DOI: 10.1109/EMBC44109.2020.9176731; PMID: 33018549 | 支撑视频/摄像头 PPG 中环境光、肤色对心率/PTT 估计影响。 | IEEE stamp/DOI pages returned bot-protection HTML, not PDF. | `knowledge_base/sources/downloads/shirbani_2020_ambient_light_skin_tone_vpg.pdf` | `"Effect of Ambient Lighting and Skin Tone" "Video Plethysmography" pdf`; `"10.1109/EMBC44109.2020.9176731" pdf`; `"Ambient Lighting and Skin Tone" "Pulse Transit Time"` |
| teng_2004_contact_force_ppg | P2 | The effect of contacting force on photoplethysmographic signals | DOI: 10.1088/0967-3334/25/5/020; PMID: 15535195 | 支撑 PPG 探头接触力/按压力影响波形。 | IOP/DOI pages returned Radware Bot Manager Captcha HTML, not PDF. | `knowledge_base/sources/downloads/teng_2004_contact_force_ppg.pdf` | `"The effect of contacting force on photoplethysmographic signals" pdf`; `"10.1088/0967-3334/25/5/020" pdf`; `"Teng" "contacting force" photoplethysmographic signals` |

## 可选清单

这些不是当前最急，但如果能找到可靠链接也请给出。

| item_id | priority | exact_title | DOI / PMID | note | known_failed_reason | desired_save_as | suggested_queries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| esc_2024_bp_guideline_key_points | P3 | 2024 ESC Guidelines for the management of elevated blood pressure and hypertension: Essential Messages | n/a | 已经有 ESC 2024 full guideline PDF；这里只缺 ESC 官方 Essential Messages PDF。不要把 DOI 声明报告或 pharmacotherapy 短文误当作此项。 | ESC static PDF returned HTTP 403. | `knowledge_base/sources/downloads/esc_2024_bp_guideline_key_points.pdf` | `"Essential Messages_2024_HTN.pdf"`; `site:escardio.org "Essential Messages" "2024" "HTN"` |
| chinese_hypertension_guideline_2024_revision_chl_bha | P3 | 中国高血压防治指南（2024年修订版）CHL-BHA mirror | n/a | 本项目已有 SciOpen 版本 PDF 和摘要；这个只是 CHL-BHA 镜像备份，找不到也可以跳过。 | CHL-BHA direct PDF connection reset. | `knowledge_base/sources/downloads/chinese_hypertension_guideline_2024_revision_chl_bha.pdf` | `"中国高血压防治指南" "2024年修订版" filetype:pdf`; `site:chl-bha.org.cn "中国高血压防治指南" "2024"` |

## 不要重复查找，已经下载归档

这些已经在本地有 PDF，不需要再给链接：

- ADA 2026 cardiovascular disease and risk management: `ada_2026_standards_cvd_bp.pdf`
- ESH 2023 guideline: `esh_2023_hypertension_guideline.pdf`
- ESC 2024 full guideline: `esc_2024_elevated_bp_hypertension_guideline.pdf`
- 2019 中国家庭血压监测指南: `chinese_2019_home_bp_monitoring_guideline.pdf`
- Charlton 2022 wearable PPG review: `charlton_2022_wearable_ppg_cardiovascular_review.pdf`
- Allen 2007 PPG clinical physiological measurement: `allen_2007_ppg_clinical_measurement_review.pdf`
- Bent 2020 wearable optical heart-rate sensor inaccuracy: `bent_2020_wearable_optical_hr_inaccuracy.pdf`
- AHA PREVENT equations: `aha_prevent_equations_circulation_2024.pdf`

