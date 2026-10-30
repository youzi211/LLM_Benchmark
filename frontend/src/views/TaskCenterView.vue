<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Refresh, Search } from "@element-plus/icons-vue";
import PageHero from "@/components/layouts/PageHero.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import FilterChips from "@/components/common/FilterChips.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import {
  formatDate,
  listBasicTasks,
  listIntelligenceTasks,
  listStressTasks,
} from "@/api/evaluations";
import {
  TASK_CENTER_LANES,
  TASK_CENTER_LANE_META,
  buildTaskCenterItems,
  filterTaskCenterItems,
  taskDetailLocation,
  type TaskCenterFilter,
  type TaskCenterItem,
  type TaskCenterLane,
  type TaskCenterSources,
} from "@/utils/taskCenter";

const router = useRouter();
const loading = ref(false);
const queryText = ref("");
const laneFilter = ref<string>("all");
const statusFilter = ref<string>("all");
const sources = ref<TaskCenterSources>({
  basic: null,
  stress: null,
  intelligence: null,
});
const errors = ref<Record<TaskCenterLane, string>>({
  basic: "",
  stress: "",
  intelligence: "",
});

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

async function reload() {
  loading.value = true;
  try {
    const [basic, stress, intelligence] = await Promise.allSettled([
      listBasicTasks(),
      listStressTasks(),
      listIntelligenceTasks(),
    ]);
    sources.value = {
      basic: basic.status === "fulfilled" ? basic.value : null,
      stress: stress.status === "fulfilled" ? stress.value : null,
      intelligence: intelligence.status === "fulfilled" ? intelligence.value : null,
    };
    errors.value = {
      basic: basic.status === "rejected" ? errorMessage(basic.reason) : "",
      stress: stress.status === "rejected" ? errorMessage(stress.reason) : "",
      intelligence: intelligence.status === "rejected" ? errorMessage(intelligence.reason) : "",
    };
  } finally {
    loading.value = false;
  }
}

const items = computed(() => buildTaskCenterItems(sources.value));
const failedLanes = computed(() =>
  TASK_CENTER_LANES.filter((lane) => Boolean(errors.value[lane])),
);
const laneScopedItems = computed(() =>
  laneFilter.value === "all"
    ? items.value
    : items.value.filter((item) => item.lane === laneFilter.value),
);
const laneOptions = computed(() => [
  { value: "all", label: "全部评测线", count: items.value.length },
  ...TASK_CENTER_LANES.map((lane) => ({
    value: lane,
    label: TASK_CENTER_LANE_META[lane].label,
    count: items.value.filter((item) => item.lane === lane).length,
  })),
]);
const statusOptions = computed(() => [
  { value: "all", label: "全部状态", count: laneScopedItems.value.length },
  {
    value: "active",
    label: "进行中",
    count: laneScopedItems.value.filter((item) => ["queued", "running", "pending"].includes(item.status)).length,
  },
  {
    value: "completed",
    label: "已完成",
    count: laneScopedItems.value.filter((item) => item.status === "completed").length,
  },
  {
    value: "attention",
    label: "需关注",
    count: laneScopedItems.value.filter((item) => ["failed", "error", "interrupted"].includes(item.status)).length,
  },
]);
const filteredItems = computed(() =>
  filterTaskCenterItems(items.value, {
    lane: laneFilter.value as TaskCenterFilter["lane"],
    status: statusFilter.value as TaskCenterFilter["status"],
    query: queryText.value,
  }),
);

function formatDuration(durationMs: number | null): string {
  if (durationMs === null) return "—";
  if (durationMs < 1_000) return `${Math.round(durationMs)} ms`;
  if (durationMs < 60_000) return `${(durationMs / 1_000).toFixed(1)} s`;
  const minutes = Math.floor(durationMs / 60_000);
  const seconds = Math.round((durationMs % 60_000) / 1_000);
  return `${minutes}m ${seconds}s`;
}

function lastActivity(item: TaskCenterItem): string {
  return item.timestamp ? formatDate(new Date(item.timestamp).toISOString()) : "—";
}

function openTask(item: TaskCenterItem) {
  router.push(taskDetailLocation(item.lane, item.id));
}

function clearFilters() {
  queryText.value = "";
  laneFilter.value = "all";
  statusFilter.value = "all";
}

onMounted(reload);
</script>

<template>
  <div class="task-center">
    <PageHero
      eyebrow="TASK CENTER"
      title="任务中心"
      description="汇总基础、压测与能力三条评测线各最近 50 条任务；点击任意任务即可进入原详情页继续分析。"
    >
      <template #actions>
        <el-button size="small" :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
      </template>
    </PageHero>

    <el-alert
      v-if="failedLanes.length"
      class="task-center__alert"
      :type="failedLanes.length === TASK_CENTER_LANES.length ? 'error' : 'warning'"
      :closable="false"
      show-icon
      role="alert"
      :title="`${failedLanes.map((lane) => TASK_CENTER_LANE_META[lane].label).join('、')}加载失败`"
    >
      <template #default>
        其余评测线仍可继续查看。失败原因：{{ failedLanes.map((lane) => errors[lane]).join('；') }}
      </template>
    </el-alert>

    <el-card class="panel-card task-center__panel" shadow="never">
      <div class="task-center__toolbar">
        <el-input
          v-model="queryText"
          clearable
          placeholder="搜索任务 ID / 模型"
          class="task-center__search"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <span class="task-center__count" role="status" aria-live="polite">
          显示 {{ filteredItems.length }} / {{ items.length }} 个任务
        </span>
      </div>

      <div class="task-center__filters">
        <FilterChips v-model="laneFilter" :options="laneOptions" show-count size="small" />
        <span class="task-center__divider" aria-hidden="true"></span>
        <FilterChips v-model="statusFilter" :options="statusOptions" show-count size="small" />
      </div>

      <el-table
        v-if="loading || filteredItems.length"
        v-loading="loading"
        :data="filteredItems"
        height="560"
        row-key="id"
        highlight-current-row
        class="task-center__table"
        empty-text=""
        @row-click="openTask"
      >
        <el-table-column label="评测线" width="112">
          <template #default="{ row }">
            <span :class="['task-center__lane', `task-center__lane--${row.lane}`]">
              {{ TASK_CENTER_LANE_META[row.lane as TaskCenterLane].label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="任务 ID" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="task-center__id">{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="model" label="模型" min-width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="112">
          <template #default="{ row }"><StatusTag :status="row.status" compact /></template>
        </el-table-column>
        <el-table-column label="最近活动" width="176">
          <template #default="{ row }">
            <span class="task-center__time">{{ lastActivity(row as TaskCenterItem) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="106">
          <template #default="{ row }">
            <span class="task-center__duration">{{ formatDuration(row.durationMs) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="78" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openTask(row as TaskCenterItem)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-else
        :variant="failedLanes.length === TASK_CENTER_LANES.length ? 'error' : queryText ? 'search' : 'list'"
        :title="failedLanes.length === TASK_CENTER_LANES.length ? '任务数据加载失败' : items.length ? '无匹配任务' : '暂无评测任务'"
        :description="failedLanes.length === TASK_CENTER_LANES.length ? '请检查服务状态后重新加载。' : items.length ? '试着调整评测线、状态或搜索条件。' : '从基础评测、压测评测或能力评测启动第一个任务。'"
        :action-label="failedLanes.length === TASK_CENTER_LANES.length ? '重新加载' : items.length ? '清空筛选' : '去基础评测'"
        @action="failedLanes.length === TASK_CENTER_LANES.length ? reload() : items.length ? clearFilters() : router.push('/basic')"
      />
    </el-card>
  </div>
</template>

<style scoped>
.task-center {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.task-center__alert {
  margin: 0;
}

.task-center__panel {
  min-width: 0;
}

.task-center__toolbar,
.task-center__filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.task-center__toolbar {
  justify-content: space-between;
  margin-bottom: 12px;
}

.task-center__search {
  width: min(360px, 100%);
}

.task-center__count {
  color: var(--lb-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.task-center__filters {
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--lb-border-soft);
}

.task-center__divider {
  width: 1px;
  height: 20px;
  background: var(--lb-border);
}

.task-center__table :deep(.el-table__body tr) {
  cursor: pointer;
}

.task-center__lane {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
}

.task-center__lane--basic {
  color: var(--lb-info);
  background: var(--lb-accent-soft);
}

.task-center__lane--stress {
  color: var(--lb-warning);
  background: rgba(217, 119, 6, 0.10);
}

.task-center__lane--intelligence {
  color: var(--lb-success);
  background: var(--lb-success-tint);
}

.task-center__id,
.task-center__duration {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--lb-fg-soft);
  font-variant-numeric: tabular-nums;
}

.task-center__id {
  color: var(--lb-primary);
}

.task-center__time {
  color: var(--lb-muted);
  font-size: 12px;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .task-center__toolbar {
    align-items: stretch;
  }

  .task-center__search {
    width: 100%;
  }

  .task-center__count {
    align-self: flex-end;
  }

  .task-center__divider {
    display: none;
  }
}
</style>
