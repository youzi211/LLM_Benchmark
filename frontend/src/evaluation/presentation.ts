function nonNegativeNumber(value: unknown): number | undefined {
  if (typeof value !== "number" && typeof value !== "string") return undefined;
  if (typeof value === "string" && !value.trim()) return undefined;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : undefined;
}

/** 仅格式化任务字段，不重算或推断评测结果。 */
export function formatEvaluationDuration(value: unknown): string {
  const milliseconds = nonNegativeNumber(value);
  if (milliseconds === undefined) return "—";
  const [divisor, unit] = milliseconds >= 3600000 ? [3600000, "小时"] as const
    : milliseconds >= 60000 ? [60000, "分钟"] as const
      : milliseconds >= 1000 ? [1000, "秒"] as const : [1, "毫秒"] as const;
  const number = divisor === 1 ? Math.round(milliseconds) : Number((milliseconds / divisor).toFixed(1));
  return `${number} ${unit}`;
}

export function progressPercentOf(detail: unknown): number | undefined {
  if (!detail || typeof detail !== "object") return undefined;
  const record = detail as Record<string, unknown>;
  const value = nonNegativeNumber(record.overall_percent ?? record.percent);
  return value === undefined ? undefined : Math.min(value, 100);
}

export function progressSampleCounts(detail: unknown): { processed: number | undefined; total: number | undefined } {
  const record = detail && typeof detail === "object" ? detail as Record<string, unknown> : {};
  const current = typeof record.current_dataset === "string" && Array.isArray(record.datasets)
    ? record.datasets.find((row) => row?.dataset === record.current_dataset) : undefined;
  const count = (value: unknown) => {
    const number = nonNegativeNumber(value);
    return number !== undefined && Number.isInteger(number) ? number : undefined;
  };
  return {
    processed: count(record.processed_count) ?? count(current?.processed_count),
    total: count(record.total_count) ?? count(current?.total_count),
  };
}

/** 沿用原页面的 0–1 / 百分制兼容规则，但不把 null、空串转换为零分。 */
export function scorePercent(value: unknown): number | null {
  const number = nonNegativeNumber(value);
  if (number === undefined) return null;
  return Math.round(number <= 1 ? number * 1000 : number * 10) / 10;
}

export function metricResultCounts(results: unknown) {
  const rows: Array<{ status?: string }> = Array.isArray(results) ? results : [];
  return {
    completed: rows.filter((row) => row.status === "completed").length,
    errors: rows.filter((row) => row.status === "error" || row.status === "failed").length,
    skipped: rows.filter((row) => row.status === "skipped").length,
    total: rows.length,
  };
}

export function effectiveDatasetNames(
  localNames: readonly string[],
  defaultNames: readonly string[],
  custom: boolean,
  chosenNames: readonly string[],
): string[] {
  const local = new Set(localNames);
  const selected = custom ? chosenNames.filter((name) => local.has(name))
    : localNames.filter((name) => defaultNames.includes(name));
  return [...new Set(selected)];
}

export function modelDisplayName(id: string | undefined, models: ReadonlyArray<{ id: string; name?: string }>): string {
  return models.find((model) => model.id === id)?.name || id || "—";
}
