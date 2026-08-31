<script setup lang="ts">
/**
 * 移动端底部 Tab (Phase 4.4)
 * < 760px 出现, 替代/补充主 tabs, 方便单手操作.
 */
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Odometer, Document, Lightning, Promotion } from "@element-plus/icons-vue";

const route = useRoute();
const router = useRouter();

interface Tab { name: string; label: string; path: string; icon: unknown; }

const tabs: Tab[] = [
  { name: "overview",     label: "概览", path: "/overview",     icon: Odometer },
  { name: "basic",        label: "基础", path: "/basic",        icon: Document },
  { name: "stress",       label: "压测", path: "/stress",       icon: Lightning },
  { name: "intelligence", label: "能力", path: "/intelligence", icon: Promotion },
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
    >
      <el-icon class="lb-mobile-nav__icon"><component :is="t.icon" /></el-icon>
      <span>{{ t.label }}</span>
    </button>
  </nav>
</template>
