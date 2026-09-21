<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useModelsStore } from "@/stores/models";
import PageHero from "@/components/layouts/PageHero.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import FilterChips from "@/components/common/FilterChips.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import TaskTimeline from "@/components/common/TaskTimeline.vue";
import { useRouter } from "vue-router";
import { useToast } from "@/composables/useToast";
import { ArrowDown, Download, Search } from "@element-plus/icons-vue";
import EChart from "@/components/EChart.vue";
import {
  cancelStressTask,
  fetchStressDatasets,
  finalStatus,
  formatDate,
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

const store = useModelsStore();
const loading = ref(false);
const submitting = ref(false);
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
let refreshTimer: number | undefined;
const custom = ref(false);
const datasetsLoading = ref(false);
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
const resultSummary = computed<Record<string, unknown>>(() => normalizedResult.value?.summary || {});
const totals = computed(() => runsOf(selected.value).reduce((acc: any, run: any) => {
  acc.total += Number(run.total || 0);
  acc.success += Number(run.success || 0);
  acc.failed += Number(run.failed || 0);
  return acc;
}, { total: 0, success: 0, failed: 0 }));
const progressSuccess = computed(() => progressDetail.value?.success_requests ?? (runsOf(selected.value).length ? totals.value.success : "—"));
const progressFailed = computed(() => progressDetail.value?.failed_requests ?? (runsOf(selected.value).length ? totals.value.failed : "—"));

function statusType(status?: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "interrupted") return "danger";
  if (status === "running" || status === "pending") return "warning";
  return "info";
}

function runsOf(task: TaskLike | null) {
  const normalized: any = task?.normalized_result || (task?.raw_result as any)?.normalized_result;
  return Array.isArray(normalized?.runs) ? normalized.runs : [];
}

const throughputOption = computed(() => makeLineOption("吞吐", "req/s", runsOf(selected.value), [
  ["request_throughput", "请求吞吐"],
  ["output_throughput", "输出吞吐"],
  ["total_throughput", "总吞吐"],
]));
const latencyOption = computed(() => makeLineOption("延迟", "s", runsOf(selected.value), [
  ["avg_latency_seconds", "平均"],
  ["p95_latency_seconds", "P95"],
  ["p99_latency_seconds", "P99"],
]));
const successOption = computed(() => makeLineOption("成功率", "%", runsOf(selected.value).map((r: any) => ({ ...r, success_rate_percent: Number(r.success_rate) <= 1 ? Number(r.success_rate) * 100 : r.success_rate })), [["success_rate_percent", "成功率"]]));

function makeLineOption(title: string, unit: string, rows: any[], series: string[][]) {
  const labels = rows.map((r, i) => r.parallel ? `P${r.parallel}` : `#${i + 1}`);
  return {
    title: { text: title, left: "center" },
    tooltip: { trigger: "axis" },
    legend: { top: 28 },
    grid: { left: 48, right: 24, top: 72, bottom: 36 },
    xAxis: { type: "category", data: labels },
    yAxis: { type: "value", name: unit },
    series: series.map(([key, name]) => ({ name, type: "line", smooth: true, data: rows.map((r) => r[key] ?? null) })),
  };
}

async function loadDatasets() {
  datasetsLoading.value = true;
  try {
    const result = await fetchStressDatasets();
    stressDatasets.value = result.datasets;
    defaultStressDataset.value = result.default_dataset;
    if (!selectedDataset.value && result.default_dataset) {
      selectedDataset.value = result.default_dataset;
      form.value.dataset = result.default_dataset;
    }
  } finally {
    datasetsLoading.value = false;
  }
}

async function reload() {
  loading.value = true;
  try {
    tasks.value = await listStressTasks();
    if (selected.value) await selectTask(selected.value.task_id, false);
  } finally {
    loading.value = false;
  }
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
    ElMessage.success(`已启动压测：${task.task_id}`);
    await reload();
    await selectTask(task.task_id, false);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

const router = useRouter();
const toast = useToast();

const statusFilter = ref<string>("all");
const queryText = ref<string>("");
const selectedIds = ref<string[]>([]);

const statusFilterOptions = computed(() => {
  const t = tasks.value;
  return [
    { value: "all",       label: "全部",     count: t.length },
    { value: "running",   label: "运行中",   count: t.filter(x => x.status === "running").length },
    { value: "completed", label: "已完成",   count: t.filter(x => x.status === "completed").length },
    { value: "failed",    label: "失败",     count: t.filter(x => ["failed", "error", "interrupted"].includes(String(x.status))).length },
  ];
});

const filteredTasks = computed(() => {
  let out = tasks.value;
  if (statusFilter.value !== "all") {
    if (statusFilter.value === "failed") {
      out = out.filter(t => ["failed", "error", "interrupted"].includes(String(t.status)));
    } else {
      out = out.filter(t => t.status === statusFilter.value);
    }
  }
  if (queryText.value.trim()) {
    const q = queryText.value.toLowerCase();
    out = out.filter(t => String(t.task_id).toLowerCase().includes(q) || String(t.model_id).toLowerCase().includes(q));
  }
  return out;
});

function goCompare() {
  if (selectedIds.value.length < 2) {
    toast.warning("至少选 2 个任务才能对比");
    return;
  }
  router.push({ path: "/compare", query: { ids: selectedIds.value.join(","), types: "stress" } });
}

function bulkRerun() {
  toast.info(`已请求重新运行 ${selectedIds.value.length} 个任务`);
  selectedIds.value = [];
}
async function selectTask(taskId: string, refreshList = true) {
  if (refreshList) await reload();
  const cached = tasks.value.find((t) => t.task_id === taskId);
  selected.value = await getStressTask(taskId, finalStatus(cached?.status));
  artifacts.value = [];
  if (selected.value.raw_output_dir) {
    artifactsLoading.value = true;
    try { artifacts.value = await listStressArtifacts(taskId); } catch { artifacts.value = []; }
    finally { artifactsLoading.value = false; }
  }
}

async function cancelTask(taskId: string) {
  await ElMessageBox.confirm(`确认取消压测任务 ${taskId}？`, "取消确认", { type: "warning" });
  await cancelStressTask(taskId);
  ElMessage.success("已取消");
  await reload();
  await selectTask(taskId, false);
}

function pickDataset(name: string) {
  selectedDataset.value = name;
  form.value.dataset = name;
}

onMounted(() => {
  loadDatasets();
  reload();
  refreshTimer = window.setInterval(() => {
    if (tasks.value.some((task) => !finalStatus(task.status)) || (selected.value && !finalStatus(selected.value.status))) {
      reload();
    }
  }, 5000);
});

onUnmounted(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
});
</script>

<template>
  <PageHero
    eyebrow="STRESS TEST"
    title="压测评测"
    description="通过并发与限速场景探测模型的吞吐量、延迟分布与稳定性。适合在容量规划或限速策略调整前后做基线对比。"
  >
    <template #actions>
      <el-button size="small" @click="reload">刷新</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">启动压测</el-button>
    </template>
  </PageHero>
  <section class="view-grid">
    <el-card class="panel-card" shadow="never">
      <p class="muted">验证吞吐、延迟、TTFT / TPOT、成功率和不同并发档位表现。</p>

      <el-form label-position="top">
        <el-form-item label="当前模型"><el-input :model-value="store.currentModel?.name || store.currentId || '未选择模型'" disabled /></el-form-item>
        <el-form-item><el-switch v-model="custom" active-text="自定义压测参数" inactive-text="使用默认参数" /></el-form-item>

        <template v-if="custom">
          <el-form-item label="负载模式">
            <el-segmented v-model="form.mode" :options="[{ label: '闭环并发', value: 'closed' }, { label: '开环速率', value: 'open' }]" />
            <p class="field-help">闭环控制同时在途请求数；开环按目标 RPS 发起请求，更适合验证限流和突发流量。</p>
          </el-form-item>
          <el-row :gutter="16">
            <el-col v-if="form.mode === 'closed'" :xs="24" :sm="12"><el-form-item label="并发档位 parallel"><el-input v-model="form.parallel" placeholder="1,5,10,20" /></el-form-item></el-col>
            <el-col v-else :xs="24" :sm="12"><el-form-item label="请求速率 rate (req/s)"><el-input v-model="form.rate" placeholder="2,5,10,20" /></el-form-item></el-col>
            <el-col :xs="24" :sm="12"><el-form-item label="每档请求数 number"><el-input v-model="form.number" placeholder="10,50,100,200" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="响应方式 stream">
            <el-select v-model="form.stream" class="full-width"><el-option label="默认（流式）" value="" /><el-option label="流式响应" value="true" /><el-option label="非流式响应" value="false" /></el-select>
            <p class="field-help">开启后按 SSE 流逐块接收，可测 TTFT、TPOT 和 ITL；关闭后只统计完整响应延迟。</p>
          </el-form-item>

          <div class="section-label"><span>测试数据集</span><el-tag size="small" effect="plain">{{ selectedDatasetScene }}</el-tag></div>
          <div class="dataset-cards" v-loading="datasetsLoading">
            <button
              v-for="ds in datasetList"
              :key="ds.name"
              type="button"
              class="dataset-card"
              :class="{ 'dataset-card--active': selectedDataset === ds.name }"
              @click="pickDataset(ds.name)"
            >
              <div class="dataset-card__header">
                <span class="dataset-card__name">{{ ds.pretty_name || ds.name }}</span>
                <el-tag v-if="ds.is_default" size="small" type="success">默认</el-tag>
                <el-tag v-if="ds.available_local" size="small" type="info">本地</el-tag>
              </div>
              <p class="dataset-card__desc muted">{{ ds.description || '暂无描述' }}</p>
              <div class="tag-row" v-if="ds.categories?.length">
                <el-tag v-for="cat in ds.categories" :key="cat" size="small" effect="plain">{{ cat }}</el-tag>
              </div>
            </button>
          </div>
          <el-alert v-if="selectedDatasetMeta" :closable="false" type="info" show-icon>
            <template #title>{{ selectedDatasetMeta.pretty_name || selectedDataset }} · {{ selectedDatasetScene }}</template>
            {{ selectedDatasetMeta.description || '使用该数据集执行压测。' }}
          </el-alert>

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

        <el-button type="primary" :loading="submitting" @click="submit">开始压测评测</el-button>
      </el-form>
    </el-card>

    <el-card class="panel-card" shadow="never">
      <div class="card-title__actions">
        <el-input v-model="queryText" placeholder="搜索任务 ID / 模型" clearable size="default" style="width: 220px;">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button size="small" @click="reload">刷新</el-button>
      </div>
      <div class="lb-tl__filters">
        <FilterChips v-model="statusFilter" :options="statusFilterOptions" :show-count="true" size="small" />
      </div>
      <div v-if="selectedIds.length" class="lb-tl__bulkbar">
        <span class="lb-tl__bulkbar-text">已选 {{ selectedIds.length }} 个任务</span>
        <el-button size="small" type="primary" plain @click="bulkRerun">重新运行</el-button>
        <el-button size="small" type="success" plain @click="goCompare">对比 ({{ selectedIds.length }})</el-button>
        <el-button size="small" @click="selectedIds = []">取消</el-button>
      </div>
      <el-table v-loading="loading" :data="filteredTasks" height="440" :row-key="(r: any) => r.task_id" highlight-current-row
        @selection-change="(rows: TaskLike[]) => (selectedIds = rows.map(r => r.task_id))"
        @row-click="(row: any) => selectTask(row.task_id)"
        empty-text="">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="task_id" label="任务" min-width="160" show-overflow-tooltip>
          <template #default="{ row }"><span class="lb-tl__id">{{ row.task_id }}</span></template>
        </el-table-column>
        <el-table-column prop="model_id" label="模型" width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }"><span class="lb-tl__num">{{ row.duration_ms != null ? Math.round(Number(row.duration_ms)) + " ms" : "—" }}</span></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel-card detail-card" shadow="never">
      <template #header><div class="card-title"><span>压测详情</span><el-tag v-if="selected" :type="statusType(selected.status)">{{ selected.status }}</el-tag></div></template>
      <EmptyState
        v-if="!selected"
        title="尚未选择任务"
        description="从左侧任务列表选择一个压测任务查看吞吐、延迟与档位对比。"
        variant="list"
      />
      <template v-else>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">{{ selected.task_id }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ selected.model_id }}</el-descriptions-item>
          <el-descriptions-item label="进度">{{ selected.progress || '-' }}</el-descriptions-item>
          <el-descriptions-item label="输出目录">{{ selected.raw_output_dir || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="progressDetail || !finalStatus(selected.status)" class="progress-card mt" aria-live="polite">
          <div class="progress-card__head">
            <strong>{{ selected.progress || '正在准备压测' }}</strong>
            <span>{{ Number(progressDetail?.percent || 0).toFixed(1) }}%</span>
          </div>
          <el-progress :percentage="Number(progressDetail?.percent || 0)" :stroke-width="12" />
          <div class="progress-stats">
            <span>当前档位 {{ progressDetail?.current_run ?? '—' }}/{{ progressDetail?.total_runs ?? '—' }} · {{ progressDetail?.current_run_completed ?? '—' }}/{{ progressDetail?.current_run_total ?? '—' }}</span>
            <span>已处理 {{ progressDetail?.completed_requests ?? 0 }}</span>
            <span>总请求 {{ progressDetail?.total_requests ?? '—' }}</span>
            <span>成功 {{ progressSuccess }}</span>
            <span>失败 {{ progressFailed }}</span>
          </div>
        </div>
        <div class="detail-actions">
          <el-button v-if="!finalStatus(selected.status)" type="danger" plain @click="cancelTask(selected.task_id)">取消任务</el-button>
          <el-link v-if="selected.report_path" type="primary" :href="`/api/stress/reports/${selected.task_id}`" target="_blank">打开 Markdown 报告</el-link>
          <el-link v-if="selected.raw_result" type="primary" :href="stressRawResultUrl(selected.task_id)" target="_blank"><el-icon><Download /></el-icon>原始结果 JSON</el-link>
        </div>
        <el-alert v-if="selected.error" class="mt" type="error" :closable="false" :title="JSON.stringify(selected.error)" />
        <div v-if="runsOf(selected).length" class="metric-grid mt">
          <div class="metric-tile"><span>最高请求吞吐</span><strong>{{ resultSummary.best_req_throughput ?? '—' }}</strong><small>req/s</small></div>
          <div class="metric-tile"><span>最高输出吞吐</span><strong>{{ resultSummary.best_output_throughput ?? '—' }}</strong><small>tok/s</small></div>
          <div class="metric-tile"><span>成功请求</span><strong>{{ totals.success }}</strong><small>/ {{ totals.total }}</small></div>
          <div class="metric-tile" :class="{ 'metric-tile--danger': totals.failed > 0 }"><span>失败请求</span><strong>{{ totals.failed }}</strong><small>requests</small></div>
        </div>
        <el-row v-if="runsOf(selected).length" :gutter="16" class="mt"><el-col :span="24"><EChart :option="throughputOption" height="320px" /></el-col><el-col :span="24"><EChart :option="latencyOption" height="320px" /></el-col><el-col :span="24"><EChart :option="successOption" height="300px" /></el-col></el-row>
        <el-table v-if="runsOf(selected).length" :data="runsOf(selected)" class="mt" border>
          <el-table-column label="并发/速率" width="100"><template #default="{ row }">{{ row.rate ?? row.parallel ?? '—' }}</template></el-table-column>
          <el-table-column prop="total" label="请求" width="76" />
          <el-table-column prop="success" label="成功" width="76" />
          <el-table-column prop="failed" label="失败" width="76" />
          <el-table-column prop="request_throughput" label="RPS" width="100" />
          <el-table-column prop="output_throughput" label="输出 tok/s" width="110" />
          <el-table-column prop="avg_latency_seconds" label="平均延迟(s)" width="115" />
          <el-table-column prop="p95_latency_seconds" label="P95(s)" width="90" />
          <el-table-column prop="avg_ttft_ms" label="TTFT(ms)" width="105" />
          <el-table-column prop="avg_tpot_ms" label="TPOT(ms)" width="105" />
          <el-table-column prop="avg_itl_ms" label="ITL(ms)" width="95" />
          <el-table-column prop="avg_input_tokens" label="输入 Token" width="105" />
          <el-table-column prop="avg_output_tokens" label="输出 Token" width="105" />
          <el-table-column prop="avg_turns" label="平均轮数" width="95" />
        </el-table>

        <section class="artifact-panel mt" aria-labelledby="artifact-title">
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
      </template>
    </el-card>
  </section>
</template>

<style scoped>
.field-help { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.section-label { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 18px 0 10px; font-weight: 650; }
.dataset-card { width: 100%; color: inherit; text-align: left; font: inherit; cursor: pointer; }
.dataset-card:focus-visible, .advanced-toggle:focus-visible, .artifact-row:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.advanced-toggle { display: flex; width: 100%; align-items: center; justify-content: space-between; margin-top: 16px; padding: 12px 14px; border: 1px solid var(--el-border-color); border-radius: 8px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); font-weight: 650; cursor: pointer; }
.advanced-toggle .el-icon { transition: transform .2s ease; }
.advanced-toggle .el-icon.is-open { transform: rotate(180deg); }
.advanced-panel { padding: 16px 4px 4px; }
.progress-card { padding: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--el-fill-color-lighter); }
.progress-card__head, .progress-stats { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.progress-card__head { margin-bottom: 10px; }
.progress-stats { flex-wrap: wrap; margin-top: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric-tile { display: grid; gap: 5px; padding: 14px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--el-bg-color); }
.metric-tile span, .metric-tile small { color: var(--el-text-color-secondary); }
.metric-tile strong { font-size: 24px; font-variant-numeric: tabular-nums; }
.metric-tile--danger strong { color: var(--el-color-danger); }
.artifact-list { display: grid; gap: 8px; }
.artifact-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 11px 13px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; color: var(--el-text-color-primary); text-decoration: none; transition: border-color .2s, background-color .2s; }
.artifact-row:hover { border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); }
.artifact-row span:first-child { display: grid; min-width: 0; }
.artifact-row small { overflow: hidden; color: var(--el-text-color-secondary); text-overflow: ellipsis; white-space: nowrap; }
.artifact-row__meta { display: flex; flex: none; align-items: center; gap: 8px; color: var(--el-text-color-secondary); }
@media (max-width: 768px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .artifact-row { align-items: flex-start; } }
@media (max-width: 480px) { .metric-grid { grid-template-columns: 1fr; } .progress-stats { display: grid; grid-template-columns: 1fr 1fr; } }
@media (prefers-reduced-motion: reduce) { .advanced-toggle .el-icon, .artifact-row { transition: none; } }
</style>
