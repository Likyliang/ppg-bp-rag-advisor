---
source_id: desquins_2022_ppg_quality_assessment_survey
title: A Survey of Photoplethysmography and Imaging Photoplethysmography Quality Assessment
  Methods
source_type: quality_assessment_survey
organization: Applied Sciences
region: global
topic: measurement_quality
language: en
url: https://www.mdpi.com/2076-3417/12/19/9582
doi: 10.3390/app12199582
pmid: ''
year: '2022'
last_accessed: '2026-05-16'
evidence_class: review
source_quality_score: '22'
allowed_uses:
- signal_quality
- remeasurement
- research_background
review_status: included
derived_from: knowledge_base/sources/source_catalog.yaml
source_hash: ea0c3467ca51b0cc
safety_level: standard
---

## 来源摘要

该综述聚焦 PPG 与成像 PPG 的信号质量评估，可用于说明为什么需要 quality score、波形筛选和低质量拦截。

## 可用于报告的要点

- PPG 信号可能受外部和生理因素干扰，质量评估有助于避免误解。
- 成像/摄像头 PPG 更需要关注环境光、运动和画面稳定性。
- 低质量信号应触发重新采集、延长采集或改用规范设备复核。

## 实现使用说明

- 用于 signal_quality 和 RAG 检索解释；不用于临床阈值。

## 全文候选与下载材料摘要

### A Survey of Photoplethysmography and Imaging Photoplethysmography Quality Assessment Methods

- candidate_id: `desquins_2022_ppg_quality_assessment_survey_pdf`
- access_mode: `public_pdf`
- fulltext_status: local_pdf_available
- source_url: https://www.mdpi.com/2076-3417/12/19/9582
- doi: 10.3390/app12199582
- pmid: n/a
- access_recorded: 2026-05-16
- local_pdf: `desquins_2022_ppg_quality_assessment_survey.pdf`

#### 摘要入库要点

- 已从 MDPI 公开 PDF 资源下载；本项目只提交中文摘要、citation 和访问记录，不提交全文 PDF。
- 该综述覆盖 PPG/iPPG 信号质量评估方法，强调运动、光照、低信噪比、ROI/接触/摄像头条件和自动质量分级的重要性。
- 本系统可用该来源支持低质量拦截、重新采集、延长采集和“质量不足不做强风险解释”的边界。
- 该来源只支持 signal_quality、remeasurement 和 research_background，不用于临床阈值、诊断或治疗建议。

#### 使用边界

- 只把上述摘要用于 PPG 估算解释、复测建议、设备局限、生活方式教育或安全提醒。
- 不复制全文、不引用未审校段落、不生成诊断、治疗、开药、停药或替代规范血压测量的结论。
- candidate_hash: `a0ee970c91ce61ff`

## 安全边界

- 该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。
- 不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。
- 研究或综述来源只用于背景和局限说明，不用于患者级临床建议。

