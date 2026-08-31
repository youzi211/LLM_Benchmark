<script setup lang="ts">
/**
 * 任务对比 (Phase 4.2)
 * 接受 ?ids=a,b,c&types=basic,stress,intelligence, 并排显示每个任务的关键指标.
 * 适合选 2-4 个同类型任务做横向对比 (e.g. 同一模型不同版本, 或同一任务不同模型).
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useToast } from "@/composables/useToast";
import PageHero from "@/components/layouts/PageHero.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusDot from "@/components/common/StatusDot.vue";
import { Close, Download } from "@element-plus/icons-vue";
import { getBasicTask, getStressTask, getIntelligenceTask, type TaskLike } from "@/api/evaluations";

const route = useRoute();
const router = useRouter();
const toast = useToast();

interface Column {
  id: string;
  type: "basic" | "stress" | "intelligence";
  task: TaskLike | null;
  loading: boolean;
  error?: string;
}

const columns = ref<Column[]>([]);
const loading = ref(true);

function parseQuery() {
  const ids = String(route.query.ids || "").split(",").filter(Boolean);
  const types = String(route.query.types || "").split(",").filter(Boolean);
  if (!ids.length) return [];
  const cols: Column[] = ids.map((id, i) => ({
    id,
    type: (types[i] as Column["type"]) || "basic",
    task: null,
    loading: true,
  }));
  return cols;
}

async function fetchOne(col: Column) {
  try {
    let data: TaskLike;
    if (col.type === "stress") data = await getStressTask(col.id, true);
    else if (col.type === "intelligence") data = await getIntelligenceTask(col.id, true);
    else data = await getBasicTask(col.id);
    col.task = data;
  } catch (err) {
    col.error = String((err as Error)?.message || err);
  } finally {
    col.loading = false;
  }
}

async function reload() {
  loading.value = true;
  columns.value = parseQuery();
  if (!columns.value.length) {
    loading.value = false;
    return;
  }
  await Promise.all(columns.value.map(fetchOne));
  loading.value = false;
}

onMounted(reload);
watch(() => route.query.ids, reload);

function back() {
  const types = String(route.query.types || "basic").split(",")[0];
  router.push("/" + (types || "basic"));
}

function removeCol(id: string) {
  const remaining = columns.value.filter(c => c.id !== id);
  const newQuery: Record<string, string> = {
    ids: remaining.map(c => c.id).join(","),
    types: remaining.map(c => c.type).join(","),
  };
  router.replace({ path: "/compare", query: newQuery });
}

function exportCsv() {
  if (!columns.value.length) return;
  const header = ["任务 ID", "类型", "模型", "状态", "耗时(ms)", "指标数"];
  const rows = columns.value.map(c => {
    const t = c.task;
    return [
      c.id,
      c.type,
      t?.model_id || "-",
      t?.status || "-",
      t?.duration_ms ? Math.round(Number(t.duration_ms)) : "-",
      Array.isArray(t?.results) ? t.results.length : 0,
    ];
  });
  const csv = [header, ...rows].map(r => r.map(cell => `"${String(cell).replace(/"/g, "''")}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `task-compare-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast.success("已导出 CSV");
}

// 收集所有出现过的指标 key
const allMetricKeys = computed(() => {
  const set = new Set<string>();
  columns.value.forEach(c => {
    if (Array.isArray(c.task?.results)) {
      c.task!.results.forEach((m: any) => {
        if (m.metric_name) set.add(m.metric_name);
      });
    }
  });
  return Array.from(set);
});

function metricFor(col: Column, key: string) {
  if (!col.task || !Array.isArray(col.task.results)) return null;
  return col.task.results.find((m: any) => m.metric_name === key) || null;
}

function getModelName(col: Column) {
  return col.task?.model_id || "-";
}
function getStatus(c: Column) {
  return c.task?.status || "-";
}
function getDuration(c: Column) {
  return c.task?.duration_ms ? Math.round(Number(c.task.duration_ms)) + " ms" : "-";
}
function getMetricCount(c: Column) {
  return Array.isArray(c.task?.results) ? c.task!.results.length : 0;
}
</script>

<template>
  <div class="lb-cmp">
    <PageHero
      eyebrow="COMPARE"
      :title="columns.length ? `对比 ${columns.length} 个任务` : '任务对比'"
      description="横向对比多个任务的指标、状态与耗时。适合在同模型不同版本, 或同任务不同模型间做快速对比。"
    >
      <template #actions>
        <el-button size="small" :icon="Download" :disabled="!columns.length" @click="exportCsv">导出 CSV</el-button>
        <el-button size="small" @click="back">返回列表</el-button>
      </template>
    </PageHero>

    <EmptyState
      v-if="!loading && !columns.length"
      title="还没有选中任务"
      description="从基础 / 压测 / 能力 任务列表, 勾选 2-4 个任务后, 通过'对比'按钮打开此页。"
      variant="search"
      action-label="返回基础评测"
      @action="back"
    />

    <div v-else class="lb-cmp__board" v-loading="loading">
      <div v-for="col in columns" :key="col.id" class="lb-cmp__col">
        <div class="lb-cmp__col-head">
          <div class="lb-cmp__col-id">{{ col.id }}</div>
          <el-button text size="small" @click="removeCol(col.id)" :icon="Close" title="移除此列" />
        </div>
        <div class="lb-cmp__col-type">{{ col.type === "basic" ? "基础评测" : col.type === "stress" ? "压测评测" : "能力评测" }}</div>

        <div v-if="col.error" class="lb-cmp__error">{{ col.error }}</div>
        <div v-else-if="col.loading" class="lb-cmp__loading">加载中…</div>
        <template v-else-if="col.task">
          <div class="lb-cmp__metric">
            <span class="lb-cmp__metric-label">状态</span>
            <StatusTag :status="getStatus(col)" />
          </div>
          <div class="lb-cmp__metric">
            <span class="lb-cmp__metric-label">模型</span>
            <span class="lb-cmp__metric-value">{{ getModelName(col) }}</span>
          </div>
          <div class="lb-cmp__metric">
            <span class="lb-cmp__metric-label">耗时</span>
            <span class="lb-cmp__metric-value">{{ getDuration(col) }}</span>
          </div>
          <div class="lb-cmp__metric">
            <span class="lb-cmp__metric-label">指标数</span>
            <span class="lb-cmp__metric-value">{{ getMetricCount(col) }}</span>
          </div>
        </template>
      </div>
    </div>

    <!-- 指标横向对比表 -->
    <div v-if="columns.length && allMetricKeys.length" class="lb-cmp__table-wrap">
      <h3 class="lb-cmp__table-title">指标对比</h3>
      <div class="lb-cmp__table-scroll">
        <table class="lb-cmp__table">
          <thead>
            <tr>
              <th class="lb-cmp__th-key">指标</th>
              <th v-for="col in columns" :key="col.id" class="lb-cmp__th-col">
                <div class="lb-cmp__th-id">{{ col.id }}</div>
                <div class="lb-cmp__th-type">{{ col.type }}</div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in allMetricKeys" :key="key">
              <td class="lb-cmp__td-key">{{ key }}</td>
              <td v-for="col in columns" :key="col.id" class="lb-cmp__td-cell">
                <template v-if="metricFor(col, key)">
                  <div class="lb-cmp__cell-head">
                    <StatusTag :status="metricFor(col, key).status" compact />
                    <StatusDot :state="metricFor(col, key).status === 'completed' ? 'ok' : metricFor(col, key).status === 'failed' ? 'fail' : 'pending'" :size="6" :pulse="false" />
                  </div>
                  <div class="lb-cmp__cell-summary" :title="metricFor(col, key).summary">{{ metricFor(col, key).summary || '—' }}</div>
                </template>
                <span v-else class="lb-cmp__cell-empty">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <EmptyState
      v-else-if="!loading && columns.length && !allMetricKeys.length"
      title="这些任务都没有指标结果"
      description="选中的任务可能还未完成, 或不包含结构化指标。"
      variant="list"
    />
  </div>
</template>

<style scoped>
.lb-cmp {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lb-cmp__board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.lb-cmp__col {
  padding: 14px 16px;
  background: var(--lb-surface);
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  box-shadow: var(--lb-shadow);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lb-cmp__col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.lb-cmp__col-id {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-primary);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1 1 auto;
}

.lb-cmp__col-type {
  font-size: 11px;
  color: var(--lb-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}

.lb-cmp__metric {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  background: var(--lb-surface-soft);
  border-radius: 6px;
}

.lb-cmp__metric-label {
  font-size: 11.5px;
  color: var(--lb-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}

.lb-cmp__metric-value {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-fg-strong);
  font-weight: 500;
}

.lb-cmp__loading,
.lb-cmp__error {
  padding: 16px;
  text-align: center;
  color: var(--lb-muted);
  font-size: 12.5px;
}

.lb-cmp__error {
  color: var(--lb-danger);
  background: var(--lb-danger-bg);
  border-radius: 6px;
}

.lb-cmp__table-wrap {
  padding: 18px 20px;
  background: var(--lb-surface);
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  box-shadow: var(--lb-shadow);
}

.lb-cmp__table-title {
  margin: 0 0 12px;
  font-family: "Fira Code", monospace;
  font-size: 14px;
  color: var(--lb-fg-strong);
  font-weight: 600;
}

.lb-cmp__table-scroll {
  overflow-x: auto;
}

.lb-cmp__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.lb-cmp__table th,
.lb-cmp__table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--lb-border-soft);
  text-align: left;
  vertical-align: top;
}

.lb-cmp__th-key {
  width: 200px;
  font-weight: 600;
  color: var(--lb-fg-strong);
  background: var(--lb-surface-soft);
  position: sticky;
  left: 0;
  z-index: 1;
}

.lb-cmp__th-col {
  min-width: 180px;
  background: var(--lb-surface-soft);
  font-weight: 500;
}

.lb-cmp__th-id {
  font-family: "Fira Code", monospace;
  font-size: 11.5px;
  color: var(--lb-primary);
  font-weight: 500;
}

.lb-cmp__th-type {
  font-size: 10.5px;
  color: var(--lb-muted);
  margin-top: 2px;
}

.lb-cmp__td-key {
  font-family: "Fira Code", monospace;
  font-size: 12px;
  color: var(--lb-fg-strong);
  font-weight: 500;
  background: var(--lb-surface);
  position: sticky;
  left: 0;
}

.lb-cmp__td-cell {
  background: var(--lb-surface);
}

.lb-cmp__cell-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.lb-cmp__cell-summary {
  font-size: 11.5px;
  color: var(--lb-fg-soft);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.lb-cmp__cell-empty {
  color: var(--lb-muted);
  font-size: 12px;
}
</style>
