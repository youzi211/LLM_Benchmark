export interface ChartEvidence { model_id: string; metrics: Record<string, any>[]; load_mode?: string | null; snapshot?: { conditions: Record<string, any> } | null }
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
export function stressMode(e: ChartEvidence): string {
  if (e.load_mode) return e.load_mode;
  if (typeof e.snapshot?.conditions.open_loop === "boolean") return e.snapshot.conditions.open_loop ? "open" : "closed";
  if (e.metrics.some(r => r.parallel > 0) && !e.metrics.some(r => r.rate > 0)) return "closed";
  return "unknown";
}
export function stressOption(entries: ChartEvidence[], field: string, unit: string, open: boolean) {
  const relevant = entries.filter(e => stressMode(e) === (open ? "open" : "closed"));
  const axis = (r: Record<string, any>) => open ? r.rate : r.parallel;
  const points = [...new Set(relevant.flatMap(e => e.metrics.map(axis)).filter(finite))].sort((a, b) => a - b);
  return { tooltip: { trigger: "axis", renderMode: "richText" }, legend: { type: "scroll", bottom: 0 }, grid: { left: 65, right: 30, top: 35, bottom: 75 },
    xAxis: { type: "category", name: open ? "请求速率 (req/s)" : "并发数", nameLocation: "middle", nameGap: 27, data: points },
    yAxis: { type: "value", name: unit, scale: true },
    series: relevant.map(e => ({ name: e.model_id, type: "line", smooth: false, connectNulls: false, symbolSize: 7,
      data: points.map(x => { const row = e.metrics.find(r => axis(r) === x); return row && finite(row[field]) && row[field] >= 0 ? row[field] : null; }) })) };
}
export function abilityGroups(entries: ChartEvidence[]) {
  const groups = new Map<string, { name: string; datasets: Set<string>; entries: ChartEvidence[] }>();
  for (const e of entries) for (const r of e.metrics) {
    const name = `${r.metric_id || '指标未知'} · ${r.unit || '单位未知'} · ${r.direction || '方向未知'}`;
    const key = `${name}|${r.display_multiplier ?? 1}`;
    if (!groups.has(key)) groups.set(key, { name, datasets: new Set(), entries });
    groups.get(key)!.datasets.add(r.dataset);
  }
  return [...groups.entries()].map(([key, g]) => {
    const datasets = [...g.datasets];
    return { key, name: g.name, option: {
      tooltip: { trigger: "axis", renderMode: "richText" }, legend: { type: "scroll", bottom: 0 },
      grid: { left: 60, right: 25, top: 30, bottom: 85 },
      xAxis: { type: "category", data: datasets, axisLabel: { interval: 0, rotate: datasets.length > 4 ? 25 : 0 } },
      yAxis: { type: "value", name: g.name.split(' · ')[1] },
      series: entries.map(e => ({ name: e.model_id, type: "bar", barMaxWidth: 42,
        data: datasets.map(dataset => { const row = e.metrics.find(r => r.dataset === dataset && `${r.metric_id || '指标未知'} · ${r.unit || '单位未知'} · ${r.direction || '方向未知'}|${r.display_multiplier ?? 1}` === key);
          return row && finite(row.score) ? row.score * (row.display_multiplier ?? 1) : null; }) }))
    } };
  });
}
