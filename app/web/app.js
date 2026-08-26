const API_ROOT = "/api";
const FINAL_STATUSES = new Set(["completed", "partial", "failed", "interrupted"]);

let pollTimer = null;
let activeSuiteId = "";
let activeSuite = null;
let insightsRequestSeq = 0;

const $ = (id) => document.getElementById(id);

const elements = {
  quickForm: $("quick-form"),
  notice: $("notice"),
  suiteCard: $("suite-card"),
  suiteId: $("suite-id"),
  reportLink: $("report-link"),
  suiteList: $("suite-list"),
  modelSelect: $("model-select"),
  loadModels: $("load-models"),
  startDefault: $("start-default"),
  refreshSuites: $("refresh-suites"),
  trackSuite: $("track-suite"),
  stopPoll: $("stop-poll"),
  clearKey: $("clear-key"),
  refreshInsights: $("refresh-insights"),
  insightsEmpty: $("insights-empty"),
  insightsGrid: $("insights-grid"),
  scheduleModelSelect: $("schedule-model-select"),
  scheduleList: $("schedule-list"),
  scheduleMode: $("schedule-mode"),
  scheduleDate: $("schedule-date"),
  scheduleDateField: $("schedule-date-field"),
  scheduleIntervalField: $("schedule-interval-field"),
  scheduleModeHelp: $("schedule-mode-help"),
  scheduleProfile: $("schedule-profile"),
  refreshSchedules: $("refresh-schedules"),
  createQuickSchedule: $("create-quick-schedule"),
  createModelSchedule: $("create-model-schedule"),
};

function setNotice(message, type = "info") {
  elements.notice.textContent = message;
  elements.notice.classList.toggle("error", type === "error");
}

function toNumberOrNull(value) {
  if (value === undefined || value === null || String(value).trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseIntegerList(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const list = raw
    .split(/[，,\s]+/)
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item > 0);
  return list.length ? Array.from(new Set(list)) : null;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function localDateString(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultOneShotDate() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return localDateString(date);
}

function updateScheduleMode() {
  const isOnce = elements.scheduleMode.value === "once";
  elements.scheduleDateField.classList.toggle("hidden-field", !isOnce);
  elements.scheduleIntervalField.classList.toggle("hidden-field", isOnce);
  $("schedule-interval").disabled = isOnce;
  elements.scheduleDate.disabled = !isOnce;
  elements.scheduleModeHelp.textContent = isOnce
    ? "只执行一次：到达指定日期和时间后自动触发一次，执行后计划会自动停用。"
    : "周期执行：从下一次 time_of_day 开始，之后每 interval_days 天重复触发。";
}


function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = body?.error?.message || body?.detail || body || `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return body;
}

function getSuiteOptions() {
  const connectivityOnly = $("connectivity-only").checked;
  const payload = {
    run_gateway: connectivityOnly ? true : $("run-gateway").checked,
    run_intelligence: connectivityOnly ? false : $("run-intelligence").checked,
    run_stress: connectivityOnly ? false : $("run-stress").checked,
    wait_for_completion: false,
  };

  if (connectivityOnly) {
    payload.gateway_metric_ids = ["connectivity"];
  }

  const parallel = parseIntegerList($("stress-parallel").value);
  const number = parseIntegerList($("stress-number").value);
  if (parallel || number) {
    payload.stress_options = {};
    if (parallel) payload.stress_options.parallel = parallel;
    if (number) payload.stress_options.number = number;
  }

  const pollInterval = toNumberOrNull($("poll-interval").value);
  const totalTimeout = toNumberOrNull($("total-timeout").value);
  if (pollInterval !== null) payload.poll_interval_seconds = pollInterval;
  if (totalTimeout !== null) payload.timeout_seconds_total = totalTimeout;

  if (!payload.run_gateway && !payload.run_intelligence && !payload.run_stress) {
    throw new Error("至少选择一个评测通道。");
  }
  return payload;
}

function buildQuickPayload() {
  const payload = {
    url: $("url").value.trim(),
    key: $("key").value,
    model: $("model").value.trim(),
    protocol: $("protocol").value,
    ...getSuiteOptions(),
  };

  const title = $("title").value.trim();
  const contextWindow = toNumberOrNull($("context-window").value);
  const maxOutput = toNumberOrNull($("max-output").value);
  const requestTimeout = toNumberOrNull($("request-timeout").value);

  if (title) payload.title = title;
  if (contextWindow !== null) payload.context_window_tokens = contextWindow;
  if (maxOutput !== null) payload.max_output_tokens = maxOutput;
  if (requestTimeout !== null) payload.timeout_seconds = requestTimeout;

  return payload;
}

async function startQuickSuite(event) {
  event.preventDefault();
  const button = $("start-quick");
  try {
    const payload = buildQuickPayload();
    button.disabled = true;
    setNotice("正在提交 quick suite，服务端会在后台执行评测……");
    const suite = await apiFetch("/suites/quick", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("key").value = "";
    setNotice(`已启动 ${suite.suite_id}。Key 输入框已清空，开始轮询进度。`);
    selectSuite(suite.suite_id, suite);
    await loadSuites();
  } catch (error) {
    setNotice(`启动失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function startDefaultSuite() {
  const modelId = elements.modelSelect.value;
  if (!modelId) {
    setNotice("请先读取并选择一个已有模型。", "error");
    return;
  }
  try {
    const payload = {
      model_id: modelId,
      title: `${modelId} 一键评测`,
      ...getSuiteOptions(),
    };
    delete payload.timeout_seconds_total;
    const totalTimeout = toNumberOrNull($("total-timeout").value);
    if (totalTimeout !== null) payload.timeout_seconds = totalTimeout;
    setNotice(`正在用已有模型 ${modelId} 启动 suite……`);
    const suite = await apiFetch("/suites/default", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setNotice(`已启动 ${suite.suite_id}，开始轮询进度。`);
    selectSuite(suite.suite_id, suite);
    await loadSuites();
  } catch (error) {
    setNotice(`启动失败：${error.message}`, "error");
  }
}

function sanitizeModelId(value) {
  const cleaned = String(value || "")
    .trim()
    .replace(/[^a-zA-Z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96);
  return cleaned || `scheduled-${Date.now()}`;
}

function scheduleNameFallback(modelId) {
  return `${modelId} 每日定时评测`;
}

function buildPersistedModelPayload() {
  const modelId = sanitizeModelId($("schedule-model-id").value || $("model").value || "scheduled-model");
  $("schedule-model-id").value = modelId;
  const payload = {
    id: modelId,
    name: $("schedule-model-name").value.trim() || `${$("model").value.trim() || modelId} 定时评测模型`,
    protocol: $("protocol").value,
    base_url: $("url").value.trim(),
    api_key: $("key").value,
    model: $("model").value.trim(),
    timeout_seconds: toNumberOrNull($("request-timeout").value) || 60,
    enabled: true,
  };
  const contextWindow = toNumberOrNull($("context-window").value);
  const maxOutput = toNumberOrNull($("max-output").value);
  const concurrency = parseIntegerList($("stress-parallel").value);
  if (contextWindow !== null) payload.declared_context_tokens = contextWindow;
  if (maxOutput !== null) payload.declared_max_output_tokens = maxOutput;
  if (concurrency) payload.concurrency_levels = concurrency;
  if (!payload.base_url || !payload.model) {
    throw new Error("请先填写左侧服务地址 URL 和模型名 model。");
  }
  return payload;
}

async function saveModelConfig(payload) {
  try {
    return await apiFetch("/models", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if (!/already exists|already_exists|已存在/i.test(error.message)) throw error;
    const updatePayload = { ...payload };
    delete updatePayload.id;
    return apiFetch(`/models/${encodeURIComponent(payload.id)}`, {
      method: "PUT",
      body: JSON.stringify(updatePayload),
    });
  }
}

function buildSchedulePayload(modelId, fallbackTitle = "一键定时评测") {
  if (!modelId) throw new Error("请选择或填写 model_id。");
  const suiteOptions = getSuiteOptions();
  const timeOfDay = $("schedule-time").value || "00:00";
  const mode = elements.scheduleMode.value || "once";
  const interval = mode === "once" ? 1 : toNumberOrNull($("schedule-interval").value) || 1;
  const payload = {
    name: $("schedule-name").value.trim() || scheduleNameFallback(modelId),
    model_id: modelId,
    profile: elements.scheduleProfile?.value || "scheduled_light",
    enabled: true,
    title: $("schedule-run-title").value.trim() || fallbackTitle,
    time_of_day: timeOfDay,
    timezone: $("schedule-timezone").value.trim() || "Asia/Shanghai",
    interval_days: interval,
    run_once: mode === "once",
    run_gateway: suiteOptions.run_gateway,
    run_intelligence: suiteOptions.run_intelligence,
    run_stress: suiteOptions.run_stress,
    gateway_plan_id: "gateway_acceptance_v1",
  };
  if (mode === "once") {
    const runDate = elements.scheduleDate.value;
    if (!runDate) throw new Error("请选择一次性任务的执行日期。");
    payload.run_date = runDate;
  }
  if (suiteOptions.gateway_metric_ids) payload.gateway_metric_ids = suiteOptions.gateway_metric_ids;
  if (suiteOptions.stress_options) payload.stress_options = suiteOptions.stress_options;
  if (suiteOptions.poll_interval_seconds !== undefined) payload.poll_interval_seconds = suiteOptions.poll_interval_seconds;
  if (suiteOptions.timeout_seconds_total !== undefined) payload.timeout_seconds = suiteOptions.timeout_seconds_total;
  return payload;
}

async function createSchedule(payload) {
  return apiFetch("/suites/schedules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function createScheduleFromQuick() {
  const button = elements.createQuickSchedule;
  try {
    button.disabled = true;
    const modelPayload = buildPersistedModelPayload();
    setNotice("正在保存模型配置并创建定时计划……");
    const model = await saveModelConfig(modelPayload);
    const schedulePayload = buildSchedulePayload(model.id, `${modelPayload.model} 定时综合评测`);
    const schedule = await createSchedule(schedulePayload);
    $("key").value = "";
    setNotice(`已创建定时计划 ${schedule.schedule_id}，下一次触发：${formatDate(schedule.next_run_at)}。Key 输入框已清空。`);
    await Promise.all([loadModels(), loadSchedules()]);
  } catch (error) {
    setNotice(`创建定时计划失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function createScheduleFromSaved() {
  const modelId = elements.scheduleModelSelect.value || elements.modelSelect.value;
  if (!modelId) {
    setNotice("请先读取并选择一个已有模型。", "error");
    return;
  }
  const button = elements.createModelSchedule;
  try {
    button.disabled = true;
    const schedule = await createSchedule(buildSchedulePayload(modelId, `${modelId} 定时综合评测`));
    setNotice(`已为 ${modelId} 创建定时计划 ${schedule.schedule_id}，下一次触发：${formatDate(schedule.next_run_at)}。`);
    await loadSchedules();
  } catch (error) {
    setNotice(`创建定时计划失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

function selectSuite(suiteId, initialSuite = null) {
  activeSuiteId = suiteId;
  elements.suiteId.value = suiteId;
  stopPolling();
  if (initialSuite) renderSuite(initialSuite);
  pollSuite(suiteId);
  pollTimer = setInterval(() => pollSuite(suiteId), 4000);
}

async function pollSuite(suiteId) {
  try {
    const suite = await apiFetch(`/suites/${encodeURIComponent(suiteId)}`);
    renderSuite(suite);
    if (FINAL_STATUSES.has(suite.status)) {
      stopPolling();
      setNotice(`suite ${suite.suite_id} 已结束，状态：${suite.status}。`);
      await loadSuites();
    }
  } catch (error) {
    stopPolling();
    setNotice(`查询失败：${error.message}`, "error");
  }
}

function renderSuite(suite) {
  activeSuite = suite;
  elements.suiteCard.classList.remove("empty");
  elements.suiteCard.replaceChildren();

  const titleRow = document.createElement("div");
  titleRow.className = "suite-title-row";
  const title = document.createElement("h3");
  title.textContent = suite.title || suite.suite_id;
  const badge = document.createElement("span");
  badge.className = `status-badge ${suite.status || ""}`;
  badge.textContent = suite.status || "unknown";
  titleRow.append(title, badge);

  const meta = document.createElement("div");
  meta.className = "meta-grid";
  addMeta(meta, "suite_id", suite.suite_id);
  addMeta(meta, "model_id", suite.model_id);
  addMeta(meta, "当前步骤", suite.current_step || "-");
  addMeta(meta, "更新时间", formatDate(suite.updated_at));

  const list = document.createElement("ul");
  list.className = "step-list";
  const steps = suite.steps || [];
  if (steps.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "暂无步骤信息。";
    elements.suiteCard.append(titleRow, meta, empty);
  } else {
    for (const step of steps) list.append(renderStep(step));
    elements.suiteCard.append(titleRow, meta, list);
  }

  if (suite.errors?.length) {
    const errors = document.createElement("p");
    errors.className = "muted";
    errors.textContent = `错误摘要：${suite.errors.map((item) => item.message || item.code || JSON.stringify(item)).join("；")}`;
    elements.suiteCard.append(errors);
  }

  if (suite.overview_report_path) {
    elements.reportLink.href = `/api/suites/${encodeURIComponent(suite.suite_id)}/report`;
    elements.reportLink.classList.remove("disabled");
  } else {
    elements.reportLink.href = "#";
    elements.reportLink.classList.add("disabled");
  }

  loadSuiteInsights(suite);
}

function addMeta(container, label, value) {
  const item = document.createElement("div");
  const labelNode = document.createElement("span");
  const valueNode = document.createElement("strong");
  labelNode.textContent = label;
  valueNode.textContent = value || "-";
  item.append(labelNode, valueNode);
  container.append(item);
}


function renderStep(step) {
  const template = $("step-template");
  const node = template.content.firstElementChild.cloneNode(true);
  node.classList.add(step.status || "pending");
  node.querySelector("strong").textContent = step.title || step.name;
  const detail = [step.status, step.message, step.task_id ? `task: ${step.task_id}` : ""].filter(Boolean).join(" · ");
  node.querySelector("small").textContent = detail || "pending";
  return node;
}

function setInsightsEmpty(message) {
  elements.insightsGrid.replaceChildren();
  elements.insightsEmpty.hidden = false;
  elements.insightsEmpty.textContent = message;
}

function clearInsightsEmpty() {
  elements.insightsEmpty.hidden = true;
}

async function safeFetchInsight(name, path) {
  try {
    return { name, data: await apiFetch(path, { headers: {} }) };
  } catch (error) {
    return { name, error };
  }
}

async function loadSuiteInsights(suite) {
  const seq = ++insightsRequestSeq;
  if (!suite) {
    setInsightsEmpty("尚未选择 suite，或该 suite 还没有可展示的指标结果。");
    return;
  }

  const jobs = [];
  if (suite.gateway_task_id) jobs.push(safeFetchInsight("gateway", `/tasks/${encodeURIComponent(suite.gateway_task_id)}`));
  if (suite.intelligence_task_id) {
    const suffix = FINAL_STATUSES.has(suite.status) ? "/result" : "";
    jobs.push(safeFetchInsight("intelligence", `/intelligence/tasks/${encodeURIComponent(suite.intelligence_task_id)}${suffix}`));
  }
  if (suite.stress_task_id) {
    const suffix = FINAL_STATUSES.has(suite.status) ? "/result" : "";
    jobs.push(safeFetchInsight("stress", `/stress/tasks/${encodeURIComponent(suite.stress_task_id)}${suffix}`));
  }

  if (jobs.length === 0) {
    setInsightsEmpty("该 suite 还没有生成 gateway、intelligence 或 stress task_id，指标曲线会在任务启动后出现。");
    return;
  }

  elements.insightsEmpty.hidden = false;
  elements.insightsEmpty.textContent = "正在读取指标结果……";
  const results = await Promise.all(jobs);
  if (seq !== insightsRequestSeq) return;

  elements.insightsGrid.replaceChildren();
  const cards = [];
  const errors = [];
  for (const result of results) {
    if (result.error) {
      errors.push(`${result.name}: ${result.error.message}`);
      continue;
    }
    if (result.name === "gateway") cards.push(...buildGatewayCards(result.data));
    if (result.name === "stress") cards.push(...buildStressCards(result.data));
    if (result.name === "intelligence") cards.push(...buildIntelligenceCards(result.data));
  }

  if (cards.length === 0) {
    setInsightsEmpty(errors.length ? `暂未拿到可绘制指标：${errors.join("；")}` : "当前结果还没有可绘制的指标数据。");
    return;
  }

  clearInsightsEmpty();
  for (const card of cards) elements.insightsGrid.append(card);
  if (errors.length) {
    const warning = createMetricCard("部分指标读取失败", errors.join("；"), "wide");
    elements.insightsGrid.append(warning);
  }
}

function buildStressCards(task) {
  const normalized = task?.normalized_result || task?.raw_result?.normalized_result || null;
  const runs = Array.isArray(normalized?.runs) ? normalized.runs : [];
  const rows = normalizeStressRuns(runs);
  if (rows.length === 0) {
    return task?.status && task.status !== "completed" ? [createMetricCard("压测曲线", `压测任务状态：${task.status}，完成后展示吞吐和延迟曲线。`, "wide")] : [];
  }
  return [
    createLineChart("压测吞吐", "按并发档位展示 request/output/total throughput", rows, [
      { key: "request_throughput", label: "请求吞吐", color: "#62d6ff" },
      { key: "output_throughput", label: "输出吞吐", color: "#45e0a8" },
      { key: "total_throughput", label: "总吞吐", color: "#a78bfa" },
    ], "req/s"),
    createLineChart("延迟曲线", "按并发档位展示平均、P95、P99 延迟", rows, [
      { key: "avg_latency_seconds", label: "平均延迟", color: "#62d6ff" },
      { key: "p95_latency_seconds", label: "P95", color: "#ffbf47" },
      { key: "p99_latency_seconds", label: "P99", color: "#ff6b7a" },
    ], "s"),
    createLineChart("首 token 与生成间隔", "TTFT / TPOT 毫秒级延迟", rows, [
      { key: "avg_ttft_ms", label: "平均 TTFT", color: "#62d6ff" },
      { key: "p95_ttft_ms", label: "P95 TTFT", color: "#a78bfa" },
      { key: "avg_tpot_ms", label: "平均 TPOT", color: "#45e0a8" },
      { key: "p95_tpot_ms", label: "P95 TPOT", color: "#ffbf47" },
    ], "ms"),
    createLineChart("成功率", "每个压测档位的成功请求占比", rows.map((row) => ({ ...row, success_rate_percent: normalizeRate(row.success_rate) })), [
      { key: "success_rate_percent", label: "成功率", color: "#45e0a8" },
    ], "%", { yMax: 100 }),
  ];
}

function buildIntelligenceCards(task) {
  const normalized = task?.normalized_result || task?.raw_result?.normalized_result || null;
  const datasets = Array.isArray(normalized?.dataset_results) ? normalized.dataset_results : [];
  const scored = datasets
    .map((item) => ({ label: item.pretty_name || item.dataset, value: normalizeScore(item.score) }))
    .filter((item) => item.value !== null);
  const categoryScores = Array.isArray(normalized?.category_summaries)
    ? normalized.category_summaries
        .map((item) => ({ label: item.category, value: normalizeScore(item.average_score) }))
        .filter((item) => item.value !== null)
    : [];
  const cards = [];
  if (scored.length) cards.push(createBarChart("智力评测数据集分数", "展示各数据集归一化百分制分数", scored, "%", "wide"));
  if (categoryScores.length) cards.push(createBarChart("能力类别平均分", "按 EvalScope 类别聚合的平均分", categoryScores, "%"));
  if (!cards.length && task?.status && task.status !== "completed") {
    cards.push(createMetricCard("智力评测分数", `智力评测任务状态：${task.status}，完成后展示数据集分数。`, "wide"));
  }
  return cards;
}

function buildGatewayCards(task) {
  const results = Array.isArray(task?.results) ? task.results : [];
  if (results.length === 0) return [];
  const counts = results.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});
  const summary = `completed ${counts.completed || 0} · skipped ${counts.skipped || 0} · error ${counts.error || 0}`;
  const card = createMetricCard("网关 smoke 指标", summary, "wide");
  const grid = document.createElement("div");
  grid.className = "gateway-grid";
  for (const result of results) {
    const item = document.createElement("div");
    item.className = `gateway-metric ${result.status || ""}`;
    const name = document.createElement("strong");
    name.textContent = result.metric_name || result.metric_id;
    const detail = document.createElement("small");
    detail.textContent = `${result.status || "unknown"} · ${result.summary || "无摘要"}`;
    item.append(name, detail);
    grid.append(item);
  }
  card.append(grid);
  return [card];
}

function normalizeStressRuns(runs) {
  return runs
    .map((run, index) => ({
      ...run,
      _label: run.parallel ? `P${run.parallel}${run.number ? `/N${run.number}` : ""}` : `#${index + 1}`,
    }))
    .sort((a, b) => (a.parallel || 0) - (b.parallel || 0) || (a.number || 0) - (b.number || 0));
}

function normalizeRate(value) {
  const number = toNumberOrNull(value);
  if (number === null) return null;
  return number <= 1 ? number * 100 : number;
}

function normalizeScore(value) {
  const number = toNumberOrNull(value);
  if (number === null) return null;
  return number <= 1 ? number * 100 : number;
}

function createMetricCard(title, summary, extraClass = "") {
  const card = document.createElement("article");
  card.className = `metric-card ${extraClass}`.trim();
  const heading = document.createElement("h3");
  heading.textContent = title;
  const text = document.createElement("p");
  text.textContent = summary;
  card.append(heading, text);
  return card;
}

function createLineChart(title, subtitle, rows, series, unit = "", options = {}) {
  const validSeries = series.map((item) => ({ ...item, values: rows.map((row) => toNumberOrNull(row[item.key])) })).filter((item) => item.values.some((value) => value !== null));
  if (validSeries.length === 0) return createMetricCard(title, "没有可绘制的数据。", "wide");

  const card = document.createElement("article");
  card.className = "chart-card";
  const head = createChartHead(title, subtitle, validSeries);
  const svg = svgEl("svg");
  svg.setAttribute("viewBox", "0 0 720 320");
  svg.classList.add("chart-svg");

  const margin = { left: 54, right: 20, top: 22, bottom: 54 };
  const width = 720;
  const height = 320;
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const allValues = validSeries.flatMap((item) => item.values).filter((value) => value !== null);
  const yMax = options.yMax ?? niceMax(Math.max(...allValues));
  const yMin = 0;

  for (const ratio of [0, 0.5, 1]) {
    const y = margin.top + plotHeight * ratio;
    svg.append(line(margin.left, y, width - margin.right, y, "chart-grid-line"));
    svg.append(textNode(12, y + 4, formatNumber(yMax - (yMax - yMin) * ratio, unit), "chart-label"));
  }
  svg.append(line(margin.left, margin.top, margin.left, height - margin.bottom, "chart-axis"));
  svg.append(line(margin.left, height - margin.bottom, width - margin.right, height - margin.bottom, "chart-axis"));

  rows.forEach((row, index) => {
    const x = xForIndex(index, rows.length, margin.left, plotWidth);
    svg.append(textNode(x, height - 26, row._label || String(index + 1), "chart-label", "middle"));
  });

  for (const item of validSeries) {
    const points = item.values
      .map((value, index) => (value === null ? null : [xForIndex(index, rows.length, margin.left, plotWidth), yForValue(value, yMin, yMax, margin.top, plotHeight)]))
      .filter(Boolean);
    if (points.length === 0) continue;
    const path = svgEl("path");
    path.setAttribute("d", points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0]},${point[1]}`).join(" "));
    path.setAttribute("stroke", item.color);
    path.classList.add("chart-line");
    svg.append(path);
    for (const point of points) {
      const circle = svgEl("circle");
      circle.setAttribute("cx", point[0]);
      circle.setAttribute("cy", point[1]);
      circle.setAttribute("r", "4");
      circle.setAttribute("fill", item.color);
      circle.classList.add("chart-point");
      svg.append(circle);
    }
  }

  card.append(head, svg);
  return card;
}

function createBarChart(title, subtitle, data, unit = "", extraClass = "") {
  const items = data.slice(0, 16);
  const card = document.createElement("article");
  card.className = `chart-card ${extraClass}`.trim();
  const head = createChartHead(title, subtitle, [{ label: unit || "score", color: "#62d6ff" }]);
  const svg = svgEl("svg");
  svg.setAttribute("viewBox", "0 0 720 330");
  svg.classList.add("chart-svg");

  const margin = { left: 48, right: 20, top: 24, bottom: 88 };
  const width = 720;
  const height = 330;
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const max = niceMax(Math.max(100, ...items.map((item) => item.value)));
  svg.append(line(margin.left, height - margin.bottom, width - margin.right, height - margin.bottom, "chart-axis"));
  for (const ratio of [0, 0.5, 1]) {
    const y = margin.top + plotHeight * ratio;
    svg.append(line(margin.left, y, width - margin.right, y, "chart-grid-line"));
    svg.append(textNode(12, y + 4, formatNumber(max - max * ratio, unit), "chart-label"));
  }

  const gap = 10;
  const barWidth = Math.max(14, (plotWidth - gap * (items.length - 1)) / Math.max(items.length, 1));
  items.forEach((item, index) => {
    const x = margin.left + index * (barWidth + gap);
    const barHeight = (item.value / max) * plotHeight;
    const y = height - margin.bottom - barHeight;
    const rect = svgEl("rect");
    rect.setAttribute("x", x);
    rect.setAttribute("y", y);
    rect.setAttribute("width", barWidth);
    rect.setAttribute("height", barHeight);
    rect.setAttribute("rx", "7");
    rect.setAttribute("fill", "url(#barGradient)");
    svg.append(rect);
    svg.append(textNode(x + barWidth / 2, y - 8, formatNumber(item.value, unit), "bar-label", "middle"));
    const label = textNode(x + barWidth / 2, height - 62, truncateLabel(item.label), "chart-label", "end");
    label.setAttribute("transform", `rotate(-38 ${x + barWidth / 2} ${height - 62})`);
    svg.append(label);
  });

  const defs = svgEl("defs");
  const gradient = svgEl("linearGradient");
  gradient.setAttribute("id", "barGradient");
  gradient.setAttribute("x1", "0");
  gradient.setAttribute("x2", "0");
  gradient.setAttribute("y1", "0");
  gradient.setAttribute("y2", "1");
  const stop1 = svgEl("stop");
  stop1.setAttribute("offset", "0%");
  stop1.setAttribute("stop-color", "#62d6ff");
  const stop2 = svgEl("stop");
  stop2.setAttribute("offset", "100%");
  stop2.setAttribute("stop-color", "#a78bfa");
  gradient.append(stop1, stop2);
  defs.append(gradient);
  svg.prepend(defs);

  if (data.length > items.length) {
    const note = document.createElement("p");
    note.textContent = `仅展示前 ${items.length} 项，共 ${data.length} 项。`;
    note.className = "muted";
    card.append(head, svg, note);
    return card;
  }
  card.append(head, svg);
  return card;
}

function createChartHead(title, subtitle, series) {
  const head = document.createElement("div");
  head.className = "chart-head";
  const copy = document.createElement("div");
  const heading = document.createElement("h3");
  heading.textContent = title;
  const text = document.createElement("p");
  text.textContent = subtitle;
  copy.append(heading, text);
  const legend = document.createElement("div");
  legend.className = "chart-legend";
  for (const item of series) {
    const legendItem = document.createElement("span");
    legendItem.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = item.color;
    const label = document.createElement("span");
    label.textContent = item.label;
    legendItem.append(swatch, label);
    legend.append(legendItem);
  }
  head.append(copy, legend);
  return head;
}

function svgEl(name) {
  return document.createElementNS("http://www.w3.org/2000/svg", name);
}

function line(x1, y1, x2, y2, className) {
  const node = svgEl("line");
  node.setAttribute("x1", x1);
  node.setAttribute("y1", y1);
  node.setAttribute("x2", x2);
  node.setAttribute("y2", y2);
  node.classList.add(className);
  return node;
}

function textNode(x, y, value, className, anchor = "start") {
  const node = svgEl("text");
  node.setAttribute("x", x);
  node.setAttribute("y", y);
  node.setAttribute("text-anchor", anchor);
  node.classList.add(className);
  node.textContent = value;
  return node;
}

function xForIndex(index, length, left, width) {
  return length <= 1 ? left + width / 2 : left + (width * index) / (length - 1);
}

function yForValue(value, min, max, top, height) {
  if (max <= min) return top + height;
  return top + height - ((value - min) / (max - min)) * height;
}

function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / power) * power;
}

function formatNumber(value, unit = "") {
  if (!Number.isFinite(value)) return "-";
  const fixed = Math.abs(value) >= 100 ? value.toFixed(0) : Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2);
  return `${fixed}${unit}`;
}

function truncateLabel(value) {
  const text = String(value || "-");
  return text.length > 14 ? `${text.slice(0, 13)}…` : text;
}

async function loadSuites() {
  try {
    const suites = await apiFetch("/suites?limit=20", { headers: {} });
    renderSuiteList(suites);
  } catch (error) {
    setNotice(`读取 suite 列表失败：${error.message}`, "error");
  }
}

function renderSuiteList(suites) {
  elements.suiteList.replaceChildren();
  if (!Array.isArray(suites) || suites.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "暂无 suite 记录。";
    elements.suiteList.append(empty);
    return;
  }
  for (const suite of suites) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "suite-row";
    const left = document.createElement("span");
    const name = document.createElement("strong");
    const id = document.createElement("small");
    name.textContent = suite.title || suite.suite_id;
    id.textContent = suite.suite_id;
    left.append(name, id);
    const badge = document.createElement("span");
    badge.className = `status-badge ${suite.status || ""}`;
    badge.textContent = suite.status || "unknown";
    row.append(left, badge);
    row.addEventListener("click", () => selectSuite(suite.suite_id, suite));
    elements.suiteList.append(row);
  }
}

function populateModelSelect(select, models) {
  select.replaceChildren();
  if (!Array.isArray(models) || models.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无已保存模型";
    select.append(option);
    return;
  }
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = `${model.name || model.id} · ${model.model} · ${model.protocol}`;
    select.append(option);
  }
}

async function loadModels() {
  try {
    const models = await apiFetch("/models", { headers: {} });
    populateModelSelect(elements.modelSelect, models);
    populateModelSelect(elements.scheduleModelSelect, models);
    if (!Array.isArray(models) || models.length === 0) {
      setNotice("没有读取到已保存模型；可使用 Quick suite 直接评测，或在定时区域保存左侧模型配置。");
      return;
    }
    setNotice(`已读取 ${models.length} 个模型配置。`);
  } catch (error) {
    setNotice(`读取模型失败：${error.message}`, "error");
  }
}

async function loadSchedules() {
  try {
    const schedules = await apiFetch("/suites/schedules?limit=20", { headers: {} });
    renderScheduleList(schedules);
  } catch (error) {
    setNotice(`读取定时计划失败：${error.message}`, "error");
  }
}

function renderScheduleList(schedules) {
  elements.scheduleList.replaceChildren();
  if (!Array.isArray(schedules) || schedules.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "暂无定时计划。";
    elements.scheduleList.append(empty);
    return;
  }
  for (const schedule of schedules) {
    const row = document.createElement("article");
    row.className = "schedule-row";

    const main = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = schedule.name || schedule.schedule_id;
    const detail = document.createElement("small");
    const modeText = schedule.run_once
      ? `只执行一次${schedule.run_date ? `: ${schedule.run_date}` : ""}`
      : `周期执行: 每 ${schedule.interval_days || 1} 天`;
    detail.textContent = [
      schedule.schedule_id,
      `model: ${schedule.model_id}`,
      modeText,
      `${schedule.time_of_day || "--:--"} ${schedule.timezone || ""}`,
      `next: ${formatDate(schedule.next_run_at)}`,
      schedule.last_suite_id ? `last: ${schedule.last_suite_id}` : "",
      `runs: ${schedule.run_count || 0}`,
    ].filter(Boolean).join(" · ");
    main.append(title, detail);

    const actions = document.createElement("div");
    actions.className = "schedule-actions";
    const badge = document.createElement("span");
    badge.className = `status-badge ${schedule.enabled ? "completed" : "failed"}`;
    badge.textContent = schedule.enabled ? "enabled" : (schedule.run_once ? "done" : "disabled");
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "mini";
    trigger.textContent = "立即触发";
    trigger.addEventListener("click", () => triggerSchedule(schedule.schedule_id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini danger";
    remove.textContent = "删除";
    remove.addEventListener("click", () => deleteSchedule(schedule.schedule_id));
    actions.append(badge, trigger, remove);
    row.append(main, actions);
    elements.scheduleList.append(row);
  }
}

async function triggerSchedule(scheduleId) {
  try {
    setNotice(`正在手动触发定时计划 ${scheduleId}……`);
    const suite = await apiFetch(`/suites/schedules/${encodeURIComponent(scheduleId)}/trigger`, { method: "POST" });
    setNotice(`已触发 ${suite.suite_id}，开始轮询进度。`);
    selectSuite(suite.suite_id, suite);
    await Promise.all([loadSchedules(), loadSuites()]);
  } catch (error) {
    setNotice(`触发失败：${error.message}`, "error");
  }
}

async function deleteSchedule(scheduleId) {
  if (!window.confirm(`确认删除定时计划 ${scheduleId}？`)) return;
  try {
    await apiFetch(`/suites/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" });
    setNotice(`已删除定时计划 ${scheduleId}。`);
    await loadSchedules();
  } catch (error) {
    setNotice(`删除失败：${error.message}`, "error");
  }
}

elements.quickForm.addEventListener("submit", startQuickSuite);
elements.loadModels.addEventListener("click", loadModels);
elements.startDefault.addEventListener("click", startDefaultSuite);
elements.createQuickSchedule.addEventListener("click", createScheduleFromQuick);
elements.createModelSchedule.addEventListener("click", createScheduleFromSaved);
elements.refreshSchedules.addEventListener("click", loadSchedules);
elements.scheduleMode.addEventListener("change", updateScheduleMode);
elements.refreshSuites.addEventListener("click", loadSuites);
elements.trackSuite.addEventListener("click", () => {
  const suiteId = elements.suiteId.value.trim();
  if (!suiteId) return setNotice("请输入 suite_id。", "error");
  selectSuite(suiteId);
});
elements.stopPoll.addEventListener("click", () => {
  stopPolling();
  setNotice(activeSuiteId ? `已停止轮询 ${activeSuiteId}。` : "当前没有正在轮询的 suite。");
});
elements.clearKey.addEventListener("click", () => {
  $("key").value = "";
  setNotice("Key 输入框已清空。浏览器不会把 Key 写入本页面的本地存储。");
});
elements.refreshInsights.addEventListener("click", () => {
  if (!activeSuite) return setInsightsEmpty("请先选择一个 suite。");
  loadSuiteInsights(activeSuite);
});

if (!elements.scheduleDate.value) elements.scheduleDate.value = defaultOneShotDate();
updateScheduleMode();
loadSuites();
loadModels();
loadSchedules();
