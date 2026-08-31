# LLM Benchmark 前端重构规划

> 基于 ui-ux-pro-max 设计系统（MASTER.md）+ 现状视觉诊断
> 目标: 从组件拼接升级为有品牌一致性与上下文体验的数据密集型工作台
> 范围: Vue 3 + Vite + Element Plus 2.8 + ECharts 5.5 现有栈

## 0. 设计令牌

### 色彩
- primary #1E40AF 品牌主色、关键 CTA、激活态
- secondary #3B82F6 次级强调、链接
- cta #F59E0B 行动按钮、警告、强调数字
- bg #F8FAFC 全局背景
- surface #FFFFFF 卡片表面
- fg #1E3A8A 正文/标题
- fg-soft #475569 副文
- muted #64748B 提示、占位
- success #16A34A 成功、通过
- warning #D97706 警告、运行中
- danger #DC2626 失败、错误
- info #3B82F6 信息、提示

### 字体
- Heading / 数字: Fira Code 400/500/600/700
- Body: Fira Sans 300/400/500/600/700

### 暗色模式扩展
- data-theme dark 完整覆盖所有 lb token
- 主背景 #0B1220、表面 #111A2E、边框 gba(148,163,184,0.18)

## 1. 反模式清单

| 不要 | 改为 |
|------|------|
| el-table 默认 No Data | 自定义品牌空状态 |
| Element Plus 默认插画 | 自绘 SVG |
| 所有 panel-card 无差异 | primary/secondary/tertiary 卡片变体 |
| 红条错误横在顶 | toast + 边角连接灯 |
| 仅 hover 触发 | 同时 onClick 适配触屏 |
| 0.2s 平移 | 150-300ms 过渡 |
| 系统默认字体 | Fira Code/Sans 体系 |
| 单行长表单 | 字段分组 + 步骤式 |
| 单条操作 | 复选框 + 批量 |

## 2. 重构任务清单

### Phase 1: 基础设施 (1.5d)

**1.1 暗色模式 + 主题切换 (0.5d)**
- styles/global.css 加 [data-theme=dark] token 覆盖
- 新增 composables/useTheme.ts
- MainLayout 加切换按钮
- App.vue 初始化读取 localStorage
- 验收: 切换无白底闪烁；暗色文字对比 ≥ 4.5:1

**1.2 设计系统展示页 (0.5d)**
- 新增 iews/StyleGuideView.vue + 路由 /style-guide
- 展示色板、字体、按钮状态、tag、卡片变体
- 验收: 完整可视化所有 token

**1.3 全局加载与错误体系 (0.5d)**
- 新增 composables/useToast.ts
- 新增 components/common/StatusDot.vue
- 新增 components/common/ConnectionBanner.vue
- 验收: 错误用 toast；连接状态有视觉指示

### Phase 2: 布局升级 (2.0d)

**2.1 MainLayout 双层结构 (1.0d)**
- 拆为品牌顶栏 40px + 页面英雄区 80-120px
- 新增 components/layouts/{PageHero,TopBar,Breadcrumb}.vue
- 重写 layouts/MainLayout.vue
- 验收: 切 tab 英雄区联动；有面包屑

**2.2 通知中心入口 (1.0d)**
- 新增 components/layouts/NotificationCenter.vue
- 新增 stores/notifications.ts
- 顶栏铃铛 + 下拉面板（运行中/完成/失败 分组）
- 验收: 完成/失败自动入通知；可跳转；可标已读

### Phase 3: 核心页面 (8.0d)

**3.1 Overview 概览页 (1.5d)**
- 新增 iews/OverviewView.vue (替代 / 默认)
- 4 KPI 卡 + 7 日趋势 ECharts + 服务健康 + 运行中列表
- 新增 components/overview/{KpiCard,ServiceHealth,TrendChart,RunningTasks}.vue
- 验收: 进入首页即可见全局状态

**3.2 任务列表通用升级 (2.0d)**
- 新增通用 components/common/{DataTable,FilterChips,StatusTag,ProgressBar,EmptyState,BulkActionBar}.vue
- 改造 iews/{Basic,Stress,Intelligence}View.vue 任务列表部分
- 验收: 筛选 30s→3s；批量可用；空态引导

**3.3 任务详情实时页 (2.0d)**
- 新增 components/common/{TaskTimeline,LogTail,MetricStream,ProgressRing}.vue
- 改造 3 个 View 的详情部分
- 验收: 长任务可见实时进度；失败可展开

**3.4 SuiteView 步骤式向导 (1.5d)**
- 新增 components/suites/{SuiteWizard,StepLane,StepProfile,StepJudge,StepConfirm}.vue
- 改造 iews/SuitesView.vue
- 验收: 4 步可后退；每步可校验

**3.5 SchedulesView 升级 (1.0d)**
- 列表改用通用 DataTable
- 新增 components/schedules/CronPreview.vue 可视化 cron
- 验收: cron 可视化；列表筛选/批量

### Phase 4: 体验打磨 (4.5d)

**4.1 键盘快捷键 (0.5d)**
- 新增 composables/useShortcuts.ts
- 新增 components/layouts/ShortcutHelp.vue
- 绑定 g b/s/i、c、/、?

**4.2 任务对比 (1.5d)**
- 新增 iews/CompareView.vue + 路由
- 新增 components/common/ComparePanel.vue

**4.3 报告内联预览 (1.5d)**
- 新增 components/common/MarkdownReport.vue
- 集成到 TaskTimeline

**4.4 移动端适配 (1.0d)**
- 新增断点 + MobileTabs.vue
- DataTable 卡片模式

## 3. 依赖图

`
Phase 1 (1.1 -> 1.2 -> 1.3)
        ↓
Phase 2 (2.1 -> 2.2)
        ↓
Phase 3 (3.1 -> 3.2 -> 3.3, 同时 3.4 / 3.5)
        ↓
Phase 4 (4.1 -> 4.2 -> 4.3 -> 4.4)
`

## 4. 验收标准

- [ ] dev 服务启动无错
- [ ] playwright 截图实际页面
- [ ] 暗色文字对比 ≥ 4.5:1
- [ ] 键盘 tab 顺序合理
- [ ] 响应式 1440/1024/768/375 可读
- [ ] git diff 只动计划内文件

## 5. 不动的东西

- 后端 API 契约
- data/models.json / data/evalscope.json
- vite.config.ts 端口与代理
- app/web_vue 输出目录
- 不引入新依赖除非必要 (markdown 渲染可用 markdown-it)

## 6. 工时合计

| Phase | 任务 | 工时 |
|-------|------|------|
| 1 | 3 | 1.5d |
| 2 | 2 | 2.0d |
| 3 | 5 | 8.0d |
| 4 | 4 | 4.5d |
| 合计 | 14 | 16.0d |

## 7. 推进节奏

每个任务:
1. 启动 - 读 MASTER.md + 当前文件 + 接口契约
2. 设计 - 必要时 --page 持久化覆盖
3. 实现 - 单文件/单组件完成
4. 验证 - vite 启动 + playwright 截图
5. 回灌 - 追加变更日志

## 8. 变更日志

| 日期 | 任务 | 改动 | 备注 |
|------|------|------|------|
| 2026-08-29 | 规划 | REFACTOR_PLAN.md | 初版建立 |
| 2026-08-30 | Phase 1.1 | composables/useTheme.ts, styles/global.css, App.vue, MainLayout.vue | 暗色模式 + 主题切换 (light/dark/auto + 持久化 + 顶栏按钮 + 提前初始化避免闪烁) |
| 2026-08-30 | Phase 1.2 | views/StyleGuideView.vue, router/index.ts, MainLayout.vue | 设计系统展示页 /style-guide, 含 12 色板/字体/圆角阴影/按钮/状态/Token 速查/反模式 7 个 section |
| 2026-08-30 | Phase 1.3 | composables/useToast.ts, components/common/StatusDot.vue, ConnectionBanner.vue, layouts/MainLayout.vue | 全局错误 toast + 边角连接状态条 + 顶栏状态灯, 替代全宽红条; 错误有 retry/dismiss |
| 2026-08-30 | Phase 2.1 | components/layouts/PageHero.vue, views/BasicView.vue, StressView.vue, IntelligenceView.vue | 每个主 tab 上方加页面英雄区 (eyebrow + h1 + description + 右上 actions), 把"开始评测/刷新"等主操作从表单底部上移到 hero |
| 2026-08-30 | Phase 3.1 | components/overview/{KpiCard,TrendChart,ServiceHealth,RunningTasks}.vue, views/OverviewView.vue, router/index.ts, MainLayout.vue | Overview 概览页 (新首页): Page Hero + 4 KPI 卡 + 7 日 ECharts 双轴趋势 + 服务健康 4 项 + 当前运行中 3 任务 + 最近完成 5 条; / 重定向到 /overview; MainTabs 加入 概览 |
| 2026-08-30 | Phase 3.2 | components/common/{StatusTag,EmptyState,FilterChips}.vue, views/BasicView.vue | 通用组件: StatusTag 语义状态; EmptyState 品牌空态 (4 变体 + 自绘 SVG); FilterChips 含计数过滤条. BasicView 任务列表升级: 搜索 + 状态 chips + 复选框 + 批量操作栏 + 耗时列 + EmptyState |
| 2026-08-30 | Phase 3.3 | components/common/TaskTimeline.vue, views/BasicView.vue | 任务详情升级: TaskTimeline 4 步 (已提交/排队/执行/完成) 状态驱动; 详情区改用品牌空态 + 4 项 meta 卡片网格 + 指标卡 + 错误体 (pre+JSON 高亮) |
| 2026-08-30 | Phase 3.4 | components/layouts/Stepper.vue, views/SuitesView.vue | Suite 步骤式向导: 5 步 (选线/能力集/压测参数/临时模型/确认启动) 横线 Stepper + 上下步导航 + 各步 EmptyState 引导 + 第 5 步确认页含汇总表 + 启动按钮 |
| 2026-08-30 | Phase 3.5 | components/schedules/CronPreview.vue, views/SchedulesView.vue | Cron 预览组件 (5 段解析 + 人类可读 + 接下来 3 次触发 + 相对时间). SchedulesView 加 Page Hero + Cron 列 + StatusTag 化状态 + 下次运行含相对时间 + EmptyState 品牌空态 |
| 2026-08-30 | Phase 4.1 | composables/useShortcuts.ts, components/layouts/ShortcutHelp.vue, layouts/MainLayout.vue | 键盘快捷键: g b/s/i/o/u/d 跳转 6 个主页面; ? 打开/关闭帮助; Esc 关闭. 顶栏键盘图标触发. ShortcutHelp 全屏模态按 Esc 或 点击遮罩关闭 |
| 2026-08-30 | Phase 4.2 | views/CompareView.vue, router/index.ts, views/BasicView.vue | 任务对比: ?ids=a,b,c&types=basic,...; 3 列并排展示 状态/模型/耗时/指标数; 下方指标横向表 + 行 sticky; CSV 导出; 单列移除; 空状态与无指标状态引导; BasicView 批量栏加"对比"按钮 |
| 2026-08-30 | Phase 4.3 | components/common/MarkdownReport.vue, views/BasicView.vue | Markdown 内联报告: 极简自实现 (标题/段落/列表/表格/代码块/引用/分隔/行内格式), 深色代码块; BasicView 详情区加"内联报告"区, 根据 selected task 自动 build markdown 字符串, maxHeight 420 滚动, 保留原 report_path 外链 |
| 2026-08-30 | Phase 4.4 | components/layouts/MobileTabs.vue, styles/global.css, layouts/MainLayout.vue | 移动端适配: <760px 触发. (a) 顶栏隐藏副标题+API 状态紧凑 (b) Tabs 横向滚动隐藏滚动条 (c) Connection banner 隐藏详情行 (d) Page hero actions 全宽 (e) KPI 自动 2 列. 新增 MobileTabs 底部固定导航 4 tab (概览/基础/压测/能力) 含图标, 移动端加主区 padding-bottom 80 防遮挡. 375px 视口实测通过 |
| 2026-08-30 | 重构 | styles/global.css, views/SuitesView.vue, views/SchedulesView.vue | Agent A (CSS): view-grid 三列等高 (stretch + grid-auto-rows:1fr + 卡片 flex column + body overflow-y:auto), 字号梯度 (2xs-3xl) + leading tokens, --lb-gap-5/6, --lb-shadow-sm/md/lg/hover 双层系统, 卡片 outline 风格 + hover translateY -1px, 主区 padding 24/28/48, max-width 1480. Agent B (Suites/Schedules): 删除内嵌 #header (一键完整评测/任务列表/任务详情) 让 PageHero 唯一; el-empty 换 EmptyState. Agent C: 误 git checkout -- 删 BasicView 的 Phase 3.2/3.3/4.3 工作, 后续手工重建 |
| 2026-08-30 | 重建 | views/BasicView.vue, views/StressView.vue, views/IntelligenceView.vue | 重建 BasicView (16KB, 完整 PageHero + FilterChips + 搜索 + 复选框 + 批量 + 对比 + StatusTag + TaskTimeline + 4 meta 卡 + 指标网格 + 错误体 + MarkdownReport + EmptyState); 同步 StressView 与 IntelligenceView (去 inner header + 加 FilterChips/搜索/批量/StatusTag/EmptyState); 3 个 view 全部使用 view-grid 等高布局, 消除双 hero 问题, 暗色模式正常 |













| 2026-08-31 | 交付前清单 | styles/global.css, api/evaluations.ts, views/{Basic,Intelligence,Stress,Schedules}View.vue | ui-ux-pro-max Pre-Delivery Checklist 收口: 补 :focus-visible 主色焦点环 + prefers-reduced-motion 全局降级; TaskLike 补 started_at/finished_at 字段对齐后端契约; 补回丢失的 relativeFromNow 工具并修复 SchedulesView 引用; 修复能力/压测 Hero 按钮误绑原始 store action (会传 MouseEvent 当 payload); BasicView 状态兜底 pending. vue-tsc + vite build 通过 |
| 2026-08-31 | Playwright 验收 | .tmp/ui-acceptance/* (gitignore 外) | 64 张截图(4 视口 x 8 页 x 亮/暗); 对比度审计: 暗色全 OK, 亮色内容文字全 OK; 键盘 Tab 11/14 焦点可见(3 个为 EP 内部控件 wrapper 焦点态); 375px 溢出 8/8 OK. 修复: 亮色 --lb-muted #6b7280→#5b6b83(4.8:1); el-table 表头/空态 #909399→fg-soft(7.58:1); view-grid--two 去掉 360px 下限并在 ≤1180 折叠单列; overview 网格 minmax(0,...) 防内容撑破; 长任务 ID 省略号兜底 |
