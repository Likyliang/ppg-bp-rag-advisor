# 第二批仍未归档 / 受阻文献名单 - 2026-05-21

来源：用户提供的 Batch 2 网页端检索结果 + 本地下载目录核对。  
边界：只记录合法官方/机构入口；不使用 Sci-Hub、盗版镜像、账号密码、cookie、token 或机构会话数据。

## 本轮已归档，不再列为缺口

| item_id | archive status | archived file | pages | note |
| --- | --- | --- | ---: | --- |
| `muntner_2019_aha_bp_measurement_scientific_statement` | archived from user download | `knowledge_base/sources/downloads/muntner_2019_aha_bp_measurement_scientific_statement.pdf` | 70 | AHA 血压测量科学声明，PMC/Europe PMC 公开全文。 |
| `aami_esh_iso_2018_universal_validation_standard` | archived from user download | `knowledge_base/sources/downloads/aami_esh_iso_2018_universal_validation_standard.pdf` | 16 | AAMI/ESH/ISO 血压设备验证统一标准，PMC 公开全文。 |
| `esh_2021_home_bp_monitoring_position_paper` | archived from user download | `knowledge_base/sources/downloads/esh_2021_home_bp_monitoring_position_paper.pdf` | 26 | ESH 2021 家庭血压监测立场文件，机构仓储开放 PDF。 |
| `fine_2021_ppg_sources_of_inaccuracy` | archived from user download | `knowledge_base/sources/downloads/fine_2021_ppg_sources_of_inaccuracy.pdf` | 36 | PPG 误差来源综述，只用于 signal_quality / research_background。 |
| `tamura_2014_wearable_ppg_sensors_past_present` | archived from user download | `knowledge_base/sources/downloads/tamura_2014_wearable_ppg_sensors_past_present.pdf` | 21 | 可穿戴 PPG 传感器综述，只用于 signal_quality / research_background。 |
| `sun_2016_ppg_revisited_contact_noncontact_imaging` | archived from user download | `knowledge_base/sources/downloads/sun_2016_ppg_revisited_contact_noncontact_imaging.pdf` | 35 | 接触式/非接触式/iPPG 综述，只用于 PPG 局限和信号质量。 |
| `frontiers_2019_ppg_measurement_site_waveform` | archived from user download | `knowledge_base/sources/downloads/frontiers_2019_ppg_measurement_site_waveform.pdf` | 8 | 测量部位影响 PPG 波形研究，只用于 sensor_position 解释。 |
| `tamura_2019_current_progress_ppg_spo2` | archived from user download | `knowledge_base/sources/downloads/tamura_2019_current_progress_ppg_spo2.pdf` | 16 | PPG/SpO2 健康监测综述，只用于技术背景。 |
| `lee_2021_skin_compatible_wearable_ppg` | archived from user download | `knowledge_base/sources/downloads/lee_2021_skin_compatible_wearable_ppg.pdf` | 21 | 皮肤兼容可穿戴 PPG 系统综述，只用于佩戴/接触稳定性背景。 |
| `electronics_2023_ppg_wearable_devices_review` | archived from user download | `knowledge_base/sources/downloads/electronics_2023_ppg_wearable_devices_review.pdf` | 24 | 可穿戴 PPG 综合综述，只用于技术挑战和局限背景。 |

## 仍未归档 / 后续手动下载

| item_id | status | official / best URL | reason | next action |
| --- | --- | --- | --- | --- |
| `esh_2010_international_protocol_validation` | blocked / not archived | `https://www.dableducational.org/pdfs/esh-ip%202010%20protocol.pdf` | PubMed/KCL 可确认题名与 DOI，DABL Educational Trust 列出合法 PDF 路径；网页端报告 DABL 站点/PDF 返回 502 或受阻。本地未发现匹配 PDF。 | 若手动下载成功，请保存为 `knowledge_base/sources/downloads/esh_2010_international_protocol_validation.pdf`。当前已有 AAMI/ESH/ISO 2018 统一验证标准，设备验证内容不被该项阻塞。 |

## 摘要入库提醒

- 第二批已归档 PDF 会通过 source catalog + fulltext summary notes 进入 RAG；PDF 全文仍不提交。
- PPG/光学传感来源只允许支撑 `signal_quality`、`cuffless_ppg_limitations` 或 `research_background`，不能支撑诊断、治疗、调药或替代规范袖带血压测量。
