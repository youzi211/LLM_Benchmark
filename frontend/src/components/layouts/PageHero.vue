<script setup lang="ts">
/**
 * 轻量页面标题区：标题与说明在左，主操作在右。
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
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0;
  margin: 0 0 24px;
}

.lb-page-hero__copy {
  min-width: 0;
  flex: 1 1 auto;
}

.lb-page-hero .eyebrow {
  margin: 0 0 8px;
  color: var(--lb-muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.lb-page-hero h1 {
  margin: 0 0 8px;
  font-family: var(--font-heading);
  font-size: 28px;
  line-height: 1.3;
  color: var(--lb-fg-strong);
  font-weight: 650;
}

.lb-page-hero__desc {
  margin: 0;
  color: var(--lb-muted);
  font-size: 13px;
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

.lb-page-hero__actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

@media (max-width: 760px) {
  .lb-page-hero {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
  .lb-page-hero h1 {
    font-size: 24px;
  }
  .lb-page-hero__actions {
    width: 100%;
  }
  .lb-page-hero__actions :deep(.el-button) {
    flex: 1;
  }
}
</style>
