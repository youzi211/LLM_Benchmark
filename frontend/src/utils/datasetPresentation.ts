export type DatasetMetaLike = { pretty_name?: string } | undefined;

export interface DatasetSummary {
  /** 列表单元格展示：前两个名称，其余折叠为 +N；无数据为 — */
  short: string;
  /** 完整名称列表，用于悬停提示；无数据为空串 */
  full: string;
}

/** 任务数据集列摘要：优先 pretty_name，缺失时回退原始 ID。 */
export function datasetSummary(names: unknown, meta: Record<string, DatasetMetaLike> = {}): DatasetSummary {
  if (!Array.isArray(names)) return { short: "—", full: "" };
  const labels = names
    .map((name) => String(name ?? "").trim())
    .filter(Boolean)
    .map((name) => meta[name]?.pretty_name?.trim() || name);
  if (!labels.length) return { short: "—", full: "" };
  const full = labels.join("、");
  const short = labels.length > 2 ? `${labels.slice(0, 2).join("、")} +${labels.length - 2}` : full;
  return { short, full };
}
