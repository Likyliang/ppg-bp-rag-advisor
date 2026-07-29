<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
  lastUpdated?: Date | null;
  refreshing?: boolean;
  refreshable?: boolean;
}>();
defineEmits<{ refresh: [] }>();

function time(value?: Date | null) {
  return value?.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) || "尚未刷新";
}
</script>

<template>
  <header class="page-header">
    <div>
      <h1 class="page-title">{{ title }}</h1>
      <p v-if="description" class="page-description">{{ description }}</p>
    </div>
    <div v-if="refreshable" class="refresh-box">
      <span class="muted">{{ refreshing ? "正在更新…" : `更新于 ${time(lastUpdated)}` }}</span>
      <button class="btn" type="button" :disabled="refreshing" @click="$emit('refresh')">刷新</button>
    </div>
    <slot />
  </header>
</template>
