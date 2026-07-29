<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { RouterLink } from "vue-router";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import { configMeta, configSummary } from "../uiLabels";

const user = inject<Ref<any>>("adminUser")!;
const configs = ref<any[]>([]);
const drafts = ref<any[]>([]);
const revisions = ref<any[]>([]);
const selectedKey = ref("");
const editor = ref("");
const reason = ref("");
const draftFilter = ref("");
const historyPage = ref(0);
const historyPageSize = 20;
const message = ref("");
const acting = ref("");
const showAdvancedEditor = ref(false);
const publishTarget = ref<any>(null);
const publishReason = ref("");
const publishConfirmation = ref("");
const rollbackTarget = ref<any>(null);
const rollbackReason = ref("");

const selected = computed(() => configs.value.find((item) => item.key === selectedKey.value));
const selectedSummary = computed(() => configSummary(selected.value?.content || {}));
const filteredDrafts = computed(() => drafts.value.filter((row) => !draftFilter.value || row.status === draftFilter.value));
const historyTotalPages = computed(() => Math.max(1, Math.ceil(revisions.value.length / historyPageSize)));
const visibleRevisions = computed(() => revisions.value.slice(historyPage.value * historyPageSize, (historyPage.value + 1) * historyPageSize));
const editorState = computed(() => {
  try {
    const parsed = JSON.parse(editor.value);
    const original = selected.value ? JSON.stringify(selected.value.content) : "";
    return { valid: true, changed: JSON.stringify(parsed) !== original, message: "" };
  } catch (reason) {
    return { valid: false, changed: true, message: reason instanceof Error ? reason.message : String(reason) };
  }
});

watch(historyTotalPages, () => { if (historyPage.value >= historyTotalPages.value) historyPage.value = historyTotalPages.value - 1; });

function select(key: string) {
  selectedKey.value = key;
  const row = configs.value.find((item) => item.key === key);
  editor.value = JSON.stringify(row?.content || {}, null, 2);
  reason.value = "";
  showAdvancedEditor.value = false;
}

function resetEditor() {
  if (selected.value) editor.value = JSON.stringify(selected.value.content, null, 2);
}

function formatEditor() {
  try { editor.value = JSON.stringify(JSON.parse(editor.value), null, 2); }
  catch { /* error state already explains the parse failure */ }
}

async function load() {
  const [configResult, draftResult, revisionResult] = await Promise.all([
    api<any>("/api/v1/admin/configs"),
    api<any>("/api/v1/admin/config-drafts"),
    api<any>("/api/v1/admin/config-revisions"),
  ]);
  configs.value = configResult.configs || [];
  drafts.value = draftResult.drafts || [];
  revisions.value = revisionResult.revisions || [];
  if (!selectedKey.value && configs.value.length) select(configs.value[0].key);
}

async function runAction(key: string, action: () => Promise<void>) {
  acting.value = key;
  error.value = "";
  try { await action(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { acting.value = ""; }
}

async function makeDraft() {
  if (!selected.value || !editorState.value.valid) return;
  await runAction("create", async () => {
    await api<any>(`/api/v1/admin/configs/${selectedKey.value}/drafts`, {
      method: "POST",
      body: jsonBody({ content: JSON.parse(editor.value), reason: reason.value.trim() || null }),
    });
    message.value = `${configMeta[selectedKey.value]?.title || "规则"}草稿已保存，尚未影响当前系统。`;
    reason.value = "";
    await refresh(true);
  });
}

async function validateDraft(id: string) {
  await runAction(`validate:${id}`, async () => {
    await api<any>(`/api/v1/admin/config-drafts/${id}/validate`, { method: "POST" });
    message.value = "内容检查和安全回归已安排，完成后会自动更新状态。";
    await refresh(true);
  });
}

function requestPublish(row: any) {
  publishTarget.value = row;
  publishReason.value = row.reason || "";
  publishConfirmation.value = "";
}

async function publish() {
  const row = publishTarget.value;
  if (!row || publishConfirmation.value !== row.config_key || publishReason.value.trim().length < 3) return;
  await runAction(`publish:${row.id}`, async () => {
    await api(`/api/v1/admin/config-drafts/${row.id}/publish`, {
      method: "POST",
      headers: { "If-Match": row.base_revision },
      body: jsonBody({ reason: publishReason.value.trim(), expected_revision: row.base_revision, confirmation: publishConfirmation.value }),
    });
    publishTarget.value = null;
    message.value = "配置已原子发布并立即刷新运行时缓存。";
    await refresh(true);
    select(row.config_key);
  });
}

function requestRollback(row: any) {
  rollbackTarget.value = row;
  rollbackReason.value = "";
}

async function rollback() {
  const row = rollbackTarget.value;
  const current = configs.value.find((item) => item.key === row?.config_key);
  if (!row || !current || rollbackReason.value.trim().length < 3) return;
  await runAction(`rollback:${row.id}`, async () => {
    await api<any>(`/api/v1/admin/config-revisions/${row.id}/rollback`, {
      method: "POST",
      headers: { "If-Match": current.revision },
      body: jsonBody({ reason: rollbackReason.value.trim() }),
    });
    rollbackTarget.value = null;
    message.value = "历史版本恢复检查已安排，只有验证通过后才会生效。";
    await refresh(true);
  });
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 30_000 });
</script>

<template>
  <PageHeader title="规则设置" description="管理健康解释、资料检索和安全表达规则；修改会先保存为草稿并经过自动检查。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="warning">诊断、调药、错误安抚和替代规范袖带测量等安全边界始终开启，任何人都不能从后台关闭。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }} <RouterLink v-if="message.includes('任务')" class="inline-link" to="/jobs">查看任务</RouterLink></FeedbackBanner>
  <div v-if="loading" class="card loading-panel">正在加载配置版本和发布记录…</div>

  <template v-else>
    <div class="config-layout">
      <aside class="card config-list">
        <div class="section-heading"><div><h2>规则分类</h2><p>共 {{ configs.length }} 类设置</p></div></div>
        <button v-for="row in configs" :key="row.key" :class="{ active: selectedKey === row.key }" @click="select(row.key)">
          <span><strong>{{ configMeta[row.key]?.title || row.key }}</strong><small>{{ configMeta[row.key]?.description || row.read_by }}</small></span>
          <StatusBadge :status="row.risk_level" />
        </button>
      </aside>

      <section class="card config-editor">
        <div v-if="selected" class="editor-head">
          <div><small>当前使用中的规则</small><h2>{{ configMeta[selected.key]?.title || selected.key }}</h2><p>{{ configMeta[selected.key]?.description || selected.read_by }}</p></div>
          <StatusBadge :status="selected.risk_level" />
        </div>
        <div class="business-summary">
          <div v-for="item in selectedSummary" :key="item.key"><span>{{ item.label }}</span><strong>{{ item.summary }}</strong></div>
        </div>
        <div class="config-version-note"><span>最近发布版本已生效</span><details class="inline-details"><summary>版本信息</summary><code>{{ selected?.revision }}</code><p>{{ selected?.read_by }}</p></details></div>

        <button v-if="user.role==='admin' && !showAdvancedEditor" class="btn advanced-entry" @click="showAdvancedEditor=true">进入专业编辑</button>
        <div v-if="showAdvancedEditor" class="advanced-editor">
          <FeedbackBanner kind="info">这里展示完整规则结构，适合熟悉配置格式的管理员。日常查看无需修改。</FeedbackBanner>
          <div class="editor-toolbar"><button class="btn" @click="formatEditor">整理格式</button><button class="btn" :disabled="!editorState.changed" @click="resetEditor">恢复当前版本</button><button class="btn ghost" @click="showAdvancedEditor=false">收起</button><span :class="editorState.valid ? (editorState.changed ? 'warning-text' : 'success') : 'danger'">{{ !editorState.valid ? `格式错误：${editorState.message}` : (editorState.changed ? "有未保存修改" : "与当前版本一致") }}</span></div>
          <textarea class="input code-editor" v-model="editor" spellcheck="false"></textarea>
          <label>为什么要修改
            <input class="input" v-model.trim="reason" maxlength="1000" placeholder="例如：同步新版居家测量术语，安全边界保持不变" />
          </label>
          <button class="btn primary" :disabled="!editorState.valid || !editorState.changed || !!acting" @click="makeDraft">{{ acting==='create' ? "正在保存…" : "保存为待检查草稿" }}</button>
        </div>
      </section>
    </div>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>待检查与待发布</h2><p>重点规则必须通过固定样例、安全检查和完整质量检查。</p></div><label>状态<select class="input" v-model="draftFilter"><option value="">全部</option><option value="draft">待完善</option><option value="validating">检查中</option><option value="validated">可以发布</option><option value="invalid">需要修改</option><option value="published">已发布</option></select></label></div>
      <div v-if="filteredDrafts.length" class="draft-grid">
        <article v-for="row in filteredDrafts" :key="row.id" class="draft-card">
          <div class="draft-head"><div><small>规则草稿</small><strong>{{ configMeta[row.config_key]?.title || row.config_key }}</strong></div><div><StatusBadge :status="row.risk_level" /><StatusBadge :status="row.status" /></div></div>
          <p v-if="row.reason">{{ row.reason }}</p>
          <FeedbackBanner v-if="row.validation?.errors?.length" kind="error">{{ row.validation.errors.join("；") }}</FeedbackBanner>
          <details class="technical-details"><summary>查看修改内容</summary><pre class="code diff-code">{{ row.diff || "无差异" }}</pre><small>基于版本 {{ row.base_revision }}</small></details>
          <details v-if="Object.keys(row.validation || {}).length" class="technical-details"><summary>查看检查详情</summary><div class="validation-list"><div v-for="(value,key) in row.validation" :key="key"><span>{{ key }}</span><span v-if="typeof value==='boolean'"><StatusBadge :status="value?'current':'failed'" /></span><span v-else>{{ Array.isArray(value) ? `${value.length} 项` : value }}</span></div></div></details>
          <div v-if="user.role==='admin'" class="toolbar">
            <button class="btn" v-if="!['published','validating'].includes(row.status)" :disabled="!!acting" @click="validateDraft(row.id)">运行安全检查</button>
            <button class="btn primary" v-if="row.status==='validated'" :disabled="!!acting" @click="requestPublish(row)">发布规则</button>
          </div>
        </article>
      </div>
      <EmptyState v-else title="没有匹配的配置草稿" />
    </section>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>发布记录</h2><p>恢复历史版本也会先经过完整安全检查。</p></div></div>
      <div v-if="visibleRevisions.length" class="table-scroll"><table><thead><tr><th>规则</th><th>发布人 / 时间</th><th>修改原因</th><th>操作</th></tr></thead><tbody><tr v-for="row in visibleRevisions" :key="row.id"><td><strong>{{ configMeta[row.config_key]?.title || row.config_key }}</strong><details class="inline-details"><summary>版本号</summary><code>{{ row.revision }}</code></details></td><td>{{ row.published_by || "—" }}<small>{{ formatDate(row.created_at) }}</small></td><td>{{ row.reason || "—" }}</td><td><button v-if="user.role==='admin'" class="btn" @click="requestRollback(row)">恢复此版本</button></td></tr></tbody></table></div>
      <EmptyState v-else title="尚无发布历史" />
      <div class="pagination"><span>第 {{ historyPage+1 }} / {{ historyTotalPages }} 页</span><button class="btn" :disabled="historyPage===0" @click="historyPage--">上一页</button><button class="btn" :disabled="historyPage+1>=historyTotalPages" @click="historyPage++">下一页</button></div>
    </section>
  </template>

  <div v-if="publishTarget" class="modal-back" @click.self="publishTarget=null"><div class="modal modal-small">
    <div class="modal-head"><div><small>发布重点规则</small><h2>{{ configMeta[publishTarget.config_key]?.title || publishTarget.config_key }}</h2></div><button class="icon-btn" @click="publishTarget=null">×</button></div>
    <FeedbackBanner kind="warning">发布后会立即影响系统行为。安全检查不能跳过，并且必须填写原因。</FeedbackBanner>
    <label>发布原因<textarea class="input prose-input" v-model.trim="publishReason"></textarea></label>
    <label>输入规则编号确认：<strong>{{ publishTarget.config_key }}</strong><input class="input" v-model.trim="publishConfirmation" /></label>
    <div class="modal-actions"><button class="btn" @click="publishTarget=null">取消</button><button class="btn primary" :disabled="publishReason.length<3 || publishConfirmation!==publishTarget.config_key || !!acting" @click="publish">确认发布</button></div>
  </div></div>

  <div v-if="rollbackTarget" class="modal-back" @click.self="rollbackTarget=null"><div class="modal modal-small">
    <div class="modal-head"><div><small>恢复历史版本</small><h2>{{ configMeta[rollbackTarget.config_key]?.title || rollbackTarget.config_key }}</h2></div><button class="icon-btn" @click="rollbackTarget=null">×</button></div>
    <p>系统会先检查历史版本，确认安全后才会替换当前规则。</p>
    <label>恢复原因<textarea class="input prose-input" v-model.trim="rollbackReason"></textarea></label>
    <div class="modal-actions"><button class="btn" @click="rollbackTarget=null">取消</button><button class="btn danger" :disabled="rollbackReason.length<3 || !!acting" @click="rollback">检查并恢复</button></div>
  </div></div>
</template>
