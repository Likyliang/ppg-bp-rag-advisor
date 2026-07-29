<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { RouterLink } from "vue-router";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

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
const publishTarget = ref<any>(null);
const publishReason = ref("");
const publishConfirmation = ref("");
const rollbackTarget = ref<any>(null);
const rollbackReason = ref("");

const selected = computed(() => configs.value.find((item) => item.key === selectedKey.value));
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
    const row = await api<any>(`/api/v1/admin/configs/${selectedKey.value}/drafts`, {
      method: "POST",
      body: jsonBody({ content: JSON.parse(editor.value), reason: reason.value.trim() || null }),
    });
    message.value = `配置草稿 ${row.id} 已创建，尚未影响运行时。`;
    reason.value = "";
    await refresh(true);
  });
}

async function validateDraft(id: string) {
  await runAction(`validate:${id}`, async () => {
    const result = await api<any>(`/api/v1/admin/config-drafts/${id}/validate`, { method: "POST" });
    message.value = `隔离校验、固定病例和回归任务 ${result.job.id} 已排队。`;
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
    const result = await api<any>(`/api/v1/admin/config-revisions/${row.id}/rollback`, {
      method: "POST",
      headers: { "If-Match": current.revision },
      body: jsonBody({ reason: rollbackReason.value.trim() }),
    });
    rollbackTarget.value = null;
    message.value = `安全回滚任务 ${result.job.id} 已排队，验证通过后才会激活。`;
    await refresh(true);
  });
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 30_000 });
</script>

<template>
  <PageHeader title="配置中心" description="六份 YAML 仍是事实源；后台保存草稿、差异、验证、发布人和回滚快照。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="warning">医学规则遵循草稿 → 差异 → 隔离回归 → 管理员确认 → 原子发布；核心医疗安全边界不能在后台关闭。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }} <RouterLink v-if="message.includes('任务')" class="inline-link" to="/jobs">查看任务</RouterLink></FeedbackBanner>
  <div v-if="loading" class="card loading-panel">正在加载配置版本和发布记录…</div>

  <template v-else>
    <div class="config-layout">
      <aside class="card config-list">
        <div class="section-heading"><div><h2>已发布配置</h2><p>{{ configs.length }} 份可审计事实源</p></div></div>
        <button v-for="row in configs" :key="row.key" :class="{ active: selectedKey === row.key }" @click="select(row.key)">
          <span><strong>{{ row.key }}</strong><small>{{ row.read_by || "运行时配置" }}</small></span>
          <StatusBadge :status="row.risk_level" />
        </button>
      </aside>

      <section class="card config-editor">
        <div v-if="selected" class="editor-head">
          <div><small>当前 revision <code>{{ selected.revision }}</code></small><h2>{{ selected.key }}</h2><p>影响范围：{{ selected.read_by }}</p></div>
          <StatusBadge :status="selected.risk_level" />
        </div>
        <div class="editor-toolbar"><button class="btn" @click="formatEditor">格式化</button><button class="btn" :disabled="!editorState.changed" @click="resetEditor">恢复当前版本</button><span :class="editorState.valid ? (editorState.changed ? 'warning-text' : 'success') : 'danger'">{{ !editorState.valid ? `JSON 错误：${editorState.message}` : (editorState.changed ? "有未保存修改" : "与当前版本一致") }}</span></div>
        <textarea class="input code-editor" v-model="editor" spellcheck="false" :disabled="user.role!=='admin'"></textarea>
        <template v-if="user.role==='admin'">
          <label>草稿原因（建议说明目的与影响）
            <input class="input" v-model.trim="reason" maxlength="1000" placeholder="例如：同步新版居家测量术语，保持安全边界不变" />
          </label>
          <button class="btn primary" :disabled="!editorState.valid || !editorState.changed || !!acting" @click="makeDraft">{{ acting==='create' ? "创建中…" : "创建配置草稿" }}</button>
        </template>
      </section>
    </div>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>草稿与发布</h2><p>高风险配置必须通过固定病例、安全与严格质量门验证。</p></div><label>状态<select class="input" v-model="draftFilter"><option value="">全部</option><option value="draft">草稿</option><option value="validating">校验中</option><option value="validated">已校验</option><option value="invalid">未通过</option><option value="published">已发布</option></select></label></div>
      <div v-if="filteredDrafts.length" class="draft-grid">
        <article v-for="row in filteredDrafts" :key="row.id" class="draft-card">
          <div class="draft-head"><div><small>{{ row.id }}</small><strong>{{ row.config_key }}</strong></div><div><StatusBadge :status="row.risk_level" /><StatusBadge :status="row.status" /></div></div>
          <p>基于 <code>{{ row.base_revision }}</code></p>
          <p v-if="row.reason">{{ row.reason }}</p>
          <FeedbackBanner v-if="row.validation?.errors?.length" kind="error">{{ row.validation.errors.join("；") }}</FeedbackBanner>
          <details><summary>查看差异</summary><pre class="code diff-code">{{ row.diff || "无差异" }}</pre></details>
          <details v-if="Object.keys(row.validation || {}).length"><summary>查看验证摘要</summary><div class="validation-list"><div v-for="(value,key) in row.validation" :key="key"><span>{{ key }}</span><span v-if="typeof value==='boolean'"><StatusBadge :status="value?'current':'failed'" /></span><span v-else>{{ Array.isArray(value) ? `${value.length} 项` : value }}</span></div></div></details>
          <div v-if="user.role==='admin'" class="toolbar">
            <button class="btn" v-if="!['published','validating'].includes(row.status)" :disabled="!!acting" @click="validateDraft(row.id)">校验与回归</button>
            <button class="btn primary" v-if="row.status==='validated'" :disabled="!!acting" @click="requestPublish(row)">确认发布</button>
          </div>
        </article>
      </div>
      <EmptyState v-else title="没有匹配的配置草稿" />
    </section>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>发布历史与回滚</h2><p>回滚也必须经过当前版本校验和自动回归。</p></div></div>
      <div v-if="visibleRevisions.length" class="table-scroll"><table><thead><tr><th>配置</th><th>Revision</th><th>发布人 / 时间</th><th>原因</th><th>操作</th></tr></thead><tbody><tr v-for="row in visibleRevisions" :key="row.id"><td><strong>{{ row.config_key }}</strong></td><td><code>{{ row.revision }}</code></td><td>{{ row.published_by || "—" }}<small>{{ row.created_at }}</small></td><td>{{ row.reason || "—" }}</td><td><button v-if="user.role==='admin'" class="btn" @click="requestRollback(row)">安全回滚</button></td></tr></tbody></table></div>
      <EmptyState v-else title="尚无发布历史" />
      <div class="pagination"><span>第 {{ historyPage+1 }} / {{ historyTotalPages }} 页</span><button class="btn" :disabled="historyPage===0" @click="historyPage--">上一页</button><button class="btn" :disabled="historyPage+1>=historyTotalPages" @click="historyPage++">下一页</button></div>
    </section>
  </template>

  <div v-if="publishTarget" class="modal-back" @click.self="publishTarget=null"><div class="modal modal-small">
    <div class="modal-head"><div><small>高风险原子发布</small><h2>{{ publishTarget.config_key }}</h2></div><button class="icon-btn" @click="publishTarget=null">×</button></div>
    <FeedbackBanner kind="warning">发布将立即刷新运行时缓存。验证不能跳过，即使管理员自批也必须填写原因并确认配置名。</FeedbackBanner>
    <label>发布原因<textarea class="input prose-input" v-model.trim="publishReason"></textarea></label>
    <label>输入配置名确认：<strong>{{ publishTarget.config_key }}</strong><input class="input" v-model.trim="publishConfirmation" /></label>
    <div class="modal-actions"><button class="btn" @click="publishTarget=null">取消</button><button class="btn primary" :disabled="publishReason.length<3 || publishConfirmation!==publishTarget.config_key || !!acting" @click="publish">原子发布</button></div>
  </div></div>

  <div v-if="rollbackTarget" class="modal-back" @click.self="rollbackTarget=null"><div class="modal modal-small">
    <div class="modal-head"><div><small>回滚至 {{ rollbackTarget.revision }}</small><h2>{{ rollbackTarget.config_key }}</h2></div><button class="icon-btn" @click="rollbackTarget=null">×</button></div>
    <p>回滚不会直接覆盖当前文件，而是创建安全验证任务。</p>
    <label>回滚原因<textarea class="input prose-input" v-model.trim="rollbackReason"></textarea></label>
    <div class="modal-actions"><button class="btn" @click="rollbackTarget=null">取消</button><button class="btn danger" :disabled="rollbackReason.length<3 || !!acting" @click="rollback">创建回滚任务</button></div>
  </div></div>
</template>
