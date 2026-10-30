<script setup lang="ts">
/**
 * 移动端底部 Tab (Phase 4.4)
 * < 760px 出现, 替代/补充主 tabs, 方便单手操作.
 */
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Odometer, Tickets, VideoPlay, Calendar, MoreFilled } from "@element-plus/icons-vue";

const route = useRoute();
const router = useRouter();

interface Tab { name: string; label: string; path: string; icon: unknown; }

const tabs: Tab[] = [
  { name: "overview",     label: "概览", path: "/overview",     icon: Odometer },
  { name: "tasks",        label: "任务", path: "/tasks",        icon: Tickets },
  { name: "suites", label: "新建", path: "/suites", icon: VideoPlay },
  { name: "schedules", label: "定时", path: "/schedules", icon: Calendar },
];

const currentPath = computed(() => route.path);

function go(t: Tab) {
  router.push(t.path);
}
</script>

<template>
  <nav class="lb-mobile-nav" aria-label="主导航">
    <button
      v-for="t in tabs"
      :key="t.name"
      type="button"
      :class="['lb-mobile-nav__item', { 'lb-mobile-nav__item--active': currentPath === t.path }]"
      @click="go(t)"
      :aria-label="t.label"
      :aria-current="currentPath === t.path ? 'page' : undefined"
    >
      <el-icon class="lb-mobile-nav__icon"><component :is="t.icon" /></el-icon>
      <span>{{ t.label }}</span>
    </button>
    <el-dropdown trigger="click" @command="(path: string) => router.push(path)">
      <button type="button" class="lb-mobile-nav__item" aria-label="更多评测入口">
        <el-icon class="lb-mobile-nav__icon"><MoreFilled /></el-icon><span>更多</span>
      </button>
      <template #dropdown><el-dropdown-menu>
        <el-dropdown-item command="/basic">基础评测</el-dropdown-item>
        <el-dropdown-item command="/stress">压测评测</el-dropdown-item>
        <el-dropdown-item command="/intelligence">能力评测</el-dropdown-item>
      </el-dropdown-menu></template>
    </el-dropdown>
  </nav>
</template>
