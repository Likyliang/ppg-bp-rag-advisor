<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, jsonBody } from "../api";
import EmptyState from "../components/EmptyState.vue";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { allowedUseLabels, displayLabel, evidenceClassLabels } from "../uiLabels";

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

function matchLabel(value: any) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "相关资料";
  if (numeric >= 0.75) return "高度相关";
  if (numeric >= 0.5) return "比较相关";
  return "可供参考";
}

onMounted(loadTaxonomy);
</script>

<template>
  <PageHeader title="回答效果预览" description="输入一个用户可能提出的问题，看看系统会找到哪些资料作为回答依据。" />
  <FeedbackBanner kind="info">这里只预览资料引用效果，不会生成诊断或用药建议，也不代表 PPG 血压估算经过准确性验证。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>

  <section class="card search-console">
    <label class="search-query">用户可能会问
      <div class="search-input-row"><input class="input question-input" v-model="query" @keyup.enter="search" placeholder="例如：手机估算值偏高，我应该怎样用上臂式血压计复测？" /><button class="btn primary" :disabled="searching || !query.trim()" @click="search">{{ searching ? "正在查找…" : "查看可引用资料" }}</button></div>
    </label>
    <button class="advanced-toggle" @click="showAdvanced=!showAdvanced">{{ showAdvanced ? "收起专业筛选" : "专业筛选（可选）" }}</button>
    <div v-if="showAdvanced" class="retrieval-filters">
      <label>最多显示<input class="input" type="number" min="1" max="20" v-model.number="topK" /></label>
      <label>最低可信评分<input class="input" type="number" min="0" max="25" v-model.number="minQuality" placeholder="不限制" /></label>
      <label>资料允许用途
        <select class="input multi-select" v-model="selectedUses" multiple><option v-for="item in taxonomy.allowed_uses" :key="item" :value="item">{{ displayLabel(allowedUseLabels, item) }}</option></select>
        <small>可多选；不选择表示使用问题本身判断。</small>
      </label>
      <label>资料类型
        <select class="input multi-select" v-model="selectedClasses" multiple><option v-for="item in taxonomy.evidence_classes" :key="item" :value="item">{{ displayLabel(evidenceClassLabels, item) }}</option></select>
        <small>用于限定资料范围，不用于提高质量评测分数。</small>
      </label>
    </div>
  </section>

  <FeedbackBanner v-if="warnings.length" kind="warning">{{ warnings.join("；") }}</FeedbackBanner>

  <section v-if="hasSearched" class="results-section">
    <div class="results-head">
      <div><h2>可引用资料</h2><p>找到 {{ evidence.length }} 条与问题相关的内容</p></div>
      <details class="inline-details"><summary>检索说明</summary><p>当前检索方式：{{ backend || "未报告" }}</p></details>
    </div>
    <div v-if="evidence.length" class="evidence-list">
      <article v-for="(item, index) in evidence" :key="`${item.source_id}-${index}`" class="card evidence-card">
        <div class="rank">{{ index + 1 }}</div>
        <div class="evidence-main">
          <div class="evidence-title"><div><small>{{ item.organization || "来源机构未填写" }} · {{ item.year || "年份未知" }}</small><h3>{{ item.title }}</h3></div><div class="match-label">{{ matchLabel(item.score) }}</div></div>
          <p class="snippet">{{ item.snippet }}</p>
          <div class="evidence-meta">
            <span><strong>用于</strong>{{ displayLabel(allowedUseLabels, item.used_for) }}</span>
            <span><strong>资料类型</strong>{{ displayLabel(evidenceClassLabels, item.evidence_class) }}</span>
            <span><strong>可信评分</strong>{{ item.source_quality_score ?? "—" }}/25</span>
          </div>
          <div class="tag-list"><StatusBadge v-for="use in item.allowed_uses || []" :key="use" status="current" :label="displayLabel(allowedUseLabels, use)" /></div>
          <details class="technical-details"><summary>引用信息与专业详情</summary><p class="citation">{{ citation(item) }}</p><p class="citation">内部编号：{{ item.source_id }} · 原始相关分：{{ score(item.score) }}</p></details>
        </div>
      </article>
    </div>
    <EmptyState v-else title="暂时没有找到合适资料" detail="可以换一种更具体的问法，或减少专业筛选条件。" />
  </section>
  <EmptyState v-else title="先输入一个问题" detail="系统会展示可以引用的资料、用途和来源信息。" />
</template>
