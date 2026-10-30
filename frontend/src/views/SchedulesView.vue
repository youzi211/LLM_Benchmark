<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import PageHero from "@/components/layouts/PageHero.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import CronPreview from "@/components/schedules/CronPreview.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import { ElMessage, ElMessageBox } from "element-plus";
import ScheduleEditorDrawer from "@/components/schedules/ScheduleEditorDrawer.vue";
import {
  deleteSchedule,
  fetchDatasets,
  fetchSuiteProfiles,
  finalStatus,
  formatDate,
  relativeFromNow,
  getScheduleLastRun,
  listSchedules,
  triggerSchedule,
  type DatasetMeta,
  type SuiteProfile,
} from "@/api/evaluations";

const loading = ref(false);
const router = useRouter();
const drawerVisible = ref(false);
const schedules = ref<Record<string, any>[]>([]);
const selected = ref<Record<string, any> | null>(null);
const lastRun = ref<Record<string, any> | null>(null);
const profiles = ref<SuiteProfile[]>([]);
const datasetMap = ref<Record<string, DatasetMeta>>({});
let refreshTimer: number | undefined;
let activeReload: Promise<void> | null = null;

function statusType(status?: string) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "interrupted") return "danger";
  if (status === "running" || status === "pending" || status === "queued") return "warning";
  return "info";
}

function scheduleLanes(row?: Record<string, any>) {
  const request = row?.request || {};
  const lanes: string[] = [];
  if (request.run_gateway !== false) lanes.push("基础");
  if (request.run_stress !== false) lanes.push("压测");
  if (request.run_intelligence !== false) lanes.push("能力");
  return lanes;
}

function scheduleDatasetCount(row?: Record<string, any>) {
  const datasets = row?.request?.intelligence_datasets;
  return Array.isArray(datasets) ? datasets.length : 0;
}

function scheduleStressDataset(row?: Record<string, any>) {
  const dataset = row?.request?.stress_options?.dataset;
  return typeof dataset === "string" && dataset ? dataset : "默认";
}

const lastRunSteps = computed(() => (lastRun.value?.suite?.steps as any[]) || []);

function reload(options: { background?: boolean } = {}): Promise<void> {
  if (activeReload) return activeReload;
  if (!options.background) loading.value = true;
  activeReload = (async () => {
    try {
      schedules.value = await listSchedules();
    } finally {
      loading.value = false;
    }
  })().finally(() => {
    activeReload = null;
  });
  return activeReload;
}

async function reloadSelectedLastRun() {
  if (!selected.value) return;
  const scheduleId = selected.value.schedule_id;
  try {
    const run = await getScheduleLastRun(scheduleId);
    if (selected.value?.schedule_id === scheduleId) lastRun.value = run;
  } catch {
    // 后台刷新失败保持旧数据。
  }
}

async function selectSchedule(row: Record<string, any>) {
  selected.value = row;
  lastRun.value = null;
  try {
    lastRun.value = await getScheduleLastRun(row.schedule_id);
  } catch {
    // 详情加载失败不影响列表展示。
  }
}

async function trigger(scheduleId: string) {
  try {
    await triggerSchedule(scheduleId);
    ElMessage.success("已手动触发");
    await reload();
    if (selected.value?.schedule_id === scheduleId) {
      await selectSchedule(selected.value);
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  }
}

async function remove(scheduleId: string) {
  try {
    await ElMessageBox.confirm("确定删除该定时任务？", "删除确认", { type: "warning" });
    await deleteSchedule(scheduleId);
    ElMessage.success("已删除");
    if (selected.value?.schedule_id === scheduleId) {
      selected.value = null;
      lastRun.value = null;
    }
    await reload();
  } catch (err) {
    if (err !== "cancel") ElMessage.error(err instanceof Error ? err.message : String(err));
  }
}

function onCreated() {
  void reload();
}

onMounted(async () => {
  await reload();
  const ps = await fetchSuiteProfiles();
  profiles.value = Array.isArray(ps) ? ps : [];
  try {
    const ds = await fetchDatasets();
    datasetMap.value = ds?.datasets || {};
  } catch {
    datasetMap.value = {};
  }
  // 有正在跑的 suite、或即将到点的任务时每 5 秒后台刷新列表与详情。
  refreshTimer = window.setInterval(() => {
    if (document.visibilityState !== "visible" || activeReload) return;
    // 列表行不含套件状态，只有选中任务的 last-run 详情带 last_suite_status。
    const running = lastRun.value?.last_suite_status && !finalStatus(lastRun.value.last_suite_status);
    const due = running || schedules.value.some((row) => {
      // next_run_at 过点超过 1 分钟视为陈旧（如调度器被禁用），不再触发刷新。
      const delta = row.next_run_at ? Date.parse(row.next_run_at) - Date.now() : -Infinity;
      return delta > -60_000 && delta < 60_000;
    });
    if (due) {
      reload({ background: true });
      void reloadSelectedLastRun();
    }
  }, 5000);
});

onUnmounted(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
});

const selectedProfile = computed(() =>
  selected.value ? profiles.value.find((p) => p.profile_id === selected.value?.profile) ?? null : null,
);

function profileLaneLabels(p?: SuiteProfile | null) {
  if (!p) return [];
  const lanes: string[] = [];
  if (p.run_gateway !== false) lanes.push("基础");
  if (p.run_stress !== false) lanes.push("压测");
  if (p.run_intelligence !== false) lanes.push("能力");
  return lanes;
}

function profileDatasetLabels(p?: SuiteProfile | null) {
  return (p?.intelligence_datasets || []).map((name) => datasetMap.value[name]?.pretty_name || name);
}

function profileLimitLabel(p?: SuiteProfile | null) {
  const v = p?.intelligence_limit;
  if (v === undefined || v === null) return "不限";
  return String(v);
}
</script>

<template>
  <section class="schedules-page">
    <PageHero
      eyebrow="SCHEDULED SUITES"
      title="定时任务"
      description="观察与触发定时评测套件; 复杂配置已移至右侧 Drawer, 避免主页被数据集配置拉长。"
    >
      <template #actions>
        <el-button size="small" @click="reload()">刷新</el-button>
        <el-button type="primary" size="small" @click="drawerVisible = true">新建定时任务</el-button>
      </template>
    </PageHero>

    <div class="view-grid view-grid--two schedules-grid">
      <el-card class="panel-card" shadow="never">
        <div class="lb-sched-count">{{ schedules.length }} 个任务</div>
        <el-table
          class="schedule-table"
          v-loading="loading"
          :data="schedules"
          height="580"
          highlight-current-row
          :empty-text="''"
          @row-click="selectSchedule"
        >
          <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
          <el-table-column label="状态" width="76">
            <template #default="{ row }">
              <StatusTag :status="row.enabled ? 'completed' : 'pending'" :label="row.enabled ? '启用' : '停用'" />
            </template>
          </el-table-column>
          <el-table-column label="下次运行" min-width="145">
            <template #default="{ row }">
              <div class="lb-sched-next">
                <div class="lb-sched-next__time">{{ formatDate(row.next_run_at) }}</div>
                <div v-if="row.next_run_at" class="lb-sched-next__rel">{{ relativeFromNow(row.next_run_at) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="最近运行" min-width="120">
            <template #default="{ row }">
              <span v-if="row.last_error">触发失败</span>
              <span v-else>{{ row.last_run_at ? formatDate(row.last_run_at) : '尚未运行' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="schedule-mobile-list">
          <button v-for="row in schedules" :key="row.schedule_id" type="button" class="schedule-mobile-row" @click="selectSchedule(row)">
            <strong>{{ row.name }}</strong>
            <StatusTag :status="row.enabled ? 'completed' : 'pending'" :label="row.enabled ? '启用' : '停用'" />
            <span>下次：{{ formatDate(row.next_run_at) }}</span>
            <span>最近：{{ row.last_error ? '触发失败' : row.last_run_at ? formatDate(row.last_run_at) : '尚未运行' }}</span>
          </button>
        </div>
        <EmptyState
          v-if="!loading && schedules.length === 0"
          title="还没有定时任务"
          description="新建一个定时任务, 周期性地自动跑评测套件。"
          variant="list"
          action-label="新建定时任务"
          @action="drawerVisible = true"
        />
      </el-card>

      <el-card class="panel-card detail-card" shadow="never">
        <EmptyState
          v-if="!selected"
          title="还没有选中任务"
          description="从左侧任务列表选一个查看 cron 预览, 最近运行情况, 触发或删除。"
          variant="list"
        />

        <template v-else>
          <div class="schedule-summary-card">
            <div>
              <p class="muted">任务名称</p>
              <h2>{{ selected.name }}</h2>
            </div>
            <el-tag :type="selected.enabled ? 'success' : 'info'">{{ selected.enabled ? "启用" : "停用" }}</el-tag>
          </div>
          <div class="detail-actions">
            <el-button type="primary" plain @click="trigger(selected.schedule_id)">立即触发</el-button>
            <el-button v-if="selected.last_suite_id" @click="router.push({ path: '/suites', query: { suite_id: selected.last_suite_id } })">查看最近评测</el-button>
            <el-button type="danger" plain @click="remove(selected.schedule_id)">删除</el-button>
          </div>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="Schedule ID">{{ selected.schedule_id }}</el-descriptions-item>
            <el-descriptions-item label="Profile">{{ selected.profile || '-' }}</el-descriptions-item>
            <el-descriptions-item label="模型">{{ selected.model_id }}</el-descriptions-item>
            <el-descriptions-item label="运行次数">{{ selected.run_count }}</el-descriptions-item>
            <el-descriptions-item label="下次运行">{{ formatDate(selected.next_run_at) }}</el-descriptions-item>
            <el-descriptions-item label="上次运行">{{ formatDate(selected.last_run_at) }}</el-descriptions-item>
            <el-descriptions-item label="评测内容">
              <div class="lane-tags">
                <el-tag v-for="lane in scheduleLanes(selected)" :key="lane" size="small" effect="plain">{{ lane }}</el-tag>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="数据集">
              能力 {{ scheduleDatasetCount(selected) }} 个 / 压测 {{ scheduleStressDataset(selected) }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="selectedProfile || selected.profile" class="section-title">Profile 详情</div>
          <el-descriptions v-if="selectedProfile || selected.profile" :column="2" border>
            <el-descriptions-item label="Profile 名">{{ selectedProfile?.name || selected.profile }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ selectedProfile?.description || '未配置' }}</el-descriptions-item>
            <el-descriptions-item label="评测线">
              <div class="lane-tags">
                <el-tag v-for="lane in profileLaneLabels(selectedProfile)" :key="lane" size="small" effect="plain">{{ lane }}</el-tag>
                <span v-if="!profileLaneLabels(selectedProfile).length" class="muted">-</span>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="能力数据集">
              <template v-if="profileDatasetLabels(selectedProfile).length">
                <el-tag v-for="ds in profileDatasetLabels(selectedProfile)" :key="ds" size="small" type="primary" effect="plain">{{ ds }}</el-tag>
                <span class="muted">共 {{ profileDatasetLabels(selectedProfile).length }} 个</span>
              </template>
              <span v-else class="muted">-</span>
            </el-descriptions-item>
            <el-descriptions-item label="Limit">{{ profileLimitLabel(selectedProfile) }}</el-descriptions-item>
            <el-descriptions-item label="Sandbox">
              <el-tag v-if="selectedProfile?.requires_sandbox" size="small" type="warning">需要 sandbox</el-tag>
              <span v-else>不需要</span>
            </el-descriptions-item>
          </el-descriptions>
          <p v-else class="muted">未配置 Profile，无法展示详情。</p>

          <el-divider />
          <div class="section-title">上次运行详情</div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="上次状态">
              <StatusTag v-if="lastRun?.last_suite_status" :status="lastRun.last_suite_status" compact />
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="当前步骤">{{ lastRun?.last_suite_current_step || '-' }}</el-descriptions-item>
          </el-descriptions>

          <div v-if="lastRunSteps.length" class="section-title">步骤</div>
          <el-timeline v-if="lastRunSteps.length">
            <el-timeline-item
              v-for="step in lastRunSteps"
              :key="step.name"
              :type="step.status === 'completed' ? 'success' : step.status === 'failed' || step.status === 'interrupted' ? 'danger' : step.status === 'running' ? 'warning' : 'info'"
              :timestamp="formatDate(step.completed_at || step.started_at)"
            >
              <span>{{ step.title }}</span>
              <StatusTag :status="step.status" compact />
              <span v-if="step.message" class="muted"> ({{ step.message }})</span>
            </el-timeline-item>
          </el-timeline>

          <el-alert v-if="lastRun?.last_suite_errors?.length" class="mt" type="error" :closable="false" :title="`错误 ${lastRun.last_suite_errors.length} 条`" />
          <div v-if="lastRun?.last_suite_errors?.length" class="error-list">
            <div v-for="(err, i) in lastRun.last_suite_errors" :key="i" class="error-item">
              <el-tag size="small" type="danger">{{ err.step }}</el-tag>
              <span>{{ err.message }}</span>
            </div>
          </div>
        </template>
      </el-card>
    </div>

    <ScheduleEditorDrawer v-model="drawerVisible" @created="onCreated" />
  </section>
</template>

<style scoped>
.lb-sched-count {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--lb-muted, #909399);
}
.schedule-mobile-list { display: none; }
@media (max-width: 760px) {
  .schedule-table { display: none; }
  .schedule-mobile-list { display: grid; gap: 8px; }
  .schedule-mobile-row {
    display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px;
    width: 100%; padding: 12px; text-align: left; color: var(--lb-fg);
    background: var(--lb-surface); border: 1px solid var(--lb-border); border-radius: 8px;
    cursor: pointer;
  }
  .schedule-mobile-row strong { overflow-wrap: anywhere; }
  .schedule-mobile-row span { font-size: 12px; }
}
</style>
