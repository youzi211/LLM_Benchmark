import axios, { AxiosError, type AxiosInstance } from "axios";

// 后端 /api 前缀由 Vite dev server 代理到 http://127.0.0.1:8020；
// 产物部署后由同源 FastAPI（/ui-vue/）直接服务静态资源。
export const http: AxiosInstance = axios.create({
  baseURL: "/api",
  timeout: 30_000,
});

export class ApiError extends Error {
  code?: string;
  details?: unknown;
  status?: number;

  constructor(message: string, options: { code?: string; details?: unknown; status?: number } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.details = options.details;
    this.status = options.status;
  }
}

function normalizeAxiosError(error: unknown) {
  if (!axios.isAxiosError(error)) return error;
  const axiosError = error as AxiosError<any>;
  const status = axiosError.response?.status;
  const data = axiosError.response?.data;
  const envelope = data?.error;
  if (envelope && typeof envelope === "object") {
    return new ApiError(String(envelope.message || axiosError.message), {
      code: typeof envelope.code === "string" ? envelope.code : undefined,
      details: envelope.details,
      status,
    });
  }
  if (status === 422 && data?.detail) {
    return new ApiError("请求参数校验失败", { code: "validation_error", details: data.detail, status });
  }
  return new ApiError(axiosError.message, { status, details: data });
}

http.interceptors.response.use(
  (resp) => resp,
  (error) => Promise.reject(normalizeAxiosError(error)),
);
