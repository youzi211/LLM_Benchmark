# 一键完整评测页覆盖规则

> 路由: `/suites` | 覆盖 MASTER.md 全局规则

## 布局
PageHero + Stepper 五步向导（选线 / 能力集 / 压测参数 / 临时模型 / 确认）

## 与 Master 的偏差
- 非三列 view-grid，而是 Stepper 横线步骤导航 + 每步内容区
- 各步可后退；第 5 步确认页含汇总表 + 启动按钮
- 各步 EmptyState 引导

## 关键组件
Stepper, EmptyState, EvalScopeConfigDrawer

## 注意事项
- 步骤间状态由 Stepper item.state 驱动（done/current/upcoming）
- 向导式交互，与 basic/stress/intelligence 的列表+详情模式不同
- 移动端 Stepper 横向滚动
