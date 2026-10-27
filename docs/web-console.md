# Web 控制台操作说明

> 本文档说明 Web 控制台的功能、访问方式和它调用的后端接口。控制台是 `frontend/` 下的 Vue 3 + Vite 单页应用，**没有独立前端后端**，所有操作都复用 `/api` 下的 JSON 接口。主服务（8020）只提供 API，不挂载页面。

## 1. 访问方式

本地开发用 `cd frontend && npm install && npm run dev` 启动 vite dev server（默认 `http://127.0.0.1:5174/`），它把 `/api/*` 代理到 `http://127.0.0.1:8020`。主服务侧对应命令：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020
```

`GET /`、`GET /ui/`、`GET /ui-vue/` 在 8020 上均返回 404；`tests/test_web_console.py::test_public_app_is_api_only` 覆盖了这一点。

## 2. 页面信息架构

左侧导航第一项是**概览**，汇总三条评测线的任务状态和整体健康情况；其后按用户理解的三条评测线组织，而不是按照后端存储对象组织：

1. **基础评测**：网关 smoke / 工程检查。
2. **压测评测**：EvalScope perf 吞吐、延迟、成功率评测。
3. **能力评测**：EvalScope 数据集能力评测。

顶部提供全局能力：

- 当前模型选择：从 `GET /api/models` 读取已保存模型，三条评测线共用。
- 系统状态：显示基础服务、EvalScope 压测、EvalScope 能力和 Judge 状态；连接异常时顶栏会显示脱敏的错误横幅。
- 辅助入口：一键完整评测、定时任务；开发模式下额外提供“设计系统”页（`/style-guide`，仅 dev 构建可见）。
- 任务对比：基础评测页和能力评测页选中多个任务后跳转 `/compare` 对比。

控制台界面跟随明暗主题（无手动切换开关，由系统 `prefers-color-scheme` 决定），所有颜色来自 `frontend/src/styles/global.css` 中的 `--lb-*` 设计 token，图表（ECharts）同样通过 `frontend/src/composables/useChartTheme.ts` 读取 token 渲染。

## 3. 三条评测线

### 3.1 基础评测

用于验证模型服务基础可用性、协议兼容、usage、错误结构、上下文和缓存 smoke。

页面能力：

- 选择评测计划，默认 `gateway_acceptance_v1`。
- 可选输入 `metric_ids`，逗号或空白分隔。
- 提交基础评测。
- 查看最近基础评测任务列表。
- 点击任务查看指标结果、错误摘要和 Markdown 报告入口。

主要接口：

- `POST /api/tasks/run`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{task_id}`

### 3.2 压测评测

用于验证不同并发和请求数下的吞吐、延迟、TTFT / TPOT、成功率。

页面能力：

- 使用默认压测参数提交任务。
- 开启“自定义压测参数”后填写 `parallel`、`number`、`stream`、`dataset`、`dataset_path`、长度和 token 过滤参数。
- 查看最近压测任务列表。
- 点击任务查看状态、参数摘要、吞吐曲线、延迟曲线、TTFT/TPOT、成功率和报告入口。
- 对非终态任务执行取消。

主要接口：

- `GET /api/stress/evalscope/health`
- `POST /api/stress/tasks/default`
- `GET /api/stress/tasks`
- `GET /api/stress/tasks/{task_id}`
- `GET /api/stress/tasks/{task_id}/result`
- `POST /api/stress/tasks/{task_id}/cancel`
- `GET /api/stress/reports/{task_id}`

### 3.3 能力评测

用于验证模型在数学、代码、中文考试、综合推理等数据集上的能力表现。

页面能力：

- 使用默认数据集组合提交任务。
- 开启“自定义数据集”后选择具体 EvalScope 数据集。数据集卡片展示中文名称、用途描述、是否本地可用、分类、Judge/sandbox 要求、本地路径、本地 subset 列表以及当前默认 `subset_list`。
- 设置 `limit` 和 `eval_batch_size`。
- 查看最近能力评测任务列表。
- 点击任务查看当前数据集、样本进度、整体进度条、数据集分数、能力类别汇总和报告入口。
- 对非终态任务执行取消。

主要接口：

- `GET /api/intelligence/evalscope/health`
- `GET /api/intelligence/evalscope/judge-config`
- `GET /api/intelligence/datasets`
- `POST /api/intelligence/tasks/default`
- `POST /api/intelligence/tasks`
- `GET /api/intelligence/tasks`
- `GET /api/intelligence/tasks/{task_id}`
- `GET /api/intelligence/tasks/{task_id}/progress`
- `GET /api/intelligence/tasks/{task_id}/result`
- `POST /api/intelligence/tasks/{task_id}/cancel`
- `GET /api/intelligence/reports/{task_id}`

## 4. 辅助入口

### 4.1 一键完整评测

“一键完整评测”是 suite 编排能力的轻量入口，不再作为页面主心智。它用于一次性执行基础、压测、能力三条线并生成总览报告。

支持两种模式：

- 使用当前已保存模型，调用 `POST /api/suites/default`。
- 临时填写 URL / API Key / model，调用 `POST /api/suites/quick`。提交后前端会清空 Key 输入框，不写 localStorage。

辅助区也展示最近完整评测列表，可查看报告或取消非终态 suite。

### 4.2 定时任务

“定时任务”作为辅助入口保留，用于为当前模型创建一次性或周期 suite 计划。

页面能力：

- 选择 `scheduled_light` / `scheduled_code` / `full_offline` profile。
- 设置只执行一次或周期执行。
- 选择基础、压测、能力三条评测线。
- 创建计划、列出计划、立即触发、删除计划。

主要接口：

- `POST /api/suites/schedules`
- `GET /api/suites/schedules`
- `POST /api/suites/schedules/{id}/trigger`
- `DELETE /api/suites/schedules/{id}`

## 5. 安全边界

- 临时模型完整评测中的 `key` 只随本次请求发送到服务端，前端提交后清空，不写 localStorage。
- 顶部当前模型只读取 `data/models.json` 中的已保存模型，API Key 不在页面中提供明文编辑能力。
- API 响应、suite JSON 和报告中的错误信息都会脱敏。
- `data/models.json` 属于本地敏感配置，不提交 Git。

## 6. 前端工程

`frontend/` 用 Vue 3 + Vite + Element Plus + ECharts 实现控制台，`npm run dev` 运行开发服务器，`npm run build` 只用于产出静态资源（`app/web_vue/`，不入库）；主服务不再挂载该产物。详见 `frontend/README.md`。

接口契约详见 [API 接口文档](api.md)；评测口径详见 [指标测试方法文档](metric-test-methods.md)。
