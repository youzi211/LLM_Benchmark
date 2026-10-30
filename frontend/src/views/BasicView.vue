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
import { Search } from "@element-plus/icons-vue";
import { cancelBasicTask, formatDate, getBasicTask, listBasicTasks, submitBasic, type TaskLike } from "@/api/evaluations";
import { taskIdFromQuery } from "@/utils/taskCenter";

const route = useRoute();
const router = useRouter();
const toast = useToast();
const store = useModelsStore();
const loading = ref(false);
const submitting = ref(false);
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
const planId = ref("gateway_acceptance_v1");
const metricIds = ref("");

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
  router.push({ path: "/compare", query: { ids: selectedIds.value.join(","), types: "basic" } });
}

function bulkRerun() {
  toast.info(`已请求重新运行 ${selectedIds.value.length} 个任务`);
  selectedIds.value = [];
}

async function reload() {
  loading.value = true;
  try {
    tasks.value = await listBasicTasks();
    if (selected.value) selected.value = await getBasicTask(selected.value.task_id);
    if (!activeTaskId.value && !taskIdFromQuery(route.query.task_id)) {
      const running = tasks.value.find(isActiveTask);
      if (running) beginPolling(running.task_id);
    }
  } catch (err) {
    toast.error("加载任务失败: " + String((err as Error)?.message || err));
  } finally {
    loading.value = false;
  }
}

function splitMetricIds() {
  const raw = metricIds.value.trim();
  return raw ? raw.split(/[\uFF0C,\s]+/).filter(Boolean) : undefined;
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
    toast.info(`评测已提交: ${accepted.task_id}`);
    activeTaskId.value = accepted.task_id;
    await reload();
    selected.value = await getBasicTask(accepted.task_id);
    beginPolling(accepted.task_id);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

async function selectTask(row: TaskLike) {
  selected.value = await getBasicTask(row.task_id);
  if (isActiveTask(selected.value)) beginPolling(selected.value.task_id);
}

async function selectTaskAndSync(row: TaskLike) {
  await selectTask(row);
  if (taskIdFromQuery(route.query.task_id) === row.task_id) return;
  await router.replace({ query: { ...route.query, task_id: row.task_id } });
}

async function selectRequestedTask() {
  const taskId = taskIdFromQuery(route.query.task_id);
  if (!taskId || selected.value?.task_id === taskId) return;
  try {
    selected.value = await getBasicTask(taskId);
    if (isActiveTask(selected.value)) beginPolling(taskId);
  } catch (err) {
    toast.error("加载任务详情失败: " + String((err as Error)?.message || err));
  }
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
});
onBeforeUnmount(stopPolling);
</script>

<template>
  <PageHero
    eyebrow="BASIC SMOKE"
    title="基础评测"
    description="验证服务连通、协议兼容、usage、错误结构、上下文与缓存等基础能力。适合在每次接入新模型时跑一次, 确认网关能通。"
  >
    <template #actions>
      <el-button size="small" @click="reload">刷新</el-button>
      <el-button type="primary" :loading="submitting" :disabled="Boolean(activeTaskId)" @click="submit">
        {{ activeTaskId ? "评测运行中" : "开始基础评测" }}
      </el-button>
    </template>
  </PageHero>
  <section class="view-grid">
    <el-card class="panel-card" shadow="never">
      <el-form label-position="top">
        <el-form-item label="当前模型">
          <el-input :model-value="store.currentModel?.name || store.currentId || '未选择模型'" disabled />
        </el-form-item>
        <el-form-item label="评测计划">
          <el-select v-model="planId" class="full-width">
            <el-option label="gateway_acceptance_v1" value="gateway_acceptance_v1" />
          </el-select>
        </el-form-item>
        <el-form-item label="指定指标 (可选, 逗号分隔)">
          <el-input v-model="metricIds" placeholder="connectivity, usage" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="panel-card" shadow="never">
      <div class="card-title__actions">
        <el-input
          v-model="queryText"
          placeholder="搜索任务 ID / 模型"
          clearable
          size="default"
          style="width: 220px;"
        >
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
      <el-table
        v-loading="loading"
        :data="filteredTasks"
        height="480"
        highlight-current-row
        :row-key="(r: TaskLike) => r.task_id"
        @selection-change="(rows: TaskLike[]) => (selectedIds = rows.map(r => r.task_id))"
        @row-click="selectTaskAndSync"
        empty-text=""
      >
        <el-table-column type="selection" width="40" />
        <el-table-column prop="task_id" label="任务" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="lb-tl__id">{{ row.task_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="model_id" label="模型" width="130" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">
            <span class="lb-tl__num">{{ row.duration_ms ? Math.round(Number(row.duration_ms)) + ' ms' : '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState
        v-if="!loading && filteredTasks.length === 0"
        :title="queryText || statusFilter !== 'all' ? '无匹配任务' : '暂无基础评测任务'"
        :description="queryText || statusFilter !== 'all' ? '试着清空筛选条件或在左侧表单启动一次评测' : '点击左侧表单启动第一次评测'"
        :variant="queryText ? 'search' : 'list'"
        :action-label="queryText || statusFilter !== 'all' ? '清空筛选' : '开始基础评测'"
        @action="queryText = ''; statusFilter = 'all';"
      />
    </el-card>

    <el-card class="panel-card detail-card" shadow="never">
      <EmptyState
        v-if="!selected"
        title="尚未选择任务"
        description="从左侧任务列表选择一个任务查看详细进度、指标结果与错误栈。"
        variant="list"
      />
      <template v-else>
        <div class="lb-detail__head">
          <div class="lb-detail__id">{{ selected.task_id }}</div>
          <div class="lb-detail__head-actions">
            <StatusTag :status="selected.status ?? 'pending'" />
            <el-button v-if="isActiveTask(selected)" size="small" type="danger" plain @click="cancelSelected">取消任务</el-button>
          </div>
        </div>
        <div class="lb-detail__meta">
          <div class="lb-detail__meta-item">
            <span class="lb-detail__meta-label">模型</span>
            <span class="lb-detail__meta-value">{{ selected.model_id || '—' }}</span>
          </div>
          <div class="lb-detail__meta-item">
            <span class="lb-detail__meta-label">计划</span>
            <span class="lb-detail__meta-value">{{ selected.plan_id || '—' }}</span>
          </div>
          <div class="lb-detail__meta-item">
            <span class="lb-detail__meta-label">耗时</span>
            <span class="lb-detail__meta-value">{{ selected.duration_ms ? Math.round(Number(selected.duration_ms)) + ' ms' : '—' }}</span>
          </div>
          <div class="lb-detail__meta-item">
            <span class="lb-detail__meta-label">更新时间</span>
            <span class="lb-detail__meta-value">{{ formatDate(selected.updated_at || selected.finished_at || selected.started_at) }}</span>
          </div>
        </div>

        <TaskTimeline :status="selected.status" :started-at="selected.started_at" :finished-at="selected.finished_at" :error="selected.error" />
        <div v-if="isActiveTask(selected)" class="lb-detail__running" role="status" aria-live="polite">
          任务正在后台运行，已完成的指标会自动更新。
        </div>

        <div class="lb-detail__section-title">指标结果 <span class="lb-detail__section-count">{{ Array.isArray(selected.results) ? selected.results.length : 0 }} 个</span></div>
        <div v-if="Array.isArray(selected.results) && selected.results.length" class="lb-detail__metrics">
          <div v-for="m in selected.results" :key="m.metric_name" class="lb-detail__metric">
            <div class="lb-detail__metric-head">
              <span class="lb-detail__metric-name">{{ m.metric_name }}</span>
              <StatusTag :status="m.status" compact />
            </div>
            <div class="lb-detail__metric-summary" :title="m.summary">{{ m.summary || '—' }}</div>
          </div>
        </div>
        <div v-else class="lb-detail__no-metrics">该任务暂无指标结果</div>

        <el-alert v-if="selected.error" class="lb-detail__alert" :type="selected.status === 'interrupted' ? 'warning' : 'error'" :closable="false">
          <template #title>
            <div class="lb-detail__alert-title">{{ selected.status === "interrupted" ? "任务已取消" : "执行错误" }}</div>
          </template>
          <pre class="lb-detail__alert-body">{{ JSON.stringify(selected.error, null, 2) }}</pre>
        </el-alert>

        <div class="lb-detail__section-title">内联报告</div>
        <div class="lb-detail__report-wrap">
          <MarkdownReport :source="reportSource" max-height="420px" />
        </div>

        <el-link v-if="selected.report_path" class="lb-detail__report" type="primary" :href="`/api/reports/${selected.task_id}`" target="_blank">
          打开 Markdown 报告 ↗
        </el-link>
      </template>
    </el-card>
  </section>
</template>

<style scoped>
.card-title__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0 12px;
  border-bottom: 1px solid var(--lb-border-soft);
  margin-bottom: 12px;
}
.lb-tl__filters {
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--lb-border-soft);
}
.lb-tl__id {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-primary);
  font-weight: 500;
}
.lb-tl__num {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-fg-soft);
}
.lb-tl__bulkbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 10px;
  background: var(--lb-accent-soft);
  border: 1px solid var(--lb-accent-soft-2);
  border-radius: 8px;
  font-size: 12.5px;
}
.lb-tl__bulkbar-text {
  color: var(--lb-primary);
  font-weight: 500;
  margin-right: auto;
}
.lb-detail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 10px 14px;
  background: var(--lb-surface-soft);
  border-radius: 10px;
  border: 1px solid var(--lb-border-soft);
}
.lb-detail__head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lb-detail__id {
  font-family: "Fira Code", monospace;
  font-size: 13.5px;
  color: var(--lb-primary);
  font-weight: 600;
}
.lb-detail__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
  margin-bottom: 14px;
}
.lb-detail__running {
  padding: 9px 12px;
  margin-bottom: 12px;
  font-size: 12.5px;
  color: var(--lb-primary);
  background: var(--lb-accent-soft);
  border: 1px solid var(--lb-accent-soft-2);
  border-radius: 8px;
}
.lb-detail__meta-item {
  display: flex;
  flex-direction: column;
  padding: 8px 10px;
  background: var(--lb-surface-soft);
  border-radius: 8px;
  border: 1px solid var(--lb-border-soft);
}
.lb-detail__meta-label {
  font-size: 11px;
  color: var(--lb-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 2px;
}
.lb-detail__meta-value {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-fg-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lb-detail__section-title {
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--lb-fg-strong);
  display: flex;
  align-items: center;
  gap: 8px;
}
.lb-detail__section-count {
  font-family: "Fira Code", monospace;
  font-size: 11.5px;
  color: var(--lb-muted);
  font-weight: 400;
}
.lb-detail__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}
.lb-detail__metric {
  padding: 8px 10px;
  border: 1px solid var(--lb-border-soft);
  border-radius: 8px;
  background: var(--lb-surface-soft);
}
.lb-detail__metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.lb-detail__metric-name {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-fg-strong);
  font-weight: 500;
}
.lb-detail__metric-summary {
  font-size: 12px;
  color: var(--lb-fg-soft);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.lb-detail__no-metrics {
  padding: 16px;
  text-align: center;
  color: var(--lb-muted);
  font-size: 12.5px;
  background: var(--lb-surface-soft);
  border-radius: 8px;
  border: 1px dashed var(--lb-border);
}
.lb-detail__alert {
  margin-top: 12px;
}
.lb-detail__alert-title {
  font-weight: 600;
}
.lb-detail__alert-body {
  margin: 0;
  font-family: "Fira Code", monospace;
  font-size: 11.5px;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}
.lb-detail__report-wrap {
  margin-top: 8px;
  padding: 14px 16px;
  background: var(--lb-surface-soft);
  border: 1px solid var(--lb-border);
  border-radius: 10px;
}
.lb-detail__report {
  display: inline-block;
  margin-top: 12px;
}
</style>
