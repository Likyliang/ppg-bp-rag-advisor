---
source_id: local_confidence_interpretation_rule
title: Model confidence interpretation rule
source_type: local_safety_rule
organization: project
region: global
topic: measurement_quality
language: zh
url: ''
doi: ''
pmid: ''
year: '2026'
last_accessed: '2026-05-10'
evidence_class: safety_rule
source_quality_score: '24'
allowed_uses:
- signal_quality
- remeasurement
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: 77aeea4e6706d8d6
safety_level: standard
---

## 来源摘要

本地规则规定上游置信度偏低时只提示复测和规范设备复核。

## 可用于报告的要点

- 低置信度不等同疾病风险。
- 报告应避免确定性结论。
- 优先说明估算不确定性。

## 实现使用说明

- 用于 signal_quality。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

