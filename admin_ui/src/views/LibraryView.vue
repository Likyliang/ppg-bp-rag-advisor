<script setup lang="ts">
import { computed, inject, onMounted, ref, type Ref } from "vue";
import { api, jsonBody } from "../api";

const user = inject<Ref<any>>("adminUser")!;
const sources = ref<any[]>([]), drafts = ref<any[]>([]), trash = ref<any[]>([]);
const duplicates = ref<any[]>([]), identifiedTexts = ref<string[]>([]);
const fulltext = ref<any>({ sources: [], access_modes: [] });
const total = ref(0), page = ref(0), query = ref(""), view = ref<"sources" | "trash">("sources");
const identifyInput = ref(""), error = ref(""), message = ref("");
const editing = ref<any>(null), editAllowed = ref(""), editScreening = ref(""), editNotes = ref("");
const uploadFor = ref<any>(null), uploadFile = ref<File | null>(null), uploadMode = ref("public_pdf"), uploadAttested = ref(false);
const draftText = ref(JSON.stringify({
  source_id: "", title: "", organization: "", year: new Date().getFullYear(), language: "en",
  region: "global", topic: "research_context", evidence_class: "research_context", source_type: "review",
  url: "", doi: null, pmid: null, journal: "", journal_tier: null, include: true,
  allowed_uses: ["research_background"], copyright_note: "", access_note: "public",
  screening: { authority: 4, recency: 4, relevance: 4, accessibility: 4, safety_applicability: 4 }, notes: {}
}, null, 2));

const canCurate = computed(() => ["admin", "curator"].includes(user.value?.role));
const canReview = computed(() => ["admin", "reviewer"].includes(user.value?.role));
const fulltextById = computed(() => Object.fromEntries((fulltext.value.sources || []).map((x: any) => [x.source_id, x])));

async function load() {
  error.value = "";
  try {
    const params = new URLSearchParams({ limit: "25", offset: String(page.value * 25) });
    if (query.value) params.set("query", query.value);
    const [sourceResult, draftResult, trashResult, fulltextResult] = await Promise.all([
      api<any>(`/api/v1/library/sources?${params}`),
      api<any>("/api/v1/admin/library/drafts"),
      api<any>("/api/v1/library/trash?limit=100"),
      api<any>("/api/v1/library/fulltext"),
    ]);
    sources.value = sourceResult.sources; total.value = sourceResult.total;
    drafts.value = draftResult.drafts; trash.value = trashResult.sources; fulltext.value = fulltextResult;
  } catch (e) { error.value = (e as Error).message; }
}

function openEdit(source: any) {
  editing.value = JSON.parse(JSON.stringify(source));
  editAllowed.value = (editing.value.allowed_uses || []).join(",");
  editScreening.value = JSON.stringify(editing.value.screening || {}, null, 2);
  editNotes.value = JSON.stringify(editing.value.notes || {}, null, 2);
}
async function saveEdit() {
  try {
    const item = editing.value;
    item.allowed_uses = editAllowed.value.split(",").map((x: string) => x.trim()).filter(Boolean);
    item.screening = JSON.parse(editScreening.value); item.notes = JSON.parse(editNotes.value);
    const revision = item._revision;
    const body = { ...item };
    for (const key of ["tier", "source_quality_score", "_catalog", "_revision"]) delete body[key];
    await api(`/api/v1/library/sources/${encodeURIComponent(item.source_id)}`, {
      method: "PATCH", headers: { "If-Match": revision }, body: jsonBody(body),
    });
    editing.value = null; message.value = "文献已更新并重新筛选"; await load();
  } catch (e) { error.value = (e as Error).message; }
}
async function toggle(source: any) {
  try {
    await api(`/api/v1/library/sources/${encodeURIComponent(source.source_id)}/include`, {
      method: "PUT", headers: { "If-Match": source._revision }, body: jsonBody({ include: !source.include }),
    }); await load();
  } catch (e) { error.value = (e as Error).message; }
}
async function moveToTrash(source: any) {
  const reason = prompt("移入回收站的原因", "治理复核后停用"); if (!reason) return;
  try {
    await api(`/api/v1/library/sources/${encodeURIComponent(source.source_id)}?reason=${encodeURIComponent(reason)}`, {
      method: "DELETE", headers: { "If-Match": source._revision },
    }); message.value = "已移入回收站"; await load();
  } catch (e) { error.value = (e as Error).message; }
}
async function restore(row: any) { try { await api(`/api/v1/library/sources/${encodeURIComponent(row.source_id)}/restore`, { method: "POST", headers:{"If-Match":row._revision} }); await load(); } catch (e) { error.value = (e as Error).message; } }
async function purge(row: any) { if (!confirm("永久删除不可恢复，是否继续？")) return; try { await api(`/api/v1/library/trash/${encodeURIComponent(row.source_id)}`, { method: "DELETE", headers:{"If-Match":row._revision} }); await load(); } catch (e) { error.value = (e as Error).message; } }

async function identifyBatch() {
  const queries = identifyInput.value.split("\n").map(x => x.trim()).filter(Boolean);
  if (!queries.length) return;
  try {
    const result = await api<any>("/api/v1/library/autofill/batch", { method: "POST", body: jsonBody({ queries }) });
    identifiedTexts.value = result.drafts.map((row: any) => JSON.stringify(row, null, 2));
    message.value = `识别出 ${result.count} 条；请逐项确认 allowed_uses、五维评分和访问说明`;
  } catch (e) { error.value = (e as Error).message; }
}
async function saveIdentifiedDrafts() {
  try {
    let count = 0;
    for (const text of identifiedTexts.value) {
      const source = JSON.parse(text);
      if (!source.source_id || !source.title) continue;
      for (const key of Object.keys(source)) if (key.startsWith("_")) delete source[key];
      await api("/api/v1/admin/library/drafts", { method: "POST", body: jsonBody({ source }) }); count++;
    }
    identifiedTexts.value = []; message.value = `${count} 条识别结果已进入治理草稿，不会直接发布`; await load();
  } catch (e) { error.value = (e as Error).message; }
}
async function scanDuplicates() { try { const result = await api<any>("/api/v1/library/duplicates"); duplicates.value = result.clusters; } catch (e) { error.value = (e as Error).message; } }

async function createDraft() { try { const source = JSON.parse(draftText.value); const row = await api<any>("/api/v1/admin/library/drafts", { method: "POST", body: jsonBody({ source }) }); message.value = `草稿 ${row.id} 已创建`; await load(); } catch (e) { error.value = (e as Error).message; } }
async function validateDraft(id: string) { try { await api(`/api/v1/admin/library/drafts/${id}/validate`, { method: "POST" }); await load(); } catch (e) { error.value = (e as Error).message; } }
async function publishDraft(id: string) { try { await api(`/api/v1/admin/library/drafts/${id}/publish`, { method: "POST" }); await load(); } catch (e) { error.value = (e as Error).message; } }
async function rejectDraft(id: string) { const reason = prompt("驳回原因"); if (!reason) return; try { await api(`/api/v1/admin/library/drafts/${id}/reject`, { method: "POST", body: jsonBody({ reason }) }); await load(); } catch (e) { error.value = (e as Error).message; } }

function chooseFile(event: Event) { uploadFile.value = (event.target as HTMLInputElement).files?.[0] || null; }
async function attachFulltext() {
  if (!uploadFor.value || !uploadFile.value || !uploadAttested.value) return;
  const params = new URLSearchParams({ access_mode: uploadMode.value, attestation: "authorized_local_governance", rebuild: "true" });
  try {
    const result = await api<any>(`/api/v1/library/sources/${encodeURIComponent(uploadFor.value.source_id)}/fulltext?${params}`, {
      method: "POST", headers: { "content-type": "application/pdf" }, body: uploadFile.value,
    });
    message.value = result.job ? `PDF 已治理入库；索引任务 ${result.job.id} 已排队` : "PDF 已治理入库";
    uploadFor.value = null; uploadFile.value = null; uploadAttested.value = false; await load();
  } catch (e) { error.value = (e as Error).message; }
}
async function detachFulltext(source: any) { if (!confirm("删除本地 PDF 并更新全文索引？")) return; try { const result = await api<any>(`/api/v1/library/sources/${encodeURIComponent(source.source_id)}/fulltext`, { method: "DELETE" }); message.value = result.job ? `删除完成，索引任务 ${result.job.id} 已排队` : "全文已删除"; await load(); } catch (e) { error.value = (e as Error).message; } }

onMounted(load);
</script>

<template>
  <h1 class="page-title">文献工作台</h1>
  <div class="alert">所有识别结果先进入草稿；发布后才写入事实目录。allowed_uses、授权和五维评分必须逐项确认。</div>
  <div v-if="error" class="error">{{ error }}</div><div v-if="message" class="alert">{{ message }}</div>
  <div class="toolbar"><button class="btn" :class="{primary:view==='sources'}" @click="view='sources'">在库文献</button><button class="btn" :class="{primary:view==='trash'}" @click="view='trash'">回收站（{{trash.length}}）</button><input v-if="view==='sources'" class="input" style="max-width:340px" v-model="query" @keyup.enter="page=0;load()" placeholder="搜索 ID、标题、机构或期刊" /><button v-if="view==='sources'" class="btn" @click="page=0;load()">查询</button><span class="muted" v-if="view==='sources'">共 {{ total }} 条</span></div>

  <div v-if="view==='sources'" class="card" style="padding:0;overflow:auto"><table><thead><tr><th>Tier</th><th>ID / 标题</th><th>机构 / 年份</th><th>主题 / 用途</th><th>全文</th><th>状态</th><th>操作</th></tr></thead><tbody>
    <tr v-for="source in sources" :key="source.source_id"><td>{{ source.tier }}</td><td><code>{{ source.source_id }}</code><br>{{ source.title }}</td><td>{{ source.organization }}<br><span class="muted">{{ source.year }}</span></td><td>{{ source.topic }}<br><span class="muted">{{ (source.allowed_uses||[]).join('、') }}</span></td><td><span v-if="fulltextById[source.source_id]?.indexed" class="badge current">已索引 {{fulltextById[source.source_id].chunk_count}}</span><span v-else-if="fulltextById[source.source_id]?.has_pdf" class="badge building">待索引</span><span v-else class="badge missing">无</span></td><td><span class="badge" :class="source.include?'current':'missing'">{{ source.include?'启用':'禁用' }}</span></td><td><div class="row-actions"><button class="btn" @click="openEdit(source)">{{canCurate?'详情/编辑':'详情'}}</button><template v-if="canCurate"><button class="btn" @click="toggle(source)">{{ source.include?'禁用':'启用' }}</button><button class="btn" @click="uploadFor=source">上传全文</button><button v-if="fulltextById[source.source_id]?.has_pdf" class="btn danger" @click="detachFulltext(source)">移除全文</button><button class="btn danger" @click="moveToTrash(source)">回收</button></template></div></td></tr>
  </tbody></table></div>
  <div v-else class="card"><table><thead><tr><th>ID / 标题</th><th>删除原因</th><th>操作</th></tr></thead><tbody><tr v-for="row in trash" :key="row.source_id"><td><code>{{row.source_id}}</code><br>{{row.title}}</td><td>{{row._trash_reason || '—'}}</td><td><button class="btn" v-if="canCurate" @click="restore(row)">恢复</button> <button class="btn danger" v-if="user.role==='admin'" @click="purge(row)">永久删除</button></td></tr></tbody></table></div>
  <div v-if="view==='sources'" class="toolbar" style="justify-content:flex-end;margin-top:10px"><button class="btn" :disabled="page===0" @click="page--;load()">上一页</button><span class="muted">第 {{ page+1 }} 页</span><button class="btn" :disabled="(page+1)*25>=total" @click="page++;load()">下一页</button></div>

  <div v-if="canCurate" class="grid two" style="margin-top:18px">
    <section class="card"><h3>批量识别</h3><p class="muted">每行一个 DOI、URL 或标题。识别不会直接发布。</p><textarea class="input" v-model="identifyInput" placeholder="10.xxxx/xxxxx\nhttps://...\n论文标题"></textarea><div class="toolbar"><button class="btn" @click="identifyBatch">识别</button><button class="btn" @click="scanDuplicates">扫描在库重复项</button></div><div v-for="(_,i) in identifiedTexts" :key="i"><label>识别结果 {{i+1}}（请明确检查 allowed_uses）<textarea class="input" v-model="identifiedTexts[i]"></textarea></label></div><button v-if="identifiedTexts.length" class="btn primary" @click="saveIdentifiedDrafts">确认后保存为草稿</button></section>
    <section class="card"><h3>手工新建完整治理草稿</h3><textarea class="input" v-model="draftText"></textarea><button class="btn primary" style="margin-top:10px" @click="createDraft">保存草稿</button></section>
  </div>
  <section v-if="duplicates.length" class="card" style="margin-top:14px"><h3>重复项人工复核</h3><div v-for="(cluster,i) in duplicates" :key="i"><strong>{{cluster.strong?'强匹配':'弱匹配'}}：{{cluster.reasons.join('、')}}</strong><span class="muted"> — {{cluster.members.map((x:any)=>x.source_id).join(' / ')}}</span></div></section>
  <section class="card" style="margin-top:14px"><h3>草稿流转</h3><table><thead><tr><th>来源</th><th>状态</th><th>复核信息</th><th>操作</th></tr></thead><tbody><tr v-for="row in drafts" :key="row.id"><td>{{ row.source.source_id || '未命名' }}<br><span class="muted">{{ row.source.title }}</span></td><td><span class="badge" :class="row.status">{{ row.status }}</span><div class="danger" v-if="row.validation?.errors?.length">{{ row.validation.errors.join('；') }}</div></td><td>{{row.review_note || '—'}}</td><td><button class="btn" v-if="row.status!=='published' && row.status!=='rejected' && user.role!=='viewer'" @click="validateDraft(row.id)">校验</button> <button class="btn primary" v-if="row.status==='validated' && canReview" @click="publishDraft(row.id)">发布</button> <button class="btn danger" v-if="row.status!=='published' && canReview" @click="rejectDraft(row.id)">驳回</button></td></tr></tbody></table></section>

  <div v-if="editing" class="modal-back" @click.self="editing=null"><div class="modal"><h2>文献详情与编辑</h2><div class="form-grid">
    <label>source_id<input class="input" v-model="editing.source_id" disabled /></label><label>标题<input class="input" v-model="editing.title" :disabled="!canCurate" /></label><label>机构<input class="input" v-model="editing.organization" :disabled="!canCurate" /></label><label>年份<input class="input" type="number" v-model.number="editing.year" :disabled="!canCurate" /></label><label>URL<input class="input" v-model="editing.url" :disabled="!canCurate" /></label><label>DOI<input class="input" v-model="editing.doi" :disabled="!canCurate" /></label><label>PMID<input class="input" v-model="editing.pmid" :disabled="!canCurate" /></label><label>地区<input class="input" v-model="editing.region" :disabled="!canCurate" /></label><label>来源类型<input class="input" v-model="editing.source_type" :disabled="!canCurate" /></label><label>期刊<input class="input" v-model="editing.journal" :disabled="!canCurate" /></label><label>期刊等级<input class="input" type="number" min="1" max="3" v-model.number="editing.journal_tier" :disabled="!canCurate" /></label><label>主题<input class="input" v-model="editing.topic" :disabled="!canCurate" /></label><label>证据类别<input class="input" v-model="editing.evidence_class" :disabled="!canCurate" /></label><label>allowed_uses（逗号）<input class="input" v-model="editAllowed" :disabled="!canCurate" /></label><label>版权说明<textarea class="input" v-model="editing.copyright_note" :disabled="!canCurate"></textarea></label><label>访问说明<textarea class="input" v-model="editing.access_note" :disabled="!canCurate"></textarea></label><label class="span-2">五维评分 JSON<textarea class="input" v-model="editScreening" :disabled="!canCurate"></textarea></label><label class="span-2">备注 JSON<textarea class="input" v-model="editNotes" :disabled="!canCurate"></textarea></label>
  </div><div class="toolbar" style="justify-content:flex-end;margin-top:12px"><button class="btn" @click="editing=null">关闭</button><button v-if="canCurate" class="btn primary" @click="saveEdit">保存</button></div></div></div>

  <div v-if="uploadFor" class="modal-back" @click.self="uploadFor=null"><div class="modal"><h2>治理全文：{{uploadFor.source_id}}</h2><p class="alert">原 PDF 仅保存到 Git 忽略的本地治理目录；不保存原文件名、Cookie 或访问凭证。</p><label>访问模式<select class="input" v-model="uploadMode"><option v-for="mode in fulltext.access_modes" :key="mode">{{mode}}</option></select></label><label>PDF（最大 50 MB）<input class="input" type="file" accept="application/pdf,.pdf" @change="chooseFile" /></label><label><input type="checkbox" v-model="uploadAttested" /> 我确认该副本获准用于本地治理与检索，且不含机构会话或访问凭证</label><div class="toolbar" style="justify-content:flex-end"><button class="btn" @click="uploadFor=null">取消</button><button class="btn primary" :disabled="!uploadFile||!uploadAttested" @click="attachFulltext">上传并排队索引</button></div></div></div>
</template>
