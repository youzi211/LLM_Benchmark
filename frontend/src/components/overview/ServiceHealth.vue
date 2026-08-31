<script setup lang="ts">
/**
 * 服务健康面板 (Phase 3.1)
 * 显示 API / EvalScope / Scheduler / Sandbox 状态, 每个可点击 retry 或跳配置.
 */
import { computed } from "vue";
import StatusDot from "@/components/common/StatusDot.vue";
import { ArrowRight, Refresh, Setting } from "@element-plus/icons-vue";

interface Service {
  key: string;
  name: string;
  state: "ok" | "warn" | "fail" | "pending" | "off";
  detail?: string;
  latencyMs?: number;
}

const props = withDefaults(defineProps<{
  services?: Service[];
  loading?: boolean;
}>(), {
  services: () => [
    { key: "api",      name: "FastAPI 网关",  state: "ok",  detail: "127.0.0.1:8020",  latencyMs: 12 },
    { key: "models",   name: "模型 API",      state: "ok",  detail: "已配置 3 个",       latencyMs: 280 },
    { key: "evalscope",name: "EvalScope",     state: "off", detail: "未运行, 见评测环境" },
    { key: "scheduler",name: "调度服务",      state: "ok",  detail: "APScheduler",        latencyMs: 8 },
  ],
  loading: false,
});

const emit = defineEmits<{
  (e: "retry", key: string): void;
  (e: "configure", key: string): void;
}>();

const okCount = computed(() => props.services.filter(s => s.state === "ok").length);
const total = computed(() => props.services.length);
</script>

<template>
  <div class="lb-sh">
    <div class="lb-sh__head">
      <h3>服务健康</h3>
      <span class="lb-sh__summary" :class="{ 'lb-sh__summary--full': okCount === total }">
        {{ okCount }} / {{ total }} 在线
      </span>
    </div>

    <div v-if="loading" class="lb-sh__list">
      <div v-for="i in 4" :key="i" class="lb-sh__skel"></div>
    </div>

    <ul v-else class="lb-sh__list">
      <li v-for="svc in services" :key="svc.key" class="lb-sh__item">
        <StatusDot :state="svc.state" :size="8" :pulse="svc.state === 'ok'" />
        <div class="lb-sh__meta">
          <div class="lb-sh__name">{{ svc.name }}</div>
          <div class="lb-sh__detail" :title="svc.detail">{{ svc.detail }}</div>
        </div>
        <div v-if="svc.latencyMs !== undefined" class="lb-sh__lat">
          {{ svc.latencyMs }}<span>ms</span>
        </div>
        <div class="lb-sh__actions">
          <el-button
            v-if="svc.state === 'fail' || svc.state === 'off'"
            size="small"
            text
            type="primary"
            @click="emit('retry', svc.key)"
            title="重试"
          >
            <el-icon><Refresh /></el-icon>
          </el-button>
          <el-button
            size="small"
            text
            @click="emit('configure', svc.key)"
            title="配置"
          >
            <el-icon><Setting /></el-icon>
          </el-button>
          <el-icon class="lb-sh__arrow"><ArrowRight /></el-icon>
        </div>
      </li>
    </ul>

    <div class="lb-sh__foot">
      <el-link type="primary" :underline="false" @click="emit('configure', 'all')">
        查看完整诊断 <el-icon class="lb-sh__arrow"><ArrowRight /></el-icon>
      </el-link>
    </div>
  </div>
</template>

<style scoped>
.lb-sh {
  padding: 18px 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.lb-sh__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--lb-border);
}

.lb-sh__head h3 {
  margin: 0;
  font-family: "Fira Code", monospace;
  font-size: 14px;
  font-weight: 600;
  color: var(--lb-fg-strong);
}

.lb-sh__summary {
  font-family: "Fira Code", monospace;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--lb-warning-bg, rgba(217, 119, 6, 0.10));
  color: var(--lb-warning);
}

.lb-sh__summary--full {
  background: var(--lb-success-tint);
  color: var(--lb-success);
}

.lb-sh__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 auto;
}

.lb-sh__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 8px;
  transition: background 150ms ease;
}

.lb-sh__item:hover {
  background: var(--lb-surface-soft);
}

.lb-sh__meta {
  flex: 1 1 auto;
  min-width: 0;
}

.lb-sh__name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--lb-fg-strong);
  line-height: 1.3;
}

.lb-sh__detail {
  font-size: 11.5px;
  color: var(--lb-muted);
  font-family: "Fira Code", monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lb-sh__lat {
  font-family: "Fira Code", monospace;
  font-size: 13px;
  color: var(--lb-fg-soft);
}

.lb-sh__lat span {
  font-size: 10px;
  color: var(--lb-muted);
  margin-left: 2px;
}

.lb-sh__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  color: var(--lb-muted);
}

.lb-sh__arrow {
  font-size: 14px;
  opacity: 0;
  transition: opacity 150ms ease;
}

.lb-sh__item:hover .lb-sh__arrow {
  opacity: 1;
}

.lb-sh__skel {
  height: 44px;
  border-radius: 8px;
  background: linear-gradient(90deg, var(--lb-surface-soft) 25%, var(--lb-surface-alt) 50%, var(--lb-surface-soft) 75%);
  background-size: 200% 100%;
  animation: lb-sh-shimmer 1.5s infinite;
}

@keyframes lb-sh-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.lb-sh__foot {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--lb-border);
  text-align: center;
}
</style>
