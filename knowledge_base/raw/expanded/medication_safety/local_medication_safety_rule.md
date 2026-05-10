---
source_id: local_medication_safety_rule
title: Medication safety boundary rule
source_type: local_safety_rule
organization: project
region: global
topic: medication_safety
language: zh
url: ''
doi: ''
pmid: ''
year: '2026'
last_accessed: '2026-05-10'
evidence_class: safety_rule
source_quality_score: '24'
allowed_uses:
- medication_safety
- special_population
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: 6f145916c8d82301
safety_level: high
---

## 来源摘要

本项目规则：报告不得建议自行服药、停药、换药或调整剂量。

## 可用于报告的要点

- 正在用药用户应保留记录并咨询医生。
- 不能根据 PPG 估算值改变用药。
- Safety Agent 必须拦截调药表达。

## 实现使用说明

- 用于 medication_safety。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

