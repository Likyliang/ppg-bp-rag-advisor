<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import { api } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

const data = ref<any>(null);
const freshnessAlerts = computed(() => data.value?.freshness?.items?.filter((item: any) => item.status !== "current") || []);
const integrationAlerts = computed(() => (data.value?.integrations || [])
  .filter((item: any) => item.enabled && item.channel !== "crossref" && !item.secret_configured)
  .map((item: any) => ({ artifact: `integration:${item.channel}`, label: `${channelName(item.channel)} 密钥`, status: "missing" })));
const governanceAlerts = computed(() => data.value?.fulltext?.license_pending
  ? [{
      artifact: "fulltext:license_review",
      label: `${data.value.fulltext.license_pending} 份全文授权待复核`,
      status: "stale",
    }]
  : []);
const alerts = computed(() => [...freshnessAlerts.value, ...integrationAlerts.value, ...governanceAlerts.value]);
const qualityFreshness = computed(() => data.value?.freshness?.items?.find((item: any) => item.artifact === "quality_gate"));
const qualityLabel = computed(() => {
  if (qualityFreshness.value?.status && qualityFreshness.value.status !== "current") return "需重跑";
  if (data.value?.quality_gate?.passed === true) return "通过";
  if (data.value?.quality_gate?.passed === false) return "未通过";
  return "未运行";
});

function channelName(channel: string) {
  return ({ report_llm: "报告 LLM", embedding: "OpenAI Embedding", evaluation: "评估模型", crossref: "Crossref" } as Record<string, string>)[channel] || channel;
}

function formatDate(value: string | number | null | undefined) {
  if (!value) return "暂无当前报告";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

async function load() {
  data.value = await api("/api/v1/admin/overview");
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 10_000 });
</script>

<template>
  <PageHeader title="概览" description="优先处理会影响证据可追溯性、检索结果或安全验证的告警。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <div v-if="loading" class="skeleton-grid"><div v-for="i in 6" :key="i" class="skeleton-card"></div></div>
  <template v-else-if="data">
    <FeedbackBanner v-if="alerts.length" kind="warning">
      <strong>{{ alerts.length }} 项需要处理。</strong>
      <span>{{ alerts.slice(0, 4).map((item:any) => `${item.label}（${item.status}）`).join("、") }}</span>
      <RouterLink class="inline-link" to="/knowledge">查看索引治理</RouterLink>
    </FeedbackBanner>
    <FeedbackBanner v-else kind="success">核心产物、已启用集成和质量状态当前没有告警。</FeedbackBanner>

    <div class="grid cards stats-grid">
      <RouterLink class="card stat-card" to="/library"><span class="stat">{{ data.library?.total ?? "—" }}</span><span class="muted">文献总数</span><small>{{ data.library?.included ?? 0 }} 条已启用</small></RouterLink>
      <RouterLink class="card stat-card" to="/library"><span class="stat">{{ data.fulltext?.indexed ?? "—" }}</span><span class="muted">全文已索引</span><small>{{ data.fulltext?.with_pdf ?? 0 }} 份本地治理 PDF · {{ data.fulltext?.license_pending ?? 0 }} 份授权待复核</small></RouterLink>
      <RouterLink class="card stat-card" to="/knowledge"><span class="stat" :class="data.freshness.alert_count ? 'danger' : 'success'">{{ data.freshness.alert_count }}</span><span class="muted">过期或缺失产物</span><small>按输入/构建指纹判断</small></RouterLink>
      <RouterLink class="card stat-card" to="/jobs"><span class="stat">{{ data.jobs?.queued || 0 }} / {{ data.jobs?.running || 0 }}</span><span class="muted">排队 / 运行任务</span><small>{{ data.jobs?.failed || 0 }} 个失败任务</small></RouterLink>
      <RouterLink class="card stat-card" to="/quality"><span class="stat" :class="data.quality_gate?.passed && qualityFreshness?.status === 'current' ? 'success' : 'danger'">{{ qualityLabel }}</span><span class="muted">严格质量门</span><small>{{ formatDate(data.quality_gate?.timestamp) }}</small></RouterLink>
      <RouterLink class="card stat-card" to="/knowledge"><span class="stat" :class="data.audit?.unsafe_source_leakage ? 'danger' : 'success'">{{ data.audit?.unsafe_source_leakage ?? "—" }}</span><span class="muted">不安全来源泄漏</span><small>{{ data.audit?.orphan_source_ids ?? 0 }} 个孤立来源 ID</small></RouterLink>
    </div>

    <div class="grid two dashboard-panels">
      <section class="card">
        <div class="section-heading"><div><h2>产物新鲜度</h2><p>上游变化后，下游必须重新构建。</p></div><RouterLink to="/knowledge">管理索引</RouterLink></div>
        <div v-if="data.freshness.items?.length" class="status-list">
          <div v-for="item in data.freshness.items" :key="item.artifact" class="status-row">
            <div><strong>{{ item.label }}</strong><small>{{ item.artifact }}</small></div>
            <StatusBadge :status="item.status" />
          </div>
        </div>
        <EmptyState v-else title="没有新鲜度记录" detail="尚未产生可检查的派生产物。" />
      </section>

      <section class="card">
        <div class="section-heading"><div><h2>外部 API</h2><p>通道隔离，密钥永不回显。</p></div><RouterLink to="/integrations">管理集成</RouterLink></div>
        <div class="status-list">
          <div v-for="item in data.integrations" :key="item.channel" class="status-row">
            <div><strong>{{ channelName(item.channel) }}</strong><small>{{ item.provider }} · {{ item.model || "无模型" }}</small></div>
            <div class="align-right"><StatusBadge :status="item.enabled ? 'active' : 'disabled'" /><small>{{ item.channel === "crossref" ? "无需密钥" : (item.secret_configured ? "密钥已配置" : "无密钥") }}</small></div>
          </div>
        </div>
      </section>
    </div>
  </template>
</template>
