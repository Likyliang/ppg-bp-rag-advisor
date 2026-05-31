# 2026-05-28 组会汇报提纲：高血压 RAG demo

## 建议汇报结构（10-12 分钟）

1. 研究定位：这是高血压健康解释应用 demo，不是 PPG 血压估算准确性验证。
2. 文档库现状：展示正式入库来源、主题覆盖、证据等级和本地 PDF 向量规模。
3. 授权受限清单：说明哪些文献不能自动下载，为什么要走机构/浏览器/人工核验。
4. Chunk 分割过程：展示 PDF 到 page、sentence、overlap chunk、metadata、vector 的链路。
5. 报告生成链路：小程序结构化数据 -> 规则引擎 -> RAG 检索 -> Safety Agent -> 报告。
6. 安全边界：不诊断、不调药、不替代袖带血压计、不替代医生。
7. 下一步：补齐待授权文献、优化 chunk 质量抽检、准备论文中 demo 与核心实验的边界说明。

## 一页总览数据

- 正式摘要入库来源：126
- 正式 KB chunks：584
- 本地 PDF 全文向量来源：62
- 本地 PDF 页数：2220
- 本地全文 chunks：13168
- 中国官方/准官方来源：16
- 质量门禁：included_sources=126, test_count=227, retrieval_match_rate=1.0, unsafe_source_leakage_count=0

## 核心口径

- 文档库治理：只纳入权威、可追溯、允许用于健康解释的来源。
- 摘要入库：提交中文摘要、citation、访问记录和安全边界，不提交 raw PDF full text。
- 本地全文索引：用于 demo 检索调试，保留页码和 sha256，方便回查，但不作为论文准确性结论。
- 结构化报告：系统根据 SBP/DBP/HR/质量分数/症状/特殊人群等字段生成解释，不把 PPG 估算写成诊断。
- Safety Agent：把所有输出限制在复测、记录、就医沟通、生活方式教育和安全提醒范围内。

## 现场演示顺序

1. 打开 `01_current_document_inventory.md`，展示文档来源与主题覆盖。
2. 打开 `02_access_limited_literature_list.md`，说明授权/站点限制导致不能自动下载的项目。
3. 打开 `03_chunk_splitting_process_demo.md`，讲 chunk 切分流程和真实 chunk metadata。
4. 打开 Streamlit 或 CLI demo，输入小程序结构化样例，生成报告。
5. 用最后一页强调：这是安全约束 RAG-Agent 的解释应用，不是 PPG 估计模型有效性验证。

