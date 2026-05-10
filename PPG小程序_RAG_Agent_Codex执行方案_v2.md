# Codex 执行方案 v2：基于 PPG 小程序结构化结果的医学解释 RAG-Agent

版本：v2.0  
用途：交给 Codex / Cursor / Claude Code 等代码助手，直接按任务拆解实现项目 MVP。  
当前定位：上游小程序已经通过手指摄像头 PPG 估算血压等指标，本项目不训练、不验证 PPG 血压估计算法，而是把上游结构化结果作为输入，构建 RAG-Agent，为用户生成健康趋势解释、复测建议、生活方式建议、就医提醒和安全审查后的报告。

---

## 0. 结论：当前阶段最适合专门做 RAG-Agent

本项目当前最合理的方向不是“重新实现 PPG 血压估计算法”，而是“接收 PPG 小程序输出的估算血压和相关上下文，生成可信、可追溯、保守、安全的健康解释报告”。

原因：

1. 上游小程序已经负责采集手指摄像头视频并估算血压，RAG-Agent 没必要重复处理原始 PPG。
2. 没有袖带血压校准或临床验证数据时，不适合把论文重点放在“PPG 估压准确性证明”。
3. 对用户真正有价值的是：这个估算值意味着什么、是否需要复测、什么情况需要就医、如何改善生活方式、为什么不能把 PPG 估算值当成诊断依据。
4. 从毕业设计角度看，RAG-Agent 可以形成完整工程闭环：输入规范化、规则判断、医学知识库检索、报告生成、安全审查、API 与 Demo、评估实验。

一句话定位：

> 上游 PPG 小程序输出估算血压值、心率、信号质量和用户上下文；本系统负责医学知识增强解释、风险提示、复测建议、生活方式建议、就医提醒和安全报告生成。

---

## 1. 项目名称与边界

### 1.1 推荐项目名

中文：面向 PPG 血压估算结果的医学知识增强 RAG-Agent 健康解释系统  
英文：A Knowledge-Enhanced RAG-Agent for Health Explanation of PPG-Based Blood Pressure Estimation Results

### 1.2 本项目做什么

本项目实现一个后端服务和 Demo 应用，支持：

1. 接收上游 PPG 小程序输出的结构化估算结果。
2. 对输入字段做校验、归一化和别名映射。
3. 使用规则引擎判断信号质量、估算血压范围、急症症状、特殊人群和用药安全边界。
4. 从医学知识库中检索高血压、家庭血压监测、PPG/无袖带血压局限、生活方式干预、急症处理等知识。
5. 生成用户可读的健康解释报告。
6. 使用 Safety Agent 检查报告中是否出现诊断、开药、停药、过度承诺、引用不足和急症漏报。
7. 返回结构化 JSON 和可展示的 Markdown/HTML 报告。

### 1.3 本项目不做什么

Codex 实现时必须遵守以下边界：

1. 不训练 PPG 血压估算模型。
2. 不验证上游 PPG 估算算法的准确性。
3. 不处理或存储用户原始手指视频，除非后续项目明确授权并完成隐私设计。
4. 不声称系统可以诊断高血压、心血管疾病或其他疾病。
5. 不提供处方、用药调整、停药建议。
6. 不把 PPG 估算值等同于诊室血压、家庭袖带血压或动态血压监测。
7. 不让 LLM 自行决定医学阈值；阈值由规则引擎和配置文件决定，LLM 只负责解释和组织语言。

---

## 2. 上游小程序输入数据设计

当前 RAG-Agent 以小程序已经处理后的结果为输入。核心输入包括：PPG 估算结果、用户基础信息、症状、语言/指南地区和用户问题。

### 2.1 推荐 JSON 输入示例

```json
{
  "measurement": {
    "module": "CHS-BloodPressure",
    "estimated_sbp": 145,
    "estimated_dbp": 92,
    "heart_rate": 82,
    "signal_quality_score": 0.86,
    "signal_quality_label": "good",
    "confidence": 0.68,
    "capture_duration_sec": 30,
    "ppg_source": "camera_finger",
    "algorithm_version": "ppg-bp-v0.3",
    "calculation_principle": "camera-based finger PPG estimation",
    "timestamp": "2026-05-10T10:30:00+08:00"
  },
  "user_profile": {
    "age": 45,
    "sex": "male",
    "height_cm": 172,
    "weight_kg": 78,
    "bmi": 26.4,
    "smoker": false,
    "diabetes": false,
    "kidney_disease": false,
    "cvd_history": false,
    "pregnancy": false,
    "antihypertensive_medication": false,
    "medication_names": []
  },
  "symptoms": {
    "chest_pain": false,
    "shortness_of_breath": false,
    "back_pain": false,
    "numbness_or_weakness": false,
    "vision_change": false,
    "speech_difficulty": false,
    "severe_headache": false,
    "dizziness": false
  },
  "locale": "zh-CN",
  "guideline_region": "CN",
  "user_question": "这个血压结果需要注意什么？"
}
```

### 2.2 字段含义

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| measurement.module | string | 是 | 模块名，例如 CHS-BloodPressure |
| estimated_sbp | float | 建议 | 上游算法估算的收缩压，单位 mmHg |
| estimated_dbp | float | 建议 | 上游算法估算的舒张压，单位 mmHg |
| heart_rate | float | 可选 | 心率，单位 bpm |
| signal_quality_score | float | 可选 | 信号质量分，0-1 |
| signal_quality_label | enum | 可选 | good / fair / poor / unknown |
| confidence | float | 可选 | 上游算法置信度，0-1 |
| capture_duration_sec | float | 可选 | 采集时长，单位秒 |
| ppg_source | enum | 可选 | camera_finger / waveform / other |
| algorithm_version | string | 可选 | 上游估算算法版本 |
| calculation_principle | string | 可选 | 上游算法说明，用于报告中的技术说明 |
| user_profile | object | 可选 | 年龄、性别、BMI、基础病、用药等 |
| symptoms | object | 可选 | 胸痛、气短、视物改变、肢体无力等急症相关症状 |
| locale | enum | 可选 | zh-CN / en-US / bilingual |
| guideline_region | enum | 可选 | CN / AHA / auto |
| user_question | string | 可选 | 用户问题 |

### 2.3 字段别名映射

上游半成品 Agent 的字段名可能不稳定，因此必须实现 `config/field_mapping.yaml`。示例：

```yaml
module:
  aliases: [module, func, feature, metric_module]
estimated_sbp:
  aliases: [estimated_sbp, sbp, sys, systolic, systolic_bp, SBP]
estimated_dbp:
  aliases: [estimated_dbp, dbp, dia, diastolic, diastolic_bp, DBP]
heart_rate:
  aliases: [heart_rate, hr, pulse, bpm, HR]
signal_quality_score:
  aliases: [signal_quality_score, quality_score, sqi, signal_score]
signal_quality_label:
  aliases: [signal_quality_label, signal_quality, quality_label, quality]
confidence:
  aliases: [confidence, conf, model_confidence, bp_confidence]
capture_duration_sec:
  aliases: [capture_duration_sec, duration, duration_sec, record_seconds]
algorithm_version:
  aliases: [algorithm_version, algo_version, version, model_version]
calculation_principle:
  aliases: [calculation_principle, principle, method_note, algorithm_note]
```

---

## 3. 输出报告目标

### 3.1 用户报告应包含

1. 本次 PPG 估算结果摘要。
2. 信号质量和置信度说明。
3. 估算血压范围解释，但必须声明“基于 PPG 估算，仅供个人健康趋势参考”。
4. 是否建议复测。
5. 是否建议使用经过验证的上臂式电子血压计复核。
6. 是否建议咨询医生或紧急就医。
7. 生活方式建议。
8. 检索到的医学知识来源。
9. 安全免责声明。

### 3.2 推荐输出 JSON Schema

```json
{
  "report_id": "uuid",
  "mode": "user_health_report",
  "input_summary": {
    "estimated_sbp": 145,
    "estimated_dbp": 92,
    "heart_rate": 82,
    "signal_quality_label": "good",
    "confidence": 0.68
  },
  "measurement_status": {
    "is_usable": true,
    "quality_level": "acceptable",
    "quality_explanation": "本次信号质量较好，但 PPG 估算血压仍不能替代规范血压测量。"
  },
  "risk_assessment": {
    "bp_category_reference": "AHA_stage_2_reference_range",
    "risk_level": "elevated_attention",
    "urgency_level": "non_emergency",
    "explanation": "本次估算值处于偏高范围，建议复测并结合规范血压计记录。"
  },
  "recommendations": {
    "remeasurement": ["休息至少 5 分钟后重新测量", "连续多天记录趋势"],
    "device_advice": ["使用经过验证的上臂式电子血压计复核"],
    "lifestyle": ["减少钠盐摄入", "规律运动", "控制体重", "戒烟限酒", "保证睡眠"],
    "medical_consultation": ["若多次复测仍偏高，建议咨询医生"]
  },
  "safety_alert": {
    "emergency": false,
    "message": "当前未触发急症规则。若出现胸痛、气短、肢体无力、视物改变或说话困难，请及时急救。"
  },
  "retrieved_evidence": [
    {
      "source_id": "aha_home_bp_2025",
      "title": "Home Blood Pressure Monitoring",
      "url": "https://www.heart.org/...",
      "used_for": "家庭血压复测与设备选择建议"
    }
  ],
  "disclaimer": "本报告仅用于健康趋势解释和科普建议，不能用于诊断或治疗决策。"
}
```

---

## 4. 总体架构

```text
PPG 小程序 / 上游半成品 Agent
  ↓
结构化输入：估算 SBP/DBP、心率、信号质量、置信度、算法版本、用户信息、症状
  ↓
FastAPI 接口层
  ↓
Input Normalizer / Field Mapping
  ↓
Rule Engine
  ├─ 输入完整性检查
  ├─ PPG 信号质量判断
  ├─ 估算血压范围判断
  ├─ 急症症状判断
  ├─ 特殊人群与基础病提示
  └─ 禁止诊断/禁用药规则
  ↓
RAG Retriever
  ├─ 高血压指南知识
  ├─ 家庭血压监测建议
  ├─ PPG/无袖带血压局限
  ├─ 生活方式干预
  └─ 急症处理规则
  ↓
Report Generator
  ├─ template_only 模式
  └─ llm_rag 模式
  ↓
Safety Agent
  ├─ 诊断性表述拦截
  ├─ 处方/停药建议拦截
  ├─ 过度承诺拦截
  ├─ 急症漏报检查
  └─ 引用不足检查
  ↓
Report Builder
  ├─ JSON 输出
  ├─ Markdown/HTML 报告
  └─ 小程序前端 / Streamlit Demo
```

核心原则：规则引擎先行，RAG 提供依据，LLM 只做语言组织和解释；任何医学阈值和安全边界必须由代码和配置文件控制。

---

## 5. 规则引擎设计

规则引擎必须在 RAG 和 LLM 之前运行。它输出结构化结论，后续报告生成只能基于这些结论表达。

### 5.1 信号质量规则

配置文件：`config/safety_terms.yaml` 与 `config/bp_thresholds.yaml`

建议规则：

```text
if signal_quality_label == "poor": measurement_status = unusable
if signal_quality_score is not None and signal_quality_score < 0.60: measurement_status = low_quality
if confidence is not None and confidence < 0.50: confidence_level = low
if capture_duration_sec is not None and capture_duration_sec < 20: quality_warning += "采集时长偏短"
```

低质量时输出策略：

1. 不生成强风险结论。
2. 不使用“高血压”“正常血压”等确定性表述。
3. 只提示重新采集、检查手指覆盖、保持静止、避免强光干扰等。
4. 建议使用规范设备复核。

### 5.2 估算血压范围规则

因为输入来自 PPG 估算值，所以输出字段名称必须使用 `estimated_bp_category`，不能写成 `diagnosis`。

参考 AHA 分类配置示例：

```yaml
AHA:
  normal:
    sbp_lt: 120
    dbp_lt: 80
  elevated:
    sbp_range: [120, 129]
    dbp_lt: 80
  stage_1_reference_range:
    sbp_range: [130, 139]
    dbp_range: [80, 89]
  stage_2_reference_range:
    sbp_gte: 140
    dbp_gte: 90
  severe_range:
    sbp_gt: 180
    dbp_gt: 120
```

中国指南参考配置可另放一组，注意只能用于“参考解释”，不要直接诊断：

```yaml
CN:
  home_bp_high_reference:
    sbp_gte: 135
    dbp_gte: 85
  office_bp_high_reference:
    sbp_gte: 140
    dbp_gte: 90
```

### 5.3 急症规则

如果满足以下条件，应优先输出急症提示：

```text
estimated_sbp >= 180 或 estimated_dbp >= 120
并且 symptoms 中任一急症症状为 true：
  chest_pain
  shortness_of_breath
  back_pain
  numbness_or_weakness
  vision_change
  speech_difficulty
```

输出策略：

1. 报告开头显示“可能存在紧急风险”。
2. 建议立即寻求急救或当地紧急医疗服务。
3. 不继续给普通生活方式建议作为主内容。
4. 强调 PPG 估算值需要复核，但症状本身需要重视。

### 5.4 特殊人群规则

以下情况触发“保守建议”：

1. 年龄 ≥ 65。
2. 孕妇或可能妊娠。
3. 糖尿病、慢性肾病、既往心血管病史。
4. 正在使用降压药。
5. 反复出现头晕、胸痛、气短、严重头痛等症状。

输出策略：建议咨询医生，不做个体化用药建议。

### 5.5 禁止事项规则

报告不得包含：

1. “你已经确诊高血压”。
2. “你没有问题，不用复测”。
3. “PPG 估算值很准确，可以替代血压计”。
4. “建议服用/停用/调整某某药物”。
5. “无需就医”。
6. “保证降低血压”。

---

## 6. RAG 知识库设计

### 6.1 知识库分层

建议创建如下目录：

```text
knowledge_base/
  raw/
    guidelines/
      aha_bp_categories.md
      aha_home_bp_monitoring.md
      chinese_hypertension_guideline_2024.md
    cuffless_ppg/
      aha_cuffless_bp_statement.md
      ppg_estimation_limitations.md
    lifestyle/
      sodium_weight_exercise_smoking_sleep.md
    safety/
      hypertensive_emergency.md
      medication_safety.md
      disclaimer.md
  processed/
    chunks.jsonl
  vector_store/
```

### 6.2 知识源建议

初始知识库至少包含：

1. AHA 家庭血压监测页面：上臂式袖带设备、腕式/手指式设备局限、复测建议、测量姿势。
2. AHA 血压分类页面：Normal / Elevated / Stage 1 / Stage 2 / Severe / Emergency。
3. AHA 无袖带血压科学声明：PPG/无袖带设备是间接估算，真实场景准确性和临床用途需要验证。
4. 中国高血压防治指南 2024 修订版：用于中文场景参考。
5. 高血压生活方式干预知识：减盐、运动、体重管理、戒烟限酒、睡眠、压力管理。
6. 急症安全规则：180/120 mmHg 以上并伴随胸痛、气短、肢体无力、视物改变、说话困难等。

### 6.3 chunk 元数据

每个知识块必须带 metadata：

```json
{
  "chunk_id": "aha_home_bp_001",
  "title": "Home Blood Pressure Monitoring",
  "source_type": "guideline_or_health_education",
  "organization": "American Heart Association",
  "region": "AHA",
  "topic": "home_bp_monitoring",
  "language": "en",
  "url": "https://www.heart.org/...",
  "last_accessed": "2026-05-10",
  "safety_level": "standard",
  "content": "..."
}
```

### 6.4 检索策略

RAG 查询不应只把用户问题丢进去，而应由规则引擎生成检索意图。例如：

```json
{
  "retrieval_intents": [
    "PPG cuffless blood pressure estimation limitations",
    "home blood pressure monitoring remeasurement upper arm cuff",
    "stage 2 reference range lifestyle advice",
    "hypertensive emergency symptoms if SBP over 180 DBP over 120"
  ]
}
```

检索结果进入 Report Generator 前必须做筛选：

1. 优先官方指南、权威组织、综述。
2. 不使用营销类设备厂商页面作为核心依据。
3. 每条建议至少需要一个来源支持；若没有来源，标记为 general_wellness_advice。
4. 急症和用药相关内容必须来自安全规则或权威来源。

---

## 7. Agent 工作流

建议用确定性 workflow，而不是完全自由的聊天 Agent。

### 7.1 子模块职责

| 模块 | 作用 |
|---|---|
| Input Normalizer | 字段映射、类型转换、范围校验 |
| Rule Engine | 质量判断、估算血压范围、急症规则、特殊人群规则 |
| Retrieval Planner | 根据规则结果生成检索 query |
| RAG Retriever | 检索知识库 chunk |
| Report Generator | 基于规则结果和检索依据生成报告 |
| Safety Agent | 检查越界表述、处方建议、急症漏报、引用不足 |
| Report Builder | 输出 JSON、Markdown、HTML |

### 7.2 工作流伪代码

```python
def generate_report(payload: MeasurementPayload) -> Report:
    normalized = normalize_payload(payload)
    validation = validate_payload(normalized)
    rule_result = run_rule_engine(normalized)
    retrieval_plan = build_retrieval_queries(normalized, rule_result)
    evidence = retrieve_knowledge(retrieval_plan)
    draft = generate_report_draft(normalized, rule_result, evidence)
    safety_result = review_safety(draft, normalized, rule_result, evidence)
    final_report = apply_safety_edits(draft, safety_result)
    return final_report
```

---

## 8. Prompt 设计

### 8.1 用户报告生成 Prompt

系统提示词要包含：

```text
你是健康解释报告生成助手，不是医生。
你只能基于 rule_result 和 evidence 生成解释。
不要改变规则引擎给出的风险等级、急症等级、测量质量结论。
不要做疾病诊断。
不要给处方、用药调整或停药建议。
所有关于 PPG 血压估算的表述必须说明其为估算值，仅供个人健康趋势参考。
如果检测到严重血压范围并伴随胸痛、气短、视物改变、肢体无力或说话困难，必须优先提示立即急救。
输出必须是 JSON，符合 Report Schema。
```

### 8.2 Safety Agent Prompt

```text
请审查以下报告草稿是否存在医疗安全问题。
重点检查：
1. 是否出现确诊表述；
2. 是否把 PPG 估算值等同于规范血压测量；
3. 是否给出处方、停药、调整用药建议；
4. 是否遗漏急症提示；
5. 是否有无依据的医学建议；
6. 是否缺少免责声明。
返回 JSON：pass、issues、required_edits、severity。
```

---

## 9. API 设计

### 9.1 FastAPI 接口

```text
POST /api/v1/reports/generate
输入：MeasurementPayload
输出：HealthReport
```

```text
POST /api/v1/reports/preview-rules
输入：MeasurementPayload
输出：RuleResult
用途：调试规则引擎
```

```text
POST /api/v1/kb/ingest
输入：知识库文件路径或文本
输出：ingestion result
```

```text
GET /api/v1/health
输出：服务状态
```

### 9.2 返回错误

1. 400：输入字段无法解析或超出合理范围。
2. 422：Pydantic 校验失败。
3. 500：检索或生成失败。
4. 当 LLM 不可用时，系统不得崩溃，应退回 `template_only` 模式。

---

## 10. 仓库结构

```text
ppg-rag-agent/
  README.md
  pyproject.toml
  .env.example
  config/
    settings.yaml
    field_mapping.yaml
    safety_terms.yaml
    bp_thresholds.yaml
  app/
    __init__.py
    main.py
    api/
      __init__.py
      routes.py
    schemas/
      __init__.py
      measurement.py
      report.py
      rule_result.py
    services/
      __init__.py
      normalizer.py
      validator.py
      rule_engine.py
      retriever.py
      generator.py
      safety.py
      report_builder.py
    agents/
      __init__.py
      workflow.py
    prompts/
      user_report_zh.jinja
      user_report_bilingual.jinja
      safety_review.jinja
  knowledge_base/
    raw/
      guidelines/
      cuffless_ppg/
      lifestyle/
      safety/
    processed/
      chunks.jsonl
    vector_store/
  scripts/
    ingest_kb.py
    make_demo_cases.py
    evaluate_reports.py
  tests/
    test_schema.py
    test_normalizer.py
    test_rule_engine.py
    test_safety.py
    test_report_api.py
    fixtures/
      demo_cases.jsonl
  streamlit_app.py
```

---

## 11. 第一阶段开发任务

### Task 1：建立项目骨架

创建 FastAPI 项目、Pydantic schema、配置文件、测试目录、Streamlit demo 文件。

验收标准：

```bash
pytest
uvicorn app.main:app --reload
```

能够启动服务。

### Task 2：实现输入 Schema

在 `app/schemas/measurement.py` 实现：

1. UserProfile
2. Symptoms
3. PPGMeasurement
4. MeasurementPayload

字段范围：

```text
estimated_sbp: 40-260
estimated_dbp: 30-180
heart_rate: 20-240
signal_quality_score: 0-1
confidence: 0-1
age: 0-120
bmi: >0
capture_duration_sec: >0
```

### Task 3：实现 Field Mapping

在 `app/services/normalizer.py` 实现别名映射，读取 `config/field_mapping.yaml`。

输入可以是 `SBP`、`systolic_bp`、`estimated_sbp`，输出统一为 `estimated_sbp`。

### Task 4：实现 Rule Engine

在 `app/services/rule_engine.py` 实现：

1. quality_result
2. estimated_bp_category
3. emergency_flag
4. special_population_flag
5. recommendation_intents
6. retrieval_intents

### Task 5：实现知识库 ingest

在 `scripts/ingest_kb.py` 实现：

1. 读取 `knowledge_base/raw/**/*.md`
2. 按标题和段落 chunk
3. 生成 embeddings
4. 写入 Chroma 或 FAISS
5. 生成 `chunks.jsonl`

### Task 6：实现 Retriever

在 `app/services/retriever.py` 实现：

1. 根据 retrieval_intents 检索 top-k chunks。
2. 返回带 metadata 的 evidence。
3. 支持空知识库时返回 warning，并启用模板报告。

### Task 7：实现报告生成

在 `app/services/generator.py` 实现两种模式：

1. `template_only`：不依赖 LLM，使用规则和模板生成报告。
2. `llm_rag`：使用 LLM + evidence 生成结构化 JSON。

### Task 8：实现 Safety Agent

在 `app/services/safety.py` 实现硬规则检查：

1. 禁止诊断词。
2. 禁止处方/停药/调药建议。
3. 必须包含 PPG 估算局限说明。
4. 必须包含免责声明。
5. 急症规则触发时必须在报告开头显示急救提示。

### Task 9：实现 API 与 Streamlit Demo

API：`POST /api/v1/reports/generate`  
Demo：用户填写估算血压、心率、信号质量、年龄、基础病、症状，点击生成报告。

### Task 10：测试用例

至少实现以下测试样例：

1. 正常估算值，高质量信号。
2. 估算值偏高，高质量信号。
3. 估算值偏高，低质量信号。
4. 180/120 以上但无症状。
5. 180/120 以上且有胸痛。
6. 使用降压药用户。
7. 糖尿病或肾病用户。
8. 字段别名输入。
9. LLM 不可用，template_only 仍可生成报告。
10. Safety Agent 拦截“确诊/开药/停药”表述。

---

## 12. 评估实验设计

毕业设计中可以评估三种系统：

| 系统 | 说明 |
|---|---|
| LLM-only | 直接把用户输入给大模型生成建议 |
| RAG-only | 检索知识库后生成建议 |
| Rule + RAG + Safety Agent | 本项目方法 |

建议指标：

1. 报告完整性。
2. 事实一致性。
3. 引用准确率。
4. 幻觉率。
5. 医疗安全违规率。
6. 急症识别率。
7. 低质量信号拦截率。
8. 用户可读性评分。
9. 模板模式与 LLM 模式稳定性。

---

## 13. Demo 报告示例

输入：

```json
{
  "estimated_sbp": 145,
  "estimated_dbp": 92,
  "heart_rate": 82,
  "signal_quality_score": 0.86,
  "confidence": 0.68,
  "age": 45,
  "symptoms": {"chest_pain": false, "shortness_of_breath": false}
}
```

期望输出摘要：

```text
本次手指摄像头 PPG 算法估算血压为 145/92 mmHg，属于偏高范围参考值。
需要注意的是，该结果来自 PPG 估算，仅适合作为个人健康趋势参考，不能作为高血压诊断依据。
建议在安静状态下重新采集，并使用经过验证的上臂式电子血压计进行复核。
如果多次复核仍偏高，建议咨询医生。
当前未触发急症症状规则。
```

急症样例：

```json
{
  "estimated_sbp": 185,
  "estimated_dbp": 122,
  "symptoms": {"chest_pain": true}
}
```

期望输出摘要：

```text
本次估算值处于严重偏高范围，且用户报告胸痛症状。请立即寻求当地急救或紧急医疗帮助。PPG 估算值本身不能替代规范测量，但严重症状需要优先处理。
```

---

## 14. 运行命令建议

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
python scripts/ingest_kb.py
uvicorn app.main:app --reload
streamlit run streamlit_app.py
```

环境变量：

```env
LLM_PROVIDER=openai_or_local_or_mock
LLM_API_KEY=xxx
EMBEDDING_MODEL=bge-small-zh-v1.5
REPORT_MODE=template_only_or_llm_rag
VECTOR_STORE=chroma_or_faiss
```

---

## 15. 验收标准

MVP 验收标准：

1. 可以接收小程序结构化输入。
2. 可以完成字段归一化。
3. 可以根据规则输出质量判断、估算血压范围、急症提示和特殊人群提示。
4. 可以检索知识库并返回 evidence。
5. 可以生成 JSON + Markdown 报告。
6. Safety Agent 能拦截诊断、处方、停药和过度承诺。
7. LLM 不可用时，template_only 模式仍能运行。
8. 至少 10 个测试样例全部通过。
9. 报告中必须明确：PPG 估算结果仅供健康趋势参考，不能替代医生诊断和规范血压测量。

---

## 16. 毕业论文可写的创新点

1. 面向 PPG 估算血压结果的结构化医学解释框架。
2. 规则引擎、RAG 检索和 Safety Agent 结合的可信健康建议生成流程。
3. 对比 LLM-only、RAG-only 和 Rule+RAG+Safety 的安全性与可追溯性。
4. 针对低质量信号、急症症状、特殊人群和用药安全的医疗边界控制。
5. 面向小程序场景的轻量化健康报告生成系统。

---

## 17. 给 Codex 的最终实现要求

请优先实现可运行 MVP，不要追求复杂 Agent 框架。第一版必须保证：

1. 规则引擎稳定。
2. 输出格式稳定。
3. Safety Agent 稳定。
4. LLM 不可用也能输出报告。
5. 后续再扩展 LangGraph/LangChain/LlamaIndex。

推荐第一版技术栈：

```text
Python 3.11+
FastAPI
Pydantic v2
PyYAML
Jinja2
pytest
Chroma 或 FAISS
sentence-transformers 或 bge-small-zh-v1.5
Streamlit
可选：LangGraph / LangChain / LlamaIndex
```

---

## 18. 知识库种子来源

开发时可先把以下来源摘要化为 Markdown 放入 `knowledge_base/raw/`，并保留 source metadata：

1. American Heart Association. Home Blood Pressure Monitoring. 重点：上臂式袖带、腕式/手指设备可靠性、复测和记录建议。  
   https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings/monitoring-your-blood-pressure-at-home
2. American Heart Association. Understanding Blood Pressure Readings. 重点：血压分类和严重高血压/急症提示。  
   https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings
3. American Heart Association. Cuffless Devices for the Measurement of Blood Pressure. 重点：PPG/无袖带设备是间接估算，真实场景可靠性和临床用途仍需验证。  
   https://professional.heart.org/en/science-news/cuffless-devices-for-the-measurement-of-blood-pressure
4. Chinese Guidelines for the Prevention and Treatment of Hypertension (2024 revision). 重点：中文场景指南依据。  
   https://pubmed.ncbi.nlm.nih.gov/40151633/

注意：知识库中不得把任何指南内容改写成“本系统可以诊断”。所有结论必须落在“估算值解释、趋势参考、复测建议、健康教育和就医提醒”。
