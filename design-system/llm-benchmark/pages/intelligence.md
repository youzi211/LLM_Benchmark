# 能力评测页覆盖规则

> 路由: `/intelligence` | 覆盖 MASTER.md 全局规则

## 布局
PageHero + view-grid 三列（数据集选择 + 任务列表 + 任务详情）

## 与 Master 的偏差
- 复用 basic 的 view-grid
- 数据集列表只展示本地已提供的数据集（data/evalscope_datasets）
- DatasetPicker 可展开子集选择

## 关键组件
DatasetPicker, FilterChips, StatusTag, EmptyState

## 注意事项
- 数据集动态从 EvalScope BENCHMARK_REGISTRY 读取，无需改代码
- Judge/Sandbox 配置在 EvalScopeConfigDrawer（顶栏「评测环境」按钮触发）
- 数据集列表无数据时品牌空态引导放入本地数据集
