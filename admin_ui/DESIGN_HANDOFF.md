# 前端重设计交接文档 · 高血压 RAG 治理后台（admin_ui）

> 给 Claude Design 的注意事项。这是一次 **视觉 / UX / 信息架构重设计**，不是重写后端，也不是改数据契约。

---

## 0. 一句话定位

这是一个 **医学血压 RAG 系统的「内部知识治理 + 运维后台」**。
它 **不是面向患者的诊断产品**——是给管理员用的：管文献、管索引、调检索、看质量、跑任务、审计。
登录页那句免责声明要保留其精神：**「仅供内部知识治理与安全运维，不是医疗诊断系统。」**

- UI 语言：**中文（zh-CN）**，保持中文文案。
- 用户：内部管理员（单人到小团队），桌面为主（现有 `min-width: 1080px`）。

---

## 1. 在哪里改

**项目根**（路径含空格，命令行请整体加引号）：
```
"/Users/lianghao/Work/high blood pressure RAG_advisor_embedding_demo"
```

**你要动的目录 = `admin_ui/`**，一个标准 **Vite + Vue 3 + TypeScript + vue-router** 工程：
```
admin_ui/
├─ index.html            ← 挂载点，一般不用动
├─ src/
│  ├─ main.ts            ← 路由表（9 条路由）
│  ├─ App.vue            ← 外壳：侧边栏 + 顶栏 + 登录门 + <RouterView>
│  ├─ style.css          ← 全局样式（现有设计 token，重设计主战场）
│  ├─ api.ts             ← fetch 封装 + CSRF（★契约层，不要改行为）
│  └─ views/
│     ├─ DashboardView.vue      概览（已实现，46 行）
│     ├─ LibraryView.vue        文献工作台（最完整，148 行）
│     ├─ KnowledgeView.vue      知识库与索引（占位/骨架）
│     ├─ RetrievalView.vue      检索调试台（占位/骨架）
│     ├─ ConfigView.vue         配置中心（占位/骨架）
│     ├─ IntegrationsView.vue   外部 API 集成（占位/骨架）
│     ├─ QualityView.vue        质量评测（占位/骨架）
│     ├─ JobsView.vue           任务中心（占位/骨架）
│     └─ AccessAuditView.vue    访问与审计（占位/骨架）
├─ vite.config.ts        ← 构建配置（★不要改 base / outDir，见 §4）
└─ package.json          ← 依赖已装（node_modules 就在目录里）
```

> 现状：`Dashboard` 和 `Library` 有实质内容，其余 7 个视图基本是骨架/占位——**这是重设计的机会**：可以把它们设计成完整页面，但每个页面的数据来源要对齐后端已有端点（见 §3）。

---

## 2. 怎么跑起来（开发环境）

需要 **两个进程**：后端 API + 前端 dev server。

1. **后端**（在项目根，Python venv 已存在）：
   ```bash
   cd "/Users/lianghao/Work/high blood pressure RAG_advisor_embedding_demo"
   source .venv/bin/activate
   uvicorn app.main:app --port 8000
   ```
   > `vite.config.ts` 里 dev 代理写死 `/api → http://127.0.0.1:8000`，所以后端必须在 **8000** 端口（或你同步改代理）。

2. **前端**（热更新）：
   ```bash
   cd admin_ui
   npm run dev        # 依赖已装，直接起
   ```
   打开 Vite 提示的地址（默认 `http://localhost:5173`）。

3. **构建产物**（部署形态）：
   ```bash
   npm run build      # 输出到 ../app/static/admin_dist/，由后端挂在 /admin
   ```
   构建后访问 `http://127.0.0.1:8000/admin/`。

- 需要 **Node 20+**（Vite 7 要求）。
- 登录挡路时：后端 `app/admin/security.py` 有鉴权开关（`auth_disabled`），dev 下可放行以便浏览所有页面——**别把登录门从 UI 里删掉**，只是开发期绕过。

---

## 3. ★ 绝对不能破坏的契约：后端端点

重设计是**换皮 + 改交互 + 补页面**，但页面拉/写的数据端点、路径、请求体形状必须保持。下面是前端当前调用的**全部后端端点**（都在 `/api/v1/...`，同源）：

**鉴权 / 会话**
- `GET  /api/v1/admin/auth/me`      当前用户
- `POST /api/v1/admin/auth/login`   `{username, password}`
- `POST /api/v1/admin/auth/logout`

**概览 / 指标**
- `GET  /api/v1/admin/overview`
- `GET  /api/v1/admin/metrics/summary`
- `GET  /api/v1/admin/manifests`     索引 manifest 状态
- `GET  /api/v1/admin/freshness`     数据新鲜度

**文献工作台**（复用主库 API）
- `GET  /api/v1/library/sources/…`   列表/详情/增删改
- `GET  /api/v1/library/trash`、`/api/v1/library/trash/…`  废纸篓
- `GET  /api/v1/library/fulltext`    全文状态
- `POST /api/v1/library/autofill/batch`  批量识别（DOI/PDF → 草稿）
- `GET  /api/v1/library/duplicates`  查重簇
- `GET/POST /api/v1/admin/library/drafts…`  草稿工作流

**知识库 / 配置 / 集成 / 质量 / 任务 / 审计 / 用户**
- `GET/POST /api/v1/admin/configs…`、`config-drafts…`、`config-revisions…`
- `GET/POST /api/v1/admin/integrations…`、`api-clients…`
- `GET  /api/v1/admin/quality/runs`
- `POST /api/v1/admin/retrieval/search`  检索调试
- `GET/POST /api/v1/admin/jobs…`
- `GET  /api/v1/admin/audit-events`
- `GET/POST /api/v1/admin/users…`

**规则**：
- 所有网络请求都走 `src/api.ts` 的 `api()` 封装，**保留它**（它处理 JSON、错误、以及 CSRF）。
- **写操作（非 GET/HEAD/OPTIONS）自动带 CSRF**：从 cookie `ppg_admin_csrf` 读值 → 塞进 `x-csrf-token` 头，且 `credentials: "same-origin"`。**不要删这套**，否则所有写操作会被后端拒。
- 要新页面/新数据时，先看后端是否已有端点；缺的先跟维护者确认，**别在前端伪造/mock 成真数据**（这是医学库，禁止呈现假数据）。

---

## 4. ★ 构建 / 路由配置：别动这些键

`vite.config.ts`：
- `base: "/admin/"` —— 后端把 SPA 挂在 `/admin`，改了资源路径就 404。
- `build.outDir → ../app/static/admin_dist` —— 构建产物落点，后端从这里读。改了就白构建。

`src/main.ts`：
- 用 **hash 路由**（`createWebHashHistory`），9 条路由。可以调整**导航呈现/分组/图标**，但**路由 path 尽量保持**（`/library`、`/knowledge`、`/retrieval`、`/config`、`/integrations`、`/quality`、`/jobs`、`/access`）——审计和深链依赖它们；确要改就整套一致改。

---

## 5. 现有设计基线（可整套替换）

现在是很朴素的蓝灰后台（`src/style.css`，59 行）。可参考的 token：
- 主色 `#2457d6`（蓝）、侧栏深色 `#132238`、背景 `#f3f6fa`、卡片白 + `#dfe6ef` 边、圆角 8–10px。
- 语义色：warning `#fff7df/#f4d884`、error `#fff0f1/#a42534`、success `#087f5b`、danger `#b42335`。
- 结构类：`.layout`(238px 侧栏 + 主区)、`.card`、`.grid.cards`、`.stat`、`.toolbar`、`.btn/.btn.primary/.btn.danger`、`.input`、`.form-grid`、`.alert`、`.error`。

**你可以整套重做设计系统**（配色、排版、间距、组件、暗色模式、响应式）。建议：
- 组件化（把重复的 card/stat/table/toolbar 抽成 `src/components/*.vue`，现在都堆在各 view 里）。
- 保持信息密度适中——这是运维后台，表格/状态/操作是主角，别做成营销落地页。
- 医学语境要克制、专业、可信；避免夸张插画或诊断暗示。

---

## 6. 边界：可动 vs 别碰

✅ **可动**：`admin_ui/src/**`（App.vue、views、style.css、可新增 components/composables）、`index.html` 的 `<title>`/favicon。

🚫 **别碰**（后端，改了会连锁坏）：
- `app/admin/**`（Python：鉴权/审计/指标/任务/配置/集成服务）
- `app/api/**`、`app/services/**`
- `app/main.py`（挂载 + 安全中间件）

如果重设计**确实需要**后端加字段/端点，写成一份「需要后端配合的清单」交回来，由维护者实现，**不要自己去改 Python**。

---

## 7. 交接前的两个提醒（维护者已知）

1. **`admin_ui/` 目前未纳入 git**（连同 `app/admin/`、部分改动的 services 都是工作树里未提交的状态）。设计师开工前，维护者会先给它做一次快照/提交，作为可回滚基线——**在有基线前不要做大范围重构**。
2. 仓库里还有一套**更轻的旧后台** `app/static/admin.html`（挂 `/api/v1/admin`，4 模块，无构建）。它将被本工程取代/退役，**不是**重设计对象——别混淆。

---

## 8. 期望交付

- 一套统一、现代、专业的后台设计系统（浅/深色皆可用），落到 `src/style.css` + 组件。
- 9 个视图都有完整、数据对齐的设计（占位视图补成完整页面）。
- 保留登录门、CSRF、路由、构建配置与 API 契约。
- `npm run build` 能过（`vue-tsc --noEmit` 类型检查也要过），构建产物在 `/admin` 正常渲染。
- 附一份变更说明 + （如有）需要后端配合的清单。
