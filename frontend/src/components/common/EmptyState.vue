<script setup lang="ts">
/**
 * 品牌空状态 (Phase 3.2)
 * 替代 Element Plus 默认插画, 简单 SVG 自绘.
 */
import { computed } from "vue";

const props = withDefaults(defineProps<{
  /** 主标题 */
  title?: string;
  /** 副标题 / 引导文字 */
  description?: string;
  /** 主题: list / search / error / success */
  variant?: "list" | "search" | "error" | "success";
  /** 自定义图标 (Element Plus 组件) */
  icon?: unknown;
  /** 主操作按钮文字 */
  actionLabel?: string;
}>(), {
  title: "暂无数据",
  description: "",
  variant: "list",
});

const emit = defineEmits<{ (e: "action"): void }>();

const paths: Record<string, string> = {
  list: "M3 6h18M3 12h18M3 18h12",
  search: "M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z",
  error: "M12 8v5m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  success: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
};
const colorByVariant: Record<string, string> = {
  list: "var(--lb-muted)",
  search: "var(--lb-info)",
  error: "var(--lb-danger)",
  success: "var(--lb-success)",
};
const dPath = computed(() => paths[props.variant] ?? paths.list);
const colorOf = computed(() => colorByVariant[props.variant] ?? colorByVariant.list);
</script>

<template>
  <div class="lb-empty">
    <div class="lb-empty__icon" :style="{ background: colorOf + '15', color: colorOf }">
      <svg v-if="!icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path :d="dPath" />
      </svg>
      <component v-else :is="icon" style="width: 28px; height: 28px;" />
    </div>
    <h3 class="lb-empty__title">{{ title }}</h3>
    <p v-if="description" class="lb-empty__desc">{{ description }}</p>
    <el-button v-if="actionLabel" type="primary" plain size="small" @click="emit('action')">
      {{ actionLabel }}
    </el-button>
  </div>
</template>

<style scoped>
.lb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
  min-height: 240px;
}

.lb-empty__icon {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 14px;
}

.lb-empty__title {
  margin: 0 0 6px;
  font-family: "Fira Code", monospace;
  font-size: 15px;
  color: var(--lb-fg-strong);
  font-weight: 600;
}

.lb-empty__desc {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--lb-muted);
  line-height: 1.6;
  max-width: 360px;
}
</style>
