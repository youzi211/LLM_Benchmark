<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useModelsStore } from "@/stores/models";
import PageHero from "@/components/layouts/PageHero.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import FilterChips from "@/components/common/FilterChips.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import EvaluationWorkspace from "@/components/evaluation/EvaluationWorkspace.vue";
import { useRoute, useRouter } from "vue-router";
import { useToast } from "@/composables/useToast";
import { ArrowDown, Document, Download, Plus, Refresh, Search, VideoPlay } from "@element-plus/icons-vue";
import type { TableInstance } from "element-plus";
import { formatEvaluationDuration, modelDisplayName, progressPercentOf } from "@/evaluation/presentation";
import {
  buildStressGroups,
  formatStressLoad,
  runsOfTask as runsOf,
  stressMetricValue,
  stressRatePercent,
  stressGroupKey as groupKey,
  stressStatusLabel,
} from "@/stress/stressView";
import { shouldShowTaskListEmpty, taskById } from "@/utils/taskListState";
import { taskIdFromQuery } from "@/utils/taskCenter";
import {
  cancelStressTask,
  fetchStressDatasets,
  finalStatus,
  formatDate,
  getStressProgress,
  getStressTask,
  listStressArtifacts,
  listStressTasks,
  parseIntegerList,
  runStress,
  stressArtifactUrl,
  stressRawResultUrl,
  toNumber,
  type StressDatasetMeta,
  type StressArtifact,
  type TaskLike,
} from "@/api/evaluations";

const EChart = defineAsyncComponent(() => import("@/components/EChart.vue"));
const store = useModelsStore();
const loading = ref(true);
const refreshing = ref(false);
const listError = ref("");
const submitting = ref(false);
const configurationVisible = ref(false);
const resultTab = ref("charts");
const taskTable = ref<TableInstance>();
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
const groupByConfig = ref(true);
const chartTab = ref("requests");
const selectedGroupKey = ref<string | null>(null);
let refreshTimer: number | undefined;
let activeReload: Promise<void> | null = null;
let selectionVersion = 0;
const custom = ref(false);
const datasetsLoading = ref(false);
const datasetsError = ref("");
const stressDatasets = ref<Record<string, StressDatasetMeta>>({});
const defaultStressDataset = ref("");
const selectedDataset = ref<string>("");
const advancedOpen = ref(false);
const artifactsLoading = ref(false);
const artifacts = ref<StressArtifact[]>([]);
const form = ref({
  mode: "closed", parallel: "1,5,10,20", number: "10,50,100,200", rate: "",
  stream: "", dataset: "", dataset_path: "", data_source: "", min_prompt_length: "",
  max_prompt_length: "", min_tokens: "", max_tokens: "", tokenizer_path: "", prefix_length: "",
  warmup_num: "", duration: "", multi_turn: false, min_turns: "", max_turns: "",
  connect_timeout: "", read_timeout: "", total_timeout: "", temperature: "", top_p: "", top_k: "",
  frequency_penalty: "", repetition_penalty: "", seed: "", n_choices: "", logprobs: "", tokenize_prompt: false,
  stop: "", dataset_args: "", extra_args: "",
});

const datasetList = computed(() => Object.values(stressDatasets.value).sort((a, b) => Number(b.is_default) - Number(a.is_default)));
const selectedDatasetMeta = computed(() => stressDatasets.value[selectedDataset.value]);
const selectedDatasetScene = computed(() => {
  const name = selectedDataset.value.toLowerCase();
  if (name.includes("multi_turn")) return "多轮对话";
  if (name.includes("long") || name.includes("kontext")) return "长上下文";
  return "短对话 / 吞吐基线";
});
const normalizedResult = computed<any>(() => selected.value?.normalized_result || null);
const progressDetail = computed<any>(() => selected.value?.progress_detail || null);
const selectedProgress = computed(() => progressPercentOf(progressDetail.value));
const resultSummary = computed<Record<string, unknown>>(() => normalizedResult.value?.summary || {});
const selectedConfig = computed<Record<string, unknown>>(() =>
  (selected.value?.request_config as Record<string, unknown> | undefined) || {},
);
const groupMembers = computed(() => {
  if (!selectedGroupKey.value) return [];
  return tasks.value
    .filter((task) => groupKey(task) === selectedGroupKey.value)
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
});
const totals = computed(() => runsOf(selected.value).reduce((acc: any, run: any) => {
  acc.total += Number(run.total || 0);
  acc.success += Number(run.success || 0);
  acc.failed += Number(run.failed || 0);
  return acc;
}, { total: 0, success: 0, failed: 0 }));
const progressSuccess = computed(() => progressDetail.value?.success_requests ?? (runsOf(selected.value).length ? totals.value.success : "—"));
const progressFailed = computed(() => progressDetail.value?.failed_requests ?? (runsOf(selected.value).length ? totals.value.failed : "—"));

const metricFormatter = new Intl.NumberFormat("zh-CN", { maximumSignificantDigits: 5 });
function formatMetric(value: unknown) {
  const number = stressMetricValue(value);
  return number === undefined ? "—" : metricFormatter.format(number);
}

function modelName(id?: string) { return modelDisplayName(id, store.models); }

const requestThroughputOption = computed(() => makeLineOption("请求吞吐", "req/s", runsOf(selected.value), [
  ["request_throughput", "请求吞吐"],
]));
const tokenThroughputOption = computed(() => makeLineOption("Token 吞吐", "tok/s", runsOf(selected.value), [
  ["output_throughput", "输出吞吐"],
  ["total_throughput", "总吞吐"],
]));
const latencyOption = computed(() => makeLineOption("延迟", "s", runsOf(selected.value), [
  ["avg_latency_seconds", "平均"],
  ["p95_latency_seconds", "P95"],
  ["p99_latency_seconds", "P99"],
]));
const successOption = computed(() => makeLineOption(
  "成功率",
  "%",
  runsOf(selected.value).map((run) => ({ ...run, success_rate_percent: stressRatePercent(run.success_rate) })),
  [["success_rate_percent", "成功率"]],
));

function makeLineOption(title: string, unit: string, rows: any[], series: string[][]) {
  const labels = rows.map((run, index) => {
    const label = formatStressLoad(run, selectedConfig.value).axisLabel;
    return label === "—" ? `#${index + 1}` : label;
  });
  return {
    title: { text: title, show: false },
    tooltip: { trigger: "axis" },
    legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 8, itemGap: 20 },
    grid: { left: 12, right: 24, top: 48, bottom: 12, containLabel: true },
    xAxis: { type: "category", data: labels },
    yAxis: { type: "value", name: unit },
    series: series.map(([key, name]) => ({
      name,
      type: "line",
      smooth: false,
      symbolSize: 7,
      lineStyle: { width: 2 },
      data: rows.map((run) => stressMetricValue(run[key]) ?? null),
    })),
  };
}

function formatTaskError(error: unknown) {
  if (error == null || error === "") return "—";
  if (typeof error === "string") return error;
  return JSON.stringify(error);
}

async function loadDatasets() {
  datasetsLoading.value = true;
  try {
    const result = await fetchStressDatasets();
    stressDatasets.value = result.datasets;
    datasetsError.value = "";
    defaultStressDataset.value = result.default_dataset;
    if (!selectedDataset.value && result.default_dataset) {
      selectedDataset.value = result.default_dataset;
      form.value.dataset = result.default_dataset;
    }
  } catch (err) {
    datasetsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    datasetsLoading.value = false;
  }
}

// 运行中的分组只认组内任务，避免列表刷新后 group_key 重复或消失导致选中错位。
function resolveGroupSelection() {
  const key = selectedGroupKey.value;
  const current = selected.value as any;
  const still = groupedTasks.value.find((task: any) => task.group_key === key);
  if (!still) { selectedGroupKey.value = null; selected.value = null; return; }
  selected.value = current?.progress_detail ? { ...still, progress_detail: current.progress_detail } : still;
}

let detailRequests = 0;
let progressRequests = 0;
// 选中任务在跑时只拉详情拿 progress_detail；用计数防止慢请求互相覆盖。
async function refreshSelected() {
  const selectedAny = selected.value as any;
  if (!selectedAny || selectedAny.grouped || finalStatus(selectedAny.status)) return;
  const request = ++detailRequests;
  const selection = selectionVersion;
  try {
    const detail = await getStressTask(String(selectedAny.task_id), false);
    if (request === detailRequests && selection === selectionVersion && !selectedGroupKey.value) {
      selected.value = detail;
    }
  } catch { /* 单次轮询失败保持旧数据 */ }
}

async function refreshGroupProgress() {
  const selectedAny = selected.value as any;
  if (!selectedAny?.grouped || finalStatus(selectedAny.status)) return;
  const selection = selectionVersion;
  const groupKeyAtRequest = selectedGroupKey.value;
  const running = tasks.value.find((task) => groupKey(task) === selectedGroupKey.value && !finalStatus(task.status));
  if (!running) return;
  const request = ++progressRequests;
  try {
    const progress = await getStressProgress(running.task_id);
    if (
      request === progressRequests
      && selection === selectionVersion
      && groupKeyAtRequest === selectedGroupKey.value
      && selected.value
    ) {
      selected.value = { ...(selected.value as any), progress_detail: progress };
    }
  } catch { /* 单次轮询失败保持旧数据 */ }
}

function reload(options: { background?: boolean } = {}): Promise<void> {
  if (activeReload) return activeReload;
  if (!options.background) refreshing.value = true;
  activeReload = (async () => {
    try {
      tasks.value = await listStressTasks();
      listError.value = "";
      if (selectedGroupKey.value) {
        resolveGroupSelection();
        await refreshGroupProgress();
      } else if (selected.value) {
        // 选中的是单个任务：列表已刷新，只补详情，不再重拉 artifacts。
        await refreshSelected();
      }
    } catch (err) {
      listError.value = err instanceof Error ? err.message : String(err);
      if (!options.background) ElMessage.error("加载压测任务失败: " + listError.value);
    } finally {
      loading.value = false;
      if (!options.background) refreshing.value = false;
    }
  })().finally(() => {
    activeReload = null;
  });
  return activeReload;
}

function buildPayload() {
  if (!store.currentId) throw new Error("请先选择当前模型");
  const payload: Record<string, unknown> = { model_id: store.currentId };
  if (!custom.value) return payload;
  const number = parseIntegerList(form.value.number);
  const parallel = parseIntegerList(form.value.parallel);
  const rates = parseNumberList(form.value.rate);
  payload.open_loop = form.value.mode === "open";
  if (form.value.mode === "closed") {
    if (parallel && number && parallel.length !== number.length) throw new Error("闭环模式下 parallel 与 number 必须一一对应。");
    if (parallel) payload.parallel = parallel;
  } else {
    if (!rates?.length) throw new Error("开环模式必须填写 rate（请求/秒）。");
    if (number && rates.length !== number.length) throw new Error("开环模式下 rate 与 number 必须一一对应。");
    payload.rate = rates.length === 1 ? rates[0] : rates;
  }
  if (number) payload.number = number;
  if (form.value.stream) payload.stream = form.value.stream === "true";
  if (form.value.dataset) payload.dataset = form.value.dataset;
  if (form.value.dataset_path) payload.dataset_path = form.value.dataset_path;
  if (form.value.multi_turn || selectedDataset.value.includes("multi_turn")) payload.multi_turn = true;
  for (const key of [
    "min_prompt_length", "max_prompt_length", "min_tokens", "max_tokens", "prefix_length", "warmup_num",
    "duration", "min_turns", "max_turns", "connect_timeout", "read_timeout", "total_timeout", "temperature",
    "top_p", "top_k", "frequency_penalty", "repetition_penalty", "seed", "n_choices",
  ] as const) {
    const value = toNumber(form.value[key]);
    if (value !== undefined) payload[key] = value;
  }
  for (const key of ["dataset_path", "data_source", "tokenizer_path"] as const) {
    if (form.value[key].trim()) payload[key] = form.value[key].trim();
  }
  if (form.value.logprobs) payload.logprobs = form.value.logprobs === "true";
  if (form.value.tokenize_prompt) payload.tokenize_prompt = true;
  if (form.value.stop.trim()) payload.stop = form.value.stop.split(/[，,\n]+/).map((v) => v.trim()).filter(Boolean);
  for (const key of ["dataset_args", "extra_args"] as const) {
    if (form.value[key].trim()) payload[key] = parseJsonObject(form.value[key], key);
  }
  return payload;
}

function parseNumberList(raw: string): number[] | undefined {
  const text = raw.trim();
  if (!text) return undefined;
  const values = text.split(/[，,\s]+/).filter(Boolean).map(Number);
  if (values.some((value) => !Number.isFinite(value) || value <= 0)) throw new Error(`rate 只能包含正数：${text}`);
  return values;
}

function parseJsonObject(raw: string, label: string) {
  try {
    const value = JSON.parse(raw);
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error();
    return value;
  } catch {
    throw new Error(`${label} 必须是合法 JSON 对象。`);
  }
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

async function submit() {
  submitting.value = true;
  try {
    const task = await runStress(buildPayload());
    configurationVisible.value = false;
    ElMessage.success(`已启动压测：${task.task_id}`);
    await reload();
    await selectTask(task.task_id, false);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

const route = useRoute();
const router = useRouter();
const toast = useToast();

const statusFilter = ref<string>("all");
const queryText = ref<string>("");
const selectedIds = ref<string[]>([]);
const hasFilters = computed(() => Boolean(queryText.value.trim()) || statusFilter.value !== "all");
const autoUpdating = computed(() => tasks.value.some((task) => !finalStatus(task.status)));
function clearSelection() { taskTable.value?.clearSelection(); selectedIds.value = []; }
function emptyAction() {
  if (hasFilters.value) { queryText.value = ""; statusFilter.value = "all"; }
  else configurationVisible.value = true;
}

const groupedTasks = computed(() => buildStressGroups(tasks.value));

const displayTasks = computed(() => groupByConfig.value ? groupedTasks.value : tasks.value);

const statusFilterOptions = computed(() => {
  const t = displayTasks.value;
  return [
    { value: "all",       label: "全部",     count: t.length },
    { value: "running",   label: "运行中",   count: t.filter(x => ["running", "pending", "queued"].includes(String(x.status))).length },
    { value: "completed", label: "已完成",   count: t.filter(x => x.status === "completed").length },
    { value: "partial",   label: "部分失败", count: t.filter(x => x.status === "partial").length },
    { value: "failed",    label: "失败",     count: t.filter(x => ["failed", "error", "interrupted"].includes(String(x.status))).length },
  ];
});

const filteredTasks = computed(() => {
  let out = displayTasks.value;
  if (statusFilter.value !== "all") {
    if (statusFilter.value === "failed") {
      out = out.filter(t => ["failed", "error", "interrupted"].includes(String(t.status)));
    } else if (statusFilter.value === "running") {
      out = out.filter(t => ["running", "pending", "queued"].includes(String(t.status)));
    } else {
      out = out.filter(t => t.status === statusFilter.value);
    }
  }
  if (queryText.value.trim()) {
    const q = queryText.value.toLowerCase();
    out = out.filter(t => String((t as any).group_label || t.task_id).toLowerCase().includes(q) || String(t.model_id).toLowerCase().includes(q));
  }
  return out;
});

function goCompare() {
  if (selectedIds.value.length < 2) {
    toast.warning("至少选 2 个任务才能对比");
    return;
  }
  router.push({ path: "/compare", query: { ids: selectedIds.value.join(","), types: selectedIds.value.map(() => "stress").join(",") } });
}

const rerunning = ref(false);
async function bulkRerun() {
  const rows = tasks.value.filter((t) => selectedIds.value.includes(t.task_id));
  if (!rows.length) return;
  rerunning.value = true;
  let ok = 0;
  let failed = 0;
  try {
    for (const row of rows as any[]) {
      try {
        // request_config 已去掉 api_key；model/url/api 为多余字段，后端 Pydantic 默认忽略。
        await runStress({ model_id: row.model_id, ...(row.request_config || {}) });
        ok += 1;
      } catch (err) {
        failed += 1;
        ElMessage.error(`重跑失败 ${row.task_id}: ` + (err instanceof Error ? err.message : String(err)));
      }
    }
  } finally {
    rerunning.value = false;
    clearSelection();
    await reload();
  }
  if (ok && !failed) ElMessage.success(`已重新运行 ${ok} 个压测任务`);
}
async function selectTask(taskId: string, refreshList = false) {
  const selection = ++selectionVersion;
  selectedGroupKey.value = null;
  if (refreshList) await reload({ background: true });
  if (selection !== selectionVersion) return;
  const cached = taskById(tasks.value, taskId);
  selected.value = cached;
  artifacts.value = [];
  artifactsLoading.value = false;
  let detail: TaskLike;
  try {
    detail = await getStressTask(taskId, finalStatus(cached?.status));
  } catch (err) {
    if (selection === selectionVersion) {
      ElMessage.error("加载压测详情失败: " + (err instanceof Error ? err.message : String(err)));
    }
    return;
  }
  if (selection !== selectionVersion) return;
  selected.value = detail;
  if (detail.raw_output_dir) {
    artifactsLoading.value = true;
    try {
      const loadedArtifacts = await listStressArtifacts(taskId);
      if (selection === selectionVersion) artifacts.value = loadedArtifacts;
    } catch {
      if (selection === selectionVersion) artifacts.value = [];
    } finally {
      if (selection === selectionVersion) artifactsLoading.value = false;
    }
  }
}

async function selectTaskAndSync(taskId: string) {
  groupByConfig.value = false;
  await selectTask(taskId);
  if (selected.value?.task_id !== taskId || taskIdFromQuery(route.query.task_id) === taskId) return;
  await router.replace({ query: { ...route.query, task_id: taskId } });
}

async function selectRequestedTask() {
  const taskId = taskIdFromQuery(route.query.task_id);
  if (!taskId || selected.value?.task_id === taskId) return;
  groupByConfig.value = false;
  await selectTask(taskId);
}

function selectGroup(task: TaskLike) {
  selectionVersion++;
  selectedGroupKey.value = String((task as any).group_key);
  selected.value = task;
  artifacts.value = [];
  artifactsLoading.value = false;
}

async function cancelTask(taskId: string) {
  try {
    await ElMessageBox.confirm(`确认取消压测任务 ${taskId}？`, "取消确认", { type: "warning" });
    await cancelStressTask(taskId);
    ElMessage.success("已取消");
    await reload();
    await selectTask(taskId, false);
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error("取消压测失败: " + (err instanceof Error ? err.message : String(err)));
    }
  }
}

function pickDataset(name: string) {
  selectedDataset.value = name;
  form.value.dataset = name;
}

onMounted(async () => {
  await Promise.allSettled([loadDatasets(), reload()]);
  await selectRequestedTask();
  refreshTimer = window.setInterval(() => {
    if (document.visibilityState !== "visible" || activeReload) return;
    if (tasks.value.some((task) => !finalStatus(task.status)) || (selected.value && !finalStatus(selected.value.status))) {
      reload({ background: true }); // reload 内部已按分组/单任务分别刷新进度或详情
    }
  }, 5000);
});

onUnmounted(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
});

watch(() => route.query.task_id, () => { void selectRequestedTask(); });
</script>

<template>
  <PageHero
    eyebrow="STRESS TEST"
    title="压测评测"
    description="观察不同负载下的吞吐、响应延迟与稳定性，保留每个档位的测试证据。"
  >
    <template #actions>
      <el-button :icon="Refresh" :loading="refreshing" @click="reload()">刷新数据</el-button>
      <el-button type="primary" :icon="Plus" @click="configurationVisible = true">新建压测评测</el-button>
    </template>
  </PageHero>
  <EvaluationWorkspace
    v-model:configuration-visible="configurationVisible" lane="stress" :task-count="displayTasks.length"
    :count-unit="groupByConfig ? '个方案' : '条任务'" :model-name="store.currentModel?.name || store.currentId || '未选择模型'"
    :auto-updating="autoUpdating" detail-title="压测结果" detail-description="吞吐、延迟与档位明细，基于真实请求结果展示"
    configuration-title="新建压测评测" configuration-description="可直接使用服务端默认参数，或按并发 / 请求速率自定义负载。" drawer-size="min(760px, 100vw)"
  >
    <template #configuration>
      <el-form label-position="top" class="lb-eval-form">
        <el-form-item><el-switch v-model="custom" aria-label="自定义压测参数" active-text="自定义压测参数" inactive-text="使用默认参数" /></el-form-item>
        <div v-if="!custom" class="lb-eval-defaults"><strong>使用服务端默认方案</strong><p>自动采用默认负载档位、请求数及生成配置，无需逐项填写。默认数据集：{{ defaultStressDataset || '以服务端配置为准' }}。</p><p>完成后可查看请求 / Token 吞吐、延迟分布与流式指标。</p></div>

        <template v-if="custom">
          <el-form-item label="负载模式">
            <el-segmented v-model="form.mode" :options="[{ label: '闭环并发', value: 'closed' }, { label: '开环速率', value: 'open' }]" />
            <p class="field-help">闭环控制同时在途请求数；开环按目标 RPS 发起请求，更适合验证限流和突发流量。</p>
          </el-form-item>
          <el-row :gutter="16">
            <el-col v-if="form.mode === 'closed'" :xs="24" :sm="12"><el-form-item label="并发档位 parallel"><el-input v-model="form.parallel" aria-label="并发档位 parallel" placeholder="1,5,10,20" /></el-form-item></el-col>
            <el-col v-else :xs="24" :sm="12"><el-form-item label="请求速率 rate (req/s)"><el-input v-model="form.rate" aria-label="请求速率 rate" placeholder="2,5,10,20" /></el-form-item></el-col>
            <el-col :xs="24" :sm="12"><el-form-item label="每档请求数 number"><el-input v-model="form.number" aria-label="每档请求数 number" placeholder="10,50,100,200" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="响应方式 stream">
            <el-select v-model="form.stream" class="full-width"><el-option label="默认（流式）" value="" /><el-option label="流式响应" value="true" /><el-option label="非流式响应" value="false" /></el-select>
            <p class="field-help">开启后按 SSE 流逐块接收，可测 TTFT、TPOT 和 ITL；关闭后只统计完整响应延迟。</p>
          </el-form-item>

          <div class="lb-eval-form__section"><h3>测试数据</h3><p>选择语料和输入 / 输出长度，保证不同任务可重复对比。</p></div>
          <el-alert v-if="datasetsError" class="lb-eval-alert" type="warning" :closable="false" :title="`数据集列表加载失败：${datasetsError}`"><el-button link type="primary" @click="loadDatasets">重新加载</el-button></el-alert>
          <el-form-item label="测试数据集">
            <el-select v-model="selectedDataset" :loading="datasetsLoading" aria-label="压测数据集" placeholder="使用服务端默认数据集" @change="pickDataset">
              <el-option v-for="ds in datasetList" :key="ds.name" :label="ds.pretty_name || ds.name" :value="ds.name"><span>{{ ds.pretty_name || ds.name }}</span><small class="lb-stress-option-id">{{ ds.name }}</small></el-option>
            </el-select>
          </el-form-item>
          <div v-if="selectedDatasetMeta" class="lb-eval-defaults"><strong>{{ selectedDatasetMeta.pretty_name || selectedDataset }} · {{ selectedDatasetScene }}</strong><p>{{ selectedDatasetMeta.description || '使用该数据集执行压测。' }}</p><div class="tag-row"><el-tag v-if="selectedDatasetMeta.available_local" size="small" effect="plain">本地可用</el-tag><el-tag v-for="category in selectedDatasetMeta.categories || []" :key="category" size="small" type="info" effect="plain">{{ category }}</el-tag></div></div>

          <el-row :gutter="16" class="mt">
            <el-col :xs="24" :sm="12"><el-form-item label="最小输入长度"><el-input v-model="form.min_prompt_length" placeholder="默认 0" /></el-form-item></el-col>
            <el-col :xs="24" :sm="12"><el-form-item label="最大输入长度"><el-input v-model="form.max_prompt_length" placeholder="默认 131072" /></el-form-item></el-col>
            <el-col :xs="24" :sm="12"><el-form-item label="最小输出 Token"><el-input v-model="form.min_tokens" placeholder="留空则不发送" /></el-form-item></el-col>
            <el-col :xs="24" :sm="12"><el-form-item label="最大输出 Token"><el-input v-model="form.max_tokens" placeholder="默认 512" /></el-form-item></el-col>
          </el-row>

          <button type="button" class="advanced-toggle" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
            <span>高级参数</span><el-icon :class="{ 'is-open': advancedOpen }"><ArrowDown /></el-icon>
          </button>
          <div v-show="advancedOpen" class="advanced-panel">
            <div class="lb-eval-form__section"><h3>执行与超时</h3><p>按需设置，多轮、预热与超时均保持原有服务端语义。</p></div>
            <el-switch v-model="form.multi_turn" active-text="启用多轮对话" />
            <el-row :gutter="16" class="mt">
              <el-col :xs="24" :sm="12"><el-form-item label="最少轮数"><el-input v-model="form.min_turns" /></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="最多轮数"><el-input v-model="form.max_turns" /></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="预热请求/比例"><el-input v-model="form.warmup_num" placeholder="如 10 或 0.1" /></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="单档持续时间(s)"><el-input v-model="form.duration" /></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="Tokenizer 路径"><el-input v-model="form.tokenizer_path" /></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="随机数据前缀长度"><el-input v-model="form.prefix_length" /></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="数据源"><el-select v-model="form.data_source" clearable class="full-width"><el-option label="ModelScope" value="modelscope" /><el-option label="Hugging Face" value="huggingface" /><el-option label="本地" value="local" /></el-select></el-form-item></el-col>
              <el-col :xs="24" :sm="12"><el-form-item label="本地数据集路径"><el-input v-model="form.dataset_path" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="连接超时(s)"><el-input v-model="form.connect_timeout" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="读取超时(s)"><el-input v-model="form.read_timeout" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="总超时(s)"><el-input v-model="form.total_timeout" /></el-form-item></el-col>
            </el-row>
            <div class="lb-eval-form__section"><h3>生成与采样</h3><p>留空的参数不会加入请求，继续使用服务端默认值。</p></div>
            <el-row :gutter="16">
              <el-col :xs="24" :sm="8"><el-form-item label="temperature"><el-input v-model="form.temperature" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="top_p"><el-input v-model="form.top_p" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="top_k"><el-input v-model="form.top_k" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="frequency_penalty"><el-input v-model="form.frequency_penalty" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="repetition_penalty"><el-input v-model="form.repetition_penalty" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="seed"><el-input v-model="form.seed" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="n_choices"><el-input v-model="form.n_choices" /></el-form-item></el-col>
              <el-col :xs="24" :sm="8"><el-form-item label="logprobs"><el-select v-model="form.logprobs" clearable class="full-width"><el-option label="true" value="true" /><el-option label="false" value="false" /></el-select></el-form-item></el-col>
            </el-row>
            <el-switch v-model="form.tokenize_prompt" active-text="客户端 tokenize prompt" />
            <el-form-item label="停止词（逗号或换行分隔）"><el-input v-model="form.stop" type="textarea" :rows="2" /></el-form-item>
            <el-form-item label="dataset_args (JSON)"><el-input v-model="form.dataset_args" type="textarea" :rows="3" placeholder='{"subset": "..."}' /></el-form-item>
            <el-form-item label="extra_args (JSON)"><el-input v-model="form.extra_args" type="textarea" :rows="3" placeholder='{"ignore_eos": true}' /></el-form-item>
          </div>
        </template>

      </el-form>
    </template>
    <template #configuration-footer><el-button @click="configurationVisible = false">返回工作台</el-button><el-button type="primary" :icon="VideoPlay" :loading="submitting" :disabled="!store.currentId" @click="submit">开始压测评测</el-button></template>

    <template #list>
      <div class="lb-eval-toolbar__mode"><span>记录视图</span><el-switch v-model="groupByConfig" aria-label="按方案归组" active-text="按方案归组" inactive-text="逐条任务" @change="clearSelection" /></div>
      <div class="lb-eval-toolbar">
        <el-input v-model="queryText" :placeholder="groupByConfig ? '搜索方案 / 模型' : '搜索任务 ID / 模型'" aria-label="搜索压测任务" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button text circle :icon="Refresh" :loading="refreshing" aria-label="刷新压测任务" @click="reload()" />
      </div>
      <el-alert v-if="listError" class="lb-eval-alert" type="error" :closable="false" show-icon :title="`任务列表加载失败：${listError}`" />
      <div class="lb-eval-filters">
        <FilterChips v-model="statusFilter" :options="statusFilterOptions" :show-count="true" size="small" />
      </div>
      <div v-if="selectedIds.length && !groupByConfig" class="lb-eval-bulk">
        <span>已选 {{ selectedIds.length }} 个任务</span>
        <el-button size="small" type="primary" plain :loading="rerunning" @click="bulkRerun">重新运行</el-button>
        <el-button size="small" :disabled="selectedIds.length < 2" @click="goCompare">对比任务</el-button>
        <el-button size="small" text @click="clearSelection">取消选择</el-button>
      </div>
      <el-table ref="taskTable" v-loading="loading" :data="filteredTasks" :max-height="520" :row-key="(r: any) => r.task_id" :current-row-key="selected?.task_id" highlight-current-row
        @selection-change="(rows: TaskLike[]) => (selectedIds = rows.map(r => r.task_id))"
        @row-click="(row: any, column) => column?.type !== 'selection' && (row.grouped ? selectGroup(row) : selectTaskAndSync(row.task_id))"
        empty-text="">
        <el-table-column v-if="!groupByConfig" type="selection" width="36" :reserve-selection="true" />
        <el-table-column prop="task_id" label="任务 / 方案" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <button type="button" class="lb-eval-task-link" :aria-label="row.grouped ? `查看方案 ${row.group_label}` : `查看任务 ${row.task_id}`" @click.stop="row.grouped ? selectGroup(row as TaskLike) : selectTaskAndSync(row.task_id)"><strong>{{ row.grouped ? row.group_label : modelName(row.model_id) }}</strong><small>{{ row.grouped ? `${modelName(row.model_id)} · ${row.group_count} 条记录 · ${runsOf(row as any).length} 个档位` : row.task_id }}</small></button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="84">
          <template #default="{ row }"><StatusTag :status="row.status" :label="stressStatusLabel(row.status, row.grouped)" compact /></template>
        </el-table-column>
        <el-table-column label="耗时" width="76">
          <template #default="{ row }"><span class="lb-eval-numeric" :title="row.duration_ms != null ? `${row.duration_ms} ms` : undefined">{{ formatEvaluationDuration(row.duration_ms) }}</span></template>
        </el-table-column>
        <template #empty><EmptyState
        v-if="shouldShowTaskListEmpty(loading, listError, filteredTasks.length)"
        :title="queryText || statusFilter !== 'all' ? '无匹配任务' : '暂无压测任务'"
        :description="hasFilters ? '试着清空筛选条件。' : '新建压测方案，比较不同负载的结果。'"
        :variant="queryText ? 'search' : 'list'"
        :action-label="hasFilters ? '清空筛选' : '新建压测评测'"
        @action="emptyAction"
      /></template>
      </el-table>
    </template>

    <template #detail-actions><StatusTag v-if="selected" :status="selected.status ?? 'pending'" :label="stressStatusLabel(selected.status, Boolean((selected as any).grouped))" /><el-button v-if="selected && !(selected as any).grouped && !finalStatus(selected.status)" size="small" type="danger" plain @click="cancelTask(selected.task_id)">取消任务</el-button></template>
    <template #detail>
      <EmptyState
        v-if="!selected"
        title="尚未选择任务"
        description="从左侧任务列表选择一个压测任务查看吞吐、延迟与档位对比。"
        variant="list"
      />
      <template v-else>
        <div class="lb-eval-task-title"><div><strong>{{ (selected as any).grouped ? (selected as any).group_label : modelName(selected.model_id) }}</strong><code>{{ (selected as any).grouped ? (selected as any).group_config : selected.task_id }}</code></div><el-button v-if="(selected as any).grouped" size="small" @click="resultTab = 'artifacts'">查看组内任务</el-button></div>
        <div v-if="!(selected as any).grouped && (progressDetail || !finalStatus(selected.status))" class="lb-eval-progress" aria-live="polite">
          <div class="lb-eval-progress__head">
            <strong>{{ selected.progress || '正在准备压测' }}</strong>
            <span>{{ selectedProgress === undefined ? '等待进度' : selectedProgress.toFixed(1) + '%' }}</span>
          </div>
          <el-progress v-if="selectedProgress !== undefined" :percentage="selectedProgress" :stroke-width="5" :show-text="false" />
          <div v-else class="lb-eval-progress__waiting"></div>
          <div class="lb-eval-progress__stats">
            <span>当前档位 {{ progressDetail?.current_run ?? '—' }}/{{ progressDetail?.total_runs ?? '—' }} · {{ progressDetail?.current_run_completed ?? '—' }}/{{ progressDetail?.current_run_total ?? '—' }}</span>
            <span>已处理 {{ progressDetail?.completed_requests ?? '—' }}</span>
            <span>总请求 {{ progressDetail?.total_requests ?? '—' }}</span>
            <span>成功 {{ progressSuccess }}</span>
            <span>失败 {{ progressFailed }}</span>
          </div>
        </div>
        <div v-if="selected.report_path || selected.raw_result" class="lb-eval-result-actions">
          <el-link v-if="selected.report_path" type="primary" :icon="Document" :href="`/api/stress/reports/${selected.task_id}`" target="_blank">打开 Markdown 报告</el-link>
          <el-link v-if="selected.raw_result" type="primary" :href="stressRawResultUrl(selected.task_id)" target="_blank"><el-icon><Download /></el-icon>原始结果 JSON</el-link>
        </div>
        <el-alert v-if="selected.error" class="lb-eval-alert" type="error" :closable="false" title="压测执行异常"><pre class="lb-eval-error">{{ JSON.stringify(selected.error, null, 2) }}</pre></el-alert>
        <div v-if="runsOf(selected).length" class="lb-eval-stats">
          <div class="lb-eval-stat"><span>最高请求吞吐</span><strong>{{ formatMetric(resultSummary.best_req_throughput) }}</strong><small>req/s</small></div>
          <div class="lb-eval-stat"><span>最高输出吞吐</span><strong>{{ formatMetric(resultSummary.best_output_throughput) }}</strong><small>tok/s</small></div>
          <div class="lb-eval-stat"><span>成功请求</span><strong>{{ totals.success }}</strong><small>/ {{ totals.total }} 次请求</small></div>
          <div class="lb-eval-stat" :class="{ 'lb-eval-stat--danger': totals.failed > 0 }"><span>失败请求</span><strong>{{ totals.failed }}</strong><small>请求失败数</small></div>
        </div>
        <el-alert v-if="totals.failed > 0" class="lb-eval-alert" type="warning" :closable="false" show-icon
          :title="`已有 ${totals.failed} 个请求失败，请检查负载档位和原始产物`" />
        <el-tabs v-model="resultTab" class="lb-eval-tabs">
          <el-tab-pane label="性能图表" name="charts">
            <template v-if="runsOf(selected).length">
              <div class="lb-eval-chart-switch"><el-segmented v-model="chartTab" :options="[{ label: '请求吞吐', value: 'requests' }, { label: 'Token 吞吐', value: 'tokens' }, { label: '延迟', value: 'latency' }, { label: '成功率', value: 'success' }]" /></div>
              <EChart v-if="resultTab === 'charts' && chartTab === 'requests'" :option="requestThroughputOption" height="340px" />
              <EChart v-if="resultTab === 'charts' && chartTab === 'tokens'" :option="tokenThroughputOption" height="340px" />
              <EChart v-if="resultTab === 'charts' && chartTab === 'latency'" :option="latencyOption" height="340px" />
              <EChart v-if="resultTab === 'charts' && chartTab === 'success'" :option="successOption" height="340px" />
            </template>
            <EmptyState v-else :title="finalStatus(selected.status) ? '暂无档位结果' : '等待压测结果'" description="每个档位完成后，吞吐与延迟数据会展示在这里。" />
          </el-tab-pane>
          <el-tab-pane label="档位明细" name="runs">
            <p class="lb-eval-note">并发与请求速率分别展示；无效或缺失指标标为“—”。宽表可横向滚动。</p>
        <el-table v-if="runsOf(selected).length" :data="runsOf(selected)" border>
          <el-table-column label="负载档位" width="140"><template #default="{ row }">{{ formatStressLoad(row, selectedConfig).label }}</template></el-table-column>
          <el-table-column prop="total" label="请求" width="76" />
          <el-table-column prop="success" label="成功" width="76" />
          <el-table-column prop="failed" label="失败" width="76" />
          <el-table-column prop="request_throughput" label="RPS" width="100"><template #default="{ row }">{{ formatMetric(row.request_throughput) }}</template></el-table-column>
          <el-table-column prop="output_throughput" label="输出 tok/s" width="110"><template #default="{ row }">{{ formatMetric(row.output_throughput) }}</template></el-table-column>
          <el-table-column prop="avg_latency_seconds" label="平均延迟(s)" width="115"><template #default="{ row }">{{ formatMetric(row.avg_latency_seconds) }}</template></el-table-column>
          <el-table-column prop="p95_latency_seconds" label="P95(s)" width="90"><template #default="{ row }">{{ formatMetric(row.p95_latency_seconds) }}</template></el-table-column>
          <el-table-column prop="avg_ttft_ms" label="TTFT(ms)" width="105"><template #default="{ row }">{{ formatMetric(row.avg_ttft_ms) }}</template></el-table-column>
          <el-table-column prop="avg_tpot_ms" label="TPOT(ms)" width="105"><template #default="{ row }">{{ formatMetric(row.avg_tpot_ms) }}</template></el-table-column>
          <el-table-column prop="avg_itl_ms" label="ITL(ms)" width="95"><template #default="{ row }">{{ formatMetric(row.avg_itl_ms) }}</template></el-table-column>
          <el-table-column prop="avg_input_tokens" label="输入 Token" width="105"><template #default="{ row }">{{ formatMetric(row.avg_input_tokens) }}</template></el-table-column>
          <el-table-column prop="avg_output_tokens" label="输出 Token" width="105"><template #default="{ row }">{{ formatMetric(row.avg_output_tokens) }}</template></el-table-column>
          <el-table-column prop="avg_turns" label="平均轮数" width="95"><template #default="{ row }">{{ formatMetric(row.avg_turns) }}</template></el-table-column>
        </el-table>
            <EmptyState v-else title="暂无档位明细" description="尚未收到可展示的压测档位结果。" />
          </el-tab-pane>
          <el-tab-pane :label="(selected as any).grouped ? '组内任务' : '任务与产物'" name="artifacts">
            <dl class="lb-eval-meta">
              <div><dt>模型配置 ID</dt><dd class="lb-eval-mono">{{ selected.model_id || '—' }}</dd></div>
              <div><dt>{{ (selected as any).grouped ? '归组记录' : '任务耗时' }}</dt><dd>{{ (selected as any).grouped ? (selected as any).group_count + ' 条任务' : formatEvaluationDuration(selected.duration_ms) }}</dd></div>
              <div><dt>数据集</dt><dd>{{ selectedConfig.dataset || '服务端默认' }}</dd></div>
              <div><dt>创建时间</dt><dd>{{ formatDate(selected.created_at) }}</dd></div>
              <div v-if="!(selected as any).grouped" class="lb-eval-meta__wide"><dt>原始输出目录</dt><dd class="lb-eval-mono">{{ selected.raw_output_dir || '尚未生成' }}</dd></div>
            </dl>

        <section v-if="(selected as any).grouped" class="group-members mt" aria-labelledby="group-members-title">
          <div class="section-label">
            <span id="group-members-title">组内任务</span>
            <el-tag size="small" effect="plain">{{ groupMembers.length }} 条任务</el-tag>
          </div>
          <el-table :data="groupMembers" size="small" row-key="task_id" @row-click="(row: TaskLike) => selectTaskAndSync(row.task_id)">
            <el-table-column prop="task_id" label="任务 ID" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="105"><template #default="{ row }"><StatusTag :status="row.status" compact /></template></el-table-column>
            <el-table-column label="错误" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">{{ formatTaskError(row.error) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click.stop="selectTaskAndSync(row.task_id)">查看</el-button>
                <el-button v-if="!finalStatus(row.status)" link type="danger" @click.stop="cancelTask(row.task_id)">取消</el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <section v-if="!(selected as any).grouped" class="artifact-panel mt" aria-labelledby="artifact-title">
          <div class="section-label"><span id="artifact-title">原始产物</span><el-tag size="small" effect="plain">{{ artifacts.length }} 个文件</el-tag></div>
          <el-skeleton v-if="artifactsLoading" :rows="2" animated />
          <el-empty v-else-if="!artifacts.length" description="暂无可下载原始产物" :image-size="64" />
          <div v-else class="artifact-list">
            <a v-for="artifact in artifacts" :key="artifact.path" class="artifact-row" :href="stressArtifactUrl(selected.task_id, artifact.path)" target="_blank">
              <span><strong>{{ artifact.name }}</strong><small>{{ artifact.path }}</small></span>
              <span class="artifact-row__meta">{{ formatBytes(artifact.size_bytes) }}<el-icon><Download /></el-icon></span>
            </a>
          </div>
        </section>
          </el-tab-pane>
        </el-tabs>
      </template>
    </template>
  </EvaluationWorkspace>
</template>

<style scoped>
.field-help { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.section-label { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 24px 0 14px; font-size: 13px; font-weight: 600; }
.lb-stress-option-id { float: right; margin-left: 12px; color: var(--lb-muted); font: 10px var(--font-mono); }
.advanced-toggle:focus-visible, .artifact-row:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.advanced-toggle { display: flex; width: 100%; align-items: center; justify-content: space-between; margin-top: 16px; padding: 12px 14px; border: 1px solid var(--el-border-color); border-radius: 8px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); font-weight: 650; cursor: pointer; }
.advanced-toggle .el-icon { transition: transform .2s ease; }
.advanced-toggle .el-icon.is-open { transform: rotate(180deg); }
.advanced-panel { padding: 16px 4px 4px; }
.artifact-list { display: grid; gap: 8px; }
.artifact-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 11px 13px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; color: var(--el-text-color-primary); text-decoration: none; transition: border-color .2s, background-color .2s; }
.artifact-row:hover { border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); }
.artifact-row span:first-child { display: grid; min-width: 0; }
.artifact-row strong, .artifact-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.artifact-row small { color: var(--el-text-color-secondary); }
.artifact-row__meta { display: flex; flex: none; align-items: center; gap: 8px; color: var(--el-text-color-secondary); }
@media (max-width: 768px) { .artifact-row { align-items: flex-start; } }
@media (prefers-reduced-motion: reduce) { .advanced-toggle .el-icon, .artifact-row { transition: none; } }
</style>
