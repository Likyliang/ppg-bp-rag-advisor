---
source_id: local_capture_environment_rule
title: Camera PPG capture environment rule
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
source_hash: c519ad1db7d455b6
safety_level: standard
---

## 来源摘要

本地规则补充摄像头 PPG 采集环境对信号质量的影响。

## 可用于报告的要点

- 强光、移动、按压力度和采集时间会影响信号。
- 低质量时优先重新采集。
- 不要输出强风险结论。

## 实现使用说明

- 用于 signal_quality。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

