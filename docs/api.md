# API 接口文档

> 本文档是项目的一部分。后续新增、删除或修改接口时，必须同步更新本文档和 `README.md` 中的文档入口。

## 1. 基本约定

- 服务框架：FastAPI。
- 默认本地地址：`http://127.0.0.1:8000`。
- 所有业务接口前缀：`/api`。
- 当前不做平台鉴权；上游模型 API Key 仅保存在本地 `data/models.json`，不要提交。
- 请求与响应默认使用 JSON；报告下载接口返回 Markdown 文件。
- 时间字段使用 ISO 8601 字符串，通常带 UTC 时区。
- 本服务只采集评测数据和生成报告，不输出“上线通过 / 失败”的自动判定。

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
| `plan_id` | string | 否 | `gateway_baseline_v1` | 评测计划 ID。 |
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
    "id": "gateway_baseline_v1",
    "name": "模型网关基础工程评测 V1",
    "description": "默认基础评测计划：覆盖连通性、延迟、上下文、输出、并发、限流、错误处理、Token 用量和流式规范性。",
    "metric_ids": [
      "connectivity",
      "latency_breakdown",
      "context_length",
      "output_length",
      "concurrency",
      "rate_limit",
      "error_handling",
      "token_usage_accuracy",
      "stream_spec"
    ]
  }
]
```

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
  "plan_id": "gateway_baseline_v1"
}
```

#### 请求示例：只执行部分指标

```json
{
  "model_id": "demo-chat",
  "plan_id": "gateway_baseline_v1",
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

## 10. OpenAI 兼容协议说明

模型配置中的 `protocol` 决定上游调用风格：

| `protocol` | 上游路径 | 请求要点 | 响应解析 |
|---|---|---|---|
| `chat_completions` | `{base_url}/chat/completions` | `model`、`messages`、`temperature`、`stream`、可选 `max_tokens`。 | 读取 `choices[0].message.content` 或 `reasoning_content`、`finish_reason`、`usage`。 |
| `responses` | `{base_url}/responses` | `model`、`input`、`temperature`、`stream`、可选 `max_output_tokens`。 | 读取 `output_text`，或从 `output[].content[]` 拼接文本，读取 `usage`。 |

## 11. PowerShell 调用示例

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

Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/models' `
  -Method Post `
  -ContentType 'application/json' `
  -Body $body | ConvertTo-Json -Depth 10
```

### 执行评测并下载报告

```powershell
$runBody = @{ model_id = 'demo-chat'; plan_id = 'gateway_baseline_v1' } | ConvertTo-Json
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/tasks/run' `
  -Method Post `
  -ContentType 'application/json' `
  -Body $runBody

$result | ConvertTo-Json -Depth 20
$taskId = $result.task_id
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/reports/$taskId" -OutFile "$taskId.md"
```
