<script setup lang="ts">
import { useRoute } from "vue-router";
import { Brush, Calendar, Connection, Cpu, DataAnalysis, DataLine, Grid, Operation, Switch, Tickets } from "@element-plus/icons-vue";

const route = useRoute();
const emit = defineEmits<{ navigate: [] }>();
const development = import.meta.env.DEV;
const groups = [
  {
    label: "工作空间",
    items: [
      { label: "概览", path: "/overview", icon: Grid },
      { label: "任务中心", path: "/tasks", icon: Tickets },
      { label: "任务对比", path: "/compare", icon: Switch },
    ],
  },
  {
    label: "模型评测",
    items: [
      { label: "基础评测", path: "/basic", icon: Connection },
      { label: "压测评测", path: "/stress", icon: DataLine },
      { label: "能力评测", path: "/intelligence", icon: Cpu },
    ],
  },
  {
    label: "自动化",
    items: [
      { label: "一键完整评测", path: "/suites", icon: Operation },
      { label: "定时任务", path: "/schedules", icon: Calendar },
    ],
  },
];
</script>

<template>
  <div class="lb-workspace-sidebar">
    <router-link to="/overview" class="lb-workspace-brand" aria-label="LLM Benchmark 首页" @click="emit('navigate')">
      <span class="lb-workspace-brand__mark"><el-icon><DataAnalysis /></el-icon></span>
      <span class="lb-workspace-brand__copy">
        <strong>Benchmark<span>LLM</span></strong>
        <small>模型评测工作台</small>
      </span>
    </router-link>

    <nav class="lb-workspace-nav" aria-label="工作台导航">
      <div v-for="group in groups" :key="group.label" class="lb-workspace-nav__group">
        <p class="lb-workspace-nav__label">{{ group.label }}</p>
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="lb-workspace-nav__link"
          :class="{ 'is-active': route.path === item.path }"
          :aria-current="route.path === item.path ? 'page' : undefined"
          @click="emit('navigate')"
        >
          <el-icon aria-hidden="true"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </div>
    </nav>

    <div class="lb-workspace-sidebar__foot">
      <router-link v-if="development" to="/style-guide" class="lb-workspace-nav__link" @click="emit('navigate')">
        <el-icon aria-hidden="true"><Brush /></el-icon><span>设计系统</span>
      </router-link>
      <div class="lb-workspace-sidebar__note">
        <span>INTERNAL WORKSPACE</span>
        <p>评测事实 · 结果归档</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lb-workspace-sidebar { display: flex; flex-direction: column; height: 100%; padding: 26px 14px 18px; }
.lb-workspace-brand { display: flex; align-items: center; gap: 10px; padding: 0 10px 32px; color: var(--lb-fg-strong); text-decoration: none; }
.lb-workspace-brand__mark { display: grid; place-items: center; flex-shrink: 0; width: 34px; height: 36px; border-radius: 10px; background: var(--lb-primary); color: var(--lb-on-primary); font-size: 21px; }
.lb-workspace-brand__copy { display: flex; flex-direction: column; gap: 5px; }
.lb-workspace-brand__copy strong { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 700; letter-spacing: -0.5px; }
.lb-workspace-brand__copy strong span { color: var(--lb-muted); font-size: 9px; font-weight: 600; letter-spacing: 0.02em; }
.lb-workspace-brand__copy small { color: var(--lb-muted); font-size: 11px; }
.lb-workspace-nav { flex: 1; }
.lb-workspace-nav__group + .lb-workspace-nav__group { margin-top: 26px; }
.lb-workspace-nav__label { margin: 0 0 9px; padding-left: 12px; color: var(--lb-muted); font-size: 11px; font-weight: 500; }
.lb-workspace-nav__link { display: flex; align-items: center; gap: 11px; min-height: 41px; margin-top: 3px; padding: 10px 12px; border: 1px solid transparent; border-radius: 8px; color: var(--lb-fg-soft); text-decoration: none; font-size: 13px; line-height: 1.4; transition: background-color 150ms ease, color 150ms ease; }
.lb-workspace-nav__link .el-icon { flex-shrink: 0; font-size: 17px; }
.lb-workspace-nav__link:hover { background: var(--lb-surface-soft); color: var(--lb-fg-strong); }
.lb-workspace-nav__link.is-active { color: var(--lb-primary); background: var(--lb-accent-soft); font-weight: 600; }
.lb-workspace-sidebar__foot { margin-top: 32px; }
.lb-workspace-sidebar__note { margin: 14px 10px 0; padding-top: 18px; border-top: 1px solid var(--lb-border); color: var(--lb-muted); }
.lb-workspace-sidebar__note span { font-size: 9px; letter-spacing: 0.08em; }
.lb-workspace-sidebar__note p { margin: 6px 0 0; font-size: 11px; }
</style>
