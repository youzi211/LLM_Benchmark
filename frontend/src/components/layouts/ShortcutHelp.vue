<script setup lang="ts">
/**
 * 快捷键帮助 (Phase 4.1)
 * 按 ? 触发, 弹出全屏遮罩列出所有快捷键.
 */
import { onMounted, onUnmounted, ref } from "vue";

const visible = ref(false);

function toggle() {
  visible.value = !visible.value;
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") visible.value = false;
}

function onShortcutEvent() {
  visible.value = true;
}

onMounted(() => {
  window.addEventListener("keydown", onKey);
  window.addEventListener("lb:shortcuts-help", onShortcutEvent as EventListener);
});
onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("lb:shortcuts-help", onShortcutEvent as EventListener);
});

const groups = [
  {
    title: "导航",
    items: [
      { keys: ["G", "B"], desc: "跳到 基础评测" },
      { keys: ["G", "S"], desc: "跳到 压测评测" },
      { keys: ["G", "I"], desc: "跳到 能力评测" },
      { keys: ["G", "O"], desc: "跳到 概览" },
      { keys: ["G", "U"], desc: "跳到 一键完整评测" },
      { keys: ["G", "D"], desc: "跳到 定时任务" },
    ],
  },
  {
    title: "其他",
    items: [
      { keys: ["?"], desc: "打开 / 关闭本帮助" },
      { keys: ["Esc"], desc: "关闭弹窗 / 抽屉" },
    ],
  },
];
</script>

<template>
  <span class="lb-sc-trigger" @click="toggle" title="快捷键 (?)">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h12" />
    </svg>
  </span>
  <Teleport to="body">
    <Transition name="lb-fade">
      <div v-if="visible" class="lb-sc-mask" @click.self="visible = false">
        <div class="lb-sc-card">
          <div class="lb-sc-head">
            <h2>键盘快捷键</h2>
            <button class="lb-sc-close" @click="visible = false" aria-label="关闭">×</button>
          </div>
          <div class="lb-sc-body">
            <section v-for="g in groups" :key="g.title" class="lb-sc-group">
              <h3>{{ g.title }}</h3>
              <ul>
                <li v-for="(it, i) in g.items" :key="i">
                  <span class="lb-sc-keys">
                    <kbd v-for="k in it.keys" :key="k">{{ k }}</kbd>
                  </span>
                  <span class="lb-sc-desc">{{ it.desc }}</span>
                </li>
              </ul>
            </section>
          </div>
          <div class="lb-sc-foot">按 <kbd>?</kbd> 或 <kbd>Esc</kbd> 关闭</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.lb-sc-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  color: var(--lb-muted);
  cursor: pointer;
  transition: all 150ms ease;
}
.lb-sc-trigger:hover {
  color: var(--lb-fg);
  background: var(--lb-accent-soft);
}

.lb-sc-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(2px);
}

.lb-sc-card {
  background: var(--lb-surface);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.3);
  width: min(560px, 92vw);
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.lb-sc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--lb-border);
}

.lb-sc-head h2 {
  margin: 0;
  font-family: "Fira Code", monospace;
  font-size: 16px;
  color: var(--lb-fg-strong);
}

.lb-sc-close {
  background: none;
  border: none;
  font-size: 22px;
  color: var(--lb-muted);
  cursor: pointer;
  line-height: 1;
  padding: 0 4px;
}
.lb-sc-close:hover { color: var(--lb-fg); }

.lb-sc-body {
  padding: 16px 20px;
  overflow-y: auto;
}

.lb-sc-group {
  margin-bottom: 14px;
}
.lb-sc-group:last-child { margin-bottom: 0; }
.lb-sc-group h3 {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--lb-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.lb-sc-group ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.lb-sc-group li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13.5px;
  color: var(--lb-fg);
}

.lb-sc-group li:hover {
  background: var(--lb-surface-soft);
}

.lb-sc-keys {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-width: 64px;
}

.lb-sc-desc {
  color: var(--lb-fg-soft);
}

.lb-sc-foot {
  padding: 10px 20px;
  border-top: 1px solid var(--lb-border);
  font-size: 12px;
  color: var(--lb-muted);
  text-align: center;
}

kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  font-family: "Fira Code", monospace;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--lb-fg-strong);
  background: var(--lb-surface-soft);
  border: 1px solid var(--lb-border);
  border-bottom-width: 2px;
  border-radius: 4px;
  line-height: 1;
}

.lb-fade-enter-active,
.lb-fade-leave-active {
  transition: opacity 200ms ease;
}
.lb-fade-enter-from,
.lb-fade-leave-to {
  opacity: 0;
}
</style>
