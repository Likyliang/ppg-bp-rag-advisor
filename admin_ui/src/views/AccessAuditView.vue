<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import {
  auditActionLabels,
  displayLabel,
  resourceLabels,
  roleLabels,
} from "../uiLabels";

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

function scopeLabel(value: string) {
  return scopeChoices.find((item) => item.value === value)?.label || value;
}

function routeLabel(value: string) {
  if (/report|preview_rules/.test(value)) return "健康解释报告";
  if (/advisor/.test(value)) return "随访问答";
  if (/retrieval|kb_search/.test(value)) return "回答预览与资料检索";
  if (/source|taxonomy|trash|fulltext|literature|autofill|duplicate|rescreen|ingest/.test(value)) return "资料管理";
  if (/job|freshness|manifest/.test(value)) return "内容更新与处理";
  if (/quality/.test(value)) return "质量检查";
  if (/config/.test(value)) return "规则设置";
  if (/integration/.test(value)) return "服务设置";
  if (/login|logout|^me$|user|api_client|audit|metric/.test(value)) return "成员与安全";
  if (/overview|admin_page|admin_legacy/.test(value)) return "工作概览";
  return "系统其他功能";
}

const routeSummary = computed(() => {
  const groups = new Map<string, { label: string; count: number; error_count: number; p95_ms: number; routes: string[] }>();
  for (const row of metrics.value?.routes || []) {
    const label = routeLabel(row.route);
    const group = groups.get(label) || { label, count: 0, error_count: 0, p95_ms: 0, routes: [] };
    group.count += Number(row.count || 0);
    group.error_count += Number(row.error_count || 0);
    group.p95_ms = Math.max(group.p95_ms, Number(row.p95_ms || 0));
    group.routes.push(row.route);
    groups.set(label, group);
  }
  return [...groups.values()].sort((left, right) => right.count - left.count);
});

function generationModeLabel(value: string) {
  if (value === "template_only") return "安全报告模板";
  if (value === "template_advisor") return "安全随访模板";
  if (value === "llm") return "智能生成";
  return "其他生成方式";
}

function retrievalBackendLabel(value: string) {
  if (["hashing", "local_hashing"].includes(value)) return "本地基础检索";
  if (["openai", "openai_embedding"].includes(value)) return "云端语义检索";
  if (/chroma|bge/.test(value)) return "本地智能检索";
  return "其他检索方式";
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
  <PageHeader title="成员与安全" description="管理团队成员、系统接入方式和操作记录，了解服务是否稳定运行。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="info">这里只保存汇总运行数据和操作记录，不保存原始血压、用户画像、对话正文或外部服务密钥。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }}</FeedbackBanner>

  <nav class="workspace-tabs">
    <button :class="{active:view==='metrics'}" @click="view='metrics'">使用概况</button>
    <button v-if="user.role==='admin'" :class="{active:view==='users'}" @click="view='users'">成员账号 <span>{{ users.length }}</span></button>
    <button v-if="user.role==='admin'" :class="{active:view==='clients'}" @click="view='clients'">系统接入 <span>{{ clients.filter(item=>item.active).length }}</span></button>
    <button v-if="canAudit" :class="{active:view==='audit'}" @click="view='audit'">操作记录 <span>{{ events.length }}</span></button>
  </nav>

  <div v-if="loading" class="card loading-panel">正在读取使用概况和成员状态…</div>

  <template v-else-if="view==='metrics' && metrics">
    <section class="card filter-bar"><label>统计窗口<select class="input" v-model.number="hours" @change="refresh()"><option :value="1">最近 1 小时</option><option :value="24">最近 24 小时</option><option :value="168">最近 7 天</option><option :value="720">最近 30 天</option></select></label><span class="muted filter-summary">{{ metrics.privacy_note }}</span></section>
    <div class="grid cards stats-grid">
      <div class="card stat-card"><span class="stat-icon">次</span><span class="stat">{{ metrics.request_count }}</span><span class="stat-label">服务调用</span></div>
      <div class="card stat-card"><span class="stat-icon">!</span><span class="stat" :class="metrics.error_count ? 'danger' : 'success'">{{ metrics.error_count }}</span><span class="stat-label">未成功调用</span></div>
      <div class="card stat-card"><span class="stat-icon">速</span><span class="stat">{{ metrics.p50_ms }} ms</span><span class="stat-label">一般响应时间</span></div>
      <div class="card stat-card"><span class="stat-icon">慢</span><span class="stat">{{ metrics.p95_ms }} ms</span><span class="stat-label">较慢请求参考</span></div>
      <div class="card stat-card"><span class="stat-icon">安</span><span class="stat">{{ metrics.safety_fallback_count }}</span><span class="stat-label">安全备用模式</span></div>
    </div>
    <div class="grid two section-gap">
      <section class="card"><div class="section-heading"><div><h2>系统各部分使用情况</h2><p>按业务模块合并展示调用次数、是否成功和汇总响应时间。</p></div></div><div v-if="routeSummary.length" class="table-scroll"><table><thead><tr><th>模块</th><th>调用次数</th><th>未成功</th><th>较慢请求参考</th></tr></thead><tbody><tr v-for="row in routeSummary" :key="row.label"><td><strong>{{ row.label }}</strong><details class="inline-details"><summary>接口信息</summary><code>{{ row.routes.join("、") }}</code></details></td><td>{{ row.count }}</td><td>{{ row.error_count }}</td><td>{{ row.p95_ms }} ms</td></tr></tbody></table></div><EmptyState v-else title="所选时间内没有服务调用" /></section>
      <section class="card"><div class="section-heading"><div><h2>系统使用方式</h2><p>确认回答生成和资料检索是否启用了安全备用方式。</p></div></div><h3>回答生成</h3><div class="distribution-list"><div v-for="(count,name) in metrics.generation_modes" :key="name"><span>{{ generationModeLabel(String(name)) }}</span><strong>{{ count }}</strong></div><span v-if="!Object.keys(metrics.generation_modes||{}).length" class="muted">暂无记录</span></div><h3>资料检索</h3><div class="distribution-list"><div v-for="(count,name) in metrics.retrieval_backends" :key="name"><span>{{ retrievalBackendLabel(String(name)) }}</span><strong>{{ count }}</strong></div><span v-if="!Object.keys(metrics.retrieval_backends||{}).length" class="muted">暂无记录</span></div></section>
    </div>
  </template>

  <template v-else-if="view==='users' && user.role==='admin'">
    <div class="grid two">
      <section class="card table-card"><div class="section-heading"><div><h2>团队成员</h2><p>调整权限或停用账号后，该成员需要重新登录。</p></div></div><table><thead><tr><th>成员</th><th>权限</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead><tbody><tr v-for="row in users" :key="row.id"><td><strong>{{ row.username }}</strong><small>{{ row.id===user.id ? "当前账号" : "" }}</small></td><td><select class="input" v-model="row.role" :disabled="row.id===user.id || !!acting" @change="changeRole(row)"><option value="admin">{{ roleLabels.admin }}</option><option value="curator">{{ roleLabels.curator }}</option><option value="reviewer">{{ roleLabels.reviewer }}</option><option value="viewer">{{ roleLabels.viewer }}</option></select></td><td><StatusBadge :status="row.active?'active':'disabled'" /></td><td>{{ formatDate(row.last_login_at) }}</td><td><button class="btn" :disabled="row.id===user.id || !!acting" @click="toggleUser(row)">{{ row.active ? "停用" : "启用" }}</button></td></tr></tbody></table></section>
      <section class="card"><div class="section-heading"><div><h2>添加成员</h2><p>不提供默认密码，请通过安全渠道交付初始密码。</p></div></div><form class="form-grid" @submit.prevent="createUser"><label>账号<input class="input" v-model.trim="newUser.username" pattern="[A-Za-z0-9_.-]{3,80}" required /></label><label>权限<select class="input" v-model="newUser.role"><option value="admin">{{ roleLabels.admin }}</option><option value="curator">{{ roleLabels.curator }}</option><option value="reviewer">{{ roleLabels.reviewer }}</option><option value="viewer">{{ roleLabels.viewer }}</option></select></label><label class="span-2">初始密码（至少 12 位）<input class="input" type="password" v-model="newUser.password" minlength="12" autocomplete="new-password" required /></label><button class="btn primary" :disabled="!!acting">{{ acting==='user-create' ? "正在添加…" : "添加成员" }}</button></form></section>
    </div>
  </template>

  <template v-else-if="view==='clients' && user.role==='admin'">
    <FeedbackBanner v-if="oneTimeKey" kind="warning">
      <div class="one-time-key"><strong>新接入密钥仅显示一次（{{ oneTimePrefix }}…）</strong><code>{{ oneTimeKey }}</code><div><button class="btn" @click="copyKey">{{ copied ? "已复制" : "复制密钥" }}</button><button class="btn" @click="oneTimeKey=''">我已安全保存</button></div></div>
    </FeedbackBanner>
    <div class="grid two">
      <section class="card table-card"><div class="section-heading"><div><h2>已接入系统</h2><p>后台只保存不可还原的校验值；停用后立即生效。</p></div></div><div v-if="clients.length" class="client-list"><article v-for="row in clients" :key="row.id"><div><strong>{{ row.name }}</strong><small>密钥标识 {{ row.key_prefix }}…</small></div><StatusBadge :status="row.active?'active':'disabled'" /><p>{{ row.scopes.map(scopeLabel).join("、") }}</p><small>每分钟最多 {{ row.rate_limit_per_minute }} 次 · 到期 {{ formatDate(row.expires_at) }} · 最近使用 {{ formatDate(row.last_used_at) }}</small><button v-if="row.active" class="btn danger" :disabled="!!acting" @click="revoke(row)">停用接入</button></article></div><EmptyState v-else title="还没有其他系统接入" /></section>
      <section class="card"><div class="section-heading"><div><h2>添加系统接入</h2><p>只选择必需能力，并设置明确的到期时间。</p></div></div><form @submit.prevent="createClient"><div class="form-grid"><label>接入名称<input class="input" v-model.trim="newClient.name" minlength="2" required /></label><label>每分钟最多调用<input class="input" type="number" min="1" max="10000" v-model.number="newClient.rate_limit_per_minute" required /></label><label class="span-2">到期时间<input class="input" type="datetime-local" v-model="newClient.expires_at" /></label></div><fieldset><legend>允许使用的能力</legend><div class="choice-grid"><label v-for="scope in scopeChoices" :key="scope.value" class="choice"><input type="checkbox" :checked="newClient.scopes.includes(scope.value)" @change="toggleScope(scope.value, ($event.target as HTMLInputElement).checked)" /><span>{{ scope.label }}</span></label></div></fieldset><button class="btn primary" :disabled="!newClient.scopes.length || !!acting">{{ acting==='client-create' ? "正在添加…" : "添加并显示一次密钥" }}</button></form></section>
    </div>
  </template>

  <template v-else-if="view==='audit' && canAudit">
    <section class="card filter-bar">
      <label>操作类型<select class="input" v-model="auditAction" @change="auditPage=0;refresh()"><option value="">全部操作</option><option v-for="action in auditActions" :key="action" :value="action">{{ displayLabel(auditActionLabels, action) }}</option></select></label>
      <label>结果<select class="input" v-model="auditStatus"><option value="">全部</option><option value="success">成功</option><option value="failed">失败</option></select></label>
      <label class="filter-search">搜索记录<input class="input" v-model.trim="auditSearch" placeholder="成员、操作或资源" /></label>
      <label>加载数量<select class="input" v-model.number="auditLimit" @change="refresh()"><option :value="100">100</option><option :value="200">200</option><option :value="500">500</option></select></label>
    </section>
    <section class="card table-card"><div v-if="visibleEvents.length" class="table-scroll"><table><thead><tr><th>时间</th><th>成员</th><th>做了什么</th><th>对象</th><th>原因</th><th>结果</th></tr></thead><tbody><tr v-for="row in visibleEvents" :key="row.id"><td>{{ formatDate(row.created_at) }}<details class="inline-details"><summary>专业信息</summary><code>{{ row.request_id }}</code></details></td><td>{{ row.actor_name || row.actor_type }}</td><td><strong>{{ displayLabel(auditActionLabels, row.action) }}</strong></td><td>{{ displayLabel(resourceLabels, row.resource_type) }}<small>{{ row.resource_id || "—" }}</small></td><td>{{ row.reason || "未填写原因" }}<details v-if="row.before_hash || row.after_hash" class="inline-details"><summary>版本变化</summary><code>{{ row.before_hash?.slice(0,8) || "∅" }} → {{ row.after_hash?.slice(0,8) || "∅" }}</code></details></td><td><StatusBadge :status="row.status==='success'?'current':'failed'" :label="row.status==='success'?'成功':'失败'" /></td></tr></tbody></table></div><EmptyState v-else title="没有匹配的操作记录" /><div class="pagination"><span>第 {{ auditPage+1 }} / {{ auditTotalPages }} 页，共 {{ filteredEvents.length }} 条</span><button class="btn" :disabled="auditPage===0" @click="auditPage--">上一页</button><button class="btn" :disabled="auditPage+1>=auditTotalPages" @click="auditPage++">下一页</button></div></section>
  </template>

  <EmptyState v-else-if="view!=='metrics'" title="你没有查看此页面的权限" detail="如工作需要，请联系系统管理员调整权限。" />
</template>
