# 模型评测与定时评测接口对接说明

> 面向接口调用方：本文只说明如何通过后端接口提交一次模型评测，以及如何创建一个定时模型评测计划。服务已启动在 `8020` 端口。

## 0. 基础信息

假设评测服务地址为：

```text
http://<服务器IP>:8020
```

接口统一前缀：

```text
http://<服务器IP>:8020/api
```

示例中使用变量：

```bash
API_BASE="http://<服务器IP>:8020/api"
```

如果在服务器本机调用，可以使用：

```bash
API_BASE="http://127.0.0.1:8020/api"
```

### 重要概念

| 名称 | 含义 |
|---|---|
| 评测服务地址 | 本系统的地址，即 `http://<服务器IP>:8020`。 |
| 上游模型地址 `url` / `base_url` | 被测模型的 OpenAI 兼容接口地址，例如 `http://10.1.2.3:8000/v1`。不要填成本系统地址。 |
| `key` / `api_key` | 调用上游模型所需的 API Key。 |
| `model` | 上游模型名，例如 `qwen2.5-72b-instruct`。 |
| `protocol` | 上游协议，常用 `chat_completions`；如果上游只支持 Responses API，可填 `responses`。 |
| `suite_id` | 一次综合评测任务 ID。后续查询进度、报告都靠它。 |
| `schedule_id` | 一个定时评测计划 ID。后续查询、手动触发、删除计划都靠它。 |

---

## 1. 直接提交一次模型评测，不保存模型配置

如果调用方直接提供：

- 上游模型地址 `url`
- API Key `key`
- 模型名 `model`

推荐使用：

```http
POST /api/suites/quick
```

这个接口会立即创建一次综合评测任务。它不会把传入的 Key 写入 `data/models.json`，适合临时评测或一次性接入验证。

### 1.1 请求示例

```bash
curl -X POST "$API_BASE/suites/quick" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://<上游模型IP>:<端口>/v1",
    "key": "<上游模型API_KEY>",
    "model": "<上游模型名>",
    "protocol": "chat_completions",
    "title": "模型A-综合评测",

    "context_window_tokens": 32768,
    "max_output_tokens": 4096,
    "timeout_seconds": 60,

    "run_gateway": true,
    "run_intelligence": true,
    "run_stress": true,

    "stress_options": {
      "parallel": [1, 2, 4],
      "number": [2, 4, 8],
      "stream": true
    },

    "poll_interval_seconds": 5,
    "timeout_seconds_total": 7200,
    "wait_for_completion": false
  }'
```

### 1.2 常用参数说明

| 参数 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `url` | 是 | string | 上游模型服务地址。可填 OpenAI 兼容 base URL，例如 `http://10.1.2.3:8000/v1`。如果误填成本系统 `8020` 地址，会评测失败。 |
| `key` | 否 | string | 上游模型 API Key。没有鉴权时可传空字符串 `""`。 |
| `model` | 是 | string | 上游模型名称。 |
| `protocol` | 否 | string | 默认 `chat_completions`。可选 `chat_completions` / `responses`。 |
| `title` | 否 | string | 本次评测显示标题。 |
| `context_window_tokens` | 否 | integer | 模型上下文窗口大小，例如 `32768`、`131072`。用于上下文相关评测和报告说明。 |
| `max_output_tokens` | 否 | integer | 模型最大输出 token 数，例如 `4096`、`8192`。 |
| `timeout_seconds` | 否 | integer | 单次上游请求超时时间，默认 `60` 秒，范围 `1~600`。 |
| `run_gateway` | 否 | boolean | 是否执行网关 smoke / 工程检查，默认 `true`。 |
| `run_intelligence` | 否 | boolean | 是否执行智力评测，默认 `true`。 |
| `run_stress` | 否 | boolean | 是否执行压测，默认 `true`。 |
| `stress_options.parallel` | 否 | integer[] | 压测并发档位，例如 `[1,2,4]`。 |
| `stress_options.number` | 否 | integer[] | 每个并发档位的请求数，例如 `[2,4,8]`。 |
| `stress_options.stream` | 否 | boolean | 压测是否使用流式请求。 |
| `wait_for_completion` | 否 | boolean | 是否阻塞等待评测完成。对接口对接建议填 `false`，然后轮询查询。 |
| `poll_interval_seconds` | 否 | number | 服务内部等待子任务完成的轮询间隔。 |
| `timeout_seconds_total` | 否 | number | 整个 suite 最长等待时间，例如 `7200` 秒。 |
| `intelligence_limit` | 否 | integer | 智力评测样本上限，传给 EvalScope 的 `limit`。注意 EvalScope 对多 subset 数据集是按 subset 截断；本系统已对 `live_code_bench` 默认限制为 `release_latest` 单一 subset，避免 `200 × 多个 subset` 放大。`null`（不传）表示不限制所选 subset 的样本数。定时评测会默认取前 `200` 条（见第五节），quick 评测默认不限。 |

> 至少要有一个评测通道为 `true`：`run_gateway`、`run_intelligence`、`run_stress` 不能全是 `false`。

### 1.3 返回值示例

```json
{
  "suite_id": "suite_20260807153021_ab12cd34",
  "model_id": "inline_20260807153021_ef56ab78",
  "title": "模型A-综合评测",
  "status": "queued",
  "current_step": null,
  "schedule_id": null,
  "created_at": "2026-08-07T15:30:21.123456Z",
  "updated_at": "2026-08-07T15:30:21.123456Z",
  "started_at": null,
  "completed_at": null,
  "gateway_task_id": null,
  "intelligence_task_id": null,
  "stress_task_id": null,
  "overview_id": null,
  "overview_report_path": null,
  "steps": [
    {
      "name": "gateway",
      "title": "网关 smoke / 工程检查",
      "enabled": true,
      "status": "pending",
      "task_id": null,
      "started_at": null,
      "completed_at": null,
      "message": null
    }
  ],
  "errors": []
}
```

重点字段：

| 字段 | 说明 |
|---|---|
| `suite_id` | 本次综合评测任务 ID。后续查询进度、下载报告都用它。 |
| `status` | 当前状态：`queued`、`running`、`completed`、`partial`、`failed`、`interrupted`。 |
| `current_step` | 当前执行阶段。 |
| `gateway_task_id` | 网关 smoke 子任务 ID，完成后会有值。 |
| `intelligence_task_id` | 智力评测子任务 ID，完成后会有值。 |
| `stress_task_id` | 压测子任务 ID，完成后会有值。 |
| `overview_report_path` | 总览报告文件路径，完成后会有值。 |
| `steps` | 每个评测阶段的状态。 |
| `errors` | 错误列表。 |

---

## 2. 查询评测进度和报告

### 2.1 查询 suite 进度

```bash
curl -X GET "$API_BASE/suites/<suite_id>"
```

例如：

```bash
curl -X GET "$API_BASE/suites/suite_20260807153021_ab12cd34"
```

返回仍然是 `SuiteRun` 结构。重点看：

```json
{
  "suite_id": "suite_20260807153021_ab12cd34",
  "status": "running",
  "current_step": "intelligence",
  "gateway_task_id": "task_xxx",
  "intelligence_task_id": null,
  "stress_task_id": "stress_task_xxx",
  "overview_report_path": null,
  "steps": [
    {"name": "gateway", "status": "completed"},
    {"name": "stress", "status": "completed"},
    {"name": "intelligence", "status": "running"}
  ],
  "errors": []
}
```

当 `status` 进入以下状态时，说明本次 suite 已结束：

| 状态 | 含义 |
|---|---|
| `completed` | 全部启用的评测通道都完成。 |
| `partial` | 部分通道完成，部分通道失败或跳过。 |
| `failed` | suite 整体失败。 |

### 2.2 下载总览报告

suite 完成后调用：

```bash
curl -X GET "$API_BASE/suites/<suite_id>/report"
```

返回内容是 Markdown 报告文本，例如：

```markdown
# 模型评测总览报告

## 一眼看懂
...
```

如果还没生成报告，会返回 `404 suite_report_not_found`。

---

## 3. 创建定时模型评测

定时评测和 `quick` 不一样：**定时任务必须依赖已保存的模型配置 `model_id`**。

原因是定时任务要在未来自动执行，届时请求方不一定还在线，所以系统必须能从本地配置中读取上游模型地址、Key、模型名等信息。

因此创建定时任务分两步：

```text
第一步：POST /api/models 保存模型配置
第二步：POST /api/suites/schedules 创建定时计划
```

> 注意：保存模型配置会把上游模型 Key 写入服务端本地 `data/models.json`。该文件不能提交 Git，也不要外传。

### 3.1 查看可用 profile

```bash
curl -X GET "$API_BASE/evalscope/profiles"
```

默认推荐使用 `scheduled_light`，它只包含非代码类能力数据集和小档位压测，不依赖 sandbox。`scheduled_code` 和 `full_offline` 会使用 HumanEval/MBPP 等代码执行类数据集，创建前需要在 `data/evalscope.json` 中启用 sandbox。

---

## 4. 第一步：保存模型配置

### 4.1 请求示例

```bash
curl -X POST "$API_BASE/models" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "model-a",
    "name": "模型A",
    "protocol": "chat_completions",
    "base_url": "http://<上游模型IP>:<端口>/v1",
    "api_key": "<上游模型API_KEY>",
    "model": "<上游模型名>",
    "timeout_seconds": 60,
    "enabled": true,
    "declared_context_tokens": 32768,
    "declared_max_output_tokens": 4096,
    "concurrency_levels": [1, 2, 4]
  }'
```

### 4.2 参数说明

| 参数 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `id` | 是 | string | 模型配置 ID。只能包含字母、数字、下划线、点和横线，例如 `model-a`。后续创建定时任务用这个值。 |
| `name` | 是 | string | 人类可读名称。 |
| `protocol` | 是 | string | `chat_completions` 或 `responses`。 |
| `base_url` | 是 | string | 上游模型 OpenAI 兼容 base URL。 |
| `api_key` | 否 | string | 上游模型 API Key。无鉴权可传空字符串。 |
| `model` | 是 | string | 上游模型名。 |
| `timeout_seconds` | 否 | integer | 单次请求超时，默认 `60` 秒。 |
| `enabled` | 否 | boolean | 是否启用该模型配置，默认 `true`。 |
| `declared_context_tokens` | 否 | integer | 声明的上下文窗口大小。 |
| `declared_max_output_tokens` | 否 | integer | 声明的最大输出 token 数。 |
| `concurrency_levels` | 否 | integer[] | 默认压测并发档位。每个值范围 `1~200`。 |

### 4.3 返回值示例

```json
{
  "id": "model-a",
  "name": "模型A",
  "protocol": "chat_completions",
  "base_url": "http://<上游模型IP>:<端口>/v1",
  "api_key": "<masked-api-key>",
  "model": "<上游模型名>",
  "timeout_seconds": 60,
  "enabled": true,
  "declared_context_tokens": 32768,
  "declared_max_output_tokens": 4096,
  "concurrency_levels": [1, 2, 4],
  "created_at": "2026-08-07T15:40:00.000000Z",
  "updated_at": "2026-08-07T15:40:00.000000Z"
}
```

返回里的 `api_key` 会被掩码显示，但服务端本地会保存真实 Key。

如果 `id` 已存在，接口会返回错误。此时可以改用更新接口：

```http
PUT /api/models/{model_id}
```

---

## 5. 第二步：创建只执行一次的定时评测

如果需求是：

> 今天提交，今晚/明天凌晨 00:00 只跑一次。

使用 `run_once: true`。

### 5.1 请求示例

```bash
curl -X POST "$API_BASE/suites/schedules" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "模型A-今晚零点评测",
    "model_id": "model-a",
    "enabled": true,
    "profile": "scheduled_light",

    "run_once": true,
    "run_date": "2026-08-08",
    "time_of_day": "00:00",
    "timezone": "Asia/Shanghai",

    "title": "模型A-零点综合评测",
    "run_gateway": true,
    "run_intelligence": true,
    "run_stress": true,

    "stress_options": {
      "parallel": [1, 2, 4],
      "number": [2, 4, 8],
      "stream": true
    },

    "poll_interval_seconds": 5,
    "timeout_seconds": 7200
  }'
```

### 5.2 参数说明

| 参数 | 必填 | 类型 | 说明 |
|---|---:|---|---|
| `name` | 是 | string | 定时计划名称。 |
| `model_id` | 是 | string | 已保存的模型配置 ID，即第 4 步里的 `id`。 |
| `enabled` | 否 | boolean | 是否启用计划，默认 `true`。 |
| `profile` | 否 | string/null | 评测 profile，默认 `scheduled_light`。轻量 profile 不含 HumanEval/MBPP/LiveCodeBench 等代码执行类数据集；如需代码评测可传 `scheduled_code`，但必须先启用 sandbox。传 `null` 可跳过 profile。内置 profile 数据集组合统一维护在 `app/evalscope_defaults.py`。 |
| `run_once` | 否 | boolean | 是否只执行一次。只跑一天/只跑一次时填 `true`。 |
| `run_date` | `run_once=true` 时建议填写 | string | 执行日期，格式 `YYYY-MM-DD`，例如 `2026-08-08`。 |
| `time_of_day` | 否 | string | 执行时间，格式 `HH:MM`，例如 `00:00`。 |
| `timezone` | 否 | string | 时区，国内一般填 `Asia/Shanghai`。 |
| `title` | 否 | string | 触发后生成 suite 的标题。 |
| `run_gateway` | 否 | boolean | 是否执行网关 smoke。 |
| `run_intelligence` | 否 | boolean | 是否执行智力评测。 |
| `run_stress` | 否 | boolean | 是否执行压测。 |
| `stress_options` | 否 | object | 压测参数。 |
| `poll_interval_seconds` | 否 | number | suite 内部轮询间隔。 |
| `timeout_seconds` | 否 | number | 定时 suite 总等待超时时间，和 quick 接口的 `timeout_seconds_total` 含义一致。 |
| `intelligence_datasets` | 否 | string[] | 能力评测数据集列表。默认由 profile 决定；当前 `scheduled_light` 为 `gsm8k`、`math_500`、`ceval`，维护位置为 `app/evalscope_defaults.py`。 |
| `intelligence_limit` | 否 | integer | 智力评测样本上限，传给 EvalScope 的 `limit`。`scheduled_light` 默认 `50`；不使用 profile 时默认 `200`。EvalScope 原生语义是按 subset 截断，因此内置默认对 `live_code_bench` 注入 `subset_list=["release_latest"]`，让该数据集在 `limit=200` 时实际只跑 200 条。需要覆盖到固定版本、更多 subset 或不限制所选 subset 样本数时，请显式传足够大的 `intelligence_limit`/不传该字段，并在 `data/evalscope.json` 覆盖 `dataset_args`。 |

> 执行顺序说明：suite 内部按 网关 smoke → EvalScope 压测 → EvalScope 智力评测 → 总览报告 的顺序执行（先跑压测拿到性能数据，再跑智力评测，避免长时智力评测卡死整条 suite 时丢掉性能结果）。返回示例里的 `steps` 和 `current_step` 也按这个顺序推进。

### 5.3 返回值示例

```json
{
  "schedule_id": "suite_schedule_20260807154500_ab12cd34",
  "name": "模型A-今晚零点评测",
  "model_id": "model-a",
  "enabled": true,
  "title": "模型A-零点综合评测",
  "time_of_day": "00:00",
  "timezone": "Asia/Shanghai",
  "interval_days": 1,
  "run_once": true,
  "run_date": "2026-08-08",
  "next_run_at": "2026-08-07T16:00:00Z",
  "last_run_at": null,
  "last_suite_id": null,
  "run_count": 0,
  "last_error": null
}
```

重点字段：

| 字段 | 说明 |
|---|---|
| `schedule_id` | 定时计划 ID。查询、删除、立即触发都用它。 |
| `next_run_at` | 下一次实际触发时间，返回为 UTC 时间。例：`2026-08-07T16:00:00Z` 等于北京时间 `2026-08-08 00:00:00`。 |
| `run_once` | `true` 表示只执行一次。执行后计划会自动变成 `enabled=false`。 |
| `last_suite_id` | 最近一次由该计划触发出的 `suite_id`。刚创建时为 `null`。 |
| `run_count` | 已触发次数。 |
| `last_error` | 最近一次调度投递错误。正常为 `null`；它不代表最近 suite 的执行结果，执行失败请看 `last-run` 或 `GET /api/suites/{last_suite_id}`。 |

---

## 6. 创建每天/每 N 天重复执行的定时评测

如果需求是每天 00:00 都跑，使用：

```json
"run_once": false,
"interval_days": 1
```

请求示例：

```bash
curl -X POST "$API_BASE/suites/schedules" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "模型A-每日零点评测",
    "model_id": "model-a",
    "enabled": true,

    "run_once": false,
    "time_of_day": "00:00",
    "timezone": "Asia/Shanghai",
    "interval_days": 1,

    "title": "模型A-每日综合评测",
    "run_gateway": true,
    "run_intelligence": true,
    "run_stress": true,

    "stress_options": {
      "parallel": [1, 2, 4],
      "number": [2, 4, 8],
      "stream": true
    },

    "poll_interval_seconds": 5,
    "timeout_seconds": 7200
  }'
```

`interval_days` 说明：

| 值 | 含义 |
|---:|---|
| `1` | 每天执行一次。 |
| `2` | 每 2 天执行一次。 |
| `7` | 每 7 天执行一次。 |

---

## 7. 查询、手动触发和删除定时计划

### 7.1 查询所有计划

```bash
curl -X GET "$API_BASE/suites/schedules"
```

### 7.2 查询单个计划

```bash
curl -X GET "$API_BASE/suites/schedules/<schedule_id>"
```

### 7.3 立即触发计划

```bash
curl -X POST "$API_BASE/suites/schedules/<schedule_id>/trigger"
```

含义：不等 `next_run_at`，立刻按该计划保存的配置启动一次 suite。默认 `wait_for_completion=false`，即立即返回新建 suite；需要阻塞等待时可加 query 参数 `?wait_for_completion=true`。

注意：

- 如果计划是 `run_once: true`，立即触发后该计划会自动停用。
- 如果计划是 `run_once: false`，立即触发只是额外跑一次，后续仍按 `interval_days` 周期执行。

返回值是新创建的 `SuiteRun`，里面会有新的 `suite_id`。

### 7.4 查询最近一次计划执行结果

```bash
curl -X GET "$API_BASE/suites/schedules/<schedule_id>/last-run"
```

该接口返回计划本身和最近一次 `last_suite_id` 对应的 suite 摘要，重点字段包括：

- `last_suite_status`：最近一次 suite 的状态。
- `last_suite_current_step`：最近一次 suite 当前步骤。
- `last_suite_error_count`：最近一次 suite 错误数量。
- `last_suite_errors`：最近一次 suite 错误摘要。

注意：`GET /api/suites/schedules/<schedule_id>` 中的 `last_error` 只代表调度器投递 suite 失败，例如模型配置缺失或创建 suite 失败；如果 `last_error=null` 但 `last_suite_status=partial/failed`，说明计划已成功触发，但评测执行阶段失败。

### 7.5 删除计划

```bash
curl -X DELETE "$API_BASE/suites/schedules/<schedule_id>"
```

返回示例：

```json
{
  "deleted": true,
  "schedule_id": "suite_schedule_20260807154500_ab12cd34"
}
```

---

## 8. 常见对接流程

### 8.1 立刻测一个模型

```text
POST /api/suites/quick
  -> 得到 suite_id
GET /api/suites/{suite_id}
  -> 轮询直到 status 是 completed / partial / failed / interrupted
GET /api/suites/{suite_id}/report
  -> 下载 Markdown 报告
```

### 8.2 今晚 00:00 只测一次

```text
POST /api/models
  -> 得到或确认 model_id
POST /api/suites/schedules，run_once=true，run_date=目标日期，time_of_day=00:00
  -> 得到 schedule_id 和 next_run_at
GET /api/suites/schedules/{schedule_id}/last-run
  -> 到点后查看 last_suite_id / run_count / last_error / last_suite_status / last_suite_errors
GET /api/suites/{last_suite_id}
  -> 必要时查看完整评测进度
GET /api/suites/{last_suite_id}/report
  -> 下载报告
```

### 8.3 每天 00:00 都测

```text
POST /api/models
  -> 得到或确认 model_id
POST /api/suites/schedules，run_once=false，interval_days=1，time_of_day=00:00
  -> 得到 schedule_id 和 next_run_at
```

---

## 9. 错误返回格式

接口出错时通常返回：

```json
{
  "error": {
    "code": "model_not_found",
    "message": "Model config not found: model-a"
  }
}
```

常见错误：

| HTTP 状态 | code | 原因 |
|---:|---|---|
| `400` | `invalid_suite_request` | 请求参数不合法，例如三个评测通道都为 `false`。 |
| `404` | `model_not_found` | 创建定时任务时传入的 `model_id` 不存在。 |
| `404` | `suite_not_found` | 查询的 `suite_id` 不存在。 |
| `404` | `suite_schedule_not_found` | 查询、触发或删除的 `schedule_id` 不存在。 |
| `400` | `profile_not_found` | 创建定时任务时指定的 profile 不存在。 |
| `400` | `profile_requires_sandbox` | 创建定时任务时指定了需要 sandbox 的 profile，但未启用 sandbox。 |
| `404` | `suite_report_not_found` | 报告还没生成或文件不存在。 |

---

## 10. 对接注意事项

1. `POST /api/suites/quick` 适合立刻评测，不保存 Key。
2. 定时评测必须先 `POST /api/models` 保存模型配置，因此 Key 会保存在服务端本地 `data/models.json`。
3. `url` / `base_url` 是上游模型服务地址，不是本评测服务的 `8020` 地址。
4. `next_run_at` 返回 UTC 时间；如果 `timezone` 是 `Asia/Shanghai`，北京时间 `00:00` 会显示为前一天 UTC `16:00`。
5. 代码执行类智力评测，例如 MBPP/MBPP+、HumanEval/HumanEval+，需要 sandbox 服务保持运行；使用 `scheduled_code` 或 `full_offline` profile 时，如果未启用 sandbox，创建计划会返回 `400 profile_requires_sandbox`。
6. 建议对接方保存 `suite_id` 和 `schedule_id`，并优先用 `GET /api/suites/schedules/{schedule_id}/last-run` 排查定时任务执行结果。
7. 能力评测默认数据集组合、内置 `dataset_args` 和 profile 维护在 `app/evalscope_defaults.py`，未命中本地目录时会从 ModelScope 下载（例如 `humaneval`、`gsm8k` 等）。若希望评测时不依赖外网、不重复下载，可提前在 `data/evalscope_datasets/` 下按数据集名准备本地目录（例如 `data/evalscope_datasets/gsm8k/`、`data/evalscope_datasets/humaneval/`），后端会自动识别并改为本地加载（日志显示 `Loading dataset ... from local` 而非 `from modelscope`）。通过 `GET /api/intelligence/datasets/local` 可确认本机已就绪的数据集（`available_local=true`）。同机已有另一份完整数据集时，对每个数据集目录建立符号链接即可复用，无需复制，尤其推荐用于 `live_code_bench` 等大体量数据集。`live_code_bench` 内置只跑 `release_latest`；如需固定版本，可在 `data/evalscope.json` 设置 `"dataset_args": {"live_code_bench": {"subset_list": ["release_v6"]}}`。
8. `data/models.json` 可能包含明文 API Key，已在 `.gitignore` 中忽略，切勿提交到 Git；`data/evalscope_datasets/`、`data/evalscope.json` 同理。
