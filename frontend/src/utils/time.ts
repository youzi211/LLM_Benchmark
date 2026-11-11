/** 无时区的历史时间只展示原值，不推断它属于哪个时区。 */
export function timestamp(value: unknown): number | undefined {
  if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)) return undefined;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? milliseconds : undefined;
}

export function formatDate(value?: unknown): string {
  if (!value) return "—";
  const milliseconds = timestamp(value);
  if (milliseconds === undefined) return `${String(value).replace("T", " ")}（时区未知）`;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(milliseconds) + " UTC+08:00";
}
