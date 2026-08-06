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

`data/evalscope.json` 只保存本地 EvalScope 执行配置，例如数据集目录、输出目录、超时和可选 Judge 配置：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope",
  "poll_interval_seconds": 5,
  "default_timeout_seconds": 14400,
  "stress_timeout_seconds": 86400,
  "judge_model_id": "",
  "judge_api_url": "",
  "judge_api_key": "",
  "judge_generation_config": {
    "temperature": 0.0,
    "max_tokens": 4096
  },
  "judge_worker_num": 5,
  "ignore_dataset_errors": true
}
```

历史版本中的 `base_url` 字段仍会被兼容读取，但当前不会再用于访问 EvalScope HTTP 包装服务。

## 2. 安装依赖

基础服务：

```bash
uv sync
```

包含 EvalScope 能力评测与 perf 压测依赖：

```bash
uv sync --group evalscope
```

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
