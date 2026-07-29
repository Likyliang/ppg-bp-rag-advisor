<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import { api } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import { artifactMeta, channelLabels } from "../uiLabels";

const data = ref<any>(null);
const freshnessAlerts = computed(() => (data.value?.freshness?.items || [])
  .filter((item: any) => item.status !== "current")
  .map((item: any) => ({
    key: item.artifact,
    title: `${artifactMeta[item.artifact]?.title || item.label}需要处理`,
    detail: item.status === "failed" ? "上次更新没有成功，可以在内容更新页重新执行。" : "资料或规则有变化，需要重新更新后才是最新版本。",
    to: "/knowledge",
  })));
const integrationAlerts = computed(() => (data.value?.integrations || [])
  .filter((item: any) => item.enabled && item.channel !== "crossref" && !item.secret_configured)
  .map((item: any) => ({
    key: `integration:${item.channel}`,
    title: `${channelLabels[item.channel]?.title || "外部服务"}暂不可用`,
    detail: "访问密钥尚未设置，系统会自动使用安全的本地方式。",
    to: "/integrations",
  })));
const governanceAlerts = computed(() => data.value?.fulltext?.license_pending
  ? [{
      key: "fulltext:license_review",
      title: `${data.value.fulltext.license_pending} 份全文需要确认授权`,
      detail: "技术上可读取不等于已经获得使用授权，请逐份核实。",
      to: "/library",
    }]
  : []);
const attentionItems = computed(() => [...governanceAlerts.value, ...freshnessAlerts.value, ...integrationAlerts.value]);
const qualityFreshness = computed(() => data.value?.freshness?.items?.find((item: any) => item.artifact === "quality_gate"));
const qualityLabel = computed(() => {
  if (qualityFreshness.value?.status && qualityFreshness.value.status !== "current") return "需重跑";
  if (data.value?.quality_gate?.passed === true) return "通过";
  if (data.value?.quality_gate?.passed === false) return "未通过";
  return "未运行";
});

function formatDate(value: string | number | null | undefined) {
  if (!value) return "尚未检查";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

async function load() {
  data.value = await api("/api/v1/admin/overview");
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 10_000 });
</script>

<template>
  <PageHeader title="工作概览" description="先看待办，再了解资料、内容更新和质量检查的整体状态。" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <div v-if="loading" class="skeleton-grid"><div v-for="i in 6" :key="i" class="skeleton-card"></div></div>
  <template v-else-if="data">
    <div v-if="attentionItems.length" class="attention-list">
      <RouterLink v-for="item in attentionItems.slice(0, 4)" :key="item.key" class="attention-item" :to="item.to">
        <span class="attention-icon">!</span>
        <span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span>
        <span class="attention-action">去处理 →</span>
      </RouterLink>
    </div>
    <FeedbackBanner v-else kind="success">今天没有需要立即处理的事项，资料和服务状态正常。</FeedbackBanner>

    <div class="grid cards stats-grid">
      <RouterLink class="card stat-card" to="/library"><span class="stat-icon">文</span><span class="stat">{{ data.library?.total ?? "—" }}</span><span class="stat-label">资料总数</span><span class="stat-caption">{{ data.library?.included ?? 0 }} 份正在用于健康解释</span></RouterLink>
      <RouterLink class="card stat-card" to="/library"><span class="stat-icon">全</span><span class="stat">{{ data.fulltext?.indexed ?? "—" }}</span><span class="stat-label">可在本机检索的全文</span><span class="stat-caption">{{ data.fulltext?.license_pending ?? 0 }} 份仍需人工确认授权</span></RouterLink>
      <RouterLink class="card stat-card" to="/knowledge"><span class="stat-icon">↻</span><span class="stat" :class="data.freshness.alert_count ? 'danger' : 'success'">{{ data.freshness.alert_count }}</span><span class="stat-label">需要更新</span><span class="stat-caption">{{ data.freshness.alert_count ? "有内容不是最新版本" : "所有内容均为最新版本" }}</span></RouterLink>
      <RouterLink class="card stat-card" to="/jobs"><span class="stat-icon">时</span><span class="stat">{{ (data.jobs?.queued || 0) + (data.jobs?.running || 0) }}</span><span class="stat-label">后台处理中</span><span class="stat-caption">{{ data.jobs?.failed || 0 }} 项需要重试</span></RouterLink>
      <RouterLink class="card stat-card" to="/quality"><span class="stat-icon">✓</span><span class="stat" :class="data.quality_gate?.passed && qualityFreshness?.status === 'current' ? 'success' : 'danger'">{{ qualityLabel }}</span><span class="stat-label">最近质量检查</span><span class="stat-caption">{{ formatDate(data.quality_gate?.timestamp) }}</span></RouterLink>
    </div>

    <div class="grid two dashboard-panels">
      <section class="card">
        <div class="section-heading"><div><h2>内容更新状态</h2><p>资料或规则修改后，相关内容会提示重新更新。</p></div><RouterLink to="/knowledge">查看内容更新</RouterLink></div>
        <div v-if="data.freshness.items?.length" class="status-list">
          <div v-for="item in data.freshness.items" :key="item.artifact" class="status-row">
            <div><strong>{{ artifactMeta[item.artifact]?.title || item.label }}</strong><small>{{ artifactMeta[item.artifact]?.description }}</small></div>
            <StatusBadge :status="item.status" />
          </div>
        </div>
        <EmptyState v-else title="尚无内容更新记录" detail="完成首次资料整理后会在这里显示。" />
      </section>

      <section class="card">
        <div class="section-heading"><div><h2>外部服务</h2><p>各项服务互相独立，不可用时会安全降级。</p></div><RouterLink to="/integrations">管理服务</RouterLink></div>
        <div class="status-list">
          <div v-for="item in data.integrations" :key="item.channel" class="status-row">
            <div><strong>{{ channelLabels[item.channel]?.title || item.channel }}</strong><small>{{ channelLabels[item.channel]?.description }}</small></div>
            <div class="align-right"><StatusBadge :status="item.enabled ? 'active' : 'disabled'" /><small>{{ item.channel === "crossref" ? "公开服务" : (item.secret_configured ? "连接信息完整" : "需要设置密钥") }}</small></div>
          </div>
        </div>
      </section>
    </div>
  </template>
</template>
