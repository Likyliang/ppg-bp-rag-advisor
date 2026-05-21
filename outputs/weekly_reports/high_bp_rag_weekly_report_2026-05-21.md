# 高血压 PPG 估算解释 RAG-Agent 本周工作汇报

日期：2026-05-21  
项目：PPG 血压估算结果解释与安全约束 RAG-Agent Demo  
定位：本系统解释上游 PPG/无袖带血压估算结果，强调健康趋势参考、规范复测和就医提醒；不验证 PPG 血压算法准确性，不做诊断、治疗、开药、停药或替代规范血压测量。

## 1. 本周总体进展

本周主要完成了从“可运行 MVP”到“可审计知识库 + 文献全文摘要化入库 + 安全评估闭环 + Obsidian 文献管理”的扩展工作。系统当前已经形成一套可重复的医学 RAG 工作流：文献候选筛选、合法下载、PDF 归档、source catalog 记录、中文摘要 notes、metadata chunk 生成、检索评估、报告评估、安全审查和 Obsidian 文献库同步。

当前质量门禁结果：

| 指标 | 当前结果 |
| --- | ---: |
| 纳入来源 | 114 |
| RAG chunks | 524 |
| 测试数 | 223 passed |
| Golden queries | 100 |
| Report fixtures | 50 |
| Calibrated query-only match rate | 1.0 |
| Precision@5 | 1.0 |
| Topic hit rate | 1.0 |
| Sensitive high-trust evidence rate | 1.0 |
| Unsafe source leakage | 0 |
| 建议级证据绑定率 | 1.0 |
| 报告评估最大并发 | 5 |
| Benchmark 最大并发 | 5 |
| 报告 P95 | 0.2413s |

这些指标可以分成四类理解：知识库规模、评估集规模、检索可信度和报告安全性。

| 指标 | 解释 | 汇报含义 |
| --- | --- | --- |
| 纳入来源 | 经过筛选后正式进入知识库的指南、官方材料、科学声明、标准、综述和研究文献数量 | 说明知识库不是临时抓取网页，而是经过 source catalog 治理后纳入 |
| RAG chunks | 将纳入来源拆分成的可检索证据片段，每个片段都带 source_id、topic、evidence_class、allowed_uses 等 metadata | 说明系统检索的是可追溯证据片段，而不是直接让模型记忆整篇文章 |
| 测试数 | 自动化测试数量，覆盖 schema、规则引擎、安全边界、检索、API 和报告生成 | `223 passed` 表示当前代码、知识库处理流程和并发限制逻辑通过了自动化回归测试 |
| Golden queries | 人工设计的标准检索问题集，覆盖 PPG 准确性、信号质量、家庭复测、急症、用药、孕妇、糖尿病、CKD、生活方式等场景 | 用来评估 RAG 面对真实问题时能否检索到正确主题和合适证据 |
| Report fixtures | 标准病例输入样例，覆盖正常值、偏高、低质量信号、180/120、胸痛、特殊人群、用药用户等 | 用来评估报告生成是否稳定、安全、证据完整 |
| Calibrated query-only match rate | 只把用户问题交给检索器，不把标准答案或 expected_uses 传进去，测试是否命中预期证据 | 这是比较诚实的主检索指标，避免“用答案提示检索器”的自证问题 |
| Precision@5 | 前 5 条检索结果中符合预期主题或用途的比例 | `1.0` 表示前 5 条检索结果全部符合评估标准 |
| Topic hit rate | 检索结果是否命中正确主题，例如信号质量、家庭血压监测、急症、用药安全等 | 用来说明检索不是只找到相似文字，而是能落到正确医学/工程主题 |
| Sensitive high-trust evidence rate | 急症、用药、孕妇、CKD、糖尿病等敏感场景中，是否使用指南、官方健康教育、科学声明、验证标准或安全规则等高可信来源 | `1.0` 表示敏感建议全部绑定高可信证据，没有依赖普通研究论文做高风险判断 |
| Unsafe source leakage | 不合适来源进入敏感建议的次数，例如用研究背景论文支持急症判断、用生活方式网页支持用药建议 | `0` 表示安全过滤没有发现越界来源泄漏 |
| 建议级证据绑定率 | 报告中的每条建议是否都能追溯到至少一个 evidence_id | `1.0` 表示报告不是模型凭空生成建议，而是每条建议都有证据来源 |
| 报告评估最大并发 | 报告评估脚本允许并行执行，但最多同时跑 5 个任务 | 避免后续 LLM/RAG 实验或本地资源被过高并发打爆 |
| Benchmark 最大并发 | 性能 benchmark 同样使用统一并发上限 | 即使传入更高参数，也会被自动限制到 5 |
| 报告 P95 | 95% 报告生成请求的耗时上限 | `0.2413s` 表示当前 template/rule-based 报告生成仍然很快，适合 Demo 展示 |

本周最重要的变化不是单纯增加文献数量，而是把知识库治理、全文材料处理和评估口径做成了可追溯流程。每一条来源都有 source_id、标题、组织/期刊、URL/DOI/PMID、年份、语言、地区、主题、证据等级、筛选分、allowed_uses、访问说明和安全边界；每条进入报告的建议也能追溯到具体 evidence。

### 系统输入边界补充

本系统的输入不是开放式问诊文本，而是小程序上游算法输出的结构化 PPG 血压估算结果。典型字段包括估算 SBP/DBP、心率、PPG 置信度、信号质量评分/标签、采集时长、PPG 来源、算法版本、计算原理、用户基础信息和症状标记。RAG-Agent 不训练或验证 PPG 估算模型本身，只负责对这些结构化估算结果进行保守解释、规范复测建议、证据检索、引用绑定和 Safety Agent 审查。

因此，当前测试和报告 fixtures 也按真实小程序链路设计，例如 `145/92 + 心率 + 信号质量 0.86 + 置信度 0.68`、`150/95 + 低信号质量`、`185/122 + 胸痛`、`孕妇/糖尿病/CKD 用户 + PPG 估算偏高` 等。系统会把这些输入字段保留到报告 `input_summary`，用于审计和解释，但不会据此给出诊断、治疗或调药结论。

## 2. 文献整理与入库工作量

本周围绕全文文献做了三批专项整理。

第一批处理了 AHA/AMA 家庭自测血压政策声明、PPG 接触压力、环境光/肤色 video PPG、接触力 PPG 等材料。对能下载的 PDF 做了归档，对无法下载或访问受阻的来源建立未下载名单。

第二批重点补强家庭血压监测、血压测量规范、设备验证标准和 PPG 信号质量综述，包括 AHA 血压测量科学声明、AAMI/ESH/ISO 设备验证统一标准、ESH 2021 家庭血压监测立场文件，以及 Fine 2021、Tamura 2014/2019、Sun 2016、Frontiers 2019、Lee 2021、Electronics 2023 等 PPG/可穿戴综述或研究。

第三批继续补强两个薄弱方向：无袖带 BP/PTT 的校准和验证边界，以及 PPG 光学信号质量、公平性和运动伪差。已归档并入库 11 篇 PDF，包括 Mukkamala 2015/2017 PTT 研究、Bradley 2022 无袖带 BP 综述、Parati 2026 ESC 无袖带 BP 科学声明、Ode 2020 PTT 数据采集、Park 2022 PPG 分析综述、Arguello-Prada 2024 运动伪差综述、Lee 2013 RGB 反射式 PPG、Sjoding 2020 脉搏氧肤色偏差、Shi 2022 和 Cabanas 2022 肤色/脉搏氧系统综述。

当前本地 Obsidian 文献库已经同步：

| 项目 | 数量 |
| --- | ---: |
| PDF symlink | 62 |
| PDF-backed summary notes | 48 |
| PDF 已归档但摘要待处理 | 14 |
| 未下载/访问受阻条目 | 6 |
| Topic hubs | 10 |

未下载/访问受阻条目包括 ESC 2024 Essential Messages、CHL-BHA 中国 2024 指南镜像、ESH 2010 validation protocol、Stergiou 2023 ESH cuffless validation recommendations、Maeda 2011 measurement site/motion artifact PPG、Sole-Morillo 2024 LED viewing angle/optical window PPG。这些都已记录官方入口和失败原因，目前不是 RAG 可用性阻塞项。

## 3. 拿到文献后的工作流

本项目已经把“下载文献后怎么处理”固化为一套流程。

1. 文献来源登记  
   将网页端返回的 item_id、title、best_pdf_url、landing_url、access_type、source_confidence、reason、save_as 整理为机器可读记录，例如 `web_batch3_results_2026-05-21.json`。如果没有合法全文，则进入 `unavailable_fulltext_list_current_2026-05-21.md`，记录官方入口、失败原因和下一步动作。

2. PDF 归档  
   可下载的 PDF 从 Downloads 复制到 `knowledge_base/sources/downloads/`。该目录被 Git 忽略，不提交全文、不保存账号密码、不保存 cookie/token。归档时记录文件大小、页数、SHA-256，确保可审计和可复核。

3. Source catalog 入库  
   每个纳入来源写入 `source_catalog_extra.yaml`，包含 source_id、组织/期刊、URL、DOI/PMID、年份、语言、地区、主题、evidence_class、allowed_uses、版权/访问说明、筛选分和中文 notes。筛选分由权威性、时效性、相关性、可访问性、安全适用性组成，低于阈值不纳入。

4. Fulltext candidate 记录  
   每个 PDF 同步写入 `fulltext_candidates.yaml`，记录 access_mode、status、summary_status、是否需要机构访问、是否可摘要入库、selection_reason 和 access_instruction。

5. 中文摘要 notes  
   使用 `scripts/create_fulltext_summaries.py` 生成 `knowledge_base/sources/fulltext_summaries/*.summary.md`。这些文件只写中文摘要、citation、访问记录和使用边界，不复制论文全文。

6. Markdown source notes 生成  
   使用 `scripts/extract_source_notes.py --clean` 把 source catalog 转成带 YAML front matter 的 Markdown 原始知识文件，按主题放在 `knowledge_base/raw/expanded/`。每个文件包含来源摘要、可用于报告的要点、实现使用说明、全文候选摘要和安全边界。

7. Ingest 与 chunk 生成  
   使用 `scripts/ingest_kb.py` 生成 `knowledge_base/processed/chunks.jsonl`。每个 chunk 都带有 source_id、topic、evidence_class、source_quality_score、allowed_uses、review_status、source_hash 等 metadata。

8. 审计与评估  
   使用 `scripts/audit_kb.py` 检查主题覆盖、来源数量、重复 hash、orphan source、unsafe-source leakage。使用 `scripts/evaluate_retrieval.py` 跑 calibrated query-only 检索评估，并保留 metadata-filter safety 作为辅助评估。使用 `scripts/evaluate_reports.py` 检查报告完整性、引用覆盖、建议级证据绑定和敏感建议高可信引用。

9. Obsidian 同步  
   使用 `scripts/sync_obsidian_literature.py` 将 PDF 以 symlink 方式同步到 Obsidian 文献库，生成 MOC、topic hubs、单篇 literature note 和 unresolved list。Obsidian 里不复制 PDF 正文，图谱结构控制为 `MOC -> Topic Hub -> Literature Note`，避免图谱混乱。

10. 质量门禁  
   重大变更后运行 `python scripts/run_quality_gate.py --strict-stop`。门禁会统一跑 source screening、candidate validation、summary generation、ingest、audit、retrieval evaluation、report evaluation、benchmark 和 pytest。

## 4. RAG 知识库组织方式

知识库不是普通“把论文丢进向量库”的做法，而是 metadata-governed RAG。

核心层次如下：

| 层级 | 文件/目录 | 作用 |
| --- | --- | --- |
| 来源治理层 | `knowledge_base/sources/source_catalog*.yaml` | 记录权威来源、筛选分、证据等级、allowed_uses 和安全边界 |
| 全文候选层 | `knowledge_base/sources/fulltext_candidates.yaml` | 跟踪 PDF 获取状态、访问方式、摘要状态和版权边界 |
| 摘要层 | `knowledge_base/sources/fulltext_summaries/` | 保存中文摘要和 citation，不保存全文 |
| 原始知识层 | `knowledge_base/raw/expanded/` | 按主题生成 Markdown source notes，带 front matter |
| 检索层 | `knowledge_base/processed/chunks.jsonl` | 生成带 metadata 的 chunks，用于检索和证据引用 |
| 审计层 | `knowledge_base/processed/*report*.json` | 保存 audit、retrieval、report、quality gate 等指标 |
| Obsidian 层 | Obsidian Literature Library | 人可读的 PDF 索引、文献笔记、主题 hub 和未下载名单 |

系统检索时不是只看关键词相似度，还会结合主题、allowed_uses、证据等级和安全场景过滤。例如急症、用药、孕妇、CKD、糖尿病等敏感场景必须优先使用 guideline、scientific_statement、official_health_education、validation_standard 或 safety_rule；research_context 和 lifestyle-only 来源不能支持急症判断、用药建议或临床结论。

报告生成遵循“规则引擎 + RAG evidence + Safety Agent”的结构。规则引擎先判断输入质量、血压估算分类、急症风险、特殊人群和用药安全边界；RAG 检索只为解释、复测建议、生活方式教育和安全提醒提供证据；Safety Agent 最后检查是否出现诊断、开药、停药、过度承诺、设备替代规范血压测量或遗漏急症提示。

## 5. 文献来源和期刊/来源等级

说明：下面的“等级”是本项目周报口径下的证据/来源等级，不等同于正式 JCR 分区或中科院分区。正式期刊分区需要后续用学校数据库、Journal Citation Reports 或中科院分区表逐条核验。

当前纳入来源按 evidence_class 统计：

| 证据等级 | 来源数 |
| --- | ---: |
| official_health_education | 51 |
| review | 18 |
| guideline | 15 |
| research_context | 10 |
| safety_rule | 9 |
| scientific_statement | 5 |
| validation_standard | 4 |
| patient_education | 2 |

按来源权威性可以分为四层。

第一层是指南、科学声明、标准和监管/官方来源，属于报告里可用于安全边界和复测/设备建议的高可信来源。代表包括 AHA/ACC 2025 高血压指南、AHA 血压测量科学声明、AHA/AMA 家庭自测血压政策声明、中国高血压防治指南 2024、ESC 2024 高血压指南、NICE NG136、ISH 2020、KDIGO 2024、WHO、FDA、USPSTF、AAMI/ESH/ISO 设备验证标准、STRIDE BP/ValidateBP 等。

第二层是心血管/高血压专业期刊或组织相关综述和声明，用于加强无袖带 BP、PTT 校准、设备验证和临床边界。代表包括 Journal of Hypertension、American Journal of Hypertension、European Journal of Preventive Cardiology、Hypertension、Circulation 相关声明或记录。这些在系统中通常作为 scientific_statement、guideline、validation_standard 或 review，不允许越界为诊断/治疗依据。

第三层是生物医学工程、传感器和生理测量方向的同行评议研究/综述，用于解释 PPG/无袖带技术局限、信号质量、运动伪差、接触压力、环境光、肤色、采集时长和传感器位置。代表包括 IEEE Transactions on Biomedical Engineering、Physiological Measurement、Frontiers in Physiology、Sensors、Biosensors、Electronics、Applied Sciences、Biomedical Engineering Letters 等。它们主要进入 signal_quality、cuffless_ppg_limitations 和 research_background。

第四层是患者教育和公共健康材料，用于把报告语言转成用户可理解的复测、记录、生活方式和就医提醒。代表包括 AHA 面向公众页面、CDC、MedlinePlus、NHLBI、NIA、NHC/国家卫健委材料等。这类来源不用于设备验证或临床诊断，但非常适合生成保守、清晰、可读的用户建议。

本周新增第三批中较关键的来源包括：

| 来源 | 期刊/组织 | 项目用途等级 |
| --- | --- | --- |
| Parati 2026 cuffless BP statement | European Journal of Preventive Cardiology / ESC | scientific_statement，高可信设备边界 |
| Bradley 2022 Cuffless BP Devices | American Journal of Hypertension | review，无袖带设备综述 |
| Mukkamala 2015/2017 PTT papers | IEEE Transactions on Biomedical Engineering | review/research_context，PTT 校准和理论限制 |
| Park 2022 PPG review | Frontiers in Physiology | review，PPG 分析和应用边界 |
| Arguello-Prada 2024 motion artifact review | Sensors | review，运动伪差和质量评估 |
| Sjoding 2020 racial bias | New England Journal of Medicine | research_context，光学传感公平性 caveat |
| Shi 2022 skin pigmentation systematic review | BMC Medicine | review，光学测量肤色影响 |
| Cabanas 2022 skin pigmentation review | Sensors | review，肤色/光学测量补充证据 |

## 6. 当前知识库主题覆盖

| 主题 | 来源数 | chunks |
| --- | ---: | ---: |
| measurement_quality | 27 | 136 |
| lifestyle | 18 | 78 |
| home_bp_monitoring | 16 | 76 |
| special_population | 16 | 69 |
| cuffless_ppg_limitations | 9 | 45 |
| bp_categories | 7 | 32 |
| validated_devices | 7 | 31 |
| emergency | 6 | 24 |
| medication_safety | 5 | 21 |
| disclaimer | 3 | 12 |

相比早期 MVP，知识库已经从“高血压健康解释 + 基础 PPG 局限”扩展为覆盖血压分类、家庭测量、急症规则、用药安全、特殊人群、生活方式、验证设备、PPG 信号质量和无袖带设备边界的完整结构。尤其是 measurement_quality 和 cuffless_ppg_limitations 本周获得了显著增强，可以更有依据地解释运动、肤色/光照、接触压力、采集时长、传感器位置、校准和设备验证问题。

## 7. 当前系统原则

1. 保守医学边界  
   系统只解释 PPG 估算结果，不做诊断、治疗、开药、停药或急症安抚。

2. 高风险场景高可信证据  
   急症、用药、孕妇、CKD、糖尿病等敏感场景必须绑定高可信来源，不能由单篇 PPG/ML 论文支持。

3. 研究论文只做技术背景  
   PPG/无袖带研究论文可用于解释信号质量和设备局限，但不能用于判断“可以不用就医”“可以替代血压计”“设备很准”等结论。

4. 建议级证据绑定  
   报告中的每条建议都需要 evidence_ids，敏感建议需要 high-trust evidence。

5. 评估不自证  
   主检索评估采用 calibrated query-only，不把 gold expected_uses 直接传给 retriever；metadata-filter safety 只作为安全过滤辅助项。

6. 全文不入库，只入摘要  
   PDF 全文只放在本地 ignored 目录；可提交知识库只保存中文摘要、citation、访问记录和安全边界。

7. 实验可并行但限制并发  
   报告评估和 benchmark 可以并行执行以提高效率，但统一通过 `evaluation.max_concurrency = 5` 限制最大并发，脚本收到更高并发参数时会自动降到 5。

## 8. 可用于周报的一句话总结

本周完成了高血压 PPG 估算解释 RAG-Agent 的知识库治理和全文文献摘要化扩展：系统明确以小程序结构化 PPG 估算输出为输入边界，累计归档维护 62 份完整 PDF 文献/资料，筛选后形成 114 个纳入来源、524 个 chunks，并建立了从文献下载、PDF 归档、source catalog、中文摘要、metadata chunk、检索评估、报告评估到 Obsidian 文献管理的闭环；在新增无袖带 BP、PTT 校准、PPG 信号质量、运动伪差和肤色公平性证据后，严格质量门禁仍全部通过，223 个测试通过，检索 precision@5 为 1.0，unsafe-source leakage 为 0，建议级证据绑定率为 1.0，实验评估支持并行但最大并发限制为 5。
