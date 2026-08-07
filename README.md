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

## 部署与启动

### 运行形态先说清楚

本项目推荐部署为**一个 FastAPI 主服务进程**：

- 主服务端口默认 `8000`，负责模型配置、网关 smoke、EvalScope 能力评测、EvalScope perf 压测、任务归档和 Markdown 报告。
- EvalScope 能力评测和压测都在主服务进程内直接 `import evalscope` 执行，不再启动额外 EvalScope HTTP 包装服务。
- 主服务启动时会启动内置 suite 定时调度器；只要没有设置 `LLM_BENCHMARK_SCHEDULER_DISABLED=1`，它会轮询 `data/suite_schedules/` 并按 `next_run_at` 触发评测。
- **主服务不会自动启动 EvalScope sandbox / `ms-enclave server`。** MBPP、MBPP+、HumanEval、HumanEval+、LiveCodeBench 等代码执行评分需要 sandbox 时，必须先把 sandbox 作为独立服务启动，再在 `data/evalscope.json` 里配置它的地址。

### 1. 安装依赖

进入项目目录：

```bash
cd /opt/LLM_Benchmark
```

生产/完整评测推荐安装 EvalScope、perf 和 sandbox 相关依赖：

```bash
uv sync --group evalscope
```

如果只做网关 smoke，不跑 EvalScope 能力评测和压测，可以只安装基础依赖：

```bash
uv sync
```

Windows PowerShell 同样使用：

```powershell
cd D:\lakala\LLM_Benchmark
uv sync --group evalscope
```

### 2. 配置模型

模型配置通过 API 写入本地 `data/models.json`，也可以手工准备该文件。该文件可能包含明文 API Key，**不要提交到 Git**。

最常用方式是先启动主服务后调用：

```bash
export API_BASE=http://127.0.0.1:8000

curl -fsS -X POST "$API_BASE/api/models" \
  -H 'Content-Type: application/json' \
  -d '{
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
  }'
```

如果需要报告分析模型或 EvalScope Judge，可在 `data/models.json` 顶层配置 `analysis_model_id`，指向某个已有模型配置 ID。Judge 的 URL 和 Key 仍然只放在 `data/models.json` 的模型配置里，不放在 `data/evalscope.json`。

### 3. 可选：配置代码评分 sandbox

只有跑代码执行类数据集时才需要 sandbox，例如：

- `humaneval`
- `humaneval_plus`
- `mbpp`
- `mbpp_plus`
- `live_code_bench`

如果不配置 sandbox，这些数据集会在执行阶段返回 `sandbox_required:<dataset>`，避免出现“预测已生成但没有分数”的情况。

远程 sandbox 推荐作为独立服务启动。下面命令要在 sandbox 节点执行，不会被主服务启动脚本自动执行：

```bash
pip install "evalscope[sandbox]"
ms-enclave server --host 0.0.0.0 --port 1234
```

确认 sandbox 健康：

```bash
curl -fsS http://<sandbox-host>:1234/health
```

然后在主服务节点创建 `data/evalscope.json`，或复制 `data/evalscope.remote-sandbox.json.example` 后修改地址：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope",
  "sandbox_enabled": true,
  "sandbox_type": "docker",
  "sandbox_manager_config": {
    "base_url": "http://<sandbox-host>:1234"
  }
}
```

安全建议：通过内网、防火墙或安全组限制 `1234` 端口只允许主服务访问。

### 4. 启动主服务

Linux 直接启动：

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Linux 使用脚本启动：

```bash
MAIN_PORT=8000 bash scripts/start_all.sh
```

Windows PowerShell 直接启动：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell 使用脚本启动：

```powershell
.\scripts\start_all.ps1 -MainHost 0.0.0.0 -MainPort 8000
```

启动脚本只启动主服务，并会打印 sandbox 提醒；它不会自动执行 `ms-enclave server`。

### 5. 健康检查和部署检查

主服务健康检查：

```bash
curl -fsS http://127.0.0.1:8000/health
```

EvalScope import 健康检查：

```bash
curl -fsS http://127.0.0.1:8000/api/intelligence/evalscope/health
curl -fsS http://127.0.0.1:8000/api/stress/evalscope/health
```

如果配置了远程 sandbox，再单独检查 sandbox：

```bash
curl -fsS http://<sandbox-host>:1234/health
```

部署后可以运行内置检查脚本：

```bash
uv run python scripts/test_deployment.py --main-url http://127.0.0.1:8000
```

### 6. 定时评测

定时计划通过 API 创建，保存在本地 `data/suite_schedules/`。主服务启动后内置调度器会自动轮询到期计划。

创建每日 02:00 评测计划：

```bash
curl -fsS -X POST "$API_BASE/api/suites/schedules" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "nightly-demo-chat",
    "model_id": "demo-chat",
    "enabled": true,
    "time_of_day": "02:00",
    "timezone": "Asia/Shanghai",
    "interval_days": 1,
    "run_gateway": true,
    "run_intelligence": true,
    "run_stress": true,
    "stress_parallel": [1, 5],
    "stress_number": [10, 50],
    "timeout_seconds": 86400
  }'
```

手动触发某个计划：

```bash
curl -fsS -X POST "$API_BASE/api/suites/schedules/<schedule_id>/trigger"
```

临时关闭定时器：

```bash
export LLM_BENCHMARK_SCHEDULER_DISABLED=1
```

关闭后重启主服务才生效。

### 7. systemd 部署示例

生产环境可以用 systemd 托管主服务进程：

```ini
[Unit]
Description=LLM Benchmark API
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/LLM_Benchmark
Environment=HOST_ADDRESS=0.0.0.0
Environment=PORT=8000
# 不设置 LLM_BENCHMARK_SCHEDULER_DISABLED 时，定时 suite 会随主服务启用。
ExecStart=/usr/local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

常用管理命令：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now llm-benchmark
sudo systemctl status llm-benchmark
journalctl -u llm-benchmark -f
```

如果使用远程 sandbox，建议另建独立 systemd 服务管理 `ms-enclave server`，或者由专门的 Docker/运维系统管理；不要误以为 `llm-benchmark` 主服务会自动拉起 sandbox。

### 8. 运行目录和敏感文件

不要提交以下运行文件或目录：

```text
data/models.json
data/evalscope.json
data/tasks/
data/intelligence_tasks/
data/stress_tasks/
data/overview_reports/
data/suite_runs/
data/suite_schedules/
reports/
outputs/
.env
.venv/
```

详细部署说明见 [部署指南](docs/deployment.md)。

## 项目文档

- [系统架构说明](docs/architecture.md)：记录当前模块分层、数据流、存储结构、扩展点和 Codex 快速排查入口。
- [API 接口文档](docs/api.md)：记录所有服务接口、请求/响应结构、错误格式、协议兼容说明和调用示例。
- [指标测试方法文档](docs/metric-test-methods.md)：记录网关 smoke 指标、EvalScope 能力评测、EvalScope 压测和统一报告的测试目标、调用方式、观测字段、状态规则和人工关注点。
- [部署指南](docs/deployment.md)：记录 Linux 服务器安装、启动、健康检查和运行目录说明。
- EvalScope 智力评测接口已纳入 [API 接口文档](docs/api.md) 和 [系统架构说明](docs/architecture.md)，用于模型代码、数学、知识、推理等数据集表现评测。
- EvalScope 压测接口已纳入文档，用于获取并发、限流、延迟、TTFT/TPOT 等正式性能数据。

后续接口或指标发生新增、删除或行为变更时，必须同步更新上述文档，并检查 `README.md` 中的入口和摘要是否仍然准确。

## 可选：启动假上游服务验证完整流程

本地联调时可以启动假上游服务：

```bash
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
GET    /api/intelligence/datasets
GET    /api/intelligence/datasets/local
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

以下 API 示例默认先设置服务地址：

```bash
export API_BASE=http://127.0.0.1:8000
```

## 模型配置示例

通过 API 创建模型配置：

```bash
curl -fsS -X POST "$API_BASE/api/models" \
  -H 'Content-Type: application/json' \
  -d '{
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
  }'
```

接口响应会脱敏 `api_key`，但 `data/models.json` 会按内网测试服务假设保存本地明文密钥，请不要提交该文件。

### 报告分析模型和默认 Judge

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

- `analysis_model_id` 未配置时，网关 smoke 评测仍正常完成，Markdown 报告会显示“未配置报告分析模型”。
- 能力评测包含需要 LLM Judge 的数据集时，默认也使用 `analysis_model_id` 指向的模型作为 Judge；没有可用 Judge 时，提交阶段会返回 `400 judge_required`。
- 报告分析模型调用失败、返回非 JSON 或字段校验失败时，基础评测任务仍保持完成；报告中会记录分析失败原因和脱敏后的原始摘要。
- 分析模型可复用普通模型配置，`protocol` 需要显式指定为 `chat_completions` 或 `responses`。
- `data/models.json` 可能包含明文密钥，必须保留在本地运行目录，不要提交到 Git。

## 一键评测与定时计划

如果希望“给一个模型 ID，自动完成网关接入验收、EvalScope 能力评测、EvalScope 压测，并生成统一总览报告”，使用 Suite 接口。

默认 Suite 是当前推荐的一键测试计划，包含以下阶段：

| 阶段 | 默认接口 | 测什么 | 主要输出 |
|---|---|---|---|
| 网关 smoke | `POST /api/tasks/run`，计划 `gateway_acceptance_v1` | OpenAI 兼容协议、连通性、流式、usage、上下文、输出长度、错误结构、缓存观测等工程接入项。 | `data/tasks/` 结构化结果和 `reports/YYYY-MM-DD/` Markdown。 |
| 模型能力测试 | `POST /api/intelligence/tasks/default` | 通过 EvalScope 跑默认公开数据集，覆盖代码、数学、知识、中文和复杂推理。 | `data/intelligence_tasks/` 标准化结果、能力维度汇总、EvalScope 原始输出和 Markdown 报告。 |
| 性能压测 | `POST /api/stress/tasks/default` | 通过 EvalScope `perf` 采集并发、吞吐、延迟、TTFT/TPOT、失败率等性能数据。 | `data/stress_tasks/` 结果、`outputs/evalscope/` 原始输出和 Markdown 报告。 |
| 统一总览 | `POST /api/overview/reports` | 汇总三类任务，给出统一中文摘要和详情入口。 | `data/overview_reports/` 与 `reports/overview/` 总览报告。 |

默认模型能力数据集如下；完整元数据可通过 `GET /api/intelligence/datasets` 查询，本机已准备的数据集可通过 `GET /api/intelligence/datasets/local` 查询。

| dataset | 展示名 | 能力维度 | 说明 | 默认需要 Judge |
|---|---|---|---|---|
| `humaneval` | HumanEval | Code | 代码生成评测。 | 否 |
| `mbpp` | MBPP | Code | 基础编程题评测。 | 否 |
| `humaneval_plus` | HumanEval+ | Code | HumanEval 增强版。 | 否 |
| `mbpp_plus` | MBPP+ | Code | MBPP 增强版。 | 否 |
| `live_code_bench` | LiveCodeBench | Code | 实时代码评测。 | 否 |
| `gsm8k` | GSM8K | Math / Reasoning | 小学数学多步推理。 | 否 |
| `math_500` | MATH-500 | Math / Reasoning | 数学竞赛题。 | 否 |
| `mmlu_pro` | MMLU-Pro | Knowledge | 综合知识增强评测。 | 否 |
| `ceval` | C-Eval | Knowledge / Chinese | 中文综合能力评测。 | 否 |
| `bbh` | BBH | Reasoning | Big-Bench Hard 复杂推理。 | 否 |

默认能力测试数据集当前不需要 LLM Judge；如果调用 `POST /api/intelligence/tasks` 自定义加入 `simple_qa`、`chinese_simpleqa`、`truthful_qa`、`alpaca_eval`、`arena_hard`、`longbench_v2` 等 Judge 数据集，则会使用内置 Judge 配置，缺少 Judge 时提交阶段返回 `400 judge_required`。

> 代码类数据集虽然默认不需要 LLM Judge，但需要 EvalScope sandbox 才能评分。主服务不会自动启动 sandbox；运行 MBPP/MBPP+/HumanEval 等数据集前，请先独立启动 `ms-enclave server`，并在 `data/evalscope.json` 中配置 `sandbox_enabled=true` 和 `sandbox_manager_config.base_url`。

后台启动一键评测，接口立即返回 `suite_id`：

```bash
curl -fsS -X POST "$API_BASE/api/suites/default" \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "demo-chat",
    "title": "demo-chat full benchmark",
    "run_gateway": true,
    "run_intelligence": true,
    "run_stress": true,
    "wait_for_completion": false,
    "stress_options": {
      "parallel": [1, 5],
      "number": [10, 50]
    }
  }'
```

查询 suite 进度：

```bash
curl -fsS "$API_BASE/api/suites/<suite_id>"
```

下载最终总览报告：

```bash
curl -fsS "$API_BASE/api/suites/<suite_id>/report" -o suite-overview.md
```

如果希望调用方一直等待完成，可以设置 `wait_for_completion=true` 和超时时间：

```bash
curl -fsS -X POST "$API_BASE/api/suites/default" \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "demo-chat",
    "wait_for_completion": true,
    "poll_interval_seconds": 10,
    "timeout_seconds": 86400,
    "stress_options": {
      "parallel": [1, 5],
      "number": [10, 50]
    }
  }'
```

半夜低峰期定时评测通过 API 创建本地计划：

```bash
curl -fsS -X POST "$API_BASE/api/suites/schedules" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "nightly-demo-chat",
    "model_id": "demo-chat",
    "enabled": true,
    "time_of_day": "02:00",
    "timezone": "Asia/Shanghai",
    "interval_days": 1,
    "run_gateway": true,
    "run_intelligence": true,
    "run_stress": true,
    "stress_parallel": [1, 5],
    "stress_number": [10, 50],
    "timeout_seconds": 86400
  }'
```

定时计划保存在 `data/suite_schedules/`。主服务启动后会运行轻量轮询器，到 `next_run_at` 后自动创建 suite；最近一次 suite ID 会写回计划的 `last_suite_id`。如果需要临时关闭定时器，再设置环境变量 `LLM_BENCHMARK_SCHEDULER_DISABLED=1` 后重启服务。

## 执行网关 smoke 评测

`/api/tasks/run` 用于基础协议和工程观测，不承担正式能力评测或正式压测：

```bash
curl -fsS -X POST "$API_BASE/api/tasks/run" \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "demo-chat",
    "plan_id": "gateway_acceptance_v1"
  }'
```

读取报告：

```bash
curl -fsS "$API_BASE/api/reports/<task_id>" -o report.md
head -80 report.md
```

## EvalScope 配置与压测

压测通过 EvalScope `perf` 执行，本项目负责编排、归档和报告。通常不需要创建 `data/evalscope.json`；只有要覆盖本地目录、Judge 选择或 sandbox 地址时才使用该文件。最小示例：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope"
}
```

能力评测默认把 `data/models.json` 顶层 `analysis_model_id` 指向的模型作为内置 Judge 使用；只有要覆盖 Judge 选择时，才在可选文件中额外加入 `judge_model_config_id`、`judge_generation_config` 和 `judge_worker_num`。Judge 的地址和密钥仍只存放在 `data/models.json` 的模型配置里，不放在 `data/evalscope.json`。

提交默认压测：

```bash
curl -fsS -X POST "$API_BASE/api/stress/tasks/default" \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "demo-chat",
    "parallel": [1, 5],
    "number": [10, 50]
  }'

curl -fsS "$API_BASE/api/stress/tasks/<stress_task_id>/result"
curl -fsS "$API_BASE/api/stress/reports/<stress_task_id>" -o stress-report.md
```

## 统一总览报告

当网关接入验收、EvalScope 能力评测和 EvalScope 压测分别完成后，可以生成一份统一中文总览报告。它只做摘要、导航和归档，不重做 EvalScope 原生可视化：

```bash
curl -fsS -X POST "$API_BASE/api/overview/reports" \
  -H 'Content-Type: application/json' \
  -d '{
    "gateway_task_id": "<task_id>",
    "intelligence_task_id": "<intel_task_id>",
    "stress_task_id": "<stress_task_id>"
  }'

curl -fsS "$API_BASE/api/overview/reports/<overview_id>/markdown" -o overview-report.md
```

总览报告包含：网关接入验收摘要、能力评测摘要、压测摘要和三类详情报告入口。生产使用时更推荐直接调用 suite 接口，由 suite 自动串联三类任务并生成 overview。

## 默认网关 smoke 计划

默认网关 smoke 计划为 `gateway_acceptance_v1`，定位为“模型网关接入验收 / 协议 smoke”。历史计划名 `gateway_baseline_v1` 仍可使用，但只是兼容别名，语义等同于 `gateway_acceptance_v1`。

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
