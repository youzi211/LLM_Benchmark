<script setup lang="ts">
/**
 * 过滤 chips (Phase 3.2)
 * 用于状态/类型快速筛选.
 */
type FilterOption = { value: string; label: string; count?: number };

const props = defineProps<{
  modelValue: string;
  options: FilterOption[];
  /** 是否显示每个选项的计数 */
  showCount?: boolean;
  /** chip 大小: small | default */
  size?: "small" | "default";
}>();

const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

function pick(v: string) {
  emit("update:modelValue", v);
}
</script>

<template>
  <div class="lb-fc" :class="size === 'small' ? 'lb-fc--sm' : ''">
    <button
      v-for="opt in options"
      :key="opt.value"
      class="lb-fc__chip"
      :class="{ 'lb-fc__chip--on': modelValue === opt.value }"
      @click="pick(opt.value)"
      :type="'button'"
    >
      <span>{{ opt.label }}</span>
      <span v-if="showCount && opt.count !== undefined" class="lb-fc__count">{{ opt.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.lb-fc {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.lb-fc__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  font-family: "Fira Sans", sans-serif;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--lb-fg-soft);
  background: var(--lb-surface-soft);
  border: 1px solid var(--lb-border);
  border-radius: 999px;
  cursor: pointer;
  transition: all 150ms ease;
  line-height: 1.5;
}

.lb-fc__chip:hover {
  color: var(--lb-fg-strong);
  border-color: var(--lb-accent-soft-2);
  background: var(--lb-surface);
}

.lb-fc__chip--on {
  color: white;
  background: var(--lb-primary);
  border-color: var(--lb-primary);
}

.lb-fc__chip--on:hover {
  color: white;
  background: var(--lb-primary);
  opacity: 0.92;
}

.lb-fc__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  padding: 0 5px;
  height: 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  font-family: "Fira Code", monospace;
  font-size: 10.5px;
  font-weight: 600;
}

.lb-fc__chip:not(.lb-fc__chip--on) .lb-fc__count {
  background: var(--lb-accent-soft);
  color: var(--lb-primary);
}

.lb-fc--sm .lb-fc__chip {
  padding: 2px 10px;
  font-size: 11.5px;
}
</style>
