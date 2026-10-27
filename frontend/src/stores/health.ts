import { defineStore } from "pinia";
import { getHealth, type HealthStatus } from "@/api/evaluations";

/**
 * 全局健康状态：MainLayout 与概览页共用一份轮询，避免两处各自每 10 秒请求 /health。
 * 由 MainLayout 在挂载时 start、卸载时 stop。
 */
export const useHealthStore = defineStore("health", {
  state: () => ({
    status: null as HealthStatus | null,
    timer: undefined as number | undefined,
  }),
  actions: {
    async refresh() {
      try {
        this.status = await getHealth();
      } catch {
        this.status = null; // 后端不可达时由 connServices 反映
      }
    },
    start() {
      if (this.timer !== undefined) return;
      this.refresh();
      this.timer = window.setInterval(() => {
        if (document.visibilityState !== "visible") return;
        this.refresh();
      }, 10000);
    },
    stop() {
      if (this.timer !== undefined) window.clearInterval(this.timer);
      this.timer = undefined;
    },
  },
});