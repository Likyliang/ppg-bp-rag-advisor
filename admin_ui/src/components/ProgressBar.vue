<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ value?: number; status?: string }>();
const normalized = computed(() => Math.max(0, Math.min(100, Number(props.value || 0))));
</script>

<template>
  <div class="progress-wrap">
    <div class="progress-track" :aria-valuenow="normalized" aria-valuemin="0" aria-valuemax="100" role="progressbar">
      <div class="progress-fill" :class="status" :style="{ width: `${normalized}%` }"></div>
    </div>
    <span>{{ normalized }}%</span>
  </div>
</template>
