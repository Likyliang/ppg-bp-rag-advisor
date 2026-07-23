# 高血压 RAG 内部治理后台 V1

后台用于单机内部协作的知识、配置与运行治理，不是患者 CRM，不浏览个案，也不验证 PPG 血压估算准确性。报告仍坚持“不诊断、不调药停药、不错误安抚急症、不替代规范袖带测量”的代码级边界。

## 1. 组成与事实源

- FastAPI 同源提供 `/admin/` 和 `/api/v1/admin/*`。
- Vue 3 + TypeScript 源码位于 `admin_ui/`，生产产物位于 `app/static/admin_dist/`。
- SQLite 保存账号、会话、API Clients、草稿、发布快照、集成配置、任务、匿名指标和审计事件。
- `config/*.yaml` 与知识库 source catalog 仍是运行时事实源；数据库不替代这些文件。
- 原始 PDF、全文块、SQLite、锁文件和密钥均为本地状态并被 Git 忽略。

## 2. 首次部署

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
cp .env.example .env

# 生成 Fernet 主密钥，手工写入 .env；不要提交或放进命令历史。
python -m scripts.manage_admin generate-master-key

alembic upgrade head
python -m scripts.manage_admin create-user admin --role admin

npm --prefix admin_ui install
npm --prefix admin_ui run build
```

没有默认账号和默认密码。密码交互输入且至少 12 个字符。已有早期 V1 SQLite 会在应用启动时执行幂等的兼容增量迁移，不需要删除数据库。

启动两个本地进程：

```bash
APP_ENV=internal uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.admin.worker
```

建议在受控反向代理后提供 HTTPS，并配置：

```dotenv
APP_ENV=internal
ADMIN_AUTH_DISABLED=0
ADMIN_COOKIE_SECURE=1
ADMIN_SESSION_HOURS=8
REQUIRE_API_CLIENT=1
ADVISOR_SESSION_TTL_HOURS=24
```

`/api/v1/health` 保持公开。后台和文献治理接口需要登录；浏览器写操作还需要同源 CSRF token。报告、随访和 KB 搜索在 internal/production 模式使用带作用域的 `X-API-Key`。

## 3. 角色

| 角色 | 权限 |
| --- | --- |
| `admin` | 账号、API Clients、密钥、配置发布/回滚、全部文献及任务操作 |
| `curator` | 文献草稿、详情编辑、启停、软删除和授权全文上传 |
| `reviewer` | 文献校验/发布/驳回、质量查看和评测任务 |
| `viewer` | 只读查看治理、质量、任务与允许的审计信息 |

管理员可在「访问与审计」创建/停用账号。CLI 可用于恢复：

```bash
python -m scripts.manage_admin list-users
python -m scripts.manage_admin reset-password admin
```

## 4. 九个模块

1. 概览：告警优先显示 `stale/missing/building/failed`，不以数量相等代替指纹一致。
2. 文献工作台：完整字段编辑、批量识别、查重、草稿校验/发布/驳回、回收站与全文治理。
3. 知识库与索引：摘要哈希、Chroma/BGE、OpenAI 摘要和全文索引分别建任务。
4. 检索调试台：过滤条件、实际后端、融合分数、用途、元数据和引用预览。
5. 配置中心：草稿、diff、隔离回归、`revision/If-Match`、原子发布、历史和安全回滚。
6. 外部 API 集成：报告 LLM、OpenAI Embedding、离线 Judge、Crossref 四通道隔离。
7. 质量评测：`calibrated_query_only` 与 `metadata_filter_safety` 分开显示。
8. 任务中心：队列、资源锁、进度、事件、脱敏日志、失败重试和进程取消。
9. 访问与审计：RBAC、API Clients、登录/操作记录和匿名运行指标。

## 5. 密钥与外部连接

后台只有在 `ADMIN_SECRET_MASTER_KEY` 有效时才允许保存 API Key。Key 使用 Fernet 加密；读取接口只返回 `secret_configured` 和更新时间。密钥值不进入审计、指标、任务日志或异常正文。

连接测试只发送固定合成文本。评估通道 `send_fulltext=false` 是代码级 V1 不变量。环境变量只在尚未建立数据库集成配置时作为首次启动回退；已有配置遇到主密钥缺失或轮换不匹配时会拒绝解密并安全降级到模板报告、哈希检索或关键词检索，不会悄悄恢复旧环境密钥。

小程序 API Client Key 只在创建响应显示一次；数据库仅保存 SHA-256 哈希。可配置 `reports:write`、`advisor:write`、`kb:search`、到期时间与每分钟限速，并可立即吊销。

## 6. 文献、配置与任务闭环

文献采用 `draft → validated → published/rejected`。只有发布动作写入 `source_catalog_extra.yaml`。自动识别的 `allowed_uses`、评分和访问字段都必须人工可见、可改。

全文上传必须声明 `access_mode` 并勾选固定授权确认；最大 50 MB，只接受 `%PDF-` 文件。服务不保存原文件名和自由文本授权内容。认证部署中，请求只完成治理落盘，解析/索引由 Worker 异步执行。

配置发布固定为草稿、结构/语义校验、diff/影响预览、三组固定合成病例预览、自动回归、填写原因、`If-Match` 原子发布、清缓存和审计。校验与安全回滚由 Worker 执行并先返回 `202`；高风险配置不能关闭代码固化的安全边界，也不能以“跳过回归”的服务层状态发布，高风险回滚目标同样会重新执行隔离回归和严格质量门。

Worker 只执行服务端 `JOB_RESOURCES` 白名单，不接受任意命令或 argv，且同一主机只允许一个 Worker 持有进程锁。任务日志会移除项目绝对路径和常见凭证形式；进程重启会先终止仍存活的受管子进程，再把遗留的 `running/cancelling` 任务标记为 `interrupted`，可人工重试。

## 7. 隐私与验收

匿名指标仅含路由名、状态码、耗时、检索后端、生成模式和安全回退，不保存原始血压、画像或对话正文。Advisor 使用完整随机 UUID，默认 24 小时过期并支持 `DELETE /api/v1/advisor/sessions/{id}`；后台不提供会话浏览页。

发布前运行：

```bash
npm --prefix admin_ui run build
python -m pytest -q
python scripts/run_quality_gate.py --strict-stop
```

若变更影响论文表述、指标、安全边界或评测设计，还必须分别完成 Claude Code 叙事审查和 Codex 工程审查后才能视为定稿。
