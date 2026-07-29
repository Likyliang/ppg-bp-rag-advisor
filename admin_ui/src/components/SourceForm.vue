<script setup lang="ts">
import { computed } from "vue";
import {
  allowedUseLabels,
  displayLabel,
  evidenceClassLabels,
  regionLabels,
  sourceTypeLabels,
  topicLabels,
} from "../uiLabels";

const props = withDefaults(defineProps<{
  modelValue: Record<string, any>;
  taxonomy?: Record<string, any>;
  disabled?: boolean;
  sourceIdDisabled?: boolean;
}>(), {
  taxonomy: () => ({}),
  disabled: false,
  sourceIdDisabled: false,
});

const dimensions = [
  ["authority", "权威性"],
  ["recency", "时效性"],
  ["relevance", "相关性"],
  ["accessibility", "可访问性"],
  ["safety_applicability", "安全适用性"],
];

function ensureNotes() {
  if (!props.modelValue.notes || typeof props.modelValue.notes !== "object") props.modelValue.notes = {};
  return props.modelValue.notes;
}

function noteText(key: string) {
  return computed({
    get() {
      const value = ensureNotes()[key];
      if (Array.isArray(value)) return value.join("\n");
      if (value && typeof value === "object") return JSON.stringify(value, null, 2);
      return String(value || "");
    },
    set(value: string) {
      ensureNotes()[key] = key === "summary"
        ? value.trim()
        : value.split("\n").map((item) => item.trim()).filter(Boolean);
    },
  });
}

const summary = noteText("summary");
const keyPoints = noteText("key_points");
const implementationNotes = noteText("implementation_notes");
const allowedUses = computed<string[]>(() => props.taxonomy.allowed_uses || []);
const topics = computed<string[]>(() => props.taxonomy.topics || []);
const evidenceClasses = computed<string[]>(() => props.taxonomy.evidence_classes || []);
const sourceTypes = Object.keys(sourceTypeLabels);

function toggleUse(value: string, checked: boolean) {
  const current = new Set<string>(props.modelValue.allowed_uses || []);
  if (checked) current.add(value);
  else current.delete(value);
  props.modelValue.allowed_uses = [...current];
}
</script>

<template>
  <div class="source-form">
    <fieldset>
      <legend>基本信息</legend>
      <div class="form-grid">
        <label>资料编号
          <input class="input" v-model.trim="modelValue.source_id" :disabled="disabled || sourceIdDisabled" placeholder="例如：nhc_2024_home_bp" />
          <small>用于系统内部识别，发布后不能修改。</small>
        </label>
        <label>年份
          <input class="input" type="number" min="1900" :max="new Date().getFullYear() + 1" v-model.number="modelValue.year" :disabled="disabled" />
        </label>
        <label class="span-2">标题
          <input class="input" v-model.trim="modelValue.title" :disabled="disabled" />
        </label>
        <label>机构
          <input class="input" v-model.trim="modelValue.organization" :disabled="disabled" />
        </label>
        <label>语言
          <select class="input" v-model="modelValue.language" :disabled="disabled">
            <option value="zh">中文</option><option value="en">英文</option>
          </select>
        </label>
        <label>发布地区
          <select class="input" v-model="modelValue.region" :disabled="disabled">
            <option v-for="item in ['global','CN','US','UK','EU','CA','AHA']" :key="item" :value="item">{{ displayLabel(regionLabels, item) }}</option>
          </select>
        </label>
        <label>资料形式
          <select class="input" v-model="modelValue.source_type" :disabled="disabled">
            <option v-if="modelValue.source_type && !sourceTypes.includes(modelValue.source_type)" :value="modelValue.source_type">{{ modelValue.source_type }}</option>
            <option v-for="item in sourceTypes" :key="item" :value="item">{{ displayLabel(sourceTypeLabels, item) }}</option>
          </select>
        </label>
        <label>内容主题
          <select class="input" v-model="modelValue.topic" :disabled="disabled">
            <option value="">请选择</option><option v-for="item in topics" :key="item" :value="item">{{ displayLabel(topicLabels, item) }}</option>
          </select>
        </label>
        <label>可信资料类型
          <select class="input" v-model="modelValue.evidence_class" :disabled="disabled">
            <option value="">请选择</option><option v-for="item in evidenceClasses" :key="item" :value="item">{{ displayLabel(evidenceClassLabels, item) }}</option>
          </select>
        </label>
      </div>
    </fieldset>

    <fieldset>
      <legend>定位与出版信息</legend>
      <div class="form-grid">
        <label class="span-2">公开 URL
          <input class="input" type="url" v-model.trim="modelValue.url" :disabled="disabled" placeholder="https://…" />
        </label>
        <label>DOI<input class="input" v-model.trim="modelValue.doi" :disabled="disabled" /></label>
        <label>PMID<input class="input" v-model.trim="modelValue.pmid" :disabled="disabled" /></label>
        <label>期刊<input class="input" v-model.trim="modelValue.journal" :disabled="disabled" /></label>
        <label>期刊等级
          <select class="input" v-model.number="modelValue.journal_tier" :disabled="disabled">
            <option :value="null">不适用</option><option :value="1">T1 · 顶刊</option><option :value="2">T2 · 主流</option><option :value="3">T3 · 较弱</option>
          </select>
        </label>
      </div>
    </fieldset>

    <fieldset>
      <legend>这份资料可以用于什么（发布前必须确认）</legend>
      <div class="choice-grid">
        <label v-for="item in allowedUses" :key="item" class="choice">
          <input type="checkbox" :checked="(modelValue.allowed_uses || []).includes(item)" :disabled="disabled" @change="toggleUse(item, ($event.target as HTMLInputElement).checked)" />
          <span>{{ displayLabel(allowedUseLabels, item) }}</span>
        </label>
      </div>
      <p v-if="!(modelValue.allowed_uses || []).length" class="field-error">至少选择一种使用方式。</p>
    </fieldset>

    <fieldset>
      <legend>资料可信度评分</legend>
      <p class="fieldset-help">每项 0–5 分，用于决定资料的可信等级和展示顺序。</p>
      <div class="score-grid">
        <label v-for="item in dimensions" :key="item[0]">{{ item[1] }}
          <input class="input" type="number" min="0" max="5" v-model.number="modelValue.screening[item[0]]" :disabled="disabled" />
        </label>
      </div>
    </fieldset>

    <fieldset>
      <legend>版权与获取说明</legend>
      <div class="form-grid">
        <label>版权说明<textarea class="input prose-input" v-model="modelValue.copyright_note" :disabled="disabled"></textarea></label>
        <label>访问说明<textarea class="input prose-input" v-model="modelValue.access_note" :disabled="disabled"></textarea></label>
      </div>
    </fieldset>

    <details class="advanced-panel">
      <summary>策展备注</summary>
      <div class="form-grid">
        <label class="span-2">摘要<textarea class="input prose-input" v-model="summary" :disabled="disabled"></textarea></label>
        <label>关键点（每行一项）<textarea class="input prose-input" v-model="keyPoints" :disabled="disabled"></textarea></label>
        <label>实施备注（每行一项）<textarea class="input prose-input" v-model="implementationNotes" :disabled="disabled"></textarea></label>
      </div>
    </details>

    <label class="switch-row">
      <input type="checkbox" v-model="modelValue.include" :disabled="disabled" />
      <span>发布后启用该来源</span>
    </label>
  </div>
</template>
