---
source_id: local_hypertensive_emergency_rule
title: Hypertensive emergency safety rule
source_type: local_safety_rule
organization: project
region: global
topic: emergency
language: zh
url: ''
doi: ''
pmid: ''
year: '2026'
last_accessed: '2026-05-10'
evidence_class: safety_rule
source_quality_score: '24'
allowed_uses:
- emergency_alert
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: c31fa99fb1a10901
safety_level: high
---

## 来源摘要

本项目规则：严重偏高估算值并伴急症症状时，把急救提示放在报告最前。

## 可用于报告的要点

- 不要用普通生活方式建议冲淡急救提示。
- PPG 需要复核但不延误急救。
- 症状包括胸痛、气短、神经症状等。

## 实现使用说明

- 与 rule_engine emergency 规则保持一致。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

