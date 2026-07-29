import { onMounted, onUnmounted, ref } from "vue";

type PollingOptions = {
  intervalMs?: number;
  immediate?: boolean;
};

export function usePolling(task: () => Promise<void>, options: PollingOptions = {}) {
  const loading = ref(false);
  const refreshing = ref(false);
  const error = ref("");
  const lastUpdated = ref<Date | null>(null);
  let timer: number | undefined;
  let running = false;

  async function refresh(silent = false) {
    if (running) return;
    running = true;
    if (lastUpdated.value && silent) refreshing.value = true;
    else loading.value = true;
    try {
      await task();
      error.value = "";
      lastUpdated.value = new Date();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : String(reason);
    } finally {
      running = false;
      loading.value = false;
      refreshing.value = false;
    }
  }

  function onVisibilityChange() {
    if (document.visibilityState === "visible") void refresh(true);
  }

  onMounted(() => {
    if (options.immediate !== false) void refresh();
    if ((options.intervalMs || 0) > 0) {
      timer = window.setInterval(() => {
        if (document.visibilityState === "visible") void refresh(true);
      }, options.intervalMs);
      document.addEventListener("visibilitychange", onVisibilityChange);
    }
  });

  onUnmounted(() => {
    if (timer) window.clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisibilityChange);
  });

  return { loading, refreshing, error, lastUpdated, refresh };
}
