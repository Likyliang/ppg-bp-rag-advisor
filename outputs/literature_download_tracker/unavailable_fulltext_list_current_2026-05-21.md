# 当前仍未归档 / 受阻文献总名单 - 2026-05-21

来源：Batch 1 + Batch 2 + Batch 3 网页端检索结果、本地下载目录核对和 Obsidian 同步清单。  
边界：只记录合法官方/机构入口；不使用 Sci-Hub、盗版镜像、账号密码、cookie、token 或机构会话数据。

| item_id | batch | status | official / best URL | reason | next action |
| --- | --- | --- | --- | --- | --- |
| `esc_2024_bp_guideline_key_points` | Batch 1 | official URL found, local archive unresolved | `https://www.escardio.org/static-file/Escardio/Guidelines/Products/Essential%20Messages/2024%20EM/Essential%20Messages_2024%20HTN.pdf` | ESC 官方 Essential Messages PDF URL 已识别，但本地自动下载仍返回 403；本地同名文件实际为 pharmacotherapy 短文，不是 Essential Messages。 | 若浏览器可下载，请保存为 `knowledge_base/sources/downloads/esc_2024_bp_guideline_key_points.pdf`。当前已有 ESC 2024 full guideline，可先不作为内容阻塞。 |
| `chinese_hypertension_guideline_2024_revision_chl_bha` | Batch 1 | blocked / not archived | `https://www.chl-bha.org.cn/Public/ueditor/php/upload/20240815/17236841017752.pdf` | CHL-BHA 官方镜像链接存在，但自动访问 connection reset / timeout；本地未发现匹配 PDF。 | 若手动下载成功，请保存为 `knowledge_base/sources/downloads/chinese_hypertension_guideline_2024_revision_chl_bha.pdf`。当前已有中国 2024 指南的既有 catalog/SciOpen 表示。 |
| `esh_2010_international_protocol_validation` | Batch 2 | blocked / not archived | `https://www.dableducational.org/pdfs/esh-ip%202010%20protocol.pdf` | PubMed/KCL 可确认题名与 DOI，DABL Educational Trust 列出合法 PDF 路径；网页端报告 DABL 站点/PDF 返回 502 或受阻。本地未发现匹配 PDF。 | 若手动下载成功，请保存为 `knowledge_base/sources/downloads/esh_2010_international_protocol_validation.pdf`。当前已有 AAMI/ESH/ISO 2018 统一验证标准，设备验证内容不被该项阻塞。 |
| `stergiou_2023_esh_cuffless_validation_recommendations` | Batch 3 | institution_required / not archived | `https://doi.org/10.1097/HJH.0000000000003483` | PubMed 与机构页确认题名、DOI、PMID 和出版信息；未找到合法公开 PDF，LWW / Journal of Hypertension 正式全文更可能需要机构访问。 | 若后续通过机构或浏览器合法下载，请保存为 `knowledge_base/sources/downloads/stergiou_2023_esh_cuffless_validation_recommendations.pdf`。当前已有 AHA/FDA/ESC/PPG 局限来源，暂不阻塞。 |
| `maeda_2011_measurement_site_motion_artifacts_ppg` | Batch 3 | institution_required / not archived | `https://link.springer.com/article/10.1007/s10916-010-9505-0` | Springer 与 PubMed 记录确认题名、DOI、PMID；网页端未找到合法公开 PDF 或机构仓储版本。 | 若后续下载成功，请保存为 `knowledge_base/sources/downloads/maeda_2011_measurement_site_motion_artifacts_ppg.pdf`。当前已有 Frontiers 2019 测量部位和多篇 PPG 质量综述，暂不阻塞。 |
| `sole_morillo_2024_led_viewing_angle_optical_window_ppg_signal_quality` | Batch 3 | blocked / not archived | `https://doi.org/10.1117/12.3001707` | VUB 和 SPIE 官方页确认 citation，但 SPIE 页面受 Incapsula/访问限制，未找到合法公开 PDF。 | 若后续下载成功，请保存为 `knowledge_base/sources/downloads/sole_morillo_2024_led_viewing_angle_optical_window_ppg_signal_quality.pdf`。当前仅作为硬件光路补充项，不阻塞 RAG。 |

## 当前影响

- 这些是“来源访问缺口”，不是当前 RAG 可用性阻塞。
- 第二批 10 个已下载 PDF 已完成 source catalog、中文摘要 notes、raw note 生成、ingest、audit、retrieval/report evaluation 和 Obsidian 同步。
- 第三批 11 个已下载 PDF 已完成 source catalog、中文摘要 notes、raw note、ingest、audit、retrieval/report evaluation 和 Obsidian 同步。
- 所有 PDF 全文仍只放在 Git 忽略目录或 Obsidian symlink，不进入可提交知识库。
