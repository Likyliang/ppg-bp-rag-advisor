---
source_id: mehrang_2018_smartphone_mechanocardiography_cvd
title: Multiclass Classifier based Cardiovascular Condition Detection Using Smartphone Mechanocardiography
source_type: clinical_research_study
organization: Scientific Reports
region: global
topic: research_context
language: en
url: https://www.nature.com/articles/s41598-018-27683-9
doi: 10.1038/s41598-018-27683-9
pmid: ''
year: '2018'
last_accessed: '2026-06-12'
evidence_class: research_context
source_quality_score: '21'
allowed_uses:
- research_background
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
safety_level: standard
---

## 来源摘要

该研究用智能手机机械心动图（mechanocardiography，联合心振 SCG 与陀螺心动图 GCG）对多类心血管状态（如房颤、缺血）进行分类，是“手机贴胸心振 → 节律/缺血排查”的研究背景。

## 可用于报告的要点

- 智能手机内置加速度计与陀螺仪可采集心振(SCG)与陀螺心动图(GCG)，无需外接传感器。
- 机械心动图在研究数据集上可对房颤等节律异常分类，并有检测“静默”阵发性房颤的潜力。
- 房颤等节律异常需经心电图/动态心电图(Holter)确认；机械信号结果只能提示“建议做心电图排查”。
- 心振逐拍幅值在房颤时呈明显逐拍变化，可作为节律不规则的机械学线索之一。

## 实现使用说明

- 仅用于 research_background：支持“节律异常建议心电图排查”的研究背景。
- 不输出房颤等诊断；节律结论需心电图/Holter 确认。
