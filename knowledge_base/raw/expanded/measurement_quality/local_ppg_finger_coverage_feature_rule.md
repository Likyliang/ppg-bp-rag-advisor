---
source_id: local_ppg_finger_coverage_feature_rule
title: PPG finger coverage feature interpretation rule
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
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: 2845db01975cc5e6
safety_level: standard
---

## 来源摘要

本地特征字典规则：finger_coverage_score 只用于解释手指覆盖摄像头是否稳定。

## 可用于报告的要点

- 覆盖不完整时，摄像头 PPG 波形可能不稳定，报告应建议重新覆盖后复测。
- 覆盖完整度只说明采集条件，不代表血压估算值一定准确。
- 用户报告应使用易懂表达，不展示复杂算法术语。

## 实现使用说明

- 用于 signal_quality 和 remeasurement；与摄像头 PPG 采集流程提示配合使用。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

