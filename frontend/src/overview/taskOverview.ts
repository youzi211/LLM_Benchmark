import type { TaskLike } from "@/api/evaluations";

export const OVERVIEW_LANES = ["basic", "stress", "intelligence"] as const;

export type OverviewLane = typeof OVERVIEW_LANES[number];

export type OverviewTaskSources = Record<OverviewLane, TaskLike[] | null>;

export interface OverviewRunningTask {
  id: string;
  type: OverviewLane;
  model: string;
  startedAt?: number;
  progress?: number;
  stage?: string;
}

export interface OverviewRecentTask {
  lane: OverviewLane;
  task: TaskLike;
}

export interface OverviewTaskSummary {
  runningTasks: OverviewRunningTask[];
  recentTasks: OverviewRecentTask[];
  failedLanes: OverviewLane[];
}

const RUNNING_STATUSES = new Set(["running", "pending", "queued"]);
const FINAL_STATUSES = new Set(["completed", "partial", "failed", "interrupted", "error"]);

function timestamp(value: unknown): number | undefined {
  if (!value) return undefined;
  const valueMs = new Date(String(value)).getTime();
  return Number.isFinite(valueMs) ? valueMs : undefined;
}

function startedAt(task: TaskLike): number | undefined {
  return timestamp(task.started_at) ?? timestamp(task.created_at);
}

function recentAt(task: TaskLike): number {
  return timestamp(task.finished_at)
    ?? timestamp(task.updated_at)
    ?? timestamp(task.started_at)
    ?? timestamp(task.created_at)
    ?? 0;
}

function progressOf(task: TaskLike): number | undefined {
  const detail = task.progress_detail;
  const raw = detail && typeof detail === "object"
    ? (detail as Record<string, unknown>).overall_percent ?? (detail as Record<string, unknown>).percent
    : undefined;
  const progress = Number(raw);
  if (!Number.isFinite(progress)) return undefined;
  return Math.max(0, Math.min(progress, 100));
}

function stageOf(task: TaskLike): string {
  if (typeof task.progress === "string" && task.progress.trim()) return task.progress;
  return String(task.status) === "running" ? "运行中" : "等待中";
}

export function buildOverviewTaskSummary(
  sources: OverviewTaskSources,
): OverviewTaskSummary {
  const failedLanes = OVERVIEW_LANES.filter((lane) => sources[lane] === null);
  const loadedTasks = OVERVIEW_LANES.flatMap((lane) =>
    (sources[lane] ?? []).map((task) => ({ lane, task })),
  );

  const runningTasks = loadedTasks
    .filter(({ task }) => RUNNING_STATUSES.has(String(task.status)))
    .map(({ lane, task }): OverviewRunningTask => ({
      id: task.task_id,
      type: lane,
      model: String(task.model_id || "—"),
      startedAt: startedAt(task),
      progress: progressOf(task),
      stage: stageOf(task),
    }))
    .sort((a, b) => (b.startedAt ?? 0) - (a.startedAt ?? 0));

  const recentTasks = loadedTasks
    .filter(({ task }) => FINAL_STATUSES.has(String(task.status)))
    .sort((a, b) => recentAt(b.task) - recentAt(a.task))
    .slice(0, 5);

  return {
    runningTasks,
    recentTasks,
    failedLanes,
  };
}
