import type { HealthStatus } from "../api/evaluations";

export function schedulerHealth(health: Pick<HealthStatus, "scheduler_disabled" | "scheduler">): {
  state: "ok" | "off" | "warn";
  detail: string;
} {
  if (health.scheduler_disabled && health.scheduler.state === "disabled") {
    return { state: "off", detail: "已按配置禁用" };
  }
  return {
    state: health.scheduler.ok ? "ok" : "warn",
    detail: health.scheduler.state === "running"
      ? "单机定时调度器"
      : `调度器状态：${health.scheduler.state || "未知"}`,
  };
}
