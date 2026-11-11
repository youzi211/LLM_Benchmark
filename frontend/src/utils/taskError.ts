function message(value: unknown, depth = 0): string {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object" || depth > 4) return "";
  if (Array.isArray(value)) return value.map(item => message(item, depth + 1)).filter(Boolean).join("；");
  const record = value as Record<string, unknown>;
  return message(record.message ?? record.detail ?? record.error ?? record.reason, depth + 1);
}

export function taskErrorSummary(task: { status?: unknown; error?: unknown; errors?: unknown }): string {
  if (!["failed", "error", "interrupted", "partial"].includes(String(task.status))) return "";
  const raw = message(task.error) || message(task.errors) || "未提供原因，请查看任务详情";
  // 先脱敏再截断，避免把密钥前半段带到列表中。
  const safe = raw.replace(/\b(?:sk|ark)-[a-zA-Z0-9._-]+/g, "[已脱敏]")
    .replace(/Bearer\s+[^\s,;"'}]+/gi, "Bearer [已脱敏]")
    .replace(/((?:api[_-]?key|access[_-]?token|password|authorization)["']?\s*[=:]\s*["']?)[^\s,;&"'}]+/gi, "$1[已脱敏]")
    .replace(/\s+/g, " ").trim();
  const characters = Array.from(safe);
  return characters.length > 60 ? characters.slice(0, 59).join("") + "…" : safe;
}
