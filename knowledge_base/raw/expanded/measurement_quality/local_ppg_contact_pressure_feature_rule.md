---
source_id: local_ppg_contact_pressure_feature_rule
title: PPG contact pressure feature interpretation rule
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
source_hash: 3e7332f7541fc2c4
safety_level: standard
---

## 来源摘要

本地特征字典规则：contact_pressure_level 只用于解释手指按压力度对 PPG 波形质量的影响。

## 可用于报告的要点

- 按压力度过紧、过松或不稳定时，报告应建议放松手指并保持稳定。
- 接触压力异常只能说明采集质量不确定，不能估计真实血压偏差。
- 该特征应与 contact pressure / contact force PPG 研究证据一起用于研发审计。

## 实现使用说明

- 用于 signal_quality、remeasurement 和研究背景；不用于个体诊断或血压准确性验证。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

