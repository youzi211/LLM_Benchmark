<script setup lang="ts">
/**
 * 工作台概览：真实任务指标、任务动态与服务状态。
 */
import { computed, defineAsyncComponent, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useModelsStore } from "@/stores/models";
import { useHealthStore } from "@/stores/health";
import { useToast } from "@/composables/useToast";
import PageHero from "@/components/layouts/PageHero.vue";
import KpiCard from "@/components/overview/KpiCard.vue";
import ServiceHealth from "@/components/overview/ServiceHealth.vue";
import RunningTasks from "@/components/overview/RunningTasks.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { ArrowRight, Connection, Cpu, DataLine, Plus, Refresh, Tickets } from "@element-plus/icons-vue";
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
import { taskDetailLocation } from "@/utils/taskCenter";
import { formatDurationMetric } from "@/overview/presentation";

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
  stats.value?.completion_rate == null ? "—" : stats.value.completion_rate.toFixed(1),
);
const averageDuration = computed(() => formatDurationMetric(stats.value?.avg_duration_ms));

const entries = [
  { title: "基础评测", description: "协议兼容与网关工程检查", path: "/basic", icon: Connection },
  { title: "压测评测", description: "并发、吞吐与响应延迟", path: "/stress", icon: DataLine },
  { title: "能力评测", description: "知识、代码与推理能力", path: "/intelligence", icon: Cpu },
];

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
    { key: "scheduler", name: "调度服务",      state: h.scheduler.ok ? ("ok" as const) : ("warn" as const), detail: h.scheduler.state === "running" ? "单机定时调度器" : "已禁用" },
  ];
});

const recentItems = computed(() =>
  taskSummary.value.recentTasks.map(({ task, lane }) => ({
    task,
    model: store.models.find((model) => model.id === task.model_id)?.name || task.model_id || "未命名模型",
    location: taskDetailLocation(lane, task.task_id),
    lane: lane === "stress"
      ? { label: "压测" }
      : lane === "intelligence"
        ? { label: "能力" }
        : { label: "基础" },
  })),
);

function goNew() {
  router.push("/basic");
}

const ModelCreateDrawer = defineAsyncComponent(() => import("@/components/models/ModelCreateDrawer.vue"));
const EvalScopeConfigDrawer = defineAsyncComponent(() => import("@/components/evalscope/EvalScopeConfigDrawer.vue"));
const modelDrawerVisible = ref(false);
const evalscopeDrawerVisible = ref(false);

// 服务健康卡的重试 / 配置动作。
function onRetryService(key: string) {
  if (key === "models") {
    store.load(true).catch((err) => toast.error("重试失败: " + String(err?.message ?? err)));
  }
  healthStore.refresh().catch((err) => toast.error("重试失败: " + String(err?.message ?? err)));
}

function onConfigureService(key: string) {
  if (key === "models") modelDrawerVisible.value = true;
  else if (key === "evalscope") evalscopeDrawerVisible.value = true;
  else if (key === "scheduler") router.push("/schedules");
  else toast.info("FastAPI 网关无需配置，请检查后端服务状态");
}
</script>

<template>
  <div class="lb-overview">
    <PageHero
      class="lb-overview__hero"
      eyebrow="WORKSPACE"
      title="评测概览"
      description="汇总全部模型的评测进展、运行状态与最近结果。"
    >
      <template #actions>
        <el-button :icon="Refresh" @click="reload" :loading="refreshing">刷新数据</el-button>
        <el-button type="primary" :icon="Plus" @click="goNew">新建评测</el-button>
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
        :value="stats?.today_count.toLocaleString('zh-CN') ?? '—'"
        unit="次"
        variant="primary"
        :loading="summaryLoading"
        :caption="statsUnavailable ? '统计接口不可用' : '全部模型 · 今日任务'"
      />
      <KpiCard
        label="执行完成率"
        :value="completionRateText"
        :unit="stats?.completion_rate == null ? '' : '%'"
        variant="success"
        :loading="summaryLoading"
        :caption="statsUnavailable ? '统计接口不可用' : '已完成 / 已结束 · 全部任务'"
      />
      <KpiCard
        label="平均任务耗时"
        :value="averageDuration.value"
        :unit="averageDuration.unit"
        :title="stats?.avg_duration_ms != null ? `原始平均耗时：${stats.avg_duration_ms} ms` : undefined"
        variant="warning"
        :loading="summaryLoading"
        :caption="statsUnavailable ? '统计接口不可用' : '仅统计有耗时记录的任务'"
      />
      <KpiCard
        label="已配置模型"
        :value="store.error ? '—' : store.models.length"
        :unit="store.error ? '' : '个'"
        variant="info"
        :loading="store.loading"
        :caption="store.error ? '模型配置加载失败' : '已保存的模型配置数'"
      />
    </section>

    <section class="lb-overview__content" aria-label="任务与服务概览">
      <div class="lb-overview__column">
        <RunningTasks
          :tasks="taskSummary.runningTasks"
          :loading="tasksLoading"
          :error="runningError"
          :partial-error="runningPartialError"
        />

        <section class="lb-overview__recent" aria-labelledby="recent-tasks-title">
          <div class="lb-overview__panel-head">
            <h3 id="recent-tasks-title">最近结束</h3>
            <router-link to="/tasks" class="lb-overview__text-link">查看全部 <el-icon><ArrowRight /></el-icon></router-link>
          </div>
          <div v-if="tasksLoading" class="lb-overview__recent-loading" aria-label="正在加载最近任务">
            <div v-for="i in 3" :key="i" class="lb-overview__skeleton"></div>
          </div>
          <ul v-else-if="recentItems.length" class="lb-overview__recent-list">
            <li v-for="item in recentItems" :key="item.task.task_id">
              <router-link :to="item.location" class="lb-overview__recent-item">
                <span class="lb-overview__recent-icon"><el-icon><Tickets /></el-icon></span>
                <div class="lb-overview__recent-meta">
                  <div class="lb-overview__recent-name">
                    <span :title="item.model">{{ item.model }}</span>
                    <span class="lb-overview__recent-lane">{{ item.lane.label }}</span>
                  </div>
                  <code class="lb-overview__recent-id" :title="item.task.task_id">{{ item.task.task_id }}</code>
                </div>
                <div class="lb-overview__recent-result">
                  <StatusTag :status="String(item.task.status)" compact />
                  <time class="lb-overview__recent-time">{{ formatDate(item.task.finished_at || item.task.updated_at) }}</time>
                </div>
                <el-icon class="lb-overview__recent-arrow"><ArrowRight /></el-icon>
              </router-link>
            </li>
          </ul>
          <div v-else class="lb-overview__recent-empty">
            <el-icon><Tickets /></el-icon><span>{{ recentEmptyText }}</span>
          </div>
        </section>
      </div>

      <aside class="lb-overview__column lb-overview__aside">
        <ServiceHealth :services="healthServices" @configure="onConfigureService" @retry="onRetryService" />
        <section class="lb-overview__quickstart" aria-labelledby="quickstart-title">
          <div class="lb-overview__panel-head"><h3 id="quickstart-title">开始评测</h3><span class="lb-overview__panel-note">三条评测线</span></div>
          <router-link v-for="entry in entries" :key="entry.path" :to="entry.path" class="lb-overview__entry">
            <span class="lb-overview__entry-icon"><el-icon><component :is="entry.icon" /></el-icon></span>
            <span class="lb-overview__entry-copy"><strong>{{ entry.title }}</strong><small>{{ entry.description }}</small></span>
            <el-icon class="lb-overview__entry-arrow"><ArrowRight /></el-icon>
          </router-link>
          <router-link to="/suites" class="lb-overview__suite-link">一键运行完整评测 <el-icon><ArrowRight /></el-icon></router-link>
        </section>
      </aside>
    </section>

    <ModelCreateDrawer v-if="modelDrawerVisible" v-model="modelDrawerVisible" @created="(id: string) => store.select(id)" />
    <EvalScopeConfigDrawer v-if="evalscopeDrawerVisible" v-model="evalscopeDrawerVisible" />
  </div>
</template>

<style scoped>
.lb-overview { display: flex; flex-direction: column; gap: 24px; }
.lb-overview__hero { margin-bottom: 0; }
.lb-overview__kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.lb-overview__alert-body { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.lb-overview__content { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr); gap: 24px; align-items: start; }
.lb-overview__column { display: flex; flex-direction: column; min-width: 0; gap: 24px; }
.lb-overview__recent, .lb-overview__quickstart { min-width: 0; padding: 20px; border: 1px solid var(--lb-border); border-radius: var(--lb-radius); background: var(--lb-surface); box-shadow: var(--lb-shadow); }
.lb-overview__panel-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; padding-bottom: 16px; border-bottom: 1px solid var(--lb-border); }
.lb-overview__panel-head h3 { margin: 0; font-family: var(--font-heading); font-size: 14px; font-weight: 600; }
.lb-overview__text-link { display: inline-flex; align-items: center; gap: 4px; color: var(--lb-primary); font-size: 11px; text-decoration: none; }
.lb-overview__text-link:hover { text-decoration: underline; }
.lb-overview__panel-note { color: var(--lb-muted); font-size: 11px; }
.lb-overview__recent-list { list-style: none; margin: 0; padding: 0; }
.lb-overview__recent-list li + li { border-top: 1px solid var(--lb-border-soft); }
.lb-overview__recent-item { display: flex; align-items: center; gap: 12px; min-width: 0; padding: 16px 0; color: inherit; text-decoration: none; border-radius: 6px; transition: background-color 150ms ease; }
.lb-overview__recent-item:hover { background: var(--lb-surface-soft); }
.lb-overview__recent-list li:last-child .lb-overview__recent-item { padding-bottom: 4px; }
.lb-overview__recent-icon { display: grid; place-items: center; flex-shrink: 0; width: 34px; height: 36px; border: 1px solid var(--lb-border); border-radius: 8px; color: var(--lb-muted); font-size: 17px; }
.lb-overview__recent-meta { flex: 1; min-width: 0; }
.lb-overview__recent-name { display: flex; align-items: center; min-width: 0; gap: 8px; color: var(--lb-fg-strong); font-size: 12px; font-weight: 500; }
.lb-overview__recent-name > span:first-child { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.lb-overview__recent-lane { flex-shrink: 0; padding: 2px 5px; border-radius: 4px; background: var(--lb-surface-alt); color: var(--lb-muted); font-size: 10px; font-weight: 400; }
.lb-overview__recent-id { display: block; margin-top: 6px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: var(--lb-muted); font-family: var(--font-mono); font-size: 10px; }
.lb-overview__recent-result { display: flex; flex-shrink: 0; flex-direction: column; align-items: flex-end; gap: 7px; }
.lb-overview__recent-time { color: var(--lb-muted); font-size: 10px; }
.lb-overview__recent-arrow { flex-shrink: 0; color: var(--lb-muted); font-size: 12px; }
.lb-overview__recent-empty { display: flex; flex-direction: column; align-items: center; gap: 12px; min-height: 150px; padding: 36px 16px; text-align: center; color: var(--lb-muted); font-size: 12px; }
.lb-overview__recent-empty .el-icon { font-size: 24px; }
.lb-overview__recent-loading { display: grid; gap: 12px; padding-top: 16px; }
.lb-overview__skeleton { height: 48px; border-radius: 8px; background: var(--lb-surface-soft); }
.lb-overview__entry { display: flex; align-items: center; gap: 12px; padding: 15px 0; border-bottom: 1px solid var(--lb-border-soft); color: inherit; text-decoration: none; }
.lb-overview__entry-icon { display: grid; place-items: center; flex-shrink: 0; width: 34px; height: 36px; border-radius: 8px; background: var(--lb-surface-soft); color: var(--lb-fg-soft); font-size: 17px; transition: color 150ms ease, background-color 150ms ease; }
.lb-overview__entry-copy { display: flex; flex: 1; flex-direction: column; min-width: 0; gap: 5px; }
.lb-overview__entry-copy strong { color: var(--lb-fg-strong); font-size: 12px; font-weight: 500; }
.lb-overview__entry-copy small { color: var(--lb-muted); font-size: 11px; line-height: 1.5; }
.lb-overview__entry-arrow { color: var(--lb-muted); font-size: 12px; }
.lb-overview__entry:hover .lb-overview__entry-icon { color: var(--lb-primary); background: var(--lb-accent-soft); }
.lb-overview__entry:hover strong { color: var(--lb-primary); }
.lb-overview__suite-link { display: flex; justify-content: space-between; align-items: center; padding-top: 16px; color: var(--lb-primary); font-size: 11px; text-decoration: none; }
.lb-overview__suite-link:hover { text-decoration: underline; }
@media (max-width: 1180px) {
  .lb-overview__kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .lb-overview__content { grid-template-columns: minmax(0, 1fr); }
  .lb-overview__aside { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
}
@media (max-width: 600px) {
  .lb-overview { gap: 20px; }
  .lb-overview__kpis { gap: 12px; }
  .lb-overview__column, .lb-overview__content { gap: 20px; }
  .lb-overview__aside { grid-template-columns: minmax(0, 1fr); }
  .lb-overview__recent, .lb-overview__quickstart { padding: 16px; }
  .lb-overview__recent-item { gap: 10px; }
  .lb-overview__recent-icon { display: none; }
  .lb-overview__recent-arrow { display: none; }
}
</style>
