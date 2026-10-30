<script setup lang="ts">
/**
 * KPI 卡片 (Phase 3.1)
 * 顶栏小图标 + 标签 + 大数字 + 趋势
 */
import { computed } from "vue";
import { ArrowUp, ArrowDown, CircleCheck, Cpu, DataAnalysis, Lightning, Minus, Timer, Warning } from "@element-plus/icons-vue";

const props = withDefaults(defineProps<{
  /** 标签: 今日评测 / 执行完成率 / 平均任务耗时 / 已配置模型 */
  label: string;
  /** 主数值 (字符串, 允许 "94.7%" "342ms" 等含单位) */
  value: string | number;
  /** 单位与数字分开排版，长时长不再显示为一串毫秒。 */
  unit?: string;
  /** 趋势百分比 (正=上升, 负=下降, 0=持平). 可选. */
  trend?: number;
  /** 趋势对比文字, 例如 "较昨日" "较上周" */
  trendLabel?: string;
  /** 主色变体: primary | success | warning | danger | info | cta */
  variant?: "primary" | "success" | "warning" | "danger" | "info" | "cta";
  /** 副标题 (底部补充文字) */
  caption?: string;
  /** 是否在加载中 (显示骨架) */
  loading?: boolean;
}>(), {
  variant: "primary",
  trendLabel: "较昨日",
  loading: false,
});

const variantColor = computed(() => {
  switch (props.variant) {
    case "success": return "var(--lb-success)";
    case "warning": return "var(--lb-warning)";
    case "danger":  return "var(--lb-danger)";
    case "info":    return "var(--lb-info)";
    case "cta":     return "var(--lb-cta)";
    case "primary":
    default:        return "var(--lb-primary)";
  }
});

const metricIcon = computed(() => {
  switch (props.variant) {
    case "success": return CircleCheck;
    case "warning": return Timer;
    case "info": return Cpu;
    case "danger": return Warning;
    case "cta": return Lightning;
    default: return DataAnalysis;
  }
});

const trendColor = computed(() => {
  if (props.trend === undefined || props.trend === null) return "var(--lb-muted)";
  if (props.trend > 0) return "var(--lb-success)";
  if (props.trend < 0) return "var(--lb-danger)";
  return "var(--lb-muted)";
});

const trendIcon = computed(() => {
  if (props.trend === undefined || props.trend === null) return null;
  if (props.trend > 0) return ArrowUp;
  if (props.trend < 0) return ArrowDown;
  return Minus;
});

const trendText = computed(() => {
  if (props.trend === undefined || props.trend === null) return "";
  const sign = props.trend > 0 ? "+" : "";
  return sign + props.trend.toFixed(1) + "%";
});
</script>

<template>
  <div class="lb-kpi" :class="{ 'lb-kpi--loading': loading }" :style="{ '--kpi-color': variantColor }">
    <div class="lb-kpi__head">
      <span class="lb-kpi__label">{{ label }}</span>
      <span class="lb-kpi__chip" aria-hidden="true">
        <el-icon><component :is="metricIcon" /></el-icon>
      </span>
    </div>
    <div v-if="loading" class="lb-kpi__skeleton"></div>
    <div v-else class="lb-kpi__value"><span class="lb-kpi__number">{{ value }}</span><span v-if="unit" class="lb-kpi__unit">{{ unit }}</span></div>
    <div v-if="!loading && trend !== undefined" class="lb-kpi__trend" :style="{ color: trendColor }">
      <el-icon v-if="trendIcon" class="lb-kpi__trend-icon"><component :is="trendIcon" /></el-icon>
      <span>{{ trendText }}</span>
      <span class="lb-kpi__trend-label">{{ trendLabel }}</span>
    </div>
    <div v-if="!loading && caption" class="lb-kpi__caption">{{ caption }}</div>
  </div>
</template>

<style scoped>
.lb-kpi {
  position: relative;
  padding: 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
  min-width: 0;
}

.lb-kpi__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.lb-kpi__label {
  font-size: 12px;
  color: var(--lb-fg-soft);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.lb-kpi__chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  font-size: 16px;
  color: var(--kpi-color);
  background: color-mix(in srgb, var(--kpi-color) 8%, var(--lb-surface));
}

.lb-kpi__value {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  font-family: var(--font-body);
  font-variant-numeric: tabular-nums;
  font-size: 32px;
  line-height: 1.2;
  color: var(--lb-fg-strong);
  font-weight: 600;
  letter-spacing: -0.8px;
}

.lb-kpi__number { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lb-kpi__unit { flex-shrink: 0; color: var(--lb-muted); font-size: 13px; font-weight: 400; letter-spacing: 0; }

.lb-kpi__trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  font-weight: 500;
}

.lb-kpi__trend-icon {
  width: 12px;
  height: 12px;
}

.lb-kpi__trend-label {
  color: var(--lb-muted);
  margin-left: 4px;
  font-weight: 400;
}

.lb-kpi__caption {
  margin-top: 10px;
  font-size: 11px;
  color: var(--lb-muted);
  line-height: 1.5;
}

.lb-kpi__skeleton {
  height: 36px;
  margin-bottom: 8px;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--lb-surface-soft) 25%, var(--lb-surface-alt) 50%, var(--lb-surface-soft) 75%);
  background-size: 200% 100%;
  animation: lb-shimmer 1.5s infinite;
}

@keyframes lb-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

@media (max-width: 480px) {
  .lb-kpi { padding: 16px; }
  .lb-kpi__head { margin-bottom: 16px; gap: 4px; }
  .lb-kpi__chip { width: 24px; height: 24px; font-size: 14px; }
  .lb-kpi__value { font-size: 28px; gap: 4px; }
  .lb-kpi__unit { font-size: 11px; }
}
</style>
