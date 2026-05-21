# 第一批仍未归档 / 受阻文献名单 - 2026-05-21

来源：用户提供的网页版检索结果 + 本地下载目录核对。  
边界：只记录合法官方/机构入口；不使用 Sci-Hub、盗版镜像、账号密码、cookie、token 或机构会话数据。

## 本轮已归档，不再列为缺口

| item_id | archive status | archived file | pages | note |
| --- | --- | --- | ---: | --- |
| `aha_ama_2020_smbp_policy_statement` | archived from user download | `knowledge_base/sources/downloads/aha_ama_2020_smbp_policy_statement.pdf` | 22 | 网页端为 AHA 403，但用户本地 PDF 已匹配归档。 |
| `chandrasekhar_2020_contact_pressure_cuffless_bp` | archived from user download | `knowledge_base/sources/downloads/chandrasekhar_2020_contact_pressure_cuffless_bp.pdf` | 14 | PMC 开放全文，本地 PDF 已归档。 |
| `shirbani_2020_ambient_light_skin_tone_vpg` | archived from user download | `knowledge_base/sources/downloads/shirbani_2020_ambient_light_skin_tone_vpg.pdf` | 4 | 网页端未找到开放 PDF，但用户本地 PDF 已归档；仅用于 PPG 信号质量/研究背景。 |
| `teng_2004_contact_force_ppg` | archived from user download | `knowledge_base/sources/downloads/teng_2004_contact_force_ppg.pdf` | 14 | IOP 官方入口有机器人保护，但用户本地 PDF 已归档；仅用于接触压力/信号质量。 |

## 仍未归档 / 后续手动下载

| item_id | status | official / best URL | reason | next action |
| --- | --- | --- | --- | --- |
| `esc_2024_bp_guideline_key_points` | official URL found, local archive unresolved | `https://www.escardio.org/static-file/Escardio/Guidelines/Products/Essential%20Messages/2024%20EM/Essential%20Messages_2024%20HTN.pdf` | 网页端识别为 ESC 官方 Essential Messages PDF，但本地自动下载仍返回 403；本地同名下载实际是 pharmacotherapy 短文，不是 Essential Messages，因此未误归档。 | 如果浏览器可下载，请保存为 `knowledge_base/sources/downloads/esc_2024_bp_guideline_key_points.pdf`。当前已有 ESC 2024 full guideline，可先不作为内容阻塞。 |
| `chinese_hypertension_guideline_2024_revision_chl_bha` | blocked / not archived | `https://www.chl-bha.org.cn/Public/ueditor/php/upload/20240815/17236841017752.pdf` | CHL-BHA 官方镜像链接存在，但自动访问 connection reset / timeout；本地未发现匹配 PDF。 | 若手动下载成功，请保存为 `knowledge_base/sources/downloads/chinese_hypertension_guideline_2024_revision_chl_bha.pdf`。当前项目已有中国 2024 指南的既有 catalog/SciOpen 表示，因此这是镜像来源缺口。 |

## 摘要入库提醒

- 已归档 PDF 还不是自动等于 RAG 证据，需要后续补 source catalog、中文摘要 notes，然后重新 `ingest/audit/evaluate`。
- `shirbani_2020_ambient_light_skin_tone_vpg` 和 `teng_2004_contact_force_ppg` 只允许支撑 `signal_quality` / `research_background`，不能用于临床诊断、治疗、调药或替代规范袖带血压测量。
