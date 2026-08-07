# 单服务部署指南

本项目当前推荐部署为**一个 FastAPI 主服务进程**。主服务负责模型配置、网关 smoke、EvalScope 能力评测、EvalScope perf 压测、任务归档和 Markdown 报告；能力评测与压测都在主服务进程内直接调用 EvalScope Python package，不再启动额外 HTTP 包装服务。

## 1. 部署形态

```text
LLM_Benchmark/
├── app/                  # 主服务，端口 8000
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

代码执行类能力评测（当前包括 `humaneval`、`humaneval_plus`、`mbpp`、`mbpp_plus`、`live_code_bench`）需要 EvalScope sandbox 才能执行评分。生产环境推荐使用远程 sandbox server：主服务仍保持单 FastAPI 进程，sandbox 只承担隔离代码执行，不是 EvalScope HTTP 包装服务。可复制 `data/evalscope.remote-sandbox.json.example` 为 `data/evalscope.json` 并修改内网地址：

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

`sandbox_manager_config.base_url` 只写 sandbox manager 地址，不写模型 API Key。

## 2. 安装依赖

基础服务：

```bash
uv sync
```

包含 EvalScope 能力评测、sandbox 评分与 perf 压测依赖：

```bash
uv sync --group evalscope
```

如果采用远程 sandbox，sandbox 节点也需要安装 sandbox extra 并具备 Docker：

```bash
pip install "evalscope[sandbox]"
ms-enclave server --host 0.0.0.0 --port 1234
```

建议通过内网、防火墙或安全组限制 `1234` 端口只允许主服务访问。

### Windows 依赖安装提示

如果 Windows 首次安装 EvalScope 依赖时出现 hardlink、临时 exe 或 `transformers` 权限相关错误，可先设置：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --group evalscope
```

Linux 服务器通常不需要该设置。

## 3. 启动服务

Linux：

```bash
bash scripts/start_all.sh
```

Windows PowerShell：

```powershell
.\scripts\start_all.ps1
```

默认端口：

- 主服务：`http://127.0.0.1:8000`
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
