<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";

const data = ref<any>(null);
const error = ref("");
const freshnessAlerts = computed(() => data.value?.freshness?.items?.filter((item: any) => item.status !== "current") || []);
const integrationAlerts = computed(() => (data.value?.integrations || [])
  .filter((item: any) => item.enabled && item.channel !== "crossref" && !item.secret_configured)
  .map((item: any) => ({ label: `${item.channel} 密钥`, status: "missing" })));
const alerts = computed(() => [...freshnessAlerts.value, ...integrationAlerts.value]);
const qualityFreshness = computed(() => data.value?.freshness?.items?.find((item: any) => item.artifact === "quality_gate"));
const qualityLabel = computed(() => {
  if (qualityFreshness.value?.status && qualityFreshness.value.status !== "current") return qualityFreshness.value.status.toUpperCase();
  if (data.value?.quality_gate?.passed === true) return "PASS";
  if (data.value?.quality_gate?.passed === false) return "FAIL";
  return "—";
});

async function load() {
  try { data.value = await api("/api/v1/admin/overview"); }
  catch (e) { error.value = (e as Error).message; }
}
onMounted(load);
</script>

<template>
  <h1 class="page-title">概览</h1>
  <div v-if="error" class="error">{{ error }}</div>
  <div v-if="!data" class="card">正在加载…</div>
  <template v-else>
    <div v-if="alerts.length" class="alert"><strong>{{ alerts.length }} 项需要处理：</strong> {{ alerts.map((x:any) => `${x.label}（${x.status}）`).join('、') }}</div>
    <div class="grid cards">
      <div class="card"><div class="stat">{{ data.library?.total ?? '—' }}</div><div class="muted">文献总数</div></div>
      <div class="card"><div class="stat success">{{ data.library?.included ?? '—' }}</div><div class="muted">已启用来源</div></div>
      <div class="card"><div class="stat">{{ data.fulltext?.indexed ?? '—' }}</div><div class="muted">全文已索引</div></div>
      <div class="card"><div class="stat" :class="data.freshness.alert_count ? 'danger' : 'success'">{{ data.freshness.alert_count }}</div><div class="muted">过期/缺失产物</div></div>
      <div class="card"><div class="stat">{{ data.jobs?.queued || 0 }}/{{ data.jobs?.running || 0 }}</div><div class="muted">排队 / 运行任务</div></div>
      <div class="card"><div class="stat" :class="data.quality_gate?.passed && qualityFreshness?.status === 'current' ? 'success' : 'danger'">{{ qualityLabel }}</div><div class="muted">严格质量门</div></div>
    </div>
    <div class="grid two" style="margin-top:14px">
      <section class="card"><h3>产物新鲜度</h3><table><tbody><tr v-for="item in data.freshness.items" :key="item.artifact"><td>{{ item.label }}</td><td><span class="badge" :class="item.status">{{ item.status }}</span></td></tr></tbody></table></section>
      <section class="card"><h3>外部集成</h3><table><tbody><tr v-for="item in data.integrations" :key="item.channel"><td>{{ item.channel }}</td><td>{{ item.provider }}</td><td><span class="badge" :class="item.enabled ? 'current' : 'missing'">{{ item.enabled ? '启用' : '停用' }}</span></td><td>{{ item.secret_configured ? '密钥已配置' : (item.channel === 'crossref' ? '无需密钥' : '无密钥') }}</td></tr></tbody></table></section>
    </div>
  </template>
</template>
