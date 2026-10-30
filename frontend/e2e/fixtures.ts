import { expect, test as base, type Page } from "@playwright/test";

export const lanes = [
  { lane: "basic", title: "基础评测", list: "/api/tasks", submit: "/api/tasks/run-async", completed: "task_ui_completed", running: "task_ui_running" },
  { lane: "stress", title: "压测评测", list: "/api/stress/tasks", submit: "/api/stress/tasks/default", completed: "stress_ui_completed", running: "stress_ui_running" },
  { lane: "intelligence", title: "能力评测", list: "/api/intelligence/tasks", submit: "/api/intelligence/tasks/default", completed: "intel_ui_completed", running: "intel_ui_running" },
] as const;
export type Lane = typeof lanes[number]["lane"];

export interface UiApi {
  scenario: "normal" | "empty" | "failed";
  seedActive: boolean;
  submissions: Array<{ path: string; body: Record<string, unknown> }>;
  unexpected: string[];
  pageErrors: string[];
}

const models = [
  { id: "ui-model", name: "Qwen · 接入验证模型", model: "ui-model", protocol: "chat_completions", enabled: true },
  { id: "ui-reference", name: "DeepSeek · 对照模型", model: "ui-reference", protocol: "responses", enabled: true },
];
const metrics = [
  { id: "connectivity", name: "连通性", priority: "P0" },
  { id: "stream_spec", name: "流式规范性", priority: "P1" },
  { id: "cache_behavior", name: "缓存能力", priority: "P1" },
];
const datasets = {
  gsm8k: { name: "gsm8k", pretty_name: "GSM8K", description: "小学数学与多步计算推理", available_local: true, categories: ["Math"], local_path: "data/evalscope_datasets/gsm8k", subsets: ["main", "extended"], configured_subset_list: ["main"] },
  bbh: { name: "bbh", pretty_name: "BBH", description: "复杂指令理解与多任务推理", available_local: true, categories: ["Reasoning"], local_path: "data/evalscope_datasets/bbh", subsets: ["logical_deduction", "word_sorting"] },
  humaneval: { name: "humaneval", pretty_name: "HumanEval", description: "代码生成与可执行单元测试", available_local: true, categories: ["Coding"], local_path: "data/evalscope_datasets/humaneval" },
  unavailable: { name: "unavailable", pretty_name: "未下载的数据集", available_local: false, categories: ["Knowledge"] },
};
const stressConfig = { dataset: "longalpaca", open_loop: false, stream: true, parallel: [1, 5], number: [10, 50], max_tokens: 512 };
const runs = [
  { parallel: 1, rate: -1, total: 10, success: 10, failed: 0, success_rate: 1, request_throughput: 5.2, output_throughput: 800, total_throughput: 1200, avg_latency_seconds: 1.2, p95_latency_seconds: 1.8, p99_latency_seconds: 2.1, avg_ttft_ms: 120, avg_tpot_ms: 12, avg_itl_ms: 11, avg_input_tokens: 512, avg_output_tokens: 256, avg_turns: 1 },
  { parallel: 5, rate: -1, total: 50, success: 49, failed: 1, success_rate: .98, request_throughput: 25.6, output_throughput: 2300, total_throughput: 3500, avg_latency_seconds: 2.4, p95_latency_seconds: 3.8, p99_latency_seconds: 4.1, avg_ttft_ms: 180, avg_tpot_ms: 18, avg_itl_ms: -1, avg_input_tokens: 1024, avg_output_tokens: 512, avg_turns: 1 },
];

function initialTasks(): Record<Lane, Array<Record<string, any>>> {
  const common = { model_id: "ui-model", created_at: "2026-10-30T08:00:00Z", started_at: "2026-10-30T08:00:00Z", finished_at: "2026-10-30T08:02:00Z", completed_at: "2026-10-30T08:02:00Z", updated_at: "2026-10-30T08:02:00Z" };
  return {
    basic: [
      { ...common, task_id: "task_ui_completed", status: "completed", duration_ms: 125000, plan_id: "gateway_acceptance_v1", metric_ids: metrics.map((m) => m.id), report_path: "reports/ui/basic.md", results: metrics.map((m, index) => ({ metric_name: m.id, status: index === 2 ? "skipped" : "completed", summary: index === 2 ? "上游未返回缓存字段，保留观察结果，不进行自动判定。" : "请求与响应结构符合预期，已采集协议与用量信息。" })) },
      { ...common, task_id: "task_ui_failed", status: "error", duration_ms: 0, plan_id: "gateway_acceptance_v1", metric_ids: ["connectivity"], results: [], error: { code: "fixture_error", message: "测试接口连接失败" } },
      { ...common, task_id: "task_ui_running", status: "running", duration_ms: null, finished_at: null, results: [], metric_ids: ["connectivity"], plan_id: "gateway_acceptance_v1" },
    ],
    stress: [
      { ...common, task_id: "stress_ui_completed", status: "completed", duration_ms: 120000, request_config: stressConfig, normalized_result: { summary: { best_req_throughput: 25.6, best_output_throughput: 2300 }, runs, errors: [] }, report_path: "reports/ui/stress.md", raw_result: { fixture: true }, raw_output_dir: "outputs/ui/stress" },
      { ...common, task_id: "stress_ui_failed", status: "failed", duration_ms: 1200, request_config: stressConfig, normalized_result: null, error: { code: "fixture_error", message: "部分档位执行失败" } },
      { ...common, task_id: "stress_ui_running", status: "running", request_config: { ...stressConfig, dataset: "random" }, normalized_result: null, progress: "正在执行并发 5 档位", progress_detail: null, duration_ms: null },
    ],
    intelligence: [
      { ...common, task_id: "intel_ui_completed", status: "completed", datasets: ["gsm8k", "bbh"], report_path: "reports/ui/intelligence.md", raw_output_dir: "outputs/ui/intelligence", progress: "评测完成", progress_detail: { overall_percent: 100, processed_count: 100, total_count: 100, dataset_index: 2, dataset_total: 2 }, normalized_result: { dataset_results: [{ dataset: "gsm8k", pretty_name: "GSM8K", categories: ["Math"], score: .825 }, { dataset: "bbh", pretty_name: "BBH", categories: ["Reasoning"], score: null }], category_summaries: [{ category: "Math", dataset_count: 1, scored_dataset_count: 1, average_score: .825 }, { category: "Reasoning", dataset_count: 1, scored_dataset_count: 0, average_score: null }] } },
      { ...common, task_id: "intel_ui_failed", status: "failed", datasets: ["gsm8k"], normalized_result: null, error: { code: "fixture_error", message: "数据集执行失败" } },
      { ...common, task_id: "intel_ui_running", status: "running", datasets: ["gsm8k"], progress: "正在准备数据集", progress_detail: null, normalized_result: null },
    ],
  };
}

async function installApi(page: Page): Promise<UiApi> {
  const state: UiApi = { scenario: "normal", seedActive: true, submissions: [], unexpected: [], pageErrors: [] };
  const records = initialTasks();
  const allowedOrigin = new URL(process.env.LLM_BENCHMARK_UI_BASE_URL || "http://127.0.0.1:5186").origin;
  page.on("pageerror", (error) => state.pageErrors.push(error.message));
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) {
      if (url.protocol.startsWith("http") && url.origin !== allowedOrigin) {
        state.unexpected.push(`外部请求被阻止：${url.origin}`);
        return route.abort();
      }
      return route.continue();
    }
    const pathname = url.pathname;
    const method = request.method();
    const definition = lanes.find((item) => pathname === item.list || pathname.startsWith(`${item.list}/`));
    if (method === "GET") {
      if (definition && pathname === definition.list) {
        if (state.scenario === "failed") return route.fulfill({ status: 503, json: { error: { message: "隔离测试：任务接口暂不可用" } } });
        const rows = state.scenario === "empty" ? [] : records[definition.lane].filter((row) => state.seedActive || row.status !== "running");
        return route.fulfill({ json: rows.map((row) => Object.fromEntries(Object.entries(row).filter(([key]) => key !== "raw_result" && !(definition.lane === "basic" && ["results", "analysis"].includes(key)) && !(definition.lane === "intelligence" && key === "normalized_result")))) });
      }
      if (definition) {
        const suffix = pathname.slice(definition.list.length + 1).split("/");
        const task = records[definition.lane].find((row) => row.task_id === decodeURIComponent(suffix[0]));
        if (task && suffix[1] === "artifacts") return route.fulfill({ json: { artifacts: [{ name: "metrics.json", path: "results/metrics.json", size_bytes: 2048 }] } });
        if (task) return route.fulfill({ json: task });
      }
      const payloads: Record<string, unknown> = {
        "/api/models": models,
        "/api/metrics": metrics,
        "/api/health": { status: "ok", uptime_s: 7200, scheduler_disabled: false, models: { ok: true, count: models.length }, evalscope: { ok: true, state: "ready" }, scheduler: { ok: true, state: "running" } },
        "/api/intelligence/datasets": { default_datasets: ["gsm8k", "bbh"], datasets },
        "/api/stress/datasets": { default_dataset: "longalpaca", datasets: { longalpaca: { name: "longalpaca", pretty_name: "LongAlpaca", description: "长上下文语料，用于吞吐与延迟测试", categories: ["Long Context"], is_default: true, available_local: true }, random: { name: "random", pretty_name: "Random", description: "随机生成 Token，不依赖外部数据集", categories: ["Synthetic"] } } },
      };
      if (pathname in payloads) return route.fulfill({ json: payloads[pathname] });
    }
    if (method === "POST") {
      const body = request.postDataJSON() || {};
      const submission = lanes.find((item) => item.submit === pathname || (item.lane === "intelligence" && pathname === item.list));
      if (submission) {
        state.submissions.push({ path: pathname, body });
        const task = { ...structuredClone(records[submission.lane][0]), ...body, task_id: `${submission.lane}_ui_created_${state.submissions.length}`, status: "pending", results: [], normalized_result: null, raw_result: null, report_path: null, progress_detail: null, raw_output_dir: null };
        records[submission.lane].unshift(task);
        return route.fulfill({ status: 202, json: { ...task, job_id: "job_ui_fixture" } });
      }
      if (definition && pathname.endsWith("/cancel")) {
        const taskId = pathname.slice(definition.list.length + 1).split("/")[0];
        const task = records[definition.lane].find((row) => row.task_id === taskId);
        if (task) {
          task.status = "interrupted";
          state.submissions.push({ path: pathname, body });
          return route.fulfill({ json: task });
        }
      }
    }
    state.unexpected.push(`${method} ${pathname}`);
    return route.fulfill({ status: 404, json: { error: { message: "未匹配的测试接口；已阻止访问真实后端" } } });
  });
  return state;
}

export const test = base.extend<{ api: UiApi }>({
  api: [async ({ page }, use) => {
    const state = await installApi(page);
    await use(state);
    expect(state.unexpected, "测试不允许穿透到真实后端或外部服务").toEqual([]);
    expect(state.pageErrors, "浏览器不应产生未处理异常").toEqual([]);
  }, { auto: true }],
});
export { expect };
