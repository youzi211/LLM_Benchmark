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

只启动主服务：

```powershell
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开：`http://127.0.0.1:8000/docs`

健康检查：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health'
```

## 单服务部署 EvalScope

当前推荐部署方式是**一个 FastAPI 主服务进程**：能力评测和压测都在主服务进程内直接 `import evalscope` 执行，不再启动额外的 EvalScope HTTP 包装服务。

```text
LLM_Benchmark 主服务       :8000
EvalScope 执行模式         in-process（Python package）
```

安装包含 EvalScope 的依赖组：

```powershell
uv sync --group evalscope
```

`data/evalscope.json` 是可选覆盖文件。默认目录即可运行；只有需要自定义 EvalScope 数据集目录或输出目录时才复制示例：

```powershell
Copy-Item data/evalscope.json.example data/evalscope.json
```

启动主服务：

```powershell
.\scripts\start_all.ps1
```

Linux 服务器上对应命令：

```bash
bash scripts/start_all.sh
```

已启动后执行部署健康检查：

```powershell
uv run python scripts/test_deployment.py
```

本地开发也可以临时拉起测试端口并自动检查：

```powershell
uv run python scripts/smoke_deploy.py
```

详细说明见 [单服务部署指南](docs/deployment.md)。

## 项目文档

- [系统架构说明](docs/architecture.md)：记录当前模块分层、数据流、存储结构、扩展点和 Codex 快速排查入口。
- [API 接口文档](docs/api.md)：记录所有服务接口、请求/响应结构、错误格式、协议兼容说明和调用示例。
- [指标测试方法文档](docs/metric-test-methods.md)：记录默认评测计划中每个指标的测试目标、调用方式、观测字段、状态规则和人工关注点。
- [单服务部署指南](docs/deployment.md)：记录主服务内直接调用 EvalScope Python package 的安装、启动和验证方法。
- EvalScope 智力评测接口已纳入 [API 接口文档](docs/api.md) 和 [系统架构说明](docs/architecture.md)，用于模型代码、数学、知识、推理等数据集表现评测。
- EvalScope 压测接口已纳入文档，默认在主服务进程内调用 EvalScope `perf`，获取并发、限流、延迟、TTFT/TPOT 等正式性能数据。

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

GET    /api/intelligence/evalscope/health
POST   /api/intelligence/tasks/default
POST   /api/intelligence/tasks
GET    /api/intelligence/tasks
GET    /api/intelligence/tasks/{task_id}
GET    /api/intelligence/tasks/{task_id}/result
GET    /api/intelligence/reports/{task_id}

GET    /api/stress/evalscope/health
POST   /api/stress/tasks/default
POST   /api/stress/tasks
GET    /api/stress/tasks
GET    /api/stress/tasks/{task_id}
GET    /api/stress/tasks/{task_id}/result
GET    /api/stress/reports/{task_id}

POST   /api/overview/reports
GET    /api/overview/reports
GET    /api/overview/reports/{overview_id}
GET    /api/overview/reports/{overview_id}/markdown

POST   /api/suites/default
GET    /api/suites
GET    /api/suites/{suite_id}
GET    /api/suites/{suite_id}/report
POST   /api/suites/schedules
GET    /api/suites/schedules
GET    /api/suites/schedules/{schedule_id}
DELETE /api/suites/schedules/{schedule_id}
POST   /api/suites/schedules/{schedule_id}/trigger
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

## 一键评测与定时计划

如果希望“给一个模型 ID，自动完成网关接入验收、EvalScope 能力评测、EvalScope 压测，并生成统一总览报告”，使用 Suite 接口：

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
$suite = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/suites/default' -Method Post -ContentType 'application/json' -Body $suiteBody
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/suites/$($suite.suite_id)/report" -OutFile suite-overview.md
```

默认 `wait_for_completion = $false`，接口会立即返回 `suite_id` 并在后台执行，可用以下接口查看进度：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/suites/$($suite.suite_id)" | ConvertTo-Json -Depth 20
```

半夜低峰期定时评测可以创建本地计划：

```powershell
$scheduleBody = @{
  name = 'nightly-demo-chat'
  model_id = 'demo-chat'
  time_of_day = '02:00'
  timezone = 'Asia/Shanghai'
  interval_days = 1
  stress_parallel = @(1, 5)
  stress_number = @(10, 50)
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/suites/schedules' -Method Post -ContentType 'application/json' -Body $scheduleBody | ConvertTo-Json -Depth 20
```

定时计划保存在 `data/suite_schedules/`。主服务启动后会运行轻量轮询器，到 `next_run_at` 后自动创建 suite；最近一次 suite ID 会写回计划的 `last_suite_id`。
## 执行评测

```powershell
$runBody = @{ model_id = 'demo-chat'; plan_id = 'gateway_acceptance_v1' } | ConvertTo-Json
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/tasks/run' -Method Post -ContentType 'application/json' -Body $runBody
$result | ConvertTo-Json -Depth 20
$taskId = $result.task_id
```

读取报告：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/reports/$taskId" -OutFile report.md
Get-Content .\report.md -Encoding UTF8 | Select-Object -First 80
```


## EvalScope 压测

压测由主服务进程内直接调用 EvalScope `perf` 执行，本项目负责编排、归档和报告。通常不需要创建 `data/evalscope.json`；只有要覆盖本地目录时才使用这个最小示例：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope"
}
```

能力评测如果要启用需要 LLM Judge 的数据集，可在同一个可选文件中额外加入 `judge_model_id`、`judge_api_url`、`judge_api_key`、`judge_generation_config` 和 `judge_worker_num`。

提交默认压测：

```powershell
$stressBody = @{ model_id = 'demo-chat'; parallel = @(1, 5); number = @(10, 50) } | ConvertTo-Json
$stress = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/stress/tasks/default' -Method Post -ContentType 'application/json' -Body $stressBody
$stressTaskId = $stress.task_id
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/stress/tasks/$stressTaskId/result" | ConvertTo-Json -Depth 20
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stress/reports/$stressTaskId" -OutFile stress-report.md
```

## 统一总览报告

当网关接入验收、EvalScope 能力评测和 EvalScope 压测分别完成后，可以生成一份统一中文总览报告。它只做摘要、导航和归档，不重做 EvalScope 原生可视化：

```powershell
$overviewBody = @{
  gateway_task_id = $taskId
  intelligence_task_id = '<intel-task-id>'
  stress_task_id = $stressTaskId
} | ConvertTo-Json
$overview = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/overview/reports' -Method Post -ContentType 'application/json' -Body $overviewBody
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/overview/reports/$($overview.overview_id)/markdown" -OutFile overview-report.md
```

总览报告包含：网关接入验收摘要、能力评测摘要、压测摘要和三类详情报告入口。

## 默认评测计划

默认计划为 `gateway_acceptance_v1`，定位为“模型网关接入验收 / 协议 smoke”。历史计划名 `gateway_baseline_v1` 仍可使用，但只是兼容别名，语义等同于 `gateway_acceptance_v1`。

`metric_id` 保持英文，便于 API、脚本和历史数据稳定；报告和指标元数据使用中文名 + 英文 ID 的双语展示。

| 中文名 | metric_id | 说明 |
|---|---|---|
| 连通性 | `connectivity` | 检查接口是否可访问、是否返回内容、finish_reason 和 usage 等基础字段。 |
| 延迟拆解 | `latency_breakdown` | 单次流式 smoke，采集 TTFT、端到端耗时、流式输出时长和估算吞吐；正式延迟/吞吐以 EvalScope 压测为准。 |
| 上下文长度 | `context_length` | 分档构造长上下文，观察 marker 找回和当前网关链路可用上下文能力。 |
| 输出长度 | `output_length` | 观察指定 max_tokens 下的实际输出长度、finish_reason 和 usage。 |
| 错误处理 | `error_handling` | 检查无效 key、无效模型、空输入、非法参数、上下文超限等错误结构。 |
| Token 用量观测（Usage） | `token_usage_accuracy` | 观察 usage token 字段，并与本地估算值做辅助对比。 |
| 缓存能力（Prompt Cache） | `cache_behavior` | 通过长稳定前缀冷/热请求观察缓存字段、cached tokens、命中轮次和延迟变化。 |
| 流式规范性 | `stream_spec` | 检查 SSE 可解析、[DONE]、finish_reason 和流式 usage。 |

`concurrency` 与 `rate_limit` 作为历史兼容的轻量性能 smoke 指标保留，可通过 `metric_ids` 显式运行，但不再属于默认接入验收计划；正式并发、吞吐、延迟分位数和限流/容量边界请使用 EvalScope 压测 `/api/stress/*`。

状态语义：

- `completed`：指标执行完成并采集到观测数据。
- `error`：请求、协议、结构或必要字段存在明确异常。
- `skipped`：缺少必要配置，当前指标跳过。

## 存储布局

```text
data/
  models.json          # 本地模型配置，可能包含明文 API Key，不要提交
  evalscope.json      # 可选 EvalScope 本地覆盖配置，不要提交
  tasks/
    task_xxx.json      # 基础工程评测任务结构化结果
  intelligence_tasks/
    intel_task_xxx.json # 智力评测任务结构化结果
  stress_tasks/
    stress_task_xxx.json # 压测任务结构化结果

reports/
  YYYY-MM-DD/
    task_xxx.md        # 基础工程评测 Markdown 报告
  intelligence/YYYY-MM-DD/
    intel_task_xxx.md  # 智力评测 Markdown 报告
  stress/YYYY-MM-DD/
    stress_task_xxx.md # 压测 Markdown 报告
```

## Token 用量观测（Usage）说明

报告中本地 token 数为启发式估算值，仅用于辅助观察，不作为自动判定依据。
