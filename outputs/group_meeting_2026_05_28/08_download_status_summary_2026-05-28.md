# 文献下载状态汇总（组会展示版）

## 当前检查结论

- fulltext candidate catalog：76 条
- 本地 PDF 文件：68 个
- 可抽取文本并进入全文 chunks/向量索引：67 篇
- PDF 存在但未抽出有效文本：1 篇（`nhc_ws_t_430_2013_hypertension_dietary_guidance`）
- 全文细切 chunks：14849 个，覆盖 2446 页
- 仍未进入本地 PDF 全文索引的候选：8 条
- P1 必须会前补齐：0 条；P2 可选补强：3 条；P3 不阻塞演示：5 条

## 新增补入

- 2019中国家庭血压监测指南：已切 26 个 chunks，是中文家庭血压监测、上臂式血压计复核、连续记录建议的重点证据。
- ESC 2024 高血压指南全文：已切 1162 个 chunks，用作国际指南对照，不覆盖中国官方优先级。
- ESC 2024 DOI report、ESC 2024 pharmacotherapy 评论、AHA PREVENT equations：均已入库，但只作为研发背景/补充材料，不用于给用户开药、调药或做个体风险预测。

## 展示时建议这样说

“目前本地已有 68 个 PDF，其中 67 篇抽取出可检索全文，形成 14849 个细粒度 chunks。真正未下载且会前必须补齐的文献已经没有；剩下的是付费标准、公开网页、注册库或已有完整替代来源的补强项。演示重点可以放在：中文官方/指南来源增强、PDF 细切 chunk 展示、hashing vector 检索和 RAG/非 RAG 对照。”

## 对应文件

- 已下载 PDF 完整清单：`06_downloaded_pdf_literature_list_2026-05-28.md` / `.csv`
- 未下载优先级清单：`07_undownloaded_literature_priority_list_2026-05-28.md` / `.csv`
- 旧清单校正说明：`07a_access_list_correction_note_2026-05-28.md`
