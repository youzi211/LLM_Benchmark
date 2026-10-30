# LLM Benchmark · Vue 控制台

控制台源码，使用 Vue 3 + Vite + Element Plus + ECharts。后端（8020）只提供 `/api`，页面由 vite dev server 提供。

- 本地开发：`npm run dev`，配置端口为 `5173`，占用时 Vite 会选择下一可用端口（例如 `5174`），以终端输出为准；`/api` 代理到 `http://127.0.0.1:8020`。
- `npm run build` 产物输出到 `app/web_vue/`，不入库，主服务也不挂载。

## 启动与构建

```bash
# 安装依赖
npm install

# 开发期：Vite dev server，/api 代理到本地 FastAPI :8020
npm run dev

# 构建产物输出到 ../app/web_vue/（不入库，主服务不挂载）
npm run build
```

后端启动示例：

```powershell
$env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020
```

访问终端输出的地址，首页 hash 路由为 `#/overview`。

## 当前页面结构

产品主线保持为三块：

桌面端使用分组侧边导航与紧凑顶部工具栏；小于 1100px 时导航收为抽屉，移动端保留底部快捷入口。模型选择、刷新、添加/编辑模型、评测环境与主题切换均在顶部。

| 路由 | 页面 | 能力 |
| --- | --- | --- |
| `#/basic` | 基础评测 | 异步提交 `/api/tasks/run-async`，查看/取消基础任务、指标结果和 Markdown 报告 |
| `#/stress` | 压测评测 | 提交 `/api/stress/tasks/default`，查看/取消任务，展示吞吐、延迟、成功率曲线 |
| `#/intelligence` | 能力评测 | 只展示本地可用数据集，展示描述/本地路径/subsets/configured_subset_list，提交评测、查看进度和分数图 |

辅助入口：

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `#/overview` | 概览 | 全量任务指标、运行中与最近结束任务、服务健康和三线评测快捷入口 |
| `#/tasks` | 任务中心 | 三条评测线统一筛选与详情导航 |
| `#/compare` | 任务对比 | 对比已选任务的指标 |
| `#/suites` | 一键完整评测 | 选择评测线、设置参数、启动并跟踪 suite |
| `#/schedules` | 定时任务 | 创建、查看、触发和删除定时计划 |

概览采用浅灰背景、白色面板和蓝色强调；标题使用系统无衬线字体，指标使用等宽数字。平均耗时自动选择毫秒、秒、分钟或小时，悬停可查看原始毫秒值。指标来自原有统计接口，空态、加载态和接口失败分别展示。

## 工程结构

```text
frontend/
├── index.html
├── package.json
├── vite.config.ts          # dev 起始端口 5173，/api 代理到 8020，outDir = ../app/web_vue
├── tsconfig.json
├── tsconfig.node.json
├── env.d.ts
└── src/
    ├── main.ts             # createApp + Pinia + Router
    ├── App.vue
    ├── styles/global.css
    ├── layouts/MainLayout.vue
    ├── router/index.ts
    ├── stores/models.ts    # 顶部全局模型选择
    ├── api/
    │   ├── http.ts         # axios 实例，baseURL = "/api"
    │   ├── models.ts       # /api/models
    │   └── evaluations.ts  # 三条评测线 + suite/schedule 的 API 封装
    ├── components/
    │   └── EChart.vue      # ECharts 封装
    └── views/
        ├── BasicView.vue
        ├── StressView.vue
        ├── IntelligenceView.vue
        ├── SuitesView.vue
        └── SchedulesView.vue
```

## 设计约束

- 不在浏览器存储 API Key；模型配置仍以服务端 `/api/models` 为准。
- 能力评测数据集只展示后端返回的 `available_local=true` 数据集，避免用户选择本地不存在的数据集导致 EvalScope 远程下载或运行失败。
- 数据集有子集时在卡片中展示 `subsets`，并高亮 `configured_subset_list`，帮助用户理解默认运行范围。
- 使用 hash 路由。
- `app/web_vue/`、`node_modules/`、自动生成声明文件和 TypeScript buildinfo 都不提交。
