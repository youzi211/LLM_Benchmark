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
import { Search } from "@element-plus/icons-vue";
import EChart from "@/components/EChart.vue";
import {
  cancelStressTask,
  fetchStressDatasets,
  finalStatus,
  formatDate,
  getStressTask,
  listStressTasks,
  parseIntegerList,
  runStress,
  toNumber,
  type StressDatasetMeta,
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
const form = ref({ parallel: "1,5,10,20", number: "10,50,100,200", stream: "", dataset: "", dataset_path: "", rate: "", min_prompt_length: "", max_prompt_length: "", min_tokens: "", max_tokens: "" });

const datasetList = computed(() => Object.values(stressDatasets.value).sort((a, b) => Number(b.is_default) - Number(a.is_default)));

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
  const parallel = parseIntegerList(form.value.parallel);
  const number = parseIntegerList(form.value.number);
  if (parallel && number && parallel.length !== number.length) {
    throw new Error("parallel 与 number 必须一一对应，例如 1,5,10 和 10,50,100。");
  }
  if (parallel) payload.parallel = parallel;
  if (number) payload.number = number;
  if (form.value.stream) payload.stream = form.value.stream === "true";
  if (form.value.dataset) payload.dataset = form.value.dataset;
  if (form.value.dataset_path) payload.dataset_path = form.value.dataset_path;
  for (const key of ["rate", "min_prompt_length", "max_prompt_length", "min_tokens", "max_tokens"] as const) {
    const value = toNumber(form.value[key]);
    if (value !== undefined) payload[key] = value;
  }
  return payload;
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
      <el-button type="primary" :loading="submitting" @click="runStress">启动压测</el-button>
    </template>
  </PageHero>
  <section class="view-grid">
    <el-card class="panel-card" shadow="never">
      <p class="muted">验证吞吐、延迟、TTFT / TPOT、成功率和不同并发档位表现。</p>

      <el-form label-position="top">
        <el-form-item label="当前模型"><el-input :model-value="store.currentModel?.name || store.currentId || '未选择模型'" disabled /></el-form-item>
        <el-form-item><el-switch v-model="custom" active-text="自定义压测参数" inactive-text="使用默认参数" /></el-form-item>

        <template v-if="custom">
          <el-form-item label="parallel"><el-input v-model="form.parallel" /></el-form-item>
          <el-form-item label="number"><el-input v-model="form.number" /></el-form-item>
          <el-form-item label="stream"><el-select v-model="form.stream" class="full-width"><el-option label="默认" value="" /><el-option label="true" value="true" /><el-option label="false" value="false" /></el-select></el-form-item>

          <div class="dataset-cards" v-loading="datasetsLoading">
            <div
              v-for="ds in datasetList"
              :key="ds.name"
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
            </div>
          </div>

          <el-form-item label="dataset_path"><el-input v-model="form.dataset_path" placeholder="可选本地路径，留空自动解析" /></el-form-item>
          <el-row :gutter="16"><el-col :span="12"><el-form-item label="最小 token"><el-input v-model="form.min_tokens" /></el-form-item></el-col><el-col :span="12"><el-form-item label="最大 token"><el-input v-model="form.max_tokens" /></el-form-item></el-col></el-row>
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
          <template #default="{ row }"><span class="lb-tl__num">{{ row.duration_ms ? Math.round(Number(row.duration_ms)) + " ms" : "—" }}</span></template>
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
        <div class="detail-actions">
          <el-button v-if="!finalStatus(selected.status)" type="danger" plain @click="cancelTask(selected.task_id)">取消任务</el-button>
          <el-link v-if="selected.report_path" type="primary" :href="`/api/stress/reports/${selected.task_id}`" target="_blank">打开 Markdown 报告</el-link>
        </div>
        <el-alert v-if="selected.error" class="mt" type="error" :closable="false" :title="JSON.stringify(selected.error)" />
        <el-row v-if="runsOf(selected).length" :gutter="16" class="mt"><el-col :span="24"><EChart :option="throughputOption" height="320px" /></el-col><el-col :span="24"><EChart :option="latencyOption" height="320px" /></el-col><el-col :span="24"><EChart :option="successOption" height="300px" /></el-col></el-row>
      </template>
    </el-card>
  </section>
</template>
