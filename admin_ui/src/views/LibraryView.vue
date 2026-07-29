<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import SourceForm from "../components/SourceForm.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

type WorkspaceView = "sources" | "drafts" | "import" | "trash";

const user = inject<Ref<any>>("adminUser")!;
const sources = ref<any[]>([]);
const drafts = ref<any[]>([]);
const trash = ref<any[]>([]);
const duplicates = ref<any[]>([]);
const identified = ref<any[]>([]);
const taxonomy = ref<any>({ allowed_uses: [], topics: [], evidence_classes: [] });
const fulltext = ref<any>({ sources: [], access_modes: [] });
const total = ref(0);
const page = ref(0);
const pageSize = ref(25);
const query = ref("");
const tier = ref("");
const evidenceClass = ref("");
const includeFilter = ref("");
const draftStatus = ref("");
const view = ref<WorkspaceView>("sources");
const identifyInput = ref("");
const message = ref("");
const acting = ref("");
const editing = ref<any>(null);
const editingDraft = ref<any>(null);
const creatingDraft = ref<any>(null);
const uploadFor = ref<any>(null);
const uploadFile = ref<File | null>(null);
const uploadMode = ref("public_pdf");
const uploadAttested = ref(false);
const reasonAction = ref<{ kind: "trash" | "reject"; row: any; title: string } | null>(null);
const reasonText = ref("");

const canCurate = computed(() => ["admin", "curator"].includes(user.value?.role));
const canReview = computed(() => ["admin", "reviewer"].includes(user.value?.role));
const fulltextById = computed(() => Object.fromEntries((fulltext.value.sources || []).map((item: any) => [item.source_id, item])));
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const filteredDrafts = computed(() => drafts.value.filter((row) => !draftStatus.value || row.status === draftStatus.value));
const activeDrafts = computed(() => drafts.value.filter((row) => !["published", "rejected"].includes(row.status)).length);

watch([pageSize, tier, evidenceClass, includeFilter], () => { page.value = 0; void refresh(); });

function blankSource() {
  return {
    source_id: "",
    title: "",
    organization: "",
    year: new Date().getFullYear(),
    language: "en",
    region: "global",
    topic: "research_context",
    evidence_class: "research_context",
    source_type: "review",
    url: "",
    doi: null,
    pmid: null,
    journal: "",
    journal_tier: null,
    include: true,
    allowed_uses: ["research_background"],
    copyright_note: "",
    access_note: "public",
    screening: { authority: 4, recency: 4, relevance: 4, accessibility: 4, safety_applicability: 4 },
    notes: { summary: "", key_points: [], implementation_notes: [] },
  };
}

function prepareSource(source: any) {
  const prepared = JSON.parse(JSON.stringify(source || blankSource()));
  prepared.allowed_uses ||= [];
  prepared.screening = { authority: 0, recency: 0, relevance: 0, accessibility: 0, safety_applicability: 0, ...(prepared.screening || {}) };
  prepared.notes = prepared.notes && typeof prepared.notes === "object" ? prepared.notes : {};
  return prepared;
}

function cleanSource(source: any) {
  const body = JSON.parse(JSON.stringify(source));
  for (const key of Object.keys(body)) {
    if (key.startsWith("_") || ["tier", "source_quality_score"].includes(key)) delete body[key];
  }
  body.doi = body.doi || null;
  body.pmid = body.pmid || null;
  body.journal_tier = body.journal_tier || null;
  return body;
}

function showMessage(value: string) {
  message.value = value;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function load() {
  const params = new URLSearchParams({ limit: String(pageSize.value), offset: String(page.value * pageSize.value) });
  if (query.value.trim()) params.set("query", query.value.trim());
  if (tier.value) params.set("tier", tier.value);
  if (evidenceClass.value) params.set("evidence_class", evidenceClass.value);
  if (includeFilter.value) params.set("include", includeFilter.value);
  const [sourceResult, draftResult, trashResult, fulltextResult, taxonomyResult] = await Promise.all([
    api<any>(`/api/v1/library/sources?${params}`),
    api<any>("/api/v1/admin/library/drafts"),
    api<any>("/api/v1/library/trash?limit=200"),
    api<any>("/api/v1/library/fulltext"),
    api<any>("/api/v1/library/taxonomy"),
  ]);
  sources.value = sourceResult.sources || [];
  total.value = sourceResult.total || 0;
  drafts.value = draftResult.drafts || [];
  trash.value = trashResult.sources || [];
  fulltext.value = fulltextResult;
  taxonomy.value = taxonomyResult;
}

async function runAction(key: string, action: () => Promise<void>) {
  acting.value = key;
  error.value = "";
  try { await action(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { acting.value = ""; }
}

function openEdit(source: any) {
  editing.value = prepareSource(source);
}

async function saveEdit() {
  const item = editing.value;
  await runAction(`edit:${item.source_id}`, async () => {
    await api(`/api/v1/library/sources/${encodeURIComponent(item.source_id)}`, {
      method: "PATCH",
      headers: { "If-Match": item._revision },
      body: jsonBody(cleanSource(item)),
    });
    editing.value = null;
    showMessage("文献已更新；相关下游产物会按指纹标记为待重建。");
    await refresh(true);
  });
}

async function toggle(source: any) {
  await runAction(`toggle:${source.source_id}`, async () => {
    await api(`/api/v1/library/sources/${encodeURIComponent(source.source_id)}/include`, {
      method: "PUT",
      headers: { "If-Match": source._revision },
      body: jsonBody({ include: !source.include }),
    });
    await refresh(true);
  });
}

function requestReason(kind: "trash" | "reject", row: any) {
  reasonAction.value = { kind, row, title: kind === "trash" ? "移入回收站" : "驳回治理草稿" };
  reasonText.value = kind === "trash" ? "治理复核后停用" : "";
}

async function submitReason() {
  if (!reasonAction.value || reasonText.value.trim().length < 3) return;
  const { kind, row } = reasonAction.value;
  await runAction(`${kind}:${row.id || row.source_id}`, async () => {
    if (kind === "trash") {
      await api(`/api/v1/library/sources/${encodeURIComponent(row.source_id)}?reason=${encodeURIComponent(reasonText.value.trim())}`, {
        method: "DELETE", headers: { "If-Match": row._revision },
      });
      showMessage("文献已移入回收站。");
    } else {
      await api(`/api/v1/admin/library/drafts/${row.id}/reject`, { method: "POST", body: jsonBody({ reason: reasonText.value.trim() }) });
      showMessage("草稿已驳回并记录原因。");
    }
    reasonAction.value = null;
    await refresh(true);
  });
}

async function restore(row: any) {
  await runAction(`restore:${row.source_id}`, async () => {
    await api(`/api/v1/library/sources/${encodeURIComponent(row.source_id)}/restore`, { method: "POST", headers: { "If-Match": row._revision } });
    showMessage("文献已恢复。");
    await refresh(true);
  });
}

async function purge(row: any) {
  if (!confirm(`永久删除 ${row.source_id}？此操作不可恢复。`)) return;
  await runAction(`purge:${row.source_id}`, async () => {
    await api(`/api/v1/library/trash/${encodeURIComponent(row.source_id)}`, { method: "DELETE", headers: { "If-Match": row._revision } });
    showMessage("文献已永久删除。");
    await refresh(true);
  });
}

async function identifyBatch() {
  const queries = identifyInput.value.split("\n").map((item) => item.trim()).filter(Boolean);
  if (!queries.length) return;
  await runAction("identify", async () => {
    const result = await api<any>("/api/v1/library/autofill/batch", { method: "POST", body: jsonBody({ queries }) });
    identified.value = (result.drafts || []).map(prepareSource);
    showMessage(`识别出 ${result.count} 条。保存前请逐项确认允许用途、五维评分和访问说明。`);
  });
}

async function saveIdentifiedDrafts() {
  await runAction("identified-save", async () => {
    let count = 0;
    for (const source of identified.value) {
      if (!source.source_id || !source.title) continue;
      await api("/api/v1/admin/library/drafts", { method: "POST", body: jsonBody({ source: cleanSource(source) }) });
      count += 1;
    }
    identified.value = [];
    identifyInput.value = "";
    view.value = "drafts";
    showMessage(`${count} 条识别结果已保存为治理草稿，不会直接发布。`);
    await refresh(true);
  });
}

async function scanDuplicates() {
  await runAction("duplicates", async () => {
    const result = await api<any>("/api/v1/library/duplicates");
    duplicates.value = result.clusters || [];
    if (!duplicates.value.length) showMessage("未发现需要人工复核的重复簇。");
  });
}

function startDraft() {
  creatingDraft.value = prepareSource(blankSource());
}

async function createDraft() {
  await runAction("draft-create", async () => {
    const row = await api<any>("/api/v1/admin/library/drafts", { method: "POST", body: jsonBody({ source: cleanSource(creatingDraft.value) }) });
    creatingDraft.value = null;
    view.value = "drafts";
    showMessage(`治理草稿 ${row.id} 已创建。`);
    await refresh(true);
  });
}

function openDraft(row: any) {
  editingDraft.value = { id: row.id, status: row.status, source: prepareSource(row.source) };
}

async function saveDraft() {
  await runAction(`draft-edit:${editingDraft.value.id}`, async () => {
    await api(`/api/v1/admin/library/drafts/${editingDraft.value.id}`, { method: "PATCH", body: jsonBody({ source: cleanSource(editingDraft.value.source) }) });
    editingDraft.value = null;
    showMessage("治理草稿已保存，请重新校验后再发布。");
    await refresh(true);
  });
}

async function validateDraft(id: string) {
  await runAction(`validate:${id}`, async () => {
    const result = await api<any>(`/api/v1/admin/library/drafts/${id}/validate`, { method: "POST" });
    showMessage(result.validation?.passed ? "草稿校验通过，可以进入发布复核。" : "草稿未通过校验，请按错误信息修正。");
    await refresh(true);
  });
}

async function publishDraft(id: string) {
  if (!confirm("发布后将写入可审计事实目录并排队重新筛选，确定继续？")) return;
  await runAction(`publish:${id}`, async () => {
    const result = await api<any>(`/api/v1/admin/library/drafts/${id}/publish`, { method: "POST" });
    showMessage(`草稿已发布；重新筛选任务 ${result.job?.id || "已创建"}。`);
    await refresh(true);
  });
}

function chooseFile(event: Event) {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] || null;
}

async function attachFulltext() {
  if (!uploadFor.value || !uploadFile.value || !uploadAttested.value) return;
  const params = new URLSearchParams({ access_mode: uploadMode.value, attestation: "authorized_local_governance", rebuild: "true" });
  await runAction(`upload:${uploadFor.value.source_id}`, async () => {
    const result = await api<any>(`/api/v1/library/sources/${encodeURIComponent(uploadFor.value.source_id)}/fulltext?${params}`, {
      method: "POST", headers: { "content-type": "application/pdf" }, body: uploadFile.value,
    });
    showMessage(result.job ? `PDF 已治理入库；全文索引任务 ${result.job.id} 已排队。` : "PDF 已治理入库。");
    uploadFor.value = null;
    uploadFile.value = null;
    uploadAttested.value = false;
    await refresh(true);
  });
}

async function detachFulltext(source: any) {
  if (!confirm(`删除 ${source.source_id} 的本地 PDF，并重建全文索引？`)) return;
  await runAction(`detach:${source.source_id}`, async () => {
    const result = await api<any>(`/api/v1/library/sources/${encodeURIComponent(source.source_id)}/fulltext`, { method: "DELETE" });
    showMessage(result.job ? `全文已删除；重建任务 ${result.job.id} 已排队。` : "全文已删除。");
    await refresh(true);
  });
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 30_000 });
</script>

<template>
  <PageHeader title="文献工作台" description="识别结果先进入草稿，校验和审阅通过后才写入事实目录。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="warning">允许用途、授权、访问说明和五维评分必须逐项可见、可改、可审计。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }}</FeedbackBanner>

  <nav class="workspace-tabs">
    <button :class="{ active: view === 'sources' }" @click="view='sources'">在库文献 <span>{{ total }}</span></button>
    <button :class="{ active: view === 'drafts' }" @click="view='drafts'">治理草稿 <span>{{ activeDrafts }}</span></button>
    <button :class="{ active: view === 'import' }" @click="view='import'">导入与查重</button>
    <button :class="{ active: view === 'trash' }" @click="view='trash'">回收站 <span>{{ trash.length }}</span></button>
  </nav>

  <template v-if="view === 'sources'">
    <section class="card filter-bar">
      <label class="filter-search">搜索<input class="input" v-model="query" @keyup.enter="page=0;refresh()" placeholder="ID、标题、机构或期刊" /></label>
      <label>Tier<select class="input" v-model="tier"><option value="">全部</option><option>A</option><option>B</option><option>C</option></select></label>
      <label>证据类别<select class="input" v-model="evidenceClass"><option value="">全部</option><option v-for="item in taxonomy.evidence_classes" :key="item">{{ item }}</option></select></label>
      <label>启用状态<select class="input" v-model="includeFilter"><option value="">全部</option><option value="true">启用</option><option value="false">禁用</option></select></label>
      <button class="btn primary filter-submit" @click="page=0;refresh()">查询</button>
    </section>
    <section class="card table-card">
      <div v-if="loading" class="loading-panel">正在加载文献目录…</div>
      <div v-else-if="sources.length" class="table-scroll">
        <table>
          <thead><tr><th>等级</th><th>ID / 标题</th><th>机构 / 年份</th><th>主题 / 用途</th><th>全文</th><th>状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="source in sources" :key="source.source_id">
            <td><span class="tier-badge" :class="`tier-${String(source.tier).toLowerCase()}`">{{ source.tier }}</span><small>{{ source.source_quality_score }}/25</small></td>
            <td><code>{{ source.source_id }}</code><strong class="table-title">{{ source.title }}</strong></td>
            <td>{{ source.organization }}<small>{{ source.year }} · {{ source.region }}</small></td>
            <td>{{ source.topic }}<small>{{ (source.allowed_uses || []).join("、") || "未设置用途" }}</small></td>
            <td>
              <StatusBadge v-if="fulltextById[source.source_id]?.indexed" status="current" :label="`已索引 ${fulltextById[source.source_id].chunk_count}`" />
              <StatusBadge v-else-if="fulltextById[source.source_id]?.has_pdf && fulltextById[source.source_id]?.index_eligible" status="building" label="待索引" />
              <StatusBadge v-else-if="fulltextById[source.source_id]?.has_pdf" status="disabled" :label="fulltextById[source.source_id]?.ineligible_reason === 'fulltext_allowed_uses_empty' ? '用途不匹配' : '治理不完整'" />
              <StatusBadge v-else status="missing" label="无全文" />
              <small v-if="fulltextById[source.source_id]?.has_pdf && !fulltextById[source.source_id]?.license_attested" class="field-error">授权待复核</small>
            </td>
            <td><StatusBadge :status="source.include ? 'active' : 'disabled'" /></td>
            <td><div class="row-actions">
              <button class="btn" @click="openEdit(source)">{{ canCurate ? "详情 / 编辑" : "查看详情" }}</button>
              <template v-if="canCurate">
                <button class="btn" :disabled="!!acting" @click="toggle(source)">{{ source.include ? "禁用" : "启用" }}</button>
                <button class="btn" @click="uploadFor=source">上传全文</button>
                <button v-if="fulltextById[source.source_id]?.has_pdf" class="btn danger" :disabled="!!acting" @click="detachFulltext(source)">移除全文</button>
                <button class="btn danger" @click="requestReason('trash', source)">回收</button>
              </template>
            </div></td>
          </tr></tbody>
        </table>
      </div>
      <EmptyState v-else-if="!loading" title="没有匹配的文献" detail="调整搜索或筛选条件后重试。" />
      <div class="pagination">
        <label>每页<select class="input" v-model.number="pageSize"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label>
        <span>第 {{ page + 1 }} / {{ totalPages }} 页</span>
        <button class="btn" :disabled="page === 0" @click="page--;refresh()">上一页</button>
        <button class="btn" :disabled="page + 1 >= totalPages" @click="page++;refresh()">下一页</button>
      </div>
    </section>
  </template>

  <template v-else-if="view === 'drafts'">
    <section class="card filter-bar">
      <label>状态<select class="input" v-model="draftStatus"><option value="">全部状态</option><option value="draft">草稿</option><option value="validated">已校验</option><option value="invalid">未通过</option><option value="published">已发布</option><option value="rejected">已驳回</option></select></label>
      <span class="muted filter-summary">{{ filteredDrafts.length }} 条</span>
      <button v-if="canCurate" class="btn primary" @click="startDraft">新建治理草稿</button>
    </section>
    <section class="card table-card">
      <div v-if="filteredDrafts.length" class="table-scroll"><table>
        <thead><tr><th>来源</th><th>状态</th><th>校验 / 复核</th><th>更新时间</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in filteredDrafts" :key="row.id">
          <td><code>{{ row.source.source_id || "未命名" }}</code><strong class="table-title">{{ row.source.title || "无标题" }}</strong><small>{{ (row.source.allowed_uses || []).join("、") || "尚未确认用途" }}</small></td>
          <td><StatusBadge :status="row.status" /></td>
          <td><span v-if="row.validation?.errors?.length" class="field-error">{{ row.validation.errors.join("；") }}</span><span v-else>{{ row.validation?.passed ? "自动校验通过" : "尚未校验" }}</span><small>{{ row.review_note || "无复核备注" }}</small></td>
          <td>{{ row.updated_at }}<small>创建：{{ row.created_at }}</small></td>
          <td><div class="row-actions">
            <button class="btn" @click="openDraft(row)">{{ canCurate && !['published','rejected'].includes(row.status) ? "查看 / 编辑" : "查看" }}</button>
            <button class="btn" v-if="!['published','rejected'].includes(row.status) && user.role !== 'viewer'" :disabled="!!acting" @click="validateDraft(row.id)">校验</button>
            <button class="btn primary" v-if="row.status === 'validated' && canReview" :disabled="!!acting" @click="publishDraft(row.id)">发布</button>
            <button class="btn danger" v-if="!['published','rejected'].includes(row.status) && canReview" @click="requestReason('reject', row)">驳回</button>
          </div></td>
        </tr></tbody>
      </table></div>
      <EmptyState v-else title="没有匹配的治理草稿" detail="策展人员可新建或从批量识别结果保存草稿。" />
    </section>
  </template>

  <template v-else-if="view === 'import'">
    <div class="grid two">
      <section class="card">
        <div class="section-heading"><div><h2>批量识别</h2><p>每行一个 DOI、公开 URL 或标题；识别结果不会直接发布。</p></div></div>
        <textarea class="input prose-input import-input" v-model="identifyInput" placeholder="10.xxxx/xxxxx&#10;https://…&#10;论文标题"></textarea>
        <button class="btn primary" :disabled="!identifyInput.trim() || !!acting" @click="identifyBatch">{{ acting === "identify" ? "识别中…" : "开始识别" }}</button>
      </section>
      <section class="card">
        <div class="section-heading"><div><h2>在库查重</h2><p>按 DOI、PMID、URL 和规范化标题生成强/弱匹配簇，最终由人工判断。</p></div></div>
        <button class="btn" :disabled="!!acting" @click="scanDuplicates">{{ acting === "duplicates" ? "扫描中…" : "扫描重复项" }}</button>
        <div v-if="duplicates.length" class="duplicate-list">
          <article v-for="(cluster, index) in duplicates" :key="index"><StatusBadge :status="cluster.strong ? 'failed' : 'stale'" :label="cluster.strong ? '强匹配' : '弱匹配'" /><strong>{{ cluster.reasons.join("、") }}</strong><p>{{ cluster.members.map((item:any) => item.source_id).join(" / ") }}</p></article>
        </div>
      </section>
    </div>
    <section v-if="identified.length" class="card section-gap">
      <div class="section-heading"><div><h2>逐项确认识别结果</h2><p>共 {{ identified.length }} 条；每条的允许用途和评分都必须展开检查。</p></div><button class="btn primary" :disabled="!!acting" @click="saveIdentifiedDrafts">{{ acting === "identified-save" ? "保存中…" : "全部保存为草稿" }}</button></div>
      <details v-for="(source, index) in identified" :key="index" class="identified-card" :open="index === 0">
        <summary><span>结果 {{ index + 1 }}</span><strong>{{ source.title || source.source_id || "待补充标题" }}</strong><span>{{ (source.allowed_uses || []).length }} 个允许用途</span></summary>
        <SourceForm :model-value="source" :taxonomy="taxonomy" />
        <button class="btn danger" @click="identified.splice(index, 1)">移除此结果</button>
      </details>
    </section>
  </template>

  <template v-else>
    <section class="card table-card">
      <div v-if="trash.length" class="table-scroll"><table>
        <thead><tr><th>ID / 标题</th><th>删除原因</th><th>删除时间</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in trash" :key="row.source_id"><td><code>{{ row.source_id }}</code><strong class="table-title">{{ row.title }}</strong></td><td>{{ row._trash_reason || "—" }}</td><td>{{ row._trashed_at || "—" }}</td><td><div class="row-actions"><button class="btn" v-if="canCurate" :disabled="!!acting" @click="restore(row)">恢复</button><button class="btn danger" v-if="user.role === 'admin'" :disabled="!!acting" @click="purge(row)">永久删除</button></div></td></tr></tbody>
      </table></div>
      <EmptyState v-else title="回收站为空" detail="删除的目录来源会先进入这里。" />
    </section>
  </template>

  <div v-if="editing" class="modal-back" @click.self="editing=null"><div class="modal modal-wide">
    <div class="modal-head"><div><small>{{ editing.source_id }}</small><h2>文献详情与编辑</h2></div><button class="icon-btn" @click="editing=null">×</button></div>
    <SourceForm :model-value="editing" :taxonomy="taxonomy" :disabled="!canCurate" source-id-disabled />
    <div class="modal-actions"><button class="btn" @click="editing=null">关闭</button><button v-if="canCurate" class="btn primary" :disabled="!!acting" @click="saveEdit">{{ acting.startsWith("edit:") ? "保存中…" : "保存修改" }}</button></div>
  </div></div>

  <div v-if="creatingDraft" class="modal-back" @click.self="creatingDraft=null"><div class="modal modal-wide">
    <div class="modal-head"><div><h2>新建治理草稿</h2><p>保存后先校验，再由审阅角色发布。</p></div><button class="icon-btn" @click="creatingDraft=null">×</button></div>
    <SourceForm :model-value="creatingDraft" :taxonomy="taxonomy" />
    <div class="modal-actions"><button class="btn" @click="creatingDraft=null">取消</button><button class="btn primary" :disabled="!!acting" @click="createDraft">{{ acting === "draft-create" ? "保存中…" : "保存草稿" }}</button></div>
  </div></div>

  <div v-if="editingDraft" class="modal-back" @click.self="editingDraft=null"><div class="modal modal-wide">
    <div class="modal-head"><div><small>草稿 {{ editingDraft.id }}</small><h2>治理草稿详情</h2></div><button class="icon-btn" @click="editingDraft=null">×</button></div>
    <SourceForm :model-value="editingDraft.source" :taxonomy="taxonomy" :disabled="!canCurate || ['published','rejected'].includes(editingDraft.status)" />
    <div class="modal-actions"><button class="btn" @click="editingDraft=null">关闭</button><button v-if="canCurate && !['published','rejected'].includes(editingDraft.status)" class="btn primary" :disabled="!!acting" @click="saveDraft">保存草稿</button></div>
  </div></div>

  <div v-if="uploadFor" class="modal-back" @click.self="uploadFor=null"><div class="modal modal-small">
    <div class="modal-head"><div><small>{{ uploadFor.source_id }}</small><h2>治理全文</h2></div><button class="icon-btn" @click="uploadFor=null">×</button></div>
    <FeedbackBanner kind="warning">原 PDF 仅保存到 Git 忽略的本地治理目录；不保存原文件名、Cookie 或访问凭证。</FeedbackBanner>
    <label>访问模式<select class="input" v-model="uploadMode"><option v-for="mode in fulltext.access_modes" :key="mode">{{ mode }}</option></select></label>
    <label>PDF（最大 50 MB）<input class="input" type="file" accept="application/pdf,.pdf" @change="chooseFile" /></label>
    <label class="attestation"><input type="checkbox" v-model="uploadAttested" /><span>我确认该副本获准用于本地治理与检索，且不含机构会话或访问凭证。</span></label>
    <div class="modal-actions"><button class="btn" @click="uploadFor=null">取消</button><button class="btn primary" :disabled="!uploadFile || !uploadAttested || !!acting" @click="attachFulltext">上传并排队索引</button></div>
  </div></div>

  <div v-if="reasonAction" class="modal-back" @click.self="reasonAction=null"><div class="modal modal-small">
    <div class="modal-head"><h2>{{ reasonAction.title }}</h2><button class="icon-btn" @click="reasonAction=null">×</button></div>
    <p>{{ reasonAction.row.source_id || reasonAction.row.source?.source_id }} · {{ reasonAction.row.title || reasonAction.row.source?.title }}</p>
    <label>原因（至少 3 个字符）<textarea class="input prose-input" v-model.trim="reasonText" autofocus></textarea></label>
    <div class="modal-actions"><button class="btn" @click="reasonAction=null">取消</button><button class="btn danger" :disabled="reasonText.length < 3 || !!acting" @click="submitReason">确认</button></div>
  </div></div>
</template>
