<script setup lang="ts">
import { computed, inject, ref, type Ref } from "vue";
import { RouterLink } from "vue-router";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import { artifactMeta } from "../uiLabels";

const user = inject<Ref<any>>("adminUser")!;
const items = ref<any[]>([]);
const manifests = ref<Record<string, any>>({});
const message = ref("");
const enqueuing = ref("");
const jobs = [
  { type: "rescreen", label: "更新资料入选结果", group: "资料整理", description: "按照当前规则重新确认哪些资料可以用于回答。" },
  { type: "ingest_chunks", label: "更新可检索内容", group: "资料整理", description: "把最新资料整理成系统可以引用的内容。" },
  { type: "build_chroma", label: "更新本地智能检索", group: "本地检索", description: "在本机更新语义检索，不会把资料发送到外部。" },
  { type: "build_fulltext", label: "更新本地全文检索", group: "本地检索", description: "只处理已登记使用范围的全文；授权状态仍需单独确认。" },
  { type: "build_openai_processed", label: "同步云端摘要检索", group: "云端检索", description: "把经过治理的摘要同步到已配置的语义检索服务。" },
  { type: "build_openai_fulltext", label: "同步云端全文检索", group: "云端检索", description: "仅在服务设置有效时处理符合条件的全文内容。" },
];
const manifestRows = computed(() => Object.entries(manifests.value)
  .filter(([key]) => key !== "fulltext_vector" && !key.endsWith("_count"))
  .map(([key, value]) => ({ key, ...(value || {}) })));

function shortHash(value?: string) {
  return value ? `${value.slice(0, 10)}…` : "—";
}

function detailSummary(details: Record<string, any> = {}, status = "") {
  const values = [
    details.included_sources != null ? `${details.included_sources} 份资料` : "",
    details.source_count != null ? `${details.source_count} 份资料` : "",
    details.chunk_count != null ? `${details.chunk_count} 个内容片段` : "",
    details.page_count != null ? `${details.page_count} 页内容` : "",
    details.reason || "",
  ].filter(Boolean);
  if (values.length) return values.join(" · ");
  if (details.passed === true) return "最近一次检查已经通过";
  if (status === "current") return "当前版本已经准备完成";
  if (status === "building") return "系统正在更新";
  return "尚未完成首次更新";
}

async function load() {
  const [freshness, manifestResult] = await Promise.all([
    api<any>("/api/v1/admin/freshness"),
    api<Record<string, any>>("/api/v1/admin/manifests"),
  ]);
  items.value = freshness.items || [];
  manifests.value = manifestResult;
}

async function enqueue(jobType: string) {
  message.value = "";
  enqueuing.value = jobType;
  try {
    await api<any>("/api/v1/admin/jobs", { method: "POST", body: jsonBody({ job_type: jobType, parameters: {} }) });
    message.value = `${jobs.find((item) => item.type === jobType)?.label || "后台处理"}已安排，系统会自动完成。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    enqueuing.value = "";
  }
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 8_000 });
</script>

<template>
  <PageHeader title="内容更新" description="资料或规则变化后，在这里把最新内容同步到各项检索服务。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }} <RouterLink class="inline-link" to="/jobs">前往任务中心</RouterLink></FeedbackBanner>

  <div v-if="loading" class="card loading-panel">正在确认各项内容是否为最新版本…</div>
  <template v-else>
    <div class="artifact-grid">
      <article class="card artifact-card" v-for="item in items" :key="item.artifact">
        <div class="artifact-head"><div><span class="artifact-icon">↻</span><h2>{{ artifactMeta[item.artifact]?.title || item.label }}</h2></div><StatusBadge :status="item.status" /></div>
        <p>{{ artifactMeta[item.artifact]?.description }}</p>
        <p>{{ detailSummary(item.details, item.status) }}</p>
        <details class="technical-details">
          <summary>专业信息</summary>
          <dl class="compact-dl">
            <template v-if="item.input_fingerprint"><dt>当前内容版本</dt><dd><code>{{ shortHash(item.input_fingerprint) }}</code></dd></template>
            <template v-if="item.build_fingerprint"><dt>已更新版本</dt><dd><code>{{ shortHash(item.build_fingerprint) }}</code></dd></template>
            <template v-if="item.last_built_at"><dt>最近更新时间</dt><dd>{{ item.last_built_at }}</dd></template>
          </dl>
        </details>
      </article>
    </div>
    <EmptyState v-if="!items.length" title="还没有可更新的内容" detail="请先在资料管理中添加并发布资料。" />

    <section class="card section-gap">
      <div class="section-heading"><div><h2>手动更新</h2><p>通常由系统自动提示；需要立即同步时也可以从这里开始。</p></div></div>
      <div v-if="user.role === 'admin'" class="job-action-grid">
        <article v-for="job in jobs" :key="job.type" class="job-action">
          <div><small>{{ job.group }}</small><strong>{{ job.label }}</strong><p>{{ job.description }}</p></div>
          <button class="btn" :disabled="!!enqueuing" @click="enqueue(job.type)">{{ enqueuing === job.type ? "正在安排…" : "开始更新" }}</button>
        </article>
      </div>
      <FeedbackBanner v-else kind="info">你可以查看更新状态；开始更新需要系统管理员权限。</FeedbackBanner>
    </section>

    <details class="card section-gap advanced-section">
      <summary><span><strong>版本与模型信息</strong><small>供技术排查使用，日常管理无需关注。</small></span><span>展开</span></summary>
      <div class="table-scroll">
        <table>
          <thead><tr><th>内容类型</th><th>检索方式 / 模型</th><th>规模</th><th>内容版本</th><th>更新时间</th></tr></thead>
          <tbody>
            <tr v-for="row in manifestRows" :key="row.key">
              <td><strong>{{ artifactMeta[row.key]?.title || row.key }}</strong><br><StatusBadge :status="row.status || (row.build_fingerprint ? 'current' : 'missing')" /></td>
              <td>{{ row.backend || "—" }}<br><span class="muted">{{ row.model || row.model_requested || "—" }}</span></td>
              <td>{{ row.source_count ?? "—" }} 份资料<br><span class="muted">{{ row.chunk_count ?? "—" }} 个片段 · {{ row.embedding_dims || row.embedding_dimensions || "—" }} 维</span></td>
              <td><code>{{ shortHash(row.input_fingerprint || row.input_sha256) }}</code></td>
              <td>{{ row.timestamp || "—" }}<br><span class="muted">{{ row.duration_sec != null ? `${row.duration_sec}s` : "" }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-if="!manifestRows.length" title="尚无版本记录" />
    </details>
  </template>
</template>
