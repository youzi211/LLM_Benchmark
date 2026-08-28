const API_ROOT = "/api";
const FINAL_STATUSES = new Set(["completed", "partial", "failed", "interrupted", "error"]);

const $ = (id) => document.getElementById(id);

const elements = {
  notice: $("notice"),
  globalModelSelect: $("global-model-select"),
  refreshModels: $("refresh-models"),
  refreshCurrentTab: $("refresh-current-tab"),
  statusBasic: $("status-basic"),
  statusStress: $("status-stress"),
  statusIntelligence: $("status-intelligence"),
  statusJudge: $("status-judge"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
  basicPlan: $("basic-plan"),
  basicMetrics: $("basic-metrics"),
  startBasic: $("start-basic"),
  refreshBasic: $("refresh-basic"),
  basicTaskList: $("basic-task-list"),
  basicDetail: $("basic-detail"),
  basicReportLink: $("basic-report-link"),
  stressCustomEnabled: $("stress-custom-enabled"),
  stressParallel: $("stress-parallel"),
  stressNumber: $("stress-number"),
  stressStream: $("stress-stream"),
  stressDataset: $("stress-dataset"),
  stressDatasetPath: $("stress-dataset-path"),
  stressRate: $("stress-rate"),
  stressMinPrompt: $("stress-min-prompt"),
  stressMaxPrompt: $("stress-max-prompt"),
  stressMinTokens: $("stress-min-tokens"),
  stressMaxTokens: $("stress-max-tokens"),
  startStress: $("start-stress"),
  refreshStress: $("refresh-stress"),
  stressTaskList: $("stress-task-list"),
  stressDetail: $("stress-detail"),
  stressReportLink: $("stress-report-link"),
  intelligenceCustomEnabled: $("intelligence-custom-enabled"),
  intelligenceLimit: $("intelligence-limit"),
  intelligenceBatchSize: $("intelligence-batch-size"),
  datasetPicker: $("dataset-picker"),
  startIntelligence: $("start-intelligence"),
  refreshIntelligence: $("refresh-intelligence"),
  intelligenceTaskList: $("intelligence-task-list"),
  intelligenceDetail: $("intelligence-detail"),
  intelligenceReportLink: $("intelligence-report-link"),
  startFullSuite: $("start-full-suite"),
  startQuickSuite: $("start-quick-suite"),
  refreshSuites: $("refresh-suites"),
  suiteList: $("suite-list"),
  scheduleMode: $("schedule-mode"),
  scheduleDate: $("schedule-date"),
  scheduleInterval: $("schedule-interval"),
  createSchedule: $("create-schedule"),
  scheduleList: $("schedule-list"),
};

const state = {
  activeTab: "basic",
  models: [],
  datasets: {},
  defaultDatasets: [],
  selected: { basic: null, stress: null, intelligence: null },
  tasks: { basic: [], stress: [], intelligence: [] },
  pollTimer: null,
};

function setNotice(message, type = "info") {
  elements.notice.textContent = message;
  elements.notice.classList.toggle("error", type === "error");
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

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function toNumberOrNull(value) {
  if (value === undefined || value === null || String(value).trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseIntegerList(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const parts = raw.split(/[，,\s]+/).filter(Boolean);
  const numbers = parts.map((item) => Number(item));
  if (numbers.some((item) => !Number.isInteger(item) || item < 1)) {
    throw new Error(`列表参数只能包含正整数：${raw}`);
  }
  return numbers;
}

function parseMetricList(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  return raw.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean);
}

function localDateString(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function selectedModelId() {
  return elements.globalModelSelect.value;
}

function requireModelId() {
  const modelId = selectedModelId();
  if (!modelId) throw new Error("请先在顶部选择一个模型。");
  return modelId;
}

function clear(node) {
  node.replaceChildren();
}

function textEl(tag, text, className = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function statusBadge(status) {
  const badge = document.createElement("span");
  badge.className = `status-badge ${status || ""}`;
  badge.textContent = status || "unknown";
  return badge;
}

function setHealth(element, label, ok, detail = "") {
  element.textContent = `${label} ${ok ? "OK" : "异常"}${detail ? ` · ${detail}` : ""}`;
  element.classList.toggle("ok", Boolean(ok));
  element.classList.toggle("bad", !ok);
}

function setReportLink(link, href) {
  if (href) {
    link.href = href;
    link.classList.remove("disabled");
  } else {
    link.href = "#";
    link.classList.add("disabled");
  }
}

function makeMetaGrid(rows) {
  const grid = document.createElement("div");
  grid.className = "meta-grid";
  for (const [label, value] of rows) {
    const item = document.createElement("div");
    item.append(textEl("span", label), textEl("strong", value === undefined || value === null || value === "" ? "-" : String(value)));
    grid.append(item);
  }
  return grid;
}

function taskTitle(task) {
  return task.task_id || task.suite_id || task.overview_id || "unknown";
}

function taskModel(task) {
  return task.model_id || task.model || task.upstream_model_name || "-";
}

function taskUpdatedAt(task) {
  return task.updated_at || task.completed_at || task.finished_at || task.started_at || task.created_at || "";
}

function renderTaskList(container, tasks, selectedId, onSelect, emptyText) {
  clear(container);
  if (!Array.isArray(tasks) || tasks.length === 0) {
    container.append(textEl("p", emptyText, "muted"));
    return;
  }
  for (const task of tasks) {
    const id = taskTitle(task);
    const row = document.createElement("button");
    row.type = "button";
    row.className = `task-row ${id === selectedId ? "selected" : ""}`;
    const left = document.createElement("span");
    left.append(textEl("strong", id), textEl("small", `${taskModel(task)} · ${formatDate(taskUpdatedAt(task))}`));
    row.append(left, statusBadge(task.status));
    row.addEventListener("click", () => onSelect(id));
    container.append(row);
  }
}

async function loadModels() {
  try {
    state.models = await apiFetch("/models");
    const previous = selectedModelId();
    clear(elements.globalModelSelect);
    if (!state.models.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无已保存模型";
      elements.globalModelSelect.append(option);
      setNotice("没有读取到已保存模型。可用一键完整评测里的临时模型入口先跑一次。", "error");
      return;
    }
    for (const model of state.models) {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = `${model.name || model.id} · ${model.model || "-"}`;
      elements.globalModelSelect.append(option);
    }
    if (previous && state.models.some((item) => item.id === previous)) elements.globalModelSelect.value = previous;
    setNotice(`已加载 ${state.models.length} 个模型。`);
  } catch (error) {
    setNotice(`读取模型失败：${error.message}`, "error");
  }
}

async function loadSystemStatus() {
  const [intel, stress, judge] = await Promise.allSettled([
    apiFetch("/intelligence/evalscope/health"),
    apiFetch("/stress/evalscope/health"),
    apiFetch("/intelligence/evalscope/judge-config"),
  ]);
  setHealth(elements.statusBasic, "基础服务", true);
  setHealth(elements.statusIntelligence, "能力 EvalScope", intel.status === "fulfilled", intel.status === "fulfilled" ? intel.value.evalscope_version || "" : intel.reason.message);
  setHealth(elements.statusStress, "压测 EvalScope", stress.status === "fulfilled", stress.status === "fulfilled" ? stress.value.evalscope_version || "" : stress.reason.message);
  setHealth(elements.statusJudge, "Judge", judge.status === "fulfilled" && Boolean(judge.value.configured), judge.status === "fulfilled" ? (judge.value.model_id || judge.value.missing_reason || "") : judge.reason.message);
}

async function loadDatasets() {
  try {
    const data = await apiFetch("/intelligence/datasets");
    state.datasets = data.datasets || {};
    state.defaultDatasets = Array.isArray(data.default_datasets) ? data.default_datasets : [];
    renderDatasetPicker();
  } catch (error) {
    elements.datasetPicker.textContent = `读取数据集失败：${error.message}`;
  }
}

function localDatasetNames() {
  return Object.keys(state.datasets).filter((name) => Boolean(state.datasets[name]?.available_local));
}

function renderDatasetPicker() {
  clear(elements.datasetPicker);
  const names = localDatasetNames().sort((left, right) => {
    const a = state.datasets[left] || {};
    const b = state.datasets[right] || {};
    if (state.defaultDatasets.includes(left) !== state.defaultDatasets.includes(right)) return state.defaultDatasets.includes(left) ? -1 : 1;
    return left.localeCompare(right);
  });
  if (!names.length) {
    elements.datasetPicker.append(textEl("p", "未发现本地可用数据集。请先由管理员在 data/evalscope_datasets 下提供数据集目录。", "muted"));
    return;
  }
  const help = textEl("p", "只展示本地已提供的数据集；卡片内会标明用途描述、Judge/sandbox 要求、默认 subset 和本地子集。", "hint dataset-help");
  const group = document.createElement("div");
  group.className = "dataset-grid";
  for (const name of names) {
    const meta = state.datasets[name] || {};
    const card = document.createElement("div");
    card.className = "dataset-card local";

    const label = document.createElement("label");
    label.className = "dataset-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = name;
    input.checked = state.defaultDatasets.includes(name);
    const titleWrap = document.createElement("span");
    titleWrap.className = "dataset-title";
    titleWrap.append(textEl("strong", meta.pretty_name || name), textEl("small", name));
    label.append(input, titleWrap);

    const badges = document.createElement("div");
    badges.className = "dataset-badges";
    badges.append(datasetBadge("本地可用", "ok"));
    if (state.defaultDatasets.includes(name)) badges.append(datasetBadge("默认", "info"));
    if (meta.needs_judge) badges.append(datasetBadge("需要 Judge", "warn"));
    if (Array.isArray(meta.categories) && meta.categories.includes("Code")) badges.append(datasetBadge("需要 sandbox", "warn"));
    if (Array.isArray(meta.categories)) {
      meta.categories.slice(0, 3).forEach((category) => badges.append(datasetBadge(category, "muted")));
    }

    const description = textEl("p", meta.description || "暂无描述；请参考 EvalScope 官方数据集说明后再选择。", "dataset-description");
    const localPath = meta.local_path ? textEl("small", `本地路径：${meta.local_path}`, "dataset-path") : null;
    const subsetInfo = renderDatasetSubsetInfo(meta);

    card.append(label, badges, description);
    if (localPath) card.append(localPath);
    if (subsetInfo) card.append(subsetInfo);
    group.append(card);
  }
  elements.datasetPicker.append(help, group);
  updateDatasetPickerState();
}

function datasetBadge(text, tone = "muted") {
  const badge = document.createElement("span");
  badge.className = `dataset-badge ${tone}`;
  badge.textContent = text;
  return badge;
}

function renderDatasetSubsetInfo(meta) {
  const subsets = Array.isArray(meta.subsets) ? meta.subsets : [];
  const configured = Array.isArray(meta.configured_subset_list) ? meta.configured_subset_list : [];
  if (!subsets.length && !configured.length) return null;
  const details = document.createElement("details");
  details.className = "dataset-subsets";
  const summaryParts = [];
  if (subsets.length) summaryParts.push(`本地子集 ${subsets.length} 个`);
  if (configured.length) summaryParts.push(`默认运行：${configured.join(", ")}`);
  const summary = document.createElement("summary");
  summary.textContent = summaryParts.join(" · ");
  details.append(summary);
  if (configured.length) details.append(textEl("p", `当前配置 subset_list：${configured.join(", ")}`, "dataset-subset-default"));
  if (subsets.length) {
    const list = document.createElement("div");
    list.className = "subset-list";
    subsets.forEach((subset) => list.append(datasetBadge(subset, configured.includes(subset) ? "info" : "muted")));
    details.append(list);
  }
  return details;
}

function updateDatasetPickerState() {
  const enabled = elements.intelligenceCustomEnabled.checked;
  elements.datasetPicker.classList.toggle("disabled", !enabled);
  elements.datasetPicker.querySelectorAll("input[type='checkbox']").forEach((input) => {
    input.disabled = !enabled;
  });
}

async function loadBasicTasks() {
  state.tasks.basic = await apiFetch("/tasks?limit=50");
  renderTaskList(elements.basicTaskList, state.tasks.basic, state.selected.basic, selectBasicTask, "暂无基础评测任务。");
}

async function loadStressTasks() {
  state.tasks.stress = await apiFetch("/stress/tasks?limit=50");
  renderTaskList(elements.stressTaskList, state.tasks.stress, state.selected.stress, selectStressTask, "暂无压测任务。");
}

async function loadIntelligenceTasks() {
  state.tasks.intelligence = await apiFetch("/intelligence/tasks?limit=50");
  renderTaskList(elements.intelligenceTaskList, state.tasks.intelligence, state.selected.intelligence, selectIntelligenceTask, "暂无能力评测任务。");
}

async function refreshActiveTab() {
  try {
    if (state.activeTab === "basic") await loadBasicTasks();
    if (state.activeTab === "stress") await loadStressTasks();
    if (state.activeTab === "intelligence") await loadIntelligenceTasks();
    await refreshSelectedDetail();
  } catch (error) {
    setNotice(`刷新失败：${error.message}`, "error");
  }
}

async function refreshSelectedDetail() {
  if (state.activeTab === "basic" && state.selected.basic) await selectBasicTask(state.selected.basic, { reloadList: false });
  if (state.activeTab === "stress" && state.selected.stress) await selectStressTask(state.selected.stress, { reloadList: false });
  if (state.activeTab === "intelligence" && state.selected.intelligence) await selectIntelligenceTask(state.selected.intelligence, { reloadList: false });
}

function switchTab(tab) {
  state.activeTab = tab;
  elements.tabButtons.forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  elements.tabPanels.forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${tab}`));
  refreshActiveTab();
}

async function startBasicTask() {
  try {
    const modelId = requireModelId();
    const payload = { model_id: modelId, plan_id: elements.basicPlan.value || "gateway_acceptance_v1" };
    const metrics = parseMetricList(elements.basicMetrics.value);
    if (metrics) payload.metric_ids = metrics;
    setNotice("正在提交基础评测……");
    const task = await apiFetch("/tasks/run", { method: "POST", body: JSON.stringify(payload) });
    state.selected.basic = task.task_id;
    await loadBasicTasks();
    await selectBasicTask(task.task_id, { reloadList: false });
    setNotice(`基础评测完成：${task.task_id}，状态：${task.status}`);
  } catch (error) {
    setNotice(`基础评测失败：${error.message}`, "error");
  }
}

async function startStressTask() {
  try {
    const modelId = requireModelId();
    const payload = { model_id: modelId };
    if (elements.stressCustomEnabled.checked) {
      const parallel = parseIntegerList(elements.stressParallel.value);
      const number = parseIntegerList(elements.stressNumber.value);
      if (parallel) payload.parallel = parallel;
      if (number) payload.number = number;
      if (elements.stressStream.value) payload.stream = elements.stressStream.value === "true";
      if (elements.stressDataset.value.trim()) payload.dataset = elements.stressDataset.value.trim();
      if (elements.stressDatasetPath.value.trim()) payload.dataset_path = elements.stressDatasetPath.value.trim();
      const numericFields = [
        ["rate", elements.stressRate],
        ["min_prompt_length", elements.stressMinPrompt],
        ["max_prompt_length", elements.stressMaxPrompt],
        ["min_tokens", elements.stressMinTokens],
        ["max_tokens", elements.stressMaxTokens],
      ];
      for (const [key, input] of numericFields) {
        const value = toNumberOrNull(input.value);
        if (value !== null) payload[key] = value;
      }
    }
    setNotice("正在提交压测评测……");
    const task = await apiFetch("/stress/tasks/default", { method: "POST", body: JSON.stringify(payload) });
    state.selected.stress = task.task_id;
    await loadStressTasks();
    await selectStressTask(task.task_id, { reloadList: false });
    setNotice(`已启动压测评测：${task.task_id}`);
  } catch (error) {
    setNotice(`压测提交失败：${error.message}`, "error");
  }
}

async function startIntelligenceTask() {
  try {
    const modelId = requireModelId();
    const limit = toNumberOrNull(elements.intelligenceLimit.value);
    const evalBatchSize = toNumberOrNull(elements.intelligenceBatchSize.value);
    const customEnabled = elements.intelligenceCustomEnabled.checked;
    const selected = customEnabled
      ? Array.from(elements.datasetPicker.querySelectorAll("input[type='checkbox']:checked")).map((input) => input.value)
      : localDatasetNames().filter((name) => state.defaultDatasets.includes(name));
    const fallbackLocal = localDatasetNames();
    const datasets = selected.length ? selected : fallbackLocal;
    if (!datasets.length) throw new Error("未发现本地可用数据集，请先由管理员提供数据集目录。");
    const path = "/intelligence/tasks";
    const payload = { model_id: modelId, datasets };
    if (limit !== null) payload.limit = limit;
    if (evalBatchSize !== null) payload.eval_batch_size = evalBatchSize;
    setNotice("正在提交能力评测……");
    const task = await apiFetch(path, { method: "POST", body: JSON.stringify(payload) });
    state.selected.intelligence = task.task_id;
    await loadIntelligenceTasks();
    await selectIntelligenceTask(task.task_id, { reloadList: false });
    setNotice(`已启动能力评测：${task.task_id}`);
  } catch (error) {
    setNotice(`能力评测提交失败：${error.message}`, "error");
  }
}

async function selectBasicTask(taskId, options = {}) {
  state.selected.basic = taskId;
  if (options.reloadList !== false) await loadBasicTasks();
  const task = await apiFetch(`/tasks/${encodeURIComponent(taskId)}`);
  renderBasicDetail(task);
}

async function selectStressTask(taskId, options = {}) {
  state.selected.stress = taskId;
  if (options.reloadList !== false) await loadStressTasks();
  const cached = state.tasks.stress.find((item) => item.task_id === taskId);
  const suffix = cached && FINAL_STATUSES.has(cached.status) ? "/result" : "";
  const task = await apiFetch(`/stress/tasks/${encodeURIComponent(taskId)}${suffix}`);
  renderStressDetail(task);
}

async function selectIntelligenceTask(taskId, options = {}) {
  state.selected.intelligence = taskId;
  if (options.reloadList !== false) await loadIntelligenceTasks();
  const cached = state.tasks.intelligence.find((item) => item.task_id === taskId);
  const suffix = cached && FINAL_STATUSES.has(cached.status) ? "/result" : "";
  const task = await apiFetch(`/intelligence/tasks/${encodeURIComponent(taskId)}${suffix}`);
  renderIntelligenceDetail(task);
}

function renderBasicDetail(task) {
  clear(elements.basicDetail);
  elements.basicDetail.className = "detail-content";
  setReportLink(elements.basicReportLink, task.report_path ? `/api/reports/${encodeURIComponent(task.task_id)}` : null);
  const header = document.createElement("div");
  header.className = "detail-header";
  header.append(textEl("h3", task.task_id), statusBadge(task.status));
  elements.basicDetail.append(header);
  elements.basicDetail.append(makeMetaGrid([
    ["模型", task.model_id],
    ["计划", task.plan_id],
    ["协议", task.protocol],
    ["开始", formatDate(task.started_at)],
    ["完成", formatDate(task.finished_at)],
    ["耗时", task.duration_ms ? `${Math.round(task.duration_ms)} ms` : "-"],
  ]));
  const results = Array.isArray(task.results) ? task.results : [];
  if (results.length) {
    const grid = document.createElement("div");
    grid.className = "gateway-grid";
    for (const item of results) {
      const card = document.createElement("div");
      card.className = `gateway-metric ${item.status || ""}`;
      card.append(textEl("strong", item.metric_name || item.metric_id), textEl("small", `${item.status} · ${item.summary || "-"}`));
      grid.append(card);
    }
    elements.basicDetail.append(grid);
  }
  if (task.error) elements.basicDetail.append(createMetricCard("错误摘要", JSON.stringify(task.error), "wide"));
}

function renderStressDetail(task) {
  clear(elements.stressDetail);
  elements.stressDetail.className = "detail-content";
  setReportLink(elements.stressReportLink, task.report_path ? `/api/stress/reports/${encodeURIComponent(task.task_id)}` : null);
  const header = document.createElement("div");
  header.className = "detail-header";
  header.append(textEl("h3", task.task_id), statusBadge(task.status));
  if (!FINAL_STATUSES.has(task.status)) header.append(actionButton("取消", () => cancelStressTask(task.task_id), "danger"));
  elements.stressDetail.append(header);
  elements.stressDetail.append(makeMetaGrid([
    ["模型", task.model_id],
    ["上游模型", task.upstream_model_name],
    ["进度", task.progress],
    ["创建", formatDate(task.created_at)],
    ["更新", formatDate(task.updated_at)],
    ["输出目录", task.raw_output_dir],
  ]));
  const normalized = task.normalized_result || task.raw_result?.normalized_result || null;
  const rows = normalizeStressRuns(Array.isArray(normalized?.runs) ? normalized.runs : []);
  if (rows.length) {
    const charts = buildStressCards(task);
    const chartGrid = document.createElement("div");
    chartGrid.className = "insights-grid";
    charts.forEach((card) => chartGrid.append(card));
    elements.stressDetail.append(chartGrid);
  } else if (task.status && task.status !== "completed") {
    elements.stressDetail.append(createMetricCard("压测状态", task.progress || `压测任务状态：${task.status}`));
  }
  if (task.error) elements.stressDetail.append(createMetricCard("错误摘要", JSON.stringify(task.error), "wide"));
}

function renderIntelligenceDetail(task) {
  clear(elements.intelligenceDetail);
  elements.intelligenceDetail.className = "detail-content";
  setReportLink(elements.intelligenceReportLink, task.report_path ? `/api/intelligence/reports/${encodeURIComponent(task.task_id)}` : null);
  const header = document.createElement("div");
  header.className = "detail-header";
  header.append(textEl("h3", task.task_id), statusBadge(task.status));
  if (!FINAL_STATUSES.has(task.status)) header.append(actionButton("取消", () => cancelIntelligenceTask(task.task_id), "danger"));
  elements.intelligenceDetail.append(header);
  elements.intelligenceDetail.append(makeMetaGrid([
    ["模型", task.model_id],
    ["上游模型", task.upstream_model_name],
    ["数据集", Array.isArray(task.datasets) ? task.datasets.join(", ") : "-"],
    ["进度", task.progress],
    ["创建", formatDate(task.created_at)],
    ["更新", formatDate(task.updated_at)],
    ["输出目录", task.raw_output_dir],
  ]));
  const cards = buildIntelligenceCards(task);
  if (cards.length) {
    const grid = document.createElement("div");
    grid.className = "insights-grid";
    cards.forEach((card) => grid.append(card));
    elements.intelligenceDetail.append(grid);
  }
  if (task.error) elements.intelligenceDetail.append(createMetricCard("错误摘要", JSON.stringify(task.error), "wide"));
}

function actionButton(label, handler, kind = "mini") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `mini ${kind}`.trim();
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

async function cancelStressTask(taskId) {
  if (!window.confirm(`确认取消压测任务 ${taskId}？`)) return;
  await apiFetch(`/stress/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
  await loadStressTasks();
  await selectStressTask(taskId, { reloadList: false });
  setNotice(`已取消压测任务 ${taskId}`);
}

async function cancelIntelligenceTask(taskId) {
  if (!window.confirm(`确认取消能力评测任务 ${taskId}？`)) return;
  await apiFetch(`/intelligence/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
  await loadIntelligenceTasks();
  await selectIntelligenceTask(taskId, { reloadList: false });
  setNotice(`已取消能力评测任务 ${taskId}`);
}

async function startFullSuite() {
  try {
    const modelId = requireModelId();
    const payload = {
      model_id: modelId,
      title: `${modelId} 完整评测`,
      run_gateway: $("suite-run-basic").checked,
      run_stress: $("suite-run-stress").checked,
      run_intelligence: $("suite-run-intelligence").checked,
      wait_for_completion: false,
    };
    if (!payload.run_gateway && !payload.run_stress && !payload.run_intelligence) throw new Error("至少选择一个评测部分。");
    const suite = await apiFetch("/suites/default", { method: "POST", body: JSON.stringify(payload) });
    setNotice(`已启动一键完整评测：${suite.suite_id}`);
    await loadSuites();
  } catch (error) {
    setNotice(`启动完整评测失败：${error.message}`, "error");
  }
}

async function startQuickSuite() {
  try {
    const payload = {
      url: $("quick-url").value.trim(),
      key: $("quick-key").value,
      model: $("quick-model").value.trim(),
      protocol: $("quick-protocol").value,
      run_gateway: $("suite-run-basic").checked,
      run_stress: $("suite-run-stress").checked,
      run_intelligence: $("suite-run-intelligence").checked,
      wait_for_completion: false,
    };
    if (!payload.url || !payload.model) throw new Error("请填写临时模型 URL 和 model。");
    const suite = await apiFetch("/suites/quick", { method: "POST", body: JSON.stringify(payload) });
    $("quick-key").value = "";
    setNotice(`已启动临时模型完整评测：${suite.suite_id}。Key 输入框已清空。`);
    await loadSuites();
  } catch (error) {
    setNotice(`启动临时完整评测失败：${error.message}`, "error");
  }
}

async function loadSuites() {
  try {
    const suites = await apiFetch("/suites?limit=20");
    clear(elements.suiteList);
    if (!suites.length) {
      elements.suiteList.append(textEl("p", "暂无完整评测。", "muted"));
      return;
    }
    for (const suite of suites) {
      const row = document.createElement("div");
      row.className = "schedule-row";
      const left = document.createElement("div");
      left.append(textEl("strong", suite.title || suite.suite_id), textEl("small", `${suite.model_id || "-"} · ${suite.current_step || "-"} · ${formatDate(suite.updated_at)}`));
      const actions = document.createElement("div");
      actions.className = "schedule-actions";
      actions.append(statusBadge(suite.status));
      if (suite.overview_report_path) {
        const link = document.createElement("a");
        link.className = "mini link-button";
        link.href = `/api/suites/${encodeURIComponent(suite.suite_id)}/report`;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = "报告";
        actions.append(link);
      }
      if (!FINAL_STATUSES.has(suite.status)) actions.append(actionButton("取消", () => cancelSuite(suite.suite_id), "danger"));
      row.append(left, actions);
      elements.suiteList.append(row);
    }
  } catch (error) {
    elements.suiteList.textContent = `读取完整评测失败：${error.message}`;
  }
}

async function cancelSuite(suiteId) {
  if (!window.confirm(`确认取消完整评测 ${suiteId}？`)) return;
  try {
    await apiFetch(`/suites/${encodeURIComponent(suiteId)}/cancel`, { method: "POST" });
    setNotice(`已取消完整评测 ${suiteId}`);
    await loadSuites();
  } catch (error) {
    setNotice(`取消完整评测失败：${error.message}`, "error");
  }
}

async function loadSchedules() {
  try {
    const schedules = await apiFetch("/suites/schedules?limit=20");
    clear(elements.scheduleList);
    if (!schedules.length) {
      elements.scheduleList.append(textEl("p", "暂无定时任务。", "muted"));
      return;
    }
    for (const schedule of schedules) {
      const row = document.createElement("div");
      row.className = "schedule-row";
      const left = document.createElement("div");
      left.append(textEl("strong", schedule.name || schedule.schedule_id), textEl("small", `${schedule.model_id} · ${schedule.profile || "无 profile"} · next ${formatDate(schedule.next_run_at)}`));
      const actions = document.createElement("div");
      actions.className = "schedule-actions";
      actions.append(statusBadge(schedule.enabled ? "completed" : "failed"));
      actions.append(actionButton("立即触发", () => triggerSchedule(schedule.schedule_id)));
      actions.append(actionButton("删除", () => deleteSchedule(schedule.schedule_id), "danger"));
      row.append(left, actions);
      elements.scheduleList.append(row);
    }
  } catch (error) {
    elements.scheduleList.textContent = `读取定时任务失败：${error.message}`;
  }
}

async function createSchedule() {
  try {
    const modelId = requireModelId();
    const mode = elements.scheduleMode.value;
    const payload = {
      name: $("schedule-name").value.trim() || `${modelId} 定时评测`,
      model_id: modelId,
      profile: $("schedule-profile").value || "scheduled_light",
      title: `${modelId} 定时评测`,
      time_of_day: $("schedule-time").value || "02:00",
      timezone: "Asia/Shanghai",
      interval_days: mode === "once" ? 1 : Number(elements.scheduleInterval.value || 1),
      run_once: mode === "once",
      run_gateway: $("schedule-run-basic").checked,
      run_stress: $("schedule-run-stress").checked,
      run_intelligence: $("schedule-run-intelligence").checked,
      gateway_plan_id: "gateway_acceptance_v1",
    };
    if (mode === "once") payload.run_date = elements.scheduleDate.value || localDateString(new Date(Date.now() + 24 * 3600 * 1000));
    if (!payload.run_gateway && !payload.run_stress && !payload.run_intelligence) throw new Error("至少选择一个评测部分。");
    const schedule = await apiFetch("/suites/schedules", { method: "POST", body: JSON.stringify(payload) });
    setNotice(`已创建定时任务：${schedule.schedule_id}`);
    await loadSchedules();
  } catch (error) {
    setNotice(`创建定时任务失败：${error.message}`, "error");
  }
}

async function triggerSchedule(scheduleId) {
  try {
    const suite = await apiFetch(`/suites/schedules/${encodeURIComponent(scheduleId)}/trigger`, { method: "POST" });
    setNotice(`已触发定时任务 ${scheduleId}，生成 suite：${suite.suite_id || suite.last_suite_id || "-"}`);
  } catch (error) {
    setNotice(`触发失败：${error.message}`, "error");
  }
}

async function deleteSchedule(scheduleId) {
  if (!window.confirm(`确认删除定时任务 ${scheduleId}？`)) return;
  try {
    await apiFetch(`/suites/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" });
    setNotice(`已删除定时任务 ${scheduleId}`);
    await loadSchedules();
  } catch (error) {
    setNotice(`删除失败：${error.message}`, "error");
  }
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

function normalizeStressRuns(runs) {
  return runs.map((run, index) => ({ ...run, label: run.parallel ? `P${run.parallel}` : `#${index + 1}` }));
}

function buildStressCards(task) {
  const normalized = task?.normalized_result || task?.raw_result?.normalized_result || null;
  const runs = Array.isArray(normalized?.runs) ? normalized.runs : [];
  const rows = normalizeStressRuns(runs);
  if (!rows.length) return [];
  return [
    createLineChart("压测吞吐", "request / output / total throughput", rows, [
      { key: "request_throughput", label: "请求吞吐", color: "#62d6ff" },
      { key: "output_throughput", label: "输出吞吐", color: "#45e0a8" },
      { key: "total_throughput", label: "总吞吐", color: "#a78bfa" },
    ], "req/s"),
    createLineChart("延迟曲线", "平均、P95、P99 延迟", rows, [
      { key: "avg_latency_seconds", label: "平均", color: "#62d6ff" },
      { key: "p95_latency_seconds", label: "P95", color: "#ffbf47" },
      { key: "p99_latency_seconds", label: "P99", color: "#ff6b7a" },
    ], "s"),
    createLineChart("TTFT / TPOT", "首 token 与生成间隔", rows, [
      { key: "avg_ttft_ms", label: "TTFT", color: "#a78bfa" },
      { key: "avg_tpot_ms", label: "TPOT", color: "#45e0a8" },
    ], "ms"),
    createLineChart("成功率", "每个并发档位的成功请求占比", rows.map((row) => ({ ...row, success_rate_percent: normalizeRate(row.success_rate) })), [
      { key: "success_rate_percent", label: "成功率", color: "#45e0a8" },
    ], "%", { yMax: 100 }),
  ];
}

function buildIntelligenceCards(task) {
  const cards = [];
  if (task?.status && task.status !== "completed") cards.push(createProgressCard("能力评测进度", task));
  const normalized = task?.normalized_result || task?.raw_result?.normalized_result || null;
  const datasets = Array.isArray(normalized?.dataset_results) ? normalized.dataset_results : [];
  const scored = datasets.map((item) => ({ label: item.pretty_name || item.dataset, value: normalizeScore(item.score) })).filter((item) => item.value !== null);
  const categories = Array.isArray(normalized?.category_summaries)
    ? normalized.category_summaries.map((item) => ({ label: item.category, value: normalizeScore(item.average_score) })).filter((item) => item.value !== null)
    : [];
  if (scored.length) cards.push(createBarChart("数据集分数", "各 EvalScope 数据集归一化百分制分数", scored, "%", "wide"));
  if (categories.length) cards.push(createBarChart("能力类别平均分", "按 EvalScope 类别聚合", categories, "%"));
  return cards;
}

function createMetricCard(title, summary, extraClass = "") {
  const card = document.createElement("article");
  card.className = `metric-card ${extraClass}`.trim();
  card.append(textEl("h3", title), textEl("p", summary || "-"));
  return card;
}

function createProgressCard(title, task) {
  const detail = task?.progress_detail || null;
  const summary = detail?.message || task?.progress || `任务状态：${task?.status || "unknown"}`;
  const card = createMetricCard(title, summary, "wide");
  const value = Number.isFinite(Number(detail?.overall_percent)) ? Number(detail.overall_percent) : Number(detail?.percent);
  if (Number.isFinite(value)) {
    const clamped = Math.max(0, Math.min(value, 100));
    const bar = document.createElement("div");
    bar.className = "progress-bar";
    const fill = document.createElement("span");
    fill.style.width = `${clamped}%`;
    bar.append(fill);
    card.append(bar, textEl("small", `${clamped.toFixed(1)}%`, "progress-label"));
  }
  return card;
}

function svgEl(tag) {
  return document.createElementNS("http://www.w3.org/2000/svg", tag);
}

function createChartHead(title, subtitle, series) {
  const head = document.createElement("div");
  head.className = "chart-head";
  const copy = document.createElement("div");
  copy.append(textEl("h3", title), textEl("p", subtitle));
  const legend = document.createElement("div");
  legend.className = "chart-legend";
  for (const item of series) {
    const node = document.createElement("span");
    node.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = item.color;
    node.append(swatch, document.createTextNode(item.label));
    legend.append(node);
  }
  head.append(copy, legend);
  return head;
}

function createLineChart(title, subtitle, rows, series, unit = "", options = {}) {
  const validSeries = series.map((item) => ({ ...item, values: rows.map((row) => toNumberOrNull(row[item.key])) })).filter((item) => item.values.some((value) => value !== null));
  if (!validSeries.length) return createMetricCard(title, "暂无可绘制数据。", "wide");
  const width = 720;
  const height = 280;
  const margin = { left: 50, right: 24, top: 24, bottom: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const allValues = validSeries.flatMap((item) => item.values).filter((value) => value !== null);
  const yMax = options.yMax || Math.max(...allValues, 1);
  const x = (index) => margin.left + (rows.length === 1 ? plotWidth / 2 : (index / (rows.length - 1)) * plotWidth);
  const y = (value) => margin.top + plotHeight - (value / yMax) * plotHeight;

  const card = document.createElement("article");
  card.className = "chart-card wide";
  card.append(createChartHead(title, subtitle, validSeries));
  const svg = svgEl("svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.classList.add("chart-svg");

  for (let i = 0; i <= 4; i += 1) {
    const yy = margin.top + (plotHeight / 4) * i;
    const line = svgEl("line");
    line.setAttribute("x1", margin.left);
    line.setAttribute("x2", width - margin.right);
    line.setAttribute("y1", yy);
    line.setAttribute("y2", yy);
    line.classList.add("chart-grid-line");
    svg.append(line);
    const label = svgEl("text");
    label.setAttribute("x", 8);
    label.setAttribute("y", yy + 4);
    label.classList.add("chart-label");
    label.textContent = `${Math.round(yMax - (yMax / 4) * i)}${unit}`;
    svg.append(label);
  }

  validSeries.forEach((item) => {
    const points = item.values.map((value, index) => (value === null ? null : [x(index), y(value)])).filter(Boolean);
    if (points.length > 1) {
      const path = svgEl("path");
      path.setAttribute("d", points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0]},${point[1]}`).join(" "));
      path.setAttribute("stroke", item.color);
      path.classList.add("chart-line");
      svg.append(path);
    }
    points.forEach((point) => {
      const dot = svgEl("circle");
      dot.setAttribute("cx", point[0]);
      dot.setAttribute("cy", point[1]);
      dot.setAttribute("r", 4);
      dot.setAttribute("fill", item.color);
      dot.classList.add("chart-point");
      svg.append(dot);
    });
  });

  rows.forEach((row, index) => {
    const label = svgEl("text");
    label.setAttribute("x", x(index));
    label.setAttribute("y", height - 14);
    label.setAttribute("text-anchor", "middle");
    label.classList.add("chart-label");
    label.textContent = row.label;
    svg.append(label);
  });
  card.append(svg);
  return card;
}

function createBarChart(title, subtitle, data, unit = "", extraClass = "") {
  const items = data.slice(0, 16);
  const max = Math.max(...items.map((item) => item.value), 1);
  const card = document.createElement("article");
  card.className = `chart-card ${extraClass}`.trim();
  card.append(createChartHead(title, subtitle, [{ label: unit || "score", color: "#62d6ff" }]));
  const list = document.createElement("div");
  list.className = "bar-list";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "bar-row";
    const label = textEl("span", item.label);
    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("span");
    fill.style.width = `${Math.max(2, (item.value / max) * 100)}%`;
    track.append(fill);
    const value = textEl("strong", `${item.value.toFixed(1)}${unit}`);
    row.append(label, track, value);
    list.append(row);
  }
  card.append(list);
  return card;
}

function updateScheduleMode() {
  const once = elements.scheduleMode.value === "once";
  elements.scheduleDate.disabled = !once;
  elements.scheduleInterval.disabled = once;
  if (once && !elements.scheduleDate.value) elements.scheduleDate.value = localDateString(new Date(Date.now() + 24 * 3600 * 1000));
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    refreshActiveTab();
    loadSystemStatus();
  }, 5000);
}

async function init() {
  elements.tabButtons.forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  elements.refreshModels.addEventListener("click", loadModels);
  elements.refreshCurrentTab.addEventListener("click", refreshActiveTab);
  elements.globalModelSelect.addEventListener("change", () => setNotice(`当前模型：${selectedModelId() || "未选择"}`));
  elements.startBasic.addEventListener("click", startBasicTask);
  elements.refreshBasic.addEventListener("click", loadBasicTasks);
  elements.startStress.addEventListener("click", startStressTask);
  elements.refreshStress.addEventListener("click", loadStressTasks);
  elements.startIntelligence.addEventListener("click", startIntelligenceTask);
  elements.refreshIntelligence.addEventListener("click", loadIntelligenceTasks);
  elements.intelligenceCustomEnabled.addEventListener("change", updateDatasetPickerState);
  elements.startFullSuite.addEventListener("click", startFullSuite);
  elements.startQuickSuite.addEventListener("click", startQuickSuite);
  elements.refreshSuites.addEventListener("click", loadSuites);
  elements.scheduleMode.addEventListener("change", updateScheduleMode);
  elements.createSchedule.addEventListener("click", createSchedule);

  updateScheduleMode();
  await Promise.allSettled([loadModels(), loadSystemStatus(), loadDatasets(), loadSchedules(), loadSuites()]);
  await Promise.allSettled([loadBasicTasks(), loadStressTasks(), loadIntelligenceTasks()]);
  startPolling();
}

init();
