export interface DurationMetric {
  value: string;
  unit: string;
}

/** 仅格式化展示；原始平均耗时仍由统计接口提供。 */
export function formatDurationMetric(milliseconds: number | null | undefined): DurationMetric {
  if (milliseconds == null || !Number.isFinite(milliseconds) || milliseconds < 0) {
    return { value: "—", unit: "" };
  }
  if (milliseconds < 1000) {
    return { value: Math.round(milliseconds).toString(), unit: "毫秒" };
  }
  const [divisor, unit] = milliseconds < 60000
    ? [1000, "秒"] as const
    : milliseconds < 3600000
      ? [60000, "分钟"] as const
      : [3600000, "小时"] as const;
  return { value: Number((milliseconds / divisor).toFixed(1)).toString(), unit };
}
