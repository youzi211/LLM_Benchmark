import { http } from "./http";

export type Lane = "basic" | "stress" | "intelligence";
export const lanes: Lane[] = ["basic", "intelligence", "stress"];
export const laneNames: Record<Lane, string> = { basic: "网关检查", intelligence: "能力评测", stress: "性能压测" };
export interface Evidence {
  task_id: string; model_id: string; lane: Lane; status: string; complete: boolean | null;
  cancel_requested_at?: string | null; created_at: string | null; completed_at: string | null;
  metrics: Record<string, any>[]; snapshot: { evalscope_version: string | null; conditions: Record<string, any> } | null;
  load_mode?: "open" | "closed" | "unknown" | null;
  timestamp_timezone_known?: boolean;
  report_url: string | null; task_url: string;
}
export interface LaneResults {
  latest_success: Evidence | null; latest_attempt: Evidence | null; partial_result: Evidence | null;
  selected?: Evidence | null; task_count: number;
}
export interface ModelEvaluation {
  model_id: string; name: string; upstream_model: string | null; protocol: string | null;
  archived: boolean; enabled: boolean; historical_only: boolean; coverage: number;
  last_execution_at?: string | null;
  lanes: Record<Lane, LaneResults>;
}
export interface Comparison {
  models: ModelEvaluation[];
  comparability: Record<Lane, { status: "equal" | "different" | "unknown"; reasons: string[] }>;
}
export const evaluations = {
  async list(params: Record<string, unknown> = {}) { return (await http.get<{ total: number; items: ModelEvaluation[] }>("/model-evaluations", { params })).data; },
  async detail(id: string) { return (await http.get<ModelEvaluation>(`/model-evaluations/${encodeURIComponent(id)}`)).data; },
  async history(id: string, params: Record<string, unknown> = {}) { return (await http.get<{ total: number; items: Evidence[] }>(`/model-evaluations/${encodeURIComponent(id)}/history`, { params })).data; },
  async compare(model_ids: string[], task_overrides: Record<string, Partial<Record<Lane, string>>> = {}) { return (await http.post<Comparison>("/model-comparisons", { model_ids, task_overrides })).data; },
  async archive(id: string, restore = false) { await http.post(`/models/${encodeURIComponent(id)}/${restore ? "restore" : "archive"}`); },
};
export function selectedEvidence(result: LaneResults): Evidence | null { return result.selected !== undefined ? result.selected : result.latest_success || result.partial_result; }
export function displayStatus(e?: Evidence | null): string {
  if (!e) return "未评测";
  if (e.cancel_requested_at && ["pending", "running", "queued"].includes(e.status)) return "取消中";
  return ({ completed: "已完成", partial: "部分完成", failed: "失败", error: "失败", interrupted: "已中断", running: "运行中", queued: "排队中", pending: "排队中" } as Record<string, string>)[e.status] || e.status;
}
export function exportEvidence(items: Evidence[], filename: string) {
  const blob = new Blob([JSON.stringify(items, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}
