<script setup lang="ts">
import { Cpu } from "@element-plus/icons-vue";
import "@/styles/evaluation.css";

withDefaults(defineProps<{
  lane: string;
  taskCount: number;
  countUnit?: string;
  listTitle?: string;
  detailTitle?: string;
  detailDescription?: string;
  autoUpdating?: boolean;
  configurationVisible: boolean;
  configurationTitle: string;
  configurationDescription: string;
  modelName: string;
  drawerSize?: string;
}>(), {
  countUnit: "条任务",
  listTitle: "最近任务",
  detailTitle: "任务详情",
  detailDescription: "选择一条任务，查看评测结果与运行信息",
  autoUpdating: false,
  drawerSize: "min(640px, 100vw)",
});

const emit = defineEmits<{ "update:configurationVisible": [value: boolean] }>();
</script>

<template>
  <div class="lb-evaluation" :data-lane="lane">
    <div class="lb-eval__grid">
      <section class="lb-eval-panel lb-eval-list" :aria-labelledby="`${lane}-list-title`">
        <header class="lb-eval-panel__head">
          <div class="lb-eval-panel__heading"><h2 :id="`${lane}-list-title`">{{ listTitle }}</h2><span class="lb-eval-count">{{ taskCount }} {{ countUnit }}</span></div>
          <span v-if="autoUpdating" class="lb-eval-live"><span></span>自动更新</span>
        </header>
        <div class="lb-eval-panel__body"><slot name="list" /></div>
        <footer class="lb-eval-list__foot"><slot name="list-footer">最近任务记录 · 点击查看详情，多选可重跑或对比</slot></footer>
      </section>

      <section class="lb-eval-panel lb-eval-detail" :aria-labelledby="`${lane}-detail-title`">
        <header class="lb-eval-panel__head">
          <div><h2 :id="`${lane}-detail-title`">{{ detailTitle }}</h2><p>{{ detailDescription }}</p></div>
          <div class="lb-eval-panel__actions"><slot name="detail-actions" /></div>
        </header>
        <div class="lb-eval-panel__body"><slot name="detail" /></div>
      </section>
    </div>

    <el-drawer
      :model-value="configurationVisible"
      :title="configurationTitle"
      :size="drawerSize"
      class="lb-eval-config"
      @update:model-value="emit('update:configurationVisible', $event)"
    >
      <p class="lb-eval-config__description">{{ configurationDescription }}</p>
      <div class="lb-eval-config__model">
        <span class="lb-eval-config__model-icon"><el-icon><Cpu /></el-icon></span>
        <div><span>当前模型</span><strong :title="modelName">{{ modelName }}</strong></div>
        <small>在顶部切换模型</small>
      </div>
      <slot name="configuration" />
      <template #footer><div class="lb-eval-config__footer"><slot name="configuration-footer" /></div></template>
    </el-drawer>
  </div>
</template>
