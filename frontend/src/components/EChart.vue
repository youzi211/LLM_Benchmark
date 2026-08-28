<script setup lang="ts">
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
  option: Record<string, unknown>;
  height?: string;
}

withDefaults(defineProps<Props>(), {
  height: "320px",
});
</script>

<template>
  <VChart class="echart-box" :style="{ height }" :option="option" autoresize />
</template>

<style scoped>
.echart-box {
  width: 100%;
}
</style>
