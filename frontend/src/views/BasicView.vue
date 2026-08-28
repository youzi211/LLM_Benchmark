<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useModelsStore } from "@/stores/models";
import { formatDate, getBasicTask, listBasicTasks, runBasic, type TaskLike } from "@/api/evaluations";

const store = useModelsStore();
const loading = ref(false);
const submitting = ref(false);
const tasks = ref<TaskLike[]>([]);
const selected = ref<TaskLike | null>(null);
const planId = ref("gateway_acceptance_v1");
const metricIds = ref("");

function statusType(status?: string) {
  if (status === "completed") return "success";
  if (status === "error" || status === "failed") return "danger";
  if (status === "running") return "warning";
  return "info";
}

function splitMetricIds() {
  const raw = metricIds.value.trim();
  return raw ? raw.split(/[，,\s]+/).filter(Boolean) : undefined;
}

async function reload() {
  loading.value = true;
  try {
    tasks.value = await listBasicTasks();
    if (selected.value) selected.value = await getBasicTask(selected.value.task_id);
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!store.currentId) return ElMessage.warning("请先选择当前模型");
  submitting.value = true;
  try {
    const payload: Record<string, unknown> = { model_id: store.currentId, plan_id: planId.value };
    const metrics = splitMetricIds();
    if (metrics?.length) payload.metric_ids = metrics;
    const task = await runBasic(payload);
    ElMessage.success(`基础评测完成：${task.task_id}`);
    await reload();
    selected.value = task;
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : String(err));
  } finally {
    submitting.value = false;
  }
}

async function selectTask(row: TaskLike) {
  selected.value = await getBasicTask(row.task_id);
}

onMounted(reload);
</script>

<template>
  <section class="view-grid">
    <el-card class="panel-card" shadow="never">
      <template #header>
        <div class="card-title"><span>基础评测</span><el-tag>Gateway smoke</el-tag></div>
      </template>
      <p class="muted">验证服务连通、协议兼容、usage、错误结构、上下文和缓存等基础能力。</p>
      <el-form label-position="top">
        <el-form-item label="当前模型">
          <el-input :model-value="store.currentModel?.name || store.currentId || '未选择模型'" disabled />
        </el-form-item>
        <el-form-item label="评测计划">
          <el-select v-model="planId" class="full-width">
            <el-option label="gateway_acceptance_v1" value="gateway_acceptance_v1" />
          </el-select>
        </el-form-item>
        <el-form-item label="指定指标（可选，逗号分隔）">
          <el-input v-model="metricIds" placeholder="connectivity, usage" />
        </el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">开始基础评测</el-button>
      </el-form>
    </el-card>

    <el-card class="panel-card" shadow="never">
      <template #header>
        <div class="card-title"><span>任务列表</span><el-button size="small" @click="reload">刷新</el-button></div>
      </template>
      <el-table v-loading="loading" :data="tasks" height="520" highlight-current-row @row-click="selectTask">
        <el-table-column prop="task_id" label="任务" min-width="210" show-overflow-tooltip />
        <el-table-column prop="model_id" label="模型" width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="更新时间" width="180"><template #default="{ row }">{{ formatDate(row.updated_at || row.finished_at || row.started_at) }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel-card detail-card" shadow="never">
      <template #header><div class="card-title"><span>任务详情</span><el-tag v-if="selected" :type="statusType(selected.status)">{{ selected.status }}</el-tag></div></template>
      <el-empty v-if="!selected" description="请选择一个基础评测任务" />
      <template v-else>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">{{ selected.task_id }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ selected.model_id }}</el-descriptions-item>
          <el-descriptions-item label="计划">{{ selected.plan_id }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ selected.duration_ms ? Math.round(Number(selected.duration_ms)) + ' ms' : '-' }}</el-descriptions-item>
        </el-descriptions>
        <div class="section-title">指标结果</div>
        <el-table :data="Array.isArray(selected.results) ? selected.results : []" border>
          <el-table-column prop="metric_name" label="指标" min-width="160" />
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="summary" label="摘要" min-width="260" show-overflow-tooltip />
        </el-table>
        <el-alert v-if="selected.error" class="mt" type="error" :closable="false" :title="JSON.stringify(selected.error)" />
        <el-link v-if="selected.report_path" class="mt" type="primary" :href="`/api/reports/${selected.task_id}`" target="_blank">打开 Markdown 报告</el-link>
      </template>
    </el-card>
  </section>
</template>
