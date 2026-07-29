<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { api } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import ProgressBar from "../components/ProgressBar.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

const user = inject<Ref<any>>("adminUser")!;
const rows = ref<any[]>([]);
const events = ref<Record<string, any[]>>({});
const statusFilter = ref("");
const typeFilter = ref("");
const page = ref(0);
const pageSize = ref(20);
const acting = ref("");
const reviewerJobTypes = new Set(["quality_gate", "retrieval_evaluation", "report_evaluation", "api_experiment", "kb_audit"]);
const jobLabels: Record<string, string> = {
  rescreen: "重新筛选来源",
  ingest_chunks: "摘要 chunks / 哈希索引",
  build_chroma: "Chroma / BGE",
  build_fulltext: "本地全文索引",
  build_openai_processed: "OpenAI 摘要 Embedding",
  build_openai_fulltext: "OpenAI 全文 Embedding",
  kb_audit: "知识库审计",
  quality_gate: "严格质量门",
  retrieval_evaluation: "检索评测",
  report_evaluation: "报告评测",
  api_experiment: "匿名 API 实验",
  validate_config_draft: "配置草稿回归",
  rollback_config_revision: "配置回滚验证",
};

const filtered = computed(() => rows.value.filter((row) => !typeFilter.value || row.job_type === typeFilter.value));
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
const visibleRows = computed(() => filtered.value.slice(page.value * pageSize.value, (page.value + 1) * pageSize.value));
const jobTypes = computed(() => [...new Set(rows.value.map((row) => row.job_type))].sort());
const activeCount = computed(() => rows.value.filter((row) => ["queued", "running", "cancelling"].includes(row.status)).length);

watch([statusFilter, typeFilter, pageSize], () => { page.value = 0; });
watch(totalPages, () => { if (page.value >= totalPages.value) page.value = totalPages.value - 1; });

function canRetry(row: any) {
  return user.value.role === "admin" || (user.value.role === "reviewer" && reviewerJobTypes.has(row.job_type));
}
function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

async function load() {
  const query = statusFilter.value ? `?status=${encodeURIComponent(statusFilter.value)}` : "";
  const result = await api<any>(`/api/v1/admin/jobs${query}`);
  rows.value = result.jobs || [];
  for (const row of rows.value.filter((item) => events.value[item.id] && ["running", "cancelling"].includes(item.status))) {
    await loadEvents(row.id, true);
  }
}

async function retry(id: string) {
  acting.value = id;
  try {
    await api(`/api/v1/admin/jobs/${id}/retry`, { method: "POST" });
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function cancel(row: any) {
  if (row.status !== "queued" && !confirm("将向正在运行的子进程发送终止信号，确定继续？")) return;
  acting.value = row.id;
  try {
    await api(`/api/v1/admin/jobs/${row.id}/cancel`, { method: "POST" });
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function loadEvents(id: string, silent = false) {
  try {
    const result = await api<any>(`/api/v1/admin/jobs/${id}/events`);
    events.value[id] = result.events || [];
  } catch (reason) {
    if (!silent) error.value = reason instanceof Error ? reason.message : String(reason);
  }
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 3_000 });
</script>

<template>
  <PageHeader title="任务中心" description="常驻 Worker 自动领取白名单任务；知识库、全文索引和质量门分别互斥。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner kind="info">
    当前有 <strong>{{ activeCount }}</strong> 个排队或运行任务。日志、事件和错误码均经过脱敏；页面每 3 秒自动刷新。
  </FeedbackBanner>

  <section class="card filter-bar">
    <label>状态
      <select class="input" v-model="statusFilter" @change="refresh()">
        <option value="">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="succeeded">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option><option value="interrupted">已中断</option>
      </select>
    </label>
    <label>任务类型
      <select class="input" v-model="typeFilter">
        <option value="">全部类型</option><option v-for="type in jobTypes" :key="type" :value="type">{{ jobLabels[type] || type }}</option>
      </select>
    </label>
    <label>每页
      <select class="input" v-model.number="pageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select>
    </label>
    <span class="muted filter-summary">{{ filtered.length }} 个任务</span>
  </section>

  <section class="card table-card">
    <div v-if="loading" class="loading-panel">正在加载任务队列…</div>
    <div v-else-if="visibleRows.length" class="table-scroll">
      <table class="jobs-table">
        <thead><tr><th>任务</th><th>状态与进度</th><th>时间</th><th>结果 / 事件</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="row in visibleRows" :key="row.id">
            <td><strong>{{ jobLabels[row.job_type] || row.job_type }}</strong><code class="block-code">{{ row.id }}</code><span class="muted">资源锁：{{ row.resource_lock }} · 第 {{ row.attempt }} 次</span></td>
            <td><StatusBadge :status="row.status" /><ProgressBar :value="row.progress" :status="row.status" /><span v-if="row.error_code" class="field-error">错误码：{{ row.error_code }}</span></td>
            <td><span>{{ formatDate(row.created_at) }}</span><small>开始：{{ formatDate(row.started_at) }}</small><small>结束：{{ formatDate(row.finished_at) }}</small></td>
            <td>
              <details @toggle="($event.target as HTMLDetailsElement).open && loadEvents(row.id)">
                <summary>查看脱敏日志与事件</summary>
                <pre v-if="row.log_tail" class="code compact-code">{{ row.log_tail }}</pre>
                <div v-if="events[row.id]?.length" class="event-list">
                  <div v-for="event in events[row.id]" :key="event.sequence"><span>{{ event.created_at }}</span><StatusBadge :status="event.level === 'error' ? 'failed' : 'current'" :label="event.level" /><p>{{ event.message }}</p></div>
                </div>
                <p v-else class="muted">展开后加载事件；任务运行时会持续更新。</p>
              </details>
            </td>
            <td><div class="row-actions">
              <button class="btn" v-if="['failed','cancelled','interrupted'].includes(row.status) && canRetry(row)" :disabled="!!acting" @click="retry(row.id)">重试</button>
              <button class="btn danger" v-if="['queued','running','cancelling'].includes(row.status) && user.role === 'admin'" :disabled="!!acting || row.status === 'cancelling'" @click="cancel(row)">{{ row.status === "queued" ? "取消" : "终止" }}</button>
            </div></td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState v-else-if="!loading" title="没有匹配的任务" detail="调整状态或类型筛选后重试。" />
    <div v-if="filtered.length > pageSize" class="pagination">
      <button class="btn" :disabled="page === 0" @click="page--">上一页</button><span>第 {{ page + 1 }} / {{ totalPages }} 页</span><button class="btn" :disabled="page + 1 >= totalPages" @click="page++">下一页</button>
    </div>
  </section>
</template>
