<script setup lang="ts">
/**
 * KPI 卡片 (Phase 3.1)
 * 顶栏小图标 + 标签 + 大数字 + 趋势
 */
import { computed } from "vue";
import { ArrowUp, ArrowDown, Minus } from "@element-plus/icons-vue";

const props = withDefaults(defineProps<{
  /** 标签: 今日评测 / 通过率 / 平均延迟 / 在线模型 */
  label: string;
  /** 主数值 (字符串, 允许 "94.7%" "342ms" 等含单位) */
  value: string | number;
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
  <div class="lb-kpi" :class="{ 'lb-kpi--loading': loading }">
    <div class="lb-kpi__head">
      <span class="lb-kpi__label">{{ label }}</span>
      <span class="lb-kpi__chip" :style="{ background: variantColor + '20', color: variantColor }">
        <span class="lb-kpi__chip-dot" :style="{ background: variantColor }"></span>
      </span>
    </div>
    <div v-if="loading" class="lb-kpi__skeleton"></div>
    <div v-else class="lb-kpi__value">{{ value }}</div>
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
  padding: 16px 18px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
  transition: transform 200ms ease, box-shadow 200ms ease;
  min-width: 0;
}

.lb-kpi:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.10);
}

.lb-kpi__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.lb-kpi__label {
  font-size: 12.5px;
  color: var(--lb-muted);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.lb-kpi__chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
}

.lb-kpi__chip-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.lb-kpi__value {
  font-family: "Fira Code", monospace;
  font-size: 28px;
  line-height: 1.1;
  color: var(--lb-fg-strong);
  font-weight: 600;
  margin-bottom: 6px;
  word-break: break-all;
}

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
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--lb-muted);
  line-height: 1.4;
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
</style>
