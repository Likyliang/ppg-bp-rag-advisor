<script setup lang="ts">
import { computed, inject, ref, type Ref } from "vue";
import { RouterLink } from "vue-router";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

const user = inject<Ref<any>>("adminUser")!;
const items = ref<any[]>([]);
const manifests = ref<Record<string, any>>({});
const message = ref("");
const enqueuing = ref("");
const jobs = [
  { type: "rescreen", label: "重新筛选来源", group: "目录治理", description: "按当前筛选规则更新来源入选结果。" },
  { type: "ingest_chunks", label: "重建摘要与哈希索引", group: "摘要索引", description: "重新生成摘要 chunks 和本地哈希向量。" },
  { type: "build_chroma", label: "重建 Chroma / BGE", group: "摘要索引", description: "使用本地 BGE 模型构建 Chroma，和 OpenAI 完全独立。" },
  { type: "build_fulltext", label: "重建本地全文索引", group: "全文索引", description: "仅处理具备访问模式和用途约束的本地治理全文；历史授权待复核会单独告警。" },
  { type: "build_openai_processed", label: "构建 OpenAI 摘要 Embedding", group: "OpenAI", description: "发送治理后的摘要 chunks，不复用 Chroma 开关。" },
  { type: "build_openai_fulltext", label: "构建 OpenAI 全文 Embedding", group: "OpenAI", description: "仅在集成配置有效时执行；历史授权待复核会继续显示治理告警。" },
];
const manifestRows = computed(() => Object.entries(manifests.value)
  .filter(([key]) => key !== "fulltext_vector" && !key.endsWith("_count"))
  .map(([key, value]) => ({ key, ...(value || {}) })));

function shortHash(value?: string) {
  return value ? `${value.slice(0, 10)}…` : "—";
}

function detailSummary(details: Record<string, any> = {}) {
  const values = [
    details.source_count != null ? `${details.source_count} 来源` : "",
    details.chunk_count != null ? `${details.chunk_count} chunks` : "",
    details.page_count != null ? `${details.page_count} 页` : "",
    details.reason || "",
  ].filter(Boolean);
  return values.join(" · ") || "等待首次构建";
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
    const row = await api<any>("/api/v1/admin/jobs", { method: "POST", body: jsonBody({ job_type: jobType, parameters: {} }) });
    message.value = `任务 ${row.id} 已进入队列，常驻 Worker 将自动执行。`;
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
  <PageHeader title="知识库与索引" description="状态由输入指纹和构建指纹决定；仅比较数量不足以证明索引是当前版本。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }} <RouterLink class="inline-link" to="/jobs">前往任务中心</RouterLink></FeedbackBanner>

  <div v-if="loading" class="card loading-panel">正在核对目录、chunks 和各索引指纹…</div>
  <template v-else>
    <div class="artifact-grid">
      <article class="card artifact-card" v-for="item in items" :key="item.artifact">
        <div class="artifact-head"><div><small>{{ item.artifact }}</small><h2>{{ item.label }}</h2></div><StatusBadge :status="item.status" /></div>
        <p>{{ detailSummary(item.details) }}</p>
        <dl class="compact-dl">
          <template v-if="item.input_fingerprint"><dt>当前输入</dt><dd><code>{{ shortHash(item.input_fingerprint) }}</code></dd></template>
          <template v-if="item.build_fingerprint"><dt>构建指纹</dt><dd><code>{{ shortHash(item.build_fingerprint) }}</code></dd></template>
          <template v-if="item.last_built_at"><dt>最后构建</dt><dd>{{ item.last_built_at }}</dd></template>
        </dl>
      </article>
    </div>
    <EmptyState v-if="!items.length" title="没有派生产物" detail="请先完成文献目录和 chunks 初始化。" />

    <section class="card section-gap">
      <div class="section-heading"><div><h2>构建操作</h2><p>任务类型和参数由服务端白名单限制，并按知识库、全文和质量资源互斥。</p></div></div>
      <div v-if="user.role === 'admin'" class="job-action-grid">
        <article v-for="job in jobs" :key="job.type" class="job-action">
          <div><small>{{ job.group }}</small><strong>{{ job.label }}</strong><p>{{ job.description }}</p></div>
          <button class="btn" :disabled="!!enqueuing" @click="enqueue(job.type)">{{ enqueuing === job.type ? "正在排队…" : "创建任务" }}</button>
        </article>
      </div>
      <FeedbackBanner v-else kind="info">当前角色只读；索引构建仅管理员可创建。</FeedbackBanner>
    </section>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>构建清单</h2><p>用于核对模型、规模、上游指纹和最近构建时间。</p></div></div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>产物</th><th>后端 / 模型</th><th>规模</th><th>输入指纹</th><th>构建时间</th></tr></thead>
          <tbody>
            <tr v-for="row in manifestRows" :key="row.key">
              <td><strong>{{ row.key }}</strong><br><StatusBadge :status="row.status || (row.build_fingerprint ? 'current' : 'missing')" /></td>
              <td>{{ row.backend || "—" }}<br><span class="muted">{{ row.model || row.model_requested || "—" }}</span></td>
              <td>{{ row.source_count ?? "—" }} 来源<br><span class="muted">{{ row.chunk_count ?? "—" }} chunks · {{ row.embedding_dims || row.embedding_dimensions || "—" }} 维</span></td>
              <td><code>{{ shortHash(row.input_fingerprint || row.input_sha256) }}</code></td>
              <td>{{ row.timestamp || "—" }}<br><span class="muted">{{ row.duration_sec != null ? `${row.duration_sec}s` : "" }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-if="!manifestRows.length" title="尚无构建清单" />
    </section>
  </template>
</template>
