import type { TaskLike } from "@/api/evaluations";

export const TASK_CENTER_LANES = ["basic", "stress", "intelligence"] as const;

export type TaskCenterLane = typeof TASK_CENTER_LANES[number];
export type TaskCenterStatusFilter = "all" | "active" | "completed" | "attention";

export type TaskCenterSources = Record<TaskCenterLane, TaskLike[] | null>;

export interface TaskCenterItem {
  id: string;
  lane: TaskCenterLane;
  status: string;
  model: string;
  timestamp: number;
  durationMs: number | null;
  task: TaskLike;
}

export interface TaskCenterFilter {
  lane: TaskCenterLane | "all";
  status: TaskCenterStatusFilter;
  query: string;
}

export const TASK_CENTER_LANE_META: Record<TaskCenterLane, { label: string; path: string }> = {
  basic: { label: "基础评测", path: "/basic" },
  stress: { label: "压测评测", path: "/stress" },
  intelligence: { label: "能力评测", path: "/intelligence" },
};

const ACTIVE_STATUSES = new Set(["queued", "running", "pending"]);
const ATTENTION_STATUSES = new Set(["failed", "error", "interrupted"]);

function timeValue(value: unknown): number {
  if (!value) return 0;
  const timestamp = new Date(String(value)).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function activityTime(lane: TaskCenterLane, task: TaskLike): number {
  if (lane === "basic") {
    return timeValue(task.finished_at)
      || timeValue(task.started_at)
      || timeValue(task.updated_at)
      || timeValue(task.created_at);
  }
  return timeValue(task.completed_at)
    || timeValue(task.updated_at)
    || timeValue(task.started_at)
    || timeValue(task.created_at);
}

function durationValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const duration = Number(value);
  return Number.isFinite(duration) && duration >= 0 ? duration : null;
}

export function buildTaskCenterItems(sources: TaskCenterSources): TaskCenterItem[] {
  return TASK_CENTER_LANES
    .flatMap((lane) => (sources[lane] ?? []).map((task) => ({
      id: String(task.task_id),
      lane,
      status: String(task.status || "pending"),
      model: String(task.model_id || "-"),
      timestamp: activityTime(lane, task),
      durationMs: durationValue(task.duration_ms),
      task,
    })))
    .sort((a, b) => b.timestamp - a.timestamp || a.id.localeCompare(b.id));
}

export function filterTaskCenterItems(
  items: TaskCenterItem[],
  filter: TaskCenterFilter,
): TaskCenterItem[] {
  const query = filter.query.trim().toLowerCase();
  return items.filter((item) => {
    if (filter.lane !== "all" && item.lane !== filter.lane) return false;
    if (filter.status === "active" && !ACTIVE_STATUSES.has(item.status)) return false;
    if (filter.status === "completed" && item.status !== "completed") return false;
    if (filter.status === "attention" && !ATTENTION_STATUSES.has(item.status)) return false;
    if (query && !item.id.toLowerCase().includes(query) && !item.model.toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });
}

export function taskDetailLocation(lane: TaskCenterLane, taskId: string) {
  return {
    path: TASK_CENTER_LANE_META[lane].path,
    query: { task_id: taskId },
  };
}

export function taskIdFromQuery(value: unknown): string | null {
  const raw = Array.isArray(value) ? value[0] : value;
  const taskId = String(raw ?? "").trim();
  return taskId || null;
}
