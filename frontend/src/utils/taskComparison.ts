import type { TaskLike } from "@/api/evaluations";

export type TaskComparisonType = "basic" | "stress" | "intelligence";

export interface ComparisonMetric {
  key: string;
  label: string;
  status: string;
  summary: string;
}

function asRecord(value: unknown): Record<string, any> | null {
  return value && typeof value === "object" ? value as Record<string, any> : null;
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function normalizedResult(task: TaskLike): Record<string, any> | null {
  return asRecord(task.normalized_result)
    || asRecord(asRecord(task.raw_result)?.normalized_result);
}

function basicMetrics(task: TaskLike): ComparisonMetric[] {
  const results = Array.isArray(task.results) ? task.results : [];
  return results.map((raw, index) => {
    const metric = asRecord(raw) || {};
    const label = String(metric.metric_name || metric.metric_id || `Metric ${index + 1}`);
    return {
      key: `basic:${String(metric.metric_id || label)}`,
      label,
      status: String(metric.status || task.status || "-"),
      summary: String(metric.summary || "-"),
    };
  });
}

function stressMetrics(task: TaskLike): ComparisonMetric[] {
  const normalized = normalizedResult(task);
  if (!normalized) return [];
  const summary = asRecord(normalized.summary) || {};
  const runs = Array.isArray(normalized.runs)
    ? normalized.runs.map(asRecord).filter((run): run is Record<string, any> => Boolean(run))
    : [];
  const status = String(normalized.status || task.status || "-");

  const bestRequestThroughput = finiteNumber(summary.best_req_throughput)
    ?? Math.max(-1, ...runs.map((run) => finiteNumber(run.request_throughput) ?? -1));
  const bestOutputThroughput = finiteNumber(summary.best_output_throughput)
    ?? Math.max(-1, ...runs.map((run) => finiteNumber(run.output_throughput) ?? -1));
  const totalRequests = runs.reduce((total, run) => total + (finiteNumber(run.total) ?? 0), 0);
  const successfulRequests = runs.reduce((total, run) => total + (finiteNumber(run.success) ?? 0), 0);
  const successRate = totalRequests > 0 ? successfulRequests / totalRequests * 100 : null;
  const worstP95 = Math.max(-1, ...runs.map((run) => finiteNumber(run.p95_latency_seconds) ?? -1));

  return [
    {
      key: "stress:req_throughput",
      label: "最高请求吞吐",
      status,
      summary: bestRequestThroughput >= 0 ? `${formatNumber(bestRequestThroughput)} req/s` : "-",
    },
    {
      key: "stress:output_throughput",
      label: "最高输出吞吐",
      status,
      summary: bestOutputThroughput >= 0 ? `${formatNumber(bestOutputThroughput)} tok/s` : "-",
    },
    {
      key: "stress:success_rate",
      label: "请求成功率",
      status,
      summary: successRate === null
        ? "-"
        : `${successRate.toFixed(1)}% (${successfulRequests}/${totalRequests})`,
    },
    {
      key: "stress:p95_latency",
      label: "最差 P95 延迟",
      status,
      summary: worstP95 >= 0 ? `${formatNumber(worstP95)} s` : "-",
    },
    {
      key: "stress:runs",
      label: "测试档位数",
      status,
      summary: String(runs.length),
    },
  ];
}

function intelligenceMetrics(task: TaskLike): ComparisonMetric[] {
  const normalized = normalizedResult(task);
  if (!normalized) return [];
  const datasetResults = Array.isArray(normalized.dataset_results)
    ? normalized.dataset_results.map(asRecord).filter((item): item is Record<string, any> => Boolean(item))
    : [];
  if (!datasetResults.length) return [];

  const scores = datasetResults
    .map((item) => finiteNumber(item.score))
    .filter((score): score is number => score !== null);
  const average = scores.length
    ? scores.reduce((total, score) => total + score, 0) / scores.length
    : null;
  const status = String(normalized.status || task.status || "-");
  return [
    {
      key: "intelligence:average_score",
      label: "数据集平均分",
      status,
      summary: average === null ? "-" : average.toFixed(1),
    },
    ...datasetResults.map((item) => {
      const dataset = String(item.dataset || item.pretty_name || "dataset");
      const score = finiteNumber(item.score);
      return {
        key: `intelligence:${dataset}`,
        label: String(item.pretty_name || dataset),
        status,
        summary: score === null ? "-" : score.toFixed(1),
      };
    }),
  ];
}

export function comparisonMetrics(type: TaskComparisonType, task: TaskLike | null): ComparisonMetric[] {
  if (!task) return [];
  if (type === "stress") return stressMetrics(task);
  if (type === "intelligence") return intelligenceMetrics(task);
  return basicMetrics(task);
}

export function comparisonCsv(columns: { id: string; type: TaskComparisonType; task: TaskLike | null }[]): string {
  const entries = columns.map((column) => comparisonMetrics(column.type, column.task));
  const metrics = new Map<string, string>();
  entries.flat().forEach((metric) => metrics.set(metric.key, metric.label));
  const rows = [
    ["指标", ...columns.map((column) => column.id)],
    ...Array.from(metrics, ([key, label]) => [label, ...entries.map((items) => items.find((item) => item.key === key)?.summary ?? "—")]),
  ];
  return rows.map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\n");
}
