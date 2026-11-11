<script setup lang="ts">
import { formatDate } from "@/utils/time";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { evaluations, lanes, laneNames, type ModelEvaluation } from "@/api/model-evaluations";
import LaneExecutionStatus from "@/components/models/LaneExecutionStatus.vue";
const router = useRouter();
const items = ref<ModelEvaluation[]>([]), selected = ref<ModelEvaluation[]>([]);
const search = ref(""), includeArchived = ref(false), loading = ref(false), error = ref("");
const page = ref(1), total = ref(0);
const sortBy = ref("model_id");
let loadVersion = 0;
async function load(reset = false) {
  const version = ++loadVersion;
  if (reset) page.value = 1;
  loading.value = true; error.value = "";
  try { const data = await evaluations.list({ search: search.value, include_archived: includeArchived.value, page: page.value, sort_by: sortBy.value, order: sortBy.value === "model_id" ? "asc" : "desc" }); if (version === loadVersion) { items.value = data.items; total.value = data.total; } }
  catch (e: any) { if (version === loadVersion) error.value = e.message; } finally { if (version === loadVersion) loading.value = false; }
}
function compare() { router.push({ path: "/model-compare", query: { ids: selected.value.map(m => m.model_id).join(",") } }); }
onMounted(load);
</script>
<template>
  <section class="mw-page">
    <header class="mw-title"><div><p class="mw-eyebrow">模型配置与评测证据</p><h1>模型工作台</h1><p>以模型 ID 追踪评测证据，各链路默认展示最近一次成功结果。</p></div><el-button @click="load()" :loading="loading">刷新结果</el-button></header>
    <div class="mw-kpis"><div><span>模型记录</span><strong>{{ total }}</strong></div><div><span>评测链路</span><strong>03</strong></div><div><span>当前页成功证据泳道</span><strong>{{ items.reduce((n, m) => n + m.coverage, 0) }}<small> / {{ items.length * 3 }} 个</small></strong></div></div>
    <div class="mw-tools"><el-input v-model="search" placeholder="搜索模型 ID / 名称" aria-label="搜索模型" clearable @keyup.enter="load(true)" @clear="load(true)" /><el-button @click="load(true)">查询</el-button><el-select v-model="sortBy" aria-label="模型排序" style="width:210px" @change="load(true)"><el-option label="模型 ID（升序）" value="model_id" /><el-option label="覆盖度（高到低）" value="coverage" /><el-option label="最后执行（新到旧）" value="last_execution" /></el-select><el-checkbox v-model="includeArchived" @change="load(true)">包含归档与历史模型</el-checkbox><el-button type="primary" aria-describedby="compare-selection-hint" :disabled="selected.length < 2 || selected.length > 4" @click="compare">对比所选模型（{{ selected.length }}/4）</el-button></div>
    <p id="compare-selection-hint" class="mw-muted">选择 2–4 个模型进行对比；跨页排序作用于全部匹配模型，时间未知的记录排在最后。</p>
    <p class="mw-muted">已中断：执行未正常结束，可能由取消或服务重启引起；失败：执行发生错误。最近成功证据保留历史结果，以上状态不代表模型当前可用性。</p>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-table v-loading="loading" :data="items" row-key="model_id" @selection-change="selected = $event" empty-text="暂无模型记录，请通过顶部添加模型。">
      <el-table-column type="selection" width="42" />
      <el-table-column label="模型身份" min-width="225"><template #default="{ row }"><router-link class="mw-id" :to="`/models/${encodeURIComponent(row.model_id)}`">{{ row.name || row.model_id }}</router-link><div class="mw-muted mw-mono">配置 ID：{{ row.model_id }}</div><div v-if="row.upstream_model && row.upstream_model !== row.name" class="mw-muted">上游型号：{{ row.upstream_model }}</div><el-tag v-if="row.archived" size="small" type="info">{{ row.historical_only ? '仅历史' : '已归档' }}</el-tag></template></el-table-column>
      <el-table-column v-for="lane in lanes" :key="lane" :label="laneNames[lane]" min-width="205"><template #default="{ row }"><LaneExecutionStatus :result="row.lanes[lane]" /></template></el-table-column>
      <el-table-column label="最后执行" min-width="215"><template #default="{ row }">{{ row.last_execution_at ? formatDate(row.last_execution_at) : '时间未知 / 未评测' }}</template></el-table-column>
      <el-table-column label="覆盖" width="85"><template #default="{ row }">{{ row.coverage }} / 3</template></el-table-column>
      <el-table-column label="操作" width="95" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="router.push(`/models/${encodeURIComponent(row.model_id)}`)">查看模型</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="25" layout="total, prev, pager, next" @current-change="load()" />
  </section>
</template>
