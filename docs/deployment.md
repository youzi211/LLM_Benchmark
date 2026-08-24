# 单服务部署指南

本项目当前推荐部署为**一个 FastAPI 主服务进程**。主服务负责模型配置、网关 smoke、EvalScope 能力评测、EvalScope perf 压测、任务归档和 Markdown 报告；能力评测与压测都在主服务进程内直接调用 EvalScope Python package，不再启动额外 EvalScope HTTP 包装服务。

> 注意：FastAPI 主服务启动时只会启动内置 suite 定时调度器，不会在 `app.main` 中自动启动 EvalScope sandbox / `ms-enclave server`。MBPP/MBPP+/HumanEval 等代码执行评分需要 sandbox 时，请先把 sandbox 启动好，再在 `data/evalscope.json` 中配置 `sandbox_manager_config.base_url`；`scripts/start_all.*` 默认也不启动 sandbox，但支持显式参数在同机一并拉起。

## 1. 部署形态

```text
LLM_Benchmark/
├── app/                  # 主服务，端口 8020
├── data/                 # 本地配置和任务 JSON，不提交
├── outputs/evalscope/    # EvalScope 原始输出，不提交
├── reports/              # Markdown 报告，不提交
├── scripts/              # 启动和部署检查脚本
└── pyproject.toml        # uv 统一依赖管理
```

`data/evalscope.json` 是**可选**运行时覆盖文件。默认不创建也可以启动：

- 数据集目录默认：`data/evalscope_datasets`
- EvalScope 原始输出默认：`outputs/evalscope`
- 也可用环境变量 `LLM_BENCHMARK_EVALSCOPE_DATASETS_DIR` / `LLM_BENCHMARK_EVALSCOPE_OUTPUTS_DIR` 覆盖

只有需要固定本机目录时，才复制最小示例：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope"
}
```

需要运行依赖 LLM Judge 的数据集时，系统默认使用 `data/models.json` 顶层 `analysis_model_id` 指向的模型作为内置 Judge。若要覆盖 Judge，可在同一个可选文件额外加入 `judge_model_config_id`、`judge_generation_config`、`judge_worker_num`；Judge 地址和密钥仍只存放在 `data/models.json` 的模型配置里，不能提交。旧运行文件中的 `base_url`、超时、轮询以及旧 Judge 直连字段会被忽略。

代码执行类能力评测（当前包括 `humaneval`、`humaneval_plus`、`mbpp`、`mbpp_plus`、`live_code_bench`）需要 EvalScope sandbox 才能执行评分。生产环境推荐使用远程 sandbox server：主服务仍保持单 FastAPI 进程，sandbox 只承担隔离代码执行，不是 EvalScope HTTP 包装服务，也**不会由 FastAPI 主服务自动拉起**。`scripts/start_all.*` 默认不启动 sandbox；如果 sandbox 与主服务同机，可显式开启脚本选项作为便捷模式。远程部署时可复制 `data/evalscope.remote-sandbox.json.example` 为 `data/evalscope.json` 并修改内网地址：

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

`sandbox_manager_config.base_url` 只写 sandbox manager 地址，不写模型 API Key。无论 sandbox 是独立启动还是由 `scripts/start_all.*` 显式拉起，都仍然需要维护这个配置；启动脚本不会自动改写 `data/evalscope.json`。

## 2. 安装依赖

基础服务：

```bash
uv sync
```

包含 EvalScope 能力评测、sandbox 评分与 perf 压测依赖：

```bash
uv sync --group evalscope
```

如果采用远程 sandbox，sandbox 节点也需要安装 sandbox extra 并具备 Docker。下面命令需要在 sandbox 节点单独执行；`uvicorn app.main:app` 不会自动执行它，`scripts/start_all.*` 只有在显式开启 sandbox 参数时才会执行它：

```bash
pip install "evalscope[sandbox]"
ms-enclave server --host 0.0.0.0 --port 1234
```

建议通过内网、防火墙或安全组限制 `1234` 端口只允许主服务访问。主服务启动前可先访问 `http://<sandbox-host>:1234/health` 确认 sandbox 已经独立运行。主服务本地配置继续使用 `sandbox_enabled`、`sandbox_type`、`sandbox_manager_config` 以兼容已有部署，运行时会转换为 EvalScope 官方推荐的 `sandbox={"enabled": true, "engine": "docker", "manager_config": {...}}`。

### Windows 依赖安装提示

如果 Windows 首次安装 EvalScope 依赖时出现 hardlink、临时 exe 或 `transformers` 权限相关错误，可先设置：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --group evalscope
```

Linux 服务器通常不需要该设置。

## 3. 启动服务

Linux（默认只启动主服务）：

```bash
bash scripts/start_all.sh
```

Linux（同机显式启动 sandbox）：

```bash
START_SANDBOX=1 SANDBOX_HOST=0.0.0.0 SANDBOX_PORT=1234 MAIN_PORT=8020 bash scripts/start_all.sh
```

Windows PowerShell（默认只启动主服务）：

```powershell
.\scripts\start_all.ps1
```

Windows PowerShell（同机显式启动 sandbox）：

```powershell
.\scripts\start_all.ps1 -MainHost 0.0.0.0 -MainPort 8020 -StartSandbox -SandboxHost 0.0.0.0 -SandboxPort 1234
```

默认端口与日志：

- 主服务：`http://127.0.0.1:8020`，日志写入 `.tmp/logs/main.out.log` / `.tmp/logs/main.err.log`
- sandbox：默认不随主服务启动；如果要跑代码评分，推荐使用独立的 `ms-enclave server`，例如 `http://sandbox-host:1234`；同机便捷模式可用 `START_SANDBOX=1` 或 `-StartSandbox`，日志写入 `.tmp/logs/sandbox.out.log` / `.tmp/logs/sandbox.err.log`；无论哪种方式，都要在 `data/evalscope.json` 中配置对应 `base_url`
- EvalScope 执行模式：`in-process`，由主服务内直接 `import evalscope`

## 4. 验证部署

如果服务已经启动，运行：

```bash
uv run python scripts/test_deployment.py
```

该脚本会检查：

- `GET /health`
- `GET /api/intelligence/evalscope/health`
- `GET /api/stress/evalscope/health`

本地开发可用一键 smoke 脚本临时启动主服务并验证链路：

```bash
uv run python scripts/smoke_deploy.py
```

该脚本使用临时 `data/`、`reports/` 和 `outputs/` 目录，不会读取或修改你的真实 `data/models.json`。

## 5. 运行数据和安全

不要提交以下文件或目录：

- `data/models.json`
- `data/evalscope.json`
- `data/evalscope_datasets/`
- `data/tasks/`
- `data/intelligence_tasks/`
- `data/stress_tasks/`
- `data/overview_reports/`
- `data/suite_runs/`
- `data/suite_schedules/`
- `outputs/`
- `reports/`

`api_key` 只允许作为运行时配置存在，不能写入文档、报告或 Git 提交。API 响应、任务 JSON 和报告中的错误信息都应保持脱敏。

## 6. 后续扩展

如果未来确实要把 EvalScope 执行拆到独立机器，建议重新设计为一个明确的远程执行器插件或队列 worker，而不是恢复临时 HTTP 包装服务；届时需要同步更新 API 语义、超时、鉴权、任务状态同步和安全边界。
