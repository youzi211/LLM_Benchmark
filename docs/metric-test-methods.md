# 指标测试方法文档

> 本文档是项目的一部分。后续新增、删除或修改指标时，必须同步更新本文档、`docs/api.md` 中的指标/计划说明，以及 `README.md` 中的文档入口。


## 0. Codex 快速导读

本文件记录“指标口径”，不是上线准入规则。当前系统有三类评测结果，最终可由 suite 汇总到一份 overview 报告：

| 评测类型 | API 入口 | 代码入口 | 结果/报告 | 适合回答的问题 |
|---|---|---|---|---|
| 网关 smoke / 基础工程指标 | `POST /api/tasks/run` | `app/core/runner.py`、`app/metrics/probes.py` | `data/tasks/`、`reports/YYYY-MM-DD/` | 上游 OpenAI 兼容协议是否能通、usage/stream/context/error 等基础行为是否可观测。 |
| EvalScope 能力评测 | `POST /api/intelligence/tasks/default` 或 `POST /api/intelligence/tasks` | `app/intelligence/runner.py`、`app/intelligence/evalscope_direct.py` | `data/intelligence_tasks/`、`reports/intelligence/`、`outputs/evalscope/intelligence/` | 模型在代码、数学、知识、中文、推理等数据集上的能力表现。 |
| EvalScope perf 压测 | `POST /api/stress/tasks/default` 或 `POST /api/stress/tasks` | `app/stress/runner.py`、`app/stress/evalscope_direct.py` | `data/stress_tasks/`、`reports/stress/`、`outputs/evalscope/stress/` | 并发、吞吐、延迟分位数、TTFT、TPOT、成功率等容量表现。 |
| 一键/定时总览 | `POST /api/suites/default`、`POST /api/suites/schedules` | `app/suites/runner.py`、`app/suites/scheduler.py`、`app/overview/report.py` | `data/suite_runs/`、`data/suite_schedules/`、`reports/overview/` | 同一个模型的一次完整评测导航和摘要。 |

最重要的边界：

- `/api/tasks/run` 中的 `concurrency` 和 `rate_limit` 只保留为兼容 smoke 指标；正式压测以 EvalScope perf 为准。
- 能力评测和压测的 EvalScope 原始格式不同：本系统分别在 `app/intelligence/runner.py` 和 `app/stress/runner.py` 标准化，再由 overview 引用摘要，不强行把两者压成同一种明细表。
- 需要 LLM Judge 的能力数据集默认使用 `data/models.json` 顶层 `analysis_model_id` 指向的模型；没有可用 Judge 时，包含 Judge 数据集的任务会在提交阶段返回 `400 judge_required`。
- 报告不输出自动准入结论，只输出事实、异常、风险提示和人工判断所需证据。

## 1. 总体原则

- 本服务用于模型接入模型网关前的基础工程评测。
- 指标结果只反映本次请求链路的观测事实，不自动给出“上线通过 / 失败”结论。
- 指标状态只有三类：
  - `completed`：指标执行完成并采集到观测数据。
  - `error`：指标执行完成但发现明确异常、必要字段缺失或全部请求失败。
  - `skipped`：缺少必要配置，当前指标跳过。
- 报告中的本地 token 数为启发式估算，只用于辅助观察，不作为自动判定依据。
- 所有指标都通过项目内的适配器访问上游模型接口，支持 `chat_completions` 与 `responses` 两类 OpenAI 兼容协议。

## 2. 默认评测计划

默认计划：`gateway_acceptance_v1`。历史计划名 `gateway_baseline_v1` 保留为兼容别名，指标集合相同。

该计划只承担“模型网关接入验收 / 协议 smoke”职责，正式模型能力评测和正式性能压测由 EvalScope 接口负责。

执行顺序如下：

| 顺序 | 指标 ID | 中文名 | 优先级 | 默认执行 |
|---:|---|---|---|---|
| 1 | `connectivity` | 连通性 | P0 | 是 |
| 2 | `latency_breakdown` | 延迟拆解 | P1 | 是 |
| 3 | `context_length` | 上下文长度 | P1 | 是 |
| 4 | `output_length` | 输出长度 | P1 | 是 |
| 5 | `error_handling` | 错误处理 | P0 | 是 |
| 6 | `token_usage_accuracy` | Token 用量观测（Usage） | P0 | 是 |
| 7 | `cache_behavior` | 缓存能力（Prompt Cache） | P1 | 是 |
| 8 | `stream_spec` | 流式规范性 | P1 | 是 |
| - | `concurrency` | 并发承载 | P2 | 否，需通过 `metric_ids` 显式运行 |
| - | `rate_limit` | 限流行为 | P2 | 否，需通过 `metric_ids` 显式运行 |

实际执行中，`latency_breakdown` 与 `stream_spec` 由同一次流式请求产生；`concurrency` 与 `rate_limit` 由同一组并发请求产生，但二者不再进入默认计划。

## 3. 运行前配置项

不同指标依赖的模型配置字段如下：

| 配置字段 | 影响指标 | 说明 |
|---|---|---|
| `protocol` | 全部指标 | 决定使用 Chat Completions 或 Responses 风格调用。 |
| `base_url` | 全部指标 | 上游接口根地址。 |
| `api_key` | 全部指标 | 上游接口密钥。错误处理指标会构造无效 key 场景。 |
| `model` | 全部指标 | 传给上游的模型名。错误处理指标会构造无效模型场景。 |
| `timeout_seconds` | 全部指标 | 单次请求超时。 |
| `declared_context_tokens` | `context_length`、`error_handling`、`cache_behavior` | 为空时跳过上下文长度指标；错误处理中的上下文超限场景会参考该值；缓存能力指标会用它选择稳定前缀规模，未配置时使用默认规模。 |
| `declared_max_output_tokens` | `output_length` | 为空时输出长度指标使用默认 1024。 |
| `concurrency_levels` | `concurrency`、`rate_limit` | 并发探测档位，默认 `[1, 5, 10, 20]`；二者需通过 `metric_ids` 显式运行。 |

## 4. 指标通用输出结构

每个指标输出一个 `MetricResult`：

```json
{
  "metric_id": "connectivity",
  "metric_name": "连通性",
  "status": "completed",
  "summary": "连通性探测完成",
  "observations": {},
  "errors": []
}
```

- `observations`：结构化观测数据。字段含义详见各指标章节。
- `errors`：错误列表。常见字段为 `code`、`message`、`http_status`。
- 指标 `error` 不一定表示任务失败；任务会继续收集其他指标。

## 5. `connectivity`：连通性

### 5.1 测试目标

确认模型接口的最基本可用性，包括：

- HTTP 请求是否成功。
- 响应是否可解析为 JSON。
- 是否返回文本内容。
- 是否返回 `finish_reason`。
- 是否返回 `usage`。

### 5.2 调用方式

非流式调用一次 `adapter.complete()`。

Prompt：

```text
请用一句话说明大模型 API 验证服务的作用。
```

请求参数：

| 参数 | 值 |
|---|---|
| `temperature` | `0`，由 `AdapterRequest` 默认提供。 |
| `max_tokens` | 不显式设置。 |
| `stream` | `false`。 |

### 5.3 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `http_status` | integer/null | 上游 HTTP 状态码。 |
| `latency_ms` | number/null | 单次请求耗时毫秒。 |
| `response_json_parseable` | boolean | 响应是否解析为 JSON。 |
| `content_present` | boolean | 是否提取到非空文本内容。 |
| `content_excerpt` | string | 响应内容前 300 字符。 |
| `finish_reason` | string/null | 上游返回的结束原因。 |
| `usage_present` | boolean | 是否返回 usage。 |

### 5.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | `response.ok = true`。适配器层通常要求 HTTP 状态码小于 400 且内容非空。 |
| `error` | `response.ok = false`。 |

### 5.5 关注点

- 如果 `content_present = false`，说明模型未返回有效内容或适配器未能正确解析内容。
- 如果 `response_json_parseable = false`，说明上游不符合当前兼容协议预期。
- 如果 `usage_present = false`，不一定影响连通性，但会影响 Token 用量观测。

## 6. `token_usage_accuracy`：Token 用量观测（Usage）

### 6.1 测试目标

观察上游是否返回 usage token 字段，并将 usage 与本地启发式估算值做辅助对比。

该指标不对 token 准确性做自动通过/失败判定。

### 6.2 调用方式

非流式调用一次 `adapter.complete()`。

Prompt：

```text
请用三句话解释什么是 API 网关。
```

### 6.3 usage 字段兼容规则

- Prompt token：优先读取 `prompt_tokens`，其次读取 `input_tokens`。
- Completion token：优先读取 `completion_tokens`，其次读取 `output_tokens`。
- Total token：读取 `total_tokens`。

### 6.4 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `usage_present` | boolean | 是否返回 usage。 |
| `prompt_tokens` | integer/null | 上游返回的输入 token 数。 |
| `completion_tokens` | integer/null | 上游返回的输出 token 数。 |
| `total_tokens` | integer/null | 上游返回的总 token 数。 |
| `estimated_prompt_tokens` | integer | 本地估算输入 token 数。 |
| `estimated_completion_tokens` | integer | 本地估算输出 token 数。 |
| `prompt_token_delta` | integer/null | `prompt_tokens - estimated_prompt_tokens`。 |
| `completion_token_delta` | integer/null | `completion_tokens - estimated_completion_tokens`。 |
| `token_error_ratio` | number/null | `abs(completion_tokens - estimated_completion_tokens) / completion_tokens`。 |
| `estimator` | string | 本地估算器名称。 |

### 6.5 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 响应中存在 `usage`。 |
| `error` | 响应中缺少 `usage`。 |

### 6.6 关注点

- 本地估算值不是模型官方 tokenizer，只用于横向观察。
- 如果 `usage_present = false`，后续容量、计费或审计类分析会缺少关键数据。

## 7. `cache_behavior`：缓存能力（Prompt Cache）

### 7.1 测试目标

通过“长稳定前缀 + 冷/热重复请求”观察模型网关或上游模型的 Prompt Cache 行为。

该指标只输出观测事实，不设置自动阈值，也不自动判断缓存能力是否达标。

重点观察：

- 上游 `usage` 是否暴露缓存相关字段。
- 重复请求是否出现 cached tokens、cache hit 或 cache read 信号。
- 冷请求与重复请求的延迟差异。
- 相同完整 Prompt 与相同前缀不同后缀两种场景是否表现不同。

### 7.2 调用方式

非流式顺序调用三次 `adapter.complete()`：

| 轮次 | 说明 |
|---|---|
| `warmup_same_prompt` | 首轮冷请求，用于预热缓存。 |
| `repeat_same_prompt` | 第二轮使用完全相同 Prompt，观察完整 Prompt 复用。 |
| `repeat_same_prefix_variant_suffix` | 第三轮保持长前缀不变、替换最后问题，观察前缀缓存复用。 |

稳定前缀由固定中文块重复构造，包含标记 `LAKALA-CACHE-PROBE-STABLE-PREFIX`。前缀目标 token 数规则：

- 未配置 `declared_context_tokens`：默认约 `4096` tokens。
- `declared_context_tokens <= 2048`：使用声明值约一半，最低 `256` tokens。
- 其他情况：使用声明值约四分之一，范围约 `1024` 到 `8192` tokens。

请求参数：

| 参数 | 值 |
|---|---|
| `max_tokens` / `max_output_tokens` | `64`。 |
| `temperature` | `0`。 |
| `stream` | `false`。 |

### 7.3 缓存字段兼容规则

当前会从 `usage` 中识别以下常见字段，并保留实际命中的字段路径：

| 字段路径 | 含义 |
|---|---|
| `prompt_tokens_details.cached_tokens` | OpenAI 风格 prompt cached tokens。 |
| `input_tokens_details.cached_tokens` | Responses/input 风格 cached tokens。 |
| `cached_tokens`、`prompt_cached_tokens`、`input_cached_tokens`、`cached_input_tokens` | 常见扁平缓存 token 字段。 |
| `cache_read_input_tokens` | 读取缓存的输入 token 数。 |
| `cache_creation_input_tokens`、`prompt_cache_creation_tokens` | 创建缓存的输入 token 数。 |
| `cache_hit`、`prompt_cache_hit`、`input_cache_hit` | 明确缓存命中布尔字段。 |

此外，报告会记录所有 key 名包含 `cache` 或 `cached` 的 usage 路径，方便后续扩展解析规则。

### 7.4 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `request_count` | integer | 缓存探测请求总数，当前为 3。 |
| `successful_count` | integer | 成功请求数。 |
| `stable_prefix_estimated_tokens` | integer | 本地估算的稳定前缀 token 数。 |
| `target_prefix_tokens` | integer | 本次计划构造的前缀目标 token 数。 |
| `cache_signal_present` | boolean | 是否发现缓存相关 usage 字段。 |
| `usage_field_paths_detected` | string[] | 检测到的缓存相关字段路径。 |
| `max_cached_tokens` | integer/null | 三轮中观测到的最大 cached tokens。 |
| `cache_hit_count` | integer | 按 cached/read token 或明确 hit 字段统计的命中轮次。 |
| `latency_baseline_ms` | number/null | 首轮请求延迟。 |
| `repeated_latency_avg_ms` | number/null | 后两轮平均延迟。 |
| `latency_reduction_ms` | number/null | `latency_baseline_ms - repeated_latency_avg_ms`。 |
| `latency_reduction_ratio` | number/null | 延迟下降比例。 |
| `rounds` | object[] | 三轮请求明细，包括状态码、延迟、usage token、缓存字段和错误对象。 |

### 7.5 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 三轮请求均成功。即使未发现缓存字段，也会完成并输出 `cache_signal_present = false`。 |
| `error` | 至少一轮请求失败。 |

错误码：

| `errors[].code` | 场景 |
|---|---|
| `cache_probe_request_failed` | 至少一轮缓存探测请求失败。 |

### 7.6 关注点

- `cache_signal_present = false` 只表示当前接口响应未暴露可识别缓存字段，不等于模型一定没有缓存。
- 如果 `max_cached_tokens` 或 `cache_hit_count` 大于 0，说明上游至少暴露了缓存命中信号。
- 如果未暴露缓存字段，但重复请求延迟明显下降，可能存在网关层或模型层缓存，需要结合上游日志确认。
- 如果缓存字段存在但延迟没有改善，可能是缓存粒度、前缀长度、并发环境或上游实现差异导致。

## 8. `latency_breakdown`：延迟拆解

### 8.1 测试目标

通过一次流式调用采集首包/首 token 延迟、端到端延迟、流式持续时间和估算吞吐。

### 8.2 调用方式

流式调用一次 `adapter.stream()`。该调用同时产出 `latency_breakdown` 和 `stream_spec` 两个指标。

Prompt：

```text
请用中文分 5 点简要说明：为什么大模型 API 上线前需要做工程验证。
```

请求参数：

| 参数 | 值 |
|---|---|
| `stream` | `true`。 |
| `temperature` | `0`。 |
| `max_tokens` | 不显式设置。 |

### 8.3 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `ttft_ms` | number/null | 首个内容 chunk 到达耗时。 |
| `end_to_end_latency_ms` | number/null | 流式响应结束总耗时。 |
| `stream_duration_ms` | number/null | `end_to_end_latency_ms - ttft_ms`。 |
| `output_char_count` | integer | 完整输出字符数。 |
| `estimated_output_tokens` | integer | 本地估算输出 token 数。 |
| `tps_estimated` | number/null | 估算 tokens per second。 |
| `stream_event_count` | integer | 解析到的流式事件数量。 |
| `first_content_at` | number/null | 当前等同于 `ttft_ms`。 |
| `finished_at` | number/null | 当前等同于 `end_to_end_latency_ms`。 |

### 8.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 流式响应 `response.ok = true`。 |
| `error` | 流式响应 `response.ok = false`。 |

### 8.5 关注点

- `ttft_ms` 反映用户首字等待时间。
- `end_to_end_latency_ms` 反映整段生成完成时间。
- `tps_estimated` 依赖本地 token 估算，只能做趋势参考。
- 如果流式接口实际退化为非流式或没有内容 chunk，TTFT 可能为空。

## 9. `stream_spec`：流式规范性

### 9.1 测试目标

检查流式响应是否符合 SSE 常见格式，并观察关键事件和字段：

- SSE 数据行是否可解析。
- 是否存在 `[DONE]`。
- 是否存在 `finish_reason`。
- 是否存在流式 `usage`。

### 9.2 调用方式

与 `latency_breakdown` 共用同一次 `adapter.stream()` 调用。

### 9.3 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `sse_parseable` | boolean | 存在 chunk 且所有 chunk 无解析错误。 |
| `data_line_count` | integer | 数据行数量。 |
| `event_count` | integer | 事件数量。当前等同于 chunk 数。 |
| `parse_error_count` | integer | JSON 解析错误数量。 |
| `done_event_present` | boolean | 是否出现 `[DONE]`。 |
| `finish_reason` | string/null | 流式响应结束原因。 |
| `finish_reason_present` | boolean | 是否存在 `finish_reason`。 |
| `stream_usage_present` | boolean | 是否存在流式 usage。 |
| `raw_event_excerpt` | string[] | 前 5 条原始事件摘要。 |

### 9.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 流式响应 `response.ok = true`。 |
| `error` | 流式响应 `response.ok = false`。 |

### 9.5 关注点

- `completed` 只表示流式请求成功；是否有 `[DONE]`、`finish_reason`、usage 需要人工结合字段查看。
- `parse_error_count > 0` 说明 SSE 内容与当前解析器预期不一致。
- `stream_usage_present = false` 在一些 OpenAI 兼容服务中可能是正常实现差异，但需要在网关规范中确认。

## 10. `output_length`：输出长度

### 10.1 测试目标

观察模型在指定最大输出 token 下的实际输出能力和结束原因。

### 10.2 调用方式

非流式调用一次 `adapter.complete()`。

Prompt：

```text
请生成一篇结构化中文说明文，主题是“大模型 API 网关上线前验证”，尽量详细展开，不要提前结束。
```

请求参数：

| 参数 | 值 |
|---|---|
| `max_tokens` / `max_output_tokens` | `declared_max_output_tokens`；未配置时使用 `1024`。 |
| `temperature` | `0`。 |
| `stream` | `false`。 |

协议差异：

- `chat_completions` 使用 `max_tokens`。
- `responses` 使用 `max_output_tokens`。

### 10.3 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `requested_max_tokens` | integer | 本次请求使用的最大输出 token 参数。 |
| `used_default_max_tokens` | boolean | 是否因为未配置而使用默认 1024。 |
| `output_char_count` | integer | 实际输出字符数。 |
| `estimated_output_tokens` | integer | 本地估算输出 token 数。 |
| `finish_reason` | string/null | 结束原因。 |
| `usage_completion_tokens` | integer/null | usage 中的输出 token 数。 |
| `content_excerpt` | string | 输出前 500 字符。 |

### 10.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 响应 `response.ok = true`。 |
| `error` | 响应 `response.ok = false`。 |

### 10.5 关注点

- 如果 `finish_reason` 显示长度截断，应结合 `usage_completion_tokens` 和实际内容判断最大输出能力。
- 如果未配置 `declared_max_output_tokens`，测试结果只代表默认 1024 请求下的表现。

## 11. `context_length`：上下文长度

### 11.1 测试目标

通过“needle in haystack”长上下文探测，观察两类能力：

1. API 是否接受接近目标长度的 prompt。
2. 模型是否能从长上下文中找回指定 marker。

该指标区分“API 接收能力”和“模型找回能力”。

### 11.2 前置条件

必须配置：

```text
declared_context_tokens
```

未配置时返回：

```text
status = skipped
summary = 未配置 declared_context_tokens，跳过上下文长度探测
```

### 11.3 测试点生成规则

基础测试点：

```text
4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288
```

生成逻辑：

- 取不超过 `declared_context_tokens` 的基础测试点。
- 如果 `declared_context_tokens > 524288`，追加：
  - `declared_context_tokens * 0.75`
  - `declared_context_tokens * 0.9`
  - `declared_context_tokens`
- 如果 `declared_context_tokens <= 524288` 且不在基础测试点中，追加 `declared_context_tokens`。
- 最终去重并升序排列。

### 11.4 Prompt 构造方法

使用结构化干扰块和唯一目标块：

- 开头说明：要求模型只返回 `NEEDLE_CODE`。
- 干扰块：多个 `BEGIN_CONTEXT_BLOCK / END_CONTEXT_BLOCK`，包含与指标相关的普通描述。
- 目标块：包含唯一 marker。
- 问题：询问唯一 `NEEDLE_CODE` 的值。

当前 marker：

```text
ZXQ-7F3A9C-END
```

目标块大致形式：

```text
BEGIN_CONTEXT_BLOCK NEEDLE
以下字段是本次上下文长度探测需要找回的唯一目标：
NEEDLE_CODE: ZXQ-7F3A9C-END
如果后文出现其他 CTX 编号，请忽略它们。
END_CONTEXT_BLOCK NEEDLE
```

位置策略：

- 约 65% 干扰块放在目标块之前。
- 约 35% 干扰块放在目标块之后。

每个测试点请求：

| 参数 | 值 |
|---|---|
| `prompt` | 按目标 token 数构造的长上下文。 |
| `max_tokens` / `max_output_tokens` | `256`。 |
| `temperature` | `0`。 |

### 11.5 marker 判断规则

为了容忍大小写和标点差异，会对模型输出和 marker 做归一化：

- 去掉非字母数字字符。
- 转为大写。
- 判断归一化后的 marker 是否包含在归一化输出中。

### 11.6 硬错误停止规则

如果某个测试点返回以下 HTTP 状态码之一，会停止后续更长测试点：

```text
400, 413, 422
```

这些通常表示上下文过长或请求体不被接受。

### 11.7 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `declared_context_tokens` | integer | 配置声明的上下文长度。 |
| `test_points` | integer[] | 计划测试点。 |
| `executed_test_points` | integer[] | 实际执行的测试点。遇硬错误可能提前停止。 |
| `marker` | string | 本次使用的 marker。 |
| `prompt_style` | string | 当前为 `structured_needle_in_haystack_v2`。 |
| `response_max_tokens` | integer | 当前固定为 256。 |
| `observed_accepted_max_prompt_tokens` | integer/null | API 成功接收的最大测试点。 |
| `observed_marker_found_max_prompt_tokens` | integer/null | 成功找回 marker 的最大测试点。 |
| `first_http_error_point` | integer/null | 首次 API 拒绝请求的测试点。 |
| `first_marker_miss_point` | integer/null | 首次 API 接收但 marker 未找回的测试点。 |
| `stopped_after_hard_error` | boolean | 是否因硬错误停止。 |
| `point_results` | object[] | 每个测试点的详细结果。 |

`point_results[]` 字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `requested_approx_tokens` | integer | 目标近似 token 数。 |
| `prompt_char_length` | integer | 实际 prompt 字符数。 |
| `estimated_prompt_tokens` | integer | 本地估算 prompt token 数。 |
| `ok` | boolean | 当前等同于 `retrieval_ok`。 |
| `accepted_by_api` | boolean | API 是否接收并返回成功响应。 |
| `retrieval_ok` | boolean | API 成功且输出找回 marker。 |
| `http_status` | integer/null | HTTP 状态码。 |
| `latency_ms` | number/null | 请求耗时。 |
| `marker_found` | boolean | 是否找回 marker。 |
| `finish_reason` | string/null | 结束原因。 |
| `output_char_count` | integer | 输出字符数。 |
| `content_excerpt` | string | 输出前 500 字符。 |
| `usage_prompt_tokens` | integer/null | usage 中输入 token 数。 |
| `usage_completion_tokens` | integer/null | usage 中输出 token 数。 |
| `usage_total_tokens` | integer/null | usage 中总 token 数。 |
| `error` | object/null | 上游错误对象。 |

### 11.8 状态规则

| 状态 | 条件 |
|---|---|
| `skipped` | 未配置 `declared_context_tokens`。 |
| `completed` | 所有执行测试点均成功找回 marker。 |
| `error` | 任一测试点 API 拒绝或未找回 marker。 |

错误码：

| `errors[].code` | 场景 |
|---|---|
| `context_acceptance_failed` | 出现 API 拒绝请求的测试点。 |
| `context_retrieval_failed` | API 接收成功但 marker 未找回。 |
| `context_point_failed` | 至少一个测试点未通过，但未归入前两类。 |

### 11.9 关注点

- `observed_accepted_max_prompt_tokens` 表示网关/API 链路可接收，不等于模型可有效利用。
- `observed_marker_found_max_prompt_tokens` 更接近长上下文可用能力，但仍依赖 prompt 形式和模型稳定性。
- 某些网关可能在大请求处返回限流或配额错误，这不一定代表模型真实上下文上限。

## 12. `error_handling`：错误处理

### 12.1 测试目标

构造典型错误场景，观察网关错误结构是否稳定、清晰、可解析。

### 12.2 测试场景

该指标顺序执行 5 个场景：

| `case_id` | 构造方式 | 预期关注点 |
|---|---|---|
| `invalid_api_key` | 将模型配置的 `api_key` 替换为无效值。 | 是否返回鉴权错误，错误结构是否清晰。 |
| `invalid_model` | 将 `model` 替换为无效模型名。 | 是否返回模型不存在或类似错误。 |
| `empty_input` | 使用空 prompt。 | 是否明确提示输入为空或参数非法。 |
| `invalid_parameter` | 在 `extra_body` 中设置 `temperature = -999`。 | 是否返回参数校验错误。 |
| `context_overflow` | 构造超长 prompt，长度为 `max(declared_context_tokens * 2, 20000)` 个“溢”字，`max_tokens = 16`。 | 是否返回上下文超限或请求过大错误。 |

### 12.3 观测字段

顶层字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `cases` | object[] | 每个错误场景的结果。 |

`cases[]` 字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `case_id` | string | 错误场景 ID。 |
| `http_status` | integer/null | HTTP 状态码。 |
| `latency_ms` | number/null | 请求耗时。 |
| `error_shape_present` | boolean | 是否提取到标准错误对象。 |
| `error_code` | string/null | 错误码。 |
| `error_message_excerpt` | string | 错误消息前 300 字符。 |
| `raw_excerpt` | string | 原始响应或错误对象前 500 字符。 |

### 12.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 至少执行了一个错误场景。当前实现不要求每个场景都返回错误。 |
| `error` | 没有执行任何错误场景。 |

### 12.5 关注点

- 该指标重点看错误结构是否一致，而不是简单要求每个场景必须失败。
- 如果错误对象为空但 HTTP 状态码异常，说明适配器或上游错误格式可能需要兼容增强。
- `context_overflow` 使用的是启发式超长输入，不保证一定触发所有网关的上下文超限。

## 13. `concurrency`：并发承载

> 该指标是历史兼容的轻量性能 smoke，不在 `gateway_acceptance_v1` 默认计划中。需要时通过 `metric_ids` 显式运行；正式并发承载、吞吐和延迟分布以 EvalScope 压测 `/api/stress/*` 为准。

### 13.1 测试目标

按配置并发档位发起请求，观察模型通道在不同并发下的成功数、错误数、限流数和延迟分布。

### 13.2 调用方式

读取：

```text
concurrency_levels
```

默认：

```text
[1, 5, 10, 20]
```

对每个并发档位 `level`，同时发起 `level` 个非流式请求。

Prompt 模板：

```text
请简短回答：并发测试请求 {index}
```

请求执行方式：

- 使用 `asyncio.gather(..., return_exceptions=True)` 并发执行。
- 单个请求异常会被记录为错误，不中断整个档位。

### 13.3 观测字段

顶层字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `levels` | integer[] | 实际并发档位。 |
| `per_level` | object[] | 每个档位统计。 |
| `total_requests` | integer | 总请求数。 |
| `success_count` | integer | 总成功数。 |
| `error_count` | integer | 总错误数。 |
| `rate_limited_count` | integer | 总 429 数。 |

`per_level[]` 字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `level` | integer | 并发档位。 |
| `requests` | integer | 该档位请求数。 |
| `success_count` | integer | 该档位成功数。 |
| `error_count` | integer | 该档位错误数。 |
| `rate_limited_count` | integer | 该档位 429 数。 |
| `latency_ms_min` | number/null | 该档位最小延迟。 |
| `latency_ms_max` | number/null | 该档位最大延迟。 |
| `latency_ms_avg` | number/null | 该档位平均延迟。 |

### 13.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 所有并发请求中至少一个成功。 |
| `error` | 所有并发请求均失败。 |

错误码：

| `errors[].code` | 场景 |
|---|---|
| `all_concurrency_failed` | 没有并发请求成功。 |

### 13.5 关注点

- 并发请求总数等于所有 `concurrency_levels` 之和。
- 如果某个档位出现大量 429，应结合 `rate_limit` 指标分析。
- 如果延迟随并发上升明显放大，说明通道可能需要限流或容量配置。

## 14. `rate_limit`：限流行为

> 该指标是历史兼容的轻量限流 smoke，不在 `gateway_acceptance_v1` 默认计划中。需要时通过 `metric_ids` 显式运行；正式限流/容量边界以 EvalScope 压测 `/api/stress/*` 为准。

### 14.1 测试目标

基于并发探测结果，观察是否出现 HTTP 429 或其他明确限流信号。

### 14.2 调用方式

与 `concurrency` 共用同一组并发请求，不额外发起请求。

### 14.3 观测字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `rate_limited_count` | integer | HTTP 429 总次数。 |
| `rate_limited_http_statuses` | integer[] | 观察到的限流状态码列表。当前只收集 429。 |
| `first_rate_limit_observed_at_level` | integer/null | 首次出现 429 的并发档位。 |
| `examples` | object[] | 前 5 个异常或限流样例。 |

`examples[]` 可能包含：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `level` | integer | 所属并发档位。 |
| `http_status` | integer/null | HTTP 状态码。 |
| `error` | object/string/null | 错误对象或异常摘要。 |

### 14.4 状态规则

| 状态 | 条件 |
|---|---|
| `completed` | 并发探测执行完成。当前无论是否出现限流，均为完成。 |

### 14.5 关注点

- `rate_limited_count = 0` 只表示本次并发档位未观察到 429，不代表没有限流。
- 如果出现 429，需结合上游账号配额、网关限流策略和并发档位复测。
- 某些服务可能使用非 429 状态码表达限流，当前实现只把 429 计入 `rate_limited_count`。

## 15. 报告事实包与 LLM 分析

评测完成后，服务会从 `TaskResult` 构建 `ReportFactPack`，再可选调用报告分析模型生成 `ReportAnalysis`。

### 15.1 ReportFactPack 目的

- 将原始指标结果压缩为适合 LLM 分析的稳定事实。
- 保留关键观测值、核心说明、建议关注点和必要原始摘要。
- 避免把完整大字段或敏感内容直接发送给分析模型。

### 15.2 事实包内容

| 字段 | 说明 |
|---|---|
| `task` | 任务 ID、模型配置 ID、模型名、协议、计划 ID、耗时等。 |
| `status_counts` | 指标总数、完成数、异常数、跳过数。 |
| `metric_facts` | 每个指标的状态、摘要、核心观测、建议关注、关键事实和重要原始摘要。 |

### 15.3 LLM 分析输出字段

| 字段 | 说明 |
|---|---|
| `analysis_status` | `completed`、`skipped` 或 `error`。 |
| `analysis_model_id` | 使用的报告分析模型 ID。 |
| `one_sentence_summary` | 一句话总结。 |
| `overall_assessment` | 总体分析。 |
| `key_findings` | 关键发现。 |
| `risks` | 风险点。 |
| `recommended_next_steps` | 建议下一步。 |
| `metric_notes` | 分指标备注。 |
| `error_message` | 分析失败原因。 |
| `raw_excerpt` | 分析失败时的脱敏原文摘要。 |

### 15.4 分析失败隔离

报告分析失败不会改变基础评测任务状态：

- 指标执行完成后，`TaskResult.status` 仍按基础评测结果保存。
- 分析失败只体现在 `analysis.analysis_status = error`。
- Markdown 报告会展示失败原因和脱敏摘要。


## 16. EvalScope 压测指标说明

EvalScope 压测不是 `gateway_acceptance_v1` 的同步接入验收指标，而是正式性能/负载评测的数据来源。当前责任划分如下：

| 指标 ID | 基础 `/api/tasks/run` | EvalScope 压测 `/api/stress/*` |
|---|---|---|
| `latency_breakdown` | 单次流式 smoke，观察 TTFT、端到端耗时和流式规范 | 正式统计来源，按并发档位输出平均/P50/P95/P99 延迟、TTFT、TPOT |
| `concurrency` | 轻量并发 smoke，快速发现明显不可用 | 正式压测来源，按 `parallel`/`number` 梯度统计成功率、吞吐和失败点 |
| `rate_limit` | 观察轻量并发中的 429 | 结合压测失败数、429、吞吐曲线和首次失败并发档位分析限流/容量边界 |

### 压测执行方法

1. 在 `data/models.json` 配置被测模型，协议必须显式为 `chat_completions` 或 `responses`。
2. `data/evalscope.json` 通常可以不创建；只有要覆盖 EvalScope 本地目录时才使用最小配置：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope"
}
```

3. 调用 `POST /api/stress/tasks/default`，可覆盖 `parallel`、`number`、`stream`、`rate`、`min_prompt_length`、`max_prompt_length`、`min_tokens`、`max_tokens`、`tokenizer_path`。
4. 轮询 `GET /api/stress/tasks/{task_id}`，完成后调用 `GET /api/stress/tasks/{task_id}/result` 拉取结果并生成报告。
5. 下载 `GET /api/stress/reports/{task_id}`，人工分析吞吐、延迟、失败率和错误摘要；完整 EvalScope 业务结果从同一任务结果 API 的 `raw_result` 获取，`raw_output_dir` 用于定位原始产物。

### 压测结果字段

| 字段 | 说明 |
|---|---|
| `parallel` | 并发档位。 |
| `total` / `number` | 请求总数。 |
| `success` / `failed` / `success_rate` | 成功、失败和成功率。 |
| `request_throughput` | 请求吞吐，单位 req/s。 |
| `output_throughput` / `total_throughput` | 输出或总 token 吞吐。 |
| `avg_latency_seconds` / `p50_latency_seconds` / `p95_latency_seconds` / `p99_latency_seconds` | 延迟统计。 |
| `avg_ttft_ms` / `p95_ttft_ms` / `p99_ttft_ms` | 首 token 时间统计；要求 `stream=true`。 |
| `avg_tpot_ms` / `p95_tpot_ms` / `p99_tpot_ms` | 输出 token 间隔统计。 |
| `summary.max_success_parallel` | 未发现失败的最大并发档位。 |
| `summary.best_req_throughput` | 最高请求吞吐。 |
| `summary.first_error_parallel` | 首次出现失败的并发档位。 |

### 注意事项

- 本项目不设置自动阈值，不给出“通过/不通过”结论；相关人员根据模型用途和压测曲线自行分析。
- `stream=true` 是 TTFT 可信统计的前提。
- `prefix_length` 和 `dataset_args.prefix_file` 可用于后续观察前缀/缓存压测，但当前缓存能力基础指标仍由 `cache_behavior` smoke 负责。
- 压测数据集默认使用 `longalpaca`（真实长文本语料，一次性下载到 `data/stress_datasets/longalpaca.json`，runner 自动补齐 `dataset_path` 指向本地文件，EvalScope 改为 `from local` 加载，不再每次评测从 ModelScope 下载）。长度过滤对齐 EvalScope 官方默认：`min_prompt_length=0`、`max_prompt_length=131072`、`tokenizer_path=null`（按字符长度过滤），避免原先 1024 token 过滤把长文本几乎全部丢弃。若要按 token 长度随机生成 prompt，提交时显式传 `dataset=random` 并设置 `min_prompt_length` / `max_prompt_length` / `tokenizer_path`。
- `StressTask.normalized_result` 只保留并发档位指标、吞吐、延迟、TTFT/TPOT、汇总和异常摘要；完整 EvalScope perf 返回只保留在任务级 `raw_result`，原始文件目录由 `raw_output_dir` 指向。
- 压测 Markdown 报告不复制完整原始 JSON，只提供摘要和结果定位入口；overview 同样不嵌入详细原始结果。
- 主服务内 EvalScope 执行链路必须避免在响应、任务 JSON、报告和日志中泄露 `api_key`。

## 17. EvalScope 智力评测说明

EvalScope 智力评测不是 `gateway_acceptance_v1` 的接入验收指标，因此不会出现在 `/api/metrics` 或 `/api/tasks/run` 中。它通过独立的 `/api/intelligence/*` 接口在主服务进程内调用 EvalScope Python package，用于采集模型在代码、数学、知识、复杂推理等公开数据集上的表现。

测试方法摘要：

| 步骤 | 方法 | 输出 |
|---|---|---|
| 1 | 调用 `GET /api/intelligence/datasets/local` 查看本地可用数据集。 | 数据集 `pretty_name`、`needs_judge`、`categories`。 |
| 2 | 调用 `POST /api/intelligence/tasks/default` 或 `POST /api/intelligence/tasks` 提交评测。 | 本系统 `task_id` 与 EvalScope `evalscope_task_id`。 |
| 3 | 调用 `GET /api/intelligence/tasks/{task_id}` 刷新状态。 | `pending`、`running`、`completed`、`failed` 和 `progress`。 |
| 4 | 调用 `GET /api/intelligence/tasks/{task_id}/result` 获取终态结果。 | 精简标准化数据集分数、能力维度汇总、报告路径，以及任务级 `raw_result` / `raw_output_dir` 定位。 |
| 5 | 调用 `GET /api/intelligence/reports/{task_id}` 下载报告。 | 人可读 Markdown 报告。 |

关注点：

- 默认评测的数据集组合由本系统在 `app/intelligence/evalscope_direct.py` 中维护，并逐个传给 EvalScope 执行。
- 代码执行类数据集（`humaneval`、`humaneval_plus`、`mbpp`、`mbpp_plus`、`live_code_bench`）必须配置 EvalScope sandbox 才能评分；推荐在 `data/evalscope.json` 中设置 `sandbox_enabled=true` 和远程 `sandbox_manager_config.base_url`。FastAPI 主服务启动时不会在 `app.main` 中自动启动 sandbox；运行这类数据集前必须先独立启动 `ms-enclave server` 并确认 `/health` 可访问，或在同机验证时使用 `scripts/start_all.*` 的显式 sandbox 选项。运行时适配层会把本地兼容字段转换为 EvalScope 官方 `sandbox={"enabled": true, "engine": "docker", "manager_config": {...}}`。
- 需要 Judge 的数据集默认使用 `data/models.json` 顶层 `analysis_model_id` 指向的内置 Judge；可用 `data/evalscope.json` 的 `judge_model_config_id` 覆盖。没有可用 Judge 时，包含 Judge 数据集的任务会在提交阶段被拒绝，避免跑到 EvalScope 内部才失败。
- `score` 只做展示和后续人工分析，不设置上线阈值，不输出自动准入结论。
- `normalized_result` 只保留数据集分数、能力维度汇总、状态和错误摘要；完整 EvalScope 业务结果只保留在任务级 `raw_result`，`raw_output_dir` 指向 EvalScope 原始输出目录。
- Markdown 报告和 overview 只展示摘要与原始结果定位，不再复制完整 `report_table`、metrics 或 JSON 附录；需要排查时使用 `/api/intelligence/tasks/{task_id}/result` 和报告中的原始输出目录。

## 18. 维护清单

当修改指标实现时，请同步检查：

- `app/core/plans.py`：指标名称、说明、默认计划是否更新。
- `app/metrics/probes.py`：测试方法是否与本文档一致。
- `docs/metric-test-methods.md`：指标目的、调用方式、观测字段、状态规则是否更新。
- `docs/api.md`：`/api/metrics`、`/api/plans`、`TaskResult`、`MetricResult` 是否需要更新。
- `README.md`：默认指标列表和文档入口是否需要更新。
- 测试文件：是否覆盖新增或变更字段。

建议每次涉及接口或指标的提交都把相关文档放在同一提交中，避免文档滞后。
