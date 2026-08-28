# Web 控制台操作说明

> 本文档说明内置 Web 控制台的功能、访问方式和它调用的后端接口。主控制台是纯客户端单页应用（`app/web/index.html` + `app/web/app.js` + `app/web/styles.css`），由 FastAPI 主服务以静态文件方式提供，**没有独立前端后端**，所有操作都复用 `/api` 下的 JSON 接口。`/ui-vue/` 下的 Vue 3 + Vite 重写版本（源码在 `frontend/`，构建产物在 `app/web_vue/`）作为并行验证入口，未编译该目录时主服务会跳过该挂载，不影响 `/ui/` 正常使用。

## 1. 访问方式

主服务启动后，浏览器访问 `http://<主服务地址>:8020/` 会自动跳转到 `http://<主服务地址>:8020/ui/`。

- 静态挂载点：
  - `/ui`（`app/main.py` 中 `app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True))`），主控制台；
  - `/ui-vue`（`_mount_optional_static(app, "/ui-vue", WEB_VUE_DIR, name="ui-vue")`），Vue 3 + Vite 重写版本，与 `/ui` 并行提供交叉验证。
- 根路径 `/`：返回重定向到 `/ui/`。
- 主控制台 (`/ui`) 不需要额外前端构建步骤或 Node 服务，刷新即生效。
- `/ui-vue` 的产物来自 `frontend/`（Vite `build.outDir = "../app/web_vue"`）。只有当 `app/web_vue/` 目录实际存在（即已经执行过 `npm run build`）时，主服务才会挂载 `/ui-vue`；目录缺失时挂载被安全跳过，避免在主服务启动阶段崩溃。

## 2. 页面信息架构

控制台按照用户理解的三条评测线组织，而不是按照后端存储对象组织：

1. **基础评测**：网关 smoke / 工程检查。
2. **压测评测**：EvalScope perf 吞吐、延迟、成功率评测。
3. **能力评测**：EvalScope 数据集能力评测。

顶部提供全局能力：

- 当前模型选择：从 `GET /api/models` 读取已保存模型，三条评测线共用。
- 系统状态：显示基础服务、EvalScope 压测、EvalScope 能力和 Judge 状态。
- 辅助入口：一键完整评测、定时任务。

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

## 6. Vue 重写控制台（`/ui-vue`，并行验证）

`frontend/` 是用 Vue 3 + Vite + Element Plus + ECharts 重写的控制台工程；构建后产物输出到 `app/web_vue/`，主服务以只读静态目录方式把它挂载到 `/ui-vue`。

- URL：`http://<主服务地址>:8020/ui-vue/`；`index.html` 中脚本与样式采用相对路径，可在任意 URL 前缀下正常加载。
- 触发构建：`cd frontend && npm install && npm run build`（`vite.config.ts` 中 `build.outDir = "../app/web_vue"`）。
- 运行时数据流：开发期 `vite.config.ts` 把 `/api/*` 反代到 `http://127.0.0.1:8020`；生产模式下静态产物仍通过 `http://<主服务地址>:8020/api/*` 调用同一份后端，所有现有接口契约保持不变。
- 与 `/ui` 的关系：两套前端互不耦合。`/ui`（`app/web/`）继续维护作为对照基线，`/ui-vue` 用于在不影响基线的前提下逐步替换 UI；当 `/ui-vue` 可独立交付时，再决定是否把默认跳转切到 `/ui-vue/`。
- 缺失安全：当 `app/web_vue/` 目录不存在（例如未执行过 `npm run build`，或在只部署后端的场景下），主服务 `app/main.py` 中的 `_mount_optional_static` 会跳过挂载，`/ui-vue` 路径返回 404，`/ui` 不受影响。`tests/test_web_console.py::test_public_app_serves_legacy_ui_and_optional_vue_mount` 与 `test_web_vue_optional_mount_helper_skips_when_directory_missing` 覆盖了这种行为。

接口契约详见 [API 接口文档](api.md)；评测口径详见 [指标测试方法文档](metric-test-methods.md)。
