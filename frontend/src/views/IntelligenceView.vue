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
import { Document, Plus, Refresh, Search, VideoPlay } from "@element-plus/icons-vue";
import type { TableInstance } from "element-plus";
import { effectiveDatasetNames, modelDisplayName, progressPercentOf, scorePercent } from "@/evaluation/presentation";
import DatasetPicker from "@/components/common/DatasetPicker.vue";
import { shouldShowTaskListEmpty, taskById } from "@/utils/taskListState";
import { taskIdFromQuery } from "@/utils/taskCenter";
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

const EChart = defineAsyncComponent(() => import("@/components/EChart.vue"));
const store = useModelsStore();
const loading = ref(true);
const refreshing = ref(false);
const listError = ref("");
const datasetLoading = ref(false);
const submitting = ref(false);
const configurationVisible = ref(false);
const resultTab = ref("scores");
const taskTable = ref<TableInstance>();
const datasetError = ref("");
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
let refreshTimer: number | undefined;
let activeReload: Promise<void> | null = null;
let detailRequests = 0;
let selectionVersion = 0;
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

const effectiveDatasets = computed(() => effectiveDatasetNames(localDatasetEntries.value.map(([name]) => name), defaultDatasets.value, custom.value, chosenDatasets.value));
const unavailableDefaults = computed(() => defaultDatasets.value.filter((name) => !datasets.value[name]?.available_local));
const normalizedResult = computed<any>(() => selected.value?.normalized_result || (selected.value?.raw_result as any)?.normalized_result || null);
const datasetResults = computed<any[]>(() => Array.isArray(normalizedResult.value?.dataset_results) ? normalizedResult.value.dataset_results : []);
const categorySummaries = computed<any[]>(() => Array.isArray(normalizedResult.value?.category_summaries) ? normalizedResult.value.category_summaries : []);
const scoredCount = computed(() => datasetResults.value.filter((row) => scorePercent(row.score) !== null).length);
const selectedProgress = computed(() => progressPercentOf(selected.value?.progress_detail));
function modelName(id?: string) { return modelDisplayName(id, store.models); }

const scoreOption = computed(() => {
  const rows = datasetResults.value;
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 8, right: 36, top: 16, bottom: 24, containLabel: true },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    yAxis: { type: "category", inverse: true, data: rows.map((row) => row.pretty_name || row.dataset), axisLabel: { width: 90, overflow: "truncate" }, axisTick: { show: false } },
    series: [{ type: "bar", barMaxWidth: 18, itemStyle: { borderRadius: [0, 4, 4, 0] }, data: rows.map((row) => normalizeScore(row.score)) }],
  };
});

function normalizeScore(value: unknown) {
  return scorePercent(value);
}
async function loadDatasetMeta() {
  datasetLoading.value = true;
  try {
    const data = await fetchDatasets();
    datasets.value = data.datasets;
    datasetError.value = "";
    defaultDatasets.value = data.default_datasets;
    chosenDatasets.value = localDatasetEntries.value.filter(([name]) => defaultDatasets.value.includes(name)).map(([name]) => name);
    if (!chosenDatasets.value.length) chosenDatasets.value = localDatasetEntries.value.map(([name]) => name);
  } catch (err) {
    datasetError.value = err instanceof Error ? err.message : String(err);
  } finally {
    datasetLoading.value = false;
  }
}

async function refreshSelected() {
  if (!selected.value || finalStatus(selected.value.status)) return;
  const request = ++detailRequests;
  const selection = selectionVersion;
  const taskId = selected.value.task_id;
  try {
    const detail = await getIntelligenceTask(taskId, false);
    if (request === detailRequests && selection === selectionVersion) selected.value = detail;
  } catch {
    // Background refreshes keep the last known detail.
  }
}

function reload(options: { background?: boolean } = {}): Promise<void> {
  if (activeReload) return activeReload;
  if (!options.background) refreshing.value = true;
  activeReload = (async () => {
    try {
      tasks.value = await listIntelligenceTasks();
      listError.value = "";
      await refreshSelected();
    } catch (err) {
      listError.value = err instanceof Error ? err.message : String(err);
      if (!options.background) ElMessage.error("加载能力评测任务失败: " + listError.value);
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
  const limitValue = toNumber(limit.value);
  const batchValue = toNumber(batchSize.value);
  if (!custom.value && limitValue === undefined && batchValue === undefined) {
    return { endpoint: "default" as const, payload: { model_id: store.currentId } };
  }
  const finalDatasets = effectiveDatasets.value;
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
    configurationVisible.value = false;
    ElMessage.success(`已启动能力评测：${task.task_id}`);
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

const statusFilterOptions = computed(() => {
  const t = tasks.value;
  return [
    { value: "all",       label: "全部",     count: t.length },
    { value: "running",   label: "运行中",   count: t.filter(x => ["running", "pending", "queued"].includes(String(x.status))).length },
    { value: "completed", label: "已完成",   count: t.filter(x => x.status === "completed").length },
    { value: "failed",    label: "失败",     count: t.filter(x => ["failed", "error", "interrupted"].includes(String(x.status))).length },
  ];
});

const filteredTasks = computed(() => {
  let out = tasks.value;
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
    out = out.filter(t => String(t.task_id).toLowerCase().includes(q) || String(t.model_id).toLowerCase().includes(q));
  }
  return out;
});

function goCompare() {
  if (selectedIds.value.length < 2) {
    toast.warning("至少选 2 个任务才能对比");
    return;
  }
  router.push({ path: "/compare", query: { ids: selectedIds.value.join(","), types: selectedIds.value.map(() => "intelligence").join(",") } });
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
        // 列表只存 datasets；limit 等参数不保留，重跑走后端默认。
        await runIntelligence({ model_id: row.model_id, datasets: row.datasets || [] });
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
  if (ok && !failed) ElMessage.success(`已重新运行 ${ok} 个能力评测任务`);
}
async function selectTask(taskId: string, refreshList = false) {
  const selection = ++selectionVersion;
  if (refreshList) await reload({ background: true });
  if (selection !== selectionVersion) return;
  const cached = taskById(tasks.value, taskId);
  selected.value = cached;
  try {
    const detail = await getIntelligenceTask(taskId, finalStatus(cached?.status));
    if (selection === selectionVersion) selected.value = detail;
  } catch (err) {
    if (selection === selectionVersion) {
      ElMessage.error("加载能力评测详情失败: " + (err instanceof Error ? err.message : String(err)));
    }
  }
}

async function selectTaskAndSync(taskId: string) {
  await selectTask(taskId);
  if (selected.value?.task_id !== taskId || taskIdFromQuery(route.query.task_id) === taskId) return;
  await router.replace({ query: { ...route.query, task_id: taskId } });
}

async function selectRequestedTask() {
  const taskId = taskIdFromQuery(route.query.task_id);
  if (!taskId || selected.value?.task_id === taskId) return;
  await selectTask(taskId);
}

async function cancelTask(taskId: string) {
  try {
    await ElMessageBox.confirm(`确认取消能力评测任务 ${taskId}？`, "取消确认", { type: "warning" });
    await cancelIntelligenceTask(taskId);
    ElMessage.success("已取消");
    await reload();
    await selectTask(taskId, false);
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error("取消能力评测失败: " + (err instanceof Error ? err.message : String(err)));
    }
  }
}

onMounted(async () => {
  await Promise.allSettled([loadDatasetMeta(), reload()]);
  await selectRequestedTask();
  refreshTimer = window.setInterval(() => {
    if (document.visibilityState !== "visible" || activeReload) return;
    if (tasks.value.some((task) => !finalStatus(task.status)) || (selected.value && !finalStatus(selected.value.status))) {
      reload({ background: true });
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
    eyebrow="INTELLIGENCE EVAL"
    title="能力评测"
    description="基于本地数据集评估知识、代码与推理表现，跟踪评测进度和分项得分。"
  >
    <template #actions>
      <el-button :icon="Refresh" :loading="refreshing" @click="reload()">刷新数据</el-button>
      <el-button type="primary" :icon="Plus" @click="configurationVisible = true">新建能力评测</el-button>
    </template>
  </PageHero>
  <EvaluationWorkspace
    v-model:configuration-visible="configurationVisible" lane="intelligence" :task-count="tasks.length"
    :model-name="store.currentModel?.name || store.currentId || '未选择模型'" :auto-updating="autoUpdating"
    detail-title="能力评测结果" detail-description="按数据集与能力维度查看分数，不将缺失结果当作零分"
    configuration-title="新建能力评测" configuration-description="选择数据集与样本范围。数据集来源于当前本地环境，Judge 与 Sandbox 在顶部评测环境中配置。" drawer-size="min(760px, 100vw)"
  >
    <template #configuration>
      <el-form label-position="top" class="lb-eval-form">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12"><el-form-item label="每子集样本上限 · limit"><el-input v-model="limit" aria-label="样本上限 limit" placeholder="留空使用服务端默认" /></el-form-item></el-col>
          <el-col :xs="24" :sm="12"><el-form-item label="评测批大小 · eval_batch_size"><el-input v-model="batchSize" aria-label="评测批大小" placeholder="留空使用服务端默认" /></el-form-item></el-col>
        </el-row>
        <p class="lb-eval-note">多子集数据集会对每个子集分别应用样本上限，任务总样本数可能大于 limit。</p>
        <div class="lb-eval-form__section"><h3>评测数据集</h3><p>仅展示本地可用数据集，可展开查看子集和本地路径。</p></div>
        <el-form-item><el-switch v-model="custom" aria-label="自定义数据集" active-text="自定义数据集" inactive-text="使用后端默认数据集" /></el-form-item>
        <div v-if="!custom" class="lb-eval-defaults"><strong>服务端默认组合</strong><p>不填写样本上限和批大小时使用默认入口；填写后按本地默认数据集发起自定义任务。下方勾选仅预览本地可用范围。</p><div class="tag-row"><el-tag v-for="name in defaultDatasets" :key="name" size="small" effect="plain">{{ name }}</el-tag></div></div>
        <el-skeleton v-if="datasetLoading" :rows="5" animated />
        <el-alert v-else-if="datasetError" class="lb-eval-alert" type="error" :closable="false" :title="`数据集加载失败：${datasetError}`"><el-button link type="primary" @click="loadDatasetMeta">重新加载</el-button></el-alert>
        <template v-else-if="localDatasetEntries.length">
          <el-alert v-if="!custom && unavailableDefaults.length" class="lb-eval-alert" type="warning" :closable="false" title="部分默认数据集本地不可用"><span>可切换自定义模式，仅选择已准备好的数据集。</span></el-alert>
          <DatasetPicker
            :model-value="custom ? chosenDatasets : effectiveDatasets" :datasets="datasets" :default-datasets="defaultDatasets"
            :subset-model-value="chosenSubsets" :subset-override="subsetOverride" :disabled="!custom"
            @update:model-value="(value) => chosenDatasets = value"
            @update:subset-model-value="(value) => chosenSubsets = value"
            @update:subset-override="(value) => subsetOverride = value"
          />
          <p v-if="custom" class="lb-eval-form__help">将评测 {{ effectiveDatasets.length }} 个本地数据集。{{ !chosenDatasets.length ? '未勾选时沿用原有规则，使用全部本地可用数据集。' : '子集未覆盖时保留后端默认配置。' }}</p>
        </template>
        <EmptyState v-else title="暂无本地可用数据集" description="请先由管理员在 data/evalscope_datasets 提供数据集，再重新检测。" action-label="重新检测" @action="loadDatasetMeta" />
      </el-form>
    </template>
    <template #configuration-footer><el-button @click="configurationVisible = false">返回工作台</el-button><el-button type="primary" :icon="VideoPlay" :loading="submitting" :disabled="!store.currentId || !localDatasetEntries.length || datasetLoading" @click="submit">开始能力评测</el-button></template>

    <template #list>
      <div class="lb-eval-toolbar">
        <el-input v-model="queryText" placeholder="搜索任务 ID / 模型" aria-label="搜索能力任务" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button text circle :icon="Refresh" :loading="refreshing" aria-label="刷新能力任务" @click="reload()" />
      </div>
      <el-alert v-if="listError" class="lb-eval-alert" type="error" :closable="false" show-icon :title="`任务列表加载失败：${listError}`" />
      <div class="lb-eval-filters">
        <FilterChips v-model="statusFilter" :options="statusFilterOptions" :show-count="true" size="small" />
      </div>
      <div v-if="selectedIds.length" class="lb-eval-bulk">
        <span>已选 {{ selectedIds.length }} 个任务</span>
        <el-button size="small" type="primary" plain :loading="rerunning" @click="bulkRerun">重新运行</el-button>
        <el-button size="small" :disabled="selectedIds.length < 2" @click="goCompare">对比任务</el-button>
        <el-button size="small" text @click="clearSelection">取消选择</el-button>
      </div>
      <el-table ref="taskTable" v-loading="loading" :data="filteredTasks" :max-height="520" :row-key="(row: any) => row.task_id" :current-row-key="selected?.task_id"
        @selection-change="(rows: TaskLike[]) => selectedIds = rows.map(row => row.task_id)" highlight-current-row @row-click="(row: any, column) => column?.type !== 'selection' && selectTaskAndSync(row.task_id)">
        <el-table-column type="selection" width="36" :reserve-selection="true" />
        <el-table-column prop="task_id" label="任务 / 模型" min-width="130" show-overflow-tooltip><template #default="{ row }"><button type="button" class="lb-eval-task-link" :aria-label="`查看任务 ${row.task_id}`" @click.stop="selectTaskAndSync(row.task_id)"><strong>{{ modelName(row.model_id) }}</strong><small>{{ row.task_id }}</small></button></template></el-table-column>
        <el-table-column label="状态" width="84"><template #default="{ row }"><StatusTag :status="row.status" compact /></template></el-table-column>
        <el-table-column label="数据集" width="76"><template #default="{ row }"><span class="lb-eval-numeric">{{ Array.isArray(row.datasets) ? row.datasets.length + ' 个' : '—' }}</span></template></el-table-column>
        <template #empty><EmptyState
          v-if="shouldShowTaskListEmpty(loading, listError, filteredTasks.length)" :title="hasFilters ? '无匹配任务' : '暂无能力评测任务'"
          :description="hasFilters ? '试着清空筛选条件。' : '选择数据集发起评测，结果会保留在这里。'" :variant="hasFilters ? 'search' : 'list'"
          :action-label="hasFilters ? '清空筛选' : '新建能力评测'" @action="emptyAction"
        /></template>
      </el-table>
    </template>

    <template #detail-actions><StatusTag v-if="selected" :status="selected.status ?? 'pending'" /><el-button v-if="selected && !finalStatus(selected.status)" size="small" type="danger" plain @click="cancelTask(selected.task_id)">取消任务</el-button></template>
    <template #detail>
      <EmptyState v-if="!selected" title="尚未选择任务" description="选择一条能力评测任务，查看进度、数据集得分与分类结果。" />
      <template v-else>
        <div class="lb-eval-task-title"><div><strong>{{ modelName(selected.model_id) }}</strong><code>{{ selected.task_id }}</code></div><el-link v-if="selected.report_path" type="primary" :icon="Document" :href="`/api/intelligence/reports/${selected.task_id}`" target="_blank">打开报告</el-link></div>
        <div class="lb-eval-stats">
          <div class="lb-eval-stat"><span>评测数据集</span><strong>{{ Array.isArray(selected.datasets) ? selected.datasets.length : datasetResults.length }}</strong><small>本次任务范围</small></div>
          <div class="lb-eval-stat"><span>已取得分数</span><strong>{{ normalizedResult ? scoredCount : '—' }}</strong><small>不包含缺失结果</small></div>
          <div class="lb-eval-stat"><span>能力类别</span><strong>{{ normalizedResult ? categorySummaries.length : '—' }}</strong><small>来自分类汇总</small></div>
          <div class="lb-eval-stat"><span>当前进度</span><strong>{{ selectedProgress === undefined ? '—' : selectedProgress.toFixed(1) + '%' }}</strong><small>仅使用已返回进度</small></div>
        </div>
        <div v-if="!finalStatus(selected.status) || selected.progress_detail" class="lb-eval-progress" aria-live="polite">
          <div class="lb-eval-progress__head"><strong>{{ selected.progress || '等待进度信息' }}</strong><span>{{ selectedProgress === undefined ? '等待进度' : selectedProgress.toFixed(1) + '%' }}</span></div>
          <el-progress v-if="selectedProgress !== undefined" :percentage="selectedProgress" :stroke-width="5" :show-text="false" /><div v-else class="lb-eval-progress__waiting"></div>
          <div v-if="selected.progress_detail" class="lb-eval-progress__stats"><span>已处理 {{ (selected.progress_detail as any).processed_count ?? '—' }} / {{ (selected.progress_detail as any).total_count ?? '—' }} 样本</span><span>数据集 {{ (selected.progress_detail as any).dataset_index ?? '—' }} / {{ (selected.progress_detail as any).dataset_total ?? '—' }}</span></div>
        </div>
        <el-alert v-if="selected.error" class="lb-eval-alert" type="error" :closable="false" title="能力评测执行异常"><pre class="lb-eval-error">{{ JSON.stringify(selected.error, null, 2) }}</pre></el-alert>
        <el-tabs v-model="resultTab" class="lb-eval-tabs">
          <el-tab-pane label="数据集得分" name="scores">
            <p class="lb-eval-note">0–1 区间得分折算为百分制展示；原始分数可悬停查看，缺失结果不计为零分。</p>
            <EChart v-if="scoredCount && resultTab === 'scores'" :option="scoreOption" :height="`${Math.max(240, datasetResults.length * 52 + 40)}px`" />
            <el-table v-if="datasetResults.length" :data="datasetResults" class="lb-intel-results">
              <el-table-column label="数据集" min-width="150"><template #default="{ row }"><strong>{{ row.pretty_name || row.dataset }}</strong><small class="lb-intel-dataset-id">{{ row.dataset }}</small></template></el-table-column>
              <el-table-column label="类别" min-width="120"><template #default="{ row }">{{ row.categories?.join('、') || '—' }}</template></el-table-column>
              <el-table-column label="得分（%）" min-width="110"><template #default="{ row }"><span class="lb-intel-score" :title="row.score != null ? `原始得分：${row.score}` : undefined">{{ normalizeScore(row.score) === null ? '未取得分数' : normalizeScore(row.score) + '%' }}</span></template></el-table-column>
            </el-table>
            <EmptyState v-else :title="finalStatus(selected.status) ? '暂无数据集得分' : '等待评测结果'" description="结果生成后会逐项展示；未返回的分数不会被当作零分。" />
          </el-tab-pane>
          <el-tab-pane label="能力维度" name="categories">
            <el-table v-if="categorySummaries.length" :data="categorySummaries">
              <el-table-column prop="category" label="类别" min-width="120" />
              <el-table-column prop="dataset_count" label="数据集数" min-width="100" />
              <el-table-column prop="scored_dataset_count" label="已评分数" min-width="100" />
              <el-table-column label="平均分（%）" min-width="120"><template #default="{ row }">{{ normalizeScore(row.average_score) === null ? '未取得分数' : normalizeScore(row.average_score) + '%' }}</template></el-table-column>
            </el-table>
            <EmptyState v-else title="暂无能力维度汇总" description="分类汇总以评测任务返回的数据为准。" />
          </el-tab-pane>
          <el-tab-pane label="任务信息" name="info">
            <dl class="lb-eval-meta">
              <div><dt>模型配置 ID</dt><dd class="lb-eval-mono">{{ selected.model_id || '—' }}</dd></div>
              <div><dt>创建时间</dt><dd>{{ formatDate(selected.created_at) }}</dd></div>
              <div><dt>完成时间</dt><dd>{{ formatDate(selected.completed_at) }}</dd></div>
              <div><dt>更新时间</dt><dd>{{ formatDate(selected.updated_at) }}</dd></div>
              <div class="lb-eval-meta__wide"><dt>数据集范围</dt><dd>{{ Array.isArray(selected.datasets) ? selected.datasets.join('、') : '—' }}</dd></div>
              <div class="lb-eval-meta__wide"><dt>原始输出目录</dt><dd class="lb-eval-mono">{{ selected.raw_output_dir || '尚未生成' }}</dd></div>
            </dl>
          </el-tab-pane>
        </el-tabs>
      </template>
    </template>
  </EvaluationWorkspace>
</template>

<style scoped>
.lb-intel-results strong { color: var(--lb-fg-strong); font-size: 12px; font-weight: 500; }
.lb-intel-dataset-id { display: block; margin-top: 5px; color: var(--lb-muted); font: 10px var(--font-mono); }
.lb-intel-score { color: var(--lb-primary); font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }
</style>
