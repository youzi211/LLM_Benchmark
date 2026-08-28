import { http } from "./http";

export type ModelProtocol = "chat_completions" | "responses";

export interface ModelConfig {
  id: string;
  name?: string;
  base_url?: string;
  api_key?: string;
  model?: string;
  protocol?: ModelProtocol | string;
  timeout_seconds?: number;
  enabled?: boolean;
  declared_context_tokens?: number | null;
  declared_max_output_tokens?: number | null;
  concurrency_levels?: number[];
  [key: string]: unknown;
}

export interface ModelConfigCreate {
  id: string;
  name: string;
  protocol: ModelProtocol;
  base_url: string;
  api_key: string;
  model: string;
  timeout_seconds?: number;
  enabled?: boolean;
  declared_context_tokens?: number | null;
  declared_max_output_tokens?: number | null;
  concurrency_levels?: number[];
}

export type ModelConfigUpdate = Partial<Omit<ModelConfigCreate, "id">>;

export async function fetchModels(): Promise<ModelConfig[]> {
  const { data } = await http.get("/models");
  // 老接口返回结构是 { models: [...] } 或裸数组,这里做兼容。
  if (Array.isArray(data)) return data as ModelConfig[];
  if (Array.isArray(data?.models)) return data.models as ModelConfig[];
  return [];
}

export async function createModel(payload: ModelConfigCreate): Promise<ModelConfig> {
  const { data } = await http.post("/models", payload);
  return data as ModelConfig;
}

export async function updateModel(id: string, patch: ModelConfigUpdate): Promise<ModelConfig> {
  const { data } = await http.put(`/models/${encodeURIComponent(id)}`, patch);
  return data as ModelConfig;
}

export async function deleteModel(id: string): Promise<{ deleted: boolean }> {
  const { data } = await http.delete(`/models/${encodeURIComponent(id)}`);
  return data as { deleted: boolean };
}
