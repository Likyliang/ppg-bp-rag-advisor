<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status?: string | boolean | null; label?: string }>();
const value = computed(() => {
  if (props.status === true) return "current";
  if (props.status === false) return "missing";
  return String(props.status || "unknown").toLowerCase();
});
const labels: Record<string, string> = {
  current: "可用",
  stale: "需要更新",
  missing: "尚未准备",
  building: "更新中",
  queued: "等待处理",
  running: "处理中",
  cancelling: "正在取消",
  cancelled: "已取消",
  interrupted: "需要重试",
  failed: "处理失败",
  succeeded: "处理完成",
  draft: "待完善",
  validated: "可以发布",
  validating: "正在检查",
  invalid: "需要修改",
  published: "已发布",
  rejected: "未采用",
  active: "使用中",
  disabled: "已停用",
  high: "重点规则",
  medium: "需谨慎",
  low: "常规",
  normal: "常规",
  unknown: "待确认",
};
</script>

<template><span class="badge" :class="value">{{ label || labels[value] || status }}</span></template>
