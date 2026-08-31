# 定时任务页覆盖规则

> 路由: `/schedules` | 覆盖 MASTER.md 全局规则

## 布局
PageHero + view-grid--two 两列（列表 + 详情/编辑抽屉）

## 与 Master 的偏差
- view-grid--two: minmax(0,1fr) minmax(0,1.2fr)，≤1180 折叠单列
  （原 360px 下限在 375px 下会撑破，已去除）
- 列表含 Cron 列 + StatusTag + 下次运行相对时间（relativeFromNow）
- ScheduleEditorDrawer 抽屉编辑

## 关键组件
CronPreview, StatusTag, EmptyState, ScheduleEditorDrawer

## 注意事项
- CronPreview 五段解析 + 人类可读 + 接下来 3 次触发
- 新建/编辑走抽屉，非内嵌表单
- relativeFromNow 工具在 api/evaluations.ts，模板需显式 import
