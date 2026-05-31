---
source_id: local_ppg_waveform_feature_boundary_rule
title: PPG waveform and PAT PTT feature boundary rule
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
- cuffless_ppg_limitations
- research_background
- disclaimer
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: 46bf8c4c84698211
safety_level: standard
---

## 来源摘要

本地特征字典规则：波形形态、PAT/PTT 和分布外评分只用于研究背景、质量解释和安全边界。

## 可用于报告的要点

- upstroke_time、pulse_width、dicrotic_notch、reflection_index、stiffness_index 等不应直接转成用户诊断。
- PAT/PTT 可解释无袖带估算背景和校准限制，但不能证明单次 PPG 血压估算准确。
- ood_score 偏高时应说明算法可能不适用于该输入，并建议规范复核。

## 实现使用说明

- 用于 research_background、cuffless_ppg_limitations 和 disclaimer；不进入诊断、治疗、用药或准确性验证结论。

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。

