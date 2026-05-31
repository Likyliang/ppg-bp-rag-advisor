# 当前入库文档清单（组会展示版）

适用场景：2026-05-28 组会展示当前高血压 RAG demo 的知识库覆盖情况。

## 总览

- 正式摘要入库来源：126 个
- 正式 KB chunks：584 个
- 本地全文 PDF 向量来源：62 个
- 本地全文 PDF 页数：2220 页
- 本地全文细切 chunks：13168 个
- 中国官方/准官方来源：16 个
- 本地向量后端：local_hashing_vectors，维度 384

说明：正式入库来源用于报告引用；本地 PDF 全文 chunks 用于 demo 检索调试，原始 PDF 和全文抽取文本不提交。

## 按主题统计

| 主题 | 中文说明 | 数量 |
|---|---|---:|
| `bp_categories` | 血压分类/阈值参考 | 8 |
| `cuffless_ppg_limitations` | 无袖带/PPG 局限 | 9 |
| `disclaimer` | 免责声明/安全规则 | 3 |
| `emergency` | 急症/危险信号 | 6 |
| `home_bp_monitoring` | 家庭血压监测/规范测量 | 23 |
| `lifestyle` | 生活方式 | 22 |
| `measurement_quality` | PPG/测量质量 | 27 |
| `medication_safety` | 用药安全边界 | 5 |
| `special_population` | 特殊人群 | 16 |
| `validated_devices` | 验证设备/设备注册表 | 7 |

## 按证据等级统计

| evidence_class | 中文说明 | 数量 |
|---|---|---:|
| `guideline` | 指南 | 18 |
| `official_health_education` | 官方健康教育 | 58 |
| `patient_education` | 患者教育 | 2 |
| `research_context` | 研究背景 | 10 |
| `review` | 综述 | 18 |
| `safety_rule` | 项目安全规则 | 9 |
| `scientific_statement` | 科学声明 | 6 |
| `validation_standard` | 验证标准/监管 | 5 |

## 中国官方/准官方来源清单

| # | 来源 ID | 标题 | 机构 | 年份 | 主题 | 证据等级 | 链接 |
|---:|---|---|---|---:|---|---|---|
| 1 | `chinese_hypertension_guideline_2024_catalog` | Chinese Guidelines for the Prevention and Treatment of Hypertension (2024 revision) | Chinese guideline authors | 2025 | 血压分类/阈值参考 | 指南 | [link](https://www.sciopen.com/article/10.26599/1671-5411.2025.01.008) |
| 2 | `chinese_2011_bp_measurement_guideline` | 中国血压测量指南 | 中国高血压联盟 / 国家心血管病中心 | 2011 | 家庭血压监测/规范测量 | 指南 | [link](https://www.nccd.org.cn/UploadFile/201504/20150416170041172172.pdf) |
| 3 | `healthy_china_cvd_action_2023_2030` | 健康中国行动—心脑血管疾病防治行动实施方案（2023—2030年） | 国家卫生健康委等14部门 | 2023 | 家庭血压监测/规范测量 | 官方健康教育 | [link](https://www.gov.cn/zhengce/zhengceku/202311/content_6915365.htm) |
| 4 | `nccd_2020_primary_hypertension_management_guideline` | 国家基层高血压防治管理指南（2020版） | 国家心血管病中心 / 国家基本公共卫生服务项目基层高血压管理办公室 | 2020 | 家庭血压监测/规范测量 | 指南 | [link](https://www.nccd.org.cn/Sites/Uploaded/File/2021/3/%E5%9B%BD%E5%AE%B6%E5%9F%BA%E5%B1%82%E9%AB%98%E8%A1%80%E5%8E%8B%E9%98%B2%E6%B2%BB%E7%AE%A1%E7%90%86%E6%8C%87%E5%8D%97%202020%E7%89%88.pdf) |
| 5 | `nhc_2017_basic_public_health_service_hypertension_management` | 国家基本公共卫生服务规范（第三版）高血压患者健康管理服务规范 | 原国家卫生计生委 | 2017 | 家庭血压监测/规范测量 | 指南 | [link](https://www.nhc.gov.cn/ewebeditor/uploadfile/2017/04/20170417104506514.pdf) |
| 6 | `nhc_2024_hypertension_day_key_messages` | 2024年全国高血压日宣传要点 | 国家卫生健康委 | 2024 | 家庭血压监测/规范测量 | 官方健康教育 | [link](https://www.nhc.gov.cn/ylyjs/gzdt/202409/bfc23c5086044eb0b4879e58e4df69e1.shtml) |
| 7 | `nhc_2025_primary_care_hypertension_standard_ws_t_872` | 基层医疗卫生机构高血压防治管理标准 WS/T 872-2025 | 国家卫生健康委员会 | 2025 | 家庭血压监测/规范测量 | 指南 | [link](https://www.nhc.gov.cn/fzs/c100048/202509/2f3f7cce449145f8b361e70b3ed4ae9a/files/WS%20T%20872%E2%80%942025-20250930105429913.pdf) |
| 8 | `state_council_chronic_disease_plan_2017_2025` | 中国防治慢性病中长期规划（2017—2025年） | 国务院办公厅 | 2017 | 家庭血压监测/规范测量 | 官方健康教育 | [link](https://www.gov.cn/zhengce/content/2017-02/14/content_5167886.htm) |
| 9 | `chinese_2013_hypertension_patient_education_guideline` | 中国高血压患者教育指南 | 中国高血压患者教育指南编撰委员会 | 2013 | 生活方式 | 患者教育 | [link](https://www.nccd.org.cn/UploadFile/201504/20150418172843860860.pdf) |
| 10 | `healthy_china_2019_2030_action` | 健康中国行动（2019-2030年） | 健康中国行动推进委员会 | 2019 | 生活方式 | 官方健康教育 | [link](https://www.nhc.gov.cn/cms-search/downFiles/470339610aea4a7887d0810b4c00c9bd.pdf) |
| 11 | `nhc_2023_adult_hypertension_dietary_guideline` | 成人高血压食养指南（2023年版） | 国家卫生健康委办公厅 | 2023 | 生活方式 | 指南 | [link](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) |
| 12 | `nhc_2024_chinese_health_literacy_basic_skills` | 中国公民健康素养——基本知识与技能（2024年版） | 国家卫生健康委办公厅 | 2024 | 生活方式 | 官方健康教育 | [link](https://www.nhc.gov.cn/xcs/c100123/202405/73a4927142f34152abed875634a3c13b.shtml) |
| 13 | `nhc_2024_hypertension_nutrition_exercise_guidance` | 高血压营养和运动指导原则（2024年版） | 国家卫生健康委办公厅 | 2024 | 生活方式 | 官方健康教育 | [link](https://app.www.gov.cn/govdata/gov/202407/02/516820/article.html) |
| 14 | `nhc_ws_t_430_2013_hypertension_dietary_guidance` | 高血压患者膳食指导 WS/T 430-2013 | 国家卫生健康委员会 | 2013 | 生活方式 | 验证标准/监管 | [link](https://www.nhc.gov.cn/wjw/yingyang/201308/cce5017663e6457d98db7be683c36b4c.shtml) |
| 15 | `chinese_2023_elderly_hypertension_management_guideline` | 中国老年高血压管理指南2023 | 中国老年医学学会高血压分会 / 北京高血压防治协会 | 2023 | 特殊人群 | 指南 | [link](https://medtion-image.medtion.com/uploads/1/file/public/202312/20231222151125_hjo32b9lsf.pdf) |
| 16 | `chinese_2025_secondary_hypertension_screening_consensus` | 继发性高血压筛查和诊断中国专家共识 | 中国高血压联盟等 | 2025 | 特殊人群 | 指南 | [link](https://bookcafe.yuntsg.com/ueditor/jsp/upload/file/20260117/1768636681085056202.pdf) |

## 来源类型 Top 15

| source_type | 数量 |
|---|---:|
| `patient_education` | 34 |
| `local_safety_rule` | 9 |
| `review_pdf` | 9 |
| `guideline` | 6 |
| `patient_education_pdf` | 5 |
| `device_validation_registry` | 4 |
| `research_article_pdf` | 3 |
| `systematic_review_pdf` | 3 |
| `guideline_summary` | 2 |
| `peer_reviewed_review` | 2 |
| `patient_instruction_pdf` | 2 |
| `scientific_statement_pdf` | 2 |
| `safety_education` | 1 |
| `scientific_statement` | 1 |
| `bibliographic_record` | 1 |

## 正式摘要入库来源

| # | 主题 | 来源 ID | 标题 | 机构 | 年份 | 证据等级 | 链接 |
|---:|---|---|---|---|---:|---|---|
| 1 | 血压分类/阈值参考 | `acc_aha_2025_full_guideline_record` | 2025 AHA ACC Guideline for the Prevention Detection Evaluation and Management of High Blood Pressure in Adults | American Heart Association / American College of Cardiology | 2025 | 指南 | [link](https://www.ahajournals.org/doi/10.1161/CIR.0000000000001356) |
| 2 | 血压分类/阈值参考 | `aha_2025_bp_guideline_top_things` | 2025 High Blood Pressure Guideline - Top Things to Know | American Heart Association | 2025 | 指南 | [link](https://professional.heart.org/en/science-news/2025-high-blood-pressure-guideline/top-things-to-know) |
| 3 | 血压分类/阈值参考 | `aha_understanding_bp_readings_public` | Understanding Blood Pressure Readings | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings) |
| 4 | 血压分类/阈值参考 | `chinese_hypertension_guideline_2024_catalog` | Chinese Guidelines for the Prevention and Treatment of Hypertension (2024 revision) | Chinese guideline authors | 2025 | 指南 | [link](https://www.sciopen.com/article/10.26599/1671-5411.2025.01.008) |
| 5 | 血压分类/阈值参考 | `esc_2024_bp_guideline_key_points` | 2024 ESC Guidelines for Elevated Blood Pressure and Hypertension - Key Points | European Society of Cardiology / American College of Cardiology summary | 2024 | 指南 | [link](https://www.acc.org/Latest-in-Cardiology/ten-points-to-remember/2024/09/05/14/11/2024-esc-guidelines-for-bp-esc-2024) |
| 6 | 血压分类/阈值参考 | `nhlbi_high_blood_pressure` | High Blood Pressure | National Heart, Lung, and Blood Institute | 2026 | 官方健康教育 | [link](https://www.nhlbi.nih.gov/health/high-blood-pressure) |
| 7 | 血压分类/阈值参考 | `who_global_hypertension_report_2023` | Global report on hypertension: the race against a silent killer | World Health Organization | 2023 | 官方健康教育 | [link](https://iris.who.int/handle/10665/372896) |
| 8 | 血压分类/阈值参考 | `who_hypertension_fact_sheet` | Hypertension fact sheet | World Health Organization | 2026 | 官方健康教育 | [link](https://www.who.int/news-room/fact-sheets/detail/hypertension) |
| 9 | 无袖带/PPG 局限 | `aha_cuffless_bp_scientific_statement` | Cuffless Devices for the Measurement of Blood Pressure | American Heart Association | 2025 | 科学声明 | [link](https://professional.heart.org/en/science-news/cuffless-devices-for-the-measurement-of-blood-pressure/top-things-to-know) |
| 10 | 无袖带/PPG 局限 | `bradley_2022_cuffless_bp_devices_review` | Cuffless Blood Pressure Devices | American Journal of Hypertension | 2022 | 综述 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC9088838/) |
| 11 | 无袖带/PPG 局限 | `fda_cuffless_nibp_draft_guidance` | Cuffless Non-invasive Blood Pressure Measuring Devices - Clinical Performance Testing and Evaluation | U.S. Food and Drug Administration | 2026 | 验证标准/监管 | [link](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cuffless-non-invasive-blood-pressure-measuring-devices-clinical-performance-testing-and-evaluation) |
| 12 | 无袖带/PPG 局限 | `mukkamala_2015_ptt_bp_monitoring_theory_practice` | Toward Ubiquitous Blood Pressure Monitoring via Pulse Transit Time - Theory and Practice | IEEE Transactions on Biomedical Engineering | 2015 | 综述 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4515215/) |
| 13 | 无袖带/PPG 局限 | `mukkamala_2017_ptt_calibration_error_limits` | Toward Ubiquitous Blood Pressure Monitoring via Pulse Transit Time - Predictions on Maximum Calibration Period and Acceptable Error Limits | IEEE Transactions on Biomedical Engineering | 2017 | 研究背景 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6014705/) |
| 14 | 无袖带/PPG 局限 | `ode_2020_continuous_ambulatory_bp_ptt_data_acquisition` | Towards Continuous and Ambulatory Blood Pressure Monitoring - Methods for Efficient Data Acquisition for Pulse Transit Time Estimation | Sensors | 2020 | 研究背景 | [link](https://www.mdpi.com/1424-8220/20/24/7106) |
| 15 | 无袖带/PPG 局限 | `parati_2026_esc_cuffless_bp_monitoring_statement` | Cuffless Blood Pressure Monitoring Devices - Technical Foundations and Clinical Implications | European Society of Cardiology | 2026 | 科学声明 | [link](https://academic.oup.com/eurjpc/advance-article/doi/10.1093/eurjpc/zwag058/8497606) |
| 16 | 无袖带/PPG 局限 | `pubmed_cuffless_bp_review_41460057` | Cuffless blood pressure measurement narrative review - PubMed record | PubMed | 2025 | 综述 | [link](https://pubmed.ncbi.nlm.nih.gov/41460057/) |
| 17 | 无袖带/PPG 局限 | `pubmed_cuffless_bp_statement_41376592` | Cuffless Devices for the Measurement of Blood Pressure - PubMed record | PubMed / American Heart Association | 2025 | 科学声明 | [link](https://pubmed.ncbi.nlm.nih.gov/41376592/) |
| 18 | 免责声明/安全规则 | `local_disclaimer_rule` | Required disclaimer rule | project | 2026 | 项目安全规则 |  |
| 19 | 免责声明/安全规则 | `local_evidence_quality_rule` | Evidence quality and citation safety rule | project | 2026 | 项目安全规则 |  |
| 20 | 免责声明/安全规则 | `local_kb_governance_rule` | Knowledge base governance rule | project | 2026 | 项目安全规则 |  |
| 21 | 急症/危险信号 | `aha_hypertensive_crisis_public` | Hypertensive Crisis and Emergency Warning | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings) |
| 22 | 急症/危险信号 | `cdc_heart_disease_symptoms` | Heart Attack Symptoms Risk and Recovery | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/heart-disease/about/heart-attack.html) |
| 23 | 急症/危险信号 | `cdc_stroke_signs` | Stroke Signs and Symptoms | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/stroke/signs-symptoms/index.html) |
| 24 | 急症/危险信号 | `local_hypertensive_emergency_rule` | Hypertensive emergency safety rule | project | 2026 | 项目安全规则 |  |
| 25 | 急症/危险信号 | `medlineplus_hypertensive_crisis` | Hypertensive crisis | MedlinePlus | 2026 | 官方健康教育 | [link](https://medlineplus.gov/ency/article/000491.htm) |
| 26 | 急症/危险信号 | `nhs_high_blood_pressure` | High blood pressure hypertension | National Health Service | 2026 | 官方健康教育 | [link](https://www.nhs.uk/conditions/high-blood-pressure-hypertension/) |
| 27 | 家庭血压监测/规范测量 | `aha_ama_2020_smbp_policy_statement` | Self-Measured Blood Pressure Monitoring at Home: A Joint Policy Statement From the American Heart Association and American Medical Association | American Heart Association / American Medical Association | 2020 | 科学声明 | [link](https://pubmed.ncbi.nlm.nih.gov/32567342/) |
| 28 | 家庭血压监测/规范测量 | `aha_home_bp_measurement_instructions` | Home Blood Pressure Measurement Instructions | American Heart Association | 2025 | 官方健康教育 | [link](https://www.heart.org/-/media/files/health-topics/high-blood-pressure/how_to_measure_your_blood_pressure_letter_size.pdf) |
| 29 | 家庭血压监测/规范测量 | `aha_home_bp_monitoring_public` | Home Blood Pressure Monitoring | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings/monitoring-your-blood-pressure-at-home) |
| 30 | 家庭血压监测/规范测量 | `ama_target_bp_measure_accurately` | Target BP - Measure Accurately | American Medical Association / American Heart Association | 2026 | 官方健康教育 | [link](https://targetbp.org/tools-downloads/) |
| 31 | 家庭血压监测/规范测量 | `cdc_managing_my_blood_pressure_questions` | Managing My Blood Pressure - Questions to Ask My Doctor | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/heart-disease/docs/Managing_My_Blood_Pressure.pdf) |
| 32 | 家庭血压监测/规范测量 | `cdc_measure_blood_pressure_home` | Measure Your Blood Pressure | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/high-blood-pressure/measure/index.html) |
| 33 | 家庭血压监测/规范测量 | `cdc_million_hearts_smbp_action_guide` | Million Hearts Self-Measured Blood Pressure Monitoring: Action Steps for Clinicians | Centers for Disease Control and Prevention / Million Hearts | 2014 | 官方健康教育 | [link](https://stacks.cdc.gov/view/cdc/251870) |
| 34 | 家庭血压监测/规范测量 | `cdc_self_measured_bp_monitoring` | Self-Measured Blood Pressure Monitoring | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/high-blood-pressure/php/toolkits/self-measured-blood-pressure-monitoring.html) |
| 35 | 家庭血压监测/规范测量 | `chinese_2011_bp_measurement_guideline` | 中国血压测量指南 | 中国高血压联盟 / 国家心血管病中心 | 2011 | 指南 | [link](https://www.nccd.org.cn/UploadFile/201504/20150416170041172172.pdf) |
| 36 | 家庭血压监测/规范测量 | `esh_2021_home_bp_monitoring_position_paper` | Home blood pressure monitoring - methodology clinical relevance and practical application | European Society of Hypertension | 2021 | 科学声明 | [link](https://sussex.figshare.com/articles/journal_contribution/Home_blood_pressure_monitoring_Methodology_clinical_relevance_and_practical_application_A_2021_position_paper_by_the_Working_Group_on_Blood_Pressure_Monitoring_and_Cardiovascular_Variability_of_the_European_Society_of_Hypertension/29269019) |
| 37 | 家庭血压监测/规范测量 | `esh_2023_hypertension_guideline` | 2023 ESH Guidelines for the management of arterial hypertension | European Society of Hypertension | 2023 | 指南 | [link](https://www.eshonline.org/guidelines/2023-guidelines/) |
| 38 | 家庭血压监测/规范测量 | `healthy_china_cvd_action_2023_2030` | 健康中国行动—心脑血管疾病防治行动实施方案（2023—2030年） | 国家卫生健康委等14部门 | 2023 | 官方健康教育 | [link](https://www.gov.cn/zhengce/zhengceku/202311/content_6915365.htm) |
| 39 | 家庭血压监测/规范测量 | `ish_2020_global_guideline` | 2020 International Society of Hypertension Global Hypertension Practice Guidelines | International Society of Hypertension | 2020 | 指南 | [link](https://ish-world.com/global-hypertension-practice-guidelines/) |
| 40 | 家庭血压监测/规范测量 | `medlineplus_measuring_blood_pressure` | Blood pressure measurement | MedlinePlus | 2026 | 官方健康教育 | [link](https://medlineplus.gov/ency/article/007490.htm) |
| 41 | 家庭血压监测/规范测量 | `muntner_2019_aha_bp_measurement_scientific_statement` | Measurement of Blood Pressure in Humans - A Scientific Statement From the American Heart Association | American Heart Association | 2019 | 科学声明 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC11409525/) |
| 42 | 家庭血压监测/规范测量 | `nccd_2020_primary_hypertension_management_guideline` | 国家基层高血压防治管理指南（2020版） | 国家心血管病中心 / 国家基本公共卫生服务项目基层高血压管理办公室 | 2020 | 指南 | [link](https://www.nccd.org.cn/Sites/Uploaded/File/2021/3/%E5%9B%BD%E5%AE%B6%E5%9F%BA%E5%B1%82%E9%AB%98%E8%A1%80%E5%8E%8B%E9%98%B2%E6%B2%BB%E7%AE%A1%E7%90%86%E6%8C%87%E5%8D%97%202020%E7%89%88.pdf) |
| 43 | 家庭血压监测/规范测量 | `nhc_2017_basic_public_health_service_hypertension_management` | 国家基本公共卫生服务规范（第三版）高血压患者健康管理服务规范 | 原国家卫生计生委 | 2017 | 指南 | [link](https://www.nhc.gov.cn/ewebeditor/uploadfile/2017/04/20170417104506514.pdf) |
| 44 | 家庭血压监测/规范测量 | `nhc_2024_hypertension_day_key_messages` | 2024年全国高血压日宣传要点 | 国家卫生健康委 | 2024 | 官方健康教育 | [link](https://www.nhc.gov.cn/ylyjs/gzdt/202409/bfc23c5086044eb0b4879e58e4df69e1.shtml) |
| 45 | 家庭血压监测/规范测量 | `nhc_2025_primary_care_hypertension_standard_ws_t_872` | 基层医疗卫生机构高血压防治管理标准 WS/T 872-2025 | 国家卫生健康委员会 | 2025 | 指南 | [link](https://www.nhc.gov.cn/fzs/c100048/202509/2f3f7cce449145f8b361e70b3ed4ae9a/files/WS%20T%20872%E2%80%942025-20250930105429913.pdf) |
| 46 | 家庭血压监测/规范测量 | `nhlbi_self_measured_blood_pressure_fact_sheet` | Self-Measured Blood Pressure | National Heart Lung and Blood Institute | 2023 | 官方健康教育 | [link](https://www.nhlbi.nih.gov/resources/self-measured-blood-pressure-fact-sheet) |
| 47 | 家庭血压监测/规范测量 | `nice_ng136_hypertension` | Hypertension in adults - diagnosis and management | National Institute for Health and Care Excellence | 2023 | 指南 | [link](https://www.nice.org.uk/guidance/ng136/chapter/1-Recommendations) |
| 48 | 家庭血压监测/规范测量 | `state_council_chronic_disease_plan_2017_2025` | 中国防治慢性病中长期规划（2017—2025年） | 国务院办公厅 | 2017 | 官方健康教育 | [link](https://www.gov.cn/zhengce/content/2017-02/14/content_5167886.htm) |
| 49 | 家庭血压监测/规范测量 | `uspstf_hypertension_screening_adults` | Hypertension in Adults - Screening | U.S. Preventive Services Task Force | 2021 | 指南 | [link](https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/hypertension-in-adults-screening) |
| 50 | 生活方式 | `aha_getting_active_bp` | Getting Active to Control High Blood Pressure | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure/getting-active-to-control-high-blood-pressure) |
| 51 | 生活方式 | `aha_life_essential_8_manage_blood_pressure` | Life's Essential 8 - How to Manage Blood Pressure | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/-/media/Healthy-Living-Files/LE8-Fact-Sheets/LE8_How_To_Manage_Blood_Pressure.pdf) |
| 52 | 生活方式 | `aha_lifestyle_manage_bp` | Changes You Can Make to Manage High Blood Pressure | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure) |
| 53 | 生活方式 | `aha_reduce_high_blood_pressure_answers_by_heart` | How Can I Lower High Blood Pressure? | American Heart Association | 2025 | 官方健康教育 | [link](https://www.heart.org/-/media/files/health-topics/answers-by-heart/how-can-i-reduce-high-blood-pressure.pdf) |
| 54 | 生活方式 | `aha_sodium_salt` | Sodium and Salt | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/healthy-living/healthy-eating/eat-smart/sodium/sodium-and-salt) |
| 55 | 生活方式 | `aha_steps_to_improve_high_bp` | Simple Steps to Improve Your High Blood Pressure | American Heart Association | 2025 | 官方健康教育 | [link](https://www.heart.org/-/media/Files/Health-Topics/High-Blood-Pressure/Steps-To-Improve-High-BP.pdf) |
| 56 | 生活方式 | `aha_stress_management` | Managing Stress to Control High Blood Pressure | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure/managing-stress-to-control-high-blood-pressure) |
| 57 | 生活方式 | `aha_weight_bp` | Managing Weight to Control High Blood Pressure | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure/managing-weight-to-control-high-blood-pressure) |
| 58 | 生活方式 | `cdc_high_bp_risk_factors` | High Blood Pressure Risk Factors | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/high-blood-pressure/risk-factors/index.html) |
| 59 | 生活方式 | `cdc_physical_activity_basics` | Physical Activity Basics | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/physical-activity-basics/) |
| 60 | 生活方式 | `cdc_prevent_high_blood_pressure` | Prevent High Blood Pressure | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/high-blood-pressure/prevention/index.html) |
| 61 | 生活方式 | `cdc_quit_smoking` | How to Quit Smoking | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/tobacco/campaign/tips/quit-smoking/) |
| 62 | 生活方式 | `chinese_2013_hypertension_patient_education_guideline` | 中国高血压患者教育指南 | 中国高血压患者教育指南编撰委员会 | 2013 | 患者教育 | [link](https://www.nccd.org.cn/UploadFile/201504/20150418172843860860.pdf) |
| 63 | 生活方式 | `healthy_china_2019_2030_action` | 健康中国行动（2019-2030年） | 健康中国行动推进委员会 | 2019 | 官方健康教育 | [link](https://www.nhc.gov.cn/cms-search/downFiles/470339610aea4a7887d0810b4c00c9bd.pdf) |
| 64 | 生活方式 | `medlineplus_high_blood_pressure` | High Blood Pressure | MedlinePlus | 2026 | 官方健康教育 | [link](https://medlineplus.gov/highbloodpressure.html) |
| 65 | 生活方式 | `nhc_2023_adult_hypertension_dietary_guideline` | 成人高血压食养指南（2023年版） | 国家卫生健康委办公厅 | 2023 | 指南 | [link](https://www.nhc.gov.cn/sps/c100088/202301/f01895a06c5349ef999f25da833c166d.shtml) |
| 66 | 生活方式 | `nhc_2024_chinese_health_literacy_basic_skills` | 中国公民健康素养——基本知识与技能（2024年版） | 国家卫生健康委办公厅 | 2024 | 官方健康教育 | [link](https://www.nhc.gov.cn/xcs/c100123/202405/73a4927142f34152abed875634a3c13b.shtml) |
| 67 | 生活方式 | `nhc_2024_hypertension_nutrition_exercise_guidance` | 高血压营养和运动指导原则（2024年版） | 国家卫生健康委办公厅 | 2024 | 官方健康教育 | [link](https://app.www.gov.cn/govdata/gov/202407/02/516820/article.html) |
| 68 | 生活方式 | `nhc_ws_t_430_2013_hypertension_dietary_guidance` | 高血压患者膳食指导 WS/T 430-2013 | 国家卫生健康委员会 | 2013 | 验证标准/监管 | [link](https://www.nhc.gov.cn/wjw/yingyang/201308/cce5017663e6457d98db7be683c36b4c.shtml) |
| 69 | 生活方式 | `nhlbi_dash_lowering_blood_pressure_guide` | Your Guide to Lowering Your Blood Pressure with DASH | National Heart Lung and Blood Institute | 2026 | 官方健康教育 | [link](https://www.nhlbi.nih.gov/files/docs/public/heart/new_dash.pdf) |
| 70 | 生活方式 | `nia_sleep_health` | A Good Night's Sleep | National Institute on Aging | 2026 | 官方健康教育 | [link](https://www.nia.nih.gov/health/sleep/good-nights-sleep) |
| 71 | 生活方式 | `nih_dash_eating_plan` | DASH Eating Plan | National Heart Lung and Blood Institute | 2026 | 官方健康教育 | [link](https://www.nhlbi.nih.gov/education/dash-eating-plan) |
| 72 | PPG/测量质量 | `allen_2007_ppg_clinical_measurement_review` | Photoplethysmography and its application in clinical physiological measurement | Physiological Measurement | 2007 | 综述 | [link](https://pubmed.ncbi.nlm.nih.gov/17322588/) |
| 73 | PPG/测量质量 | `arguello_prada_2024_ppg_motion_artifact_detection_review` | Machine Learning Applied to Reference Signal-Less Detection of Motion Artifacts in Photoplethysmographic Signals - A Review | Sensors | 2024 | 综述 | [link](https://www.mdpi.com/1424-8220/24/22/7193) |
| 74 | PPG/测量质量 | `bent_2020_wearable_optical_hr_inaccuracy` | Investigating sources of inaccuracy in wearable optical heart rate sensors | npj Digital Medicine | 2020 | 研究背景 | [link](https://www.nature.com/articles/s41746-020-0226-6) |
| 75 | PPG/测量质量 | `cabanas_2022_skin_pigmentation_pulse_oximetry_bibliometric` | Skin Pigmentation Influence on Pulse Oximetry Accuracy - A Systematic Review and Bibliometric Analysis | Sensors | 2022 | 综述 | [link](https://www.mdpi.com/1424-8220/22/9/3402) |
| 76 | PPG/测量质量 | `chandrasekhar_2020_contact_pressure_cuffless_bp` | PPG Sensor Contact Pressure Should Be Taken Into Account for Cuff-Less Blood Pressure Measurement | IEEE Transactions on Biomedical Engineering | 2020 | 研究背景 | [link](https://ieeexplore.ieee.org/document/9016235) |
| 77 | PPG/测量质量 | `charlton_2022_ppg_best_practices` | Establishing best practices in photoplethysmography signal acquisition and processing | Physiological Measurement | 2022 | 综述 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC9136485/) |
| 78 | PPG/测量质量 | `charlton_2022_wearable_ppg_cardiovascular_review` | Wearable Photoplethysmography for Cardiovascular Monitoring | Proceedings of the IEEE | 2022 | 综述 | [link](https://ieeexplore.ieee.org/document/9731763) |
| 79 | PPG/测量质量 | `charlton_2023_wearable_ppg_roadmap` | The 2023 wearable photoplethysmography roadmap | Physiological Measurement | 2023 | 综述 | [link](https://iopscience.iop.org/article/10.1088/1361-6579/acead2) |
| 80 | PPG/测量质量 | `charlton_2025_wrist_ppg_signal_quality` | Determinants of photoplethysmography signal quality at the wrist | PLOS Digital Health | 2025 | 研究背景 | [link](https://journals.plos.org/digitalhealth/article?id=10.1371/journal.pdig.0000585) |
| 81 | PPG/测量质量 | `desquins_2022_ppg_quality_assessment_survey` | A Survey of Photoplethysmography and Imaging Photoplethysmography Quality Assessment Methods | Applied Sciences | 2022 | 综述 | [link](https://www.mdpi.com/2076-3417/12/19/9582) |
| 82 | PPG/测量质量 | `electronics_2023_ppg_wearable_devices_review` | Photoplethysmography in Wearable Devices - A Comprehensive Review of Technological Advances Current Challenges and Future Directions | Electronics | 2023 | 综述 | [link](https://www.mdpi.com/2079-9292/12/13/2923) |
| 83 | PPG/测量质量 | `fda_pulse_oximeter_limitations` | Pulse Oximeter Accuracy and Limitations | U.S. Food and Drug Administration | 2026 | 官方健康教育 | [link](https://www.fda.gov/medical-devices/safety-communications/pulse-oximeter-accuracy-and-limitations-fda-safety-communication) |
| 84 | PPG/测量质量 | `fine_2021_ppg_sources_of_inaccuracy` | Sources of Inaccuracy in Photoplethysmography for Continuous Cardiovascular Monitoring | Biosensors | 2021 | 综述 | [link](https://www.mdpi.com/2079-6374/11/4/126) |
| 85 | PPG/测量质量 | `frontiers_2019_ppg_measurement_site_waveform` | Quantitative Comparison of Photoplethysmographic Waveform Characteristics - Effect of Measurement Site | Frontiers in Physiology | 2019 | 研究背景 | [link](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2019.00198/full) |
| 86 | PPG/测量质量 | `lee_2013_rgb_reflection_ppg_motion_hr` | Comparison between red green and blue light reflection photoplethysmography for heart rate monitoring during motion | IEEE EMBC / Kanazawa University Repository | 2013 | 研究背景 | [link](https://kanazawa-u.repo.nii.ac.jp/record/8500/files/TE-PR-YAMAKOSHI-T-1724.pdf) |
| 87 | PPG/测量质量 | `lee_2021_skin_compatible_wearable_ppg` | Systematic Review on Human Skin-Compatible Wearable Photoplethysmography Sensors | Applied Sciences | 2021 | 综述 | [link](https://www.mdpi.com/2076-3417/11/5/2313) |
| 88 | PPG/测量质量 | `local_capture_environment_rule` | Camera PPG capture environment rule | project | 2026 | 项目安全规则 |  |
| 89 | PPG/测量质量 | `local_confidence_interpretation_rule` | Model confidence interpretation rule | project | 2026 | 项目安全规则 |  |
| 90 | PPG/测量质量 | `local_ppg_signal_quality_rule` | PPG signal quality and confidence safety rule | project | 2026 | 项目安全规则 |  |
| 91 | PPG/测量质量 | `park_2022_ppg_analysis_applications_integrative_review` | Photoplethysmogram Analysis and Applications - An Integrative Review | Frontiers in Physiology | 2022 | 综述 | [link](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2021.808451/full) |
| 92 | PPG/测量质量 | `shi_2022_skin_pigmentation_pulse_oximetry_systematic_review` | The accuracy of pulse oximetry in measuring oxygen saturation by levels of skin pigmentation - a systematic review and meta-analysis | BMC Medicine | 2022 | 综述 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC9377806/) |
| 93 | PPG/测量质量 | `shirbani_2020_ambient_light_skin_tone_vpg` | Effect of Ambient Lighting and Skin Tone on Estimation of Heart Rate and Pulse Transit Time from Video Plethysmography | IEEE EMBC | 2020 | 研究背景 | [link](https://ieeexplore.ieee.org/document/9176731) |
| 94 | PPG/测量质量 | `sjoding_2020_racial_bias_pulse_oximetry` | Racial Bias in Pulse Oximetry Measurement | New England Journal of Medicine | 2020 | 研究背景 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC7808260/) |
| 95 | PPG/测量质量 | `sun_2016_ppg_revisited_contact_noncontact_imaging` | Photoplethysmography Revisited - From Contact to Noncontact From Point to Imaging | IEEE Transactions on Biomedical Engineering | 2016 | 综述 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC4822420/) |
| 96 | PPG/测量质量 | `tamura_2014_wearable_ppg_sensors_past_present` | Wearable Photoplethysmographic Sensors - Past and Present | Electronics | 2014 | 综述 | [link](https://www.mdpi.com/2079-9292/3/2/282) |
| 97 | PPG/测量质量 | `tamura_2019_current_progress_ppg_spo2` | Current progress of photoplethysmography and SpO2 for health monitoring | Biomedical Engineering Letters | 2019 | 综述 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6431353/) |
| 98 | PPG/测量质量 | `teng_2004_contact_force_ppg` | The effect of contacting force on photoplethysmographic signals | Physiological Measurement | 2004 | 研究背景 | [link](https://pubmed.ncbi.nlm.nih.gov/15535195/) |
| 99 | 用药安全边界 | `aha_bp_medicines_patient` | Types of Blood Pressure Medications | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/changes-you-can-make-to-manage-high-blood-pressure/types-of-blood-pressure-medications) |
| 100 | 用药安全边界 | `fda_taking_medicines_safely` | Tips for taking medicines safely | U.S. Food and Drug Administration | 2026 | 官方健康教育 | [link](https://www.fda.gov/drugs/resources-you-drugs/tips-taking-medicines-safely) |
| 101 | 用药安全边界 | `local_medication_safety_rule` | Medication safety boundary rule | project | 2026 | 项目安全规则 |  |
| 102 | 用药安全边界 | `medlineplus_high_bp_medicines` | High blood pressure medicines | MedlinePlus | 2026 | 官方健康教育 | [link](https://medlineplus.gov/highbloodpressuremedicines.html) |
| 103 | 用药安全边界 | `who_2021_hypertension_pharmacological_treatment_guideline` | Guideline for the pharmacological treatment of hypertension in adults | World Health Organization | 2021 | 指南 | [link](https://iris.who.int/bitstreams/f062769d-f075-4a00-87af-0a2106e0bd04/download) |
| 104 | 特殊人群 | `acog_preeclampsia_faq` | Preeclampsia and High Blood Pressure During Pregnancy FAQ | American College of Obstetricians and Gynecologists | 2026 | 官方健康教育 | [link](https://www.acog.org/womens-health/faqs/preeclampsia-and-high-blood-pressure-during-pregnancy) |
| 105 | 特殊人群 | `ada_2026_standards_cvd_bp` | Cardiovascular Disease and Risk Management - Standards of Care in Diabetes 2026 | American Diabetes Association | 2026 | 指南 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12690187/) |
| 106 | 特殊人群 | `ada_diabetes_bp` | Diabetes and High Blood Pressure | American Diabetes Association | 2026 | 官方健康教育 | [link](https://diabetes.org/health-wellness/high-blood-pressure) |
| 107 | 特殊人群 | `aha_diabetes_high_bp` | Diabetes and high blood pressure risk | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/diabetes/why-diabetes-matters/cardiovascular-disease--diabetes) |
| 108 | 特殊人群 | `aha_kidney_disease_high_bp` | High Blood Pressure and Kidney Disease | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/health-threats-from-high-blood-pressure/high-blood-pressure-and-kidney-disease) |
| 109 | 特殊人群 | `aha_pregnancy_blood_pressure_categories` | Blood Pressure Categories for Individuals who are Pregnant | American Heart Association | 2025 | 官方健康教育 | [link](https://www.heart.org/-/media/GRFW-Files/Know-Your-Risk/Maternal-Health/Pregnancy_Blood_Pressure_Categories.pdf?sc_lang=en) |
| 110 | 特殊人群 | `aha_women_high_bp` | Women and high blood pressure | American Heart Association | 2026 | 官方健康教育 | [link](https://www.heart.org/en/health-topics/high-blood-pressure/know-your-risk-factors-for-high-blood-pressure/women-and-high-blood-pressure) |
| 111 | 特殊人群 | `cdc_bp_pregnancy` | High Blood Pressure During Pregnancy | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/high-blood-pressure/about/high-blood-pressure-during-pregnancy.html) |
| 112 | 特殊人群 | `cdc_ckd_risk_factors` | Chronic Kidney Disease Risk Factors | Centers for Disease Control and Prevention | 2026 | 官方健康教育 | [link](https://www.cdc.gov/kidney-disease/risk-factors/index.html) |
| 113 | 特殊人群 | `chinese_2023_elderly_hypertension_management_guideline` | 中国老年高血压管理指南2023 | 中国老年医学学会高血压分会 / 北京高血压防治协会 | 2023 | 指南 | [link](https://medtion-image.medtion.com/uploads/1/file/public/202312/20231222151125_hjo32b9lsf.pdf) |
| 114 | 特殊人群 | `chinese_2025_secondary_hypertension_screening_consensus` | 继发性高血压筛查和诊断中国专家共识 | 中国高血压联盟等 | 2025 | 指南 | [link](https://bookcafe.yuntsg.com/ueditor/jsp/upload/file/20260117/1768636681085056202.pdf) |
| 115 | 特殊人群 | `kdigo_2024_ckd_guideline` | KDIGO 2024 Clinical Practice Guideline for the Evaluation and Management of Chronic Kidney Disease | Kidney Disease - Improving Global Outcomes | 2024 | 指南 | [link](https://kdigo.org/guidelines/ckd-evaluation-and-management/kdigo-2024-ckd-guideline/) |
| 116 | 特殊人群 | `local_special_population_rule` | Special population conservative advice rule | project | 2026 | 项目安全规则 |  |
| 117 | 特殊人群 | `nhlbi_preeclampsia_pregnancy` | Preeclampsia and High Blood Pressure During Pregnancy | National Heart, Lung, and Blood Institute | 2026 | 官方健康教育 | [link](https://www.nhlbi.nih.gov/health/high-blood-pressure/pregnancy) |
| 118 | 特殊人群 | `nia_high_blood_pressure_older_adults` | High Blood Pressure and Older Adults | National Institute on Aging | 2026 | 官方健康教育 | [link](https://www.nia.nih.gov/health/high-blood-pressure/high-blood-pressure-and-older-adults) |
| 119 | 特殊人群 | `nkf_high_bp_ckd` | High Blood Pressure and Chronic Kidney Disease | National Kidney Foundation | 2026 | 患者教育 | [link](https://www.kidney.org/kidney-topics/high-blood-pressure-and-chronic-kidney-disease) |
| 120 | 验证设备/设备注册表 | `aami_esh_iso_2018_universal_validation_standard` | A universal standard for the validation of blood pressure measuring devices | AAMI / European Society of Hypertension / International Organization for Standardization | 2018 | 验证标准/监管 | [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC5796427/) |
| 121 | 验证设备/设备注册表 | `bihs_validated_bp_monitors` | Validated blood pressure monitors | British and Irish Hypertension Society | 2026 | 官方健康教育 | [link](https://bihsoc.org/bp-monitors/) |
| 122 | 验证设备/设备注册表 | `hypertension_canada_device_recommendations` | Recommended blood pressure monitors | Hypertension Canada | 2026 | 官方健康教育 | [link](https://hypertension.ca/bpdevices) |
| 123 | 验证设备/设备注册表 | `iso_81060_2_validation_standard` | ISO 81060-2:2018 Non-invasive sphygmomanometers clinical investigation | International Organization for Standardization | 2018 | 验证标准/监管 | [link](https://www.iso.org/standard/73339.html) |
| 124 | 验证设备/设备注册表 | `stride_bp_validated_devices` | STRIDE BP validated blood pressure monitors | STRIDE BP | 2026 | 官方健康教育 | [link](https://www.stridebp.org/bp-monitors) |
| 125 | 验证设备/设备注册表 | `validatebp_validated_devices` | Validated Device Listing | ValidateBP | 2026 | 官方健康教育 | [link](https://www.validatebp.org/) |
| 126 | 验证设备/设备注册表 | `who_automated_cuff_bp_device_specs` | Technical specifications for automated non-invasive blood pressure measuring devices with cuff | World Health Organization | 2020 | 验证标准/监管 | [link](https://www.who.int/publications/i/item/9789240002654) |
