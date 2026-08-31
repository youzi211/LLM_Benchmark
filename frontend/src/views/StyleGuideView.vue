<script setup lang="ts">
/**
 * 设计系统展示页 (Phase 1.2)
 * 目的: 集中可视化所有 --lb-* token, 让任何贡献者能一眼看到当前设计语言.
 * 路由: /style-guide (不进入主导航, 由开发者手动访问)
 */
import { computed } from "vue";

const colors = [
  { name: "Primary", varName: "--lb-primary", text: "#1E40AF" },
  { name: "Secondary", varName: "--lb-secondary", text: "#3B82F6" },
  { name: "CTA", varName: "--lb-cta", text: "#F59E0B" },
  { name: "Background", varName: "--lb-bg", text: "#F8FAFC" },
  { name: "Surface", varName: "--lb-surface", text: "#FFFFFF" },
  { name: "Foreground", varName: "--lb-fg", text: "#1E3A8A" },
  { name: "FG Soft", varName: "--lb-fg-soft", text: "#475569" },
  { name: "Muted", varName: "--lb-muted", text: "#64748B" },
  { name: "Success", varName: "--lb-success", text: "#16A34A" },
  { name: "Warning", varName: "--lb-warning", text: "#D97706" },
  { name: "Danger", varName: "--lb-danger", text: "#DC2626" },
  { name: "Info", varName: "--lb-info", text: "#3B82F6" },
];

const radii = [
  { name: "SM", value: "8px", class: "lb-radius-sm" },
  { name: "MD (default)", value: "12px", class: "lb-radius" },
  { name: "LG", value: "16px", class: "lb-radius-lg" },
];

const shadows = [
  { name: "Subtle", class: "lb-shadow-sm" },
  { name: "Default", class: "lb-shadow" },
  { name: "Elevated", class: "lb-shadow-lg" },
];

const statusSamples = [
  { name: "success", label: "通过", text: "12 个指标全部通过" },
  { name: "running", label: "运行中", text: "正在执行第 7 / 12 个指标" },
  { name: "pending", label: "排队中", text: "等待空闲 worker" },
  { name: "failed", label: "失败", text: "context_length 超出 4096" },
  { name: "info", label: "信息", text: "结果待人工核对" },
];

const statusTypeMap: Record<string, string> = {
  success: "success",
  running: "warning",
  pending: "info",
  failed: "danger",
  info: "info",
};

const fontHeading = "Fira Code";
const fontBody = "Fira Sans";

const sectionTitle = (s: string) => s;

const tokenDoc = [
  { name: "--lb-primary", desc: "品牌主色; 用于导航激活态、关键 CTA、强调数字" },
  { name: "--lb-secondary", desc: "次级强调; 链接、辅助按钮、图标" },
  { name: "--lb-cta", desc: "行动号召; '新建评测' 等关键操作" },
  { name: "--lb-bg", desc: "全局背景; 浅蓝渐变基础" },
  { name: "--lb-surface", desc: "卡片表面; 白色" },
  { name: "--lb-fg", desc: "主文本色; 深蓝" },
  { name: "--lb-muted", desc: "弱化文本; 提示、占位" },
  { name: "--lb-success / warning / danger", desc: "状态语义色; 任务状态、错误、警告" },
];

const componentSamples = [
  { name: "Primary Button", element: "el-button", type: "primary", label: "新建评测" },
  { name: "Success Button", element: "el-button", type: "success", label: "确认通过" },
  { name: "Warning Button", element: "el-button", type: "warning", label: "重新运行" },
  { name: "Danger Button", element: "el-button", type: "danger", label: "取消评测" },
  { name: "Plain Button", element: "el-button", type: "primary", plain: true, label: "查看报告" },
];
</script>

<template>
  <div class="lb-style-guide">
    <header class="lb-sg-hero">
      <p class="eyebrow">DESIGN SYSTEM</p>
      <h1>LLM Benchmark · 设计令牌</h1>
      <p class="lb-sg-lead">
        基于 ui-ux-pro-max Data-Dense Dashboard 风格构建。本页是设计语言的真实样本，任何修改请同时更新
        <code>design-system/llm-benchmark/MASTER.md</code>。
      </p>
    </header>

    <!-- 1. 颜色 -->
    <section class="lb-sg-section">
      <h2>1. 色彩</h2>
      <p class="lb-sg-hint">所有色值同时支持亮色 / 暗色主题，切换顶栏的太阳/月亮按钮即可验证。</p>
      <div class="lb-sg-color-grid">
        <div v-for="c in colors" :key="c.varName" class="lb-sg-swatch" :style="{ background: `var(${c.varName})` }">
          <div class="lb-sg-swatch-meta">
            <div class="lb-sg-swatch-name">{{ c.name }}</div>
            <div class="lb-sg-swatch-var">{{ c.varName }}</div>
            <div class="lb-sg-swatch-hex">{{ c.text }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 2. 字体 -->
    <section class="lb-sg-section">
      <h2>2. 字体</h2>
      <div class="lb-sg-font-grid">
        <div class="lb-sg-font-card">
          <div class="lb-sg-font-meta">{{ fontHeading }} · heading & number</div>
          <div class="lb-sg-font-sample" :style="{ fontFamily: `'${fontHeading}', monospace` }">
            LLM Benchmark 评测趋势
            <div class="lb-sg-font-numbers">94.7% · 342ms · 156 req/s</div>
          </div>
        </div>
        <div class="lb-sg-font-card">
          <div class="lb-sg-font-meta">{{ fontBody }} · body</div>
          <div class="lb-sg-font-sample" :style="{ fontFamily: `'${fontBody}', sans-serif` }">
            验证服务连通、协议兼容、usage、错误结构、上下文与缓存等基础能力。
          </div>
        </div>
      </div>
    </section>

    <!-- 3. 圆角 / 阴影 -->
    <section class="lb-sg-section">
      <h2>3. 圆角 & 阴影</h2>
      <div class="lb-sg-shape-row">
        <div v-for="r in radii" :key="r.name" class="lb-sg-shape-item">
          <div :class="['lb-sg-shape', r.class, 'lb-shadow']"></div>
          <div class="lb-sg-shape-meta">
            <div>{{ r.name }}</div>
            <div class="lb-sg-muted">{{ r.value }}</div>
          </div>
        </div>
        <div v-for="s in shadows" :key="s.name" class="lb-sg-shape-item">
          <div :class="['lb-sg-shape', 'lb-radius', s.class]"></div>
          <div class="lb-sg-shape-meta">
            <div>{{ s.name }}</div>
            <div class="lb-sg-muted">{{ s.class }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 4. 按钮 -->
    <section class="lb-sg-section">
      <h2>4. 按钮</h2>
      <div class="lb-sg-button-row">
        <component
          v-for="(btn, idx) in componentSamples"
          :is="btn.element"
          :key="idx"
          :type="btn.type"
          :plain="btn.plain"
        >{{ btn.label }}</component>
      </div>
    </section>

    <!-- 5. 状态 -->
    <section class="lb-sg-section">
      <h2>5. 状态语义</h2>
      <div class="lb-sg-status-row">
        <div v-for="s in statusSamples" :key="s.name" class="lb-sg-status-item">
          <el-tag :type="statusTypeMap[s.name] as any" effect="light" round>{{ s.label }}</el-tag>
          <div class="lb-sg-status-text">{{ s.text }}</div>
        </div>
      </div>
    </section>

    <!-- 6. Token 速查 -->
    <section class="lb-sg-section">
      <h2>6. Token 速查</h2>
      <el-table :data="tokenDoc" stripe>
        <el-table-column prop="name" label="变量" width="240" />
        <el-table-column prop="desc" label="用途" />
      </el-table>
    </section>

    <!-- 7. 反模式 -->
    <section class="lb-sg-section">
      <h2>7. 反模式 (禁止)</h2>
      <ul class="lb-sg-do-dont">
        <li><span class="lb-sg-dont">✗</span> 使用 Element Plus 默认空状态插画</li>
        <li><span class="lb-sg-do">✓</span> 改为自绘品牌空状态 (Phase 3.2 引入 <code>EmptyState.vue</code>)</li>
        <li><span class="lb-sg-dont">✗</span> 错误条横在每个 tab 顶部</li>
        <li><span class="lb-sg-do">✓</span> 改为右上角 toast + 边角连接状态灯 (Phase 1.3)</li>
        <li><span class="lb-sg-dont">✗</span> 卡片全用相同 <code>panel-card</code></li>
        <li><span class="lb-sg-do">✓</span> 区分 primary / secondary / tertiary 卡片变体</li>
        <li><span class="lb-sg-dont">✗</span> 单行长表单 + 单按钮</li>
        <li><span class="lb-sg-do">✓</span> 字段分组 + 步骤式向导 (Phase 3.4)</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.lb-style-guide {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 20px 64px;
}

.lb-sg-hero {
  padding: 28px 28px 24px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius-lg);
  background: linear-gradient(135deg, #ffffff 0%, #f8fbff 55%, #edf5ff 100%);
  box-shadow: var(--lb-shadow);
  margin-bottom: 28px;
}

:root[data-theme="dark"] .lb-sg-hero {
  background: linear-gradient(135deg, #0f1729 0%, #111a2e 55%, #0a1424 100%);
}

.lb-sg-hero .eyebrow {
  margin: 0 0 6px;
  color: var(--lb-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.lb-sg-hero h1 {
  margin: 0 0 8px;
  font-family: "Fira Code", monospace;
  font-size: 28px;
  line-height: 1.2;
  color: var(--lb-fg-strong);
}

.lb-sg-lead {
  margin: 0;
  color: var(--lb-muted);
  line-height: 1.6;
  font-size: 14px;
}

.lb-sg-lead code {
  background: var(--lb-accent-soft);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 13px;
}

.lb-sg-section {
  margin-bottom: 32px;
  padding: 20px;
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  background: var(--lb-surface);
  box-shadow: var(--lb-shadow);
}

.lb-sg-section h2 {
  margin: 0 0 4px;
  font-family: "Fira Code", monospace;
  font-size: 18px;
  color: var(--lb-fg-strong);
}

.lb-sg-hint {
  margin: 0 0 16px;
  color: var(--lb-muted);
  font-size: 13px;
  line-height: 1.6;
}

.lb-sg-color-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.lb-sg-swatch {
  min-height: 110px;
  border-radius: var(--lb-radius);
  border: 1px solid var(--lb-border-soft);
  padding: 12px;
  display: flex;
  align-items: flex-end;
}

.lb-sg-swatch-meta {
  width: 100%;
  background: rgba(255, 255, 255, 0.92);
  padding: 8px 10px;
  border-radius: 6px;
  color: #0f172a;
}

.lb-sg-swatch-name {
  font-weight: 600;
  font-size: 13px;
}

.lb-sg-swatch-var {
  font-family: "Fira Code", monospace;
  font-size: 11px;
  color: #475569;
  margin-top: 2px;
}

.lb-sg-swatch-hex {
  font-family: "Fira Code", monospace;
  font-size: 11px;
  color: #64748b;
}

.lb-sg-font-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.lb-sg-font-card {
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  padding: 16px;
  background: var(--lb-surface-soft);
}

.lb-sg-font-meta {
  font-family: "Fira Code", monospace;
  font-size: 12px;
  color: var(--lb-muted);
  margin-bottom: 8px;
}

.lb-sg-font-sample {
  font-size: 16px;
  line-height: 1.5;
  color: var(--lb-fg);
}

.lb-sg-font-numbers {
  margin-top: 8px;
  font-weight: 600;
  font-size: 20px;
  color: var(--lb-primary);
}

.lb-sg-shape-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}

.lb-sg-shape-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.lb-sg-shape {
  width: 96px;
  height: 64px;
  background: var(--lb-surface);
  border: 1px solid var(--lb-border);
}

.lb-sg-shape-meta {
  font-size: 12px;
  text-align: center;
  color: var(--lb-fg-soft);
}

.lb-sg-muted {
  color: var(--lb-muted);
  font-family: "Fira Code", monospace;
  font-size: 11px;
}

.lb-sg-button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.lb-sg-status-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.lb-sg-status-item {
  border: 1px solid var(--lb-border);
  border-radius: var(--lb-radius);
  padding: 12px;
  background: var(--lb-surface-soft);
}

.lb-sg-status-text {
  margin-top: 8px;
  font-size: 13px;
  color: var(--lb-fg-soft);
  line-height: 1.5;
}

.lb-sg-do-dont {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 6px;
}

.lb-sg-do-dont li {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--lb-surface-soft);
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--lb-fg-soft);
}

.lb-sg-do-dont code {
  font-family: "Fira Code", monospace;
  font-size: 12px;
  background: var(--lb-accent-soft);
  padding: 1px 6px;
  border-radius: 4px;
}

.lb-sg-do {
  color: var(--lb-success);
  font-weight: 700;
}

.lb-sg-dont {
  color: var(--lb-danger);
  font-weight: 700;
}
</style>
