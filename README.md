# PPG 血压估算随访应用（RAG-Agent）

面向上游 PPG 小程序结构化输出的医学知识增强解释与随访系统。项目不训练或验证 PPG 血压估计算法，只对估算结果做保守、可追溯、带安全边界的健康趋势解释，并在报告之后通过对话主动了解用户现状、给出有文献依据的进一步建议。

## 功能

- 接收小程序估算 SBP/DBP、心率、PPG 信号质量、置信度、采集时长、算法版本、用户基础信息和症状。
- 字段别名归一化，支持 `SBP`、`DBP`、`HR`、`quality` 等输入。
- 规则引擎先行判断信号质量、估算血压参考范围、急症规则和特殊人群。
- 混合检索（中文 bigram 关键词 + 离线哈希向量融合，来源级去重），经过筛选治理的知识库证据，空知识库时自动回退模板报告。
- **随访对话（Advisor）**：报告生成后循序渐进地提问（每题解释为什么问、都可跳过，敏感话题靠后），把用户补充的事实转成带内联引用的个性化建议，并解答自由提问；急症会话抑制提问并置顶 120/急诊提示。详见 `docs/advisor_application.md`。
- **排查建议（可选，默认关闭）**：接入 PPG 节律/变异特征与 SCG（心振）时相特征后，可从信号给出“建议进一步排查”的提示——例如脉搏不规则提示做心电图排查心律失常。这是带不确定性、带就医指引、置信度封顶 `moderate` 的 **排查/分诊建议，不是诊断**；确诊、劝阻就医、调药、设备过度承诺等表述仍然阻断。请求侧用 `enable_screening_suggestions` 开启，规则与边界见 `docs/scg_screening_plan.md` 与 `config/screening_rules.yaml`。
- **学术化引用**：正文句级 `[n]` 标注、按首次出现顺序编号、未引用来源自动从参考文献剔除、同一来源去重、全文段落附页码定位，报告与对话均输出结构化 `references`。
- Source catalog 记录来源、证据等级、筛选分、允许用途、版权/访问说明和审计状态。
- Safety Agent 拦截确诊、调药、停药、设备过度承诺和急症漏报；并阻断排查建议越界为确定性诊断或劝阻就医（`screening_overreach_patterns`），同时对每条排查建议正向校验“对冲措辞 + 就医指引 + 置信度封顶”。随访回复共用同一套禁区模式并支持回退。
- 提供 FastAPI、Streamlit Demo（含随访对话标签页）、知识库筛选/ingest/审计、检索评估和论文评估脚本。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python scripts/screen_sources.py
python scripts/prepare_fulltext_candidates.py
python scripts/create_fulltext_summaries.py
python scripts/extract_source_notes.py --clean
python scripts/ingest_kb.py
python scripts/audit_kb.py
python scripts/evaluate_retrieval.py
python scripts/benchmark_report.py
python scripts/run_api_experiments.py --max-concurrency 5
pytest
uvicorn app.main:app --reload
streamlit run streamlit_app.py
```

小程序结构化数据到报告 demo：

```bash
python scripts/run_structured_report_demo.py --input examples/miniapp_payload.json --prefix miniapp_demo
```

可选向量索引：

```bash
python -m pip install -e ".[rag]"
python scripts/ingest_kb.py --vector
python scripts/download_fulltext_candidates.py --all-public-pdf
python scripts/ingest_fulltext_pdfs.py --query "PPG 接触压力 环境光 复测"
```

默认报告检索会读取 `knowledge_base/processed/chunks.jsonl` 并使用关键词 fallback，因此无需下载 embedding 模型也能运行。PDF 全文向量索引写入 `knowledge_base/vector_store/`，该目录被 Git 忽略，仅作本地 demo 和检索调试。

检索向量后端默认 `auto`：配置 `OPENAI_EMBEDDING_API_KEY` 并构建好索引后，报告与随访检索自动改用 OpenAI embedding（查询向量带缓存与故障退避，索引过期自动跳过）；无 Key 时退回离线哈希向量，再退回纯关键词。启用步骤：

```bash
# .env 写入 OPENAI_EMBEDDING_API_KEY 后：
python scripts/ingest_openai_embeddings.py --scope processed_chunks   # 摘要库（约 30 万 token）
python scripts/ingest_openai_embeddings.py --scope fulltext_chunks    # 可选：全文库
```

embedding 和评估模型分开配置：

```bash
# 官方 OpenAI embedding，只用于向量化已治理 chunks。
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_API_KEY=...
OPENAI_EMBEDDING_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_EMBEDDING_BATCH_SIZE=64
OPENAI_EMBEDDING_INPUT_SCOPE=processed_chunks

# 第三方 OpenAI-compatible GPT-5.5，只用于离线测评/打分。
EVAL_LLM_PROVIDER=openai_compatible
EVAL_LLM_API_KEY=...
EVAL_LLM_BASE_URL=https://your-provider.example/v1
EVAL_LLM_MODEL=gpt-5.5
EVAL_LLM_MAX_CONCURRENCY=2
EVAL_LLM_SEND_FULLTEXT=false
```

治理边界：embedding 会把 chunks 发到官方 OpenAI embedding API；评估模型默认只看测试问题、系统输出和必要元数据，不发送 PDF 全文。第三方 GPT-5.5 endpoint 不用于用户面向的报告生成，也不和 `DEEPSEEK_API_KEY`、`OPENAI_EMBEDDING_API_KEY` 混用。

## API

- `GET /api/v1/health`
- `POST /api/v1/reports/preview-rules`
- `POST /api/v1/reports/generate`
- `POST /api/v1/advisor/sessions` — 生成报告并开启随访会话（返回报告 + 开场白 + 首批问题）
- `POST /api/v1/advisor/sessions/{id}/messages` — 一轮对话（自由文本 / 结构化回答 / 跳过）
- `GET /api/v1/advisor/sessions/{id}` — 会话状态、画像与历史
- `POST /api/v1/kb/ingest`
- `GET /api/v1/kb/sources`
- `GET /api/v1/kb/audit`
- `POST /api/v1/kb/search`

## 质量门禁

长期迭代验收统一使用：

```bash
python scripts/run_quality_gate.py --strict-stop
```

该命令会重新生成知识库、运行审计、检索评估、报告评估、性能基准和测试，并写入 `knowledge_base/processed/quality_gate_report.json`。当前 release-candidate 门槛包括：60+ 纳入来源、250+ chunks、100 条 golden queries、50 个报告 fixtures、60+ 测试、敏感来源泄漏为 0、报告 P95 小于 3 秒。

轻量 API 实验可使用：

```bash
python scripts/run_api_experiments.py --max-concurrency 5
```

该脚本通过现有 FastAPI 路由批量运行报告生成和知识库检索探针，输出到 `outputs/experiments/`。它用于 Demo/周报展示，不替代 calibrated query-only 检索评估或严格质量门禁。

示例：

```json
{
  "estimated_sbp": 145,
  "estimated_dbp": 92,
  "heart_rate": 82,
  "signal_quality_score": 0.86,
  "confidence": 0.68,
  "capture_duration_sec": 30,
  "ppg_source": "camera_finger",
  "algorithm_version": "miniapp-bp-v1.0",
  "calculation_principle": "camera-based finger PPG estimation",
  "age": 45,
  "symptoms": {
    "chest_pain": false,
    "shortness_of_breath": false
  }
}
```

## 医疗安全边界

报告必须明确：PPG 估算结果仅供个人健康趋势参考，不能替代医生诊断、治疗决策或规范血压测量。系统不得提供处方、停药、调药建议，也不得宣称 PPG 估算可替代规范血压计。

## 知识来源

知识库由 `knowledge_base/sources/source_catalog.yaml` 驱动。每个来源记录 evidence class、allowed uses、筛选分、版权/访问说明和访问日期；筛选通过后由 `scripts/extract_source_notes.py` 生成结构化 Markdown，再由 `scripts/ingest_kb.py` 写入 `chunks.jsonl`。

当前纳入来源覆盖 AHA/ACC 2025 高血压指南要点、AHA 家庭血压监测和血压读数解释、AHA 无袖带血压科学声明、中国高血压防治指南 2024 修订版、NICE/ESC/ISH/ESH 国际指南、WHO 全球高血压报告、CDC/Million Hearts SMBP 行动指南、CDC/WHO/NHLBI/MedlinePlus 公众健康教育、STRIDE BP 验证设备注册表，以及项目本地安全规则。

排除规则包括设备厂商营销页、新闻软文、声称无需复测的博客，以及单篇模型性能论文作为患者建议依据。此类来源只可作为 excluded source 或研究背景，不进入用户报告核心证据。

## 全文候选

全文候选由 `knowledge_base/sources/fulltext_candidates.yaml` 单独治理。公开 PDF 可用 `scripts/download_fulltext_candidates.py` 下载到被 Git 忽略的 `knowledge_base/sources/downloads/`；机构访问候选进入 `knowledge_base/processed/fulltext_download_queue.md`，只通过用户当前浏览器会话下载，不保存账号凭证。可提交内容只包括 `knowledge_base/sources/fulltext_summaries/` 中的中文摘要和 citation。详细流程见 `docs/fulltext_workflow.md`。
