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
const data = ref<any>(null);
const freshness = ref<any>(null);
const message = ref("");
const acting = ref("");
const jobActions = [
  ["quality_gate", "运行严格质量门"],
  ["retrieval_evaluation", "运行检索评测"],
  ["report_evaluation", "运行报告评测"],
  ["api_experiment", "运行匿名 API 实验"],
];
const metricLabels: Record<string, string> = {
  query_count: "查询数", match_rate: "命中率", mean_precision_at_5: "平均 Precision@5",
  topic_hit_rate: "主题命中率", mean_topic_precision_at_5: "平均主题 Precision@5",
  expected_class_hit_rate: "预期证据类别命中率", high_trust_sensitive_rate: "高可信敏感问题命中率",
  case_count: "病例数", test_count: "测试数", included_sources: "启用来源", chunk_count: "Chunks",
  golden_query_count: "黄金查询", report_fixture_count: "报告 fixtures", retrieval_match_rate: "检索命中率",
  retrieval_precision_at_5: "检索 Precision@5", retrieval_topic_hit_rate: "检索主题命中率",
  retrieval_topic_precision_at_5: "检索主题 Precision@5", safety_pass_rate: "安全通过率",
  commands_ok: "命令执行", mean_sec: "平均耗时", p95_sec: "P95 耗时", max_sec: "最大耗时",
  target_p95_sec: "目标 P95", max_concurrency: "最大并发", passed: "通过",
};
const qualityFreshness = computed(() => freshness.value?.items?.find((item: any) => item.artifact === "quality_gate"));
const reportSystems = computed(() => Object.entries(data.value?.report?.summary || {}).map(([name, metrics]) => ({ name, metrics })));

function formatMetric(key: string, value: any) {
  if (typeof value === "boolean") return value ? "通过" : "未通过";
  if (typeof value === "number" && (key.includes("rate") || key.includes("precision"))) return `${(value * 100).toFixed(1)}%`;
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value ?? "—");
}
function entries(value: any) {
  return Object.entries(value || {}).filter(([, item]) => ["string", "number", "boolean"].includes(typeof item));
}
function time(value: any) {
  if (!value) return "—";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

async function load() {
  const [quality, fresh] = await Promise.all([api("/api/v1/admin/quality/runs"), api("/api/v1/admin/freshness")]);
  data.value = quality;
  freshness.value = fresh;
}

async function run(jobType: string) {
  acting.value = jobType;
  try {
    const row = await api<any>("/api/v1/admin/jobs", { method: "POST", body: jsonBody({ job_type: jobType, parameters: {} }) });
    message.value = `任务 ${row.id} 已排队；结果完成后本页会自动刷新。`;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 10_000 });
</script>

<template>
  <PageHeader title="质量评测" description="检索质量、安全过滤、报告安全和性能分别呈现，避免混淆指标含义。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="warning"><strong>指标边界：</strong>calibrated_query_only 是主检索质量；metadata_filter_safety 只检查元数据过滤安全。两者都不验证 PPG 血压估算准确性。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }} <RouterLink class="inline-link" to="/jobs">查看任务</RouterLink></FeedbackBanner>

  <div v-if="['admin','reviewer'].includes(user.role)" class="quality-actions">
    <button v-for="action in jobActions" :key="action[0]" class="btn" :class="{ primary: action[0] === 'quality_gate' }" :disabled="!!acting" @click="run(action[0])">{{ acting === action[0] ? "正在排队…" : action[1] }}</button>
  </div>

  <div v-if="loading" class="card loading-panel">正在读取评测报告和输入指纹…</div>
  <template v-else-if="data">
    <section class="card quality-gate-hero">
      <div><small>严格质量门</small><div class="gate-status"><StatusBadge :status="qualityFreshness?.status || 'missing'" /><strong :class="data.quality_gate?.passed && qualityFreshness?.status === 'current' ? 'success' : 'danger'">{{ data.quality_gate?.passed && qualityFreshness?.status === "current" ? "当前报告通过" : (qualityFreshness?.status === "stale" ? "报告已过期" : "尚未通过") }}</strong></div><p>报告时间：{{ time(data.quality_gate?.timestamp) }} · 输入指纹状态决定这份报告是否仍有效。</p></div>
      <div class="criteria-grid">
        <div v-for="(value, key) in data.quality_gate?.criteria || {}" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><StatusBadge :status="value ? 'current' : 'failed'" :label="value ? '通过' : '未通过'" /></div>
      </div>
    </section>

    <div class="grid two quality-columns">
      <section class="card metric-panel primary-metric">
        <div class="section-heading"><div><small>主检索指标</small><h2>Calibrated query-only</h2><p>不依赖预先注入元数据过滤条件的自然查询表现。</p></div><StatusBadge status="current" label="主指标" /></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.trust_calibration?.retrieval_summary)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}</strong></div></div>
      </section>
      <section class="card metric-panel safety-metric">
        <div class="section-heading"><div><small>安全检查</small><h2>Metadata filter safety</h2><p>确认 allowed_uses 和证据类别过滤没有越界泄漏。</p></div><StatusBadge status="disabled" label="安全检查（非主指标）" /></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.trust_calibration?.metadata_filter_safety_summary)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}</strong></div></div>
      </section>
    </div>

    <div class="grid two quality-columns">
      <section class="card metric-panel">
        <div class="section-heading"><div><h2>质量门规模与结果</h2><p>严格门槛实际使用的匿名聚合指标。</p></div></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.quality_gate?.metrics)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}</strong></div></div>
      </section>
      <section class="card metric-panel">
        <div class="section-heading"><div><h2>性能基准</h2><p>不包含原始病例内容，只展示聚合耗时。</p></div><StatusBadge :status="data.benchmark?.passed ? 'current' : 'failed'" :label="data.benchmark?.passed ? '达标' : '未达标'" /></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.benchmark)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}<template v-if="String(key).endsWith('_sec')"> s</template></strong></div></div>
      </section>
    </div>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>报告评测系统对照</h2><p>系统级聚合结果；不提供个案浏览。</p></div></div>
      <div v-if="reportSystems.length" class="table-scroll"><table><thead><tr><th>系统</th><th>摘要</th><th>证据</th><th>高质量证据</th><th>PPG 局限提示</th><th>安全通过</th></tr></thead><tbody>
        <tr v-for="row in reportSystems" :key="row.name"><td><strong>{{ row.name }}</strong></td><td>{{ formatMetric("has_summary", (row.metrics as any).has_summary) }}</td><td>{{ formatMetric("has_evidence", (row.metrics as any).has_evidence) }}</td><td>{{ formatMetric("has_high_quality_evidence", (row.metrics as any).has_high_quality_evidence) }}</td><td>{{ formatMetric("has_ppg_limitation", (row.metrics as any).has_ppg_limitation) }}</td><td><StatusBadge :status="(row.metrics as any).safety_pass >= 1 ? 'current' : 'failed'" :label="formatMetric('safety_pass_rate', (row.metrics as any).safety_pass)" /></td></tr>
      </tbody></table></div>
      <EmptyState v-else title="尚无报告评测结果" />
    </section>
  </template>
</template>
