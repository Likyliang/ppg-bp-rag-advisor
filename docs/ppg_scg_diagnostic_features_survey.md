# PPG / SCG 诊断性特征文献调研

> 目的：调研论文中用于**识别/筛查心血管及相关病症**的 PPG 与 SCG（心振）特征，
> 形成「特征 → 可筛查条件 → 确诊性检查」的映射，用来扩展排查建议引擎
> （`config/screening_rules.yaml`）。
>
> **边界（沿用 [scg_screening_plan.md](scg_screening_plan.md)）**：这些特征用于给出
> **“建议进一步排查”的分诊提示，不是诊断**。消费级指尖摄像头 PPG / 手机贴胸 SCG
> 的可靠性有限、混杂因素多，论文里的高准确率多来自受控数据集与研究级传感器，
> 不能直接平移成对个体的确定性结论。每条都需对冲措辞 + 就医指引 + 置信度封顶。

---

## 实现状态（2026-06-12）

已从“调研”落地为可运行产品：

- **知识库**：7 篇 SCG/心振诊断性来源已入治理 KB（`research_background`），见
  [source_catalog_extra.yaml](../knowledge_base/sources/source_catalog_extra.yaml) 与
  `knowledge_base/raw/expanded/research_context/`。质量门禁不变（precision@5≥0.95、
  每 topic≥3 源、无 unsafe leakage）。
- **排查引擎条件**：`arrhythmia_screening`（PPG 节律 + Poincaré + SCG 逐拍幅值）、
  `cardiac_timing_research`（PEP/PTT）、`valvular_screening`（主动脉瓣狭窄，置信度 low）、
  `vascular_aging_screening`（SDPPG 老化指数/b·a + SI/RI，置信度 low）、
  `tachycardia/bradycardia_eval`、`hypertension_workup`。
- **精确引用**：每个 SCG 条件经 `cite_sources` 引用其确切支撑来源（心律不齐→
  机械心动图房颤；机械时相→Taebi/Shandhi；瓣膜→Yang 主动脉瓣狭窄），不按
  allowed_use 误引无关文献；workflow 增专门的排查证据检索保证来源可被引用。
- **网页 Demo**：Streamlit 侧栏可输入心振/节律特征并开启排查建议，报告正文 +
  结构化表格展示（AppTest 验证无异常）。

### 本轮新增 SCG 病症文献要点（已入库）

| 病症 | 关键 SCG 特征 / 发现 | 来源 |
| --- | --- | --- |
| 主动脉瓣狭窄（瓣膜） | AO 开放延迟；心动机械形态 + HRV，研究数据集识别率高（报 95–100%） | Yang 2021 (Sci Rep) |
| 房颤 | 手机机械心动图(SCG+GCG)多类分类，逐拍幅值变异；可检“静默”阵发性 AF | Mehrang 2018 (Sci Rep) |
| 心衰（监测） | 可穿戴 SCG+ML 区分代偿/失代偿；估计 PCWP/肺动脉压 | Inan 2018；Shandhi 2022 |
| 失血/低血容量 | SCG+PPG+ECG 多模态评估血容量减少（急救/创伤场景，非消费级） | Hersek 2020 (Sci Adv) |
| 相机/视频心振 | 基于计算机视觉的非接触 SCG，与摄像头路线互补 | Zhang 2023 (Sci Rep) |

> 仍为**排查建议（research_background）**，不是诊断；瓣膜/心衰/失血等单次结论
> 由医生与确诊性检查（超声心动图、心电图、临床评估）决定。

---

## 1. PPG 特征族（taxonomy）

### 1.1 时域形态特征（single pulse morphology）
PPG 单拍有四个基准点：起点(foot)、收缩峰(systolic peak)、重搏切迹(dicrotic notch)、
舒张峰(diastolic peak)。重搏切迹与舒张峰是外周反射波，受动脉硬度/血管阻力与顺应性影响。

| 特征 | 定义 | 反映什么 | 指尖摄像头可提取性 |
| --- | --- | --- | --- |
| 收缩峰幅值 systolic peak | 起点后收缩射血的最大峰 | 射血/灌注 | 高 |
| 舒张峰幅值 diastolic peak | 舒张峰与起点高度差 | 外周反射、顺应性 | 中（强光/低质量时不稳） |
| 重搏切迹 dicrotic notch | 主峰后第一个局部极小 | 主动脉瓣关闭/反射；糖尿病/老化时变浅或消失 | 中 |
| 脉宽 pulse width | 在某高度百分比处的宽度 | 外周阻力 | 中 |
| 上升时间 crest time (CT) | 起点到收缩峰的时间，用于鉴别心血管病 | 大动脉硬度 | 高 |
| 脉搏面积 pulse area | 单拍面积；糖尿病时下降 | 整体波形能量 | 中 |

### 1.2 血管硬度/反射指数
- **Stiffness Index (SI)** = 身高(m) / 收缩峰到舒张峰的时间 ΔT(s)，与平均动脉压、年龄相关。
- **Reflection Index (RI)** = 舒张峰/收缩峰高度比(%)，与动脉硬度正相关。
- **Augmentation Index (AIx)** = 反射波抬高前向压力波峰的程度，反映血管硬度与反射。

来源综述：VascAgeNet「从 PPG 评估血管年龄」（AJP-Heart 2022）、MDPI Sensors 2023「PPG 评估动脉硬度」。

### 1.3 导数特征（VPG / APG-SDPPG）
- **一阶导 VPG**：最大上升斜率（max slope）等。
- **二阶导 APG / SDPPG**：a、b、c、d、e 五个波。常用比值：
  - **b/a**（也叫外周增强指数 / aging index 的核心项）：随年龄/动脉硬化升高；
  - **d/a**：年轻人偏高，随龄下降（动脉硬化↑、反射特性改变）；
  - **老化指数** = (b−c−d−e)/a。
- Takazawa 经典工作：SDPPG 老化指数与年龄相关 **r≈0.80**，且与脉搏波速度（PWV）一致地反映血管老化/动脉粥样硬化。

### 1.4 节律 / 变异（PRV / HRV，来自脉搏间期 IBI 序列）
- 时域：SDNN、RMSSD、pNN50；频域：LF/HF。
- **Poincaré 图特征**：簇数(number of clusters)、IBI 平均步进(mean stepping increment)、点相对对角线的离散度(dispersion)——AF 时呈“irregularly irregular”。

### 1.5 PPG 衍生生理量
- SpO₂（红光/红外比值）、呼吸率（基线/幅值/频率调制 RIIV）、灌注指数(PI)、
  与 ECG/SCG 联合得到的 PTT/PAT（用于无袖带血压）。

---

## 2. PPG → 可筛查条件（文献映射）

| 条件 | 关键 PPG 特征 | 论文证据要点 | 确诊性检查 | 可信层级（消费级指尖 PPG） |
| --- | --- | --- | --- | --- |
| **心律不齐 / 房颤** | 节律不规则、PRV、Poincaré（簇数/步进/离散度） | HRV+Poincaré 检测 AF：敏感度 ~91.4% / 特异度 ~92.9%；可穿戴 PPG 已成 AF 连续监测主流 | 心电图 / 动态心电图(Holter) | **中**（已在引擎） |
| **高血压 / 血压偏高** | 形态特征、SI/RI/AIx、PTT/PAT | PPG 形态可做高血压早筛/风险分层 | 规范上臂式血压计 / 动态血压 | 中（已在引擎，规范复核为主） |
| **动脉硬化 / 血管老化** | SDPPG b/a、d/a、老化指数、SI、RI、CT | 老化指数与年龄 r≈0.80；与 PWV 一致 | 颈动脉超声 / PWV / 临床评估 | **低–中**（研究性，依赖导数特征质量） |
| **糖尿病 / 血糖异常** | 重搏切迹消失、PPG 面积↓、老化指数↑、b/a、HRV、倒谱 | 多法 AUC≈0.69–0.8；**重要陷阱**：合并高血压会削弱 b/a 在糖尿病/非糖尿病间的区分（medRxiv 2022） | 空腹血糖 / HbA1c / OGTT | **低**（混杂强，建议谨慎或仅研究展示） |
| **阻塞性睡眠呼吸暂停 OSA** | 氧减指数 ODI、脉搏波幅 PWA 下降（交感唤醒）、脉搏间期 PPI | PPG 衍生呼吸事件指数与 PSG 的 AHI **r=0.935**；ODI 检测 OSA 敏感度 0.838 / 特异度 0.855 | 多导睡眠监测(PSG) / 家庭睡眠监测 | 中（需 SpO₂/夜间长时段，非单次指尖一次测量） |
| **外周动脉疾病 PAD** | PPG 形态变异指数 | 与踝臂指数(ABI)相关 | ABI / 血管超声 | 低（需多部位/特定采集） |
| **整体心血管事件风险** | 整体 PPG 波形（形态+导数） | PPG 波形可预测 CVD 事件（JAHA 2024） | 临床综合评估 | 低（人群级，不宜个体化下结论） |

---

## 3. SCG / 心振 特征族

### 3.1 基准点（fiducial points，对应机械事件）
收缩期：**AS** 房缩峰、**MC** 二尖瓣关闭、**AO** 主动脉瓣开放、**RE** 快速射血峰；
舒张期：**AC** 主动脉瓣关闭、**MO** 二尖瓣开放、**RF** 快速充盈峰；**IM/IC** 等容期运动。

### 3.2 收缩时相间期（STI，反映心室机械性能）
| 间期 | 定义 | 临床意义 |
| --- | --- | --- |
| **PEP** 射血前期 | Q 波→AO | 收缩力标志（与心率无关）；收缩力↑时 PEP↓ |
| **IVCT** 等容收缩时间 | MC→AO | 早期收缩功能 |
| **LVET** 左室射血时间 | AO→AC | 收缩功能；与收缩力、心率相关 |
| **IVRT** 等容舒张时间 | AC→MO | 舒张功能 |
| **QS2** 电机械收缩总时程 | — | 整体收缩时长 |
| **PEP/LVET 比** | — | 常用收缩力综合指标 |

### 3.3 幅值 / 能量 / 形态
- RMS 幅值（运动/心输出量↑时整体幅值↑）；各频段(0–100 Hz)能量分布；
- 3D 矢量轨迹（用于房扑等节律分析）；峰度等统计量。

来源：Taebi 等「Recent Advances in Seismocardiography」(2019)；Crow/Sørensen「Definition of Fiducial Points in the Normal SCG」；STI 自动识别(Sci Rep 2016)。

---

## 4. SCG → 可筛查条件（文献映射）

| 条件 | 关键 SCG 特征 | 论文证据要点 | 确诊性检查 | 可信层级（手机贴胸/贴片 SCG） |
| --- | --- | --- | --- | --- |
| **心力衰竭状态/失代偿监测** | PEP、STI、姿势变化、图相似度；融合 ML | 可穿戴 SCG+ML 区分代偿/失代偿(Inan 2018)；估计 PCWP/肺动脉压(可行性研究)；SEISMIC-HF(AHA24) | 超声心动图 / 右心导管 / 临床 | 中（**监测**为主，需个体基线，非单次筛查） |
| **冠心病 / 心肌缺血** | 球囊扩张时基准点变化；缺血前的充盈/瓣膜/射血改变 | 缺血可先于症状在 SCG 显现；MCG 可识别缺血 | 冠脉造影 / 负荷试验 | 低（研究性） |
| **瓣膜病** | 各瓣膜听诊区形态差异；可替代心音图监测 | 四瓣区 SCG 形态显著不同 | 超声心动图 | 低（研究性） |
| **房颤 / 房扑** | 逐拍幅值变异、SCG+ECG 电机械延迟、3D 轨迹 | 手机 MCG（SCG+GCG）AF 检测准确率高（综述报 ~98.7% SVM）；可检测“静默”阵发性 AF | 心电图 / Holter | 中（贴胸采集，研究→临床过渡中） |
| **呼吸状态** | 形态随肺容积变化 | 呼吸周期分类 ~95.4% | — | 中 |
| **心肌收缩力 / 整体心功能** | PEP↓、LVET、RMS 幅值与心输出量相关 | 运动时幅值↑、PEP↓ | 临床/超声 | 低–中（趋势性） |

> 心振的临床价值更多在**纵向监测趋势**（如心衰患者每天贴片测 STI 变化），
> 而非对陌生个体做一次性筛查；引擎里应体现“需基线/趋势”的限制。

---

## 5. PPG + SCG 融合特征

- **PTT/PAT → 无袖带血压**：PPG 与 SCG（AO 点）或 ECG 的时间差；本项目已有 `ptt_ms`，
  仅用于无袖带估算背景与校准限制，不证明血压准确。
- **PEP（SCG）+ PAT（PPG）**：分离“电机械延迟”与“血管段传导”，提升 BP/收缩力解读。
- **PCWP/肺动脉压估计**：SCG+PPG+ECG 贴片 + ML，与金标准压力相关（心衰监测研究）。
- **电机械延迟（SCG vs ECG）**：AF 时异常，可作为多模态 AF 线索。

---

## 6. 对接 screening 引擎的建议（分层）

当前引擎条件：`arrhythmia_screening`、`tachycardia_eval`、`bradycardia_eval`、
`hypertension_workup`、`cardiac_timing_research`。建议：

### 第一梯队（证据强、特征易得、建议优先接入）
1. **强化 `arrhythmia_screening`**：把 Poincaré 特征（簇数、IBI 步进、离散度）纳入触发，
   与现有 `pulse_rhythm/ibi_cv/ectopic_beat_ratio/pulse_pause` 互补。置信度 moderate。
   需上游补字段：`rhythm.poincare_cluster_count`、`rhythm.poincare_dispersion`。
2. **`osa_screening`（睡眠呼吸暂停，条件依赖夜间/SpO₂ 数据）**：触发 = 氧减指数 ODI 偏高
   + 脉搏波幅 PWA 周期性下降。置信度 moderate；指引转诊做睡眠监测(PSG/家庭睡眠监测)。
   需上游补字段：`ppg_derived.spo2`、`ppg_derived.odi`、`rhythm.pwa_drop_index`。
   **注意**：仅在提供了夜间/连续数据时启用，单次指尖测量不触发。

### 第二梯队（研究性、强对冲、置信度封顶 low）
3. **`vascular_aging_screening`（血管老化/动脉硬化）**：触发 = SDPPG 老化指数 / b/a / SI / RI / CT
   超出同龄参考。置信度 low；指引“可在体检/门诊与医生讨论血管健康、必要时测 PWV/颈动脉超声”。
   需上游补字段：`ppg_morphology.sdppg_aging_index`、`b_a_ratio`、`stiffness_index`、`reflection_index`、`crest_time_ms`。
4. **`hf_monitoring_note`（心衰趋势，仅对有基线/已知患者）**：触发 = SCG STI/PEP 较个体基线显著变化。
   置信度 low；明确写“需基线与连续监测，不能单次判断”。需 `cardiac_vibration` 趋势 + 基线。

### 暂不接入（混杂强 / 伦理敏感 / 可靠性不足）
- **糖尿病**：b/a 受合并高血压削弱（medRxiv 陷阱），指尖 PPG 个体筛查可靠性低；
  作为一个面向高血压人群的应用，不宜对个体提示“可能糖尿病”。最多在研发审计页做研究展示。
- **CAD/瓣膜病/MI 的 SCG 单次筛查**：研究级，假阳性代价高，暂不面向用户产出排查建议。

### 统一原则
- 所有新条件复用现有安全校验（对冲 + 就医指引 + 置信度≤moderate；`review_screening_suggestions` 丢弃不合规项）。
- 需要新输入字段时，先扩 `RhythmFeatures` / `CardiacVibrationFeatures` 或新增 `PPGMorphologyFeatures` / `PPGDerivedFeatures` 模型（`extra="ignore"` 向后兼容）。
- 触发阈值先用文献区间占位，**必须**用带标注的真实数据校准后再上线（见 scg_screening_plan 路线图）。

---

## 7. 重要 caveats

- **研究级 vs 消费级**：论文高准确率多来自受控采集 + 研究级传感器 + 干净数据集；
  指尖摄像头 PPG / 手机贴胸 SCG 受运动、接触压力、光照、肤色光学公平性影响，误差更大。
- **混杂因素**：年龄、高血压、用药、体温、情绪/咖啡因都会改变 PPG/SCG 形态——
  单特征不足以归因到某病，必须保留“可能/建议排查”的口径。
- **监测 ≠ 筛查**：SCG 的强项是对**已知患者**做纵向趋势监测（如心衰），而非对陌生个体一次性筛查。
- **为什么是排查不是诊断**：这正是本项目两级安全护栏的依据——可提示“去查什么”，不下“你有什么”。

---

## Sources

PPG 形态与疾病检测综述：
- [Prediction of CVD Events From the PPG Waveform (JAHA 2024)](https://www.ahajournals.org/doi/full/10.1161/JAHA.124.040237)
- [Quality Assessment and Morphological Analysis of PPG in Daily Life (Frontiers 2022)](https://www.frontiersin.org/journals/digital-health/articles/10.3389/fdgth.2022.912353/full)
- [PPG Signal Processing and Synthesis (Charlton, chapter PDF)](https://peterhcharlton.github.io/publication/ppg_sig_proc_chapter/PPG_sig_proc_Chapter_20210612.pdf)

血管老化 / 动脉硬度（SDPPG / 指数）：
- [Assessing hemodynamics from the PPG for vascular age — VascAgeNet review (AJP-Heart 2022)](https://journals.physiology.org/doi/full/10.1152/ajpheart.00392.2021)
- [Photoplethysmography for the Assessment of Arterial Stiffness (MDPI Sensors 2023)](https://www.mdpi.com/1424-8220/23/24/9882)
- [New Aging Index Using PPG and APG (PMC5334132)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5334132/)
- [Second Derivative of PPG as Indicator of Vascular Aging (MDPI)](https://www.mdpi.com/2673-4591/118/1/72)
- [SDPPG vs pulse wave velocity in hypertensives (Am J Hypertens, Takazawa-line)](https://academic.oup.com/ajh/article/13/2/165/190879)

PPG 房颤 / PRV：
- [AF detection by HRV in Poincaré plot (PMC2803479)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2803479/)

PPG 睡眠呼吸暂停：
- [Diagnosis of OSA Using Pulse-Oximeter PPG (JCSM / PMC3927434)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3927434/)
- [Evaluation of pulse-oximeter PPG for OSA (PMC5419916)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5419916/)
- [Home OSA screening from PWA + PPI + ODI (Sleep & Breathing)](https://link.springer.com/article/10.1007/s11325-026-03592-4)

PPG 糖尿病（含陷阱）：
- [Machine-Learning-Based Diabetes Detection Using PPG Features (arXiv 2308.01930)](https://arxiv.org/pdf/2308.01930)
- [Pitfall: coexisting hypertension blunts b/a difference in diabetes (medRxiv 2022)](https://www.medrxiv.org/content/10.1101/2022.12.17.22283608.full.pdf)

PPG 外周动脉疾病：
- [PPG Morphological Variability vs Ankle-Brachial Index in PAD (MDPI Sensors)](https://www.mdpi.com/1424-8220/26/6/1864)

SCG 综述与基准点 / STI：
- [Recent Advances in Seismocardiography (Taebi et al., PMC8189030)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8189030/)
- [Definition of Fiducial Points in the Normal SCG (PMC6193995)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6193995/)
- [Automatic Identification of Systolic Time Intervals in SCG (Sci Rep 2016)](https://www.nature.com/articles/srep37524)
- [Can SCG Fiducial Points Estimate Cardiac Time Intervals in Patients? (Frontiers Physiol 2022)](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2022.825918/full)

SCG 心衰 / 血流动力学（ML）：
- [Wearable SCG + ML assesses HF clinical status (Circ Heart Fail 2018, PMC5769154)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5769154/)
- [Estimating intracardiac hemodynamics (PCWP) with wearable SCG + ML (PMC9347221)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9347221/)
- [SEISMIC-HF 1 key findings (AHA24, PMC12296972)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12296972/)

SCG / GCG 房颤（手机机械心动图）：
- [Multiclass cardiovascular condition detection using smartphone mechanocardiography (Sci Rep 2018)](https://www.nature.com/articles/s41598-018-27683-9)
- [Detection of atrial fibrillation with seismocardiography (PubMed 28269246)](https://pubmed.ncbi.nlm.nih.gov/28269246/)
- [AF detection via accelerometer and gyroscope of a smartphone (PubMed 28391210)](https://pubmed.ncbi.nlm.nih.gov/28391210/)

SCG 瓣膜 / 失血 / 非接触（本轮新增、已入库）：
- [Efficient detection of aortic stenosis using cardiomechanical signals + HRV (Sci Rep 2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8664843/)
- [Severe aortic stenosis detection using seismocardiography (PMC12815048)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12815048/)
- [Enabling assessment of trauma-induced hemorrhage via smart wearables (Sci Adv 2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7375804/)
- [Non-contact heart vibration via computer-vision seismocardiography (Sci Rep 2023)](https://www.nature.com/articles/s41598-023-38607-7)
