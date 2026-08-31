<script setup lang="ts">
import MainLayout from "./layouts/MainLayout.vue";
import { initThemeEarly } from "@/composables/useTheme";

// 在 setup 同步阶段尽早设置 data-theme, 避免页面白底闪烁.
initThemeEarly();
</script>

<template>
  <MainLayout />
</template>
