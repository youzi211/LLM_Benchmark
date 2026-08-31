<script setup lang="ts">
/**
 * 页面英雄区 (Phase 2.1)
 * 每个 tab 都有, 上方大标题 + 副标题, 右侧可放主操作 / 状态.
 * 替代原先 '直接进入表单' 的突兀感.
 */
defineProps<{
  /** 上方小字 (eyebrow), 全部大写, 突出板块 */
  eyebrow?: string;
  /** 主标题 (h1) */
  title: string;
  /** 副标题/说明 */
  description?: string;
  /** 提示信息 (蓝色小卡片) */
  hint?: string;
}>();
</script>

<template>
  <header class="lb-page-hero">
    <div class="lb-page-hero__copy">
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="lb-page-hero__desc">{{ description }}</p>
      <div v-if="hint" class="lb-page-hero__hint">{{ hint }}</div>
    </div>
    <div class="lb-page-hero__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.lb-page-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px;
  margin: 0 0 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius-lg);
  background: linear-gradient(135deg, #ffffff 0%, #f8fbff 55%, #edf5ff 100%);
  box-shadow: var(--lb-shadow);
}

:root[data-theme="dark"] .lb-page-hero {
  background: linear-gradient(135deg, #0f1729 0%, #111a2e 55%, #0a1424 100%);
}

.lb-page-hero__copy {
  min-width: 0;
  flex: 1 1 auto;
}

.lb-page-hero .eyebrow {
  margin: 0 0 4px;
  color: var(--lb-accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
}

.lb-page-hero h1 {
  margin: 0 0 6px;
  font-family: "Fira Code", monospace;
  font-size: 22px;
  line-height: 1.25;
  color: var(--lb-fg-strong);
  font-weight: 600;
}

.lb-page-hero__desc {
  margin: 0;
  color: var(--lb-muted);
  font-size: 13.5px;
  line-height: 1.55;
  max-width: 720px;
}

.lb-page-hero__hint {
  margin-top: 10px;
  padding: 8px 12px;
  background: var(--lb-accent-soft);
  border: 1px solid rgba(37, 99, 235, 0.18);
  border-radius: 8px;
  font-size: 12.5px;
  color: var(--lb-fg-soft);
  display: inline-block;
}

.lb-page-hero__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 0 0 auto;
}

@media (max-width: 760px) {
  .lb-page-hero {
    flex-direction: column;
    padding: 18px;
  }
  .lb-page-hero h1 {
    font-size: 18px;
  }
  .lb-page-hero__actions {
    width: 100%;
  }
  .lb-page-hero__actions :deep(.el-button) {
    flex: 1;
  }
}
</style>
