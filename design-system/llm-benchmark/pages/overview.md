# Overview 页覆盖规则

> 本文件覆盖 MASTER.md 中与概览页相关的规则。未提及的仍以 MASTER.md 为准。

## 布局
- 顶部 PageHero (eyebrow + h1 + description)，无 actions 槽
- 主体 .lb-overview 纵向 flex，gap 20px
- KPI 行: 4 列 epeat(4, minmax(0,1fr))；≤1180 折叠 2 列
- 网格行: minmax(0, 2fr) minmax(0, 1fr) (趋势图 + 服务健康/运行中)；≤1180 折叠单列

## 组件
- KpiCard: 数字用 Fira Code，趋势用 ECharts 双轴折线
- ServiceHealth: 4 项服务状态 + 延迟，每行可 retry/configure
- RunningTasks: 运行中任务列表，空态引导跳转三线评测

## 页面专属
- KPI 自动 2 列在 <1180；移动端 <760 主区底部加 80px padding 避免被 MobileTabs 遮挡
- 趋势图 ECharts canvas 在 375 下需监听 resize 重绘
