<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import ScheduleEditorDrawer from "@/components/schedules/ScheduleEditorDrawer.vue";
import {
  deleteSchedule,
  formatDate,
  getScheduleLastRun,
  listSchedules,
  triggerSchedule,
} from "@/api/evaluations";

const loading = ref(false);
const drawerVisible = ref(false);
const schedules = ref<Record<string, any>[]>([]);
const selected = ref<Record<string, any> | null>(null);
const lastRun = ref<Record<string, any> | null>(null);

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

async function reload() {
  loading.value = true;
  try {
    schedules.value = await listSchedules();
  } finally {
    loading.value = false;
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

onMounted(() => {
  void reload();
});
</script>

<template>
  <section class="schedules-page">
    <div class="page-hero">
      <div>
        <p class="eyebrow">Scheduled suites</p>
        <h1>定时任务</h1>
        <p class="muted">列表用于观察和触发任务；复杂的创建参数已移到右侧副页，避免页面被数据集配置拉长。</p>
      </div>
      <div class="page-hero__actions">
        <el-button @click="reload">刷新</el-button>
        <el-button type="primary" @click="drawerVisible = true">新建定时任务</el-button>
      </div>
    </div>

    <div class="view-grid view-grid--two schedules-grid">
      <el-card class="panel-card" shadow="never">
        <template #header>
          <div class="card-title"><span>任务列表</span><span class="muted">{{ schedules.length }} 个任务</span></div>
        </template>
        <el-table v-loading="loading" :data="schedules" height="620" highlight-current-row @row-click="selectSchedule">
          <el-table-column prop="name" label="名称" min-width="170" show-overflow-tooltip />
          <el-table-column label="评测内容" min-width="142">
            <template #default="{ row }">
              <div class="lane-tags">
                <el-tag v-for="lane in scheduleLanes(row)" :key="lane" size="small" effect="plain">{{ lane }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="profile" label="Profile" min-width="138" show-overflow-tooltip />
          <el-table-column label="状态" width="78">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? "启用" : "停用" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="下次运行" min-width="160"><template #default="{ row }">{{ formatDate(row.next_run_at) }}</template></el-table-column>
          <el-table-column label="操作" width="124">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain @click.stop="trigger(row.schedule_id)">触发</el-button>
              <el-button size="small" type="danger" plain @click.stop="remove(row.schedule_id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="panel-card detail-card" shadow="never">
        <template #header>
          <div class="card-title"><span>任务详情</span><el-button size="small" type="primary" plain @click="drawerVisible = true">新建</el-button></div>
        </template>

        <div v-if="!selected" class="detail-empty">
          <el-empty description="选择左侧任务查看最近一次运行情况，或新建一个定时任务。">
            <el-button type="primary" @click="drawerVisible = true">新建定时任务</el-button>
          </el-empty>
        </div>

        <template v-else>
          <div class="schedule-summary-card">
            <div>
              <p class="muted">任务名称</p>
              <h2>{{ selected.name }}</h2>
            </div>
            <el-tag :type="selected.enabled ? 'success' : 'info'">{{ selected.enabled ? "启用" : "停用" }}</el-tag>
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

          <el-divider />
          <div class="section-title">上次运行详情</div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="上次状态">
              <el-tag v-if="lastRun?.last_suite_status" :type="statusType(lastRun.last_suite_status)">{{ lastRun.last_suite_status }}</el-tag>
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
              <span>{{ step.title }} — {{ step.status }}</span>
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
