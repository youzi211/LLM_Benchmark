<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Close, Edit, Menu, Moon, Plus, Refresh, Setting, Sunny } from "@element-plus/icons-vue";
import { useTheme } from "@/composables/useTheme";
import { useModelsStore } from "@/stores/models";
import { useHealthStore } from "@/stores/health";
import ConnectionBanner from "@/components/common/ConnectionBanner.vue";
import ShortcutHelp from "@/components/layouts/ShortcutHelp.vue";
import MobileTabs from "@/components/layouts/MobileTabs.vue";
import WorkspaceSidebar from "@/components/layouts/WorkspaceSidebar.vue";
import { useToast } from "@/composables/useToast";
import { useShortcuts } from "@/composables/useShortcuts";

const ModelCreateDrawer = defineAsyncComponent(() => import("@/components/models/ModelCreateDrawer.vue"));
const EvalScopeConfigDrawer = defineAsyncComponent(() => import("@/components/evalscope/EvalScopeConfigDrawer.vue"));
const store = useModelsStore();
const route = useRoute();
const modelDrawerVisible = ref(false);
const modelEditVisible = ref(false);
const evalscopeDrawerVisible = ref(false);
const navigationVisible = ref(false);

const healthStore = useHealthStore();
const health = computed(() => healthStore.status);
const { mode: themeMode, resolved: themeResolved, toggle: toggleTheme } = useTheme();
useShortcuts();
const toast = useToast();
const connDismissed = ref(false);

const connServices = computed(() => {
  const h = health.value;
  if (!h) {
    return [
      { key: "models", name: "模型", state: store.error ? ("fail" as const) : ("ok" as const), detail: store.error ?? undefined },
      { key: "evalscope", name: "EvalScope", state: "fail" as const, detail: "健康端点不可达" },
      { key: "scheduler", name: "调度", state: "fail" as const, detail: "健康端点不可达" },
    ];
  }
  return [
    { key: "models", name: "模型", state: (store.error || !h.models.ok) ? ("fail" as const) : ("ok" as const), detail: store.error ?? `已配置 ${h.models.count} 个` },
    { key: "evalscope", name: "EvalScope", state: h.evalscope.ok ? ("ok" as const) : ("warn" as const), detail: h.evalscope.state === "ready" ? "数据集目录就绪" : (h.evalscope.state || "未就绪") },
    { key: "scheduler", name: "调度", state: h.scheduler.ok ? ("ok" as const) : ("warn" as const), detail: h.scheduler.state === "running" ? "单机定时调度器" : "已禁用" },
  ];
});
const themeIcon = computed(() => (themeResolved.value === "dark" ? "moon" : "sunny"));
const themeLabel = computed(() => {
  if (themeMode.value === "auto") return "跟随系统";
  return themeResolved.value === "dark" ? "暗色" : "亮色";
});

function onSelectModel(id: string) {
  store.select(id);
}

function onModelCreated(id: string) {
  store.select(id);
}

const editingModel = computed(() => store.models.find((m) => m.id === store.currentId) ?? null);

function onModelUpdated(id: string) {
  store.select(id);
}

function onModelDeleted(id: string) {
  if (store.currentId === id) {
    const next = store.models.find((m) => m.id !== id);
    store.select(next?.id ?? "");
  }
}

function retryConn(key: string) {
  connDismissed.value = false;
  if (key === "models") {
    store.load(true).catch((err) => toast.error("重试失败: " + String(err?.message ?? err)));
    return;
  }
  toast.info(`已请求重试: ${key}`);
}

function dismissConn() {
  connDismissed.value = true;
  if (store.error) toast.warning(`隐藏了服务异常, 错误: ${store.error}`);
}

// 当 store.error 变化时, 自动显示顶部状态条
watch(() => store.error, (err, prev) => {
  if (err && err !== prev) {
    toast.error(`模型接口异常: ${err}`);
    connDismissed.value = false;
  }
});

watch(() => route.fullPath, () => { navigationVisible.value = false; });

onMounted(() => {
  store.load().catch(() => {
    // 静默失败,顶部选择区会显示错误提示;不阻塞骨架运行。
  });
  healthStore.start();
});

onUnmounted(() => {
  healthStore.stop();
});
</script>

<template>
  <div class="lb-shell lb-shell--workspace">
    <aside class="lb-desktop-sidebar"><WorkspaceSidebar /></aside>
    <div class="lb-workspace">
      <header class="lb-workspace-header">
        <div class="lb-header-leading">
          <el-button class="lb-menu-toggle" text :icon="Menu" aria-label="展开导航" @click="navigationVisible = true" />
          <div class="lb-breadcrumb" aria-label="当前位置">
            <span class="lb-breadcrumb__root">工作台</span><span class="lb-breadcrumb__separator">/</span>
            <span>{{ route.meta.title ?? '概览' }}</span>
          </div>
        </div>
        <div class="lb-workspace-toolbar">
          <div class="lb-model-picker">
            <span class="lb-model-picker__label">当前模型</span>
            <el-select
              :model-value="store.currentId ?? ''"
              placeholder="选择当前模型"
              :loading="store.loading"
              aria-label="当前模型"
              @change="onSelectModel"
            >
              <el-option v-for="m in store.models" :key="m.id" :label="m.name ?? m.model ?? m.id" :value="m.id" />
            </el-select>
            <el-tooltip content="刷新模型" placement="bottom">
              <el-button text circle :icon="Refresh" :loading="store.loading" aria-label="刷新模型" @click="store.load(true)" />
            </el-tooltip>
            <el-tooltip content="编辑模型" placement="bottom">
              <el-button text circle :icon="Edit" :disabled="!store.currentId" aria-label="编辑模型" @click="modelEditVisible = true" />
            </el-tooltip>
          </div>
          <span class="lb-toolbar-divider" aria-hidden="true"></span>
          <el-button class="lb-model-add" :icon="Plus" aria-label="添加模型" @click="modelDrawerVisible = true"><span class="lb-toolbar-label">添加模型</span></el-button>
          <el-button class="lb-env-button" :icon="Setting" aria-label="评测环境" @click="evalscopeDrawerVisible = true"><span class="lb-toolbar-label">评测环境</span></el-button>
          <div class="lb-toolbar-utilities">
            <ShortcutHelp />
            <el-tooltip :content="`当前主题: ${themeLabel} (点击切换)`" placement="bottom">
              <el-button text circle :icon="themeIcon === 'moon' ? Moon : Sunny" @click="toggleTheme" :aria-label="`切换主题: ${themeLabel}`" />
            </el-tooltip>
          </div>
        </div>
      </header>
      <ConnectionBanner
        v-if="!connDismissed"
        :services="connServices"
        :last-error="store.error"
        @retry="retryConn"
        @dismiss="dismissConn"
      />
      <main id="main-content" class="lb-main"><router-view /></main>
      <footer class="lb-workspace-footer">
        <span>LLM Benchmark</span><span>仅提供评测事实与报告，不自动判定上线</span>
      </footer>
    </div>
    <MobileTabs />
    <el-drawer v-model="navigationVisible" direction="ltr" size="248px" title="工作台导航" :with-header="false" class="lb-navigation-drawer">
      <el-button text circle class="lb-navigation-close" :icon="Close" aria-label="关闭导航" @click="navigationVisible = false" />
      <WorkspaceSidebar @navigate="navigationVisible = false" />
    </el-drawer>
    <ModelCreateDrawer v-if="modelDrawerVisible" v-model="modelDrawerVisible" @created="onModelCreated" />
    <ModelCreateDrawer v-if="modelEditVisible" v-model="modelEditVisible" :edit-target="editingModel" @updated="onModelUpdated" @deleted="onModelDeleted" />
    <EvalScopeConfigDrawer v-if="evalscopeDrawerVisible" v-model="evalscopeDrawerVisible" />
  </div>
</template>

<style scoped>
.lb-shell--workspace { display: grid; grid-template-columns: 224px minmax(0, 1fr); align-items: start; }
.lb-desktop-sidebar { position: sticky; top: 0; height: 100dvh; overflow-y: auto; background: var(--lb-surface); border-right: 1px solid var(--lb-border); }
.lb-workspace { display: flex; flex-direction: column; min-width: 0; min-height: 100vh; }
.lb-workspace-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 72px; padding: 16px 32px; background: var(--lb-surface); border-bottom: 1px solid var(--lb-border); }
.lb-header-leading, .lb-breadcrumb, .lb-workspace-toolbar, .lb-model-picker, .lb-toolbar-utilities { display: flex; align-items: center; }
.lb-header-leading { gap: 12px; flex-shrink: 0; }
.lb-breadcrumb { gap: 12px; color: var(--lb-fg-strong); font-size: 12px; white-space: nowrap; }
.lb-breadcrumb__root, .lb-breadcrumb__separator { color: var(--lb-muted); }
.lb-workspace-toolbar { gap: 10px; min-width: 0; }
.lb-workspace-toolbar :deep(.el-button + .el-button) { margin-left: 0; }
.lb-model-picker { min-width: 0; gap: 8px; }
.lb-model-picker__label { color: var(--lb-muted); font-size: 12px; white-space: nowrap; }
.lb-model-picker :deep(.el-select) { width: 210px; }
.lb-model-picker :deep(.el-select__wrapper) { box-shadow: none; background: var(--lb-surface-soft); }
.lb-model-picker :deep(.el-select__wrapper.is-focused) { box-shadow: 0 0 0 1px var(--lb-primary) inset; }
.lb-toolbar-divider { width: 1px; height: 20px; margin: 0 2px; background: var(--lb-border); }
.lb-model-add, .lb-env-button { padding: 8px 12px; font-size: 12px; }
.lb-toolbar-utilities { gap: 4px; }
.lb-menu-toggle { display: none; }
.lb-workspace-footer { display: flex; justify-content: space-between; gap: 12px; margin: auto 32px 0; padding: 18px 0 22px; color: var(--lb-muted); font-size: 11px; border-top: 1px solid var(--lb-border); }
.lb-navigation-close { position: absolute; top: 4px; right: 4px; z-index: 1; }
:global(.lb-navigation-drawer .el-drawer__body) { padding: 0; }
@media (max-width: 1279px) {
  .lb-model-picker__label, .lb-breadcrumb__root, .lb-breadcrumb__separator { display: none; }
  .lb-workspace-header { gap: 12px; padding: 16px 24px; }
}
@media (max-width: 1099px) {
  .lb-shell--workspace { grid-template-columns: minmax(0, 1fr); }
  .lb-desktop-sidebar { display: none; }
  .lb-menu-toggle { display: inline-flex; margin-left: -8px; }
}
@media (max-width: 900px) {
  .lb-toolbar-label { display: none; }
  .lb-model-add, .lb-env-button { width: 32px; padding: 8px; }
  .lb-model-add :deep(.el-icon + span), .lb-env-button :deep(.el-icon + span) { margin-left: 0; }
}
@media (max-width: 760px) {
  .lb-workspace-header { flex-wrap: wrap; min-height: 0; gap: 12px; padding: 12px 16px; }
  .lb-header-leading { flex: 1; }
  .lb-workspace-toolbar { display: contents; }
  .lb-model-picker { order: 2; flex: 1 0 100%; padding: 3px; border: 1px solid var(--lb-border); border-radius: 8px; }
  .lb-model-picker :deep(.el-select) { flex: 1; width: 0; }
  .lb-model-picker :deep(.el-select__wrapper) { background: transparent; }
  .lb-toolbar-divider { display: none; }
  .lb-workspace-footer { margin: auto 16px 76px; flex-direction: column; gap: 6px; }
}
</style>
