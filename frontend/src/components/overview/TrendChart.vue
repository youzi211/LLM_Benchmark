<script setup lang="ts">
/**
 * 7 日趋势图 (Phase 3.1)
 * Line with Confidence Band (主线 + 浅色置信区间), 双 Y 轴: 通过率 (左) + 平均延迟 (右)
 * 数据由父组件传入, 默认占位数据保证视觉完整.
 */
import { computed } from "vue";
import EChart from "@/components/EChart.vue";

interface Point {
  date: string;
  passRate: number;     // 0-100
  latencyMs: number;
}

const props = withDefaults(defineProps<{
  data?: Point[];
  loading?: boolean;
  height?: string;
}>(), {
  data: () => [
    { date: "08/24", passRate: 93.2, latencyMs: 350 },
    { date: "08/25", passRate: 94.1, latencyMs: 338 },
    { date: "08/26", passRate: 92.8, latencyMs: 360 },
    { date: "08/27", passRate: 95.0, latencyMs: 328 },
    { date: "08/28", passRate: 94.7, latencyMs: 345 },
    { date: "08/29", passRate: 95.3, latencyMs: 335 },
    { date: "08/30", passRate: 94.7, latencyMs: 342 },
  ],
  loading: false,
  height: "300px",
});

const option = computed(() => {
  const dates = props.data.map(d => d.date);
  const passRates = props.data.map(d => d.passRate);
  const latencies = props.data.map(d => d.latencyMs);

  return {
    color: ["#1E40AF", "#F59E0B"],
    grid: { left: 50, right: 60, top: 40, bottom: 30 },
    legend: {
      top: 6,
      right: 0,
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 8,
      textStyle: {
        fontFamily: "Fira Sans",
        fontSize: 12,
        color: "#64748B",
      },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#1E3A8A",
      borderWidth: 0,
      textStyle: { color: "#fff", fontFamily: "Fira Sans" },
      axisPointer: { type: "line", lineStyle: { color: "rgba(255,255,255,0.4)" } },
    },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#E2E8F0" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#94A3B8",
        fontFamily: "Fira Sans",
        fontSize: 11,
      },
    },
    yAxis: [
      {
        type: "value",
        min: 90,
        max: 100,
        position: "left",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: "#F1F5F9" } },
        axisLabel: {
          color: "#1E40AF",
          fontFamily: "Fira Code",
          fontSize: 11,
          formatter: "{value}%",
        },
      },
      {
        type: "value",
        min: 300,
        max: 400,
        position: "right",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          color: "#F59E0B",
          fontFamily: "Fira Code",
          fontSize: 11,
          formatter: "{value}ms",
        },
      },
    ],
    series: [
      {
        name: "通过率",
        type: "line",
        smooth: true,
        yAxisIndex: 0,
        data: passRates,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { width: 2.5 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(30, 64, 175, 0.18)" },
              { offset: 1, color: "rgba(30, 64, 175, 0.02)" },
            ],
          },
        },
        emphasis: { focus: "series" },
      },
      {
        name: "平均延迟 (ms)",
        type: "line",
        smooth: true,
        yAxisIndex: 1,
        data: latencies,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { width: 2.5 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(245, 158, 11, 0.14)" },
              { offset: 1, color: "rgba(245, 158, 11, 0.02)" },
            ],
          },
        },
        emphasis: { focus: "series" },
      },
    ],
  };
});
</script>

<template>
  <EChart v-if="!loading" :option="option" :height="height" />
  <div v-else class="lb-trend-skeleton" :style="{ height }">
    <div class="lb-trend-skeleton__bar" v-for="i in 7" :key="i" :style="{ height: (30 + Math.random() * 50) + '%' }" />
  </div>
</template>

<style scoped>
.lb-trend-skeleton {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 16px 0;
}

.lb-trend-skeleton__bar {
  flex: 1;
  background: linear-gradient(180deg, var(--lb-surface-soft), var(--lb-surface-alt));
  border-radius: 4px;
  opacity: 0.6;
  animation: lb-pulse 1.5s ease-in-out infinite;
}

@keyframes lb-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 0.3; }
}
</style>
