<script setup lang="ts">
import { computed, inject, ref, watch, type Ref } from "vue";
import { api } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import ProgressBar from "../components/ProgressBar.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import { jobLabels } from "../uiLabels";

const user = inject<Ref<any>>("adminUser")!;
const rows = ref<any[]>([]);
const events = ref<Record<string, any[]>>({});
const statusFilter = ref("");
const typeFilter = ref("");
const page = ref(0);
const pageSize = ref(20);
const acting = ref("");
const reviewerJobTypes = new Set(["quality_gate", "retrieval_evaluation", "report_evaluation", "api_experiment", "kb_audit"]);
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
  <PageHeader title="处理记录" description="查看内容更新、质量检查和规则验证的进度；系统会自动执行，不需要一直停留在本页。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner kind="info">
    当前有 <strong>{{ activeCount }}</strong> 项正在等待或处理中。本页会自动更新，失败项目可以从这里重新执行。
  </FeedbackBanner>

  <section class="card filter-bar">
    <label>状态
      <select class="input" v-model="statusFilter" @change="refresh()">
        <option value="">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="succeeded">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option><option value="interrupted">已中断</option>
      </select>
    </label>
    <label>处理类型
      <select class="input" v-model="typeFilter">
        <option value="">全部类型</option><option v-for="type in jobTypes" :key="type" :value="type">{{ jobLabels[type] || type }}</option>
      </select>
    </label>
    <label>每页
      <select class="input" v-model.number="pageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option></select>
    </label>
    <span class="muted filter-summary">{{ filtered.length }} 条记录</span>
  </section>

  <section class="card table-card">
    <div v-if="loading" class="loading-panel">正在加载处理记录…</div>
    <div v-else-if="visibleRows.length" class="table-scroll">
      <table class="jobs-table">
        <thead><tr><th>处理事项</th><th>状态与进度</th><th>时间</th><th>详情</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="row in visibleRows" :key="row.id">
            <td><strong>{{ jobLabels[row.job_type] || row.job_type }}</strong><small>{{ row.attempt > 1 ? `第 ${row.attempt} 次执行` : "首次执行" }}</small><details class="inline-details"><summary>专业信息</summary><code class="block-code">{{ row.id }}</code><span class="muted">互斥资源：{{ row.resource_lock }}</span></details></td>
            <td><StatusBadge :status="row.status" /><ProgressBar :value="row.progress" :status="row.status" /><span v-if="row.error_code" class="field-error">处理未完成，请查看详情或重试</span></td>
            <td><span>{{ formatDate(row.created_at) }}</span><small>开始：{{ formatDate(row.started_at) }}</small><small>结束：{{ formatDate(row.finished_at) }}</small></td>
            <td>
              <details @toggle="($event.target as HTMLDetailsElement).open && loadEvents(row.id)">
                <summary>查看处理详情</summary>
                <p v-if="row.error_code" class="field-error">错误编号：{{ row.error_code }}</p>
                <pre v-if="row.log_tail" class="code compact-code">{{ row.log_tail }}</pre>
                <div v-if="events[row.id]?.length" class="event-list">
                  <div v-for="event in events[row.id]" :key="event.sequence"><span>{{ event.created_at }}</span><StatusBadge :status="event.level === 'error' ? 'failed' : 'current'" :label="event.level" /><p>{{ event.message }}</p></div>
                </div>
                <p v-else class="muted">展开后加载记录；处理中会持续更新。</p>
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
    <EmptyState v-else-if="!loading" title="没有匹配的处理记录" detail="调整状态或类型筛选后再看。" />
    <div v-if="filtered.length > pageSize" class="pagination">
      <button class="btn" :disabled="page === 0" @click="page--">上一页</button><span>第 {{ page + 1 }} / {{ totalPages }} 页</span><button class="btn" :disabled="page + 1 >= totalPages" @click="page++">下一页</button>
    </div>
  </section>
</template>
