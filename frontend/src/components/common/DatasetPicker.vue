<script setup lang="ts">
import { computed, ref, useId } from "vue";
import { ArrowDown } from "@element-plus/icons-vue";
import type { DatasetMeta } from "@/api/evaluations";

interface Props {
  datasets: Record<string, DatasetMeta>;
  defaultDatasets?: string[];
  modelValue?: string[];
  subsetModelValue?: Record<string, string[]>;
  subsetOverride?: Record<string, boolean>;
  disabled?: boolean;
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  defaultDatasets: () => [],
  modelValue: () => [],
  subsetModelValue: () => ({}),
  subsetOverride: () => ({}),
  disabled: false,
  loading: false,
});

const emit = defineEmits<{
  "update:modelValue": [string[]];
  "update:subsetModelValue": [Record<string, string[]>];
  "update:subsetOverride": [Record<string, boolean>];
}>();

type FilterMode = "default" | "all" | "judge" | "sandbox";
const filterMode = ref<FilterMode>(props.defaultDatasets.length ? "default" : "all");
const expanded = ref<Set<string>>(new Set());
const pickerId = useId();
const filters: Array<{ value: FilterMode; label: string }> = [
  { value: "default", label: "默认推荐" }, { value: "all", label: "全部数据集" },
  { value: "judge", label: "需 Judge" }, { value: "sandbox", label: "需 Sandbox" },
];

const datasetEntries = computed(() => {
  return Object.entries(props.datasets)
    .filter(([, meta]) => meta.available_local)
    .sort(([a], [b]) => {
      const da = props.defaultDatasets.includes(a);
      const db = props.defaultDatasets.includes(b);
      if (da !== db) return da ? -1 : 1;
      return (props.datasets[a]?.pretty_name || a).localeCompare(props.datasets[b]?.pretty_name || b);
    });
});

const visibleEntries = computed(() => {
  const entries = datasetEntries.value;
  switch (filterMode.value) {
    case "all":
      return entries;
    case "default":
      return entries.filter(([n]) => props.defaultDatasets.includes(n));
    case "judge":
      return entries.filter(([, m]) => Boolean(m.needs_judge));
    case "sandbox":
      return entries.filter(([, m]) => Array.isArray(m.categories) && m.categories.includes("Coding"));
  }
  return entries;
});

function isChecked(name: string): boolean {
  return props.modelValue.includes(name);
}

function togglePick(name: string, checked: unknown) {
  if (props.disabled) return;
  const next = new Set(props.modelValue);
  const truthy = checked === true || checked === "true" || checked === 1;
  if (truthy) next.add(name);
  else next.delete(name);
  emit("update:modelValue", Array.from(next));
}

function toggleExpand(name: string) {
  const next = new Set(expanded.value);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  expanded.value = next;
}

function isExpanded(name: string): boolean {
  return expanded.value.has(name);
}

function hasSubsets(meta: DatasetMeta | undefined): boolean {
  return Boolean(meta?.subsets?.length);
}

function subsetTitle(meta: DatasetMeta): string {
  const total = meta.subsets?.length || 0;
  const configured = meta.configured_subset_list?.length || 0;
  if (!total && !configured) return "子集信息";
  if (configured) return "默认运行 " + configured + " / 本地 " + total + " 个";
  return "本地 " + total + " 个";
}

function toggleOverride(name: string, val: boolean | string | number) {
  if (props.disabled) return;
  const enabled = Boolean(val);
  emit("update:subsetOverride", { ...props.subsetOverride, [name]: enabled });
  if (enabled) {
    const meta = props.datasets[name];
    const init = meta?.configured_subset_list?.length
      ? [...meta.configured_subset_list]
      : [...(meta?.subsets || [])];
    emit("update:subsetModelValue", { ...props.subsetModelValue, [name]: init });
    const next = new Set(expanded.value);
    next.add(name);
    expanded.value = next;
  }
}

function updateChosenSubsets(name: string, vals: unknown) {
  const arr = Array.isArray(vals) ? vals.map((v) => String(v)) : [];
  emit("update:subsetModelValue", { ...props.subsetModelValue, [name]: arr });
}

function effectiveSubsetsList(name: string): string[] {
  const meta = props.datasets[name];
  const picked = props.subsetModelValue[name];
  if (props.subsetOverride[name] && picked && picked.length) return picked;
  if (meta?.configured_subset_list?.length) return meta.configured_subset_list;
  return meta?.subsets || [];
}
</script>

<template>
  <div class="dataset-picker">
    <div class="dataset-picker__filter">
      <div class="dataset-picker__tabs" role="group" aria-label="数据集筛选"><button v-for="filter in filters" :key="filter.value" type="button" :aria-pressed="filterMode === filter.value" @click="filterMode = filter.value">{{ filter.label }}</button></div>
      <small class="muted">已选 {{ modelValue.length }} / 共 {{ datasetEntries.length }} 个本地数据集</small>
    </div>

    <el-alert
      v-if="!datasetEntries.length"
      type="warning"
      :closable="false"
      title="未发现本地可用数据集。请先由管理员在 data/evalscope_datasets 下提供数据集目录。"
    />

    <ul v-else v-loading="loading" class="dataset-picker__list">
      <li v-if="!visibleEntries.length" class="dataset-picker__empty muted">没有匹配的数据集</li>
      <li
        v-for="([name, meta]) in visibleEntries"
        :key="name"
        class="dataset-picker__row"
        :class="{ 'dataset-picker__row--active': isChecked(name) }"
      >
        <div class="row-head">
          <el-checkbox
            :model-value="isChecked(name)"
            :disabled="disabled"
            @change="(v: any) => togglePick(name, v)"
            @click.stop
          >
            <span class="row-name">{{ meta.pretty_name || name }}</span>
          </el-checkbox>

          <button v-if="hasSubsets(meta)" type="button" class="row-toggle" :aria-label="`展开 ${meta.pretty_name || name} 子集`" :aria-expanded="isExpanded(name)" :aria-controls="`${pickerId}-${name}`" @click="toggleExpand(name)"><span>子集</span><el-icon class="row-chevron" :class="{ expanded: isExpanded(name) }"><ArrowDown /></el-icon></button>
        </div>
        <div class="row-tags">
          <el-tag v-if="defaultDatasets.includes(name)" size="small" type="success" effect="plain">推荐</el-tag>
          <el-tag v-if="meta.available_local" size="small" type="info" effect="plain">本地</el-tag>
          <el-tag v-if="meta.needs_judge" size="small" type="warning" effect="plain">需 Judge</el-tag>
          <el-tag v-if="meta.categories?.includes('Coding')" size="small" type="warning" effect="plain">需 Sandbox</el-tag>
          <el-tag v-for="c in meta.categories || []" :key="c" size="small" effect="plain">{{ c }}</el-tag>
        </div>

        <p class="row-desc">{{ meta.description || '暂无描述' }}</p>
        <small v-if="meta.local_path" class="row-path" :title="meta.local_path">{{ meta.local_path }}</small>

        <div v-if="hasSubsets(meta)" v-show="isExpanded(name)" :id="`${pickerId}-${name}`" class="row-subsets">
          <div class="subset-head">
            <div class="subset-meta">
              <span class="subset-title">{{ subsetTitle(meta) }}</span>
              <div v-if="meta.configured_subset_list?.length && !subsetOverride[name]" class="subset-tags">
                <el-tag
                  v-for="s in effectiveSubsetsList(name)"
                  :key="'cfg-' + name + '-' + s"
                  size="small"
                  type="primary"
                  effect="plain"
                >{{ s }}</el-tag>
              </div>
            </div>
            <el-switch
              :model-value="!!subsetOverride[name]"
              :disabled="disabled"
              active-text="自定义子集"
              inactive-text="使用默认"
              size="small"
              @update:modelValue="(v: any) => toggleOverride(name, v)"
            />
          </div>

          <div v-if="subsetOverride[name]" class="subset-list">
            <el-checkbox-group
              :model-value="(subsetModelValue[name] || []) as string[]"
              :disabled="disabled"
              @update:modelValue="(v) => updateChosenSubsets(name, v)"
            >
              <el-checkbox
                v-for="s in meta.subsets"
                :key="name + '-' + s"
                :value="s"
                :label="s"
                size="small"
              />
            </el-checkbox-group>
            <p v-if="!(subsetModelValue[name] || []).length" class="muted">未选择任何子集；将回退到默认配置。</p>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.dataset-picker {
  display: grid;
  gap: 8px;
}

.dataset-picker__filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.dataset-picker__tabs { display: flex; flex-wrap: wrap; gap: 5px; }
.dataset-picker__tabs button { padding: 6px 9px; border: 1px solid var(--lb-border); border-radius: 6px; background: var(--lb-surface); color: var(--lb-fg-soft); font: 11px var(--font-body); cursor: pointer; transition: background-color 150ms ease, color 150ms ease; }
.dataset-picker__tabs button:hover, .dataset-picker__tabs button[aria-pressed="true"] { color: var(--lb-primary); border-color: var(--lb-accent-soft-2); background: var(--lb-accent-soft); }

.dataset-picker__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
  max-height: 520px;
  overflow-y: auto;
  padding-right: 4px;
}

.dataset-picker__row {
  border: 1px solid var(--lb-border);
  border-radius: 10px;
  padding: 14px;
  background: var(--lb-surface);
  transition: border-color 0.15s ease, background 0.15s ease;
}

.dataset-picker__row--active {
  border-color: var(--lb-primary);
  background: var(--lb-surface-soft);
}

.dataset-picker__empty {
  padding: 24px;
  text-align: center;
  list-style: none;
}

.row-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.row-head :deep(.el-checkbox) {
  flex: 1;
  min-width: 0;
  margin-right: 4px;
}
.row-head :deep(.el-checkbox__label) { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.row-toggle { display: flex; align-items: center; flex-shrink: 0; gap: 7px; padding: 5px 0 5px 8px; border: 0; color: var(--lb-muted); background: transparent; font: 11px var(--font-body); cursor: pointer; }

.row-name {
  font-weight: 650;
  color: var(--lb-fg-strong);
  margin-left: 2px;
}

.row-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  flex: 1 1 auto;
  min-width: 0;
  margin-top: 6px;
}

.row-chevron {
  transition: transform 0.15s ease;
  color: var(--lb-muted);
  flex: 0 0 auto;
}

.row-chevron.expanded {
  transform: rotate(180deg);
}

.row-desc {
  margin: 6px 0 2px;
  color: var(--lb-fg-soft);
  font-size: 12px;
  line-height: 1.5;
}

.row-path {
  display: block;
  color: var(--lb-muted);
  font-size: 10px;
  line-height: 1.45;
  word-break: break-all;
  margin-top: 2px;
}

.row-subsets {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--lb-border);
  display: grid;
  gap: 8px;
}

.subset-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.subset-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.subset-title {
  color: var(--lb-fg-soft);
  font-size: 12px;
}

.subset-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.subset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}

@media (max-width: 760px) {
  .dataset-picker__list {
    max-height: none;
  }
}
</style>
