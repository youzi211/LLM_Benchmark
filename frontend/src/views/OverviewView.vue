<script setup lang="ts">
/**
 * 概览页 (Phase 3.1) - LLM Benchmark 新首页
 * Hero + 4 KPI + 服务健康 + 运行中 + 最近活动
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useModelsStore } from "@/stores/models";
import { useHealthStore } from "@/stores/health";
import { useToast } from "@/composables/useToast";
import PageHero from "@/components/layouts/PageHero.vue";
import KpiCard from "@/components/overview/KpiCard.vue";
import ServiceHealth from "@/components/overview/ServiceHealth.vue";
import RunningTasks from "@/components/overview/RunningTasks.vue";
import StatusDot from "@/components/common/StatusDot.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { ArrowRight, Clock, Refresh, Aim } from "@element-plus/icons-vue";
import {
  fetchTaskOverviewSummary,
  formatDate,
  listBasicTasks,
  listIntelligenceTasks,
  listStressTasks,
  type TaskOverviewSummary,
} from "@/api/evaluations";
import {
  buildOverviewTaskSummary,
  type OverviewLane,
  type OverviewTaskSources,
} from "@/overview/taskOverview";

const router = useRouter();
const store = useModelsStore();
const healthStore = useHealthStore();
const toast = useToast();

const tasksLoading = ref(true);
const summaryLoading = ref(true);
const sources = ref<OverviewTaskSources>({
  basic: null,
  stress: null,
  intelligence: null,
});
const stats = ref<TaskOverviewSummary | null>(null);
const statsError = ref("");

const LANE_LABELS: Record<OverviewLane, string> = {
  basic: "基础评测",
  stress: "压测任务",
  intelligence: "能力评测",
};

// /health 由 MainLayout 统一轮询，概览页只读取结果。
const health = computed(() => healthStore.status);

const refreshing = computed(() => tasksLoading.value || summaryLoading.value);

async function reloadTasks() {
  tasksLoading.value = true;
  try {
    const [b, s, i] = await Promise.allSettled([
      listBasicTasks(),
      listStressTasks(),
      listIntelligenceTasks(),
    ]);
    sources.value = {
      basic: b.status === "fulfilled" ? b.value : null,
      stress: s.status === "fulfilled" ? s.value : null,
      intelligence: i.status === "fulfilled" ? i.value : null,
    };
  } finally {
    tasksLoading.value = false;
  }
}

async function reloadSummary() {
  summaryLoading.value = true;
  try {
    const summary = await fetchTaskOverviewSummary();
    stats.value = summary;
    statsError.value = "";
  } catch (err) {
    stats.value = null;
    statsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    summaryLoading.value = false;
  }
}

async function reload() {
  await Promise.all([reloadTasks(), reloadSummary()]);
}

onMounted(async () => {
  await Promise.all([store.load(), reload()]);
});

const taskSummary = computed(() => buildOverviewTaskSummary(sources.value));
const failedLaneLabels = computed(() =>
  taskSummary.value.failedLanes.map((lane) => LANE_LABELS[lane]),
);
const taskDataError = computed(() => !tasksLoading.value && failedLaneLabels.value.length > 0);
const statsUnavailable = computed(() => !summaryLoading.value && statsError.value !== "");
const allTaskDataFailed = computed(() =>
  !tasksLoading.value && taskSummary.value.failedLanes.length === Object.keys(LANE_LABELS).length,
);
const taskErrorTitle = computed(() =>
  allTaskDataFailed.value ? "任务数据加载失败" : "部分任务数据不可用",
);
const runningError = computed(() =>
  allTaskDataFailed.value ? "任务列表加载失败，请稍后重试。" : "",
);
const runningPartialError = computed(() =>
  taskDataError.value && !allTaskDataFailed.value
    ? `${failedLaneLabels.value.join("、")}加载失败`
    : "",
);
const recentEmptyText = computed(() =>
  taskDataError.value ? "部分任务数据不可用" : "暂无已结束任务",
);
const completionRateText = computed(() =>
  stats.value?.completion_rate == null ? "—" : `${stats.value.completion_rate.toFixed(1)}%`,
);

const healthServices = computed(() => {
  const h = health.value;
  if (!h) {
    return [
      { key: "api",       name: "FastAPI 网关", state: "fail" as const, detail: "健康端点不可达" },
      { key: "models",    name: "模型 API",     state: "fail" as const, detail: "健康端点不可达" },
      { key: "evalscope", name: "EvalScope",    state: "off" as const, detail: "健康端点不可达" },
      { key: "scheduler", name: "调度服务",     state: "off" as const, detail: "健康端点不可达" },
    ];
  }
  return [
    { key: "api",       name: "FastAPI 网关",  state: "ok" as const, detail: `运行 ${Math.round(h.uptime_s / 60)} 分钟` },
    { key: "models",    name: "模型 API",      state: h.models.ok ? ("ok" as const) : ("fail" as const), detail: `已配置 ${h.models.count} 个` },
    { key: "evalscope", name: "EvalScope",     state: h.evalscope.ok ? ("ok" as const) : ("warn" as const), detail: h.evalscope.state === "ready" ? "数据集目录就绪" : h.evalscope.state },
    { key: "scheduler", name: "调度服务",      state: h.scheduler.ok ? ("ok" as const) : ("warn" as const), detail: h.scheduler.state === "running" ? "APScheduler" : "已禁用" },
  ];
});

function statusType(s?: string): "success" | "warning" | "danger" | "info" {
  if (s === "completed") return "success";
  if (s === "running" || s === "pending" || s === "queued") return "warning";
  if (s === "failed" || s === "error" || s === "interrupted") return "danger";
  return "info";
}

const recentItems = computed(() =>
  taskSummary.value.recentTasks.map(({ task, lane }) => ({
    task,
    lane: lane === "stress"
      ? { label: "压测", path: "/stress" }
      : lane === "intelligence"
        ? { label: "能力", path: "/intelligence" }
        : { label: "基础", path: "/basic" },
  })),
);

function goNew() {
  router.push("/basic");
}
</script>

<template>
  <div class="lb-overview">
    <PageHero
      eyebrow="OVERVIEW"
      title="评测概览"
      :description="`当前模型: ${store.currentModel?.name ?? store.currentId ?? '未选择'} · 查看任务状态、服务健康与最近活动。`"
    >
      <template #actions>
        <el-button size="small" :icon="Refresh" @click="reload" :loading="refreshing">刷新</el-button>
        <el-button type="primary" plain :icon="Aim" @click="goNew">新建评测</el-button>
      </template>
    </PageHero>

    <el-alert
      v-if="taskDataError"
      class="lb-overview__alert"
      :type="allTaskDataFailed ? 'error' : 'warning'"
      :closable="false"
      show-icon
      role="alert"
      aria-live="assertive"
    >
      <template #title>{{ taskErrorTitle }}</template>
      <div class="lb-overview__alert-body">
        <span>{{ failedLaneLabels.join("、") }}加载失败，运行中与最近任务可能不完整。</span>
        <el-button link type="primary" @click="reload">重新加载</el-button>
      </div>
    </el-alert>
    <el-alert
      v-if="statsUnavailable"
      class="lb-overview__alert"
      type="error"
      :closable="false"
      show-icon
      role="alert"
      aria-live="assertive"
      :title="`任务统计加载失败：${statsError}`"
    />

    <!-- 4 KPI 卡片 -->
    <section class="lb-overview__kpis">
      <KpiCard
        label="今日评测"
        :value="stats?.today_count ?? '—'"
        variant="primary"
        :loading="summaryLoading"
        :caption="statsUnavailable ? '统计接口不可用' : '全部任务'"
      />
      <KpiCard
        label="执行完成率"
        :value="completionRateText"
        variant="success"
        :loading="summaryLoading"
        :caption="statsUnavailable ? '统计接口不可用' : '已完成 / 已结束 · 全部任务'"
      />
      <KpiCard
        label="平均任务耗时"
        :value="stats?.avg_duration_ms != null ? stats.avg_duration_ms + 'ms' : '—'"
        variant="warning"
        :loading="summaryLoading"
        :caption="statsUnavailable ? '统计接口不可用' : '仅统计有耗时记录的任务'"
      />
      <KpiCard
        label="已配置模型"
        :value="store.error ? '—' : store.models.length"
        variant="info"
        :loading="store.loading"
        :caption="store.error ? '模型配置加载失败' : '已保存的模型配置数'"
      />
    </section>

    <!-- 趋势 + 健康 + 运行中 -->
    <section class="lb-overview__grid">
      <ServiceHealth
  :services="healthServices"
  @configure="(k) => toast.info(`打开配置: ${k}`)"
  @retry="(k) => toast.info(`重试: ${k}`)"
/>
    </section>

    <!-- 运行中 + 最近活动 -->
    <section class="lb-overview__grid">
      <RunningTasks
        :tasks="taskSummary.runningTasks"
        :loading="tasksLoading"
        :error="runningError"
        :partial-error="runningPartialError"
      />

      <div class="lb-overview__recent">
        <div class="lb-overview__panel-head">
          <h3>最近结束</h3>
          <el-link type="primary" underline="never" @click="router.push('/basic')">
            查看全部 <el-icon><ArrowRight /></el-icon>
          </el-link>
        </div>
        <ul v-if="recentItems.length" class="lb-overview__recent-list">
          <li
            v-for="item in recentItems"
            :key="item.task.task_id"
            class="lb-overview__recent-item"
            @click="router.push(item.lane.path)"
          >
            <StatusDot :state="statusType(item.task.status) === 'success' ? 'ok' : statusType(item.task.status) === 'danger' ? 'fail' : 'pending'" :size="7" />
            <div class="lb-overview__recent-meta">
              <div class="lb-overview__recent-id">
                <span class="lb-overview__recent-lane">{{ item.lane.label }}</span>
                {{ item.task.task_id }}
              </div>
              <div class="lb-overview__recent-time">
                <el-icon><Clock /></el-icon>
                {{ formatDate(item.task.finished_at || item.task.updated_at) }}
              </div>
            </div>
            <StatusTag :status="String(item.task.status)" compact />
          </li>
        </ul>
        <div v-else class="lb-overview__recent-empty">
          {{ recentEmptyText }}
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.lb-overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lb-overview__kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.lb-overview__alert-body {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.lb-overview__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}

.lb-overview__panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.lb-overview__panel-head h3 {
  margin: 0;
  font-family: "Fira Code", monospace;
  font-size: 14px;
  font-weight: 600;
  color: var(--lb-fg-strong);
}

.lb-overview__recent {
  padding: 18px 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
}

.lb-overview__recent-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lb-overview__recent-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 150ms ease;
}

.lb-overview__recent-item:hover {
  background: var(--lb-surface-soft);
}

.lb-overview__recent-meta {
  flex: 1 1 auto;
  min-width: 0;
}

.lb-overview__recent-id {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  color: var(--lb-primary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lb-overview__recent-lane {
  margin-right: 6px;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--lb-neutral-tint);
  color: var(--lb-fg-soft);
  font-family: inherit;
  font-size: 11px;
}

.lb-overview__recent-time {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: var(--lb-muted);
}

.lb-overview__recent-empty {
  padding: 28px 16px;
  text-align: center;
  color: var(--lb-muted);
  font-size: 13px;
}

@media (max-width: 1180px) {
  .lb-overview__kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .lb-overview__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
