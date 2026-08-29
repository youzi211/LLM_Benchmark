<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useModelsStore } from "@/stores/models";
import EChart from "@/components/EChart.vue";
import DatasetPicker from "@/components/common/DatasetPicker.vue";
import {
  cancelIntelligenceTask,
  fetchDatasets,
  finalStatus,
  formatDate,
  getIntelligenceTask,
  listIntelligenceTasks,
  runDefaultIntelligence,
  runIntelligence,
  toNumber,
  type DatasetMeta,
  type TaskLike,
} from "@/api/evaluations";

const store = useModelsStore();
const loading = ref(false);
const datasetLoading = ref(false);
const submitting = ref(false);
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
let refreshTimer: number | undefined;
const datasets = ref<Record<string, DatasetMeta>>({});
const defaultDatasets = ref<string[]>([]);
const custom = ref(false);
const chosenDatasets = ref<string[]>([]);
const limit = ref("");
const batchSize = ref("");
// Per-dataset selected subsets: { datasetName: string[] }
// Empty/null means use configured defaults.
const chosenSubsets = ref<Record<string, string[]>>({});
// Per-dataset subset override switch
const subsetOverride = ref<Record<string, boolean>>({});

const localDatasetEntries = computed(() => Object.entries(datasets.value)
  .filter(([, meta]) => meta.available_local)
  .sort(([a], [b]) => {
    const da = defaultDatasets.value.includes(a);
    const db = defaultDatasets.value.includes(b);
    if (da !== db) return da ? -1 : 1;
    return a.localeCompare(b);
  }));

const scoreOption = computed(() => {
  const normalized: any = selected.value?.normalized_result || (selected.value?.raw_result as any)?.normalized_result;
  const rows = Array.isArray(normalized?.dataset_results) ? normalized.dataset_results : [];
  return {
    title: { text: "数据集分数", left: "center" },
    tooltip: {},
    grid: { left: 80, right: 24, top: 64, bottom: 60 },
    xAxis: { type: "category", data: rows.map((r: any) => r.pretty_name || r.dataset), axisLabel: { rotate: 25 } },
    yAxis: { type: "value", max: 100 },
    series: [{ type: "bar", data: rows.map((r: any) => normalizeScore(r.score)), itemStyle: { color: "#409eff" } }],
  };
});

function normalizeScore(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n <= 1 ? Math.round(n * 1000) / 10 : Math.round(n * 10) / 10;
}

function statusType(status?: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "interrupted") return "danger";
  if (status === "running" || status === "pending") return "warning";
  return "info";
}

function progressPercent(task: TaskLike | null) {
  const detail: any = task?.progress_detail;
  const value = detail?.overall_percent ?? detail?.percent;
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(n, 100)) : 0;
}
async function loadDatasetMeta() {
  datasetLoading.value = true;
  try {
    const data = await fetchDatasets();
    datasets.value = data.datasets;
    defaultDatasets.value = data.default_datasets;
    chosenDatasets.value = localDatasetEntries.value.filter(([name]) => defaultDatasets.value.includes(name)).map(([name]) => name);
    if (!chosenDatasets.value.length) chosenDatasets.value = localDatasetEntries.value.map(([name]) => name);
  } finally {
    datasetLoading.value = false;
  }
}

async function reload() {
  loading.value = true;
  try {
    tasks.value = await listIntelligenceTasks();
    if (selected.value) await selectTask(selected.value.task_id, false);
  } finally {
    loading.value = false;
  }
}

function buildPayload() {
  if (!store.currentId) throw new Error("请先选择当前模型");
  const limitValue = toNumber(limit.value);
  const batchValue = toNumber(batchSize.value);
  if (!custom.value && limitValue === undefined && batchValue === undefined) {
    return { endpoint: "default" as const, payload: { model_id: store.currentId } };
  }
  const localNames = localDatasetEntries.value.map(([name]) => name);
  const selectedNames = custom.value ? chosenDatasets.value : localNames.filter((name) => defaultDatasets.value.includes(name));
  const finalDatasets = selectedNames.length ? selectedNames : localNames;
  if (!finalDatasets.length) throw new Error("未发现本地可用数据集，请先由管理员提供数据集目录。");
  const payload: Record<string, unknown> = { model_id: store.currentId, datasets: finalDatasets };
  if (limitValue !== undefined) payload.limit = limitValue;
  if (batchValue !== undefined) payload.eval_batch_size = batchValue;

  // Build dataset_args for datasets with user-selected subset overrides
  const datasetArgs: Record<string, Record<string, unknown>> = {};
  for (const name of finalDatasets) {
    if (subsetOverride.value[name] && chosenSubsets.value[name]?.length) {
      datasetArgs[name] = { subset_list: chosenSubsets.value[name] };
    }
  }
  if (Object.keys(datasetArgs).length) payload.dataset_args = datasetArgs;

  return { endpoint: "custom" as const, payload };
}

async function submit() {
  submitting.value = true;
  try {
    const request = buildPayload();
    const task = request.endpoint === "default"
      ? await runDefaultIntelligence(request.payload)
      : await runIntelligence(request.payload);
    ElMessage.success(`已启动能力评测：${task.task_id}`);
    await reload();
    await selectTask(task.task_id, false);
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

async function selectTask(taskId: string, refreshList = true) {
  if (refreshList) await reload();
  const cached = tasks.value.find((t) => t.task_id === taskId);
  selected.value = await getIntelligenceTask(taskId, finalStatus(cached?.status));
}

async function cancelTask(taskId: string) {
  await ElMessageBox.confirm(`确认取消能力评测任务 ${taskId}？`, "取消确认", { type: "warning" });
  await cancelIntelligenceTask(taskId);
  ElMessage.success("已取消");
  await reload();
  await selectTask(taskId, false);
}

onMounted(async () => {
  await Promise.all([loadDatasetMeta(), reload()]);
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
  <section class="view-grid">
    <el-card class="panel-card" shadow="never">
      <template #header><div class="card-title"><span>能力评测</span><el-tag>EvalScope datasets</el-tag></div></template>
      <p class="muted">只展示并提交本地已提供的数据集。数据集由管理员放入 data/evalscope_datasets。</p>
      <el-form label-position="top">
        <el-form-item label="当前模型"><el-input :model-value="store.currentModel?.name || store.currentId || '未选择模型'" disabled /></el-form-item>
        <el-row :gutter="10"><el-col :span="12"><el-form-item label="limit"><el-input v-model="limit" placeholder="可选" /></el-form-item></el-col><el-col :span="12"><el-form-item label="eval_batch_size"><el-input v-model="batchSize" placeholder="可选" /></el-form-item></el-col></el-row>
        <el-form-item><el-switch v-model="custom" active-text="自定义数据集" inactive-text="使用后端默认数据集" /></el-form-item>
        <p v-if="!custom" class="muted">不填写 limit / eval_batch_size 时走后端默认入口；填写后会按本地默认数据集发起自定义任务。</p>
        <DatasetPicker
          v-if="custom && localDatasetEntries.length"
          v-model="chosenDatasets"
          :datasets="datasets"
          :default-datasets="defaultDatasets"
          :subset-model-value="chosenSubsets"
          :subset-override="subsetOverride"
          @update:subset-model-value="(v) => (chosenSubsets = v)"
          @update:subset-override="(v) => (subsetOverride = v)"
        />
        <DatasetPicker
          v-else-if="!custom && localDatasetEntries.length"
          :datasets="datasets"
          :default-datasets="defaultDatasets"
          :model-value="localDatasetEntries.map(([name]) => name)"
          :subset-model-value="chosenSubsets"
          :subset-override="subsetOverride"
          disabled
          @update:subset-model-value="(v) => (chosenSubsets = v)"
          @update:subset-override="(v) => (subsetOverride = v)"
        />
        <el-button type="primary" :loading="submitting" :disabled="!localDatasetEntries.length" @click="submit">开始能力评测</el-button>
      </el-form>
    </el-card>

    <el-card class="panel-card" shadow="never">
      <template #header><div class="card-title"><span>能力任务</span><el-button size="small" @click="reload">刷新</el-button></div></template>
      <el-table v-loading="loading" :data="tasks" height="520" highlight-current-row @row-click="(row: any) => selectTask(row.task_id)">
        <el-table-column prop="task_id" label="任务" min-width="210" show-overflow-tooltip />
        <el-table-column prop="model_id" label="模型" width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column label="进度" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.progress || '-' }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel-card detail-card" shadow="never">
      <template #header><div class="card-title"><span>能力详情</span><el-tag v-if="selected" :type="statusType(selected.status)">{{ selected.status }}</el-tag></div></template>
      <el-empty v-if="!selected" description="请选择一个能力评测任务" />
      <template v-else>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">{{ selected.task_id }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ selected.model_id }}</el-descriptions-item>
          <el-descriptions-item label="数据集">{{ Array.isArray(selected.datasets) ? selected.datasets.join(', ') : '-' }}</el-descriptions-item>
          <el-descriptions-item label="输出目录">{{ selected.raw_output_dir || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div class="mt">
          <el-progress :percentage="progressPercent(selected)" />
          <p class="muted">{{ selected.progress || '等待进度' }}</p>
        </div>
        <div class="detail-actions">
          <el-button v-if="!finalStatus(selected.status)" type="danger" plain @click="cancelTask(selected.task_id)">取消任务</el-button>
          <el-link v-if="selected.report_path" type="primary" :href="`/api/intelligence/reports/${selected.task_id}`" target="_blank">打开 Markdown 报告</el-link>
        </div>
        <el-alert v-if="selected.error" class="mt" type="error" :closable="false" :title="JSON.stringify(selected.error)" />
        <EChart v-if="(selected.normalized_result as any)?.dataset_results?.length" class="mt" :option="scoreOption" height="360px" />
      </template>
    </el-card>
  </section>
</template>
