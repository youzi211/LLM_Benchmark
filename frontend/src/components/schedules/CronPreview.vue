<script setup lang="ts">
/**
 * Cron 表达式预览 (Phase 3.5)
 * 解析 5 段 cron 表达式 (分 时 日 月 周), 显示人类可读描述 + 接下来 3 次触发时间.
 */
import { computed } from "vue";

const props = withDefaults(defineProps<{
  /** 5 段标准 cron, 空格分隔 */
  expression?: string;
  /** 起始时间, 用于计算 next run */
  baseTime?: Date;
}>(), { baseTime: () => new Date() });

const fieldNames = ["分", "时", "日", "月", "周"];

interface Field { raw: string; values: number[]; step: number | null; }

function parseField(raw: string, min: number, max: number): Field {
  if (!raw || raw === "*") return { raw, values: rangeArr(min, max), step: null };
  let step: number | null = null;
  let body = raw;
  if (raw.includes("/")) {
    const [b, s] = raw.split("/");
    step = Number(s);
    body = b === "*" ? "*" : b;
  }
  let values: number[];
  if (body === "*") {
    values = rangeArr(min, max);
  } else if (body.includes(",")) {
    values = body.split(",").flatMap(p => expandRange(p.trim(), min, max));
  } else if (body.includes("-")) {
    values = expandRange(body, min, max);
  } else {
    values = [Number(body)];
  }
  if (step !== null) values = values.filter((_, i) => i % step === 0);
  return { raw, values, step };
}

function rangeArr(min: number, max: number) {
  const out: number[] = [];
  for (let i = min; i <= max; i++) out.push(i);
  return out;
}

function expandRange(p: string, min: number, max: number): number[] {
  const [a, b] = p.split("-").map(Number);
  return rangeArr(a, b ?? max);
}

const fields = computed<Field[]>(() => {
  if (!props.expression) return [];
  const parts = props.expression.trim().split(/\s+/);
  return parts.map((p, i) => {
    const min = i === 0 ? 0 : i === 1 ? 0 : 1;
    const max = i === 0 ? 59 : i === 1 ? 23 : i === 2 ? 31 : i === 3 ? 12 : 7;
    return parseField(p, min, max);
  });
});

const isValid = computed(() => fields.value.length === 5);

const humanReadable = computed(() => {
  if (!isValid.value) return "无效的 cron 表达式";
  const f = fields.value;
  const minRaw = f[0].raw;
  const hourRaw = f[1].raw;
  const dayRaw = f[2].raw;
  const monthRaw = f[3].raw;
  const weekRaw = f[4].raw;

  // 常见模板
  if (minRaw === "0" && hourRaw !== "*" && dayRaw === "*" && monthRaw === "*" && weekRaw === "*") {
    return `每小时的 ${hourRaw} 分`;
  }
  if (minRaw === "0" && hourRaw === "*" && dayRaw === "*" && monthRaw === "*" && weekRaw === "*") {
    return "每小时整点";
  }
  if (minRaw === "0" && hourRaw === "0" && dayRaw === "*" && monthRaw === "*" && weekRaw === "*") {
    return "每天 0 点";
  }
  if (minRaw === "0" && hourRaw === "0" && dayRaw === "1" && monthRaw === "*" && weekRaw === "*") {
    return "每月 1 日 0 点";
  }
  if (minRaw === "0" && hourRaw === "0" && dayRaw === "*" && monthRaw === "*" && weekRaw === "1") {
    return "每周一 0 点";
  }
  if (minRaw.startsWith("*/")) {
    return `每 ${minRaw.slice(2)} 分钟`;
  }
  if (hourRaw.startsWith("*/")) {
    return `每 ${hourRaw.slice(2)} 小时`;
  }
  return `分:${minRaw} 时:${hourRaw} 日:${dayRaw} 月:${monthRaw} 周:${weekRaw}`;
});

function nextRunTimes(count: number): Date[] {
  if (!isValid.value) return [];
  const out: Date[] = [];
  const f = fields.value;
  const [mins, hours, days, months, weeks] = f.map(x => x.values);
  const start = new Date(props.baseTime);
  start.setSeconds(0, 0);
  start.setMinutes(start.getMinutes() + 1); // 从下一分钟开始

  for (let i = 0; i < 60 * 24 * 366 && out.length < count; i++) {
    const t = new Date(start.getTime() + i * 60_000);
    if (months.includes(t.getMonth() + 1) &&
        days.includes(t.getDate()) &&
        hours.includes(t.getHours()) &&
        mins.includes(t.getMinutes()) &&
        (weeks.includes(t.getDay()) || weeks.length === 7)) {
      out.push(t);
    }
  }
  return out;
}

const nextRuns = computed(() => nextRunTimes(3));

function fmtTime(d: Date) {
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function relativeTime(d: Date) {
  const ms = d.getTime() - Date.now();
  if (ms < 0) return "已过期";
  const min = Math.floor(ms / 60000);
  if (min < 60) return `${min} 分钟后`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时后`;
  const day = Math.floor(h / 24);
  return `${day} 天后`;
}
</script>

<template>
  <div class="lb-cron" v-if="expression">
    <div class="lb-cron__row">
      <div class="lb-cron__expr">
        <span class="lb-cron__label">Cron</span>
        <code>{{ expression }}</code>
      </div>
      <div class="lb-cron__readable">{{ humanReadable }}</div>
    </div>
    <div v-if="isValid" class="lb-cron__runs">
      <div class="lb-cron__label">接下来 3 次</div>
      <ol class="lb-cron__list">
        <li v-for="(d, i) in nextRuns" :key="i">
          <span class="lb-cron__time">{{ fmtTime(d) }}</span>
          <span class="lb-cron__rel">{{ relativeTime(d) }}</span>
        </li>
      </ol>
    </div>
    <div v-else class="lb-cron__invalid">无效的 cron 表达式</div>
  </div>
  <div v-else class="lb-cron lb-cron--empty">未设置 cron</div>
</template>

<style scoped>
.lb-cron {
  padding: 12px 14px;
  background: var(--lb-accent-soft);
  border: 1px solid var(--lb-accent-soft-2);
  border-radius: 10px;
  font-size: 12.5px;
}

.lb-cron--empty {
  background: var(--lb-surface-soft);
  border: 1px dashed var(--lb-border);
  color: var(--lb-muted);
  text-align: center;
}

.lb-cron__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.lb-cron__expr {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.lb-cron__label {
  font-size: 11px;
  color: var(--lb-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}

.lb-cron__expr code {
  font-family: "Fira Code", monospace;
  font-size: 12.5px;
  background: var(--lb-surface);
  padding: 2px 8px;
  border-radius: 6px;
  color: var(--lb-primary);
  font-weight: 500;
  border: 1px solid var(--lb-border);
}

.lb-cron__readable {
  color: var(--lb-fg-strong);
  font-weight: 500;
}

.lb-cron__runs {
  padding-top: 8px;
  border-top: 1px solid var(--lb-accent-soft-2);
}

.lb-cron__list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.lb-cron__list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: "Fira Code", monospace;
  font-size: 12px;
  color: var(--lb-fg-soft);
  padding: 2px 0;
}

.lb-cron__time {
  color: var(--lb-fg-strong);
  font-weight: 500;
}

.lb-cron__rel {
  color: var(--lb-primary);
  font-size: 11.5px;
}

.lb-cron__invalid {
  margin-top: 8px;
  padding: 6px 10px;
  background: var(--lb-danger-bg);
  color: var(--lb-danger);
  border-radius: 6px;
  font-size: 12px;
}
</style>
