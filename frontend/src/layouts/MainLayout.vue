<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowDown, Moon, Sunny } from "@element-plus/icons-vue";
import { useTheme } from "@/composables/useTheme";
import { useModelsStore } from "@/stores/models";
import { getHealth, type HealthStatus } from "@/api/evaluations";
import ModelCreateDrawer from "@/components/models/ModelCreateDrawer.vue";
import StatusDot from "@/components/common/StatusDot.vue";
import ConnectionBanner from "@/components/common/ConnectionBanner.vue";
import ShortcutHelp from "@/components/layouts/ShortcutHelp.vue";
import MobileTabs from "@/components/layouts/MobileTabs.vue";
import { useToast } from "@/composables/useToast";
import { useShortcuts } from "@/composables/useShortcuts";
import EvalScopeConfigDrawer from "@/components/evalscope/EvalScopeConfigDrawer.vue";

const store = useModelsStore();
const router = useRouter();
const route = useRoute();
const modelDrawerVisible = ref(false);
const evalscopeDrawerVisible = ref(false);

const runningCounts = ref({ basic: 0, intelligence: 0, stress: 0 });
const runningTotal = computed(() => runningCounts.value.basic + runningCounts.value.intelligence + runningCounts.value.stress);
const { mode: themeMode, resolved: themeResolved, toggle: toggleTheme } = useTheme();
useShortcuts();
const toast = useToast();
const connDismissed = ref(false);
const health = ref<HealthStatus | null>(null);
let healthTimer: number | undefined;

async function refreshHealth() {
  try {
    health.value = await getHealth();
  } catch {
    // 后端不可达 - 静默, 让 connServices 反映出来
    health.value = null;
  }
}

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
    { key: "scheduler", name: "调度", state: h.scheduler.ok ? ("ok" as const) : ("warn" as const), detail: h.scheduler.state === "running" ? "APScheduler" : "已禁用" },
  ];
});
const themeIcon = computed(() => (themeResolved.value === "dark" ? "moon" : "sunny"));
const themeLabel = computed(() => {
  if (themeMode.value === "auto") return "跟随系统";
  return themeResolved.value === "dark" ? "暗色" : "亮色";
});
let runningTimer: number | undefined;

function isFinal(status: unknown): boolean {
  return ["completed", "partial", "failed", "interrupted", "error"].includes(String(status || ""));
}

async function refreshRunning() {
  try {
    const origin = window.location.origin;
    const fetcher = (url: string) => fetch(url).then((r) => r.ok ? r.json() : []).catch(() => []);
    const [basicRes, intelRes, stressRes] = await Promise.allSettled([
      fetcher(origin + "/api/tasks?limit=100"),
      fetcher(origin + "/api/intelligence/tasks?limit=100"),
      fetcher(origin + "/api/stress/tasks?limit=100"),
    ]);
    const safeArray = (v: PromiseSettledResult<unknown>): Array<Record<string, unknown>> => v.status === "fulfilled" && Array.isArray(v.value) ? v.value as Array<Record<string, unknown>> : [];
    runningCounts.value = {
      basic: safeArray(basicRes).filter((t: Record<string, unknown>) => !isFinal(t.status)).length,
      intelligence: safeArray(intelRes).filter((t: Record<string, unknown>) => !isFinal(t.status)).length,
      stress: safeArray(stressRes).filter((t: Record<string, unknown>) => !isFinal(t.status)).length,
    };
  } catch {
    // 静默失败；徽标继续显示上一次的状态即可。
  }
}

function startRunningPoll() {
  stopRunningPoll();
  if (healthTimer !== undefined) window.clearInterval(healthTimer);
  refreshRunning();
  runningTimer = window.setInterval(refreshRunning, 5000);
}

function stopRunningPoll() {
  if (runningTimer !== undefined) {
    window.clearInterval(runningTimer);
    runningTimer = undefined;
  }
}

onMounted(() => {
  store.load().catch(() => {
    // 静默失败,顶部选择区会显示错误提示;不阻塞骨架运行。
  });
  startRunningPoll();
  refreshHealth();
  healthTimer = window.setInterval(refreshHealth, 10000);
});

onUnmounted(() => {
  stopRunningPoll();
});

const mainTabs = [
  { name: "overview", label: "概览", path: "/overview" },
  { name: "basic", label: "基础评测", path: "/basic" },
  { name: "stress", label: "压测评测", path: "/stress" },
  { name: "intelligence", label: "能力评测", path: "/intelligence" },
];

const auxiliary = [
  { label: "一键完整评测", path: "/suites" },
  { label: "定时任务", path: "/schedules" },
  ...(import.meta.env.DEV ? [{ label: "设计系统", path: "/style-guide" }] : []),
];

const currentTab = computed(() => String(route.meta.tab ?? ""));

function onSelectModel(id: string) {
  store.select(id);
}

function selectMainTab(tabName: string | number | boolean | undefined) {
  const target = mainTabs.find((t) => t.name === String(tabName));
  if (target) router.push(target.path);
}

function onModelCreated(id: string) {
  store.select(id);
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
</script>

<template>
  <div class="lb-shell">
    <header class="lb-topbar">
      <div class="lb-topbar-inner">
        <div class="lb-brand">
          <h1>LLM Benchmark 控制台</h1>
          <p class="lb-subtitle">
            三线评测 · 基础 / 压测 / 能力，辅助入口保留一键评测与定时任务
          </p>
        </div>

        <div class="lb-model-control">
          <el-select
            :model-value="store.currentId ?? ''"
            placeholder="选择当前模型"
            :loading="store.loading"
            style="min-width: 240px"
            @change="onSelectModel"
          >
            <el-option
              v-for="m in store.models"
              :key="m.id"
              :label="m.name ?? m.model ?? m.id"
              :value="m.id"
            />
          </el-select>
          <StatusDot :state="store.error ? 'fail' : 'ok'" :label="store.error ? 'API 异常' : 'API 正常'" :size="7" />
        <div class="lb-running-pill" :class="{'lb-running-pill--on': runningTotal > 0}" :title="`基础 ${runningCounts.basic} · 能力 ${runningCounts.intelligence} · 压测 ${runningCounts.stress}`">
          <span class="lb-running-pill__dot"></span>
          <span>运行中 {{ runningTotal }}</span>
        </div>
        <el-button size="small" @click="store.load(true)">刷新模型</el-button>
          <el-button size="small" type="primary" plain @click="modelDrawerVisible = true">添加模型</el-button>
          <el-button size="small" type="warning" plain @click="evalscopeDrawerVisible = true">评测环境</el-button>
          <el-tooltip :content="`当前主题: ${themeLabel} (点击切换)`" placement="bottom">
            <ShortcutHelp />
            <el-button size="small" circle :icon="themeIcon === 'moon' ? Moon : Sunny" @click="toggleTheme" :aria-label="`切换主题: ${themeLabel}`" class="lb-theme-toggle" />
          </el-tooltip>
        </div>
      </div>

      <ConnectionBanner
        v-if="!connDismissed"
        :services="connServices"
        :last-error="store.error"
        @retry="retryConn"
        @dismiss="dismissConn"
      />
    </header>

    <nav class="lb-tabs">
      <div class="lb-tabs-inner">
        <el-radio-group class="lb-main-tabs" :model-value="currentTab" size="large" @change="selectMainTab">
          <el-radio-button v-for="t in mainTabs" :key="t.name" :value="t.name">
            {{ t.label }}
          </el-radio-button>
        </el-radio-group>

        <el-dropdown>
          <el-button size="large">
            辅助入口
            <el-icon class="lb-dropdown-icon"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="a in auxiliary"
                :key="a.path"
                @click="router.push(a.path)"
              >
                {{ a.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </nav>

    <main class="lb-main">
      <router-view />
    </main>
    <MobileTabs />

    <footer class="lb-footer">
      <small>Vue 3 · Vite · Element Plus · ECharts — 并行验证中，旧控制台仍挂在 /ui/</small>
    </footer>

    <ModelCreateDrawer v-model="modelDrawerVisible" @created="onModelCreated" />
    <EvalScopeConfigDrawer v-model="evalscopeDrawerVisible" />
  </div>
</template>

<style scoped>
.lb-topbar {
  background: #ffffff;
  border-bottom: 1px solid var(--lb-border);
}

.lb-topbar-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px 20px 8px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.lb-brand h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.lb-subtitle {
  margin: 4px 0 0;
  color: var(--lb-muted);
  font-size: 12px;
}

.lb-model-control {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.lb-error {
  background: #fef2f2;
  color: #b91c1c;
  padding: 6px 20px;
  font-size: 12px;
}

.lb-tabs {
  background: #fff;
  border-bottom: 1px solid var(--lb-border);
}

.lb-tabs-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 8px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.lb-main-tabs {
  flex: 1 1 auto;
}

.lb-dropdown-icon {
  margin-left: 4px;
}

.lb-footer {
  text-align: center;
  color: var(--lb-muted);
  padding: 12px 16px 20px;
  font-size: 12px;
}

@media (max-width: 760px) {
  .lb-topbar-inner,
  .lb-tabs-inner {
    padding-left: 12px;
    padding-right: 12px;
  }

  .lb-brand h1 {
    font-size: 16px;
  }

  .lb-model-control {
    width: 100%;
    justify-content: stretch;
  }

  .lb-model-control :deep(.el-select) {
    flex: 1 1 220px;
  }

  .lb-running-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(107, 114, 128, 0.10);
    border: 1px solid rgba(107, 114, 128, 0.22);
    color: var(--lb-muted);
    font-size: 12px;
    cursor: default;
    user-select: none;
  }

  .lb-running-pill--on {
    background: rgba(22, 163, 74, 0.10);
    border-color: rgba(22, 163, 74, 0.32);
    color: #166534;
  }

  .lb-running-pill__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(107, 114, 128, 0.6);
  }

  .lb-running-pill--on .lb-running-pill__dot {
    background: var(--lb-success);
    box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.18);
  }
}
</style>
