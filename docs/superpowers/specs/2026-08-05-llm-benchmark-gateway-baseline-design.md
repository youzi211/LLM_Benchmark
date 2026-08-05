# LLM Benchmark Gateway Baseline V1 Design

## 1. 背景与目标

本项目定位为内部开发人员使用的大模型 API 基础工程评测服务，用于模型接入模型网关前的上线前验证。

它不是普通用户平台，也不是只测连通性的脚本。V1 的目标是把模型 API 的基础工程指标完整测出来，帮助相关人员判断模型是否具备接入模型网关的基础条件。

V1 重点关注：

- 模型 API 是否可用；
- 接口协议是否兼容；
- 非流式和流式响应是否可解析；
- 延迟、上下文窗口、输出长度、并发、限流、错误处理、token usage 是否能被观测；
- 是否能生成结构化 JSON 结果和人可读 Markdown 报告。

后续再扩展：

- P1/P2 更多能力项；
- 公开 Benchmark 智力评测；
- 业务自定义题库评测；
- 前端页面；
- 异步任务；
- 数据库或更完整的平台化能力。

## 2. 已确认技术决策

| 项目 | 决策 |
|---|---|
| Python 环境管理 | uv |
| Web 框架 | FastAPI |
| API 调用层 | httpx 直接请求 |
| OpenAI SDK | V1 不使用 |
| 数据库 | V1 不使用 SQL / SQLite / MySQL / PostgreSQL |
| 配置和结果存储 | 本地 JSON 文件 |
| 报告格式 | Markdown |
| 前端 | V1 不做正式前端 |
| 使用入口 | FastAPI `/docs`、Postman、curl、Markdown 报告 |
| 平台鉴权 | V1 不做 |
| 任务执行 | 同步执行 |
| API Key 存储 | 内网部署前提下，本地配置文件明文保存 |
| API Key 展示 | 接口返回和日志必须脱敏 |

## 3. V1 不做的事情

V1 明确不做以下能力：

1. 不做正式前端页面。
2. 不做数据库和 ORM。
3. 不做平台鉴权。
4. 不做异步任务、任务队列或独立 Worker。
5. 不做复杂阈值上线判定。
6. 不输出“允许上线 / 不允许上线”。
7. 不输出人工验收结论字段、审批人、人工备注。
8. 不使用 OpenAI Python SDK 封装请求。
9. 不支持自定义 endpoint path。

V1 会做基础状态判定，但不写死复杂性能阈值。例如：

- 不写死 `TTFT < 3s`；
- 不写死 `TPS 达到厂商声明值 ±20%`；
- 不写死 `usage 误差 < 5%`；
- 不写死并发档位必须全部成功。

系统负责采集完整基础工程观测数据，并把明确执行异常、协议异常、结构异常标记为 `error`。最终是否上线由相关人员结合报告分析。

## 4. 协议支持

V1 同时支持两类协议：

```text
chat_completions
responses
```

每个模型配置必须显式指定协议：

```json
{
  "protocol": "chat_completions"
}
```

或：

```json
{
  "protocol": "responses"
}
```

地址配置只使用 `base_url`：

```json
{
  "base_url": "https://example.com/v1"
}
```

系统按协议拼接默认路径：

```text
chat_completions -> /chat/completions
responses -> /responses
```

V1 不支持自定义 endpoint path。后续如果遇到非标准内网网关或代理路径，再扩展 `endpoint_path`。

## 5. V1 默认测试计划

V1 默认测试计划命名为：

```text
gateway_baseline_v1
```

含义：模型网关上线前基础工程评测计划。

该计划包含 P0 全部指标，并额外纳入流式规范性 `stream_spec`：

```text
connectivity
latency_breakdown
context_length
output_length
concurrency
rate_limit
error_handling
token_usage_accuracy
stream_spec
```

说明：

- `stream_spec` 在原始指标清单中属于 P1，但模型网关通常会强依赖流式兼容性，因此 V1 默认纳入。
- `non_stream_schema` 不作为顶层指标，而是作为 `connectivity` 的观测项。
- `stream_ttft`、`stream_tps`、`end_to_end_latency` 不作为顶层指标，而是作为 `latency_breakdown` 的观测项。

## 6. 指标目录

### 6.1 V1 已实现指标

| 指标 ID | 来源 | 含义 | 默认纳入 gateway_baseline_v1 |
|---|---|---|---|
| `connectivity` | P0 | 连通性 | 是 |
| `latency_breakdown` | P0 | 延迟拆解，包括 TTFT、TPS、端到端延迟 | 是 |
| `context_length` | P0 | 上下文长度 | 是 |
| `output_length` | P0 | 输出长度上限 | 是 |
| `concurrency` | P0 | 并发承载观测 | 是 |
| `rate_limit` | P0 | 限流行为观测 | 是 |
| `error_handling` | P0 | 错误处理结构 | 是 |
| `token_usage_accuracy` | P0 | Token usage 返回与本地估算 | 是 |
| `stream_spec` | P1 | SSE / 流式响应规范性 | 是 |

### 6.2 后续预留指标

P1 后续指标：

```text
function_calling
json_mode
system_prompt
multi_turn
stability
```

P2 / 按需指标：

```text
content_safety
rate_limit_headers
model_version_stability
prompt_caching
quality_eval
multimodal
cross_region_latency
retry_idempotency
logging_audit
```

后续智力评测计划可独立新增，例如：

```text
intelligence_eval_v1
business_eval_v1
```

并接入：

```text
MMLU
GSM8K
HumanEval
IFEval
BBH
业务自定义题库
```

这些不强行塞进 `gateway_baseline_v1`。

## 7. 状态语义

V1 不使用：

```text
passed
failed
```

V1 使用：

```text
completed
error
skipped
```

### 7.1 completed

表示测试流程正常完成，并采集到观测数据。

示例：

- 成功请求模型；
- 成功解析响应；
- 成功统计 TTFT/TPS；
- 成功记录 usage；
- 成功生成报告。

### 7.2 error

表示出现明确工程异常。

示例：

- 认证失败；
- 请求超时；
- HTTP 请求失败；
- 响应不是合法 JSON；
- 关键字段缺失；
- SSE 完全不可解析；
- usage 缺失；
- 错误体不可结构化解析；
- 并发测试全部连接失败。

### 7.3 skipped

表示本次未执行该指标。

示例：

- 用户未选择该指标；
- 当前协议暂不支持；
- 配置缺少必要参数；
- 指标后续才实现。

## 8. 模块结构

采用独立评测内核 + FastAPI 包装。

建议目录结构：

```text
app/
  __init__.py
  main.py

  api/
    __init__.py
    routes_models.py
    routes_metrics.py
    routes_tasks.py
    routes_reports.py

  core/
    __init__.py
    runner.py
    plans.py
    registry.py
    models.py
    statuses.py

  adapters/
    __init__.py
    base.py
    chat_completions.py
    responses.py

  metrics/
    __init__.py
    base.py
    connectivity.py
    latency.py
    context_length.py
    output_length.py
    concurrency.py
    rate_limit.py
    error_handling.py
    token_usage.py
    stream_spec.py

  storage/
    __init__.py
    model_store.py
    task_store.py
    file_utils.py

  reports/
    __init__.py
    markdown.py

  utils/
    __init__.py
    masking.py
    timing.py
    ids.py
    token_estimator.py
    sse.py
```

核心调用链：

```text
API -> TaskRunner -> Probe/Metric -> Adapter -> Result -> Report
```

API 层只负责接收请求、参数校验、调用评测内核、返回结果。模型请求、指标采集、报告生成都不写死在 FastAPI 路由里。

## 9. 核心对象

### 9.1 ModelConfig

表示一个可测试模型。

```text
ModelConfig
  id: string
  name: string
  protocol: chat_completions | responses
  base_url: string
  api_key: string
  model: string
  timeout_seconds: int
  enabled: bool
  declared_context_tokens: int | null
  declared_max_output_tokens: int | null
  concurrency_levels: list[int]
  created_at: datetime
  updated_at: datetime
```

示例：

```json
{
  "id": "qwen-plus-chat",
  "name": "Qwen Plus Chat",
  "protocol": "chat_completions",
  "base_url": "https://example.com/v1",
  "api_key": "sk-xxx",
  "model": "qwen-plus",
  "timeout_seconds": 60,
  "enabled": true,
  "declared_context_tokens": 128000,
  "declared_max_output_tokens": 8192,
  "concurrency_levels": [1, 5, 10, 20],
  "created_at": "2026-08-05T10:00:00+08:00",
  "updated_at": "2026-08-05T10:00:00+08:00"
}
```

接口返回时 `api_key` 必须脱敏，例如：

```json
{
  "api_key": "sk-****abcd"
}
```

### 9.2 MetricDefinition

表示系统支持的一个指标。

```text
MetricDefinition
  id: string
  name: string
  level: P0 | P1 | P2 | on_demand
  category: string
  description: string
  implemented: bool
  default_in_gateway_baseline: bool
```

### 9.3 TestPlan

表示一组指标集合。

```text
TestPlan
  id: string
  name: string
  description: string
  metric_ids: list[string]
```

V1 默认计划：

```text
gateway_baseline_v1
```

### 9.4 RunTaskRequest

同步运行任务请求。

```text
RunTaskRequest
  model_id: string
  plan_id: string | null
  metric_ids: list[string] | null
```

约束：

- `model_id` 必填；
- `plan_id` 和 `metric_ids` 必须二选一；
- 不允许同时传 `plan_id` 和 `metric_ids`；
- 只允许运行 `implemented=true` 的指标；
- 模型配置 `enabled=false` 时拒绝执行。

### 9.5 TaskResult

表示一次完整测试结果。

```text
TaskResult
  task_id: string
  model_id: string
  model_name: string
  protocol: string
  plan_id: string | null
  metric_ids: list[string]
  status: completed | error
  started_at: datetime
  finished_at: datetime
  duration_ms: int
  summary: object
  results: list[MetricResult]
  report_path: string
```

任务状态：

- `completed`：Runner 正常完成，具体指标可能有 `error`；
- `error`：任务级错误，例如模型不存在、协议不支持、报告生成失败。

### 9.6 MetricResult

表示一个指标的观测结果。

```text
MetricResult
  metric_id: string
  name: string
  level: P0 | P1 | P2 | on_demand
  status: completed | error | skipped
  started_at: datetime
  finished_at: datetime
  duration_ms: int
  observations: object
  errors: list[ErrorObservation]
```

### 9.7 ErrorObservation

```text
ErrorObservation
  stage: request | response_parse | stream_parse | metric_logic
  message: string
  error_type: string
  http_status: int | null
  response_body_excerpt: string | null
```

原则：

- 保存错误摘要；
- 不保存完整 API Key；
- 不保存过长响应；
- 对 Authorization、api_key 做脱敏。

## 10. API 设计

基础前缀：

```http
/api
```

### 10.1 模型配置接口

```http
POST   /api/models
GET    /api/models
GET    /api/models/{model_id}
PUT    /api/models/{model_id}
DELETE /api/models/{model_id}
```

创建模型示例：

```json
{
  "id": "qwen-plus-chat",
  "name": "Qwen Plus Chat",
  "protocol": "chat_completions",
  "base_url": "https://example.com/v1",
  "api_key": "sk-xxx",
  "model": "qwen-plus",
  "timeout_seconds": 60,
  "enabled": true,
  "declared_context_tokens": 128000,
  "declared_max_output_tokens": 8192,
  "concurrency_levels": [1, 5, 10, 20]
}
```

查询模型时 `api_key` 脱敏。

### 10.2 指标和测试计划接口

```http
GET /api/metrics
GET /api/plans
GET /api/plans/{plan_id}
```

### 10.3 测试任务接口

```http
POST /api/tasks/run
GET  /api/tasks
GET  /api/tasks/{task_id}
```

运行默认计划：

```json
{
  "model_id": "qwen-plus-chat",
  "plan_id": "gateway_baseline_v1"
}
```

运行部分指标：

```json
{
  "model_id": "qwen-plus-chat",
  "metric_ids": ["context_length"]
}
```

### 10.4 报告接口

```http
GET /api/reports/{task_id}
```

返回 Markdown 文本，响应类型建议：

```http
text/markdown; charset=utf-8
```

可通过查询参数支持下载：

```http
GET /api/reports/{task_id}?download=true
```

## 11. 文件存储

V1 使用本地文件：

```text
data/
  models.json
  tasks/
    task_xxx.json

reports/
  YYYY-MM-DD/
    task_xxx.md
```

### 11.1 models.json

路径：

```text
data/models.json
```

格式：

```json
{
  "models": [
    {
      "id": "qwen-plus-chat",
      "name": "Qwen Plus Chat",
      "protocol": "chat_completions",
      "base_url": "https://example.com/v1",
      "api_key": "sk-xxx",
      "model": "qwen-plus",
      "timeout_seconds": 60,
      "enabled": true,
      "declared_context_tokens": 128000,
      "declared_max_output_tokens": 8192,
      "concurrency_levels": [1, 5, 10, 20],
      "created_at": "2026-08-05T10:00:00+08:00",
      "updated_at": "2026-08-05T10:00:00+08:00"
    }
  ]
}
```

写入规则：

- 文件不存在时自动创建；
- 写入时使用临时文件 + 原子替换；
- API 响应不返回明文 `api_key`；
- `.gitignore` 应忽略 `data/models.json`。

### 11.2 任务结果文件

路径：

```text
data/tasks/task_20260805_103000_ab12cd.json
```

内容为完整 `TaskResult`。

原则：

- 保存完整结构化观测结果；
- 保存模型配置摘要；
- 不保存完整 API Key；
- 保存错误摘要；
- 保存报告相对路径。

### 11.3 Markdown 报告

路径：

```text
reports/2026-08-05/task_20260805_103000_ab12cd.md
```

报告包含：

- 任务信息；
- 模型信息；
- 指标汇总；
- 连通性；
- 延迟拆解；
- 上下文长度；
- 输出长度；
- 并发与限流；
- 错误处理；
- Token usage；
- 流式规范性；
- 错误摘要。

报告不包含：

- 通过/失败；
- 上线建议；
- 人工结论；
- 审批备注；
- 完整 API Key。

## 12. Probe 与指标映射

V1 内部采用 Probe 复用请求。

```text
non_stream_basic_probe -> connectivity
usage_probe -> token_usage_accuracy
stream_probe -> latency_breakdown + stream_spec
output_probe -> output_length
context_probe -> context_length
error_probe -> error_handling
concurrency_probe -> concurrency + rate_limit
```

推荐执行顺序：

```text
1. connectivity
2. token_usage_accuracy
3. latency_breakdown + stream_spec
4. output_length
5. context_length
6. error_handling
7. concurrency + rate_limit
```

并发与限流放最后，避免影响后续测试。

## 13. 指标测试策略

### 13.1 connectivity

目标：验证模型 API 是否能完成一次基础非流式请求。

默认 prompt：

```text
请用一句话说明大模型 API 验证服务的作用。
```

观测字段：

```text
http_status
latency_ms
response_json_parseable
content_present
content_excerpt
finish_reason
usage_present
```

状态规则：

- `completed`：请求完成，响应可解析，且能提取到内容或有效输出；
- `error`：请求失败、认证失败、超时、JSON 不可解析、无任何有效输出。

### 13.2 latency_breakdown

目标：通过流式请求采集 TTFT、TPS、端到端耗时。

默认 prompt：

```text
请用中文分 5 点简要说明：为什么大模型 API 上线前需要做工程验证。
```

观测字段：

```text
ttft_ms
end_to_end_latency_ms
stream_duration_ms
output_char_count
estimated_output_tokens
tps_estimated
stream_event_count
first_content_at
finished_at
```

TPS 估算：

```text
tps_estimated = estimated_output_tokens / stream_duration_seconds
```

如果流式尾包返回 usage，则展示 `completion_tokens / stream_duration_seconds`，但仍保留估算值。

### 13.3 stream_spec

目标：验证流式响应是否符合网关可解析要求。

可与 `latency_breakdown` 共享同一次流式请求。

观测字段：

```text
sse_parseable
data_line_count
event_count
parse_error_count
done_event_present
finish_reason
finish_reason_present
stream_usage_present
raw_event_excerpt
```

`stream_usage_present=false` 不一定是 `error`，不同厂商支持不一致，V1 只记录。

### 13.4 context_length

目标：验证模型声明的上下文窗口在不同输入规模下是否真实可用，并观察接近上限时的行为。

依赖模型配置：

```text
declared_context_tokens
```

测试点根据声明上下文自动生成：

| declared_context_tokens | 实际测试点 |
|---:|---|
| 8192 | 4K、8K 附近 |
| 32768 | 4K、32K |
| 128000 | 4K、32K、128K |

Prompt 构造：

- 构造长文本；
- 在尾部插入唯一标记，如 `[CONTEXT_MARKER_7F3A9C]`；
- 最后提问：`请回答上文最后出现的 CONTEXT_MARKER 是什么，只输出标记本身。`

观测字段：

```text
declared_context_tokens
test_points[].target_tokens
test_points[].estimated_prompt_tokens
test_points[].http_status
test_points[].latency_ms
test_points[].marker
test_points[].marker_found_in_answer
test_points[].content_excerpt
test_points[].error
```

状态规则：

- `completed`：各测试点执行完成，结果已记录；
- `error`：所有测试点都请求失败，或配置缺失，或响应完全不可解析。

### 13.5 output_length

目标：观察 `max_tokens` 设置较大时，模型是否能实际生成较长输出，以及结束原因是什么。

依赖模型配置：

```text
declared_max_output_tokens
```

如果没有配置，V1 使用保守默认值 `1024`，并在观测中记录 `used_default_max_tokens=true`。

默认 prompt：

```text
请生成一篇结构化中文说明文，主题是“大模型 API 网关上线前验证”，尽量详细展开，不要提前结束。
```

观测字段：

```text
requested_max_tokens
actual_output_char_count
estimated_output_tokens
finish_reason
usage_completion_tokens
usage_total_tokens
latency_ms
```

### 13.6 concurrency

目标：观察不同并发档位下的请求成功率、延迟变化和错误情况。

默认并发档位来自模型配置：

```text
concurrency_levels
```

未配置时使用：

```text
[1, 5, 10, 20]
```

每个并发档位同时发起对应数量的短请求。

观测字段：

```text
levels[].concurrency
levels[].total_requests
levels[].success_count
levels[].error_count
levels[].rate_limited_count
levels[].avg_latency_ms
levels[].p95_latency_ms
levels[].status_code_counts
```

出现 429 不一定是 `error`，它是限流行为观测的一部分。

### 13.7 rate_limit

目标：观察上游模型 API 被压到限制时的表现。

可复用 `concurrency` 的结果。

观测字段：

```text
rate_limited_observed
first_rate_limited_concurrency
rate_limit_status_codes
retry_after_present
retry_after_values
rate_limit_headers
rate_limit_error_body_parseable
rate_limit_error_excerpt
```

如果没有触发限流，状态仍可以是 `completed`，记录 `rate_limited_observed=false`。

### 13.8 error_handling

目标：验证异常请求时，上游 API 是否返回结构化、可解析、便于网关处理的错误体。

V1 默认测试场景：

```text
invalid_api_key
invalid_model
empty_input
invalid_parameter
context_overflow
```

观测字段：

```text
cases[].case_id
cases[].http_status
cases[].error_body_parseable
cases[].error_code
cases[].error_message_present
cases[].response_body_excerpt
```

V1 不要求具体错误码必须是 401/404/429，因为不同厂商兼容实现不同，只记录实际表现。

### 13.9 token_usage_accuracy

目标：观察模型 API 返回的 usage 字段是否存在，以及与本地估算 token 数差异如何。

默认 prompt：

```text
请用三句话解释什么是 API 网关。
```

观测字段：

```text
usage_present
prompt_tokens
completion_tokens
total_tokens
estimated_prompt_tokens
estimated_completion_tokens
prompt_token_delta
completion_token_delta
token_error_ratio
estimator
```

V1 本地 token 估算使用简单启发式估算器，例如中文字符、英文单词、数字、标点混合估算。

报告中必须说明：

```text
本地 token 数为估算值，仅用于辅助观察，不作为自动判定依据。
```

对于 `token_usage_accuracy`，usage 缺失标记为 `error`，因为该指标本身就是测 usage。

## 14. 执行流程

一次 `gateway_baseline_v1` 执行流程：

```text
POST /api/tasks/run
  -> routes_tasks.py 校验请求
  -> TaskRunner.run()
  -> 加载 ModelConfig
  -> 根据 protocol 创建 Adapter
  -> 根据 plan_id 从 Registry 解析指标列表
  -> 根据指标反推需要执行的 Probe
  -> 按推荐顺序执行 Probe
  -> Probe 调用 Adapter 请求模型
  -> 生成 MetricResult
  -> 汇总 TaskResult
  -> 保存 data/tasks/task_xxx.json
  -> 生成 reports/YYYY-MM-DD/task_xxx.md
  -> 返回 TaskResult JSON
```

## 15. 失败与短路规则

### 15.1 任务级失败

以下情况属于任务级 `error`，直接停止：

- `model_id` 不存在；
- 模型配置 `enabled=false`；
- `protocol` 不支持；
- adapter 创建失败；
- 存储或报告生成发生不可恢复错误。

### 15.2 指标级失败

以下情况属于指标级 `error`，任务继续执行：

- 单个请求超时；
- 单个响应 JSON 不可解析；
- 某项指标缺必要配置；
- 流式响应无法解析；
- usage 缺失；
- 某个上下文长度测试点失败；
- 某个并发档位失败。

### 15.3 短路建议

如果 `connectivity` 是 `error`：

- V1 不强制跳过后续全部指标；
- 为了采集更多错误信息，后续指标可以继续尝试；
- 报告中应提示：基础连通性失败，后续指标结果可能不具参考价值。

如果 `stream_probe` 失败：

- `latency_breakdown` 标记 `error`；
- `stream_spec` 标记 `error`；
- 不影响非流式指标。

如果 `concurrency_probe` 失败：

- `concurrency` 标记 `error`；
- `rate_limit` 根据是否有部分可用观测决定 `error` 或 `completed`。

## 16. 错误响应格式

FastAPI 服务自身错误统一返回：

```json
{
  "error": {
    "code": "model_not_found",
    "message": "Model config not found: qwen-plus-chat",
    "details": {}
  }
}
```

常见错误码：

| code | 场景 |
|---|---|
| `model_not_found` | 模型配置不存在 |
| `model_disabled` | 模型被禁用 |
| `invalid_protocol` | 协议不支持 |
| `invalid_metric` | 指标不存在 |
| `metric_not_implemented` | 指标尚未实现 |
| `invalid_task_request` | plan_id 和 metric_ids 使用不合法 |
| `storage_error` | 文件读写失败 |
| `report_error` | 报告生成失败 |

## 17. .gitignore 要求

V1 应忽略敏感配置和产物：

```text
.env
data/models.json
data/tasks/
reports/
__pycache__/
.venv/
```

`data/models.json` 可能包含明文 API Key，不得提交。

## 18. 后续扩展方向

### 18.1 P1 指标

后续可新增：

```text
function_calling_probe -> function_calling
json_mode_probe -> json_mode
system_prompt_probe -> system_prompt
multi_turn_probe -> multi_turn
stability_probe -> stability
```

### 18.2 P2 和按需指标

后续可新增：

```text
content_safety
rate_limit_headers
model_version_stability
prompt_caching
quality_eval
multimodal
cross_region_latency
retry_idempotency
logging_audit
```

### 18.3 智力评测

后续可引入：

```text
EvaluationSuite
BenchmarkDataset
SampleRunner
Scorer
AggregateResult
```

并形成新的测试计划：

```text
intelligence_eval_v1
business_eval_v1
```

这些计划可以复用：

```text
ModelConfig
ProviderAdapter
TaskResult
MetricResult
Report
```

但不与 `gateway_baseline_v1` 混在一起。

### 18.4 平台化能力

后续可扩展：

- CLI；
- 异步任务；
- 独立 Worker；
- 数据库；
- 前端页面；
- 鉴权；
- 趋势统计；
- 多模型对比。

## 19. Open Questions Resolved

以下设计问题已经确认：

- V1 使用 uv 管理 Python 环境。
- V1 使用 FastAPI 提供接口服务。
- V1 API 服务优先，不做正式前端。
- V1 使用同步任务。
- V1 不使用 SQL 或 SQLite。
- V1 使用本地 JSON 和 Markdown 文件。
- V1 同时兼容 Chat Completions 和 Responses API 风格。
- 每个模型配置显式指定协议。
- 模型配置只填 `base_url`，系统按协议拼接路径。
- API Key 可以明文保存在内网本地配置文件，但接口和日志脱敏。
- 模型配置通过 API 管理，落到 `data/models.json`。
- V1 不做平台鉴权。
- V1 不做复杂阈值判定，但明确工程异常标记为 `error`。
- V1 默认计划为 `gateway_baseline_v1`，包含 P0 全部基础指标和 `stream_spec`。
