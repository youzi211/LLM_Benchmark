<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { evaluations, lanes, laneNames, displayStatus, type ModelEvaluation } from "@/api/model-evaluations";
const router = useRouter();
const items = ref<ModelEvaluation[]>([]), selected = ref<ModelEvaluation[]>([]);
const search = ref(""), includeArchived = ref(false), loading = ref(false), error = ref("");
const page = ref(1), total = ref(0);
async function load(reset = false) {
  if (reset) page.value = 1;
  loading.value = true; error.value = "";
  try { const data = await evaluations.list({ search: search.value, include_archived: includeArchived.value, page: page.value }); items.value = data.items; total.value = data.total; }
  catch (e: any) { error.value = e.message; } finally { loading.value = false; }
}
function compare() { router.push({ path: "/model-compare", query: { ids: selected.value.map(m => m.model_id).join(",") } }); }
onMounted(load);
</script>
<template>
  <section class="mw-page">
    <header class="mw-title"><div><p class="mw-eyebrow">MODEL REGISTRY / EVALUATION EVIDENCE</p><h1>模型工作台</h1><p>以模型 ID 追踪评测证据，各链路默认展示最近一次成功结果。</p></div><el-button @click="load()" :loading="loading">刷新结果</el-button></header>
    <div class="mw-kpis"><div><span>模型记录</span><strong>{{ total }}</strong></div><div><span>评测链路</span><strong>03</strong></div><div><span>当前页完成覆盖</span><strong>{{ items.reduce((n, m) => n + m.coverage, 0) }}<small> / {{ items.length * 3 }}</small></strong></div></div>
    <div class="mw-tools"><el-input v-model="search" placeholder="搜索模型 ID / 名称" aria-label="搜索模型" clearable @keyup.enter="load(true)" @clear="load(true)" /><el-button @click="load(true)">查询</el-button><el-checkbox v-model="includeArchived" @change="load(true)">包含归档与历史模型</el-checkbox><el-button type="primary" :disabled="selected.length < 2 || selected.length > 4" @click="compare">对比所选模型（{{ selected.length }}/4）</el-button></div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-table v-loading="loading" :data="items" row-key="model_id" @selection-change="selected = $event" empty-text="暂无模型记录，请通过顶部添加模型。">
      <el-table-column type="selection" width="42" />
      <el-table-column label="模型身份" min-width="225"><template #default="{ row }"><router-link class="mw-id" :to="`/models/${encodeURIComponent(row.model_id)}`">{{ row.model_id }}</router-link><div class="mw-muted">{{ row.name }} · {{ row.upstream_model || '型号未知' }}</div><el-tag v-if="row.archived" size="small" type="info">{{ row.historical_only ? '仅历史' : '已归档' }}</el-tag></template></el-table-column>
      <el-table-column v-for="lane in lanes" :key="lane" :label="laneNames[lane]" min-width="205"><template #default="{ row }"><div>{{ row.lanes[lane].latest_success ? '成功结果已归档' : row.lanes[lane].partial_result ? '部分结果可用' : '暂无成功结果' }}</div><div class="mw-muted mw-mono">{{ row.lanes[lane].latest_success?.completed_at?.slice(0, 19).replace('T', ' ') || '—' }}</div><div class="mw-muted">最新执行：{{ displayStatus(row.lanes[lane].latest_attempt) }}</div></template></el-table-column>
      <el-table-column label="覆盖" width="85"><template #default="{ row }">{{ row.coverage }} / 3</template></el-table-column>
      <el-table-column label="操作" width="95" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="router.push(`/models/${encodeURIComponent(row.model_id)}`)">查看模型</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="25" layout="total, prev, pager, next" @current-change="load()" />
  </section>
</template>
