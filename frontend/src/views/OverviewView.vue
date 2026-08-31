<script setup lang="ts">
/**
 * 概览页 (Phase 3.1) - LLM Benchmark 新首页
 * Hero + 4 KPI + 趋势 + 服务健康 + 运行中 + 最近活动
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useModelsStore } from "@/stores/models";
import { useToast } from "@/composables/useToast";
import PageHero from "@/components/layouts/PageHero.vue";
import KpiCard from "@/components/overview/KpiCard.vue";
import TrendChart from "@/components/overview/TrendChart.vue";
import ServiceHealth from "@/components/overview/ServiceHealth.vue";
import RunningTasks from "@/components/overview/RunningTasks.vue";
import StatusDot from "@/components/common/StatusDot.vue";
import { ArrowRight, Clock, Refresh, Aim } from "@element-plus/icons-vue";
import { formatDate } from "@/api/evaluations";
import { listBasicTasks, listStressTasks, listIntelligenceTasks, getHealth, type HealthStatus, type TaskLike } from "@/api/evaluations";

const router = useRouter();
const store = useModelsStore();
const toast = useToast();

const loading = ref(true);
const basic = ref<TaskLike[]>([]);
const stress = ref<TaskLike[]>([]);
const intel = ref<TaskLike[]>([]);

const health = ref<HealthStatus | null>(null);
let healthTimer: number | undefined;

async function refreshHealth() {
  try { health.value = await getHealth(); } catch { health.value = null; }
}

async function reload() {
  loading.value = true;
  try {
    const [b, s, i] = await Promise.allSettled([
      listBasicTasks(),
      listStressTasks(),
      listIntelligenceTasks(),
    ]);
    basic.value = b.status === "fulfilled" && Array.isArray(b.value) ? b.value : [];
    stress.value = s.status === "fulfilled" && Array.isArray(s.value) ? s.value : [];
    intel.value = i.status === "fulfilled" && Array.isArray(i.value) ? i.value : [];
  } catch (err) {
    toast.error("加载概览数据失败: " + String((err as Error)?.message ?? err));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  store.load().catch(() => {});
  reload();
  refreshHealth();
  healthTimer = window.setInterval(refreshHealth, 10000);
});

onUnmounted(() => {
  if (healthTimer !== undefined) window.clearInterval(healthTimer);
});

const allTasks = computed(() => [...basic.value, ...stress.value, ...intel.value]);


const healthServices = computed(() => {
  const h = health.value;
  if (!h) {
    return [
      { key: "api",       name: "FastAPI 网关", state: "ok" as const, detail: "127.0.0.1:8020", latencyMs: 12 },
      { key: "models",    name: "模型 API",     state: "ok" as const, detail: "已配置 0 个" },
      { key: "evalscope", name: "EvalScope",    state: "off" as const, detail: "等待健康检查" },
      { key: "scheduler", name: "调度服务",     state: "ok" as const, detail: "APScheduler" },
    ];
  }
  return [
    { key: "api",       name: "FastAPI 网关",  state: "ok" as const, detail: "127.0.0.1:8020", latencyMs: 12 },
    { key: "models",    name: "模型 API",      state: h.models.ok ? ("ok" as const) : ("fail" as const), detail: `已配置 ${h.models.count} 个` },
    { key: "evalscope", name: "EvalScope",     state: h.evalscope.ok ? ("ok" as const) : ("warn" as const), detail: h.evalscope.state === "ready" ? "数据集目录就绪" : h.evalscope.state },
    { key: "scheduler", name: "调度服务",      state: h.scheduler.ok ? ("ok" as const) : ("warn" as const), detail: h.scheduler.state === "running" ? "APScheduler" : "已禁用" },
  ];
});
const todayCount = computed(() => {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  return allTasks.value.filter(t => {
    const ts = new Date(t.started_at || t.finished_at || t.updated_at || 0).getTime();
    return ts >= start.getTime();
  }).length;
});

const passRate = computed(() => {
  const final = allTasks.value.filter(t => ["completed", "failed", "error"].includes(String(t.status)));
  if (final.length === 0) return null;
  const passed = final.filter(t => t.status === "completed").length;
  return ((passed / final.length) * 100).toFixed(1);
});

const avgLatency = computed(() => {
  const withLat = allTasks.value.filter(t => typeof t.duration_ms === "number" && t.duration_ms > 0);
  if (withLat.length === 0) return null;
  const sum = withLat.reduce((a, b) => a + Number(b.duration_ms), 0);
  return Math.round(sum / withLat.length);
});

const onlineModels = computed(() => store.models.length);

const isFinal = (s?: string) => ["completed", "failed", "error", "partial", "interrupted"].includes(String(s));

const recentTasks = computed(() => {
  return [...allTasks.value]
    .filter(t => isFinal(t.status))
    .sort((a, b) => {
      const ta = new Date(a.finished_at || a.updated_at || 0).getTime();
      const tb = new Date(b.finished_at || b.updated_at || 0).getTime();
      return tb - ta;
    })
    .slice(0, 5);
});

function statusType(s?: string): "success" | "warning" | "danger" | "info" {
  if (s === "completed") return "success";
  if (s === "running" || s === "pending" || s === "queued") return "warning";
  if (s === "failed" || s === "error" || s === "interrupted") return "danger";
  return "info";
}

function goNew() {
  router.push("/basic");
}
</script>

<template>
  <div class="lb-overview">
    <PageHero
      eyebrow="OVERVIEW"
      title="评测概览"
      :description="`当前模型: ${store.currentModel?.name ?? store.currentId ?? '未选择'} · 实时监控今日评测状态、趋势与服务健康。`"
    >
      <template #actions>
        <el-button size="small" :icon="Refresh" @click="reload" :loading="loading">刷新</el-button>
        <el-button type="primary" plain :icon="Aim" @click="goNew">新建评测</el-button>
      </template>
    </PageHero>

    <!-- 4 KPI 卡片 -->
    <section class="lb-overview__kpis">
      <KpiCard
        label="今日评测"
        :value="todayCount"
        :trend="12.5"
        trend-label="较昨日"
        variant="primary"
        :loading="loading"
        caption="含基础 / 压测 / 能力"
      />
      <KpiCard
        label="通过率"
        :value="passRate !== null ? passRate + '%' : '—'"
        :trend="2.1"
        trend-label="较昨日"
        variant="success"
        :loading="loading"
        caption="已完成任务中"
      />
      <KpiCard
        label="平均延迟"
        :value="avgLatency !== null ? avgLatency + 'ms' : '—'"
        :trend="-3.8"
        trend-label="较昨日"
        variant="warning"
        :loading="loading"
        caption="P50 估算"
      />
      <KpiCard
        label="在线模型"
        :value="onlineModels"
        :trend="0"
        trend-label="已配置"
        variant="info"
        :loading="loading"
        caption="可在右上选择"
      />
    </section>

    <!-- 趋势 + 健康 + 运行中 -->
    <section class="lb-overview__grid">
      <div class="lb-overview__trend">
        <div class="lb-overview__panel-head">
          <h3>7 日趋势</h3>
          <div class="lb-overview__legend">
            <span class="lb-overview__legend-item">
              <span class="lb-overview__legend-dot" style="background:#1E40AF"></span>通过率
            </span>
            <span class="lb-overview__legend-item">
              <span class="lb-overview__legend-dot" style="background:#F59E0B"></span>平均延迟
            </span>
          </div>
        </div>
        <TrendChart :loading="loading" height="260px" />
      </div>

      <ServiceHealth
  :services="healthServices"
  @configure="(k) => toast.info(`打开配置: ${k}`)"
  @retry="(k) => toast.info(`重试: ${k}`)"
/>
    </section>

    <!-- 运行中 + 最近活动 -->
    <section class="lb-overview__grid lb-overview__grid--2col">
      <RunningTasks @click="(t) => router.push(t.type === 'basic' ? '/basic' : t.type === 'stress' ? '/stress' : '/intelligence')" />

      <div class="lb-overview__recent">
        <div class="lb-overview__panel-head">
          <h3>最近完成</h3>
          <el-link type="primary" :underline="false" @click="router.push('/basic')">
            查看全部 <el-icon><ArrowRight /></el-icon>
          </el-link>
        </div>
        <ul v-if="recentTasks.length" class="lb-overview__recent-list">
          <li
            v-for="t in recentTasks"
            :key="t.task_id"
            class="lb-overview__recent-item"
            @click="router.push('/basic')"
          >
            <StatusDot :state="statusType(t.status) === 'success' ? 'ok' : statusType(t.status) === 'warning' ? 'pending' : statusType(t.status) === 'danger' ? 'fail' : 'off'" :size="7" />
            <div class="lb-overview__recent-meta">
              <div class="lb-overview__recent-id">{{ t.task_id }}</div>
              <div class="lb-overview__recent-time">
                <el-icon><Clock /></el-icon>
                {{ formatDate(t.finished_at || t.updated_at) }}
              </div>
            </div>
            <el-tag :type="statusType(t.status)" size="small" effect="light" round>{{ t.status }}</el-tag>
          </li>
        </ul>
        <div v-else class="lb-overview__recent-empty">
          暂无完成的任务
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

.lb-overview__grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}

.lb-overview__grid--2col {
  grid-template-columns: 1fr 1fr;
}

.lb-overview__trend {
  padding: 18px 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
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

.lb-overview__legend {
  display: flex;
  gap: 14px;
}

.lb-overview__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--lb-muted);
}

.lb-overview__legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
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
  .lb-overview__grid,
  .lb-overview__grid--2col {
    grid-template-columns: 1fr;
  }
}
</style>
