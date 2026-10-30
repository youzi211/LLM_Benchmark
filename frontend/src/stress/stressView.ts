import type { TaskLike } from "@/api/evaluations";

type StressRun = Record<string, unknown>;

export type StressLoadKind = "parallel" | "rate" | "unknown";

export interface StressLoadDisplay {
  label: string;
  axisLabel: string;
  kind: StressLoadKind;
}

export function stressStatusLabel(status?: string, grouped = false): string {
  if (status === "partial" && grouped) return "部分失败";
  return {
    completed: "已完成",
    partial: "部分完成",
    running: "运行中",
    pending: "等待中",
    queued: "排队中",
    failed: "失败",
    error: "错误",
    interrupted: "已中断",
  }[String(status)] ?? String(status ?? "");
}

function positiveNumber(value: unknown): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : undefined;
}

function isUnlimited(value: unknown): boolean {
  return Number(value) === -1;
}

export function stressMetricValue(value: unknown): number | undefined {
  if (value == null || (typeof value === "string" && value.trim() === "")) {
    return undefined;
  }
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : undefined;
}

export function stressRatePercent(value: unknown): number | undefined {
  const rate = stressMetricValue(value);
  if (rate === undefined) return undefined;
  return rate <= 1 ? rate * 100 : rate;
}

function parallelDisplay(value: number | "unlimited"): StressLoadDisplay {
  if (value === "unlimited") {
    return { label: "不限并发", axisLabel: "不限并发", kind: "parallel" };
  }
  return { label: `并发 ${value}`, axisLabel: `P${value}`, kind: "parallel" };
}

function rateDisplay(value: number | "unlimited"): StressLoadDisplay {
  if (value === "unlimited") {
    return { label: "不限速", axisLabel: "不限速", kind: "rate" };
  }
  return { label: `速率 ${value} req/s`, axisLabel: `${value} req/s`, kind: "rate" };
}

export function formatStressLoad(
  run: StressRun,
  requestConfig: Record<string, unknown>,
): StressLoadDisplay {
  const parallel = positiveNumber(run.parallel);
  const rate = positiveNumber(run.rate);
  const openLoop = requestConfig.open_loop;

  if (openLoop === true) {
    if (rate !== undefined) return rateDisplay(rate);
    if (isUnlimited(run.rate)) return rateDisplay("unlimited");
    if (parallel !== undefined) return parallelDisplay(parallel);
    if (isUnlimited(run.parallel)) return parallelDisplay("unlimited");
  } else if (openLoop === false) {
    if (parallel !== undefined) return parallelDisplay(parallel);
    if (isUnlimited(run.parallel)) return parallelDisplay("unlimited");
    if (rate !== undefined) return rateDisplay(rate);
  } else {
    if (parallel !== undefined) return parallelDisplay(parallel);
    if (rate !== undefined) return rateDisplay(rate);
  }

  return { label: "—", axisLabel: "—", kind: "unknown" };
}

export function runsOfTask(task: TaskLike | null): StressRun[] {
  const normalized = task?.normalized_result
    || (task?.raw_result as Record<string, unknown> | undefined)?.normalized_result;
  const runs = normalized && typeof normalized === "object"
    ? (normalized as Record<string, unknown>).runs
    : undefined;
  return Array.isArray(runs)
    ? runs.filter((run): run is StressRun => Boolean(run) && typeof run === "object")
    : [];
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`,
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function stressGroupKey(task: TaskLike): string {
  const config = { ...((task.request_config as Record<string, unknown> | undefined) || {}) };
  delete config.parallel;
  delete config.rate;
  delete config.number;
  return `${task.model_id || ""}:${stableJson(config)}`;
}

function scenarioLabel(task: TaskLike): string {
  const config = (task.request_config || {}) as Record<string, any>;
  const dataset = String(config.dataset || "压测");
  if (config.dataset_args?.target_input_len) return `短回答 · ${config.dataset_args.target_input_len} 输入`;
  if (Number(config.max_tokens) >= 4096) return `长回答 · ${dataset}`;
  if (dataset === "longalpaca") return `长文本 · ${dataset}`;
  return `${dataset} · max ${config.max_tokens ?? "默认"}`;
}

export function stressGroupStatus(statuses: string[]): string {
  if (statuses.includes("running")) return "running";
  if (statuses.includes("pending") || statuses.includes("queued")) return "pending";

  const completed = statuses.includes("completed");
  const failed = statuses.some((status) => ["failed", "error"].includes(status));
  const interrupted = statuses.includes("interrupted");
  if (statuses.includes("partial") || (completed && (failed || interrupted))) return "partial";
  if (failed) return "failed";
  if (interrupted) return "interrupted";
  if (completed) return "completed";
  return statuses[0] || "pending";
}

function sortRuns(runs: StressRun[], config: Record<string, unknown>): StressRun[] {
  const kind = formatStressLoad(runs[0] || {}, config).kind;
  const key = kind === "rate" ? "rate" : "parallel";
  return [...runs].sort((a, b) => (positiveNumber(a[key]) ?? 0) - (positiveNumber(b[key]) ?? 0));
}

function bestMetric(runs: StressRun[], key: string): number | null {
  const values = runs
    .map((run) => stressMetricValue(run[key]))
    .filter((value): value is number => value !== undefined);
  return values.length ? Math.max(...values) : null;
}

export function buildStressGroups(tasks: TaskLike[]): TaskLike[] {
  const buckets = new Map<string, TaskLike[]>();
  for (const task of tasks) {
    const key = stressGroupKey(task);
    const bucket = buckets.get(key) || [];
    bucket.push(task);
    buckets.set(key, bucket);
  }

  return Array.from(buckets, ([key, bucket]) => {
    const latest = [...bucket].sort((a, b) =>
      String(b.created_at || "").localeCompare(String(a.created_at || "")),
    )[0];
    const config = (latest.request_config || {}) as Record<string, unknown>;
    const runs = sortRuns(bucket.flatMap((task) => runsOfTask(task)), config);
    const durations = bucket.map((task) => stressMetricValue(task.duration_ms));
    const duration = durations.every((value) => value !== undefined)
      ? durations.reduce<number>((sum, value) => sum + (value ?? 0), 0)
      : null;
    const normalized = {
      task_id: `group:${key}`,
      model: latest.model_id,
      status: stressGroupStatus(bucket.map((task) => String(task.status || ""))),
      summary: {
        best_req_throughput: bestMetric(runs, "request_throughput"),
        best_output_throughput: bestMetric(runs, "output_throughput"),
        max_success_parallel: Math.max(
          0,
          ...runs
            .filter((run) => Number(run.success_rate) >= 1)
            .map((run) => positiveNumber(run.parallel) ?? 0),
        ),
        first_error_parallel: runs
          .filter((run) => Number(run.failed) > 0)
          .map((run) => positiveNumber(run.parallel) ?? 0)
          .sort((a, b) => a - b)[0] ?? null,
      },
      runs,
      errors: bucket.flatMap((task) => {
        const taskErrors = (task.normalized_result as Record<string, unknown> | undefined)?.errors;
        return Array.isArray(taskErrors) ? taskErrors : [];
      }),
    };

    return {
      ...latest,
      task_id: `group:${key}`,
      group_key: key,
      group_label: scenarioLabel(latest),
      group_config: [
        config.open_loop === true ? "开环速率" : config.open_loop === false ? "闭环并发" : null,
        `数据集 ${config.dataset || "默认"}`,
        (config.dataset_args as Record<string, unknown> | undefined)?.target_input_len
          ? `输入目标 ${(config.dataset_args as Record<string, unknown>).target_input_len}`
          : null,
        `max_tokens ${config.max_tokens ?? "默认"}`,
        config.stream === false ? "非流式" : "流式",
      ].filter(Boolean).join(" · "),
      group_count: bucket.length,
      grouped: true,
      status: normalized.status,
      progress: `${bucket.length} 条同配置记录 · ${runs.length} 个负载档位`,
      duration_ms: duration,
      normalized_result: normalized,
      raw_result: null,
      raw_output_dir: null,
      report_path: null,
    } as TaskLike;
  });
}
