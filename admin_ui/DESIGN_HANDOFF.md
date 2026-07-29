# 前端交接文档 · 高血压 RAG 治理后台

更新时间：2026-07-29
状态：九个模块均已产品化并接入真实后台 API，已完成鉴权浏览器验收。

## 1. 产品定位

这是医学血压 RAG 系统的内部知识治理与运维后台，供管理员、策展人员、
审阅人员和只读人员协作使用。它不是患者管理、诊断或治疗系统，也不验证
PPG 血压估算准确性。

必须保留的界面边界：

- 不展示个案、原始血压、用户画像或对话正文。
- 不暗示诊断、处方、调药、停药、急症安抚或替代规范袖带测量。
- `calibrated_query_only` 检索质量与 `metadata_filter_safety` 安全检查分开展示。
- 外部 API 测试只使用固定合成文本；密钥创建/轮换后永不回显。

## 2. 技术与部署

源码位于 `admin_ui/`，使用 Vue 3、TypeScript、Vite 和 vue-router。构建产物
写入 `app/static/admin_dist/`，由 FastAPI 同源挂载在 `/admin/`。

```bash
npm --prefix admin_ui install
npm --prefix admin_ui run typecheck
npm --prefix admin_ui run test
npm --prefix admin_ui run build
```

开发代理默认指向 `http://127.0.0.1:8000`。生产构建必须保留：

- `vite.config.ts` 的 `base: "/admin/"`；
- `build.outDir: "../app/static/admin_dist"`；
- `src/main.ts` 的 hash 路由和九个稳定路径。

所有请求必须经过 `src/api.ts`，保留同源 Cookie 与 CSRF 头处理。不要在界面
或日志中输出请求密钥、密码、Cookie 和原始健康数据。

## 3. 九个已接入模块

1. **概览**：文献、全文、任务、质量门、集成与产物新鲜度告警。
2. **文献工作台**：分页检索、完整编辑、批量识别、草稿审核、查重、
   回收站和全文授权治理。
3. **知识库与索引**：screening、chunks、哈希、Chroma/BGE、OpenAI
   摘要和全文索引状态，以及白名单构建任务。
4. **检索调试台**：查询、元数据过滤、实际后端、评分、用途与引用预览。
5. **配置中心**：已发布配置、草稿、差异、隔离校验、发布历史和回滚。
6. **外部 API 集成**：报告 LLM、OpenAI Embedding、评估模型和 Crossref。
7. **质量评测**：严格质量门、检索评测、报告评测、匿名 API 实验和性能。
8. **任务中心**：队列、进度、脱敏日志、事件、重试和取消。
9. **访问与审计**：本地 RBAC、API Clients、匿名指标和操作审计。

这些页面不是占位页。新增交互前先核对 `app/api/admin.py`、
`app/api/library.py` 和现有响应类型，禁止用 mock 数据伪装成真实医学数据。

## 4. 当前交互基线

- 重复的状态、反馈、空状态、分页和进度展示应继续组件化。
- 列表类页面需要加载态、空态、筛选、分页以及可恢复的请求错误。
- 概览、索引、质量和任务页面需要可见的自动刷新状态；页面隐藏时暂停轮询。
- 全文构建按来源、OpenAI Embedding 按批次上报真实进度；`100%` 只在子进程
  成功退出后显示，不能用前端定时器伪造进度。
- 普通治理字段使用结构化表单。JSON/YAML 仅保留给配置原文、差异、
  脱敏调试结果等确实需要精确结构的高级区域。
- 发布、回滚、永久删除、吊销 Client 和密钥轮换必须有明确确认与结果反馈。
- 对 `401/403/409/422/429` 给出可行动的中文错误信息；`409` 要提示刷新后
  重做，不能静默覆盖 revision。
- 保持桌面高信息密度，同时允许窄屏横向滚动或折叠侧栏，不能依赖固定
  `min-width: 1080px` 才可操作。
- 存量本地 PDF 的授权状态必须与“是否已建立技术索引”分开展示。当前历史
  记录均为授权待复核，不得在界面或文档中简写为“已授权全文”。
- 摘要或全文上游一旦为 `stale/failed`，外部 Embedding 构建必须被阻断；
  失败的全文产物也不能继续进入报告或随访检索。

## 5. 主要 API 契约

- 会话：`/api/v1/admin/auth/login|logout|me`
- 概览：`/api/v1/admin/overview|freshness|manifests|metrics/summary`
- 文献：`/api/v1/library/sources|trash|fulltext|duplicates|autofill/batch`
- 文献草稿：`/api/v1/admin/library/drafts`
- 检索：`/api/v1/admin/retrieval/search`
- 配置：`/api/v1/admin/configs|config-drafts|config-revisions`
- 集成：`/api/v1/admin/integrations`
- 质量：`/api/v1/admin/quality/runs`
- 任务：`/api/v1/admin/jobs`
- 访问：`/api/v1/admin/users|api-clients|audit-events`

写操作必须使用后端要求的 CSRF 和 `If-Match`。耗时操作只创建任务并接受
`202`，由常驻 Worker 执行，前端不得伪装成同步完成。

## 6. 权限模型

- `admin`：全部操作，包括账号、Client、配置、密钥、任务和永久删除。
- `curator`：文献草稿、编辑、全文治理；不能发布配置或永久删除。
- `reviewer`：文献发布、质量查看与评测任务。
- `viewer`：只读。

界面隐藏无权限按钮用于减少误操作，但后端 `401/403` 仍是最终边界。

## 7. 验收

交付前至少完成：

```bash
npm --prefix admin_ui run typecheck
npm --prefix admin_ui run test
npm --prefix admin_ui run build
npm --prefix admin_ui audit --audit-level=high
.venv/bin/pytest -q tests/test_admin_v1.py tests/test_fulltext_admin.py tests/test_fulltext_vector_index.py
.venv/bin/python scripts/run_quality_gate.py --strict-stop
```

随后在启用鉴权的本机环境 smoke test：登录、九个路由、CSRF 写操作、任务
轮询、revision 冲突、密钥不回显、退出登录和 `/admin/` 深链刷新。

旧的 `app/static/admin.html`、`app/static/library_admin.html` 及其 vendored
资源已退役；唯一管理界面是本 Vue SPA。
