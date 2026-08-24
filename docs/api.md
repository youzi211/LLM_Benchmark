# API 接口文档

> 本文档是项目的一部分。后续新增、删除或修改接口时，必须同步更新本文档和 `README.md` 中的文档入口。

## 1. 基本约定

- 服务框架：FastAPI。
- 默认本地地址：`http://127.0.0.1:8020`。
- 所有业务接口前缀：`/api`。
- 当前不做平台鉴权；上游模型 API Key 仅保存在本地 `data/models.json`，不要提交。
- 请求与响应默认使用 JSON；报告下载接口返回 Markdown 文件。
- 时间字段使用 ISO 8601 字符串，通常带 UTC 时区。
- 本服务只采集评测数据和生成报告，不输出“上线通过 / 失败”的自动判定。

### 1.1 可视化控制台

主服务内置一个轻量 Web 控制台，随 FastAPI 进程一起提供静态资源，不需要单独启动前端服务：

- `GET /`：浏览器访问时跳转到 `/ui/`。
- `GET /ui/`：打开评测控制台页面。
- 控制台主要调用现有 JSON API：`POST /api/suites/quick`、`POST /api/suites/default`、`GET /api/suites`、`GET /api/suites/{suite_id}` 和 `GET /api/suites/{suite_id}/report`。
- 定时一键评测区域会调用 `GET /api/models`、`GET /api/evalscope/profiles`、`POST /api/models`、`PUT /api/models/{model_id}`、`POST /api/suites/schedules`、`GET /api/suites/schedules`、`GET /api/suites/schedules/{schedule_id}/last-run`、`POST /api/suites/schedules/{schedule_id}/trigger` 和 `DELETE /api/suites/schedules/{schedule_id}`。
- 指标曲线区域会按 suite 中的 `gateway_task_id`、`intelligence_task_id`、`stress_task_id` 继续读取 `GET /api/tasks/{task_id}`、`GET /api/intelligence/tasks/{task_id}/result` 和 `GET /api/stress/tasks/{task_id}/result`，用于展示 smoke 状态、数据集分数、吞吐、延迟、TTFT/TPOT 和成功率。
- 控制台不在浏览器 localStorage 中保存 API Key；临时模型一键评测仍遵循 `/api/suites/quick` 的安全边界，即不把传入 Key 写入 `data/models.json`、suite JSON 或报告。定时计划需要持久化模型配置；如果从左侧临时参数创建定时计划，Key 会写入本机 `data/models.json`。

## 2. 通用错误格式

当接口返回错误时，响应体统一为：

```json
{
  "error": {
    "code": "error_code",
    "message": "错误说明",
    "details": {}
  }
}
```

常见 HTTP 状态码：

| 状态码 | 含义 |
|---|---|
| `400` | 请求参数不合法，例如重复模型 ID、非法计划 ID、非法指标 ID。 |
| `404` | 资源不存在，例如模型、任务或报告不存在。 |
| `500` | 本地存储或服务内部异常。 |

## 3. 数据模型

### 3.1 ModelConfigCreate / ModelConfig

模型配置用于描述一个待评测模型接口或报告分析模型。

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `id` | string | 是 | 本地模型配置 ID。只允许字母、数字、下划线、点和短横线，最大 128 字符。 |
| `name` | string | 是 | 面向人的模型配置名称。 |
| `protocol` | string | 是 | 接口协议。可选：`chat_completions`、`responses`。 |
| `base_url` | string | 是 | 上游 OpenAI 兼容服务根地址，例如 `https://example.com/v1`。保存时会去掉末尾 `/`。 |
| `api_key` | string | 是 | 上游接口密钥。API 响应会脱敏，本地 `data/models.json` 明文保存。 |
| `model` | string | 是 | 传给上游接口的 `model` 名称。 |
| `timeout_seconds` | integer | 否 | 单次请求超时秒数，范围 1-600，默认 60。 |
| `enabled` | boolean | 否 | 是否启用该配置，默认 `true`。禁用后不可执行评测。 |
| `declared_context_tokens` | integer/null | 否 | 声明上下文长度；为空时跳过上下文长度指标。 |
| `declared_max_output_tokens` | integer/null | 否 | 声明最大输出长度；为空时输出长度指标使用默认 1024。 |
| `concurrency_levels` | integer[] | 否 | 并发评测档位，默认 `[1, 5, 10, 20]`，每个值范围 1-200，会去重排序。 |
| `created_at` | datetime | 响应 | 创建时间。 |
| `updated_at` | datetime | 响应 | 更新时间。 |

API 响应中的 `api_key` 会被脱敏，例如：

```json
{
  "api_key": "te...key"
}
```

### 3.2 ModelConfigUpdate

更新模型配置时所有字段均为可选，但不允许通过该接口修改 `id`、`created_at`。

可更新字段：

```text
name, protocol, base_url, api_key, model, timeout_seconds,
enabled, declared_context_tokens, declared_max_output_tokens, concurrency_levels
```

### 3.3 RunTaskRequest

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---:|---|
| `model_id` | string | 是 | 无 | 要评测的本地模型配置 ID。 |
| `plan_id` | string | 否 | `gateway_acceptance_v1` | 评测计划 ID。`gateway_baseline_v1` 为兼容旧名，指标集合相同。 |
| `metric_ids` | string[]/null | 否 | `null` | 指定只执行某些指标；为空时执行计划内全部指标。 |

### 3.4 TaskResult

任务接口返回结构化评测结果，并在本地 `data/tasks/` 持久化。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID，例如 `task_yyyymmddhhmmss_xxxxxxxx`。 |
| `status` | string | 任务状态：`completed` 或 `error`。 |
| `model_id` | string | 本地模型配置 ID。 |
| `model_config_name` | string/null | 模型配置名称。 |
| `upstream_model_name` | string/null | 传给上游接口的 `model` 名称。 |
| `protocol` | string/null | 模型协议。 |
| `plan_id` | string | 评测计划 ID。 |
| `metric_ids` | string[] | 本次请求解析后的指标列表。 |
| `started_at` | datetime | 开始时间。 |
| `finished_at` | datetime/null | 结束时间。 |
| `duration_ms` | number/null | 任务总耗时毫秒。 |
| `results` | MetricResult[] | 各指标结果。 |
| `report_path` | string/null | 本地 Markdown 报告路径。 |
| `analysis_model_id` | string/null | 本次报告分析模型 ID。 |
| `analysis` | object/null | LLM 报告分析结构化结果。 |
| `error` | object/null | 任务级错误。 |

### 3.5 MetricResult

| 字段 | 类型 | 说明 |
|---|---:|---|
| `metric_id` | string | 指标 ID。 |
| `metric_name` | string/null | 指标中文名。 |
| `status` | string | `completed`、`error`、`skipped`。 |
| `summary` | string | 指标摘要。 |
| `observations` | object | 观测数据。不同指标字段不同，详见 `docs/metric-test-methods.md`。 |
| `errors` | object[] | 错误列表。 |

缓存能力指标 `cache_behavior` 会在 `observations` 中返回三轮冷/热请求明细、缓存字段路径、cached tokens、命中轮次和延迟变化；具体字段以 `docs/metric-test-methods.md` 为准。

## 4. 健康检查

### GET `/health`

检查服务进程是否可访问。

#### 请求

无请求参数。

#### 响应示例

```json
{
  "status": "ok"
}
```

## 5. 模型配置接口

### POST `/api/models`

创建一个模型配置。

#### 请求示例

```json
{
  "id": "demo-chat",
  "name": "Demo Chat",
  "protocol": "chat_completions",
  "base_url": "http://127.0.0.1:9001/v1",
  "api_key": "<your-api-key>",
  "model": "demo-model",
  "timeout_seconds": 60,
  "enabled": true,
  "declared_context_tokens": 8192,
  "declared_max_output_tokens": 1024,
  "concurrency_levels": [1, 2]
}
```

#### 成功响应

`200 OK`，返回脱敏后的 `ModelConfigPublic`。

```json
{
  "id": "demo-chat",
  "name": "Demo Chat",
  "protocol": "chat_completions",
  "base_url": "http://127.0.0.1:9001/v1",
  "api_key": "<m...y>",
  "model": "demo-model",
  "timeout_seconds": 60,
  "enabled": true,
  "declared_context_tokens": 8192,
  "declared_max_output_tokens": 1024,
  "concurrency_levels": [1, 2],
  "created_at": "2026-08-05T00:00:00Z",
  "updated_at": "2026-08-05T00:00:00Z"
}
```

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `400` | `model_already_exists` | `id` 已存在。 |
| `422` | FastAPI 参数校验错误 | 请求体字段缺失或格式不合法。 |
| `500` | `storage_error` | 本地存储异常。 |

### GET `/api/models`

获取所有模型配置。

#### 请求

无请求参数。

#### 成功响应

`200 OK`，返回 `ModelConfigPublic[]`。

```json
[
  {
    "id": "demo-chat",
    "name": "Demo Chat",
    "protocol": "chat_completions",
    "base_url": "http://127.0.0.1:9001/v1",
    "api_key": "<m...y>",
    "model": "demo-model",
    "timeout_seconds": 60,
    "enabled": true,
    "declared_context_tokens": 8192,
    "declared_max_output_tokens": 1024,
    "concurrency_levels": [1, 2],
    "created_at": "2026-08-05T00:00:00Z",
    "updated_at": "2026-08-05T00:00:00Z"
  }
]
```

### GET `/api/models/{model_id}`

获取单个模型配置。

#### 路径参数

| 参数 | 类型 | 说明 |
|---|---:|---|
| `model_id` | string | 本地模型配置 ID。 |

#### 成功响应

`200 OK`，返回 `ModelConfigPublic`。

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `model_not_found` | 模型配置不存在。 |

### PUT `/api/models/{model_id}`

更新模型配置。

#### 路径参数

| 参数 | 类型 | 说明 |
|---|---:|---|
| `model_id` | string | 本地模型配置 ID。 |

#### 请求示例

```json
{
  "name": "Demo Chat Updated",
  "timeout_seconds": 120,
  "declared_context_tokens": 128000,
  "concurrency_levels": [1, 5, 10]
}
```

#### 成功响应

`200 OK`，返回更新后的 `ModelConfigPublic`。

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `model_not_found` | 模型配置不存在。 |
| `422` | FastAPI 参数校验错误 | 字段类型或范围不合法。 |
| `500` | `storage_error` | 本地存储异常。 |

### DELETE `/api/models/{model_id}`

删除模型配置。

如果删除的是当前 `analysis_model_id` 指向的报告分析模型，`analysis_model_id` 会被清空。

#### 路径参数

| 参数 | 类型 | 说明 |
|---|---:|---|
| `model_id` | string | 本地模型配置 ID。 |

#### 成功响应

```json
{
  "deleted": true
}
```

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `model_not_found` | 模型配置不存在。 |

## 6. 指标与计划接口

### GET `/api/metrics`

获取当前服务支持的全部指标。

#### 成功响应

`200 OK`，返回 `MetricInfo[]`。

```json
[
  {
    "id": "connectivity",
    "priority": "P0",
    "name": "连通性",
    "description": "检查模型接口是否可访问、响应是否为可解析 JSON、是否返回有效内容、finish_reason 和 usage 等基础字段。",
    "default_in_gateway_baseline_v1": true
  }
]
```

### GET `/api/plans`

获取当前服务支持的评测计划。

#### 成功响应

`200 OK`，返回 `PlanInfo[]`。

```json
[
  {
    "id": "gateway_acceptance_v1",
    "name": "模型网关接入验收 V1",
    "description": "收缩后的默认自研指标计划：只做网关链路、协议兼容、错误结构、usage、长度与缓存 smoke；正式能力评测和正式性能压测交给 EvalScope。",
    "metric_ids": [
      "connectivity",
      "latency_breakdown",
      "context_length",
      "output_length",
      "error_handling",
      "token_usage_accuracy",
      "cache_behavior",
      "stream_spec"
    ]
  },
  {
    "id": "gateway_baseline_v1",
    "name": "模型网关接入验收 V1（兼容旧名）",
    "description": "兼容旧 plan_id；不再包含并发/限流正式压测，正式性能结果请使用 EvalScope stress。",
    "metric_ids": [
      "connectivity",
      "latency_breakdown",
      "context_length",
      "output_length",
      "error_handling",
      "token_usage_accuracy",
      "cache_behavior",
      "stream_spec"
    ]
  }
]
```

`concurrency` 与 `rate_limit` 仍会出现在 `/api/metrics`，可通过 `metric_ids` 显式运行，但不再属于默认计划；正式并发、吞吐、延迟分位数和限流/容量边界请使用 `/api/stress/*`。

### GET `/api/plans/{plan_id}`

获取单个评测计划。

#### 路径参数

| 参数 | 类型 | 说明 |
|---|---:|---|
| `plan_id` | string | 评测计划 ID。 |

#### 成功响应

`200 OK`，返回 `PlanInfo`。

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `plan_not_found` | 计划不存在。 |

## 7. 任务接口

### POST `/api/tasks/run`

同步执行一次模型评测。接口会在评测完成后返回完整 `TaskResult`，并同时落库保存任务历史与 Markdown 报告。

#### 请求示例：执行默认计划

```json
{
  "model_id": "demo-chat",
  "plan_id": "gateway_acceptance_v1"
}
```

#### 请求示例：只执行部分指标

```json
{
  "model_id": "demo-chat",
  "plan_id": "gateway_acceptance_v1",
  "metric_ids": ["connectivity", "stream_spec"]
}
```

#### 执行流程

1. 校验 `plan_id` 和 `metric_ids`。
2. 读取模型配置。
3. 校验模型是否存在、是否启用、协议是否支持。
4. 按指标顺序执行探测。
5. 构建报告事实包。
6. 如配置了报告分析模型，调用固定模型生成结构化分析。
7. 生成 Markdown 报告。
8. 保存 `TaskResult` 到 `data/tasks/`。
9. 返回完整 `TaskResult`。

#### 成功响应

`200 OK`，返回 `TaskResult`。

#### 任务级错误响应与任务内错误

部分错误会作为接口错误返回，例如非法计划或非法指标；部分错误会作为 `TaskResult.status = "error"` 返回，例如模型不存在、模型禁用、协议不支持。

| 场景 | HTTP 状态码 | 返回形式 |
|---|---:|---|
| `plan_id` 不存在 | `400` | `error.code = invalid_task_request` |
| `metric_ids` 包含未知指标 | `400` | `error.code = invalid_metric` |
| 模型配置不存在 | `200` | `TaskResult.status = error`，`error.code = model_not_found` |
| 模型配置禁用 | `200` | `TaskResult.status = error`，`error.code = model_disabled` |
| 协议不支持 | `200` | `TaskResult.status = error`，`error.code = invalid_protocol` |
| 单个指标失败 | `200` | `TaskResult.status = completed`，对应 `MetricResult.status = error` |
| 报告分析模型失败 | `200` | `TaskResult.status` 不受影响，`analysis.analysis_status = error` |

### GET `/api/tasks`

获取历史任务列表，按 `started_at` 倒序返回。

#### 查询参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `limit` | integer | `100` | 返回条数上限。当前未额外限制范围，建议调用方传入合理值。 |

#### 请求示例

```http
GET /api/tasks?limit=20
```

#### 成功响应

`200 OK`，返回 `TaskResult[]`。

### GET `/api/tasks/{task_id}`

获取单个历史任务。

#### 路径参数

| 参数 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID。 |

#### 成功响应

`200 OK`，返回 `TaskResult`。

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `task_not_found` | 任务不存在。 |

## 8. 报告接口

### GET `/api/reports/{task_id}`

下载某次评测生成的 Markdown 报告。

#### 路径参数

| 参数 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID。 |

#### 成功响应

- 状态码：`200 OK`
- `Content-Type`: `text/markdown; charset=utf-8`
- 文件名：`{task_id}.md`

#### 错误

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `report_not_found` | 任务不存在、任务无报告路径或报告文件不存在。 |

## 9. 报告分析模型配置

当前没有专门的 API 管理 `analysis_model_id`；它保存在 `data/models.json` 顶层。示例：

```json
{
  "analysis_model_id": "report-analyzer",
  "models": [
    {
      "id": "report-analyzer",
      "name": "报告分析模型",
      "protocol": "chat_completions",
      "base_url": "https://analysis.example.com/v1",
      "api_key": "<your-api-key>",
      "model": "report-analysis-model",
      "timeout_seconds": 60,
      "enabled": true,
      "declared_context_tokens": null,
      "declared_max_output_tokens": null,
      "concurrency_levels": [1]
    }
  ]
}
```

行为说明：

- `analysis_model_id` 未配置：评测正常完成，报告显示分析跳过。
- 分析模型不存在：评测正常完成，报告显示分析错误。
- 分析模型调用异常、返回非成功响应、返回非 JSON、字段校验失败：评测正常完成，报告显示分析错误。
- 报告分析只生成辅助摘要，不改变指标和任务原始事实。

## 10. 智力评测接口（EvalScope）

智力评测用于调用 EvalScope Python package 执行公开数据集能力测试。当前执行模式为 `in_process`：主服务直接 `import evalscope` 并调用 `evalscope.run_task(TaskConfig)`，不再代理到外部 EvalScope HTTP 包装服务。`data/evalscope.json` 是可选覆盖文件；默认不创建也会使用 `data/evalscope_datasets` 和 `outputs/evalscope`。代码执行类数据集（`humaneval`、`humaneval_plus`、`mbpp`、`mbpp_plus`、`live_code_bench`）需要配置 EvalScope sandbox 才能评分；未配置时会在任务执行阶段返回 `sandbox_required:<dataset>`，避免只生成预测却没有分数。FastAPI 主服务启动时不会在 `app.main` 中自动启动 sandbox；必须提前独立启动 `ms-enclave server` 或其他 EvalScope sandbox manager，或在同机验证时使用 `scripts/start_all.*` 的显式 sandbox 选项。

### 10.0 可选 sandbox 配置

远程 sandbox 推荐配置示例。该配置只告诉主服务连接哪个 sandbox manager；不会让 FastAPI 主服务自动拉起 sandbox 进程：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope",
  "sandbox_enabled": true,
  "sandbox_type": "docker",
  "sandbox_manager_config": {
    "base_url": "http://sandbox-host:1234"
  }
}
```

`base_url` 指向已经独立运行的 `ms-enclave server --host 0.0.0.0 --port 1234` 内网地址。该配置不保存模型密钥；模型和 Judge 密钥仍只来自 `data/models.json` 的模型配置。服务端读取 `sandbox_enabled`、`sandbox_type`、`sandbox_manager_config` 以兼容已有本地配置，构造 EvalScope `TaskConfig` 时会转换为官方推荐的 `sandbox={"enabled": true, "engine": "docker", "manager_config": {...}}`。

### 10.1 辅助查询接口

#### GET `/api/intelligence/evalscope/health`

检查当前 Python 环境是否可 import EvalScope。成功示例：

```json
{
  "status": "ok",
  "mode": "in_process",
  "evalscope_version": "1.10.0"
}
```

EvalScope 未安装或导入失败时返回 `502 evalscope_error`。

#### GET `/api/intelligence/evalscope/judge-config`

检查本地 Judge 配置是否完整。默认 Judge 来自 `data/models.json` 顶层 `analysis_model_id`；可选 `data/evalscope.json` 只允许用 `judge_model_config_id` 覆盖模型配置 ID。响应不会返回 API Key 明文。

#### GET `/api/intelligence/evalscope/tasks`

兼容旧入口，返回本系统本地归档的智力评测任务列表，响应包含 `mode: in_process`。

#### GET `/api/intelligence/datasets`

列出本系统内置的 EvalScope 数据集元数据和默认数据集组合。注意：该接口表示“支持”，不代表本地已下载。

#### GET `/api/intelligence/datasets/local`

扫描可选 `data/evalscope.json` 中的 `datasets_dir`，未配置时扫描默认 `data/evalscope_datasets`，列出本地已下载、可直接评测的数据集。自定义评测前建议先调用该接口确认数据集可用。

### 10.2 IntelligenceDefaultRunRequest

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `model_id` | string | 是 | 本系统 `data/models.json` 中的模型配置 ID。 |

### 10.3 IntelligenceRunRequest

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `model_id` | string | 是 | 本系统模型配置 ID。 |
| `datasets` | string[] | 是 | EvalScope 数据集 ID，例如 `gsm8k`、`humaneval`。 |
| `limit` | integer/null | 否 | 每个数据集采样数量；为空时由 EvalScope 执行默认/全量逻辑。 |
| `eval_batch_size` | integer/null | 否 | EvalScope 并发评测批量大小。 |
| `generation_config` | object/null | 否 | 传给 EvalScope 的生成参数，例如 `temperature`、`max_tokens`。 |

### 10.4 IntelligenceTask

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 本系统智力评测任务 ID，例如 `intel_task_yyyymmddhhmmss_xxxxxxxx`。 |
| `evalscope_task_id` | string/null | 兼容字段；当前通常等于本系统任务 ID 或 EvalScope 原始结果中的任务 ID。 |
| `model_id` | string | 本系统模型配置 ID。 |
| `model_config_name` | string/null | 模型配置名称。 |
| `upstream_model_name` | string/null | 传给 EvalScope 的被测模型名，来自 `ModelConfig.model`。 |
| `evalscope_base_url` | string | 兼容字段；当前固定为 `in-process`，表示主服务内直接调用 EvalScope。 |
| `datasets` | string[] | 本次评测数据集。 |
| `status` | string | `pending`、`running`、`completed`、`failed`。 |
| `progress` | string/null | 本地进度文本，例如正在执行哪个数据集。 |
| `report_path` | string/null | 本地 Markdown 报告路径。 |
| `normalized_result` | object/null | 标准化后的数据集分数、分类汇总、原始 `report_table` 等。 |
| `error` | object/null | 脱敏后的任务错误。 |

### 10.5 提交默认智力评测

#### POST `/api/intelligence/tasks/default`

提交默认数据集组合。服务会读取模型配置并映射到 EvalScope `TaskConfig`：

| 本系统字段 | EvalScope 字段 |
|---|---|
| `ModelConfig.model` | `model` |
| `ModelConfig.base_url` + `protocol` | `api_url`，自动拼接 `/chat/completions` 或 `/responses` |
| `ModelConfig.api_key` | `api_key`，仅运行时使用，不写入本地任务配置或报告 |
| `analysis_model_id` 指向的模型配置 | 默认 Judge；仅在本次数据集需要 LLM Judge 时传给 EvalScope `judge_model_args` |

请求示例：

```json
{
  "model_id": "demo-chat"
}
```

成功响应：`200 OK`，返回 `IntelligenceTask`。模型不存在返回 `404 model_not_found`；模型禁用返回 `400 model_disabled`；包含 Judge 数据集但没有可用 Judge 时返回 `400 judge_required`；参数错误返回 `400 invalid_intelligence_task_request`。

### 10.6 提交自定义智力评测

#### POST `/api/intelligence/tasks`

提交指定数据集的 EvalScope 评测。

请求示例：

```json
{
  "model_id": "demo-chat",
  "datasets": ["gsm8k", "humaneval"],
  "limit": 100,
  "eval_batch_size": 10,
  "generation_config": {
    "temperature": 0.0,
    "max_tokens": 8192
  }
}
```

成功响应：`200 OK`，返回 `IntelligenceTask`。若 `datasets` 包含 `simple_qa`、`alpaca_eval`、`arena_hard` 等需要 LLM Judge 的数据集，服务会先解析默认 Judge；没有可用 Judge 时返回 `400 judge_required`，不会启动 EvalScope。

### 10.7 查询本地智力评测任务

#### GET `/api/intelligence/tasks`

列出本系统保存的智力评测任务，按创建时间和任务 ID 倒序排列。查询参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `limit` | integer | `50` | 最大返回数量。 |

#### GET `/api/intelligence/tasks/{task_id}`

读取本地任务。任务不存在返回 `404 intelligence_task_not_found`。

#### GET `/api/intelligence/tasks/{task_id}/result`

读取本地任务结果。若任务已结束但报告尚未生成，服务会补写 Markdown 报告并返回更新后的 `IntelligenceTask`。

### 10.8 下载智力评测报告

#### GET `/api/intelligence/reports/{task_id}`

下载智力评测 Markdown 报告。报告包含“一眼看懂”、任务概览、Judge 状态提示、数据集分数表、能力维度汇总、EvalScope 原始 `report_table` 和脱敏 JSON 附录。

错误：

| 状态码 | `error.code` | 场景 |
|---|---|---|
| `404` | `intelligence_report_not_found` | 任务不存在、任务还未生成报告或报告文件不存在。 |

## 11. EvalScope 压测接口（Stress）

压测能力用于把本系统的模型配置交给 EvalScope `perf` 执行，当前执行模式同样为 `in_process`：主服务直接构造 `evalscope.perf.arguments.Arguments` 并调用 `evalscope.perf.main.run_perf_benchmark`。本系统负责任务编排、本地 JSON 落库、结果标准化和 Markdown 报告生成；正式并发、吞吐、延迟分位数和限流/容量边界以该接口为准。基础 `/api/tasks/run` 中的 `latency_breakdown` 只是单次链路 smoke，`concurrency` 与 `rate_limit` 仅作为显式兼容 smoke 指标保留。

> 配置位置：通常不需要 `data/evalscope.json`；目录默认值足够时直接运行。Judge 默认使用 `data/models.json` 顶层 `analysis_model_id` 指向的模型；如需覆盖，只在 `data/evalscope.json` 写 `judge_model_config_id`，不要在该文件保存 Judge 地址或密钥。

### 11.1 StressDefaultRunRequest / StressRunRequest

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---:|---|
| `model_id` | string | 是 | - | 本系统模型配置 ID。 |
| `parallel` | integer[]/null | 否 | `[1, 5, 10]` | EvalScope 并发档位。 |
| `number` | integer[]/null | 否 | `[10, 50, 100]` | 每个并发档位请求数。 |
| `rate` | number[]/null | 否 | `null` | 限速档位，传给 EvalScope。 |
| `dataset` | string/null | 否 | `null` | EvalScope perf 数据集。为空时走 `StressRemoteSubmitPayload` 默认 `longalpaca`。 |
| `dataset_path` | string/null | 否 | `null` | EvalScope perf 数据集路径。命中 `longalpaca` 等会从 ModelScope 下载的数据集、且 `data/stress_datasets/` 下有同名目录或 `<name>.json` 时自动补齐，使 EvalScope 改为本地加载，避免每次评测联网下载。 |
| `dataset_args` | object/null | 否 | `{}` | 数据集参数，例如自定义 prompt 文件。 |
| `min_prompt_length` / `max_prompt_length` | integer/null | 否 | `0` / `131072` | prompt 长度过滤范围，对齐 EvalScope 官方默认。`tokenizer_path` 为空时按字符长度过滤；`max_prompt_length=131072` 超出即丢弃。 |
| `min_tokens` / `max_tokens` | integer/null | 否 | `512` | 输出 token 范围。 |
| `stream` | boolean/null | 否 | `true` | 是否使用流式请求；TTFT 统计通常要求开启。 |
| `tokenizer_path` | string/null | 否 | `null` | EvalScope tokenizer 路径。为空时按字符长度过滤，适配 longalpaca 这类真实长文本语料。 |
| `prefix_length` | integer/null | 否 | `0` | 前缀长度，用于后续缓存/前缀压测。 |
| `extra_args` | object/null | 否 | `{}` | 透传给 EvalScope perf 的扩展参数。 |

`POST /api/stress/tasks` 当前与默认入口使用同一请求结构，便于后续扩展。

### 11.2 StressTask

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 本系统压测任务 ID。 |
| `evalscope_stress_task_id` | string/null | 兼容字段；当前通常等于本系统任务 ID。 |
| `model_id` | string | 本系统模型配置 ID。 |
| `model_config_name` | string/null | 模型配置名称。 |
| `upstream_model_name` | string/null | 传给上游模型服务的 `model` 名称。 |
| `protocol` | string/null | `chat_completions` 或 `responses`。 |
| `evalscope_base_url` | string | 兼容字段；当前固定为 `in-process`。 |
| `status` | string | `pending`、`running`、`completed`、`failed`。 |
| `request_config` | object | 已脱敏的压测请求配置，不包含 `api_key`。 |
| `normalized_result` | object/null | 标准化后的并发档位结果、吞吐、延迟、TTFT/TPOT 和异常摘要。 |
| `report_path` | string/null | 本地 Markdown 压测报告路径。 |
| `error` | object/null | 脱敏后的错误。 |

### 11.3 本系统压测接口

#### GET `/api/stress/evalscope/health`

检查当前 Python 环境是否可 import EvalScope。成功时返回 `status`、`mode` 和 `evalscope_version`。EvalScope 不可用时返回 `502 evalscope_stress_error`。

#### POST `/api/stress/tasks/default`

按默认压测参数提交任务。服务会读取模型配置并映射：

| 本系统字段 | EvalScope perf 字段 |
|---|---|
| `ModelConfig.model` | `model` |
| `ModelConfig.base_url` + `protocol` | `url`，自动拼接 `/chat/completions` 或 `/responses` |
| `ModelConfig.protocol` | `api`，映射为 `openai` 或 `openai_responses` |
| `ModelConfig.api_key` | `api_key`，只在运行时传给 EvalScope，不落本地任务配置 |

请求示例：

```json
{
  "model_id": "demo-chat",
  "parallel": [1, 5],
  "number": [10, 50],
  "stream": true,
  "max_tokens": 512
}
```

> 不传 `dataset` 时默认使用 `longalpaca`（已离线落盘到 `data/stress_datasets/longalpaca.json`，runner 自动补齐 `dataset_path` 指向本地文件），并采用 EvalScope 官方默认的长度过滤（`min_prompt_length=0`、`max_prompt_length=131072`、`tokenizer_path=null`）。如需按 token 长度随机生成 prompt，显式传 `"dataset": "random"` 并设置 `min_prompt_length` / `max_prompt_length` / `tokenizer_path`。

成功响应：`200 OK`，返回 `StressTask`。模型不存在返回 `404 model_not_found`；模型禁用返回 `400 model_disabled`；参数错误返回 `400 invalid_stress_task_request`。

#### POST `/api/stress/tasks`

提交自定义压测任务。当前字段同 `StressDefaultRunRequest`，用于显式传入 `parallel`、`number`、`rate`、`prefix_length`、`dataset_args` 等参数。

#### GET `/api/stress/tasks`

读取本地压测任务列表，不触发新的 EvalScope 调用。可选 query 参数：`limit`，默认 `50`。

#### GET `/api/stress/tasks/{task_id}`

读取本地任务。任务不存在返回 `404 stress_task_not_found`。

#### GET `/api/stress/tasks/{task_id}/result`

获取压测结果。若任务已结束但报告尚未生成，服务会补写 Markdown 报告并返回更新后的 `StressTask`。

#### GET `/api/stress/reports/{task_id}`

下载本地 Markdown 压测报告。报告尚未生成或文件不存在时返回 `404 stress_report_not_found`。

## 12. 统一总览报告接口（Overview）

统一总览报告用于把已有的网关接入验收任务、EvalScope 压测任务和 EvalScope 能力评测任务组合成一份中文 Markdown 导航摘要（章节顺序与 suite 执行顺序一致：网关 → 压测 → 能力评测）。本接口不自动触发新的评测任务，也不重做 EvalScope 可视化；它只负责汇总状态、关键指标、风险提示和三类详情报告入口。

### 12.1 OverviewReportRequest

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---:|---|
| `model_id` | string/null | 否 | 自动推断 | 模型配置 ID；为空时从已提供任务中按网关、能力、压测顺序推断。 |
| `gateway_task_id` | string/null | 否 | `null` | `/api/tasks/run` 生成的网关接入验收任务 ID。 |
| `intelligence_task_id` | string/null | 否 | `null` | `/api/intelligence/*` 生成的能力评测任务 ID。 |
| `stress_task_id` | string/null | 否 | `null` | `/api/stress/*` 生成的压测任务 ID。 |
| `title` | string/null | 否 | `模型评测总览报告` | Markdown 报告标题。 |

至少需要提供一个任务 ID。第一版允许只生成部分总览；未提供的模块会在报告中显示为“未提供”。

### 12.2 OverviewReport

| 字段 | 类型 | 说明 |
|---|---:|---|
| `overview_id` | string | 总览报告 ID，例如 `overview_report_yyyymmddhhmmss_xxxxxxxx`。 |
| `title` | string | 报告标题。 |
| `model_id` | string/null | 模型配置 ID。 |
| `created_at` | string | 创建时间。 |
| `gateway_task_id` / `intelligence_task_id` / `stress_task_id` | string/null | 三类被引用任务 ID。 |
| `components` | object[] | 三类模块摘要，包括状态、摘要、详情入口、关键观测和关注点。 |
| `summary` | object | 已提供模块数、完成模块数、关注点数量等总览统计。 |
| `report_path` | string/null | 本地 Markdown 总览报告路径。 |

### 12.3 创建总览报告

#### POST `/api/overview/reports`

请求示例：

```json
{
  "gateway_task_id": "task_20260806120000_aaaaaaaa",
  "intelligence_task_id": "intel_task_20260806121000_bbbbbbbb",
  "stress_task_id": "stress_task_20260806122000_cccccccc"
}
```

成功响应：`200 OK`，返回 `OverviewReport`，并写入本地 `data/overview_reports/` 和 `reports/overview/YYYY-MM-DD/`。

### 12.4 查询总览报告列表

#### GET `/api/overview/reports`

读取本地总览报告列表。可选 query 参数：`limit`，默认 `50`。

### 12.5 查询总览报告元数据

#### GET `/api/overview/reports/{overview_id}`

返回已生成的 `OverviewReport` 元数据。不存在时返回 `404 overview_report_not_found`。

### 12.6 下载总览 Markdown

#### GET `/api/overview/reports/{overview_id}/markdown`

下载统一总览 Markdown 报告。报告包含“一眼看懂”、模型与任务信息、网关接入验收摘要、EvalScope 压测摘要、EvalScope 能力评测摘要和详细报告入口（章节顺序与 suite 执行顺序一致：网关 → 压测 → 能力评测）。报告不存在或文件丢失时返回 `404 overview_report_not_found`。

## 13. 一键评测套件接口（Suites）

### 13.0 查询 EvalScope 评测 profiles

#### GET `/api/evalscope/profiles`

路由签名：GET `/api/evalscope/profiles`

返回服务内置和本地覆盖的 EvalScope 评测 profile。profile 用于给定时评测提供一组稳定默认值，减少调用方每次手写数据集、压测档位和样本上限。

内置 profile：

| profile | 说明 | 是否需要 sandbox |
|---|---|---:|
| `scheduled_light` | 默认定时轻量评测；包含网关 smoke、轻量压测、非代码类能力评测。默认数据集为 `gsm8k`、`math_500`、`ceval`，默认 `intelligence_limit=50`。 | 否 |
| `scheduled_code` | 代码能力定时评测；默认数据集为 `humaneval`、`mbpp`。 | 是 |
| `full_offline` | 人工触发的较完整离线 profile，包含代码类和非代码类数据集。 | 是 |

如果需要自定义，可在本地 `data/evalscope_profiles.json` 中增加同名或新 profile。该文件属于运行配置，不应提交 Git。

Suites 是“一键评测模型并出报告”的编排层。它复用已有三类能力，执行顺序为：先执行网关接入验收 smoke，再提交 EvalScope 压测，最后提交 EvalScope 能力评测，全部完成后自动生成统一总览报告（总览章节顺序与之保持一致：网关 → 压测 → 能力评测）。先跑压测是为了在长时能力评测之前先拿到性能数据，避免能力评测卡死整条 suite 时丢失性能结果。Suites 不新增评测指标，也不重造 EvalScope 可视化，只负责串联、等待终态、归档 suite 状态和生成 overview 入口。已有模型配置时使用 `POST /api/suites/default`；临时外部模型可使用 `POST /api/suites/quick` 直接传 `url`、`key`、`model`。

### 13.1 SuiteDefaultRunRequest

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---:|---|
| `model_id` | string | 是 | - | 要评测的模型配置 ID。 |
| `title` | string/null | 否 | `null` | 总览报告标题；为空时使用默认标题。 |
| `run_gateway` | boolean | 否 | `true` | 是否执行网关接入验收。 |
| `run_intelligence` | boolean | 否 | `true` | 是否执行 EvalScope 能力评测。 |
| `run_stress` | boolean | 否 | `true` | 是否执行 EvalScope 压测。 |
| `gateway_plan_id` | string | 否 | `gateway_acceptance_v1` | 网关验收计划。 |
| `gateway_metric_ids` | string[]/null | 否 | `null` | 显式指定网关验收指标；为空时按计划默认指标执行。 |
| `stress_options` | object | 否 | `{}` | 压测参数子集，例如 `parallel`、`number`、`rate`、`prefix_length`、`dataset_args`。 |
| `intelligence_limit` | integer/null | 否 | `null` | 能力评测每个数据集取前 N 条样本截断；`null` 表示不限制（全量评测）。手动发起的 default 评测默认不限；需精确分数时不传即可。 |
| `wait_for_completion` | boolean | 否 | `false` | `false` 时后台运行并立即返回 suite；`true` 时接口等待整套评测完成后返回。 |
| `poll_interval_seconds` | number/null | 否 | runner 默认值 | 等待 EvalScope 任务终态时的轮询间隔。 |
| `timeout_seconds` | number/null | 否 | `null` | 单个 EvalScope 等待阶段的超时时间。 |

至少需要启用一个模块。默认请求会执行三类评测；如果只想半夜跑压测，可以把 `run_gateway`、`run_intelligence` 设为 `false`。

### 13.2 SuiteRun

| 字段 | 类型 | 说明 |
|---|---:|---|
| `suite_id` | string | 一键评测套件 ID，例如 `suite_yyyymmddhhmmss_xxxxxxxx`。 |
| `model_id` | string | 模型配置 ID。 |
| `status` | string | `queued`、`running`、`completed`、`partial`、`failed`。 |
| `current_step` | string/null | 当前执行步骤，按执行顺序为：`gateway`、`stress`、`intelligence`、`overview`。 |
| `gateway_task_id` / `intelligence_task_id` / `stress_task_id` | string/null | 三类子任务 ID。 |
| `overview_id` | string/null | 自动生成的统一总览报告 ID。 |
| `overview_report_path` | string/null | 总览 Markdown 本地路径。 |
| `steps` | object[] | 每个步骤的状态、任务 ID、开始/完成时间和消息。 |
| `errors` | object[] | 步骤异常摘要，写入前会脱敏。 |

### 13.3 立即启动一键评测

#### POST `/api/suites/default`

后台运行示例：

```json
{
  "model_id": "demo-chat",
  "stress_options": {
    "parallel": [1, 5],
    "number": [10, 50]
  }
}
```

脚本同步等待示例：

```json
{
  "model_id": "demo-chat",
  "wait_for_completion": true,
  "poll_interval_seconds": 10,
  "timeout_seconds": 86400,
  "stress_options": {
    "parallel": [1, 5],
    "number": [10, 50]
  }
}
```

成功响应：`200 OK`，返回 `SuiteRun`。后台模式初始状态通常为 `queued`，随后可通过 `GET /api/suites/{suite_id}` 查询进度。

### 13.4 临时模型一键评测

#### POST `/api/suites/quick`

调用方不需要先创建模型配置，直接传 OpenAI 兼容服务地址、密钥和上游模型名即可启动 suite。服务会为本次请求生成 `inline_*` 临时模型 ID，并用进程内临时模型存储驱动网关 smoke、EvalScope 能力评测和 EvalScope 压测；不会写入 `data/models.json`，也不会把传入的 `key`/`api_key` 持久化到 suite JSON 或报告中。

请求字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---:|---|
| `url` / `base_url` | string | 是 | - | OpenAI 兼容基础地址，例如 `http://127.0.0.1:9001/v1`。也可传完整 `/chat/completions` 或 `/responses` 端点，服务会按 `protocol` 去掉末尾接口路径。 |
| `key` / `api_key` | string | 否 | `""` | 上游 API Key。无鉴权网关可以留空；响应、suite 文件和报告不会保存明文。 |
| `model` | string | 是 | - | 上游模型名。 |
| `name` | string/null | 否 | `null` | 临时模型展示名；为空时使用 `临时模型 <model>`。 |
| `protocol` | string | 否 | `chat_completions` | `chat_completions` 或 `responses`。 |
| `timeout_seconds` | integer | 否 | `60` | 单次上游请求超时时间，传给临时 `ModelConfig`。 |
| `context_window_tokens` / `declared_context_tokens` / `context_window` / `max_context_tokens` | integer/null | 建议 | `null` | 模型上下文窗口大小。用于网关 smoke 的 `context_length`；不传时该指标会跳过。 |
| `max_output_tokens` / `declared_max_output_tokens` | integer/null | 建议 | `null` | 模型最大输出长度。用于 `output_length`；不传时按默认 1024 tokens 观察。 |
| `concurrency_levels` | integer[] | 否 | `[1,5,10,20]` | 网关 smoke 兼容并发档位声明。 |
| `title`、`run_gateway`、`run_intelligence`、`run_stress`、`gateway_plan_id`、`gateway_metric_ids`、`stress_options`、`intelligence_limit`、`wait_for_completion`、`poll_interval_seconds` | - | 否 | 同 `SuiteDefaultRunRequest` | 与默认 suite 语义一致；`intelligence_limit` 默认 `null` 不限制。 |
| `timeout_seconds_total` | number/null | 否 | `null` | suite 等待 EvalScope 能力评测/压测终态的超时时间；对应默认 suite 的 `timeout_seconds`。 |

请求示例：

```json
{
  "url": "http://127.0.0.1:9001/v1",
  "key": "<your-api-key>",
  "model": "demo-model",
  "context_window_tokens": 8192,
  "max_output_tokens": 1024,
  "title": "demo-model quick benchmark",
  "stress_options": {
    "parallel": [1, 5],
    "number": [10, 50]
  }
}
```

如果调用方希望同步等待整套评测结束，可以设置：

```json
{
  "url": "http://127.0.0.1:9001/v1/chat/completions",
  "api_key": "<your-api-key>",
  "model": "demo-model",
  "context_window_tokens": 8192,
  "max_output_tokens": 1024,
  "wait_for_completion": true,
  "poll_interval_seconds": 10,
  "timeout_seconds_total": 86400
}
```

成功响应：`200 OK`，返回 `SuiteRun`，其中 `model_id` 形如 `inline_yyyymmddhhmmss_xxxxxxxx`。后台模式依赖当前服务进程内的临时模型配置；如果进程在任务完成前重启，临时密钥不会被恢复，应重新提交 quick suite。

### 13.5 查询 suite 列表

#### GET `/api/suites`

读取本地 suite 列表。可选 query 参数：`limit`，默认 `50`。

### 13.6 查询 suite 详情

#### GET `/api/suites/{suite_id}`

返回 suite 元数据、步骤状态、三类子任务 ID 和 overview ID。不存在时返回 `404 suite_not_found`。

### 13.7 下载 suite 总览报告

#### GET `/api/suites/{suite_id}/report`

下载 suite 自动生成的 overview Markdown。suite 尚未完成、没有生成 overview 或文件丢失时返回 `404 suite_report_not_found`。

### 13.8 创建定时评测计划

#### POST `/api/suites/schedules`

定时计划保存在本地 `data/suite_schedules/`。服务启动后内置轻量轮询器会检查 `next_run_at`，到点后异步投递 `SuiteDefaultRunRequest`，调度循环不会等待整套评测完成。适合半夜低峰期执行模型评测。`run_once=true` 表示只执行一次，触发后计划会自动停用；周期任务使用 `interval_days` 控制重复间隔。

只执行一次请求示例：

```json
{
  "name": "tonight-demo-chat",
  "model_id": "demo-chat",
  "profile": "scheduled_light",
  "run_once": true,
  "run_date": "2026-08-08",
  "time_of_day": "00:00",
  "timezone": "Asia/Shanghai",
  "stress_parallel": [1, 5],
  "stress_number": [10, 50]
}
```

周期执行请求示例：

```json
{
  "name": "nightly-demo-chat",
  "model_id": "demo-chat",
  "profile": "scheduled_light",
  "run_once": false,
  "time_of_day": "02:00",
  "timezone": "Asia/Shanghai",
  "interval_days": 1,
  "stress_parallel": [1, 5],
  "stress_number": [10, 50]
}
```

关键字段：

| 字段 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `name` | string | - | 计划名称。 |
| `model_id` | string | - | 要评测的模型配置 ID。 |
| `profile` | string/null | `scheduled_light` | 定时评测 profile。默认 `scheduled_light` 不依赖 sandbox；`scheduled_code` 和 `full_offline` 需要 `data/evalscope.json` 启用 sandbox。传 `null` 可跳过 profile，仅使用请求字段和代码兜底默认值。 |
| `enabled` | boolean | `true` | 是否启用。 |
| `time_of_day` | string | `02:00` | 每次触发的本地时间，格式 `HH:MM`。 |
| `timezone` | string | `Asia/Shanghai` | 计算 `next_run_at` 使用的时区。 |
| `interval_days` | integer | `1` | 周期任务每隔多少天运行一次；`run_once=true` 时不会用于重复。 |
| `run_once` | boolean | `false` | 是否只执行一次。为 `true` 时到点执行后自动停用计划。 |
| `run_date` | date/null | `null` | 一次性任务的执行日期，格式 `YYYY-MM-DD`；和 `time_of_day`、`timezone` 一起计算 `next_run_at`。 |
| `next_run_at` | datetime/null | 自动计算 | 可显式指定下一次 UTC 触发时间，便于测试或临时调度；一次性任务也可直接传它。 |
| `stress_parallel` / `stress_number` | integer[]/null | `null` | 常用压测参数快捷字段。 |
| `stress_options` | object | `{}` | 更完整的压测参数。 |
| `run_gateway` / `run_intelligence` / `run_stress` | boolean | `true` | 触发时是否执行对应阶段。 |
| `gateway_plan_id` / `gateway_metric_ids` | string / string[]/null | `gateway_acceptance_v1` / `null` | 网关验收计划与指标。 |
| `intelligence_datasets` | string[]/null | profile 决定 | 能力评测数据集列表。`scheduled_light` 默认为 `gsm8k`、`math_500`、`ceval`，不包含代码执行类数据集。 |
| `intelligence_limit` | integer/null | profile 决定 | 能力评测每个数据集取前 N 条样本截断。`scheduled_light` 默认为 `50`；不使用 profile 且未显式传值时回退为 `200`（对应常量 `DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT`）。手动 `POST /api/suites/default` 不受此默认值约束。 |
| `intelligence_eval_batch_size` / `intelligence_generation_config` | integer/null / object/null | profile 决定 | profile 或请求可指定能力评测并发与生成参数，最终透传给 EvalScope。 |
| `poll_interval_seconds` / `timeout_seconds` | number/null | `null` | suite 内部等待 EvalScope 子任务终态的轮询间隔与超时。定时调度器自身始终异步投递，不会因该字段阻塞。 |

### 13.9 查询定时计划列表

#### GET `/api/suites/schedules`

读取本地定时计划列表。可选 query 参数：`limit`，默认 `50`。

### 13.10 查询定时计划详情

#### GET `/api/suites/schedules/{schedule_id}`

返回定时计划、下一次运行时间、最近一次 suite ID、运行次数和最近调度错误。`last_error` 只表示调度投递阶段错误；如果最近一次 suite 执行失败，应继续查询 last-run 或 suite 详情。不存在时返回 `404 suite_schedule_not_found`。

### 13.11 查询定时计划最近一次执行

#### GET `/api/suites/schedules/{schedule_id}/last-run`

返回定时计划和最近一次 suite 的合并诊断视图。适合排查“计划已触发但评测失败”的情况。

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `schedule` | object | `SuiteSchedule` 原始计划。 |
| `suite` | object/null | `last_suite_id` 对应的 `SuiteRun`；尚未触发时为 `null`。 |
| `last_suite_status` | string/null | 最近 suite 的状态：`queued`、`running`、`completed`、`partial`、`failed`。 |
| `last_suite_current_step` | string/null | 最近 suite 当前步骤。 |
| `last_suite_error_count` | integer | 最近 suite 的错误数量；尚未触发时为 `0`。 |
| `last_suite_errors` | object[] | 最近 suite 的错误摘要。 |

示例：

```json
{
  "schedule": {"schedule_id": "suite_schedule_20260807154500_ab12cd34", "last_suite_id": "suite_20260808000000_ab12cd34"},
  "suite": {"suite_id": "suite_20260808000000_ab12cd34", "status": "partial"},
  "last_suite_status": "partial",
  "last_suite_current_step": null,
  "last_suite_error_count": 1,
  "last_suite_errors": [{"step": "stress", "message": "stress task failed"}]
}
```

### 13.12 删除定时计划

#### DELETE `/api/suites/schedules/{schedule_id}`

删除本地定时计划。不存在时返回 `404 suite_schedule_not_found`。

### 13.13 手动触发定时计划

#### POST `/api/suites/schedules/{schedule_id}/trigger`

立即按该定时计划保存的请求启动一次 suite。可选 query 参数：`wait_for_completion`，默认 `false`。返回新建的 `SuiteRun`。如果手动触发的是 `run_once=true` 的一次性计划，该计划也会被自动停用，避免后续重复执行。
## 14. OpenAI 兼容协议说明

模型配置中的 `protocol` 决定上游调用风格：

| `protocol` | 上游路径 | 请求要点 | 响应解析 |
|---|---|---|---|
| `chat_completions` | `{base_url}/chat/completions` | `model`、`messages`、`temperature`、`stream`、可选 `max_tokens`。 | 读取 `choices[0].message.content` 或 `reasoning_content`、`finish_reason`、`usage`。 |
| `responses` | `{base_url}/responses` | `model`、`input`、`temperature`、`stream`、可选 `max_output_tokens`。 | 读取 `output_text`，或从 `output[].content[]` 拼接文本，读取 `usage`。 |

## 15. PowerShell 调用示例

### 创建模型

```powershell
$body = @{
  id = 'demo-chat'
  name = 'Demo Chat'
  protocol = 'chat_completions'
  base_url = 'http://127.0.0.1:9001/v1'
  api_key = '<your-api-key>'
  model = 'demo-model'
  timeout_seconds = 60
  enabled = $true
  declared_context_tokens = 8192
  declared_max_output_tokens = 1024
  concurrency_levels = @(1, 2)
} | ConvertTo-Json

Invoke-RestMethod -Uri 'http://127.0.0.1:8020/api/models' `
  -Method Post `
  -ContentType 'application/json' `
  -Body $body | ConvertTo-Json -Depth 10
```

### 执行评测并下载报告

```powershell
$runBody = @{ model_id = 'demo-chat'; plan_id = 'gateway_acceptance_v1' } | ConvertTo-Json
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8020/api/tasks/run' `
  -Method Post `
  -ContentType 'application/json' `
  -Body $runBody

$result | ConvertTo-Json -Depth 20
$taskId = $result.task_id
Invoke-WebRequest -Uri "http://127.0.0.1:8020/api/reports/$taskId" -OutFile "$taskId.md"
```


### 一键评测并下载总览报告

```powershell
$suiteBody = @{
  model_id = 'demo-chat'
  wait_for_completion = $true
  poll_interval_seconds = 10
  timeout_seconds = 86400
  stress_options = @{
    parallel = @(1, 5)
    number = @(10, 50)
  }
} | ConvertTo-Json -Depth 10
$suite = Invoke-RestMethod -Uri 'http://127.0.0.1:8020/api/suites/default' -Method Post -ContentType 'application/json' -Body $suiteBody
Invoke-WebRequest -Uri "http://127.0.0.1:8020/api/suites/$($suite.suite_id)/report" -OutFile "suite-overview.md"
```

### 创建半夜定时评测计划

```powershell
$scheduleBody = @{
  name = 'nightly-demo-chat'
  model_id = 'demo-chat'
  run_once = $false
  time_of_day = '02:00'
  timezone = 'Asia/Shanghai'
  interval_days = 1
  stress_parallel = @(1, 5)
  stress_number = @(10, 50)
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri 'http://127.0.0.1:8020/api/suites/schedules' -Method Post -ContentType 'application/json' -Body $scheduleBody | ConvertTo-Json -Depth 20
```
### 生成统一总览报告

```powershell
$overviewBody = @{
  gateway_task_id = $taskId
  intelligence_task_id = '<intel-task-id>'
  stress_task_id = '<stress-task-id>'
} | ConvertTo-Json
$overview = Invoke-RestMethod -Uri 'http://127.0.0.1:8020/api/overview/reports' -Method Post -ContentType 'application/json' -Body $overviewBody
Invoke-WebRequest -Uri "http://127.0.0.1:8020/api/overview/reports/$($overview.overview_id)/markdown" -OutFile "overview.md"
```
