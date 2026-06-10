# 测量后随访应用（Advisor）：从一次性报告到对话式服务

本次迭代把系统从「结构化输入 → 一次性报告」升级为**测量后的随访应用**：
报告生成只是第一步，之后由 Advisor 通过温和、循序渐进的提问主动了解用户现状，
对用户的自由提问给出**有文献依据、正文内联引用**的解答，并把每条新信息转成
进一步的个性化建议。

## 一、整体流程

```
小程序结构化输出
   │
   ▼
POST /api/v1/advisor/sessions
   ├── 规则引擎 + 混合检索 + 报告生成（与 /reports/generate 相同管线）
   └── 创建会话：开场白（带引用的一句话结论）+ 第一批低敏感问题
   │
   ▼
POST /api/v1/advisor/sessions/{id}/messages   ← 多轮循环
   ├── 吸收结构化回答 / 跳过 / 自由文本（保守关键词抽取）
   ├── 更新用户画像（ConversationProfile）
   ├── 按"用户问题 + 本轮新增话题"定向检索证据
   ├── 生成回复：LLM（可选）或精编模板，正文句末 [n] 引用
   ├── 安全审查（诊断/用药/设备夸大/急症安抚模式）不过 → 回退模板
   └── 选择下一批问题（同一 stage、敏感期每轮最多 1 个）
   │
   ▼
GET /api/v1/advisor/sessions/{id}   ← 会话状态、画像、问答历史
```

## 二、不冒犯的渐进式提问设计

问题库在 `config/advisor_questions.yaml`，五个 stage 由低敏感到高敏感：

| stage | 主题 | 示例 |
|------|------|------|
| 0 | 测量情境 | 测量前是否休息过、姿势是否稳定 |
| 1 | 复核条件 | 家里有没有上臂式血压计、以往测量水平 |
| 2 | 生活方式 | 口味、活动量、睡眠、烟酒（带正常化铺垫） |
| 3 | 病史用药 | 既往血压提示、是否在用降压药（只记录）、家族史 |
| 4 | 目标确认 | 最想先弄清楚什么 |

硬性设计规则（引擎强制执行）：

1. **每个问题都带 why**（为什么问），与问题一起展示；
2. **一律可跳过**，敏感问题额外提供「不方便说」选项；跳过后该话题不再出现；
3. **stage 单调不减**：先问完低敏感阶段，才进入更敏感阶段；敏感阶段每轮最多 1 题；
4. **急症会话不提问**：规则触发急症时，问题全部抑制，每条回复置顶 120/急诊提示；
5. 用户已在自由文本里说过的事实（如"我没有血压计"）不再重复提问；
6. 用药问题只做记录，回复永远是"带记录咨询医生"，不给任何用药操作建议。

## 三、画像 → 有据建议

`ConversationProfile` 累积用户主动提供的事实；每个新事实映射到一条保守、
带引用的建议（`_advice_for_update`），检索时按字段定向补充对应用途的证据
（如 `salt_preference → lifestyle`，`on_bp_medication → medication_safety`），
保证建议句末的 `[n]` 引用真正指向支持该建议的来源。

自由文本事实抽取（`extract_profile_facts`）只用高置信关键词规则，否定式
（"不抽烟""没有血压计"）优先于肯定式匹配；其余内容仅作为笔记保存。

## 四、回复生成与安全

- **模板通道（默认，无 Key 可运行）**：意图映射 + 精编中文文案 + 引用注册表；
- **LLM 通道**（`LLM_PROVIDER=deepseek|anthropic`）：紧凑系统提示 + 最近 6 轮对话 +
  画像 + 编号证据 + 治理后的建议提示词；输出经过 `sanitize_medical_copy`、
  引用越界清理、安全模式审查，任一不过即回退模板通道；
- 两个通道共享同一证据编号（来源级去重），引用后处理统一走 `CitationRegistry.finalize`。

## 五、检索与引用的底层升级（同时服务报告与随访）

1. **chunk 重构**（`app/services/chunking.py`）：
   - Markdown 结构感知 + 中英句界安全切分 + 句级 overlap；
   - 治理样板（安全边界/实现使用说明）单独成块并打 `section_role: governance`，
     **默认不进入检索**，只保留审计可见；
   - 实质内容（来源摘要/可报告要点）按来源合并成连贯块（旧版 629 块中 486 块
     短于 100 字符；新版内容块中位长度 ~500 字符，无 100 字符以下碎片）。
2. **混合检索**（`retriever.py`）：中文 bigram + 英文词的统一分词；关键词余弦
   与向量余弦加权融合（`retrieval.keyword_weight/vector_weight`）。
   向量后端 `embedding_backend: auto`——配置 `OPENAI_EMBEDDING_API_KEY` 并用
   `scripts/ingest_openai_embeddings.py` 建好索引后自动使用 OpenAI
   `text-embedding-3-small`（查询向量缓存、5 分钟故障退避、id 覆盖率 + mtime
   双重过期检测），无 Key 时退回离线哈希向量，再退回纯关键词；
   按来源去重（每来源最多 2 块）+ 用途覆盖回填；
   本地全文库段落可并入报告证据（`retrieval.include_fulltext: auto`），
   敏感请求（急症/用药/特殊人群）自动跳过全文扩展并强制高可信来源。
3. **学术化引用**（`citations.py`）：
   - 同一来源多个 chunk 共享一个引用编号，参考文献不重复；
   - `finalize`：正文 `[n]` 按**首次出现顺序重编号**，未被引用的来源从参考文献
     剔除（Vancouver 风格）；全文段落引用自动附页码定位（`DOI: …(p.7)`）；
   - 报告与对话回复都输出结构化 `references`（编号、著录、DOI/PMID/URL、页码、
     摘要片段），便于前端做悬浮卡片；
   - LLM 提示升级为**句级引用**：每个由资料支持的句子在句末标注，禁止把引用
     堆在段落末尾，每句最多 2 个编号。

## 六、运行与配置

```bash
# 离线（默认）：模板报告 + 模板随访，全部可运行
uvicorn app.main:app --reload
streamlit run streamlit_app.py     # 新增「随访对话」标签页

# 启用 LLM 报告与随访回复
export LLM_PROVIDER=deepseek       # 或 anthropic / claude
export REPORT_MODE=llm_rag
export DEEPSEEK_API_KEY=...        # 或 ANTHROPIC_API_KEY

# 启用 OpenAI embedding 检索（推荐）：.env 配置 OPENAI_EMBEDDING_API_KEY 后
python scripts/ingest_openai_embeddings.py --scope processed_chunks
python scripts/ingest_openai_embeddings.py --scope fulltext_chunks   # 可选

# chunk 或向量逻辑变更后重建索引
python scripts/ingest_kb.py        # 同时重建 processed_hashing_vectors.npz
# 注意：重建 chunks 后需要重跑上面的 OpenAI embedding ingest，否则
# 检索器会检测到索引过期并自动退回哈希向量。
python - <<'PY'
from app.services.fulltext_vector_index import rebuild_hashing_vectors_from_jsonl
print(rebuild_hashing_vectors_from_jsonl())
PY
```

会话默认持久化到 `outputs/advisor_sessions/`（Git 忽略），重启进程后可恢复。

## 七、边界与不变量

- Advisor 不诊断、不开药/停药/调药、不承诺 PPG 准确性、不替代规范测量——与
  报告层共用同一套 `config/safety_terms.yaml` 模式；
- 引用编号永不越界：检索证据数决定合法编号上限，越界标注被剥除，正文与参考
  文献由同一 `finalize` 产生，不可能不一致；
- 质量门禁继续以 `python scripts/run_quality_gate.py --strict-stop` 为准。
