# Basic 评测页覆盖规则

> 本文件覆盖 MASTER.md 中与基础评测页相关的规则。未提及的仍以 MASTER.md 为准。

## 布局
- PageHero (eyebrow BASIC SMOKE + actions: 刷新/开始基础评测)
- 主体 iew-grid 三列等高: 任务列表 | 任务详情 | 指标/报告
- ≤1180 折叠单列

## 组件
- FilterChips: 状态过滤 + 计数
- 复选框 + 批量操作栏 (对比/导出)
- TaskTimeline: 4 步状态驱动 (已提交/排队/执行/完成)
- MarkdownReport: 内联极简 markdown 渲染
- EmptyState: 品牌空态 4 变体

## 页面专属
- StatusTag 状态可能为 undefined，模板需兜底 'pending'
- el-table 表头文字用 --lb-fg-soft (非 EP 默认 #909390)
- 任务详情区 4 项 meta 卡片网格 + 指标卡 + 错误体 (pre + JSON 高亮)
