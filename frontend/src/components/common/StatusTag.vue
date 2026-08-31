<script setup lang="ts">
/**
 * 统一状态 tag (Phase 3.2)
 * 替代散落的 el-tag, 状态色彩统一从设计系统 token 读取.
 */
type Status = "completed" | "failed" | "error" | "running" | "pending" | "queued" | "partial" | "interrupted" | "ok" | string;

const props = withDefaults(defineProps<{
  status: Status;
  /** 可选覆盖显示文字, 默认用 status 本身 */
  label?: string;
  /** 是否显示左侧小圆点 (默认 true) */
  showDot?: boolean;
  /** 紧凑模式 (padding 减半) */
  compact?: boolean;
}>(), { showDot: true, compact: false });

const palette: Record<string, { color: string; bg: string }> = {
  completed:  { color: "var(--lb-success)", bg: "rgba(22, 163, 74, 0.10)" },
  ok:         { color: "var(--lb-success)", bg: "rgba(22, 163, 74, 0.10)" },
  success:    { color: "var(--lb-success)", bg: "rgba(22, 163, 74, 0.10)" },
  running:    { color: "var(--lb-warning)", bg: "rgba(217, 119, 6, 0.10)" },
  pending:    { color: "var(--lb-warning)", bg: "rgba(217, 119, 6, 0.10)" },
  queued:     { color: "var(--lb-info)",    bg: "rgba(59, 130, 246, 0.10)" },
  failed:     { color: "var(--lb-danger)",  bg: "rgba(220, 38, 38, 0.10)" },
  error:      { color: "var(--lb-danger)",  bg: "rgba(220, 38, 38, 0.10)" },
  interrupted:{ color: "var(--lb-danger)",  bg: "rgba(220, 38, 38, 0.10)" },
  partial:    { color: "var(--lb-warning)", bg: "rgba(217, 119, 6, 0.10)" },
};

const colorOf = (s: string) => palette[s] ?? { color: "var(--lb-muted)", bg: "rgba(100, 116, 139, 0.10)" };
</script>

<template>
  <span class="lb-status-tag" :class="{ 'lb-status-tag--compact': compact }" :style="{ color: colorOf(status).color, background: colorOf(status).bg }">
    <span v-if="showDot" class="lb-status-tag__dot" :style="{ background: colorOf(status).color }" />
    <span>{{ label ?? status }}</span>
  </span>
</template>

<style scoped>
.lb-status-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}

.lb-status-tag--compact {
  padding: 1px 6px;
  font-size: 11px;
}

.lb-status-tag__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
