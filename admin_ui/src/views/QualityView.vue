<script setup lang="ts">
import { computed, inject, ref, type Ref } from "vue";
import { RouterLink } from "vue-router";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import { reportSystemLabels } from "../uiLabels";

const user = inject<Ref<any>>("adminUser")!;
const data = ref<any>(null);
const freshness = ref<any>(null);
const message = ref("");
const acting = ref("");
const jobActions = [
  ["quality_gate", "运行完整检查"],
  ["retrieval_evaluation", "检查资料检索"],
  ["report_evaluation", "检查报告质量"],
  ["api_experiment", "检查接口表现"],
];
const metricLabels: Record<string, string> = {
  query_count: "测试问题数", match_rate: "找到合适资料", mean_precision_at_5: "前五条资料准确度",
  topic_hit_rate: "主题匹配", mean_topic_precision_at_5: "前五条主题准确度",
  expected_class_hit_rate: "资料类型匹配", high_trust_sensitive_rate: "敏感问题高可信覆盖",
  case_count: "测试样例数", test_count: "自动测试数", included_sources: "可用资料", chunk_count: "内容片段",
  golden_query_count: "标准问题数", report_fixture_count: "报告样例数", retrieval_match_rate: "检索命中",
  retrieval_precision_at_5: "前五条资料准确度", retrieval_topic_hit_rate: "主题命中",
  retrieval_topic_precision_at_5: "主题准确度", safety_pass_rate: "安全通过",
  commands_ok: "检查流程", mean_sec: "平均响应时间", p95_sec: "大多数请求响应", max_sec: "最慢响应",
  target_p95_sec: "响应目标", max_concurrency: "同时处理数量", passed: "检查结果",
  tests: "自动测试", sources: "资料数量", chunks: "内容片段", golden_queries: "标准问题",
  report_fixtures: "报告样例", unsafe_source_leakage: "不安全资料隔离",
  report_required_use_coverage: "回答用途覆盖", report_recommendation_grounding: "建议有资料依据",
  report_sensitive_high_trust: "敏感问题可信资料", report_emergency_consistency: "紧急情况表达一致",
  audit: "资料库完整性", commands: "检查流程", performance: "响应速度",
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
    await api<any>("/api/v1/admin/jobs", { method: "POST", body: jsonBody({ job_type: jobType, parameters: {} }) });
    message.value = "质量检查已安排，完成后本页会自动更新。";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 10_000 });
</script>

<template>
  <PageHeader title="质量检查" description="检查资料是否找得准、报告是否有依据、安全边界是否生效，以及响应速度是否达标。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="info"><strong>口径说明：</strong>自然提问的检索表现是主指标；资料范围筛选只用于检查安全边界，两者分开计算，也都不验证 PPG 血压估算准确性。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }} <RouterLink class="inline-link" to="/jobs">查看任务</RouterLink></FeedbackBanner>

  <div v-if="['admin','reviewer'].includes(user.role)" class="quality-actions">
    <button v-for="action in jobActions" :key="action[0]" class="btn" :class="{ primary: action[0] === 'quality_gate' }" :disabled="!!acting" @click="run(action[0])">{{ acting === action[0] ? "正在排队…" : action[1] }}</button>
  </div>

  <div v-if="loading" class="card loading-panel">正在读取最近一次质量检查结果…</div>
  <template v-else-if="data">
    <section class="card quality-gate-hero">
      <div><small>整体结果</small><div class="gate-status"><StatusBadge :status="qualityFreshness?.status || 'missing'" /><strong :class="data.quality_gate?.passed && qualityFreshness?.status === 'current' ? 'success' : 'danger'">{{ data.quality_gate?.passed && qualityFreshness?.status === "current" ? "所有检查均通过" : (qualityFreshness?.status === "stale" ? "资料变化，需要重新检查" : "存在未通过项目") }}</strong></div><p>检查时间：{{ time(data.quality_gate?.timestamp) }}</p></div>
      <div class="criteria-grid">
        <div v-for="(value, key) in data.quality_gate?.criteria || {}" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><StatusBadge :status="value ? 'current' : 'failed'" :label="value ? '通过' : '未通过'" /></div>
      </div>
    </section>

    <div class="grid two quality-columns">
      <section class="card metric-panel primary-metric">
        <div class="section-heading"><div><small>主要结果</small><h2>自然提问检索表现</h2><p>不预先指定资料标签，直接检查用户自然提问时能否找到合适资料。</p><details class="inline-details"><summary>专业口径</summary><code>calibrated_query_only</code></details></div><StatusBadge status="current" label="主指标" /></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.trust_calibration?.retrieval_summary)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}</strong></div></div>
      </section>
      <section class="card metric-panel safety-metric">
        <div class="section-heading"><div><small>辅助安全检查</small><h2>资料范围边界</h2><p>确认资料用途和资料类型筛选不会放出不该使用的内容。</p><details class="inline-details"><summary>专业口径</summary><code>metadata_filter_safety</code></details></div><StatusBadge status="disabled" label="辅助检查" /></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.trust_calibration?.metadata_filter_safety_summary)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}</strong></div></div>
      </section>
    </div>

    <div class="grid two quality-columns">
      <section class="card metric-panel">
        <div class="section-heading"><div><h2>检查覆盖范围</h2><p>只展示汇总数量，不展示任何个案或原始健康数据。</p></div></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.quality_gate?.metrics)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}</strong></div></div>
      </section>
      <section class="card metric-panel">
        <div class="section-heading"><div><h2>响应速度</h2><p>使用固定匿名样例检查系统是否能及时返回结果。</p></div><StatusBadge :status="data.benchmark?.passed ? 'current' : 'failed'" :label="data.benchmark?.passed ? '达标' : '未达标'" /></div>
        <div class="metric-grid"><div v-for="[key,value] in entries(data.benchmark)" :key="key"><span>{{ metricLabels[String(key)] || key }}</span><strong>{{ formatMetric(String(key), value) }}<template v-if="String(key).endsWith('_sec')"> s</template></strong></div></div>
      </section>
    </div>

    <section class="card section-gap">
      <div class="section-heading"><div><h2>不同回答方式对照</h2><p>比较摘要、资料依据、PPG 局限提示和安全边界；不提供个案浏览。</p></div></div>
      <div v-if="reportSystems.length" class="table-scroll"><table><thead><tr><th>回答方式</th><th>有摘要</th><th>有资料依据</th><th>使用高可信资料</th><th>说明 PPG 局限</th><th>安全通过</th></tr></thead><tbody>
        <tr v-for="row in reportSystems" :key="row.name"><td><strong>{{ reportSystemLabels[row.name] || row.name }}</strong><small>{{ row.name }}</small></td><td>{{ formatMetric("has_summary", (row.metrics as any).has_summary) }}</td><td>{{ formatMetric("has_evidence", (row.metrics as any).has_evidence) }}</td><td>{{ formatMetric("has_high_quality_evidence", (row.metrics as any).has_high_quality_evidence) }}</td><td>{{ formatMetric("has_ppg_limitation", (row.metrics as any).has_ppg_limitation) }}</td><td><StatusBadge :status="(row.metrics as any).safety_pass >= 1 ? 'current' : 'failed'" :label="formatMetric('safety_pass_rate', (row.metrics as any).safety_pass)" /></td></tr>
      </tbody></table></div>
      <EmptyState v-else title="尚无报告评测结果" />
    </section>
  </template>
</template>
