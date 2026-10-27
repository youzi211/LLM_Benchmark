import { computed } from "vue";
import { useTheme } from "@/composables/useTheme";

/**
 * ECharts 外观配置, 颜色取自设计 token, 随明暗主题切换.
 * 在 EChart 组件里与页面传入的 option 合并, title/legend 等由页面自己维护.
 */
export function useChartTheme() {
  const { resolved } = useTheme();

  const chartTheme = computed(() => {
    // 依赖 resolved 才会在切换主题时重新计算.
    void resolved.value;
    const css = typeof document === "undefined" ? null : getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string) => css?.getPropertyValue(name).trim() || fallback;
    const fgSoft = token("--lb-fg-soft", "#475569");
    const muted = token("--lb-muted", "#5b6b83");
    const border = token("--lb-border", "#e5e7eb");
    const surface = token("--lb-surface", "#ffffff");
    const fgStrong = token("--lb-fg-strong", "#0f172a");
    return {
      color: [
        token("--lb-primary", "#1e40af"),
        token("--lb-warning", "#d97706"),
        token("--lb-success", "#16a34a"),
        token("--lb-cta", "#7c3aed"),
      ],
      textStyle: { color: fgSoft },
      title: { textStyle: { color: fgStrong } },
      legend: { textStyle: { color: fgSoft } },
      tooltip: { backgroundColor: surface, borderColor: border, textStyle: { color: fgSoft } },
      // axisLabel 取 muted 而非 fg-soft: 与页面里自定义的 axisLabel 同色, 后者覆盖时外观不变.
      xAxis: { axisLabel: { color: muted }, axisLine: { lineStyle: { color: border } } },
      yAxis: {
        axisLabel: { color: muted },
        nameTextStyle: { color: muted },
        splitLine: { lineStyle: { color: border } },
      },
    };
  });

  return { chartTheme };
}