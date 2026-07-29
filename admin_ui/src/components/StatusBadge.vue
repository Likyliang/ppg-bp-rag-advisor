<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status?: string | boolean | null; label?: string }>();
const value = computed(() => {
  if (props.status === true) return "current";
  if (props.status === false) return "missing";
  return String(props.status || "unknown").toLowerCase();
});
const labels: Record<string, string> = {
  current: "正常",
  stale: "已过期",
  missing: "缺失",
  building: "构建中",
  queued: "排队中",
  running: "运行中",
  cancelling: "取消中",
  cancelled: "已取消",
  interrupted: "已中断",
  failed: "失败",
  succeeded: "已完成",
  draft: "草稿",
  validated: "已校验",
  validating: "校验中",
  invalid: "未通过",
  published: "已发布",
  rejected: "已驳回",
  active: "启用",
  disabled: "停用",
  high: "高风险",
  medium: "中风险",
  low: "低风险",
  unknown: "未知",
};
</script>

<template><span class="badge" :class="value">{{ label || labels[value] || status }}</span></template>
