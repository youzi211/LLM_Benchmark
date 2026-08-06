# EvalScope 智力评测接入设计（in-process 版）

> 日期：2026-08-06
> 状态：已按用户反馈收缩为主服务内直接调用 EvalScope Python package。

## 1. 背景

LLM Benchmark 服务主要负责模型网关上线前的基础工程评测。EvalScope 提供代码、数学、知识、推理、QA、长文本等公开数据集能力评测。本设计将 EvalScope 作为独立“能力评测模块”接入当前系统，但不放入 `gateway_acceptance_v1` 基础工程指标中。

## 2. 目标与非目标

### 目标

- 通过当前系统使用已有 `model_id` 发起 EvalScope 默认评测或自定义数据集评测。
- 支持查询本地 EvalScope package 健康状态、本地数据集和支持数据集。
- 保存本系统能力评测任务、标准化结果和 Markdown 报告。
- 报告展示数据集分数、能力维度汇总、原始 `report_table` 和注意事项。
- 保留 EvalScope 原始输出在 `outputs/evalscope/intelligence/`，便于排查。

### 非目标

- 第一版不把能力评测合并进 `/api/tasks/run`。
- 第一版不把能力评测作为 `gateway_acceptance_v1` 的普通 metric。
- 第一版不代理写 Judge 密钥；Judge 默认复用 `data/models.json` 顶层 `analysis_model_id`，也可用可选 `data/evalscope.json` 的 `judge_model_config_id` 覆盖。
- 第一版不输出“上线通过 / 失败”的自动结论。

## 3. 当前方案

采用独立模块 `/api/intelligence/*`，主服务进程内直接调用 `evalscope.run_task(TaskConfig)`。

理由：

- EvalScope 输出是多数据集、多能力维度结果，结构与 `MetricResult` 不同。
- 独立模块能保持当前基础工程评测稳定。
- 直接 import EvalScope 避免额外 HTTP 包装带来的启动、轮询、错误处理和状态同步复杂度。

## 4. 模块结构

```text
app/
  intelligence/
    __init__.py
    schemas.py              # 能力评测请求、任务、结果模型
    evalscope_direct.py     # EvalScope 直接调用执行器
    runner.py               # 模型读取、执行、结果标准化
    report.py               # 能力评测 Markdown 报告生成
  api/
    routes_intelligence.py  # /api/intelligence/* 路由
  storage/
    intelligence_task_store.py
```

继续复用：

- `app/storage/model_store.py`：读取被评测模型配置。
- `app/reports/markdown.py` / `app/utils/masking.py`：脱敏输出。

## 5. 配置与存储

`data/evalscope.json` 是可选本地覆盖文件，不创建时使用默认数据集目录和输出目录：

```json
{
  "datasets_dir": "data/evalscope_datasets",
  "outputs_dir": "outputs/evalscope"
}
```

需要 LLM Judge 时默认使用 `data/models.json` 顶层 `analysis_model_id` 指向的模型；如需覆盖，可额外加入 `judge_model_config_id`、`judge_generation_config` 和 `judge_worker_num`。旧运行文件中的 `base_url`、超时、轮询以及旧 Judge 直连字段会被 schema 忽略，不再驱动远程调用或任务等待。
