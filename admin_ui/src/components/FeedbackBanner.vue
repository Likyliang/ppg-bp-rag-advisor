<script setup lang="ts">
defineProps<{ kind?: "info" | "warning" | "success" | "error"; dismissible?: boolean }>();
defineEmits<{ dismiss: [] }>();
</script>

<template>
  <div class="feedback" :class="kind || 'info'" role="status">
    <div><slot /></div>
    <button v-if="dismissible" class="feedback-close" type="button" aria-label="关闭" @click="$emit('dismiss')">×</button>
  </div>
</template>
