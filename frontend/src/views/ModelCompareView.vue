<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { evaluations, lanes, laneNames, selectedEvidence, type Lane, type ModelEvaluation, type Comparison } from "@/api/model-evaluations";
import ModelEvidencePanel from "@/components/ModelEvidencePanel.vue";
const route = useRoute(), router = useRouter();
const options = ref<ModelEvaluation[]>([]), ids = ref<string[]>(String(route.query.ids || '').split(',').filter(Boolean));
const result = ref<Comparison | null>(null), loading = ref(false), error = ref(''), lane = ref<Lane>('intelligence');
const overrides = ref<Record<string, Partial<Record<Lane, string>>>>(Object.fromEntries(ids.value.map(id => [id, {}])));
async function compare() {
  loading.value = true; error.value = '';
  try { const clean = Object.fromEntries(ids.value.map(id => [id, Object.fromEntries(Object.entries(overrides.value[id] || {}).filter(([, v]) => v?.trim()))]));
    result.value = await evaluations.compare(ids.value, clean); router.replace({ query: { ids: ids.value.join(',') } }); }
  catch (e: any) { error.value = e.message; result.value = null; } finally { loading.value = false; }
}
async function searchModels(search = '') { try { options.value = (await evaluations.list({ include_archived: true, page_size: 100, search })).items; } catch (e: any) { error.value = e.message; } }
onMounted(async () => { await searchModels(); ids.value.forEach(id => { overrides.value[id] = {}; }); if (ids.value.length >= 2) await compare(); });
function chooseModels() { for (const id of ids.value) overrides.value[id] ||= {}; result.value = null; }
</script>
<template>
  <section class="mw-page">
    <header class="mw-title"><div><p class="mw-eyebrow">CROSS-MODEL / CONTROLLED COMPARISON</p><h1>模型对比</h1><p>按原生指标对比 2–4 个模型，逐项核对执行条件与结果来源。</p></div></header>
    <div class="mw-tools"><el-select v-model="ids" multiple filterable remote :remote-method="searchModels" :multiple-limit="4" placeholder="选择模型 ID" aria-label="选择对比模型" style="min-width:280px;flex:1" @change="chooseModels"><el-option v-for="m in options" :key="m.model_id" :label="`${m.model_id} · ${m.name}${m.archived ? ' [归档]' : ''}`" :value="m.model_id" /></el-select><el-button type="primary" :disabled="ids.length < 2" :loading="loading" @click="compare">生成对比</el-button></div>
    <details class="mw-panel"><summary>指定历史任务（留空使用默认结果）</summary><div class="mw-override" v-for="id in ids" :key="id"><strong class="mw-mono">{{ id }}</strong><el-input v-for="l in lanes" :key="l" v-model="overrides[id]![l]" :placeholder="`${laneNames[l]}任务 ID`" :aria-label="`${id} ${laneNames[l]}任务 ID`" /></div><p class="mw-muted">可从模型详情的评测历史复制任务 ID；应用后点击生成对比。</p></details>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <template v-if="result"><el-tabs v-model="lane"><el-tab-pane v-for="l in lanes" :key="l" :name="l" :label="laneNames[l]" /></el-tabs><el-alert :type="result.comparability[lane].status === 'equal' ? 'success' : 'warning'" :closable="false" show-icon :title="({equal:'执行条件一致', different:'执行条件存在差异', unknown:'信息不足，无法确认条件一致'})[result.comparability[lane].status]" :description="result.comparability[lane].reasons.join('；')" /><ModelEvidencePanel :lane="lane" :entries="result.models.map(m => selectedEvidence(m.lanes[lane])).filter((e): e is NonNullable<typeof e> => e != null)" /></template>
    <el-empty v-else-if="!loading && !error" description="选择模型后生成对比" />
  </section>
</template>
