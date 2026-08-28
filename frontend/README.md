# LLM Benchmark · Vue 控制台

这个目录是新版 Web 控制台源码，使用 Vue 3 + Vite + Element Plus + ECharts，对原 `app/web/` 原生静态页做并行重构。

- 旧控制台仍挂载在 `/ui/`。
- Vue 控制台构建产物输出到 `app/web_vue/`，后端在该目录存在时挂载到 `/ui-vue/`。
- `app/web_vue/` 是构建产物，不入库；部署或本地预览前需要先执行 `npm run build`。

## 启动与构建

```bash
# 安装依赖
npm install

# 开发期：Vite dev server，/api 代理到本地 FastAPI :8020
npm run dev

# 生产构建：输出到 ../app/web_vue/
npm run build
```

后端启动示例：

```powershell
$env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020
```

访问入口：

- 旧控制台：`http://127.0.0.1:8020/ui/`
- Vue 控制台：`http://127.0.0.1:8020/ui-vue/`（需要先构建生成 `app/web_vue/index.html`）

## 当前页面结构

产品主线保持为三块：

| 路由 | 页面 | 能力 |
| --- | --- | --- |
| `#/basic` | 基础评测 | 提交 `/api/tasks/run`，查看基础任务、指标结果和 Markdown 报告 |
| `#/stress` | 压测评测 | 提交 `/api/stress/tasks/default`，查看/取消任务，展示吞吐、延迟、成功率曲线 |
| `#/intelligence` | 能力评测 | 只展示本地可用数据集，展示描述/本地路径/subsets/configured_subset_list，提交评测、查看进度和分数图 |

辅助入口：

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `#/suites` | 一键完整评测 | 辅助入口占位，后续接 suite 编排详情 |
| `#/schedules` | 定时任务 | 辅助入口占位，后续接 schedule 管理 |

## 工程结构

```text
frontend/
├── index.html
├── package.json
├── vite.config.ts          # base = "./"，outDir = ../app/web_vue
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
- `/ui-vue/` 使用 hash 路由，静态托管路径变化时不需要后端 fallback。
- `app/web_vue/`、`node_modules/`、自动生成声明文件和 TypeScript buildinfo 都不提交。
