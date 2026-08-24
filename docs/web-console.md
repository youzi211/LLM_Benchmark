# Web 控制台操作说明

> 本文档说明内置 Web 控制台的功能、访问方式和它调用的后端接口。控制台是纯客户端单页应用（`app/web/index.html` + `app/web/app.js` + `app/web/styles.css`），由 FastAPI 主服务以静态文件方式提供，**没有独立后端**，所有操作都复用 `/api` 下的 JSON 接口。

## 1. 访问方式

主服务启动后，浏览器访问 `http://<主服务地址>:8020/` 会自动跳转到 `http://<主服务地址>:8020/ui/`。

- 静态挂载点：`/ui`（`app/main.py` 中 `app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True))`）。
- 根路径 `/`：返回重定向到 `/ui/`。
- 不需要额外前端构建步骤或 Node 服务，刷新即生效。

## 2. 功能面板

### 2.1 临时模型一键评测（Quick suite）

直接填写上游模型信息并发起一次 quick suite，调用 `POST /api/suites/quick`：

- `url`（或 `base_url`）：OpenAI 兼容基础地址，可传 `/v1` 也可传完整 `/chat/completions` 端点，服务按 `protocol` 归一化。
- `key`（或 `api_key`）：上游密钥，密码框输入；提交后前端会清空，不写 localStorage。
- `model`：上游模型名。
- `protocol`：`chat_completions` / `responses`。
- `context_window_tokens`、`max_output_tokens`、单次请求 `timeout_seconds`。
- `title`、三个通道开关 `run_gateway` / `run_intelligence` / `run_stress`、连通性 only 模式。
- 高级压测参数 `parallel`、`number`，以及 `poll_interval_seconds`、总超时 `timeout_seconds_total`。
- `intelligence_limit`：能力评测每个数据集样本上限，quick 评测默认不限。

### 2.2 进度雷达（Live suite）

- 输入 `suite_id` 查询 `GET /api/suites/{suite_id}`，展示 suite 状态、当前步骤（`gateway → stress → intelligence → overview`）、步骤列表。
- 完成后可直接打开总览报告入口（`GET /api/suites/{suite_id}/report`）。
- 提供停止轮询按钮。

### 2.3 已有模型配置（Saved models）

- 从 `GET /api/models` 读取本机持久化模型配置。
- 选择后调用 `POST /api/suites/default` 发起一键评测。

### 2.4 定时一键评测（Scheduled suites）

- 模式切换：只执行一次 / 周期执行。
- 一次性任务填 `run_date` + `time_of_day`；周期任务填 `interval_days`。
- 默认时区 `Asia/Shanghai`，可填计划名 `name`、生成 suite 标题 `title`。
- 可先把左侧临时模型参数通过 `POST /api/models` 保存为模型配置，再 `POST /api/suites/schedules` 创建定时计划；也可为已有模型直接创建。
- 列出已有计划：状态、立即触发（`POST /api/suites/schedules/{id}/trigger`）、删除（`DELETE /api/suites/schedules/{id}`）。
- 定时智力评测默认每个数据集只取前 `200` 条样本（`DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT`），可传 `intelligence_limit` 覆盖。

### 2.5 最近 suite（History）

- 从 `GET /api/suites` 读取最近 suite 列表，点击进入详情。

### 2.6 指标曲线（Metrics curves）

选中 suite 后自动读取关联任务结果并渲染：

- 压测：吞吐、延迟、TTFT/TPOT、成功率曲线（`/api/stress/tasks/{task_id}/result`）。
- 能力评测：数据集分数、能力维度柱状图（`/api/intelligence/tasks/{task_id}/result`）。
- 网关 smoke：指标状态网格（`/api/tasks/{task_id}`）。

## 3. 安全边界

- Quick suite 的 `key` 只随本次请求发送到服务端，服务端不会写入 `data/models.json`，也不会写入 suite JSON 或报告。
- 前端不使用 localStorage 保存密钥。
- 但如果在“定时一键评测”中选择**保存左侧模型参数**为模型配置，`key` 会随模型配置写入本机 `data/models.json`，用于后续定时执行。`data/models.json` 不提交 Git。
- API 响应、suite JSON 和报告中的错误信息都会脱敏。

## 4. 调用的接口清单

| 操作 | 方法 | 路径 |
|---|---|---|
| Quick suite | POST | `/api/suites/quick` |
| Default suite | POST | `/api/suites/default` |
| Suite 列表 | GET | `/api/suites` |
| Suite 详情 | GET | `/api/suites/{suite_id}` |
| Suite 总览报告 | GET | `/api/suites/{suite_id}/report` |
| 模型列表 | GET | `/api/models` |
| 保存模型 | POST | `/api/models` |
| 更新模型 | PUT | `/api/models` |
| 定时计划列表 | GET | `/api/suites/schedules` |
| 创建定时计划 | POST | `/api/suites/schedules` |
| 删除定时计划 | DELETE | `/api/suites/schedules/{id}` |
| Profile 列表 | GET | `/api/evalscope/profiles` |
| 立即触发定时计划 | POST | `/api/suites/schedules/{id}/trigger` |
| 网关任务详情 | GET | `/api/tasks/{task_id}` |
| 能力评测结果 | GET | `/api/intelligence/tasks/{task_id}/result` |
| 压测结果 | GET | `/api/stress/tasks/{task_id}/result` |

接口契约详见 [API 接口文档](api.md)；评测口径详见 [指标测试方法文档](metric-test-methods.md)。


## 5. 定时评测 profile

Web 控制台创建定时计划时默认传 `profile=scheduled_light`，避免默认执行 HumanEval/MBPP/LiveCodeBench 等依赖 sandbox 的代码类数据集。需要代码能力定时评测时可选择 `scheduled_code`，但服务端必须已在 `data/evalscope.json` 中启用 sandbox。
