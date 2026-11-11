<script setup lang="ts">
import { formatDate } from "@/utils/time";
import { computed, ref, watch, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { evaluations, lanes, laneNames, displayStatus, type Evidence, type Lane, type ModelEvaluation } from "@/api/model-evaluations";
import LaneExecutionStatus from "@/components/models/LaneExecutionStatus.vue";
import ModelEvidencePanel from "@/components/ModelEvidencePanel.vue";
import ModelCreateDrawer from "@/components/models/ModelCreateDrawer.vue";
import { useModelsStore } from "@/stores/models";
const route = useRoute(), router = useRouter(), models = useModelsStore();
const data = ref<ModelEvaluation | null>(null), error = ref(""), loading = ref(false), editing = ref(false);
const tab = ref("overview"), history = ref<Evidence[]>([]), historyTotal = ref(0), historyPage = ref(1);
const historyLane = ref<Lane | "">("");
const chosen = ref<Partial<Record<Lane, Evidence>>>({});
const id = computed(() => String(route.params.modelId));
const editTarget = computed(() => models.models.find(m => m.id === id.value) || null);
let generation = 0;
async function load() {
  const current = ++generation; loading.value = true; error.value = "";
  try { const result = await evaluations.detail(id.value); if (current === generation) { data.value = result; if (!result.archived) models.select(id.value); } }
  catch (e: any) { if (current === generation) error.value = e.message; } finally { if (current === generation) loading.value = false; }
}
async function loadHistory() {
  try { const result = await evaluations.history(id.value, { page: historyPage.value, lane: historyLane.value || undefined }); history.value = result.items; historyTotal.value = result.total; }
  catch (e: any) { error.value = e.message; }
}
function selected(lane: Lane) { const result = data.value?.lanes[lane]; return chosen.value[lane] || result?.latest_success || result?.partial_result || null; }
function inspect(item: Evidence) { chosen.value[item.lane] = item; tab.value = item.lane; }
async function archive() {
  if (!data.value) return;
  try { await ElMessageBox.confirm(data.value.archived ? '恢复此模型以允许新建评测？' : '归档后保留历史及 ID，停止接受新的评测。', '模型生命周期', { type: 'warning' });
    await evaluations.archive(id.value, data.value.archived); await models.load(true); await load(); }
  catch (e: any) { if (e?.message) ElMessage.error(e.message); }
}
function run(lane: Lane | "suites") { models.select(id.value); router.push(`/${lane}`); }
watch(id, () => { data.value = null; chosen.value = {}; tab.value = "overview"; historyPage.value = 1; load(); }, { immediate: true });
watch([tab, historyPage, historyLane], () => { if (tab.value === 'history') loadHistory(); });
const timer = setInterval(() => { if (data.value && lanes.some(l => ['pending', 'queued', 'running'].includes(data.value!.lanes[l].latest_attempt?.status || ''))) load(); }, 5000);
onUnmounted(() => { generation++; clearInterval(timer); });
</script>
<template>
  <section class="mw-page" v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="data">
      <header class="mw-title"><div><p class="mw-eyebrow">模型 / {{ data.protocol || '历史记录' }}</p><h1>{{ data.name || data.model_id }}</h1><p class="mw-mono">配置 ID：{{ data.model_id }}</p><p><span v-if="data.upstream_model && data.upstream_model !== data.name">上游型号：{{ data.upstream_model }}</span> <el-tag v-if="data.archived" type="info">{{ data.historical_only ? '仅历史记录' : '已归档' }}</el-tag></p></div><div class="mw-actions"><el-button @click="load">刷新结果</el-button><el-button v-if="!data.historical_only" @click="archive">{{ data.archived ? '恢复模型' : '归档模型' }}</el-button><el-button type="primary" :disabled="data.archived || !data.enabled" @click="run('suites')">发起完整评测</el-button></div></header>
      <el-tabs v-model="tab"><el-tab-pane name="overview" label="总览" /><el-tab-pane v-for="lane in lanes" :key="lane" :name="lane" :label="laneNames[lane]" /><el-tab-pane name="history" label="评测历史" /><el-tab-pane name="config" label="模型配置" /></el-tabs>
      <p v-if="tab === 'overview'" class="mw-muted">已中断：执行未正常结束，可能由取消或服务重启引起；失败：执行发生错误。最近成功证据保留历史结果，以上状态不代表模型当前可用性。</p>
      <div v-if="tab === 'overview'" class="mw-lane-cards"><article class="mw-panel" v-for="lane in lanes" :key="lane"><div class="mw-title"><h2>{{ laneNames[lane] }}</h2><el-tag size="small">{{ data.lanes[lane].task_count }} 次执行</el-tag></div><LaneExecutionStatus :result="data.lanes[lane]" /><code>{{ selected(lane)?.task_id || '—' }}</code><div class="mw-actions"><el-button @click="tab = lane">查看证据</el-button><el-button :disabled="data.archived || !data.enabled" @click="run(lane)">新建评测</el-button></div></article></div>
      <template v-for="lane in lanes" :key="lane"><div v-if="tab === lane"><div class="mw-tools"><el-tag v-if="chosen[lane]" type="warning">已选择历史任务</el-tag><el-button v-if="chosen[lane]" @click="delete chosen[lane]">恢复默认结果</el-button><el-button @click="tab = 'history'; historyLane = lane">选择历史结果</el-button><el-button :disabled="data.archived || !data.enabled" @click="run(lane)">新建{{ laneNames[lane] }}</el-button><span class="mw-muted">最新执行：{{ displayStatus(data.lanes[lane].latest_attempt) }}</span></div><ModelEvidencePanel :lane="lane" :entries="selected(lane) ? [selected(lane)!] : []" /></div></template>
      <div v-if="tab === 'history'"><div class="mw-tools"><el-select v-model="historyLane" aria-label="历史链路" style="width:180px" @change="historyPage = 1"><el-option label="全部链路" value="" /><el-option v-for="lane in lanes" :key="lane" :label="laneNames[lane]" :value="lane" /></el-select></div><el-table :data="history"><el-table-column prop="task_id" label="任务 ID" min-width="230" /><el-table-column label="链路" width="120"><template #default="{ row }">{{ laneNames[row.lane as Lane] }}</template></el-table-column><el-table-column label="状态" width="120"><template #default="{ row }">{{ displayStatus(row as Evidence) }}</template></el-table-column><el-table-column label="完整性" width="120"><template #default="{ row }">{{ row.complete ? '完整' : '不完整 / 未知' }}</template></el-table-column><el-table-column label="结果时间" min-width="210"><template #default="{ row }">{{ formatDate(row.completed_at) }}</template></el-table-column><el-table-column width="100"><template #default="{ row }"><el-button link type="primary" @click="inspect(row as Evidence)">查看结果</el-button></template></el-table-column></el-table><el-pagination v-model:current-page="historyPage" :total="historyTotal" :page-size="25" layout="total, prev, pager, next" /></div>
      <article v-if="tab === 'config'" class="mw-panel"><h2>模型身份与配置</h2><el-descriptions :column="1" border><el-descriptions-item label="不可变模型 ID">{{ data.model_id }}</el-descriptions-item><el-descriptions-item label="名称">{{ data.name }}</el-descriptions-item><el-descriptions-item label="上游型号">{{ data.upstream_model || '未知' }}</el-descriptions-item><el-descriptions-item label="协议">{{ data.protocol || '未知' }}</el-descriptions-item></el-descriptions><div class="mw-tools"><el-button :disabled="!editTarget || data.archived" @click="editing = true">编辑模型配置</el-button><router-link to="/settings/evaluation">Judge LLM / 沙箱设置</router-link></div><p class="mw-muted">历史结果保留执行时的脱敏配置快照；当前配置变更不改写历史结果。</p></article>
      <ModelCreateDrawer v-if="editing" v-model="editing" :edit-target="editTarget" @updated="load" />
    </template>
  </section>
</template>
