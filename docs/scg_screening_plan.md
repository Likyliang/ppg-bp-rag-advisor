# SCG/心振 + PPG 排查建议（screening suggestions）设计

## 这一步在做什么

上游小程序之后会提供更丰富的 PPG 特征以及 SCG（seismocardiography，心脏机械振动 / “心振”）信息。
本设计在原有“保守趋势解释”之上，新增一个**排查建议层（建议进一步排查）**：

- 输入：PPG 节律/变异特征、SCG 心振时相特征、心率、估算血压分级。
- 输出：“这些信号**可能**与某类问题有关，**建议到医院做某项检查**进一步排查”。
- 关键定位：这是 **screening / triage（排查与分诊）建议**，**不是诊断**。

> 一句话边界：系统可以说“信号不规则，**可能**与心律不齐有关，**建议做心电图排查**”；
> 永远不会说“你患有 / 确诊 X”或“不用看医生”。

## 安全口径：我们放开了什么，保留了什么

“解开安全限制”被实现为**收窄而非移除**护栏——把原来“完全不谈疾病”改为“只能以
带不确定性 + 带就医指引的排查建议形式谈疾病”。

| 维度 | 原状态 | 现状态 |
| --- | --- | --- |
| 确诊 / “你患有 X” / “已经是高血压” | 阻断 | **仍然阻断**（`diagnostic_patterns`） |
| “不用复测 / 无需就医 / 不用看医生” | 阻断 | **仍然阻断**（`diagnostic_patterns` + `screening_overreach_patterns`） |
| 调药 / 停药 / 加减剂量 | 阻断 | **仍然阻断**（`medication_change_patterns`） |
| 设备过度承诺（替代血压计/保证准确） | 阻断 | **仍然阻断**（`device_overclaim_patterns`） |
| “肯定是 / 一定是 X 病”等确定性断言 | （架构上不产出） | **新增明确阻断**（`screening_overreach_patterns`） |
| “可能与 X 有关，建议就医排查 X” | 架构上从不产出 | **新增允许**，但必须满足：对冲措辞 + 就医指引 + 置信度≤moderate |

护栏从“黑名单（禁止某些话）”升级为**对新能力的正向校验**：每条排查建议必须
（1）含不确定性措辞（可能/提示/不能确定…），（2）含就医/检查指引（心电图/门诊/就医…），
（3）置信度被硬上限到 `moderate`。任何不达标的建议在 `review_screening_suggestions`
中被丢弃，不会进入用户报告。急症情境下排查建议整段抑制，120/急诊提示置顶不变。

## 进展（2026-06-12）

- Tier-1 已落地：`RhythmFeatures` 增 Poincaré 描述符并入 `arrhythmia_screening`；
  `PPGMorphologyFeatures` / `PPGDerivedFeatures` 骨架就绪（待 Tier-2 消费）。
- Tier-2（SCG）已落地：新增 `valvular_screening`（主动脉瓣狭窄，置信度 low）；
  `CardiacVibrationFeatures` 增 `beat_amplitude_cv` 并入 `arrhythmia_screening`。
- 知识库：7 篇 SCG 诊断性来源入库（research_background），见
  [ppg_scg_diagnostic_features_survey.md](ppg_scg_diagnostic_features_survey.md)。
- 引用：`cite_sources` 让每条排查建议引用其确切支撑来源；workflow 增专门排查证据检索。
- Tier-2 PPG 血管老化已落地：`vascular_aging_screening`（SDPPG 老化指数/b·a + SI/RI，
  置信度 low，引用 VascAgeNet/MDPI/Kim）；Streamlit 增形态/导数输入 + 研发审计视图。
- Demo：Streamlit 可输入心振/节律/形态特征并展示排查建议（结构化表格 + 管线审计）。
- 待办：阈值用标注 ECG/超声/PWV 队列校准；OSA（Tier-2 PPG）待夜间 SpO₂/PWA 数据。

## 数据契约（新增结构化输入）

向后兼容：所有字段可选，`extra="ignore"`，旧 payload 不受影响。

### `rhythm`（脉搏节律 / 变异，来自 PPG 脉搏串）

| 字段 | 含义 |
| --- | --- |
| `available` | 是否提供了节律分析 |
| `pulse_rhythm` | `regular` / `irregular` / `unknown`（支持“不齐/规则”等别名） |
| `ibi_cv` | 脉搏间期变异系数（SD/mean），越大越不规则 |
| `ectopic_beat_ratio` | 疑似早搏（PAC/PVC）占比 |
| `pulse_pause_detected` | 是否检测到脉搏间歇 |
| `hrv_sdnn_ms` / `hrv_rmssd_ms` | HRV 时域指标 |
| `valid_beat_count` | 可分析心搏数（节律建议的门槛） |

### `cardiac_vibration`（SCG / 心振；别名 `scg`）

| 字段 | 含义 |
| --- | --- |
| `available` | 是否提供了 SCG |
| `signal_quality_score` / `signal_quality_label` | SCG 信号质量 |
| `motion_artifact_score` | 运动伪影 |
| `sensor_site` | 采集部位（sternum/chest/wrist…） |
| `pep_ms` | 射血前期（pre-ejection period） |
| `lvet_ms` | 左室射血时间 |
| `ao_ac_interval_ms` | 主动脉开放→关闭间期 |
| `s1_s2_amplitude_ratio` | 第一/第二心音振幅比 |
| `ptt_ms` | SCG↔PPG 融合得到的脉搏传导/到达时间 |

### 根字段

- `enable_screening_suggestions`（默认 `false`）：本次请求是否开启排查建议。

归一化：`app/services/normalizer.py` 同时支持嵌套对象与**无歧义**的扁平键
（如 `pep_ms`、`pulse_rhythm`）；与 PPG measurement 同名的字段（如 `signal_quality_label`）
只能走嵌套对象，避免混淆。

## 特征 → 排查条件 → 证据（`config/screening_rules.yaml`）

| 条件 id | 触发信号 | 置信度 | 排查指引 |
| --- | --- | --- | --- |
| `arrhythmia_screening` | 节律不规则 / `ibi_cv`≥0.15 / 早搏比≥0.05 / 脉搏间歇 | moderate | 心内科或全科门诊做心电图（ECG），必要时 Holter |
| `tachycardia_eval` | 静息心率≥110 | low | 多次复核仍偏快或伴不适 → 门诊评估 |
| `bradycardia_eval` | 静息心率≤45 | low | 多次复核仍偏慢或伴不适 → 门诊评估 |
| `hypertension_workup` | 估算血压进入偏高/明显偏高/严重范围 | moderate | 规范上臂式复核+连续记录，多次仍偏高→就医评估 |
| `cardiac_timing_research` | SCG `pep_ms`≥140 或 `ptt_ms`≤180（且 SCG 质量好） | low | 研究性观察，常规体检/门诊时与医生讨论 |

门槛与抑制：
- 节律类条件要求 `rhythm.available` 且 `valid_beat_count ≥ min_valid_beats`（默认 20）。
- `arrhythmia_screening` / `hypertension_workup` 要求 PPG 质量可用（差信号先复测，不做排查解释）。
- `cardiac_timing_research` 要求 SCG 质量好，并永远封顶在 low + 强对冲。
- 急症触发时整段排查建议被抑制。

证据：每个条件带 `retrieval_intents` / `allowed_uses`，在 workflow 中并入检索意图。
当前治理知识库以高血压 / PPG 信号质量为主，心律失常类证据尚少——排查建议为规则驱动、
可独立成立（不强依赖引用）；KB 补充见下方路线图。

## 代码落点

- `app/schemas/measurement.py`：`RhythmFeatures` / `CardiacVibrationFeatures` + 根字段。
- `app/schemas/screening.py`：`ScreeningSuggestion` / `ScreeningResult`。
- `config/screening_rules.yaml`：条件、阈值、措辞、就医指引。
- `app/services/screening.py`：`run_screening()`、置信度封顶、触发/门槛评估。
- `app/services/safety.py`：`screening_overreach_patterns` 阻断 + `review_screening_suggestions()` 正向校验。
- `app/services/generator.py`：`inject_screening_markdown()` 在 **LLM 阶段之后**逐字注入排查段（不被改写、幂等、置于参考文献之前）。
- `app/agents/workflow.py`：计算→校验→并入检索→注入。

## Demo / 使用

```bash
# 默认 .env 是 llm_rag + deepseek；排查建议逐字注入，不被 LLM 改写
python scripts/run_structured_report_demo.py \
  --input examples/miniapp_payload_screening.json --prefix screening_demo
```

最小开启方式：payload 里 `enable_screening_suggestions: true` + 提供 `rhythm` / `cardiac_vibration`。
默认关闭时，报告与之前逐字节一致。

## 路线图

1. **KB 扩展**：补充房颤/心律失常 PPG 筛查、SCG 研究综述等治理 chunks，给排查建议提供引用。
2. **校准**：用真实标注（如同步 ECG）评估各触发阈值的命中/误报，按数据回填 `screening_rules.yaml`。
3. **Advisor 联动**：在随访对话里把排查建议变成可追问的话题（“要不要我解释一下心电图检查？”）。
4. **streamlit 演示页**：增加排查建议开关与“研发审计”视图（原始特征→触发条件→被拦截项）。
5. **评估指标**：排查建议不看“诊断是否正确”，而看是否对冲、是否给就医指引、是否封顶置信度、急症是否抑制。
