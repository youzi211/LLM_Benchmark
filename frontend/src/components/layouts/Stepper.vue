<script setup lang="ts">
/**
 * 步骤条 (Phase 3.4)
 * 横向步骤导航, 用于 SuiteView / ScheduleEditor 等多步表单.
 */
import { computed } from "vue";
import { Check } from "@element-plus/icons-vue";

interface StepDef {
  key: string;
  title: string;
  description?: string;
  optional?: boolean;
}

const props = withDefaults(defineProps<{
  steps: StepDef[];
  current: number;
  /** 是否可点击跳到任意步骤 */
  clickable?: boolean;
}>(), { clickable: false });

const emit = defineEmits<{ (e: "jump", idx: number): void }>();

const items = computed(() =>
  props.steps.map((s, i) => {
    const state: "done" | "active" | "pending" = i < props.current ? "done" : i === props.current ? "active" : "pending";
    return { ...s, idx: i, state };
  })
);
</script>

<template>
  <ol class="lb-stepper">
    <li
      v-for="item in items"
      :key="item.key"
      :class="['lb-stepper__item', `lb-stepper__item--${item.state}`, { 'lb-stepper__item--clickable': clickable }]"
      @click="clickable && item.state === 'done' && emit('jump', item.idx)"
    >
      <div class="lb-stepper__icon">
        <el-icon v-if="item.state === 'done'"><Check /></el-icon>
        <span v-else>{{ item.idx + 1 }}</span>
      </div>
      <div class="lb-stepper__body">
        <div class="lb-stepper__title">
          {{ item.title }}
          <span v-if="item.optional" class="lb-stepper__optional">(可选)</span>
        </div>
        <div v-if="item.description" class="lb-stepper__desc">{{ item.description }}</div>
      </div>
      <div v-if="item.idx < steps.length - 1" class="lb-stepper__line"></div>
    </li>
  </ol>
</template>

<style scoped>
.lb-stepper {
  list-style: none;
  margin: 0 0 20px;
  padding: 16px 12px;
  background: var(--lb-surface-soft);
  border: 1px solid var(--lb-border);
  border-radius: 12px;
  display: flex;
  align-items: flex-start;
  gap: 0;
}

.lb-stepper__item {
  flex: 1 1 0;
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 0 6px;
  min-width: 0;
}

.lb-stepper__item--clickable.lb-stepper__item--done {
  cursor: pointer;
}

.lb-stepper__icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  background: var(--lb-surface);
  border: 2px solid var(--lb-border);
  color: var(--lb-muted);
  position: relative;
  z-index: 1;
}

.lb-stepper__item--done .lb-stepper__icon {
  background: var(--lb-success);
  border-color: var(--lb-success);
  color: white;
}

.lb-stepper__item--active .lb-stepper__icon {
  background: var(--lb-primary);
  border-color: var(--lb-primary);
  color: white;
  box-shadow: 0 0 0 4px var(--lb-accent-soft);
}

.lb-stepper__body {
  min-width: 0;
  padding-top: 2px;
}

.lb-stepper__title {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--lb-fg-strong);
  line-height: 1.3;
}

.lb-stepper__item--pending .lb-stepper__title {
  color: var(--lb-muted);
}

.lb-stepper__optional {
  margin-left: 4px;
  font-size: 11px;
  color: var(--lb-muted);
  font-weight: 400;
}

.lb-stepper__desc {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--lb-muted);
  line-height: 1.4;
}

.lb-stepper__line {
  position: absolute;
  top: 14px;
  left: 36px;
  right: -10px;
  height: 2px;
  background: var(--lb-border);
  z-index: 0;
}

.lb-stepper__item--done .lb-stepper__line {
  background: var(--lb-success);
}

.lb-stepper__item--active .lb-stepper__line {
  background: linear-gradient(90deg, var(--lb-success) 0%, var(--lb-border) 100%);
}

@media (max-width: 760px) {
  .lb-stepper {
    flex-direction: column;
    gap: 12px;
  }
  .lb-stepper__line {
    display: none;
  }
}
</style>
