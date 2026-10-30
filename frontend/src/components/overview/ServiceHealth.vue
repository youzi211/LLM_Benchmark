<script setup lang="ts">
/**
 * 服务健康信息面板，保留真实重试与配置入口。
 */
import { computed } from "vue";
import StatusDot from "@/components/common/StatusDot.vue";
import { Refresh, Setting } from "@element-plus/icons-vue";

interface Service {
  key: string;
  name: string;
  state: "ok" | "warn" | "fail" | "pending" | "off";
  detail?: string;
  latencyMs?: number;
}

const props = withDefaults(defineProps<{
  services: Service[];
  loading?: boolean;
}>(), {
  loading: false,
});

const okCount = computed(() => props.services.filter(s => s.state === "ok").length);
const total = computed(() => props.services.length);
const emit = defineEmits<{
  retry: [key: string];
  configure: [key: string];
}>();
const stateLabels = { ok: "正常", warn: "需关注", fail: "异常", pending: "检查中", off: "未启用" };
</script>

<template>
  <div class="lb-sh">
    <div class="lb-sh__head">
      <h3>服务健康</h3>
      <span class="lb-sh__summary" :class="{ 'lb-sh__summary--full': total > 0 && okCount === total }">
        {{ okCount }} / {{ total }} 正常
      </span>
    </div>

    <div v-if="loading" class="lb-sh__list">
      <div v-for="i in 4" :key="i" class="lb-sh__skel"></div>
    </div>

    <ul v-else class="lb-sh__list">
      <li v-for="svc in services" :key="svc.key" class="lb-sh__item">
        <StatusDot :state="svc.state" :size="7" />
        <div class="lb-sh__meta">
          <div class="lb-sh__name">{{ svc.name }}</div>
          <div class="lb-sh__detail" :title="svc.detail">{{ svc.detail }}</div>
        </div>
        <div v-if="svc.latencyMs !== undefined" class="lb-sh__lat">
          {{ svc.latencyMs }}<span>ms</span>
        </div>
        <span class="lb-sh__state" :class="`lb-sh__state--${svc.state}`">{{ stateLabels[svc.state] }}</span>
        <div class="lb-sh__actions">
          <el-button v-if="svc.state === 'fail' || svc.state === 'off' || svc.state === 'warn'" text circle size="small" :icon="Refresh" :aria-label="`重试${svc.name}`" :title="`重试${svc.name}`" @click="emit('retry', svc.key)" />
          <el-button text circle size="small" :icon="Setting" :aria-label="`配置${svc.name}`" :title="`配置${svc.name}`" @click="emit('configure', svc.key)" />
        </div>
      </li>
    </ul>

    <div class="lb-sh__foot">配置请使用顶部「评测环境」入口</div>
  </div>
</template>

<style scoped>
.lb-sh {
  padding: 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.lb-sh__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--lb-border);
}

.lb-sh__head h3 {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--lb-fg-strong);
}

.lb-sh__summary {
  font-size: 11px;
  white-space: nowrap;
  color: var(--lb-muted);
}

.lb-sh__summary--full {
  color: var(--lb-success);
}

.lb-sh__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  flex: 1 1 auto;
}

.lb-sh__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 0;
  border-bottom: 1px solid var(--lb-border-soft);
}

.lb-sh__item:last-child { border-bottom: 0; }

.lb-sh__meta {
  flex: 1 1 auto;
  min-width: 0;
}

.lb-sh__name {
  font-size: 12px;
  font-weight: 500;
  color: var(--lb-fg-strong);
  line-height: 1.5;
}

.lb-sh__detail {
  margin-top: 3px;
  font-size: 11px;
  color: var(--lb-muted);
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

.lb-sh__state { flex-shrink: 0; font-size: 10px; color: var(--lb-muted); }
.lb-sh__state--ok { color: var(--lb-success); }
.lb-sh__state--warn { color: var(--lb-warning); }
.lb-sh__state--fail { color: var(--lb-danger); }
.lb-sh__actions { display: flex; flex-shrink: 0; gap: 2px; }
.lb-sh__actions :deep(.el-button + .el-button) { margin-left: 0; }

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
  margin-top: 4px;
  padding-top: 14px;
  border-top: 1px solid var(--lb-border);
  color: var(--lb-muted);
  font-size: 11px;
}
</style>
