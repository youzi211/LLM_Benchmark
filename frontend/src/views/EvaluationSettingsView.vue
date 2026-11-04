<script setup lang="ts">
import { ref } from "vue";
import EvalScopeConfigDrawer from "@/components/evalscope/EvalScopeConfigDrawer.vue";
const open = ref(false);
</script>
<template>
  <section class="mw-page"><header class="mw-title"><div><p class="mw-eyebrow">EVALUATION / ENVIRONMENT</p><h1>评测环境</h1><p>配置 Judge LLM、代码执行沙箱及评测运行环境。</p></div></header>
    <div class="mw-settings-grid"><article class="mw-panel"><h2>Judge LLM</h2><p>通过持久化模型 ID 选择评分模型，保留默认分析模型回退策略。</p><el-button type="primary" @click="open = true">配置 Judge LLM</el-button></article><article class="mw-panel"><h2>执行沙箱</h2><p>管理沙箱启用状态、引擎、连接配置和执行健康检查。</p><el-button @click="open = true">配置沙箱 / 健康检查</el-button></article></div>
    <EvalScopeConfigDrawer v-if="open" v-model="open" />
  </section>
</template>
