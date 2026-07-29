<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

type AccessView = "metrics" | "users" | "clients" | "audit";

const user = inject<Ref<any>>("adminUser")!;
const view = ref<AccessView>("metrics");
const users = ref<any[]>([]);
const clients = ref<any[]>([]);
const events = ref<any[]>([]);
const metrics = ref<any>(null);
const hours = ref(24);
const oneTimeKey = ref("");
const oneTimePrefix = ref("");
const copied = ref(false);
const message = ref("");
const acting = ref("");
const auditAction = ref("");
const auditStatus = ref("");
const auditSearch = ref("");
const auditLimit = ref(100);
const auditPage = ref(0);
const auditPageSize = ref(25);
const newUser = ref({ username: "", password: "", role: "viewer" });
const newClient = ref({ name: "", scopes: ["reports:write", "advisor:write"], rate_limit_per_minute: 60, expires_at: "" });
const scopeChoices = [
  { value: "reports:write", label: "生成报告" },
  { value: "advisor:write", label: "随访会话" },
  { value: "kb:search", label: "知识库检索" },
  { value: "*", label: "全部作用域（谨慎）" },
];

const canAudit = computed(() => user.value.role !== "curator");
const auditActions = computed(() => [...new Set(events.value.map((row) => row.action))].sort());
const filteredEvents = computed(() => events.value.filter((row) => {
  const text = `${row.actor_name} ${row.action} ${row.resource_type} ${row.resource_id} ${row.request_id}`.toLowerCase();
  return (!auditStatus.value || row.status === auditStatus.value) && (!auditSearch.value || text.includes(auditSearch.value.toLowerCase()));
}));
const auditTotalPages = computed(() => Math.max(1, Math.ceil(filteredEvents.value.length / auditPageSize.value)));
const visibleEvents = computed(() => filteredEvents.value.slice(auditPage.value * auditPageSize.value, (auditPage.value + 1) * auditPageSize.value));

watch([auditStatus, auditSearch, auditPageSize], () => { auditPage.value = 0; });
watch(auditTotalPages, () => { if (auditPage.value >= auditTotalPages.value) auditPage.value = auditTotalPages.value - 1; });

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

async function load() {
  metrics.value = await api(`/api/v1/admin/metrics/summary?hours=${hours.value}`);
  if (canAudit.value) {
    const query = new URLSearchParams({ limit: String(auditLimit.value) });
    if (auditAction.value) query.set("action", auditAction.value);
    const audit = await api<any>(`/api/v1/admin/audit-events?${query}`);
    events.value = audit.events || [];
  }
  if (user.value.role === "admin") {
    const [userResult, clientResult] = await Promise.all([api<any>("/api/v1/admin/users"), api<any>("/api/v1/admin/api-clients")]);
    users.value = userResult.users || [];
    clients.value = clientResult.api_clients || [];
  }
}

async function runAction(key: string, action: () => Promise<void>) {
  acting.value = key;
  error.value = "";
  try { await action(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { acting.value = ""; }
}

async function createUser() {
  await runAction("user-create", async () => {
    await api("/api/v1/admin/users", { method: "POST", body: jsonBody(newUser.value) });
    newUser.value = { username: "", password: "", role: "viewer" };
    message.value = "本地账号已创建。";
    await refresh(true);
  });
}

async function toggleUser(row: any) {
  await runAction(`user:${row.id}`, async () => {
    await api(`/api/v1/admin/users/${row.id}`, { method: "PATCH", body: jsonBody({ active: !row.active }) });
    message.value = `${row.username} 已${row.active ? "停用" : "启用"}；其现有会话已撤销。`;
    await refresh(true);
  });
}

async function changeRole(row: any) {
  await runAction(`user:${row.id}`, async () => {
    await api(`/api/v1/admin/users/${row.id}`, { method: "PATCH", body: jsonBody({ role: row.role }) });
    message.value = `${row.username} 的角色已更新，现有会话已撤销。`;
    await refresh(true);
  });
}

async function createClient() {
  await runAction("client-create", async () => {
    const body = {
      name: newClient.value.name,
      scopes: newClient.value.scopes,
      rate_limit_per_minute: newClient.value.rate_limit_per_minute,
      expires_at: newClient.value.expires_at ? new Date(newClient.value.expires_at).toISOString() : null,
    };
    const result = await api<any>("/api/v1/admin/api-clients", { method: "POST", body: jsonBody(body) });
    oneTimeKey.value = result.api_key;
    oneTimePrefix.value = result.key_prefix;
    copied.value = false;
    newClient.value = { name: "", scopes: ["reports:write", "advisor:write"], rate_limit_per_minute: 60, expires_at: "" };
    await refresh(true);
  });
}

async function copyKey() {
  await navigator.clipboard.writeText(oneTimeKey.value);
  copied.value = true;
}

async function revoke(row: any) {
  if (!confirm(`吊销 ${row.name}？已部署的调用方会立即失去访问权限。`)) return;
  await runAction(`client:${row.id}`, async () => {
    await api(`/api/v1/admin/api-clients/${row.id}/revoke`, { method: "POST" });
    message.value = `${row.name} 已吊销。`;
    await refresh(true);
  });
}

function toggleScope(scope: string, checked: boolean) {
  const scopes = new Set(newClient.value.scopes);
  if (checked) scopes.add(scope); else scopes.delete(scope);
  if (scope === "*" && checked) scopes.clear(), scopes.add("*");
  if (scope !== "*" && checked) scopes.delete("*");
  newClient.value.scopes = [...scopes];
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 30_000 });
</script>

<template>
  <PageHeader title="访问与审计" description="管理本地角色、机器凭证、匿名运行指标和可追溯操作记录。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="info">指标和审计不保存原始血压、用户画像、对话正文或外部 API 密钥。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }}</FeedbackBanner>

  <nav class="workspace-tabs">
    <button :class="{active:view==='metrics'}" @click="view='metrics'">匿名指标</button>
    <button v-if="user.role==='admin'" :class="{active:view==='users'}" @click="view='users'">账号与角色 <span>{{ users.length }}</span></button>
    <button v-if="user.role==='admin'" :class="{active:view==='clients'}" @click="view='clients'">API Clients <span>{{ clients.filter(item=>item.active).length }}</span></button>
    <button v-if="canAudit" :class="{active:view==='audit'}" @click="view='audit'">操作审计 <span>{{ events.length }}</span></button>
  </nav>

  <div v-if="loading" class="card loading-panel">正在读取匿名指标与访问控制状态…</div>

  <template v-else-if="view==='metrics' && metrics">
    <section class="card filter-bar"><label>统计窗口<select class="input" v-model.number="hours" @change="refresh()"><option :value="1">最近 1 小时</option><option :value="24">最近 24 小时</option><option :value="168">最近 7 天</option><option :value="720">最近 30 天</option></select></label><span class="muted filter-summary">{{ metrics.privacy_note }}</span></section>
    <div class="grid cards stats-grid">
      <div class="card stat-card"><span class="stat">{{ metrics.request_count }}</span><span class="muted">请求数</span></div>
      <div class="card stat-card"><span class="stat" :class="metrics.error_count ? 'danger' : 'success'">{{ metrics.error_count }}</span><span class="muted">错误响应</span></div>
      <div class="card stat-card"><span class="stat">{{ metrics.p50_ms }} ms</span><span class="muted">P50 延迟</span></div>
      <div class="card stat-card"><span class="stat">{{ metrics.p95_ms }} ms</span><span class="muted">P95 延迟</span></div>
      <div class="card stat-card"><span class="stat">{{ metrics.safety_fallback_count }}</span><span class="muted">安全降级</span></div>
    </div>
    <div class="grid two section-gap">
      <section class="card"><div class="section-heading"><div><h2>路由表现</h2><p>仅记录路由名、状态和聚合延迟。</p></div></div><div v-if="metrics.routes?.length" class="table-scroll"><table><thead><tr><th>路由</th><th>请求</th><th>错误</th><th>P95</th></tr></thead><tbody><tr v-for="row in metrics.routes" :key="row.route"><td><code>{{ row.route }}</code></td><td>{{ row.count }}</td><td>{{ row.error_count }}</td><td>{{ row.p95_ms }} ms</td></tr></tbody></table></div><EmptyState v-else title="该窗口没有调用" /></section>
      <section class="card"><div class="section-heading"><div><h2>运行模式</h2><p>用于确认检索和生成是否发生安全降级。</p></div></div><h3>生成模式</h3><div class="distribution-list"><div v-for="(count,name) in metrics.generation_modes" :key="name"><span>{{ name }}</span><strong>{{ count }}</strong></div><span v-if="!Object.keys(metrics.generation_modes||{}).length" class="muted">暂无记录</span></div><h3>检索后端</h3><div class="distribution-list"><div v-for="(count,name) in metrics.retrieval_backends" :key="name"><span>{{ name }}</span><strong>{{ count }}</strong></div><span v-if="!Object.keys(metrics.retrieval_backends||{}).length" class="muted">暂无记录</span></div></section>
    </div>
  </template>

  <template v-else-if="view==='users' && user.role==='admin'">
    <div class="grid two">
      <section class="card table-card"><div class="section-heading"><div><h2>本地账号 RBAC</h2><p>角色或状态变化会撤销该账号现有会话。</p></div></div><table><thead><tr><th>账号</th><th>角色</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead><tbody><tr v-for="row in users" :key="row.id"><td><strong>{{ row.username }}</strong><small>{{ row.id===user.id ? "当前账号" : row.id }}</small></td><td><select class="input" v-model="row.role" :disabled="row.id===user.id || !!acting" @change="changeRole(row)"><option>admin</option><option>curator</option><option>reviewer</option><option>viewer</option></select></td><td><StatusBadge :status="row.active?'active':'disabled'" /></td><td>{{ formatDate(row.last_login_at) }}</td><td><button class="btn" :disabled="row.id===user.id || !!acting" @click="toggleUser(row)">{{ row.active ? "停用" : "启用" }}</button></td></tr></tbody></table></section>
      <section class="card"><div class="section-heading"><div><h2>创建账号</h2><p>不提供默认密码；请通过安全渠道交付初始密码。</p></div></div><form class="form-grid" @submit.prevent="createUser"><label>用户名<input class="input" v-model.trim="newUser.username" pattern="[A-Za-z0-9_.-]{3,80}" required /></label><label>角色<select class="input" v-model="newUser.role"><option>admin</option><option>curator</option><option>reviewer</option><option>viewer</option></select></label><label class="span-2">初始密码（至少 12 位）<input class="input" type="password" v-model="newUser.password" minlength="12" autocomplete="new-password" required /></label><button class="btn primary" :disabled="!!acting">{{ acting==='user-create' ? "创建中…" : "创建账号" }}</button></form></section>
    </div>
  </template>

  <template v-else-if="view==='clients' && user.role==='admin'">
    <FeedbackBanner v-if="oneTimeKey" kind="warning">
      <div class="one-time-key"><strong>新 Client Key 仅显示一次（{{ oneTimePrefix }}…）</strong><code>{{ oneTimeKey }}</code><div><button class="btn" @click="copyKey">{{ copied ? "已复制" : "复制密钥" }}</button><button class="btn" @click="oneTimeKey=''">我已安全保存</button></div></div>
    </FeedbackBanner>
    <div class="grid two">
      <section class="card table-card"><div class="section-heading"><div><h2>机器调用凭证</h2><p>数据库只保存哈希；吊销立即生效。</p></div></div><div v-if="clients.length" class="client-list"><article v-for="row in clients" :key="row.id"><div><strong>{{ row.name }}</strong><code>{{ row.key_prefix }}…</code></div><StatusBadge :status="row.active?'active':'disabled'" /><p>{{ row.scopes.join("、") }}</p><small>{{ row.rate_limit_per_minute }}/min · 到期 {{ formatDate(row.expires_at) }} · 最近使用 {{ formatDate(row.last_used_at) }}</small><button v-if="row.active" class="btn danger" :disabled="!!acting" @click="revoke(row)">吊销</button></article></div><EmptyState v-else title="尚无 API Client" /></section>
      <section class="card"><div class="section-heading"><div><h2>创建 API Client</h2><p>选择最小作用域和明确到期时间。</p></div></div><form @submit.prevent="createClient"><div class="form-grid"><label>名称<input class="input" v-model.trim="newClient.name" minlength="2" required /></label><label>每分钟限速<input class="input" type="number" min="1" max="10000" v-model.number="newClient.rate_limit_per_minute" required /></label><label class="span-2">到期时间<input class="input" type="datetime-local" v-model="newClient.expires_at" /></label></div><fieldset><legend>作用域</legend><div class="choice-grid"><label v-for="scope in scopeChoices" :key="scope.value" class="choice"><input type="checkbox" :checked="newClient.scopes.includes(scope.value)" @change="toggleScope(scope.value, ($event.target as HTMLInputElement).checked)" /><span>{{ scope.label }}<small>{{ scope.value }}</small></span></label></div></fieldset><button class="btn primary" :disabled="!newClient.scopes.length || !!acting">{{ acting==='client-create' ? "创建中…" : "创建并显示一次密钥" }}</button></form></section>
    </div>
  </template>

  <template v-else-if="view==='audit' && canAudit">
    <section class="card filter-bar">
      <label>精确动作<select class="input" v-model="auditAction" @change="auditPage=0;refresh()"><option value="">全部动作</option><option v-for="action in auditActions" :key="action">{{ action }}</option></select></label>
      <label>结果<select class="input" v-model="auditStatus"><option value="">全部</option><option value="success">成功</option><option value="failed">失败</option></select></label>
      <label class="filter-search">页面内搜索<input class="input" v-model.trim="auditSearch" placeholder="操作者、资源或 request ID" /></label>
      <label>读取条数<select class="input" v-model.number="auditLimit" @change="refresh()"><option :value="100">100</option><option :value="200">200</option><option :value="500">500</option></select></label>
    </section>
    <section class="card table-card"><div v-if="visibleEvents.length" class="table-scroll"><table><thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>资源</th><th>版本 / 原因</th><th>结果</th></tr></thead><tbody><tr v-for="row in visibleEvents" :key="row.id"><td>{{ formatDate(row.created_at) }}<small><code>{{ row.request_id }}</code></small></td><td>{{ row.actor_name || row.actor_type }}</td><td><code>{{ row.action }}</code></td><td>{{ row.resource_type }}<small>{{ row.resource_id || "—" }}</small></td><td><span v-if="row.before_hash || row.after_hash"><code>{{ row.before_hash?.slice(0,8) || "∅" }} → {{ row.after_hash?.slice(0,8) || "∅" }}</code></span><small>{{ row.reason || "无原因文本" }}</small></td><td><StatusBadge :status="row.status==='success'?'current':'failed'" :label="row.status" /></td></tr></tbody></table></div><EmptyState v-else title="没有匹配的审计事件" /><div class="pagination"><span>第 {{ auditPage+1 }} / {{ auditTotalPages }} 页，共 {{ filteredEvents.length }} 条</span><button class="btn" :disabled="auditPage===0" @click="auditPage--">上一页</button><button class="btn" :disabled="auditPage+1>=auditTotalPages" @click="auditPage++">下一页</button></div></section>
  </template>

  <EmptyState v-else-if="view!=='metrics'" title="当前角色不能查看该模块" detail="访问控制由后端角色权限最终判定。" />
</template>
