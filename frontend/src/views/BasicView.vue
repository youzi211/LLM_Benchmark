<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useModelsStore } from "@/stores/models";
import { useToast } from "@/composables/useToast";
import PageHero from "@/components/layouts/PageHero.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import FilterChips from "@/components/common/FilterChips.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import TaskTimeline from "@/components/common/TaskTimeline.vue";
import MarkdownReport from "@/components/common/MarkdownReport.vue";
import EvaluationWorkspace from "@/components/evaluation/EvaluationWorkspace.vue";
import { Document, Plus, Refresh, Search, VideoPlay } from "@element-plus/icons-vue";
import type { TableInstance } from "element-plus";
import { cancelBasicTask, fetchMetrics, formatDate, getBasicTask, listBasicTasks, submitBasic, type MetricInfo, type TaskLike } from "@/api/evaluations";
import { taskIdFromQuery } from "@/utils/taskCenter";
import { shouldShowTaskListEmpty, taskById } from "@/utils/taskListState";
import { formatEvaluationDuration, metricResultCounts, modelDisplayName } from "@/evaluation/presentation";

const route = useRoute();
const router = useRouter();
const toast = useToast();
const store = useModelsStore();
const loading = ref(true);
const refreshing = ref(false);
const listError = ref("");
const detailLoading = ref(false);
const configurationVisible = ref(false);
const detailTab = ref("metrics");
const taskTable = ref<TableInstance>();
let selectionVersion = 0;
let activeReload: Promise<void> | null = null;
const submitting = ref(false);
const rerunning = ref(false);
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
const planId = ref("gateway_acceptance_v1");
const metricIds = ref<string[]>([]);
const metricOptions = ref<MetricInfo[]>([]);
const metricCounts = computed(() => metricResultCounts(selected.value?.results));
const hasMetricResults = computed(() => Array.isArray(selected.value?.results));
const hasFilters = computed(() => Boolean(queryText.value.trim()) || statusFilter.value !== "all");

function modelName(id?: string) { return modelDisplayName(id, store.models); }
function metricName(id: string) { return metricOptions.value.find((metric) => metric.id === id)?.name || id; }
function clearSelection() { taskTable.value?.clearSelection(); selectedIds.value = []; }
function emptyAction() {
  if (hasFilters.value) { queryText.value = ""; statusFilter.value = "all"; }
  else configurationVisible.value = true;
}

const statusFilter = ref<string>("all");
const queryText = ref<string>("");
const selectedIds = ref<string[]>([]);
const activeTaskId = ref<string | null>(null);
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollGeneration = 0;

function isActiveTask(task: TaskLike | null): boolean {
  return Boolean(task && ["queued", "running", "pending"].includes(String(task.status)));
}

const statusFilterOptions = computed(() => {
  const t = tasks.value;
  return [
    { value: "all",       label: "全部",     count: t.length },
    { value: "running",   label: "运行中",   count: t.filter(x => ["queued", "running", "pending"].includes(String(x.status))).length },
    { value: "completed", label: "已完成",   count: t.filter(x => x.status === "completed").length },
    { value: "failed",    label: "失败",     count: t.filter(x => ["failed", "error"].includes(String(x.status))).length },
  ];
});

const filteredTasks = computed(() => {
  let out = tasks.value;
  if (statusFilter.value !== "all") {
    if (statusFilter.value === "failed") {
      out = out.filter(t => ["failed", "error"].includes(String(t.status)));
    } else if (statusFilter.value === "running") {
      out = out.filter(t => ["queued", "running", "pending"].includes(String(t.status)));
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
  router.push({ path: "/compare", query: { ids: selectedIds.value.join(","), types: selectedIds.value.map(() => "basic").join(",") } });
}

async function bulkRerun() {
  const rows = tasks.value.filter((t) => selectedIds.value.includes(t.task_id));
  if (!rows.length) return;
  rerunning.value = true;
  let ok = 0;
  let failed = 0;
  try {
    for (const row of rows) {
      try {
        const payload: Record<string, unknown> = { model_id: row.model_id, plan_id: row.plan_id || planId.value };
        if (Array.isArray(row.metric_ids) && row.metric_ids.length) payload.metric_ids = row.metric_ids;
        const accepted = await submitBasic(payload);
        activeTaskId.value = accepted.task_id;
        ok += 1;
      } catch (err) {
        failed += 1;
        toast.error(`重跑失败 ${row.task_id}: ` + String((err as Error)?.message || err));
      }
    }
  } finally {
    rerunning.value = false;
    clearSelection();
    await reload();
    if (activeTaskId.value) beginPolling(activeTaskId.value);
  }
  if (ok && !failed) toast.success(`已重新运行 ${ok} 个任务`);
}

function reload(): Promise<void> {
  if (activeReload) return activeReload;
  refreshing.value = true;
  activeReload = (async () => {
    try {
      tasks.value = await listBasicTasks();
      listError.value = "";
      const taskId = selected.value?.task_id;
      const version = selectionVersion;
      if (taskId) {
        try {
          const detail = await getBasicTask(taskId);
          if (version === selectionVersion && selected.value?.task_id === taskId) selected.value = detail;
        } catch (err) {
          toast.error("刷新任务详情失败: " + String((err as Error)?.message || err));
        }
      }
      if (!activeTaskId.value && !taskIdFromQuery(route.query.task_id)) {
        const running = tasks.value.find(isActiveTask);
        if (running) beginPolling(running.task_id);
      }
    } catch (err) {
      listError.value = err instanceof Error ? err.message : String(err);
      toast.error("加载任务失败: " + listError.value);
    } finally {
      loading.value = false;
      refreshing.value = false;
    }
  })().finally(() => { activeReload = null; });
  return activeReload;
}

function splitMetricIds() {
  // 选择器只提供合法 ID，仍过滤空值以免进入请求。
  return metricIds.value.filter((id) => id.trim());
}

async function submit() {
  if (!store.currentId) {
    toast.warning("请先选择当前模型");
    return;
  }
  submitting.value = true;
  try {
    const payload: Record<string, unknown> = { model_id: store.currentId, plan_id: planId.value };
    const metrics = splitMetricIds();
    if (metrics?.length) payload.metric_ids = metrics;
    const accepted = await submitBasic(payload);
    configurationVisible.value = false;
    toast.info(`评测已提交: ${accepted.task_id}`);
    activeTaskId.value = accepted.task_id;
    await reload();
    await selectTask({ task_id: accepted.task_id });
    beginPolling(accepted.task_id);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

async function selectTask(row: TaskLike) {
  const version = ++selectionVersion;
  selected.value = taskById(tasks.value, row.task_id) || row;
  detailLoading.value = true;
  try {
    const detail = await getBasicTask(row.task_id);
    if (version !== selectionVersion) return;
    selected.value = detail;
    if (isActiveTask(detail)) beginPolling(detail.task_id);
  } catch (err) {
    if (version === selectionVersion) toast.error("加载任务详情失败: " + String((err as Error)?.message || err));
  } finally {
    if (version === selectionVersion) detailLoading.value = false;
  }
}

async function selectTaskAndSync(row: TaskLike) {
  await selectTask(row);
  if (taskIdFromQuery(route.query.task_id) === row.task_id) return;
  await router.replace({ query: { ...route.query, task_id: row.task_id } });
}

async function selectRequestedTask() {
  const taskId = taskIdFromQuery(route.query.task_id);
  if (!taskId || selected.value?.task_id === taskId) return;
  await selectTask({ task_id: taskId });
}

function stopPolling() {
  pollGeneration += 1;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

function beginPolling(taskId: string) {
  stopPolling();
  activeTaskId.value = taskId;
  const generation = pollGeneration;
  let failures = 0;

  const tick = async () => {
    if (generation !== pollGeneration) return;
    pollTimer = null;
    try {
      const task = await getBasicTask(taskId);
      if (generation !== pollGeneration) return;
      failures = 0;
      const index = tasks.value.findIndex((item) => item.task_id === taskId);
      if (index >= 0) tasks.value[index] = task;
      if (selected.value?.task_id === taskId) selected.value = task;
      if (isActiveTask(task)) {
        pollTimer = setTimeout(tick, 1_500);
        return;
      }
      stopPolling();
      activeTaskId.value = null;
      await reload();
      if (task.status === "completed") toast.success(`基础评测完成: ${task.task_id}`);
      else toast.warning(`基础评测未完成: ${task.status || "unknown"}`);
    } catch (err) {
      if (generation !== pollGeneration) return;
      failures += 1;
      if (failures === 1) {
        toast.error("任务状态刷新失败，将自动重试: " + String((err as Error)?.message || err));
      }
      pollTimer = setTimeout(tick, Math.min(5_000, 1_500 * failures));
    }
  };

  void tick();
}

async function cancelSelected() {
  if (!selected.value || !isActiveTask(selected.value)) return;
  try {
    await cancelBasicTask(selected.value.task_id);
    stopPolling();
    activeTaskId.value = null;
    await reload();
    selected.value = await getBasicTask(selected.value.task_id);
    toast.info("任务已取消");
  } catch (err) {
    toast.error("取消任务失败: " + String((err as Error)?.message || err));
  }
}

const reportSource = ref<string>("");
function buildReport(t: any): string {
  if (!t) return "";
  const out: string[] = [];
  out.push("# " + (t.task_id || "任务") + " · 基础评测报告");
  out.push("");
  out.push("> 模型 **" + (t.model_id || "-") + "** · 计划 `" + (t.plan_id || "-") + "`");
  out.push("");
  out.push("## 概览");
  out.push("");
  out.push("| 字段 | 值 |");
  out.push("| --- | --- |");
  out.push("| 状态 | `" + (t.status || "-") + "` |");
  out.push("| 耗时 | " + (t.duration_ms ? Math.round(Number(t.duration_ms)) + " ms" : "-") + " |");
  out.push("| 开始 | " + (formatDate(t.started_at) || "-") + " |");
  out.push("| 完成 | " + (formatDate(t.finished_at) || "-") + " |");
  out.push("");
  if (Array.isArray(t.results) && t.results.length) {
    out.push("## 指标结果");
    out.push("");
    out.push("| 指标 | 状态 | 摘要 |");
    out.push("| --- | --- | --- |");
    for (const m of t.results) {
      out.push("| `" + (m.metric_name || "-") + "` | " + (m.status || "-") + " | " + (m.summary || "-") + " |");
    }
    out.push("");
  }
  if (t.error) {
    out.push("## 错误");
    out.push("");
    out.push("```json");
    out.push(JSON.stringify(t.error, null, 2));
    out.push("```");
  }
  return out.join("\n");
}
watch(selected, (v) => { reportSource.value = v ? buildReport(v) : ""; }, { immediate: true });
watch(() => route.query.task_id, () => { void selectRequestedTask(); });
onMounted(async () => {
  await reload();
  await selectRequestedTask();
  fetchMetrics().then((items) => { metricOptions.value = items; }).catch(() => { metricOptions.value = []; });
});
onBeforeUnmount(stopPolling);
</script>

<template>
  <PageHero
    eyebrow="BASIC SMOKE"
    title="基础评测"
    description="检查网关连通、协议兼容与工程指标，快速确认模型接入链路。"
  >
    <template #actions>
      <el-button :icon="Refresh" :loading="refreshing" @click="reload()">刷新数据</el-button>
      <el-button type="primary" :icon="Plus" @click="configurationVisible = true">新建基础评测</el-button>
    </template>
  </PageHero>
  <EvaluationWorkspace
    v-model:configuration-visible="configurationVisible"
    lane="basic" :task-count="tasks.length" :model-name="store.currentModel?.name || store.currentId || '未选择模型'"
    :auto-updating="Boolean(activeTaskId)" detail-title="基础评测结果"
    :detail-description="detailLoading ? '正在读取任务详情…' : '协议与工程 Smoke，不替代正式压测或能力评测'"
    configuration-title="新建基础评测" configuration-description="选择评测计划与指标，提交后可在工作台跟踪进度和查看报告。"
  >
    <template #configuration>
      <el-form label-position="top" class="lb-eval-form">
        <el-form-item label="评测计划">
          <el-select v-model="planId" class="full-width" aria-label="评测计划">
            <el-option label="网关接入验收 V1" value="gateway_acceptance_v1" />
          </el-select>
          <p class="lb-eval-form__help">gateway_acceptance_v1 · 覆盖连通性、流式规范、长度、错误处理、Usage 与缓存信号。</p>
        </el-form-item>
        <el-form-item label="指定指标 (可选)">
          <el-select v-model="metricIds" class="full-width" aria-label="指定指标" multiple collapse-tags collapse-tags-tooltip :max-collapse-tags="3" clearable placeholder="使用计划默认指标">
            <el-option v-for="m in metricOptions" :key="m.id" :label="`${m.name} (${m.id})`" :value="m.id" />
          </el-select>
          <p class="lb-eval-form__help">不指定时使用后端默认指标组合；指定后只执行勾选的指标。</p>
        </el-form-item>
      </el-form>
      <div class="lb-eval-defaults"><strong>接入检查，不是上线判定</strong><p>这里只采集协议与工程事实。正式吞吐、延迟分布和模型能力，请使用对应的压测与能力评测页面。</p></div>
    </template>
    <template #configuration-footer>
      <el-button @click="configurationVisible = false">返回工作台</el-button>
      <el-button type="primary" :icon="VideoPlay" :loading="submitting" :disabled="!store.currentId || Boolean(activeTaskId)" @click="submit">{{ activeTaskId ? '评测运行中' : '开始基础评测' }}</el-button>
    </template>

    <template #list>
      <div class="lb-eval-toolbar">
        <el-input
          v-model="queryText"
          placeholder="搜索任务 ID / 模型"
          clearable
          aria-label="搜索基础任务"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button text circle :icon="Refresh" :loading="refreshing" aria-label="刷新基础任务" @click="reload()" />
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
      <el-table
        ref="taskTable"
        v-loading="loading"
        :data="filteredTasks"
        :max-height="520"
        highlight-current-row
        :row-key="(r: TaskLike) => r.task_id"
        @selection-change="(rows: TaskLike[]) => (selectedIds = rows.map(r => r.task_id))"
        :current-row-key="selected?.task_id"
        @row-click="(row, column) => column?.type !== 'selection' && selectTaskAndSync(row as TaskLike)"
        empty-text=""
      >
        <el-table-column type="selection" width="36" :reserve-selection="true" />
        <el-table-column prop="task_id" label="任务 / 模型" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <button type="button" class="lb-eval-task-link" :aria-label="`查看任务 ${row.task_id}`" @click.stop="selectTaskAndSync(row as TaskLike)"><strong>{{ modelName(row.model_id) }}</strong><small>{{ row.task_id }}</small></button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="84">
          <template #default="{ row }"><StatusTag :status="row.status" compact /></template>
        </el-table-column>
        <el-table-column label="耗时" width="76">
          <template #default="{ row }">
            <span class="lb-eval-numeric" :title="row.duration_ms != null ? `${row.duration_ms} ms` : undefined">{{ formatEvaluationDuration(row.duration_ms) }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState v-if="shouldShowTaskListEmpty(loading, listError, filteredTasks.length)" :title="hasFilters ? '无匹配任务' : '暂无基础评测任务'" :description="hasFilters ? '试着清空筛选条件。' : '新建一次接入检查，结果会保留在这里。'" :variant="hasFilters ? 'search' : 'list'" :action-label="hasFilters ? '清空筛选' : '新建基础评测'" @action="emptyAction" />
        </template>
      </el-table>
    </template>

    <template #detail-actions>
      <StatusTag v-if="selected" :status="selected.status ?? 'pending'" />
      <el-button v-if="isActiveTask(selected)" size="small" type="danger" plain @click="cancelSelected">取消任务</el-button>
    </template>
    <template #detail>
      <EmptyState
        v-if="!selected"
        title="尚未选择任务"
        description="选择一条任务，查看指标摘要、执行信息和评测报告。"
        variant="list"
      />
      <template v-else>
        <div class="lb-eval-task-title">
          <div><strong>{{ modelName(selected.model_id) }}</strong><code>{{ selected.task_id }}</code></div>
          <el-link v-if="selected.report_path" type="primary" :icon="Document" :href="`/api/reports/${selected.task_id}`" target="_blank">打开报告</el-link>
        </div>
        <div class="lb-eval-stats">
          <div class="lb-eval-stat"><span>已完成指标</span><strong>{{ hasMetricResults ? metricCounts.completed : '—' }}</strong><small>仅表示执行完成</small></div>
          <div class="lb-eval-stat" :class="{ 'lb-eval-stat--danger': metricCounts.errors > 0 }"><span>执行异常</span><strong>{{ hasMetricResults ? metricCounts.errors : '—' }}</strong><small>指标异常数</small></div>
          <div class="lb-eval-stat"><span>已跳过指标</span><strong>{{ hasMetricResults ? metricCounts.skipped : '—' }}</strong><small>保留跳过原因</small></div>
          <div class="lb-eval-stat" :title="selected.duration_ms != null ? `${selected.duration_ms} ms` : undefined"><span>任务耗时</span><strong class="lb-basic-duration">{{ formatEvaluationDuration(selected.duration_ms) }}</strong><small>原始耗时可悬停查看</small></div>
        </div>

        <div v-if="isActiveTask(selected)" class="lb-eval-progress" role="status" aria-live="polite"><div class="lb-eval-progress__head"><strong>任务正在后台运行</strong><span>自动更新</span></div><p class="lb-eval-note">已完成的指标会陆续展示，可以继续浏览历史任务。</p></div>

        <el-alert v-if="selected.error" class="lb-eval-alert" :type="selected.status === 'interrupted' ? 'warning' : 'error'" :closable="false">
          <template #title>
            <strong>{{ selected.status === "interrupted" ? "任务已取消" : "执行错误" }}</strong>
          </template>
          <pre class="lb-eval-error">{{ JSON.stringify(selected.error, null, 2) }}</pre>
        </el-alert>

        <el-tabs v-model="detailTab" class="lb-eval-tabs">
          <el-tab-pane :label="`指标结果${hasMetricResults ? ' · ' + metricCounts.total : ''}`" name="metrics">
            <el-skeleton v-if="detailLoading" :rows="5" animated />
            <div v-else-if="Array.isArray(selected.results) && selected.results.length" class="lb-basic-metrics">
              <article v-for="m in selected.results" :key="m.metric_name" class="lb-basic-metric">
                <div class="lb-basic-metric__head"><div><strong>{{ metricName(m.metric_name) }}</strong><code>{{ m.metric_name }}</code></div><StatusTag :status="m.status" :label="m.status === 'skipped' ? '已跳过' : undefined" compact /></div>
                <p>{{ m.summary || '暂无摘要，请查看完整报告。' }}</p>
              </article>
            </div>
            <EmptyState v-else :title="isActiveTask(selected) ? '等待指标结果' : '暂无指标结果'" description="结果产生后会显示在这里；执行异常请查看上方提示。" />
          </el-tab-pane>
          <el-tab-pane label="报告预览" name="report"><MarkdownReport :source="reportSource" max-height="640px" /></el-tab-pane>
          <el-tab-pane label="任务信息" name="info">
            <TaskTimeline :status="selected.status" :started_at="selected.started_at" :finished_at="selected.finished_at" :error="selected.error" />
            <dl class="lb-eval-meta">
              <div><dt>模型配置 ID</dt><dd class="lb-eval-mono">{{ selected.model_id || '—' }}</dd></div>
              <div><dt>评测计划</dt><dd class="lb-eval-mono">{{ selected.plan_id || '—' }}</dd></div>
              <div><dt>开始时间</dt><dd>{{ formatDate(selected.started_at) }}</dd></div>
              <div><dt>完成时间</dt><dd>{{ formatDate(selected.finished_at) }}</dd></div>
              <div class="lb-eval-meta__wide"><dt>指定指标</dt><dd>{{ Array.isArray(selected.metric_ids) ? selected.metric_ids.join('、') : '使用计划默认指标' }}</dd></div>
            </dl>
          </el-tab-pane>
        </el-tabs>
      </template>
    </template>
  </EvaluationWorkspace>
</template>

<style scoped>
.lb-basic-metrics { display: grid; gap: 12px; }
.lb-basic-metric { padding: 16px; border: 1px solid var(--lb-border); border-radius: 10px; }
.lb-basic-metric__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.lb-basic-metric__head > div { min-width: 0; }
.lb-basic-metric__head strong { display: block; color: var(--lb-fg-strong); font-size: 13px; font-weight: 500; }
.lb-basic-metric__head code { display: block; margin-top: 5px; color: var(--lb-muted); font: 10px var(--font-mono); overflow-wrap: anywhere; }
.lb-basic-metric p { margin: 12px 0 0; color: var(--lb-fg-soft); font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; }
.lb-eval-stat .lb-basic-duration { font-size: 16px; line-height: 1.65; }
</style>
