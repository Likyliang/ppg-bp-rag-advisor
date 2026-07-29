<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";

const query = ref("");
const topK = ref(5);
const selectedUses = ref<string[]>([]);
const selectedClasses = ref<string[]>([]);
const minQuality = ref<number | null>(null);
const taxonomy = ref<any>({ allowed_uses: [], evidence_classes: [] });
const evidence = ref<any[]>([]);
const warnings = ref<string[]>([]);
const backend = ref("");
const error = ref("");
const searching = ref(false);
const hasSearched = ref(false);
const showAdvanced = ref(false);

async function loadTaxonomy() {
  try { taxonomy.value = await api("/api/v1/library/taxonomy"); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
}

async function search() {
  if (!query.value.trim()) {
    error.value = "请输入要调试的检索问题。";
    return;
  }
  error.value = "";
  searching.value = true;
  try {
    const result = await api<any>("/api/v1/admin/retrieval/search", {
      method: "POST",
      body: jsonBody({
        queries: [query.value.trim()],
        top_k: topK.value,
        allowed_uses: selectedUses.value.length ? selectedUses.value : null,
        evidence_classes: selectedClasses.value.length ? selectedClasses.value : null,
        min_quality_score: minQuality.value,
      }),
    });
    evidence.value = result.evidence || [];
    warnings.value = result.warnings || [];
    backend.value = result.backend || "";
    hasSearched.value = true;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { searching.value = false; }
}

function citation(item: any) {
  return [item.organization, item.year, item.title, item.doi ? `DOI: ${item.doi}` : "", item.url].filter(Boolean).join(". ");
}

function score(value: any) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(4) : String(value ?? "—");
}

onMounted(loadTaxonomy);
</script>

<template>
  <PageHeader title="检索调试台" description="查看实际检索后端、排序分数、元数据过滤、允许用途和引用预览。" />
  <FeedbackBanner kind="warning">只调试已治理证据；任何结果都不得用于证明 PPG 血压估算准确性。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>

  <section class="card search-console">
    <label class="search-query">调试问题
      <div class="search-input-row"><input class="input" v-model="query" @keyup.enter="search" placeholder="例如：手机 PPG 估算偏高后如何用规范袖带复核？" /><button class="btn primary" :disabled="searching || !query.trim()" @click="search">{{ searching ? "检索中…" : "执行检索" }}</button></div>
    </label>
    <button class="advanced-toggle" @click="showAdvanced=!showAdvanced">{{ showAdvanced ? "收起过滤条件" : "展开过滤条件" }}</button>
    <div v-if="showAdvanced" class="retrieval-filters">
      <label>返回条数<input class="input" type="number" min="1" max="20" v-model.number="topK" /></label>
      <label>最低来源质量分<input class="input" type="number" min="0" max="25" v-model.number="minQuality" placeholder="不限制" /></label>
      <label>允许用途
        <select class="input multi-select" v-model="selectedUses" multiple><option v-for="item in taxonomy.allowed_uses" :key="item">{{ item }}</option></select>
        <small>按住 Command/Ctrl 可多选；不选表示不限。</small>
      </label>
      <label>证据类别
        <select class="input multi-select" v-model="selectedClasses" multiple><option v-for="item in taxonomy.evidence_classes" :key="item">{{ item }}</option></select>
        <small>该过滤是安全约束，不属于主检索质量指标。</small>
      </label>
    </div>
  </section>

  <FeedbackBanner v-if="warnings.length" kind="warning">{{ warnings.join("；") }}</FeedbackBanner>

  <section v-if="hasSearched" class="results-section">
    <div class="results-head">
      <div><h2>检索结果</h2><p>{{ evidence.length }} 条证据</p></div>
      <div class="backend-chip"><span>实际后端</span><strong>{{ backend || "未报告" }}</strong></div>
    </div>
    <div v-if="evidence.length" class="evidence-list">
      <article v-for="(item, index) in evidence" :key="`${item.source_id}-${index}`" class="card evidence-card">
        <div class="rank">{{ index + 1 }}</div>
        <div class="evidence-main">
          <div class="evidence-title"><div><code>{{ item.source_id }}</code><h3>{{ item.title }}</h3></div><div class="score-box"><span>排序分</span><strong>{{ score(item.score) }}</strong></div></div>
          <p class="snippet">{{ item.snippet }}</p>
          <div class="evidence-meta">
            <span><strong>实际用途</strong>{{ item.used_for || "—" }}</span>
            <span><strong>证据类别</strong>{{ item.evidence_class || "—" }}</span>
            <span><strong>来源质量</strong>{{ item.source_quality_score ?? "—" }}/25</span>
          </div>
          <div class="tag-list"><StatusBadge v-for="use in item.allowed_uses || []" :key="use" status="current" :label="use" /></div>
          <details><summary>引用预览与来源地址</summary><p class="citation">{{ citation(item) }}</p></details>
        </div>
      </article>
    </div>
    <EmptyState v-else title="没有命中治理证据" detail="可减少过滤条件或改写查询，但不要绕过允许用途约束。" />
  </section>
  <EmptyState v-else title="等待检索问题" detail="执行后会显示真实后端、分数和可审计来源元数据。" />
</template>
