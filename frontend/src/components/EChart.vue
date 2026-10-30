<script setup lang="ts">
import { computed } from "vue";
import { usePreferredReducedMotion } from "@vueuse/core";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart, BarChart, PieChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from "echarts/components";
import VChart from "vue-echarts";
import { useChartTheme } from "@/composables/useChartTheme";

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
]);

interface Props {
  option: Record<string, any>;
  height?: string;
}

const props = withDefaults(defineProps<Props>(), {
  height: "320px",
});

const { chartTheme } = useChartTheme();
const reducedMotion = usePreferredReducedMotion();

// 主题色兜底, 页面里的具体配置(标题/坐标轴/网格)优先.
const styledOption = computed(() => {
  const o = props.option;
  const t = chartTheme.value;
  return {
    ...t,
    ...o,
    animation: reducedMotion.value !== "reduce" && o.animation !== false,
    title: { ...t.title, ...o.title },
    legend: { ...t.legend, ...o.legend },
    tooltip: { ...t.tooltip, ...o.tooltip },
    xAxis: { ...t.xAxis, ...o.xAxis, axisLabel: { ...t.xAxis.axisLabel, ...o.xAxis?.axisLabel } },
    yAxis: { ...t.yAxis, ...o.yAxis, axisLabel: { ...t.yAxis.axisLabel, ...o.yAxis?.axisLabel } },
  };
});
</script>

<template>
  <VChart class="echart-box" :style="{ height }" :option="styledOption" autoresize />
</template>

<style scoped>
.echart-box {
  width: 100%;
}
</style>
