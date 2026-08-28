import { http } from "./http";

export interface ModelConfig {
  id: string;
  name?: string;
  base_url?: string;
  model?: string;
  protocol?: string;
  [key: string]: unknown;
}

export async function fetchModels(): Promise<ModelConfig[]> {
  const { data } = await http.get("/models");
  // 老接口返回结构是 { models: [...] } 或裸数组,这里做兼容。
  if (Array.isArray(data)) return data as ModelConfig[];
  if (Array.isArray(data?.models)) return data.models as ModelConfig[];
  return [];
}
