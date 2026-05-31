---
source_id: local_ppg_motion_artifact_feature_rule
title: PPG motion artifact feature interpretation rule
source_type: local_feature_dictionary_rule
organization: project
region: global
topic: measurement_quality
language: zh
url: ''
doi: ''
pmid: ''
year: '2026'
last_accessed: '2026-05-31'
evidence_class: safety_rule
source_quality_score: '24'
allowed_uses:
- signal_quality
- remeasurement
- cuffless_ppg_limitations
- research_background
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: e8be3f1530472de9
safety_level: standard
---

## 来源摘要

本地特征字典规则：motion_artifact_score 只用于解释手指移动或运动伪影对 PPG 采集稳定性的影响。

## 可用于报告的要点

- motion_artifact_score 偏高时，报告应提示保持静止并重新采集。
- 该特征可降低本次解释强度，但不能证明血压估算是否准确。
- 异常运动伪影不应被解释为疾病风险或血压升高原因。

## 实现使用说明

- 用于 signal_quality 和 remeasurement；不得用于诊断、治疗、用药或 PPG 准确性验证。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

