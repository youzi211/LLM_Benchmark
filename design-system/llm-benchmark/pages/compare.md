# 任务对比页覆盖规则

> 路由: `/compare` | 覆盖 MASTER.md 全局规则

## 布局
PageHero + 多列并排对比表（?ids= 参数驱动）

## 与 Master 的偏差
- 最多 3 列并排展示（状态/模型/耗时/指标数）
- 指标横向表行 sticky
- CSV 导出 + 单列移除
- 空状态与无指标状态引导

## 关键组件
EmptyState, StatusTag

## 注意事项
- 从 basic/stress/intelligence 批量栏「对比」按钮跳转
- 无任务时品牌空态引导
- 路由参数 ids 与 types 需对齐
