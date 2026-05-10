---
source_id: local_disclaimer_rule
title: Required disclaimer rule
source_type: local_safety_rule
organization: project
region: global
topic: disclaimer
language: zh
url: ''
doi: ''
pmid: ''
year: '2026'
last_accessed: '2026-05-10'
evidence_class: safety_rule
source_quality_score: '24'
allowed_uses:
- disclaimer
- cuffless_ppg_limitations
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: 2450e2cd84d0c559
safety_level: standard
---

## 来源摘要

本项目规则：报告必须声明仅供个人健康趋势参考，不能替代医生诊断和规范血压测量。

## 可用于报告的要点

- 免责声明必须出现在 Markdown 和 JSON。
- PPG 局限必须显式表达。
- 不能写成诊断或治疗建议。

## 实现使用说明

- 用于 Safety Agent 必检项。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

