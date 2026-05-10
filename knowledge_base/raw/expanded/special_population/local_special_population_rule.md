---
source_id: local_special_population_rule
title: Special population conservative advice rule
source_type: local_safety_rule
organization: project
region: global
topic: special_population
language: zh
url: ''
doi: ''
pmid: ''
year: '2026'
last_accessed: '2026-05-10'
evidence_class: safety_rule
source_quality_score: '24'
allowed_uses:
- special_population
- medication_safety
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: ff9b609769a56bb8
safety_level: high
---

## 来源摘要

本项目规则：老年、妊娠、糖尿病、肾病、心血管病史或正在用药用户应给出保守咨询医生建议。

## 可用于报告的要点

- 只提示更保守复核和就医沟通。
- 不提供个体化治疗目标。
- 不建议调药。

## 实现使用说明

- 与 rule_engine special_population 规则保持一致。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

