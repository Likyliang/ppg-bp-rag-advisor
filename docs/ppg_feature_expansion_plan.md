# PPG 特征扩展计划

## 目标边界

本计划用于扩展小程序结构化输入中的 PPG 采集与波形质量特征，并让 RAG-Agent 能解释这些特征对本次估算可信度的影响。

必须保持边界：

- 只解释 PPG 信号质量、采集条件、算法置信度和复测必要性。
- 不把 PPG 特征解释成血压估算准确性的验证。
- 不用 PPG 特征替代上臂式血压计、动态血压监测或医生诊断。
- 不根据 PPG 特征给出诊断、处方、调药或停药建议。

## 当前知识库覆盖

截至当前版本，processed chunks 中与 PPG 信号质量、无袖带局限和研究背景相关的 chunks 约 222 个，主要覆盖：

- `measurement_quality`：运动伪影、接触压力、环境光、肤色/光学传感误差、测量部位、采集流程。
- `cuffless_ppg_limitations`：无袖带/PPG 血压估算的监管边界、校准限制、不能替代规范血压测量。
- `research_background`：PPG/iPPG、可穿戴光学传感器、PTT/PAT 类无袖带估算背景。

已在库内可优先使用的来源包括：

- `aha_cuffless_bp_scientific_statement`
- `fda_cuffless_nibp_draft_guidance`
- `parati_2026_esc_cuffless_bp_monitoring_statement`
- `mukkamala_2015_ptt_bp_monitoring_theory_practice`
- `mukkamala_2017_ptt_calibration_error_limits`
- `charlton_2022_ppg_best_practices`
- `charlton_2025_wrist_ppg_signal_quality`
- `desquins_2022_ppg_quality_assessment_survey`
- `arguello_prada_2024_ppg_motion_artifact_detection_review`
- `chandrasekhar_2020_contact_pressure_cuffless_bp`
- `teng_2004_contact_force_ppg`
- `shirbani_2020_ambient_light_skin_tone_vpg`
- `shi_2022_skin_pigmentation_pulse_oximetry_systematic_review`
- `sjoding_2020_racial_bias_pulse_oximetry`
- `frontiers_2019_ppg_measurement_site_waveform`
- `lee_2013_rgb_reflection_ppg_motion_hr`

## 建议新增的结构化输入字段

### P0：先接入，直接影响报告口径

这些字段适合进入近期 demo，因为它们能清楚支持“复测、重新采集、保守解释”：

| 字段 | 含义 | 报告用途 | 风险边界 |
| --- | --- | --- | --- |
| `signal_quality_score` | 上游信号质量分 | 判断是否可解释、是否建议重采 | 不能等同于血压准确 |
| `confidence` | 上游算法置信度 | 低置信度时弱化结论 | 不能承诺高置信度就准确 |
| `capture_duration_sec` | 采集时长 | 过短时提示重新采集 | 不给出诊断判断 |
| `motion_artifact_score` | 运动伪影/手指移动评分 | 提示保持静止、重新采集 | 不解释成疾病风险 |
| `finger_coverage_score` | 手指覆盖完整度 | 提示正确覆盖摄像头 | 不解释血压高低 |
| `contact_pressure_level` | 接触压力偏高/偏低/合适 | 提示手指按压力度影响波形 | 不估计真实血压偏差 |
| `ambient_light_level` | 环境光干扰 | 提示避开强光、稳定光照 | 不用于诊断 |

### P1：第二批接入，用于更细解释

这些字段可以展示技术深度，但建议先只放在“研发审计/证据依据”页，不直接面向普通用户：

| 字段 | 含义 | 报告用途 |
| --- | --- | --- |
| `sampling_rate_hz` | 采样率 | 判断波形采集条件是否满足后续分析 |
| `valid_pulse_count` | 有效脉搏周期数 | 判断本次波形是否足够稳定 |
| `peak_detection_confidence` | 峰值检测置信度 | 解释波形识别是否可靠 |
| `baseline_wander_score` | 基线漂移 | 说明手指移动、呼吸或光照可能影响信号 |
| `clipping_ratio` | 饱和/截断比例 | 说明过曝、过暗或传感器饱和 |
| `pulse_amplitude_cv` | 脉搏幅度变异系数 | 说明每个周期波形是否稳定 |
| `ibi_cv` | 脉搏间期变异系数 | 说明节律稳定性；必要时提示重新采集 |

### P2：研究展示字段，不建议直接给用户看

这些字段偏算法研究，适合论文或组会讲“未来可接入的特征”，不建议直接转成用户建议：

| 字段 | 含义 | 使用方式 |
| --- | --- | --- |
| `upstroke_time_ms` | 上升支时间 | 仅作为波形形态研究背景 |
| `pulse_width_ms` | 脉搏宽度 | 仅用于算法特征说明 |
| `dicrotic_notch_detected` | 重搏切迹是否可见 | 仅说明波形质量/形态，不判断疾病 |
| `reflection_index` | 反射指数 | 研究背景，不做个体健康结论 |
| `stiffness_index` | 刚度相关指数 | 不用于诊断动脉硬化 |
| `pat_ms` / `ptt_ms` | 脉搏到达/传导时间 | 只解释无袖带估算背景和校准限制 |
| `ood_score` | 分布外评分 | 说明算法可能不适用于该输入 |

## 特征到 RAG 检索意图的映射

| 特征异常 | 检索意图 | 优先 evidence |
| --- | --- | --- |
| 信号质量低、置信度低 | `signal_quality`, `cuffless_ppg_limitations`, `remeasurement` | AHA/FDA 无袖带边界，PPG 最佳实践 |
| 采集时长短、有效脉搏少 | `signal_quality`, `remeasurement` | PPG 采集与处理最佳实践 |
| 运动伪影高 | `signal_quality`, `research_background` | motion artifact review、运动状态 PPG 研究 |
| 接触压力异常 | `signal_quality`, `cuffless_ppg_limitations` | contact pressure / contact force PPG 研究 |
| 环境光异常 | `signal_quality`, `research_background` | imaging/video PPG 光照研究 |
| 肤色/光学公平性相关 | `signal_quality`, `research_background`, `disclaimer` | optical sensing/pulse oximetry fairness 证据 |
| 波形形态不稳定 | `signal_quality`, `research_background` | PPG waveform/site/quality assessment 综述 |
| PAT/PTT 校准相关 | `cuffless_ppg_limitations`, `research_background` | PTT 理论与校准误差、监管边界 |

## 用户报告表达原则

用户可读报告里不要堆特征名。建议转换成自然语言：

- “这次采集时间偏短，所以先重新采集一次。”
- “波形里可能有手指移动或按压力度不稳定的影响，所以这次数值只能当趋势提醒。”
- “光照或手指覆盖可能影响摄像头采集，建议在稳定光线下重新测一次。”
- “这些特征只能说明本次采集是否稳定，不能证明血压估算一定准确。”

研发审计页可以保留完整字段：

- 原始字段值
- 触发的质量规则
- 检索到的证据 source_id
- 生成报告时降级/保守处理的原因

## 知识库扩展优先级

### P0：先补“特征字典 chunks”

为每类 PPG 特征写短 chunks，字段包括：

- 特征名称
- 上游含义
- 可能受哪些采集因素影响
- 报告里允许怎么解释
- 报告里禁止怎么解释
- 对应 evidence source_id

这类 chunks 属于本项目治理说明，`allowed_uses` 应限制在：

- `signal_quality`
- `cuffless_ppg_limitations`
- `remeasurement`
- `research_background`
- `disclaimer`

### P1：补充 fulltext 质量审计后再扩展

fulltext chunks 已能跑 pilot，但部分中文 PDF 存在编码噪声。下一步应先生成 `fulltext_quality_audit.json`，把来源分成：

- Tier 1：文本质量好，可进入 embedding pilot。
- Tier 2：有明显编码/OCR 噪声，先修复再用。
- Tier 3：质量差或版权/授权不清，暂不进入检索。

### P2：新增黄金查询与评估

新增 PPG 特征相关 golden queries，例如：

- “PPG 接触压力过大 会影响估算吗”
- “手指移动导致信号质量低 需要怎么处理”
- “环境光很强 摄像头 PPG 还能信吗”
- “采集 8 秒 PPG 血压估算能不能看”
- “PAT/PTT 可以证明血压准确吗”
- “波形切迹不清楚 是否要重新测”

评估指标不要看“血压预测是否正确”，而看：

- 是否检索到 `signal_quality` 或 `cuffless_ppg_limitations` 证据。
- 是否没有把 PPG 特征说成诊断依据。
- 是否建议规范复测或重新采集。
- 是否引用高可信来源处理安全边界。

## Demo 接入顺序

1. Schema 先加 P0 字段，保持 `extra="ignore"` 兼容旧输入。
2. Rule engine 只用 P0 字段做质量降级和复测建议。
3. RAG 检索增加特征触发 query，例如“PPG contact pressure signal quality”。
4. 用户报告用自然语言解释，不展示“触发规则/allowed_uses/source boost”等开发词。
5. 研发审计页展示字段、规则、证据来源，方便组会讲原理。

## 汇报口径

可以这样讲：

“后续小程序会提供更丰富的 PPG 采集特征。我们不会用这些特征证明血压估算准确，而是把它们作为质量控制和保守解释依据：如果出现采集时长短、运动伪影、接触压力异常或光照干扰，系统会降低解释强度，建议重新采集或用上臂式血压计复核。知识库会补充 PPG 信号质量、接触压力、运动伪影、环境光、肤色/光学传感局限和 PAT/PTT 校准限制等内容，用于支撑这些解释。”

