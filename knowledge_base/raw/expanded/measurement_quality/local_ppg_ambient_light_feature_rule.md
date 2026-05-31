---
source_id: local_ppg_ambient_light_feature_rule
title: PPG ambient light feature interpretation rule
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
source_hash: 934bfdf642d2f6c8
safety_level: standard
---

## 来源摘要

本地特征字典规则：ambient_light_level 只用于解释环境光对摄像头 PPG 采集的影响。

## 可用于报告的要点

- 强光、过暗或光线不稳定时，报告应建议在稳定光线下重新测量。
- 环境光异常不应被解释为用户血压异常原因。
- 该特征可与 imaging/video PPG 光照研究和光学传感局限证据共同使用。

## 实现使用说明

- 用于 signal_quality、remeasurement 和 research_background；不用于诊断或治疗建议。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

