# EvalScope 集成架构优化设计

日期：2026-08-24  
状态：草案  
范围：`D:\lakala\LLM_Benchmark` 中 EvalScope 能力评测、EvalScope perf 压测、一键 suite 与定时评测的架构边界优化。  
非目标：本设计不改变网关 smoke 指标语义，不引入外部队列中间件，不把 EvalScope 重新包装为独立 HTTP sidecar。

## 1. 背景与问题陈述

当前系统定位是内部 LLM 网关预发布评测服务，包含三条评测 lane：

1. 网关 smoke：轻量 OpenAI-compatible API 工程验收。
2. EvalScope intelligence：通过 EvalScope 运行能力 benchmark。
3. EvalScope stress：通过 EvalScope perf 运行吞吐、延迟、TTFT/TPOT 等压测。

仓库目前已经采用“FastAPI 主进程内直接 import EvalScope Python package”的路线，这比额外维护 EvalScope HTTP 包装服务更直接，方向正确。问题不在于接入 EvalScope 的大方向，而在于服务层逐步累积了较多自研编排能力：任务状态、后台线程、定时触发、suite 轮询、结果标准化、报告聚合、sandbox/Judge 配置、默认数据集选择散落在多个模块中。

由此带来的主要风险：

- 定时任务触发成功与实际评测成功容易混淆。
- `scheduler -> suite -> intelligence/stress thread -> EvalScope` 形成多层异步/后台执行，故障定位困难。
- 定时任务默认跑较重的数据集，尤其代码执行类 benchmark 依赖 sandbox，部署环境稍有缺口即失败。
- 部分 EvalScope 配置仍使用 legacy 字段，例如 `use_sandbox` / `sandbox_type` / `sandbox_manager_config`。
- 业务系统对 EvalScope 原始结果结构做了较深二次解析，未来 EvalScope 版本变更时维护成本较高。
- `wait_for_completion` 在定时任务中的语义与测试断言不一致，说明接口语义尚未完全收敛。

## 2. 官方 EvalScope 集成边界

对照 EvalScope 官方用法，推荐边界如下：

- 能力评测：构造 `TaskConfig`，传入 `model`、`api_url`、`api_key`、`datasets`、`dataset_args`、`limit`、`eval_batch_size`、`generation_config`、`work_dir` 等，然后调用 `run_task(task_cfg=...)`。
- OpenAI-compatible API：可通过 `eval_type='openai_api'` 或提供 `api_url` 走服务模式评测。
- perf 压测：构造 `evalscope.perf.arguments.Arguments`，传入 `parallel`、`number`、`model`、`url`、`api`、`dataset`、token 长度等参数，然后调用 `run_perf_benchmark(...)`。
- sandbox：HumanEval、MBPP 等代码执行类 benchmark 需要 sandbox。EvalScope 当前更推荐统一 `sandbox={"enabled": true, "engine": "docker", "manager_config": {...}}` 结构；旧的 `use_sandbox` / `sandbox_type` / `sandbox_manager_config` 仍可兼容，但应逐步迁移。

因此本项目应保持“薄适配层”：业务系统负责模型配置、评测 profile、触发、状态、摘要和归档；EvalScope 负责正式 benchmark/perf 执行、dataset 加载、评分与原始输出。

## 3. 设计目标

1. 保持当前单 FastAPI 服务部署形态，不新增 EvalScope sidecar。
2. 降低定时评测失败概率，使默认定时任务更轻、更可诊断。
3. 把 EvalScope 参数从散落硬编码收敛为 profile 配置。
4. 统一后台任务执行模型，避免多层异步和 daemon thread 难以追踪。
5. 提升 schedule 与 suite 的可观测性，让“触发失败”和“执行失败”清晰分离。
6. 保留现有 API 的兼容性，允许渐进迁移。

## 4. 目标职责边界

### 4.1 本系统负责

- 模型配置管理：模型 ID、base URL、API Key、协议、超时时间、上下文声明等。
- 评测 profile：定义轻量定时、代码评测、完整离线评测等预设。
- 任务提交与状态持久化：保存 job/suite/intelligence/stress 的状态与错误摘要。
- 定时触发：按照 `next_run_at` 投递评测 job。
- 中文总览：从子任务中抽取少量核心指标，生成业务可读报告。
- 安全与脱敏：API Key 不进入响应、报告、日志和 Git。

### 4.2 EvalScope 负责

- benchmark dataset 加载和缓存。
- prompt/evaluator/metric 逻辑。
- 代码执行 benchmark 的 sandbox 评分。
- perf 压测执行和原始性能指标。
- 原始输出目录、原生报告和底层日志。

## 5. 目标架构

```text
FastAPI
  |
  |-- models
  |     |-- ModelStore
  |
  |-- evalscope
  |     |-- EvalScopeService
  |     |     |-- build_intelligence_task_config()
  |     |     |-- run_intelligence()
  |     |     |-- build_perf_arguments()
  |     |     |-- run_stress()
  |     |     |-- health()
  |     |
  |     |-- EvalScopeProfileStore
  |           |-- scheduled_light
  |           |-- scheduled_code
  |           |-- full_offline
  |
  |-- jobs
  |     |-- JobStore
  |     |-- JobExecutor
  |     |-- due schedule dispatcher
  |
  |-- suites
  |     |-- SuiteRunner as thin orchestrator
  |
  |-- reports
        |-- overview summary
        |-- links to EvalScope raw outputs
```

核心原则：**不要复制 EvalScope 的评测能力，只在边界处做配置映射、状态归档和摘要提取。**

## 6. Profile 化配置

### 6.1 动机

当前默认数据集和默认参数分散在代码中：

- `DEFAULT_DATASETS`
- `DEFAULT_EVAL_BATCH_SIZE`
- `DEFAULT_GENERATION_CONFIG`
- `DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT`
- `StressRemoteSubmitPayload` 的默认 `parallel`、`number`、`dataset`、token 长度等

这些默认值不应全部内嵌在代码里，尤其定时任务默认不应直接跑 sandbox-heavy 数据集。

### 6.2 推荐 profile

新增可配置 profile，例如放在 `data/evalscope_profiles.json`，或先放在 `data/evalscope.json` 的 `profiles` 字段中。

```json
{
  "profiles": {
    "scheduled_light": {
      "description": "每日/定时轻量评测，默认不依赖 sandbox",
      "run_gateway": true,
      "run_stress": true,
      "run_intelligence": true,
      "intelligence": {
        "datasets": ["gsm8k", "math_500", "ceval"],
        "limit": 50,
        "eval_batch_size": 5,
        "generation_config": {
          "temperature": 0.0,
          "max_tokens": 8192
        }
      },
      "stress": {
        "dataset": "random",
        "parallel": [1, 2, 5],
        "number": [10, 20, 50],
        "stream": true,
        "min_prompt_length": 1024,
        "max_prompt_length": 1024,
        "min_tokens": 512,
        "max_tokens": 512
      }
    },
    "scheduled_code": {
      "description": "代码能力定时评测，需要 sandbox 健康可用",
      "requires_sandbox": true,
      "run_gateway": false,
      "run_stress": false,
      "run_intelligence": true,
      "intelligence": {
        "datasets": ["humaneval", "mbpp"],
        "limit": 20,
        "eval_batch_size": 2
      }
    },
    "full_offline": {
      "description": "人工触发的较完整离线评测",
      "run_gateway": true,
      "run_stress": true,
      "run_intelligence": true,
      "intelligence": {
        "datasets": [
          "humaneval",
          "mbpp",
          "humaneval_plus",
          "mbpp_plus",
          "live_code_bench",
          "gsm8k",
          "math_500",
          "mmlu_pro",
          "ceval",
          "bbh"
        ],
        "limit": null
      }
    }
  }
}
```

### 6.3 API 兼容策略

保留现有 schedule 创建字段，同时新增：

```json
{
  "profile": "scheduled_light"
}
```

解析优先级：

1. 请求显式字段优先。
2. profile 默认值其次。
3. 代码兜底默认值最后。

这样不破坏现有调用方。

## 7. 定时任务与 suite 状态模型

### 7.1 明确语义

- Schedule 只表示计划和触发情况。
- Suite 表示某一次评测执行。
- `schedule.last_error` 只记录调度阶段错误，例如创建 suite 失败、配置无法解析、模型不存在等。
- suite 执行失败不应写成 schedule 调度失败，而应通过 `last_suite_id` 关联查看。

### 7.2 推荐新增字段或接口

方案 A：在 schedule 响应中物化最近一次 suite 摘要：

```json
{
  "last_suite_id": "suite_xxx",
  "last_suite_status": "partial",
  "last_suite_current_step": null,
  "last_suite_error_count": 2,
  "last_suite_errors": [
    {"step": "stress", "message": "..."},
    {"step": "intelligence", "message": "..."}
  ]
}
```

方案 B：新增接口：

```text
GET /api/suites/schedules/{schedule_id}/last-run
```

返回 schedule + last suite + 子任务摘要。建议优先做方案 B，避免改变 schedule 存储结构太多。

### 7.3 定时任务执行方式

建议固定语义：

```text
定时 schedule 永远异步投递 suite，不阻塞 scheduler。
手动 default/quick 接口由 wait_for_completion 控制是否阻塞。
```

因此 `SuiteScheduleCreate.to_run_request()` 中 `wait_for_completion=False` 是合理的，但测试和文档必须同步。

## 8. 统一 JobExecutor

### 8.1 当前问题

当前执行链路类似：

```text
scheduler asyncio.create_task()
  -> SuiteRunner.execute()
    -> StressRunner.submit_default()
      -> threading.Thread(... daemon=True)
    -> SuiteRunner 轮询 stress task JSON
    -> IntelligenceRunner.submit_default()
      -> threading.Thread(... daemon=True)
    -> SuiteRunner 轮询 intelligence task JSON
```

风险：

- 多层后台执行导致异常路径分散。
- daemon thread 在进程退出时可能直接中断。
- 无全局并发限制。
- 多个 schedule 同时到期时可能同时跑多个重任务。
- scheduler 无法直接知道后台 suite 失败。

### 8.2 目标模型

新增进程内 `JobExecutor`，不要一开始引入 Celery/Redis。

```text
JobExecutor
  - submit(job_type, payload)
  - run pending jobs with max concurrency
  - persist job status
  - capture exception traceback summary
  - graceful shutdown waits or marks interrupted
```

最小 Job 类型：

```text
suite
intelligence
stress
```

可选策略：

- suite job 负责串行调用 gateway、stress、intelligence、overview。
- intelligence/stress 不再自行开 daemon thread，改为由 JobExecutor 调用同步执行函数。
- 初期可设置 `max_concurrent_suites=1`，避免定时任务并发打爆网关或 EvalScope。

## 9. EvalScopeService 薄适配层

### 9.1 Intelligence

当前 `EvalScopeIntelligenceExecutor` 可保留，但建议改名或收敛到 `EvalScopeService` 下，并只做：

1. 从业务模型构造 `TaskConfig` dict。
2. 调用 `run_task`。
3. 保存原始结果和输出目录。
4. 抽取 overview 所需摘要。

避免在业务层复刻 EvalScope 的完整报告结构。

### 9.2 Stress

当前 `EvalScopeStressExecutor` 已经较薄，方向正确。建议保留：

```python
Arguments(**data)
run_perf_benchmark(args)
```

但把结果处理改成：

- 原始结果完整保存。
- 标准化只抽取 overview 和列表页需要的字段。
- 详细档位和百分位表尽量链接 EvalScope 原始输出，而不是深度二次建模。

## 10. Sandbox 配置迁移

当前内部配置可保持：

```json
{
  "sandbox_enabled": true,
  "sandbox_type": "docker",
  "sandbox_manager_config": {
    "base_url": "http://sandbox-host:1234"
  }
}
```

但传给 EvalScope 的 `TaskConfig` 应改成官方推荐结构：

```python
data["sandbox"] = {
    "enabled": True,
    "engine": self.config.sandbox_type or "docker",
    "manager_config": dict(self.config.sandbox_manager_config or {}),
}
```

旧字段不再主动生成。这样可以降低未来 EvalScope 版本移除 legacy 字段时的风险。

## 11. 错误处理与可诊断性

### 11.1 健康检查前置

提交 scheduled profile 前，建议检查：

- EvalScope import 是否可用。
- profile 是否引用代码执行数据集。
- 如需要 sandbox，则 sandbox 配置是否存在。
- 如配置了远程 sandbox，则可选检查 `base_url` `/health`。
- 如引用 LLM Judge 数据集，则 Judge 模型是否存在且启用。

### 11.2 错误分类

错误建议统一归类为：

```text
configuration_error
missing_dependency
sandbox_unavailable
dataset_unavailable
model_unavailable
upstream_api_error
evalscope_runtime_error
timeout
internal_error
```

每个任务保存：

```json
{
  "code": "sandbox_unavailable",
  "message": "...脱敏后的短消息...",
  "step": "intelligence",
  "cause": "...可选..."
}
```

### 11.3 报告原则

- API 响应、报告和日志不得暴露 API Key。
- overview 只保留摘要和定位链接。
- 原始 EvalScope 输出路径应记录，但不要复制大表到 overview。

## 12. API 兼容与迁移

### 12.1 保持兼容的接口

继续保留：

```text
POST /api/intelligence/tasks/default
POST /api/intelligence/tasks
GET  /api/intelligence/tasks/{task_id}
GET  /api/intelligence/reports/{task_id}

POST /api/stress/tasks/default
POST /api/stress/tasks
GET  /api/stress/tasks/{task_id}
GET  /api/stress/reports/{task_id}

POST /api/suites/default
POST /api/suites/quick
POST /api/suites/schedules
GET  /api/suites/schedules
POST /api/suites/schedules/{schedule_id}/trigger
GET  /api/suites/{suite_id}
GET  /api/suites/{suite_id}/report
```

### 12.2 新增接口建议

```text
GET /api/evalscope/profiles
GET /api/evalscope/profiles/{profile_id}
GET /api/suites/schedules/{schedule_id}/last-run
GET /api/jobs/{job_id}
```

### 12.3 废弃策略

- 不立刻删除现有字段。
- 新增 `profile` 后，现有 `run_gateway`、`run_intelligence`、`run_stress`、`stress_options`、`intelligence_limit` 仍可覆盖 profile。
- 对 legacy sandbox 字段只在内部配置保留，不再透传给 EvalScope。

## 13. 实施优先级

### P0：语义修复与可观测性

目标：让现有定时任务更容易定位失败，不做大重构。

- 明确定时任务 `wait_for_completion=False`。
- 修复测试中仍期望 `wait_for_completion=True` 的断言。
- 为 schedule 增加 last-run 查询接口，或在 schedule 列表中附带最近 suite 状态摘要。
- `asyncio.create_task` 增加 done callback，记录后台 suite 未捕获异常。
- 更新 README、`docs/api.md`、`docs/model-evaluation-integration.md`。

验证：

```powershell
$env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
uv run pytest -q tests/test_suites_api.py tests/test_suite_runner.py
uv run pytest -q
```

### P1：Profile 化定时评测

目标：降低定时失败概率。

- 新增 EvalScope profile schema/store。
- 提供 `scheduled_light` 默认 profile。
- schedule 创建支持 `profile`。
- 前端创建定时任务默认使用 `scheduled_light`。
- 文档说明 full/code profile 需要 sandbox。

验证：

- 创建 `scheduled_light` 定时计划。
- 到期触发后不依赖 sandbox 即可完成或至少不会因 sandbox_required 失败。
- 显式选择 `scheduled_code` 时，如果 sandbox 未配置，创建或触发阶段给出清晰错误。

### P2：Sandbox 配置迁移

目标：对齐 EvalScope 当前推荐配置。

- `TaskConfig` 构造改为 `sandbox={...}`。
- 保留读取 `data/evalscope.json` 中现有 `sandbox_enabled`、`sandbox_type`、`sandbox_manager_config`。
- 增加单元测试验证传给 EvalScope 的 dict 使用 `sandbox`，不再使用 legacy 字段。

### P3：统一 JobExecutor

目标：降低后台执行复杂度。

- 新增进程内 JobStore/JobExecutor。
- intelligence/stress runner 提供同步执行入口，由 JobExecutor 调用。
- suite job 串行执行子步骤。
- scheduler 只提交 suite job，不直接 `asyncio.create_task(runner.execute(...))`。
- 支持最大并发限制和优雅关闭。

### P4：减少结果二次建模

目标：降低 EvalScope 版本漂移成本。

- 原始 EvalScope 输出完整归档。
- overview 只抽取必要指标。
- 复杂明细通过原始报告路径跳转。
- 删除或收敛重复标准化逻辑。

## 14. 风险与权衡

- 不引入外部队列的好处是部署简单；代价是进程重启时仍可能中断运行中任务。短期接受，长期如果需要高可靠定时任务，再考虑 Redis/Celery/RQ/APScheduler 持久 job store。
- Profile 化会增加一层配置概念，但能显著降低默认任务过重和参数散落问题。
- 保留现有 API 兼容会让一段时间内新旧字段并存，需要文档明确优先级。
- 减少结果二次建模后，前端能展示的明细可能减少；但长期维护成本更低。

## 15. 推荐决策

推荐采取渐进式优化：

1. 立即做 P0，解决语义不一致和诊断困难。
2. 接着做 P1，让服务器定时任务默认使用轻量 profile。
3. 同步做 P2，迁移 sandbox 参数结构。
4. 稳定后再做 P3，不急于一次性重构后台任务系统。
5. P4 随 EvalScope 版本升级和报告需求变化逐步推进。

最终定位保持为：

> LLM Gateway Benchmark Portal：负责模型配置、评测预设、定时触发、结果归档和中文摘要；EvalScope 负责正式 benchmark 与 perf 执行。
