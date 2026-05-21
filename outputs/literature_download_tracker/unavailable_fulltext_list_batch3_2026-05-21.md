# Batch 3 未归档 / 受阻文献名单 - 2026-05-21

来源：Batch 3 网页端检索结果和本地下载目录核对。  
边界：只记录合法官方/机构入口；不使用 Sci-Hub、盗版镜像、账号密码、cookie、token 或机构会话数据。

| item_id | status | official / best URL | reason | next action |
| --- | --- | --- | --- | --- |
| `stergiou_2023_esh_cuffless_validation_recommendations` | institution_required / not archived | `https://doi.org/10.1097/HJH.0000000000003483` | PubMed 与机构页确认题名、DOI、PMID 和出版信息；未找到合法公开 PDF，LWW / Journal of Hypertension 正式全文更可能需要机构访问。 | 若后续通过机构或浏览器合法下载，请保存为 `knowledge_base/sources/downloads/stergiou_2023_esh_cuffless_validation_recommendations.pdf`。这是无袖带 BP 验证重要来源，但当前 RAG 已有 AHA/FDA/ESC/PPG 局限来源，暂不阻塞。 |
| `maeda_2011_measurement_site_motion_artifacts_ppg` | institution_required / not archived | `https://link.springer.com/article/10.1007/s10916-010-9505-0` | Springer 与 PubMed 记录确认题名、DOI、PMID；网页端未找到合法公开 PDF 或机构仓储版本。 | 若后续下载成功，请保存为 `knowledge_base/sources/downloads/maeda_2011_measurement_site_motion_artifacts_ppg.pdf`。当前已有 Frontiers 2019 测量部位和多篇 PPG 质量综述，暂不阻塞。 |
| `sole_morillo_2024_led_viewing_angle_optical_window_ppg_signal_quality` | blocked / not archived | `https://doi.org/10.1117/12.3001707` | VUB 和 SPIE 官方页确认 citation，但 SPIE 页面受 Incapsula/访问限制，未找到合法公开 PDF。 | 若后续下载成功，请保存为 `knowledge_base/sources/downloads/sole_morillo_2024_led_viewing_angle_optical_window_ppg_signal_quality.pdf`。当前仅作为硬件光路补充项，不阻塞 RAG。 |

## Batch 3 已完成归档

- 已归档 11 个 PDF：Mukkamala 2015、Mukkamala 2017、Bradley 2022、Parati 2026、Ode 2020、Park 2022、Arguello-Prada 2024、Lee 2013、Sjoding 2020、Shi 2022、Cabanas 2022。
- 网页端末尾统计写作 `open_pdf` 10 条、`blocked` 2 条；逐条核对和本地文件验证后，本地实际完成归档 11 条，未归档 3 条。
- 所有已归档 PDF 仍位于 Git 忽略目录 `knowledge_base/sources/downloads/`；RAG 只使用中文摘要和 citation。
