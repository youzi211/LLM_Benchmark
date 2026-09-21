import { http } from "./http";

export type Status = "pending" | "running" | "completed" | "failed" | "interrupted" | "partial" | "error" | string;

export interface TaskLike {
  task_id: string;
  model_id?: string;
  status?: Status;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  started_at?: string;
  finished_at?: string;
  report_path?: string | null;
  error?: unknown;
  [key: string]: unknown;
}

export interface DatasetMeta {
  name?: string;
  pretty_name?: string;
  description?: string;
  categories?: string[];
  needs_judge?: boolean;
  available_local?: boolean;
  local_path?: string;
  subsets?: string[];
  subset_count?: number;
  configured_subset_list?: string[];
  [key: string]: unknown;
}

export async function runBasic(payload: Record<string, unknown>) {
  const { data } = await http.post("/tasks/run", payload);
  return data;
}

export async function listBasicTasks(limit = 50): Promise<TaskLike[]> {
  const { data } = await http.get(`/tasks?limit=${limit}`);
  return Array.isArray(data) ? data : [];
}

export async function getBasicTask(taskId: string): Promise<TaskLike> {
  const { data } = await http.get(`/tasks/${encodeURIComponent(taskId)}`);
  return data;
}

export async function runStress(payload: Record<string, unknown>) {
  const { data } = await http.post("/stress/tasks/default", payload);
  return data;
}

export async function listStressTasks(limit = 50): Promise<TaskLike[]> {
  const { data } = await http.get(`/stress/tasks?limit=${limit}`);
  return Array.isArray(data) ? data : [];
}

export async function getStressTask(taskId: string, result = false): Promise<TaskLike> {
  const { data } = await http.get(`/stress/tasks/${encodeURIComponent(taskId)}${result ? "/result" : ""}`);
  return data;
}

export async function cancelStressTask(taskId: string) {
  const { data } = await http.post(`/stress/tasks/${encodeURIComponent(taskId)}/cancel`);
  return data;
}

export interface StressArtifact {
  name: string;
  path: string;
  size_bytes: number;
  modified_at?: string;
  content_type?: string;
}

export async function listStressArtifacts(taskId: string): Promise<StressArtifact[]> {
  const { data } = await http.get(`/stress/tasks/${encodeURIComponent(taskId)}/artifacts`);
  return Array.isArray(data?.artifacts) ? data.artifacts : [];
}

export function stressRawResultUrl(taskId: string) {
  return `/api/stress/tasks/${encodeURIComponent(taskId)}/raw-result`;
}

export function stressArtifactUrl(taskId: string, artifactPath: string) {
  const encodedPath = artifactPath.split("/").map(encodeURIComponent).join("/");
  return `/api/stress/tasks/${encodeURIComponent(taskId)}/artifacts/${encodedPath}`;
}


export interface StressDatasetMeta {
  name: string;
  pretty_name?: string;
  description?: string;
  categories?: string[];
  is_default?: boolean;
  is_local_resolvable?: boolean;
  available_local?: boolean;
  local_path?: string;
  [key: string]: unknown;
}

export async function fetchStressDatasets(): Promise<{ default_dataset: string; datasets: Record<string, StressDatasetMeta> }> {
  const { data } = await http.get("/stress/datasets");
  return {
    default_dataset: data?.default_dataset ?? "",
    datasets: data?.datasets && typeof data.datasets === "object" ? data.datasets : {},
  };
}
export async function runIntelligence(payload: Record<string, unknown>) {
  const { data } = await http.post("/intelligence/tasks", payload);
  return data;
}

export async function runDefaultIntelligence(payload: { model_id: string }) {
  const { data } = await http.post("/intelligence/tasks/default", payload);
  return data;
}

export async function listIntelligenceTasks(limit = 50): Promise<TaskLike[]> {
  const { data } = await http.get(`/intelligence/tasks?limit=${limit}`);
  return Array.isArray(data) ? data : [];
}

export async function getIntelligenceTask(taskId: string, result = false): Promise<TaskLike> {
  const { data } = await http.get(`/intelligence/tasks/${encodeURIComponent(taskId)}${result ? "/result" : ""}`);
  return data;
}

export async function cancelIntelligenceTask(taskId: string) {
  const { data } = await http.post(`/intelligence/tasks/${encodeURIComponent(taskId)}/cancel`);
  return data;
}

export async function fetchDatasets(): Promise<{ default_datasets: string[]; datasets: Record<string, DatasetMeta> }> {
  const { data } = await http.get("/intelligence/datasets");
  return {
    default_datasets: Array.isArray(data?.default_datasets) ? data.default_datasets : [],
    datasets: data?.datasets && typeof data.datasets === "object" ? data.datasets : {},
  };
}

export async function listSuites(limit = 20) {
  const { data } = await http.get(`/suites?limit=${limit}`);
  return Array.isArray(data) ? data : [];
}

export async function runSuite(payload: Record<string, unknown>, quick = false) {
  const { data } = await http.post(quick ? "/suites/quick" : "/suites/default", payload);
  return data;
}

export async function cancelSuite(suiteId: string) {
  const { data } = await http.post(`/suites/${encodeURIComponent(suiteId)}/cancel`);
  return data;
}

export async function listSchedules(limit = 20) {
  const { data } = await http.get(`/suites/schedules?limit=${limit}`);
  return Array.isArray(data) ? data : [];
}

export async function createSchedule(payload: Record<string, unknown>) {
  const { data } = await http.post("/suites/schedules", payload);
  return data;
}

export async function triggerSchedule(scheduleId: string) {
  const { data } = await http.post(`/suites/schedules/${encodeURIComponent(scheduleId)}/trigger`);
  return data;
}

export async function deleteSchedule(scheduleId: string) {
  const { data } = await http.delete(`/suites/schedules/${encodeURIComponent(scheduleId)}`);
  return data;
}

export function finalStatus(status?: string) {
  return ["completed", "partial", "failed", "interrupted", "error"].includes(String(status || ""));
}

export function formatDate(value?: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

/** 相对时间, 如 "3 分钟后" / "2 小时前". 用于定时任务下次运行提示. */
export function relativeFromNow(value?: unknown): string {
  if (!value) return "";
  const ts = new Date(String(value)).getTime();
  if (Number.isNaN(ts)) return "";
  const diffSec = Math.round((ts - Date.now()) / 1000);
  const abs = Math.abs(diffSec);
  const future = diffSec >= 0;
  if (abs < 60) return future ? "即将触发" : "刚刚";
  let unit: string;
  if (abs < 3600) unit = `${Math.floor(abs / 60)} 分钟`;
  else if (abs < 86400) unit = `${Math.floor(abs / 3600)} 小时`;
  else unit = `${Math.floor(abs / 86400)} 天`;
  return future ? `${unit}后` : `${unit}前`;
}

export function parseIntegerList(raw: string): number[] | undefined {
  const text = String(raw || "").trim();
  if (!text) return undefined;
  const list = text.split(/[，,\s]+/).filter(Boolean).map(Number);
  if (list.some((item) => !Number.isInteger(item) || item < 1)) throw new Error(`列表参数只能包含正整数：${text}`);
  return list;
}

export function toNumber(raw: unknown): number | undefined {
  if (raw === null || raw === undefined || String(raw).trim() === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}



export async function getSuite(suiteId: string) {
  const { data } = await http.get(`/suites/${encodeURIComponent(suiteId)}`);
  return data;
}

export async function getSchedule(scheduleId: string) {
  const { data } = await http.get(`/suites/schedules/${encodeURIComponent(scheduleId)}`);
  return data;
}

export async function getScheduleLastRun(scheduleId: string) {
  const { data } = await http.get(`/suites/schedules/${encodeURIComponent(scheduleId)}/last-run`);
  return data;
}

export interface SuiteProfile {
  profile_id: string;
  name: string;
  description?: string;
  requires_sandbox?: boolean;
  run_gateway?: boolean;
  run_intelligence?: boolean;
  run_stress?: boolean;
  intelligence_datasets?: string[];
  intelligence_limit?: number;
  intelligence_eval_batch_size?: number;
  stress_options?: Record<string, unknown>;
}

export async function fetchSuiteProfiles(): Promise<SuiteProfile[]> {
  const { data } = await http.get("/suites/profiles");
  return Array.isArray(data) ? data : [];
}

export interface EvalScopeConfig {
  datasets_dir?: string | null;
  outputs_dir?: string | null;
  judge_model_config_id?: string | null;
  judge_generation_config?: Record<string, unknown>;
  judge_worker_num?: number;
  ignore_dataset_errors?: boolean;
  dataset_args?: Record<string, Record<string, unknown>>;
  sandbox_enabled?: boolean;
  sandbox_type?: string;
  sandbox_manager_config?: Record<string, unknown>;
}

export interface EvalScopeHealthStatus {
  status: string;
  configured?: boolean;
  mode?: string;
  engine?: string;
  base_url?: string;
  checked_url?: string;
  http_status?: number;
  latency_ms?: number;
  model_config_id?: string;
  model_id?: string;
  source?: string;
  message?: string;
  error?: unknown;
  [key: string]: unknown;
}

export async function fetchEvalScopeConfig(): Promise<EvalScopeConfig> {
  const { data } = await http.get("/intelligence/evalscope/config");
  return data && typeof data === "object" ? data : {};
}

export async function saveEvalScopeConfig(payload: EvalScopeConfig): Promise<EvalScopeConfig> {
  const { data } = await http.put("/intelligence/evalscope/config", payload);
  return data && typeof data === "object" ? data : {};
}

export async function fetchSandboxHealth(deep = false): Promise<EvalScopeHealthStatus> {
  const { data } = await http.get(`/intelligence/evalscope/sandbox-health${deep ? "?deep=true" : ""}`);
  return data as EvalScopeHealthStatus;
}

export async function fetchJudgeHealth(): Promise<EvalScopeHealthStatus> {
  const { data } = await http.get("/intelligence/evalscope/judge-health");
  return data as EvalScopeHealthStatus;
}


/* 健康端点 */
export interface HealthStatus {
  status: "ok" | string;
  uptime_s: number;
  scheduler_disabled: boolean;
  models: { ok: boolean; count: number };
  evalscope: { ok: boolean; state: string; datasets_dir?: string };
  scheduler: { ok: boolean; state: string };
}

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await http.get("/health");
  return data;
}
