# 压测评测页覆盖规则

> 路由: `/stress` | 覆盖 MASTER.md 全局规则

## 布局
PageHero + view-grid 三列（表单 + 任务列表 + 任务详情）

## 与 Master 的偏差
- 复用 basic 的 view-grid 与通用任务列表模式（FilterChips + 搜索 + 复选框 + 批量操作栏 + StatusTag + EmptyState）
- 表单含并发/限速/时长配置，字段较多；移动端单列堆叠
- dataset-cards 在 ≤760 折叠为单列

## 关键组件
FilterChips, StatusTag, EmptyState, DatasetPicker

## 注意事项
- 压测参数表单字段较多，移动端单列堆叠
- 任务详情复用 TaskTimeline
- view-grid ≤1180 折叠单列，防止压测参数表单撑破窄屏
