<script setup lang="ts">
/**
 * 连接 / 状态点 (Phase 1.3)
 * 用法: <StatusDot state="ok" /> | "warn" | "fail" | "pending" | "off"
 * 配套文字可选, 通过 label 槽位或 prop 提供.
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    state: "ok" | "warn" | "fail" | "pending" | "off";
    label?: string;
    pulse?: boolean;
    size?: number;
  }>(),
  { pulse: true, size: 8 }
);

const colorMap = {
  ok: "var(--lb-success)",
  warn: "var(--lb-warning)",
  fail: "var(--lb-danger)",
  pending: "var(--lb-info)",
  off: "var(--lb-muted)",
};

const dotColor = computed(() => colorMap[props.state]);
</script>

<template>
  <span class="lb-status-dot" :title="label">
    <span
      class="lb-status-dot__core"
      :class="{ 'lb-status-dot--pulse': pulse && (state === 'ok' || state === 'warn' || state === 'fail') }"
      :style="{
        background: dotColor,
        width: size + 'px',
        height: size + 'px',
        boxShadow: `0 0 0 4px ${dotColor}26`
      }"
    />
    <span v-if="label" class="lb-status-dot__label">{{ label }}</span>
  </span>
</template>

<style scoped>
.lb-status-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--lb-muted);
  line-height: 1;
}

.lb-status-dot__core {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
}

@keyframes lb-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.lb-status-dot--pulse {
  animation: lb-pulse 2s ease-in-out infinite;
}
</style>
