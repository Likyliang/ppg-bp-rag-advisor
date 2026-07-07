# 文献管理系统（Literature Management）

RAG 知识库的**统一文献管理层**：可以按分类、分级组织文献，随时**添加 / 移除 / 启停**来源，并为将来的**统一后台管理系统**预留了 REST 接口。

所有写操作都复用既有的 `source_catalog` 校验与筛选逻辑，写完自动重生成
`included_sources.json` / `excluded_sources.json` / `source_screening_report.json`，
保证下游检索与审计始终一致。

## 三个入口

| 入口 | 文件 | 用途 |
|------|------|------|
| 核心服务 | [`app/services/library_manager.py`](../app/services/library_manager.py) | `LibraryManager`，程序化增删改查 |
| 命令行 | [`scripts/manage_library.py`](../scripts/manage_library.py) | 人工日常管理 |
| REST API | [`app/api/library.py`](../app/api/library.py) | `/api/v1/library/*`，统一后台接入口 |

## 组织模型：分类（classification）+ 分级（grading）

每条文献同时被两套维度组织：

### 分类 — 主题 / 地区 / 文档类型 / 允许用途
- **`topic`**（主题分类，9 类 + `research_context`/`disclaimer`）：`bp_categories`、`home_bp_monitoring`、
  `cuffless_ppg_limitations`、`measurement_quality`、`validated_devices`、`lifestyle`、`emergency`、
  `medication_safety`、`special_population`。
- **`region`**：发布机构 / 地域（AHA、ESC、US、CN、global…）。
- **`source_type`**：文档形态（guideline_record、patient_education、review…）。
- **`allowed_uses`**：这条来源允许被引用到哪些场景（受控词表，见 `taxonomy`）。

### 分级 — 证据信任层级 + 质量分 + 期刊分级
- **`journal`**（期刊名）与 **`journal_tier`**（期刊分级 1/2/3，T1 顶刊 / T2 主流 / T3 较弱）：
  论文来源的**质量/剔除信号**。用它筛掉弱刊文献——过滤 `journal_tier=3` → 复核 → 禁用或删除。
  非论文来源（指南/患教网页）没有 journal_tier。
- **`evidence_class` → 信任层级 Tier**（`EVIDENCE_TIERS`）：

  | Tier | 含义 | evidence_class |
  |------|------|----------------|
  | **A** | 高信任（指南/标准/官方声明） | `guideline`, `validation_standard`, `scientific_statement`, `official_health_education`, `safety_rule` |
  | **B** | 中信任（综述/患教） | `review`, `patient_education` |
  | **C** | 背景（研究上下文） | `research_context` |

- **`screening`** 五维打分（`authority` / `recency` / `relevance` / `accessibility` /
  `safety_applicability`，各 0–5）求和为 `source_quality_score`；`include` 且总分 ≥ `18`
  才会进入检索库。

> 完整受控词表随时可查：`python scripts/manage_library.py taxonomy` 或 `GET /api/v1/library/taxonomy`。

## 存储与写入策略

文献存放在两个 YAML：

- `knowledge_base/sources/source_catalog.yaml` — 核心指南来源，**受保护**，工具不会主动重写。
- `knowledge_base/sources/source_catalog_extra.yaml` — **可写目录**，新增文献追加到这里。

写入策略保证 git diff 干净：
- **`add`** 采用**追加式写入**——只在文件末尾追加一个条目、更新一行 `updated:` 日期，不搅动已有条目。
- **`update` / `remove`** 会重写所在文件（规范化格式），改动谁写谁。
- 修改某条来源时，自动定位它属于哪个文件并就地更新。

## 自动识别 / 一键录入（免手填）

不想逐个字段手填时，用**自动识别**：给一个 DOI / 链接 / 标题，或上传 PDF，系统自动带出字段。

- **后台网页**（`/api/v1/library/admin` → 添加文献顶部的蓝色框）：粘贴 DOI/链接/标题点「识别」，
  或点「选择文件」上传 PDF。表单自动填好后，**黄色高亮**的是自动**建议**项——
  管理员确认/微调后点「添加到知识库」。
- **接口**：

  ```bash
  curl -X POST localhost:8000/api/v1/library/autofill \
       -H 'content-type: application/json' -d '{"query":"10.3390/s23249882"}'
  # 上传 PDF（原始请求体）
  curl -X POST localhost:8000/api/v1/library/autofill/pdf \
       -H 'content-type: application/pdf' --data-binary @paper.pdf
  ```

自动填充的边界（`app/services/literature_intake.py`）：

| 字段 | 来源 | 可信度 |
|------|------|--------|
| `title` `organization` `year` `doi` `url` `source_type` | Crossref（DOI/标题）或 PDF 内嵌 DOI | 事实，直接填 |
| `source_id` | 作者姓_年份_标题关键词 自动生成 | 事实，直接填 |
| `topic` `evidence_class` `allowed_uses` `screening` | 关键词启发式 **建议** | **需人工确认**（黄色高亮） |

> 设计原则：事实字段自动填，**策展/分级字段只给建议、由管理员拍板**——医疗证据的信任层级与
> 允许用途不能全自动判定。PDF 优先读取内嵌 DOI 再走 Crossref，取不到 DOI 时退回 PDF 元数据/首页文本。
> DOI 走 Crossref 需联网；PDF 解析需可选依赖 `pypdf`（`pip install -e ".[rag]"`，缺失时该端点返回 501）。

## 命令行用法

```bash
# 浏览（可按分类/分级过滤）
python scripts/manage_library.py list --tier A --topic lifestyle
python scripts/manage_library.py list --query dash --json
python scripts/manage_library.py show aha_sodium_salt

# 添加：命令行内联
python scripts/manage_library.py add \
    --id smith_2026_ppg_review --title "PPG BP estimation review" \
    --organization "IEEE" --url https://doi.org/10.1000/xyz --year 2026 \
    --region global --topic cuffless_ppg_limitations \
    --evidence-class review --source-type review \
    --allowed-uses cuffless_ppg_limitations,signal_quality \
    --screening 4,5,5,4,4 --summary "综述 PPG 无袖带血压估计的误差来源"

# 添加：从 JSON/YAML 文件
python scripts/manage_library.py add --file new_source.json

# 更新（合并字段）/ 全量替换
python scripts/manage_library.py update smith_2026_ppg_review --topic measurement_quality
python scripts/manage_library.py update smith_2026_ppg_review --file patch.json --replace

# 禁用/启用：仍在库里，只是不进检索（临时排除）
python scripts/manage_library.py disable smith_2026_ppg_review   # include:false
python scripts/manage_library.py enable  smith_2026_ppg_review

# 删除 = 移入废纸篓（软删除，可恢复）；其全文 PDF 一并进回收站
python scripts/manage_library.py remove  smith_2026_ppg_review
python scripts/manage_library.py trash-list                      # 查看废纸篓
python scripts/manage_library.py restore smith_2026_ppg_review   # 恢复
python scripts/manage_library.py purge   smith_2026_ppg_review   # 从废纸篓彻底删除（不可恢复）
python scripts/manage_library.py purge   --all                   # 清空废纸篓
python scripts/manage_library.py remove  smith_2026_ppg_review --hard  # 直接永久删除（跳过废纸篓）

# 概览 / 词表 / 导出 / 重新筛选
python scripts/manage_library.py stats
python scripts/manage_library.py taxonomy
python scripts/manage_library.py export --tier A --out tierA.json
python scripts/manage_library.py rescreen
```

新增来源的最小 JSON（`--file` 可用）：

```json
{
  "source_id": "smith_2026_ppg_review",
  "title": "PPG BP estimation review",
  "organization": "IEEE",
  "url": "https://doi.org/10.1000/xyz",
  "year": 2026,
  "region": "global",
  "topic": "cuffless_ppg_limitations",
  "evidence_class": "review",
  "source_type": "review",
  "allowed_uses": ["cuffless_ppg_limitations", "signal_quality"],
  "screening": {"authority": 4, "recency": 5, "relevance": 5, "accessibility": 4, "safety_applicability": 4},
  "notes": {"summary": "综述 PPG 无袖带血压估计的误差来源"}
}
```

## REST API（统一后台接入口）

挂载在 `/api/v1/library`，供统一后台管理系统调用：

| 方法 & 路径 | 作用 |
|-------------|------|
| `POST /autofill` | 由 DOI / 链接 / 标题自动识别元数据，返回待确认草稿 |
| `POST /autofill/pdf` | 上传 PDF（原始请求体）自动识别，返回待确认草稿 |
| `GET /taxonomy` | 受控词表（分类 / 分级 / 允许用途 / 阈值） |
| `GET /stats` | 按 tier / topic / evidence_class / region 计数 |
| `GET /sources` | 列表，支持 `topic` `tier` `evidence_class` `region` `include` `journal` `journal_tier` `query` 过滤 |
| `GET /sources/{id}` | 单条详情 |
| `POST /sources` | 新增（`?overwrite=true` 可覆盖同 id） |
| `PATCH /sources/{id}` | 部分更新 |
| `PUT /sources/{id}/include` | 启用 / 禁用 `{"include": bool}`（仍在库里，仅排除检索） |
| `DELETE /sources/{id}` | 删除 → **移入废纸篓**（`?hard=true` 永久删除；`?reason=` 记录原因） |
| `GET /trash` | 废纸篓内容 |
| `POST /sources/{id}/restore` | 从废纸篓恢复 |
| `DELETE /trash/{id}` | 从废纸篓彻底删除（不可恢复） |
| `POST /trash/empty` | 清空废纸篓 |
| `POST /rescreen` | 手动重生成筛选产物 |
| `POST /ingest` | 重建检索索引 `chunks.jsonl`（`?build_vector=true` 同时重建向量索引） |
| `GET /fulltext` | 全文状态总览（每来源 has_pdf / indexed / chunk_count / access_mode） |
| `GET /sources/{id}/fulltext` | 单来源全文状态 |
| `POST /sources/{id}/fulltext` | 附加全文 PDF（原始请求体）并建索引，`?access_mode=` 必填 |
| `DELETE /sources/{id}/fulltext` | 移除本地全文（删 PDF + 全文块，保留目录记录） |
| `POST /fulltext/rebuild` | 重建全文向量索引 |
| `GET /admin` | 后台管理网页（单文件 UI，同源调用上述接口） |

错误语义：校验失败 `422`、id/同一性重复 `409`、未找到 `404`。

```bash
uvicorn app.main:app --reload
curl -s localhost:8000/api/v1/library/stats | jq
curl -s -X POST localhost:8000/api/v1/library/sources \
     -H 'content-type: application/json' -d @new_source.json | jq
```

## 治理全文（Full-text governance）

除了目录级元数据，管理系统也能**治理文献全文**——让某来源的 PDF 全文进入检索，同时保住所有既有治理红线。接的是既有全文管线（`app/services/fulltext_vector_index.py`）。

**怎么用**：后台列表每行有「全文」列和「上传全文」按钮。点上传 → 声明 `access_mode`（授权/访问模式）→ 选 PDF → 系统抽取全文、切块、建**本地向量索引**，该来源即变「✓ 已索引」。检索侧 `config/settings.yaml` 的 `include_fulltext: auto` 会在本地全文库存在时**自动融合**全文（`fulltext_top_k: 2`）。

**三层数据的关系**（回答"治理的是不是全文"）：

| 层 | 谁治理 | 存哪 | 是否提交 |
|----|--------|------|----------|
| ① 目录元数据 + 分级分类 | 增删改/autofill | `source_catalog*.yaml` | ✅ 提交 |
| ② 检索笔记（人工提炼中文摘要） | ingest_kb | `raw/**/*.md` → `chunks.jsonl` | ✅ 提交 |
| ③ **文献全文** | **全文管理（本节）** | PDF→`library/<topic>/`（按主题分类）；全文块→`vector_store/` | ❌ **本地、gitignore、不提交** |

**治理红线**（全部强制执行，见 `app/services/fulltext_admin.py`）：

- **仅 included 来源**可附加全文；非收录来源直接拒绝。
- **原始 PDF 与全文文本永不提交**——PDF 只进 gitignore 的**按主题分类**的 `knowledge_base/library/<topic>/<source_id>.pdf`（回收站 `library/.trash/`），全文块只进 gitignore 的 `vector_store/`；仓库里只提交治理记录 `knowledge_base/sources/fulltext_uploads.yaml`（**元数据 + sha256 + 授权声明，无正文**）。取路径由 `governed_pdf_path()` 解析（先按 topic 精确定位，再递归兜底，最后回退旧 `downloads/`）。
- **必须声明 `access_mode`**（`public_pdf` / `public_html` / `institution_or_browser` / …），由管理员对版权合规负责；**禁止存储凭证类字段**。
- **全文块继承来源的 `allowed_uses` / `evidence_class` / `topic`** → Safety Agent 与用途门控对全文命中同样生效；全文只强化"不确定性/局限/证据"的解释，**不得扩展为诊断、治疗、调药、停药或替代经验证的血压测量**。

**命令行/接口**：

```bash
# 附加全文（原始 PDF 体）
curl -X POST "localhost:8000/api/v1/library/sources/<id>/fulltext?access_mode=public_pdf" \
     -H 'content-type: application/pdf' --data-binary @paper.pdf
# 全文状态 / 移除 / 重建
curl localhost:8000/api/v1/library/fulltext | jq '.indexed, .with_pdf'
curl -X DELETE "localhost:8000/api/v1/library/sources/<id>/fulltext"
curl -X POST   localhost:8000/api/v1/library/fulltext/rebuild
# 也可直接跑既有脚本
python scripts/ingest_fulltext_pdfs.py --query "cuffless ppg limitation"
```

> 依赖：PDF 解析需 `pypdf`（`pip install -e ".[rag]"`）。附加会重建整个本地全文索引（读取 `library/<topic>/` 下所有 PDF），约几秒。

## 按期刊分级筛选 / 剔除弱文献

论文来源登记了 `journal`（期刊）与 `journal_tier`（1=顶刊 / 2=主流 / 3=较弱）。用它做质量筛选、剔除不太行的文献：

- **后台网页**：列表工具条的「期刊级」下拉选 **T3 较弱** → 只剩弱刊文献 → 逐条「禁用」（临时排除）或「删除」（移入废纸篓）。期刊列显示 T1/T2/T3 徽章 + 期刊名。
- **命令行**：

  ```bash
  python scripts/manage_library.py list --journal-tier 3      # 列出弱刊文献（剔除候选）
  python scripts/manage_library.py list --journal "BMJ open"  # 按期刊名筛
  python scripts/manage_library.py stats                       # 看 by_journal_tier 分布
  python scripts/manage_library.py disable <source_id>         # 剔除：临时排除
  python scripts/manage_library.py remove  <source_id>         # 剔除：移入废纸篓
  ```
- **接口**：`GET /api/v1/library/sources?journal_tier=3`、`?journal=<名>`；`GET /stats` 返回 `by_journal_tier`。

> journal_tier 来自导入时的期刊质量分级（`literature_expansion` 元数据）。可在后台/接口手动调整某来源的 journal_tier。

## 废纸篓（回收站 / soft delete）

「删除」文献是**假删除**：条目移入废纸篓 `knowledge_base/sources/source_catalog_trash.yaml`（含删除时间/来源文件/原因），**从检索与筛选中消失但可恢复**；其全文 PDF 同时移入 `library/.trash/`。

- 与「禁用」的区别：**禁用**(include:false) 仍在库列表里、只是不进检索；**删除→废纸篓** 则移出库、进回收站。
- 后台网页：列表工具条「🗑 废纸篓」切换到废纸篓视图，每条可「恢复 / 彻底删除」，或「清空废纸篓」。
- 恢复会把条目放回它原来的 catalog 文件；彻底删除 / 清空不可恢复。
- 命令行见上文 `remove` / `restore` / `trash-list` / `purge`。

## 与检索管线的关系

```
manage_library.py / API  →  source_catalog_extra.yaml
        │  add/remove/update（含校验）
        ▼
   自动 rescreen  →  included_sources.json / excluded_sources.json / source_screening_report.json
        │
        ▼
   scripts/ingest_kb.py  →  chunks.jsonl  →  检索 / 报告
```

添加或调整文献后，需要**重建检索索引**才能让新内容进入检索。两种触发方式：

- **后台网页**：打开 `/api/v1/library/admin`，点右上角「重建检索索引」按钮（勾选「含向量索引」可一并重建 Chroma 向量库）。由管理员手动触发。
- **命令行 / 接口**：

  ```bash
  curl -X POST localhost:8000/api/v1/library/ingest          # 仅 chunks + 哈希向量
  curl -X POST "localhost:8000/api/v1/library/ingest?build_vector=true"  # 含向量索引
  # 或直接：
  python scripts/ingest_kb.py
  python scripts/audit_kb.py
  ```

> 说明：`ingest` 从 `knowledge_base/raw/` 的 Markdown 笔记重建 `chunks.jsonl`。目录里的
> `screening` 校验（included/excluded）在每次增删改时已自动完成；`ingest` 负责把内容重新切块入检索。
