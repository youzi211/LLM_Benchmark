<script setup lang="ts">
/**
 * 当前运行中任务 (Phase 3.1)
 * 每个任务一行: 进度条 + 已用时间 + 阶段 + 类型
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { VideoPlay, WarningFilled } from "@element-plus/icons-vue";
import type { OverviewRunningTask } from "@/overview/taskOverview";

const props = withDefaults(defineProps<{
  tasks?: OverviewRunningTask[];
  loading?: boolean;
  error?: string;
  partialError?: string;
  max?: number;
}>(), {
  tasks: () => [],
  loading: false,
  error: "",
  partialError: "",
  max: 6,
});

const router = useRouter();

// 每秒刷新真实任务的已用时间。
const tick = ref(0);
let timer: number | undefined;
onMounted(() => { timer = window.setInterval(() => { tick.value++; }, 1000); });
onUnmounted(() => { if (timer) window.clearInterval(timer); });

const visible = computed(() => props.tasks.slice(0, props.max));

const typeLabel = (t: OverviewRunningTask["type"]) => {
  if (t === "basic") return "基础";
  if (t === "stress") return "压测";
  return "能力";
};

const typeColor = (t: OverviewRunningTask["type"]) => {
  if (t === "basic") return "var(--lb-info)";
  if (t === "stress") return "var(--lb-warning)";
  return "var(--lb-primary)";
};

const elapsed = (startedAt?: number) => {
  void tick.value; // 触发响应式
  if (startedAt === undefined) return "—";
  const sec = Math.floor((Date.now() - startedAt) / 1000);
  if (sec < 60) return sec + "秒";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m + "分" + (s < 10 ? "0" + s : s) + "秒";
};

const progressColor = (p?: number) => {
  if (p === undefined) return "var(--lb-info)";
  if (p < 30) return "var(--lb-info)";
  if (p < 70) return "var(--lb-primary)";
  return "var(--lb-success)";
};

const goToTask = (t: OverviewRunningTask) => {
  const path = t.type === "basic" ? "/basic" : t.type === "stress" ? "/stress" : "/intelligence";
  router.push(path);
};
</script>

<template>
  <div class="lb-rt">
    <div class="lb-rt__head">
      <h3>当前运行中</h3>
      <span class="lb-rt__count">{{ tasks.length }} 个任务</span>
    </div>

    <div v-if="loading" class="lb-rt__list">
      <div v-for="i in 3" :key="i" class="lb-rt__skel"></div>
    </div>

    <div v-else-if="error" class="lb-rt__empty lb-rt__empty--error" role="alert">
      <el-icon class="lb-rt__empty-icon"><WarningFilled /></el-icon>
      <p>运行中任务不可用</p>
      <p class="lb-rt__empty-hint">{{ error }}</p>
    </div>

    <div v-else-if="visible.length === 0" class="lb-rt__empty">
      <el-icon class="lb-rt__empty-icon"><VideoPlay /></el-icon>
      <p>{{ partialError ? "部分任务数据不可用" : "当前没有运行中的任务" }}</p>
      <p v-if="partialError" class="lb-rt__empty-hint">{{ partialError }}；其余任务中暂无运行中记录</p>
      <p v-else class="lb-rt__empty-hint">从 <el-link type="primary" underline="never" @click="router.push('/basic')">基础评测</el-link> /
      <el-link type="primary" underline="never" @click="router.push('/stress')">压测评测</el-link> /
      <el-link type="primary" underline="never" @click="router.push('/intelligence')">能力评测</el-link> 启动</p>
    </div>

    <ul v-else class="lb-rt__list">
      <li v-for="t in visible" :key="t.id" class="lb-rt__item" @click="goToTask(t)">
        <div class="lb-rt__row1">
          <span class="lb-rt__type" :style="{ color: typeColor(t.type), background: typeColor(t.type) + '15' }">
            {{ typeLabel(t.type) }}
          </span>
          <span class="lb-rt__model">{{ t.model }}</span>
          <span class="lb-rt__time">{{ elapsed(t.startedAt) }}</span>
        </div>
        <div class="lb-rt__row2">
          <span class="lb-rt__stage">{{ t.stage || "准备中…" }}</span>
          <span class="lb-rt__pct">{{ t.progress === undefined ? "—" : t.progress + "%" }}</span>
        </div>
        <div class="lb-rt__bar">
          <div
            class="lb-rt__bar-fill"
            :style="{ width: (t.progress ?? 0) + '%', background: progressColor(t.progress) }"
          />
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.lb-rt {
  padding: 18px 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.lb-rt__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--lb-border);
}

.lb-rt__head h3 {
  margin: 0;
  font-family: "Fira Code", monospace;
  font-size: 14px;
  font-weight: 600;
  color: var(--lb-fg-strong);
}

.lb-rt__count {
  font-family: "Fira Code", monospace;
  font-size: 12px;
  color: var(--lb-primary);
  background: var(--lb-accent-soft);
  padding: 2px 8px;
  border-radius: 999px;
}

.lb-rt__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1 1 auto;
  overflow-y: auto;
}

.lb-rt__item {
  padding: 10px 12px;
  border: 1px solid var(--lb-border-soft);
  border-radius: 10px;
  cursor: pointer;
  transition: all 150ms ease;
}

.lb-rt__item:hover {
  border-color: var(--lb-accent-soft-2);
  background: var(--lb-surface-soft);
  transform: translateX(2px);
}

.lb-rt__row1 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.lb-rt__type {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  flex-shrink: 0;
}

.lb-rt__model {
  flex: 1 1 auto;
  font-size: 13px;
  font-weight: 500;
  color: var(--lb-fg-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lb-rt__time {
  font-family: "Fira Code", monospace;
  font-size: 11.5px;
  color: var(--lb-muted);
  flex-shrink: 0;
}

.lb-rt__row2 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.lb-rt__stage {
  font-size: 12px;
  color: var(--lb-fg-soft);
}

.lb-rt__pct {
  font-family: "Fira Code", monospace;
  font-size: 11.5px;
  color: var(--lb-muted);
}

.lb-rt__bar {
  height: 4px;
  background: var(--lb-surface-alt);
  border-radius: 999px;
  overflow: hidden;
}

.lb-rt__bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 600ms ease, background 300ms ease;
}

.lb-rt__empty {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 28px 16px;
  color: var(--lb-muted);
  text-align: center;
}

.lb-rt__empty-icon {
  font-size: 36px;
  margin-bottom: 8px;
  opacity: 0.5;
}

.lb-rt__empty p {
  margin: 4px 0;
  font-size: 13.5px;
  color: var(--lb-fg-soft);
}

.lb-rt__empty--error .lb-rt__empty-icon {
  color: var(--lb-danger);
}

.lb-rt__empty-hint {
  font-size: 12px;
  color: var(--lb-muted);
}

.lb-rt__skel {
  height: 64px;
  border-radius: 10px;
  background: linear-gradient(90deg, var(--lb-surface-soft) 25%, var(--lb-surface-alt) 50%, var(--lb-surface-soft) 75%);
  background-size: 200% 100%;
  animation: lb-rt-shimmer 1.5s infinite;
}

@keyframes lb-rt-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
</style>
