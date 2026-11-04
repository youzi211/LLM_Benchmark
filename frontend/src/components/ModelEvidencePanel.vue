<script setup lang="ts">
import { computed, ref } from "vue";
import EChart from "@/components/EChart.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { exportEvidence, type Evidence, type Lane } from "@/api/model-evaluations";
import { abilityGroups, stressOption, stressMode } from "@/utils/workspaceCharts";
const props = defineProps<{ lane: Lane; entries: Evidence[] }>();
const groups = computed(() => abilityGroups(props.entries));
const rows = computed(() => props.entries.flatMap(e => e.metrics.map(r => ({ ...r, model_id: e.model_id, task_id: e.task_id }))));
const gatewayChecks = computed(() => [...new Set(props.entries.flatMap(e => e.metrics.map(r => r.metric_id as string)))].map(metric_id => ({ metric_id })));
function gatewayMetric(entry: Evidence, metric: string) { return entry.metrics.find(r => r.metric_id === metric); }
const modes = computed(() => [false, true].filter(open => props.entries.some(e => stressMode(e) === (open ? "open" : "closed"))));
const throughput = ref("output_throughput");
const latencyQuantile = ref("p95"), tokenQuantile = ref("p95");
const throughputUnit = computed(() => throughput.value === "request_throughput" ? "req/s ↑" : "tok/s ↑");
const stressColumns = [
  ["parallel", "并发"], ["rate", "请求速率 req/s"], ["total", "请求数"], ["success", "成功数"], ["failed", "失败数"],
  ["request_throughput", "吞吐 req/s ↑"], ["output_throughput", "输出 tok/s ↑"], ["p50_latency_seconds", "P50 s ↓"],
  ["p95_latency_seconds", "P95 s ↓"], ["p99_latency_seconds", "P99 s ↓"], ["avg_ttft_ms", "平均 TTFT ms ↓"], ["p95_ttft_ms", "P95 TTFT ms ↓"],
  ["avg_tpot_ms", "平均 TPOT ms ↓"], ["p95_tpot_ms", "P95 TPOT ms ↓"], ["avg_input_tokens", "平均输入 token"], ["avg_output_tokens", "平均输出 token"]
];
function shown(value: unknown) { return value === null || value === undefined ? '—' : typeof value === 'number' ? Number(value.toFixed(4)) : String(value); }
</script>
<template>
  <div class="mw-evidence">
    <el-empty v-if="!entries.length" description="暂无可展示结果" />
    <template v-else>
      <div class="mw-tools"><span class="mw-muted">真实采集数据 · 缺失指标显示 — · ↑ 越高越好 / ↓ 越低越好</span><el-button @click="exportEvidence(entries, `${lane}-evidence.json`)">导出脱敏明细</el-button></div>
      <div class="mw-source" v-for="entry in entries" :key="entry.model_id"><div><strong class="mw-mono">{{ entry.model_id }}</strong><span>{{ entry.complete === false ? '部分结果' : '评测结果' }}</span><span>{{ entry.completed_at || '完成时间未知' }}</span><span v-if="entry.completed_at && entry.timestamp_timezone_known === false" class="mw-muted">原记录时区未知，排序按服务本地时间</span></div><div class="mw-muted">来源 <a :href="entry.task_url" target="_blank" rel="noopener">{{ entry.task_id }}</a> · EvalScope {{ entry.snapshot?.evalscope_version || '版本未知' }} <a v-if="entry.report_url" :href="entry.report_url" target="_blank" rel="noopener">下载报告</a></div><details><summary>执行条件与配置</summary><pre>{{ entry.snapshot?.conditions ? JSON.stringify(entry.snapshot.conditions, null, 2) : '历史执行条件未知，无法确认可比性。' }}</pre></details></div>
      <template v-if="lane === 'stress'">
        <el-alert v-if="entries.some(e => stressMode(e) === 'unknown')" title="部分历史结果的负载模式未知，仅在明细表展示。" type="warning" :closable="false" />
        <div class="mw-tools"><el-select v-model="throughput" aria-label="吞吐指标" style="width:220px"><el-option label="输出 token 吞吐" value="output_throughput" /><el-option label="总 token 吞吐" value="total_throughput" /><el-option label="请求吞吐" value="request_throughput" /></el-select><el-select v-model="latencyQuantile" aria-label="请求延迟分位数" style="width:180px"><el-option v-for="q in ['avg', 'p50', 'p95', 'p99']" :key="q" :label="`请求延迟 ${q.toUpperCase()}`" :value="q" /></el-select><el-select v-model="tokenQuantile" aria-label="Token 延迟分位数" style="width:180px"><el-option v-for="q in ['avg', 'p95', 'p99']" :key="q" :label="`Token 延迟 ${q.toUpperCase()}`" :value="q" /></el-select></div>
        <div v-for="open in modes" :key="String(open)" class="mw-chart-grid">
          <article class="mw-panel"><h3>{{ open ? '开环' : '闭环' }} · 吞吐与负载</h3><EChart :option="stressOption(entries, throughput, throughputUnit, open)" /></article>
          <article class="mw-panel"><h3>{{ open ? '开环' : '闭环' }} · 请求延迟 {{ latencyQuantile.toUpperCase() }}</h3><EChart :option="stressOption(entries, `${latencyQuantile}_latency_seconds`, 's ↓', open)" /></article>
          <article class="mw-panel"><h3>{{ open ? '开环' : '闭环' }} · 首 token 延迟 {{ tokenQuantile.toUpperCase() }}</h3><EChart :option="stressOption(entries, `${tokenQuantile}_ttft_ms`, 'ms ↓', open)" /></article>
          <article class="mw-panel"><h3>{{ open ? '开环' : '闭环' }} · 单 token 延迟 {{ tokenQuantile.toUpperCase() }}</h3><EChart :option="stressOption(entries, `${tokenQuantile}_tpot_ms`, 'ms ↓', open)" /></article>
        </div>
        <el-table :data="rows" empty-text="无压测档位"><el-table-column prop="model_id" label="模型 ID" width="170" fixed /><el-table-column v-for="[prop, label] in stressColumns" :key="prop" :label="label" min-width="140"><template #default="{ row }">{{ shown(row[prop!]) }}</template></el-table-column></el-table>
      </template>
      <template v-else-if="lane === 'intelligence'">
        <div class="mw-chart-grid"><article class="mw-panel" v-for="group in groups" :key="group.key"><h3>{{ group.name }}</h3><EChart :option="group.option" /></article></div>
        <el-table :data="rows"><el-table-column prop="model_id" label="模型 ID" min-width="160" /><el-table-column prop="dataset" label="数据集" min-width="130" /><el-table-column prop="metric_id" label="原生主指标" min-width="150" /><el-table-column label="结果" min-width="100"><template #default="{ row }">{{ shown(row.score == null ? null : row.score * (row.display_multiplier ?? 1)) }} {{ row.unit || '' }}</template></el-table-column><el-table-column label="样本量" width="90"><template #default="{ row }">{{ shown(row.sample_count) }}</template></el-table-column><el-table-column prop="direction" label="方向" min-width="100" /><el-table-column prop="unavailable_reason" label="说明" min-width="180" /></el-table>
      </template>
      <el-table v-else :data="gatewayChecks"><el-table-column prop="metric_id" label="检查项" min-width="180" fixed /><el-table-column v-for="entry in entries" :key="entry.model_id" :label="entry.model_id" min-width="260"><template #default="{ row }"><template v-if="gatewayMetric(entry, row.metric_id)"><a :href="entry.task_url" target="_blank" rel="noopener"><StatusTag :status="gatewayMetric(entry, row.metric_id)!.status" compact /></a><p>{{ gatewayMetric(entry, row.metric_id)!.summary }}</p></template><span v-else class="mw-muted">缺少此检查项证据</span></template></el-table-column></el-table>
    </template>
  </div>
</template>
