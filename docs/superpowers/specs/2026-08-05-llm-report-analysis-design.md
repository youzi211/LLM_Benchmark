# LLM 评测报告分析增强设计

日期：2026-08-05  
状态：已获用户认可，待实现计划  
项目：LLM_Benchmark

## 1. 背景

当前服务已经可以对 OpenAI Chat Completions / Responses API 风格的大模型接口执行基础上线前评测，并生成 Markdown 报告。但现有报告主要由任务信息、指标状态表和原始 JSON 数据组成，阅读体验偏工程原始输出：

- 报告开头缺少“一眼可读”的整体分析。
- 指标明细以 JSON 为主，排版单调。
- 人员需要自行从 observations/errors 中提取核心风险和后续复测动作。
- 长上下文、并发、流式、错误处理等指标后续会继续扩展，原始数据会越来越多，报告需要更强的信息组织能力。

本设计的目标是在基础评测完成后增加一层报告增强流程：程序先提炼结构化事实包，再调用固定的报告分析模型生成中文分析，最后输出“仪表盘 + 明细型”的 Markdown 报告。

## 2. 已确认决策

### 2.1 报告分析模型

采用固定的“报告分析模型”，不默认使用被测模型自评。

配置放在 `data/models.json` 顶层：

```json
{
  "analysis_model_id": "report-analyzer",
  "models": [
    {
      "id": "report-analyzer",
      "name": "报告分析模型",
      "protocol": "chat_completions",
      "base_url": "https://analysis.example.com/v1",
      "api_key": "sk-redacted",
      "model": "report-analysis-model"
    }
  ]
}
```

### 2.2 分析模型输入

采用“两层输入”：

1. 程序提炼出的结构化摘要。
2. 关键指标的必要原始片段。

不把完整 observations/errors 无筛选地直接交给分析模型。

### 2.3 报告版式

采用“仪表盘 + 明细型”：

- 前半部分适合快速阅读和转发。
- 中间部分提供指标状态、核心观测和建议关注项。
- 后半部分保留完整明细和 JSON，方便工程人员继续查数。

### 2.4 分析失败策略

LLM 分析是报告增强步骤，不改变基础评测任务结果。

如果报告分析模型未配置、请求失败或输出无法解析：

- 任务仍然按基础评测结果完成。
- Markdown 报告里明确显示“LLM 分析生成失败”及原因摘要。
- 原始指标数据仍完整写入报告。

## 3. 目标

第一版实现以下能力：

1. `data/models.json` 支持顶层 `analysis_model_id`。
2. 任务执行完成基础指标后，尝试调用固定分析模型生成报告分析。
3. 分析输入由程序构建，包含结构化事实包和关键原始片段。
4. 分析输出采用结构化 JSON，报告生成器根据 JSON 稳定排版。
5. Markdown 报告改为“仪表盘 + 明细型”。
6. 分析失败不影响任务完成。
7. 报告全文、分析输入和分析输出都执行敏感信息脱敏。
8. 增加自动化测试覆盖主要成功和失败路径。

## 4. 非目标

第一版不做以下内容：

- 不做 Web 前端页面。
- 不做 PDF / Word 导出。
- 不做自动“上线通过/失败”判定。
- 不做复杂异步任务队列。
- 不做成本统计或预算控制。
- 不做多分析模型投票。
- 不做报告历史对比趋势图。
- 不把生成报告纳入平台鉴权流程。

这些能力可以在后续版本基于当前结构继续扩展。

## 5. 数据结构设计

### 5.1 `models.json`

当前项目使用单文件 `data/models.json` 管理模型配置。第一版扩展该文件格式，支持顶层 `analysis_model_id`。

推荐兼容形态：

```json
{
  "analysis_model_id": "report-analyzer",
  "models": [
    {
      "id": "minimax-m3-ark-real",
      "name": "MiniMax-M3 火山方舟兼容接口",
      "protocol": "chat_completions",
      "base_url": "https://gateway.example.com/v1",
      "api_key": "sk-redacted",
      "model": "minimax-m3"
    },
    {
      "id": "report-analyzer",
      "name": "报告分析模型",
      "protocol": "chat_completions",
      "base_url": "https://gateway.example.com/v1",
      "api_key": "sk-redacted",
      "model": "report-analysis-model"
    }
  ]
}
```

兼容策略：

- 如果历史文件是纯数组形式，继续按模型列表读取，`analysis_model_id` 视为未配置。
- 如果是对象形式，读取 `models` 和可选的 `analysis_model_id`。
- 写回时使用对象形式，避免丢失 `analysis_model_id`。

### 5.2 报告事实包

新增内部结构 `ReportFactPack`，用于发送给分析模型。建议字段：

```json
{
  "task": {
    "task_id": "task_20260805000000_example",
    "model_id": "minimax-m3-ark-real",
    "model_config_name": "MiniMax-M3 火山方舟兼容接口",
    "upstream_model_name": "minimax-m3",
    "protocol": "chat_completions",
    "plan_id": "gateway_baseline_v1",
    "duration_ms": 127521.658
  },
  "status_counts": {
    "total": 8,
    "completed": 7,
    "error": 1,
    "skipped": 0
  },
  "metric_facts": [
    {
      "metric_id": "context_length",
      "metric_name": "上下文长度",
      "status": "error",
      "summary": "上下文长度观测发现未通过点",
      "key_facts": {
        "observed_accepted_max_prompt_tokens": 943718,
        "observed_marker_found_max_prompt_tokens": 943718,
        "first_http_error_point": 1048576,
        "first_marker_miss_point": null
      },
      "important_raw_excerpt": [
        {
          "label": "context point summary",
          "data": []
        }
      ]
    }
  ]
}
```

事实包需要满足：

- 不包含 API key。
- 不包含完整超长原始响应。
- 保留足以让分析模型解释问题的关键事实。
- 对不同指标使用统一外壳，但允许 `key_facts` 按指标定制。

### 5.3 分析结果

分析模型必须输出 JSON。建议结构：

```json
{
  "analysis_status": "completed",
  "one_sentence_summary": "本次评测基础链路可用，但仍存在需要人工复核的异常点。",
  "overall_assessment": "模型在已完成指标上表现稳定，异常指标需要结合错误类型和复测结果进一步确认。",
  "key_findings": ["连通性探测成功", "上下文长度测试存在未通过点"],
  "risks": ["部分异常可能来自网关、配额或上游模型状态，需要区分原因"],
  "recommended_next_steps": ["对异常指标进行复测", "保留原始 observations 供工程排查"],
  "metric_notes": [
    {
      "metric_id": "context_length",
      "note": "该指标存在需要人工关注的异常点。",
      "severity": "medium"
    }
  ]
}
```

`severity` 第一版只作为展示辅助，允许值：`info`、`low`、`medium`、`high`。

如果分析失败，内部结构使用：

```json
{
  "analysis_status": "error",
  "error_message": "分析模型请求失败",
  "raw_excerpt": "HTTP 500 upstream error"
}
```

## 6. 执行流程设计

现有流程：

```text
执行指标 -> 生成 Markdown 报告 -> 保存任务历史
```

新流程：

```text
执行指标
-> 构建 ReportFactPack
-> 读取 analysis_model_id
-> 调用固定报告分析模型
-> 解析结构化分析结果
-> 生成仪表盘 + 明细 Markdown 报告
-> 保存任务历史
```

流程细节：

1. 基础指标执行完成后，`TaskResult.results` 已经包含所有 `MetricResult`。
2. `ReportFactBuilder` 从 `TaskResult` 提取状态计数、核心观测和关键原始片段。
3. `ReportAnalyzer` 读取 `analysis_model_id`，创建对应 adapter。
4. `ReportAnalyzer` 向分析模型发送系统提示词和事实包。
5. 若模型返回合法 JSON，解析为 `ReportAnalysis`。
6. 若请求失败或 JSON 解析失败，构建 error 状态分析结果。
7. `write_markdown_report` 接收 `TaskResult`、`ReportFactPack`、`ReportAnalysis`，生成增强报告。
8. `TaskResult` 保存报告路径；是否把分析结果写入 task JSON 第一版可以选择写入，推荐写入，便于后续追踪分析模型输出。

## 7. 分析提示词设计

系统提示词原则：

- 使用中文输出。
- 只基于输入事实包，不臆测未提供数据。
- 不给出“上线通过/失败”的自动判定。
- 可以指出风险、异常、复测建议和需要人工确认的点。
- 输出必须是 JSON，不包裹 Markdown 代码块。
- 不输出 API key、密钥、完整原始报文。

示例要求：

```text
你是大模型 API 网关上线前评测报告分析助手。
请基于输入的结构化评测事实包，生成中文分析 JSON。
不要判断模型是否允许上线，只说明观测结果、风险点和建议下一步。
如果数据不足，请明确说明需要补测，不要编造。
```

## 8. Markdown 报告结构

第一版报告采用以下结构：

```text
# 大模型 API 评测报告 - task_20260805000000_example

## 0. LLM 分析摘要
- 分析状态
- 一句话结论
- 整体观察
- 关键发现
- 主要风险
- 建议下一步

## 1. 任务概览
- 任务 ID
- 模型配置 ID / 名称
- API model
- 协议
- 评测计划
- 开始/结束时间
- 总耗时

## 2. 指标仪表盘
- 指标总数
- completed / error / skipped 数量
- 关键观测卡片

## 3. 指标总表
| 指标 | 状态 | 核心观测 | 建议关注 |

## 4. 指标明细
每个指标一个章节：
- 指标状态
- 指标摘要
- 核心观测小表
- LLM 对该指标的备注
- 错误信息
- 原始 JSON 观测数据

## 5. 附录
- 报告事实包摘要
- 分析模型输出摘要
```

Markdown 不依赖特殊渲染器，保持 GitHub / 飞书 / 普通 Markdown 阅读器基本可读。

## 9. 指标核心事实提取规则

第一版为已有指标提供基础提取规则。

### 9.1 连通性 `connectivity`

核心事实：

- `http_status`
- `latency_ms`
- `content_present`
- `finish_reason`
- `usage_present`

### 9.2 延迟拆解 `latency_breakdown`

核心事实：

- 非流式总耗时
- 流式 TTFT
- 流式端到端耗时
- SSE 是否可解析

### 9.3 上下文长度 `context_length`

核心事实：

- `declared_context_tokens`
- `observed_accepted_max_prompt_tokens`
- `observed_marker_found_max_prompt_tokens`
- `first_http_error_point`
- `first_marker_miss_point`
- 每个点位的 `accepted_by_api`、`retrieval_ok`、`http_status`、`usage_prompt_tokens`

### 9.4 输出长度 `output_length`

核心事实：

- `requested_max_tokens`
- `output_char_count`
- `estimated_output_tokens`
- `finish_reason`
- `usage_completion_tokens`

### 9.5 并发承载 `concurrency`

核心事实：

- 并发等级列表
- 每个等级成功数、错误数、限流数
- 首个限流等级
- 延迟统计

### 9.6 限流行为 `rate_limit`

核心事实：

- 总请求数
- 限流状态码
- 限流错误类型
- 是否观测到 429

### 9.7 错误处理 `error_handling`

核心事实：

- 各错误 case 的 HTTP 状态码
- 错误结构是否存在
- error code / message 摘要

### 9.8 Token 用量观测 `token_usage_accuracy`

核心事实：

- usage 是否存在
- prompt / completion / total tokens
- 本地估算差异
- 估算器名称

### 9.9 流式规范性 `stream_spec`

核心事实：

- HTTP 状态
- TTFT
- `[DONE]` 是否存在
- finish_reason 是否存在
- chunk 是否可解析
- stream usage 是否存在

## 10. 脱敏策略

继续使用现有 `sk-***` 脱敏规则，并扩大应用范围：

- Markdown 报告全文。
- LLM 分析输入。
- LLM 分析输出。
- 错误信息摘要。
- 附录中的 JSON。

第一版至少覆盖：

- `sk-` 开头的 key。
- `ark-` 风格 key。
- 常见 `api_key` 字段值。

脱敏应在写文件前执行，避免报告中残留密钥。

## 11. 测试计划

新增或更新测试覆盖：

1. `models.json` 对象形式可读取 `analysis_model_id`。
2. 历史数组形式 `models.json` 仍兼容。
3. 有分析模型且返回合法 JSON 时，报告包含 LLM 分析摘要。
4. 未配置 `analysis_model_id` 时，报告显示未配置分析模型，任务不失败。
5. 分析模型请求失败时，报告显示分析失败，任务不失败。
6. 分析模型返回非法 JSON 时，报告显示解析失败，任务不失败。
7. 报告仪表盘包含 completed/error/skipped 计数。
8. 指标总表包含核心观测和建议关注列。
9. 报告和分析输入不会泄露 `sk-` / `ark-` 风格密钥。
10. 现有 19 个测试继续通过。

## 12. 实现边界建议

建议新增模块：

```text
app/reports/facts.py       # 从 TaskResult 构建 ReportFactPack
app/reports/analyzer.py    # 调用固定分析模型并解析结果
app/reports/schemas.py     # 报告事实包和分析结果 Pydantic 模型
```

建议修改模块：

```text
app/storage/model_store.py # 支持 analysis_model_id
app/core/runner.py         # 在报告生成前执行分析增强
app/reports/markdown.py    # 改成仪表盘 + 明细型报告
app/core/models.py         # 如需持久化分析结果，扩展 TaskResult
```

如果第一版希望减少 TaskResult 结构变动，也可以只把分析结果传给 Markdown 生成器，不写入 task JSON。但推荐写入 TaskResult，便于后续追踪和复现报告生成过程。

## 13. 风险与缓解

### 13.1 分析模型幻觉

缓解：

- 输入是结构化事实包，不直接喂杂乱全文。
- 系统提示词要求只基于事实，不做上线判定。
- 输出结构化 JSON，报告生成器控制展示形式。

### 13.2 分析模型不可用

缓解：

- 分析失败不影响任务完成。
- 报告明确记录失败原因。

### 13.3 报告过长

缓解：

- 前半部分提供摘要和仪表盘。
- 原始 JSON 放在后半部分。
- 关键原始片段限长。

### 13.4 密钥泄露

缓解：

- 扩展脱敏规则。
- 分析输入、输出、最终 Markdown 都脱敏。
- 继续忽略 `data/models.json`、`data/tasks/`、`reports/`。

## 14. 验收标准

实现完成后应满足：

1. 可以为已配置分析模型的任务生成包含 LLM 分析摘要的 Markdown 报告。
2. 报告开头能一眼看到整体观察、关键发现、主要风险和下一步建议。
3. 报告中有指标仪表盘和指标总表，不再只有原始 JSON。
4. 指标明细仍保留完整 observations/errors，方便继续查数。
5. 分析模型失败时任务不失败，报告可读且包含失败说明。
6. 自动化测试全部通过。
7. 报告不会暴露 API key。

