<script setup lang="ts">
/**
 * 顶栏连接状态条 (Phase 1.3)
 * 取代原先满屏横在每个 tab 顶部的红条错误.
 * 只在有失败时显示, 且只占顶栏右侧区域, 不挤压主内容.
 */
import { computed } from "vue";
import StatusDot from "./StatusDot.vue";
import { Warning } from "@element-plus/icons-vue";

const props = defineProps<{
  services: Array<{ key: string; name: string; state: "ok" | "warn" | "fail" | "pending" | "off"; detail?: string }>;
  lastError?: string | null;
}>();

const emit = defineEmits<{
  (e: "retry", key: string): void;
  (e: "dismiss"): void;
}>();

const hasIssue = computed(() => props.services.some(s => s.state === "fail" || s.state === "off"));
const hasWarn = computed(() => props.services.some(s => s.state === "warn" || s.state === "pending"));

const visible = computed(() => hasIssue.value || hasWarn.value);
const summary = computed(() => {
  const failed = props.services.filter(s => s.state === "fail" || s.state === "off");
  if (failed.length) return `服务异常: ${failed.map(s => s.name).join("、")}`;
  return "部分服务状态待定";
});
</script>

<template>
  <div v-if="visible" class="lb-conn-banner" :class="{ 'lb-conn-banner--fail': hasIssue }">
    <div class="lb-conn-banner__icon">
      <el-icon><Warning /></el-icon>
    </div>
    <div class="lb-conn-banner__summary">
      <span class="lb-conn-banner__text">{{ summary }}</span>
      <span v-if="lastError" class="lb-conn-banner__detail"> · {{ lastError }}</span>
    </div>
    <div class="lb-conn-banner__dots">
      <span
        v-for="svc in services"
        :key="svc.key"
        class="lb-conn-banner__svc"
        @click="emit('retry', svc.key)"
        :title="svc.detail || svc.name"
      >
        <StatusDot :state="svc.state" :label="svc.name" :size="7" :pulse="svc.state === 'ok'" />
      </span>
    </div>
    <el-button text size="small" @click="emit('dismiss')">知道了</el-button>
  </div>
</template>

<style scoped>
.lb-conn-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--lb-border);
  background: var(--lb-warning-bg, rgba(217, 119, 6, 0.08));
  color: var(--lb-warning);
  font-size: 13px;
  flex-wrap: wrap;
}

.lb-conn-banner--fail {
  background: var(--lb-danger-bg);
  color: var(--lb-danger);
}

:root[data-theme="dark"] .lb-conn-banner {
  background: rgba(245, 158, 11, 0.12);
}

:root[data-theme="dark"] .lb-conn-banner--fail {
  background: rgba(248, 113, 113, 0.12);
}

.lb-conn-banner__icon {
  display: flex;
  align-items: center;
}

.lb-conn-banner__summary {
  flex: 1 1 auto;
  min-width: 0;
}

.lb-conn-banner__text {
  font-weight: 600;
}

.lb-conn-banner__detail {
  color: inherit;
  opacity: 0.85;
  font-family: "Fira Code", monospace;
  font-size: 12px;
}

.lb-conn-banner__dots {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.lb-conn-banner__svc {
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: background 150ms ease;
}

.lb-conn-banner__svc:hover {
  background: rgba(255, 255, 255, 0.15);
}
</style>
