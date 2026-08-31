<script setup lang="ts">
/**
 * Markdown 报告内联预览 (Phase 4.3)
 * 极简自实现: 标题 / 段落 / 列表 / 表格 / 行内 code / 代码块 / 引用 / 分隔线.
 */
import { computed } from "vue";

interface Block { kind: "h"|"p"|"ul"|"ol"|"code"|"quote"|"table"|"hr"; level?: number; text?: string; items?: string[]; rows?: string[][]; lang?: string; }

const props = defineProps<{
  source?: string;
  loading?: boolean;
  maxHeight?: string;
}>();

const blocks = computed<Block[]>(() => {
  const src = props.source || "";
  if (!src.trim()) return [];
  const lines = src.split(/\r?\n/);
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const hMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (hMatch) { out.push({ kind: "h", level: hMatch[1].length, text: hMatch[2].trim() }); i++; continue; }
    if (/^---+\s*$/.test(line)) { out.push({ kind: "hr" }); i++; continue; }
    if (/^>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^>\s?/, "")); i++; }
      out.push({ kind: "quote", text: buf.join("\n") });
      continue;
    }
    if (/^```/.test(line)) {
      const lang = line.replace(/^```/, "").trim();
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;
      out.push({ kind: "code", lang, text: buf.join("\n") });
      continue;
    }
    if (line.startsWith("|") && i + 1 < lines.length && /\|[-:\s|]+\|/.test(lines[i+1])) {
      const rows: string[][] = [];
      rows.push(line.split("|").slice(1, -1).map(c => c.trim()));
      i += 2;
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(lines[i].split("|").slice(1, -1).map(c => c.trim()));
        i++;
      }
      out.push({ kind: "table", rows });
      continue;
    }
    if (/^[\-\*]\s+/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^[\-\*]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^[\-\*]\s+/, "")); i++; }
      out.push({ kind: "ul", items: buf });
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\d+\.\s+/, "")); i++; }
      out.push({ kind: "ol", items: buf });
      continue;
    }
    if (/^\s*$/.test(line)) { i++; continue; }
    const buf: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|>|```|[\-\*]\s|\d+\.\s|\|)/.test(lines[i])) { buf.push(lines[i]); i++; }
    out.push({ kind: "p", text: buf.join("\n") });
  }
  return out;
});

function inline(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code class='lb-md__code'>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "<a href='$2' target='_blank' rel='noopener'>$1</a>");
}
</script>

<template>
  <div class="lb-md" :style="{ maxHeight: maxHeight || 'unset' }">
    <div v-if="loading" class="lb-md__loading">加载报告中…</div>
    <template v-else-if="blocks.length">
      <template v-for="(b, i) in blocks" :key="i">
        <h1 v-if="b.kind === 'h' && b.level === 1" v-html="inline(b.text || '')" />
        <h2 v-else-if="b.kind === 'h' && b.level === 2" v-html="inline(b.text || '')" />
        <h3 v-else-if="b.kind === 'h' && b.level === 3" v-html="inline(b.text || '')" />
        <h4 v-else-if="b.kind === 'h' && b.level === 4" v-html="inline(b.text || '')" />
        <h5 v-else-if="b.kind === 'h' && b.level === 5" v-html="inline(b.text || '')" />
        <h6 v-else-if="b.kind === 'h' && b.level === 6" v-html="inline(b.text || '')" />
        <p v-else-if="b.kind === 'p'" v-html="inline(b.text || '')" />
        <ul v-else-if="b.kind === 'ul'">
          <li v-for="(it, j) in b.items" :key="j" v-html="inline(it)" />
        </ul>
        <ol v-else-if="b.kind === 'ol'">
          <li v-for="(it, j) in b.items" :key="j" v-html="inline(it)" />
        </ol>
        <blockquote v-else-if="b.kind === 'quote'">
          <p v-for="(line, k) in (b.text || '').split('\n')" :key="k" v-html="inline(line)" />
        </blockquote>
        <pre v-else-if="b.kind === 'code'"><code>{{ b.text }}</code></pre>
        <hr v-else-if="b.kind === 'hr'" />
        <table v-else-if="b.kind === 'table' && b.rows && b.rows.length">
          <thead>
            <tr><th v-for="(c, k) in b.rows[0]" :key="k" v-html="inline(c)" /></tr>
          </thead>
          <tbody>
            <tr v-for="(row, r) in b.rows.slice(1)" :key="r">
              <td v-for="(c, k) in row" :key="k" v-html="inline(c)" />
            </tr>
          </tbody>
        </table>
      </template>
    </template>
    <div v-else class="lb-md__empty">暂无报告内容</div>
  </div>
</template>

<style scoped>
.lb-md {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--lb-fg);
  overflow-y: auto;
}
.lb-md__loading, .lb-md__empty { padding: 24px; text-align: center; color: var(--lb-muted); }
.lb-md :deep(h1), .lb-md :deep(h2), .lb-md :deep(h3), .lb-md :deep(h4), .lb-md :deep(h5), .lb-md :deep(h6) {
  font-family: "Fira Code", monospace;
  color: var(--lb-fg-strong);
  margin: 18px 0 10px;
  line-height: 1.3;
}
.lb-md :deep(h1) { font-size: 20px; }
.lb-md :deep(h2) { font-size: 17px; }
.lb-md :deep(h3) { font-size: 15px; }
.lb-md :deep(h4), .lb-md :deep(h5), .lb-md :deep(h6) { font-size: 14px; }
.lb-md :deep(p) { margin: 0 0 12px; }
.lb-md :deep(ul), .lb-md :deep(ol) { margin: 0 0 12px; padding-left: 24px; }
.lb-md :deep(li) { margin-bottom: 4px; }
.lb-md :deep(.lb-md__code) {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  background: var(--lb-accent-soft);
  color: var(--lb-primary);
  padding: 1px 6px;
  border-radius: 4px;
}
.lb-md :deep(pre) {
  margin: 0 0 12px;
  padding: 12px 14px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.5;
}
:root[data-theme="dark"] .lb-md :deep(pre) { background: #050912; border: 1px solid var(--lb-border); }
.lb-md :deep(pre code) { font-family: "Fira Code", monospace; white-space: pre-wrap; word-break: break-all; }
.lb-md :deep(blockquote) {
  margin: 0 0 12px;
  padding: 8px 14px;
  border-left: 3px solid var(--lb-accent);
  background: var(--lb-accent-soft);
  color: var(--lb-fg-soft);
  border-radius: 0 6px 6px 0;
}
.lb-md :deep(blockquote p) { margin: 0; }
.lb-md :deep(table) { width: 100%; border-collapse: collapse; margin: 0 0 14px; font-size: 12.5px; }
.lb-md :deep(th), .lb-md :deep(td) {
  padding: 8px 12px;
  border-bottom: 1px solid var(--lb-border-soft);
  text-align: left;
  vertical-align: top;
}
.lb-md :deep(th) { background: var(--lb-surface-soft); color: var(--lb-fg-strong); font-weight: 600; }
.lb-md :deep(hr) { border: none; border-top: 1px solid var(--lb-border); margin: 16px 0; }
.lb-md :deep(strong) { color: var(--lb-fg-strong); font-weight: 600; }
.lb-md :deep(a) { color: var(--lb-primary); text-decoration: underline; text-underline-offset: 2px; }
</style>