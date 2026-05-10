---
source_id: local_ppg_signal_quality_rule
title: PPG signal quality and confidence safety rule
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
- cuffless_ppg_limitations
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: 18a4b3fd004a7a2d
safety_level: standard
---

## 来源摘要

本项目规则：低信号质量或低置信度时不生成强风险结论。

## 可用于报告的要点

- 质量差时优先重新采集。
- 采集时长短应提示复测。
- 置信度低时建议规范设备复核。

## 实现使用说明

- 与 rule_engine 质量规则保持一致。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

