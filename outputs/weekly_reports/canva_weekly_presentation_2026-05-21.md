# Canva 周报演示文稿记录

日期：2026-05-21  
主题：高血压 PPG 估算解释 RAG-Agent 本周进展

## 已生成演示文稿

- 标题：高血压 PPG RAG-Agent 本周进展（展示增强版）
- Canva design ID：`DAHKSZUYFqI`
- 页数：5
- 编辑链接：[Canva edit](https://www.canva.com/d/6XmJGbujHRGC9jF)
- 查看链接：[Canva view](https://www.canva.com/d/hA9Zvc1MW-Ga-M2)
- 来源底稿：[展示版周报](high_bp_rag_weekly_report_practical_2026-05-21.md)

## 页面结构

1. 高血压 PPG 估算解释 RAG-Agent：知识库与评估链路进展
2. 本周关键工作量总览：文献、sources、chunks、问题集、fixtures、pytest 和 API 实验
3. 文献治理：从 PDF 归档、source catalog、中文 notes 到 RAG chunks
4. 问题集与测试设计：golden queries、case fixtures 和自动化测试覆盖
5. 检索评估与安全指标：calibrated query-only、Precision@5、unsafe leakage、API 实验和并发控制

## 生成说明

- 基于上一版 RAG 汇报 PPT 的主题方向继续制作。
- 先生成 5 页短版候选，随后根据反馈升级为“内容版”，补充关键工作量、RAG 组织流程、source catalog、评估集、API 实验和并发限制。
- 之后进一步增强测试说明，加入结构化输入示例、golden query 问题集构成、case fixture 示例、防自证代码片段、敏感场景约束、并发限制代码和关键指标。
- 最终展示增强版恢复并突出关键工作量：62 份 PDF/资料、48 个中文摘要、14 个待摘要 PDF、6 个受阻来源、114 个纳入来源、524 个 RAG chunks、100 条 golden queries、50 个 fixtures、224 项 pytest 和 50 个 API cases。
- 最终版把第 3 页改为文献治理流程，明确 PDF 不提交全文、source catalog 记录 evidence_class/allowed_uses/source_hash、中文 notes 生成 chunks.jsonl，并展示审计结果。
- 当前版本控制单页信息密度，但保留展示必需的事实和指标，适合组会或阶段展示。
- 未把正式报告生成描述为本周成果；该部分保留为下周重点。

## 测试增强内容

- 输入示例：`145/92 + HR 82 + signal_quality 0.86 + confidence 0.68`、`150/95 + 低信号质量`、`185/122 + chest_pain`、`alias_input: SBP/DBP/HR/quality/conf`。
- Golden queries 覆盖：PPG 局限、信号质量、家庭复测、急症、用药、孕妇、糖尿病、CKD、生活方式、设备验证。
- Case fixtures 覆盖：正常、偏高、低质量、180/120、胸痛、孕妇、糖尿病、CKD、用药用户。
- 关键代码片段：`assert all(v is None for v in query_only_calls)`、`assert mean_precision_at_5 >= .95`、`return max(1, min(value, 5))`。
- 当前指标：100 queries、Precision@5 = 1.0、unsafe source leakage = 0、50 API cases、success_rate = 1.0、P95 latency = 0.1691s。

## 其他候选

Canva 同时生成了其他候选版本，可在需要更换视觉风格时参考：

- 候选 1：https://www.canva.com/d/YM4gR-o7ucxoEk4
- 候选 3：https://www.canva.com/d/30WVzEI4M3xhasF
- 候选 4：https://www.canva.com/d/iMpSvi-bIKJqLhG
