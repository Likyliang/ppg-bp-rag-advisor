<script setup lang="ts">
defineProps<{ title: string; detail?: string }>();
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon">○</div>
    <strong>{{ title }}</strong>
    <span v-if="detail" class="muted">{{ detail }}</span>
    <slot />
  </div>
</template>
