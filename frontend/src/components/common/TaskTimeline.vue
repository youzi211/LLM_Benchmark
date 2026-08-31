<script setup lang="ts">
/**
 * 任务进度时间轴 (Phase 3.3)
 * 显示任务生命周期: 提交 -> 启动 -> 运行 -> 收尾 -> 完成
 * 状态语义驱动, 不依赖后端实时数据.
 */
import { computed } from "vue";
import { Check, Loading, CircleClose, Clock, VideoPlay } from "@element-plus/icons-vue";

const props = defineProps<{
  status?: string;
  started_at?: string;
  finished_at?: string;
  error?: unknown;
}>();

interface Step {
  key: string;
  label: string;
  state: "done" | "active" | "fail" | "pending";
  ts?: string;
  icon: unknown;
}

const steps = computed<Step[]>(() => {
  const status = String(props.status || "");
  const isRunning = status === "running";
  const isDone = status === "completed";
  const isFailed = ["failed", "error", "interrupted"].includes(status);

  return [
    { key: "submit", label: "已提交", state: "done", icon: Check },
    { key: "queue",  label: "排队中", state: isRunning || isDone || isFailed ? "done" : "active", icon: Check },
    { key: "run",    label: "执行中", state: isDone ? "done" : isFailed ? "fail" : isRunning ? "active" : "pending", icon: isFailed ? CircleClose : isRunning ? Loading : VideoPlay },
    { key: "finish", label: "完成",   state: isDone ? "done" : isFailed ? "fail" : "pending", icon: isFailed ? CircleClose : Check },
  ];
});

function tsLabel(s?: string) {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}
</script>

<template>
  <div class="lb-tl">
    <ol class="lb-tl__steps">
      <li v-for="(s, i) in steps" :key="s.key" :class="['lb-tl__step', `lb-tl__step--${s.state}`]">
        <div class="lb-tl__icon">
          <el-icon v-if="s.state === 'active'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else><component :is="s.icon" /></el-icon>
        </div>
        <div v-if="i < steps.length - 1" class="lb-tl__line"></div>
        <div class="lb-tl__body">
          <div class="lb-tl__label">{{ s.label }}</div>
          <div v-if="s.key === 'run' && started_at" class="lb-tl__ts">开始 {{ tsLabel(started_at) }}</div>
          <div v-if="s.key === 'finish' && finished_at" class="lb-tl__ts">完成 {{ tsLabel(finished_at) }}</div>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.lb-tl {
  margin: 8px 0 16px;
  padding: 14px;
  background: var(--lb-surface-soft);
  border: 1px solid var(--lb-border-soft);
  border-radius: 10px;
}

.lb-tl__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: flex-start;
  gap: 0;
}

.lb-tl__step {
  flex: 1 1 0;
  position: relative;
  text-align: center;
  min-width: 0;
}

.lb-tl__icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin: 0 auto 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  border: 2px solid var(--lb-border);
  background: var(--lb-surface);
  color: var(--lb-muted);
  position: relative;
  z-index: 1;
}

.lb-tl__step--done .lb-tl__icon {
  border-color: var(--lb-success);
  background: var(--lb-success);
  color: white;
}

.lb-tl__step--active .lb-tl__icon {
  border-color: var(--lb-primary);
  background: var(--lb-primary);
  color: white;
  box-shadow: 0 0 0 4px var(--lb-accent-soft);
}

.lb-tl__step--fail .lb-tl__icon {
  border-color: var(--lb-danger);
  background: var(--lb-danger);
  color: white;
}

.lb-tl__step--pending .lb-tl__icon {
  opacity: 0.5;
}

.lb-tl__line {
  position: absolute;
  top: 14px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--lb-border);
  z-index: 0;
}

.lb-tl__step--done .lb-tl__line {
  background: var(--lb-success);
}

.lb-tl__step--active .lb-tl__line {
  background: linear-gradient(90deg, var(--lb-success) 0%, var(--lb-primary) 100%);
}

.lb-tl__step--fail .lb-tl__line {
  background: var(--lb-danger);
}

.lb-tl__label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--lb-fg-strong);
}

.lb-tl__step--pending .lb-tl__label {
  color: var(--lb-muted);
}

.lb-tl__ts {
  font-family: "Fira Code", monospace;
  font-size: 10.5px;
  color: var(--lb-muted);
  margin-top: 2px;
}
</style>
