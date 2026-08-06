# 大模型 API 评测服务（LLM Benchmark）

内部大模型 API 基础工程评测服务，用于模型接入模型网关前验证。

本服务不是公开 SaaS，也不输出“上线通过 / 失败”结论；它负责采集基础工程评测指标，相关人员基于 JSON 结果和 Markdown 报告自行分析。

## 技术栈

- Python 环境管理：uv
- Web 框架：FastAPI
- HTTP 调用：httpx
- 存储：本地 JSON 文件
- 报告：Markdown
- V1 不使用 SQL、不做平台鉴权、不使用 OpenAI Python SDK

## 快速启动

```powershell
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开：`http://127.0.0.1:8000/docs`

健康检查：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
```

## 项目文档

- [系统架构说明](docs/architecture.md)：记录当前模块分层、数据流、存储结构、扩展点和 Codex 快速排查入口。
- [API 接口文档](docs/api.md)：记录所有服务接口、请求/响应结构、错误格式、协议兼容说明和调用示例。
- [指标测试方法文档](docs/metric-test-methods.md)：记录默认评测计划中每个指标的测试目标、调用方式、观测字段、状态规则和人工关注点。
- EvalScope 智力评测接口已纳入 [API 接口文档](docs/api.md) 和 [系统架构说明](docs/architecture.md)，用于模型代码、数学、知识、推理等数据集表现评测。

后续接口或指标发生新增、删除或行为变更时，必须同步更新上述文档，并检查 `README.md` 中的入口和摘要是否仍然准确。

## 可选：启动假上游服务验证完整流程

另开一个 PowerShell：

```powershell
uv run uvicorn examples.fake_openai_server:app --host 127.0.0.1 --port 9001
```

然后将模型 `base_url` 配成 `http://127.0.0.1:9001/v1`。

## API

```http
POST   /api/models
GET    /api/models
GET    /api/models/{model_id}
PUT    /api/models/{model_id}
DELETE /api/models/{model_id}

GET    /api/metrics
GET    /api/plans
GET    /api/plans/{plan_id}

POST   /api/tasks/run
GET    /api/tasks
GET    /api/tasks/{task_id}

GET    /api/reports/{task_id}
```

## 模型配置示例

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

Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/models' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 10
```

接口响应会脱敏 `api_key`，但 `data/models.json` 会按内网测试服务假设保存本地明文密钥，请不要提交该文件。

### 报告分析模型配置

报告生成阶段可以额外调用一个固定的“报告分析模型”，基于结构化评测事实包生成中文摘要、关键发现、风险点和建议下一步。该步骤只做辅助分析，不改变基础评测任务状态，也不输出“上线通过 / 失败”结论。

在 `data/models.json` 顶层配置 `analysis_model_id`，指向 `models` 数组中的某个模型配置 ID：

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
      "concurrency_levels": [1]
    }
  ]
}
```

说明：

- `analysis_model_id` 未配置时，评测仍正常完成，Markdown 报告会显示“未配置报告分析模型”。
- 报告分析模型调用失败、返回非 JSON 或字段校验失败时，基础评测任务仍保持完成；报告中会记录分析失败原因和脱敏后的原始摘要。
- 分析模型可复用普通模型配置，`protocol` 需要显式指定为 `chat_completions` 或 `responses`。
- `data/models.json` 可能包含明文密钥，必须保留在本地运行目录，不要提交到 Git。

## 执行评测

```powershell
$runBody = @{ model_id = 'demo-chat'; plan_id = 'gateway_baseline_v1' } | ConvertTo-Json
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/tasks/run' -Method Post -ContentType 'application/json' -Body $runBody
$result | ConvertTo-Json -Depth 20
$taskId = $result.task_id
```

读取报告：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/reports/$taskId" -OutFile report.md
Get-Content .\report.md -Encoding UTF8 | Select-Object -First 80
```

## 默认评测计划

`gateway_baseline_v1` 包含以下指标。`metric_id` 保持英文，便于 API、脚本和历史数据稳定；报告和指标元数据使用中文名 + 英文 ID 的双语展示。

| 中文名 | metric_id | 说明 |
|---|---|---|
| 连通性 | `connectivity` | 检查接口是否可访问、是否返回内容、finish_reason 和 usage 等基础字段。 |
| 延迟拆解 | `latency_breakdown` | 采集 TTFT、端到端耗时、流式输出时长和估算吞吐。 |
| 上下文长度 | `context_length` | 分档构造长上下文，观察 marker 找回和当前网关链路可用上下文能力。 |
| 输出长度 | `output_length` | 观察指定 max_tokens 下的实际输出长度、finish_reason 和 usage。 |
| 并发承载 | `concurrency` | 按并发档位统计成功、失败和延迟分布。 |
| 限流行为 | `rate_limit` | 观察 429 或其他明确限流信号。 |
| 错误处理 | `error_handling` | 检查无效 key、无效模型、空输入、非法参数、上下文超限等错误结构。 |
| Token 用量观测（Usage） | `token_usage_accuracy` | 观察 usage token 字段，并与本地估算值做辅助对比。 |
| 流式规范性 | `stream_spec` | 检查 SSE 可解析、[DONE]、finish_reason 和流式 usage。 |

状态语义：

- `completed`：指标执行完成并采集到观测数据。
- `error`：请求、协议、结构或必要字段存在明确异常。
- `skipped`：缺少必要配置，当前指标跳过。

## 存储布局

```text
data/
  models.json          # 本地模型配置，可能包含明文 API Key，不要提交
  tasks/
    task_xxx.json      # 任务结构化结果

reports/
  YYYY-MM-DD/
    task_xxx.md        # 人可读 Markdown 报告
```

## Token 用量观测（Usage）说明

报告中本地 token 数为启发式估算值，仅用于辅助观察，不作为自动判定依据。
