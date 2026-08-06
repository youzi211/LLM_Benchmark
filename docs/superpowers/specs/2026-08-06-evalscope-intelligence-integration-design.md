# EvalScope 智力评测接入设计

> 日期：2026-08-06  
> 状态：已获得方向认可，待实现计划拆分  
> 关联文档：`evalScope/API_DOC.md`、`docs/architecture.md`、`docs/api.md`、`docs/metric-test-methods.md`

## 1. 背景

当前 LLM Benchmark 服务主要负责模型网关上线前的基础工程评测，覆盖连通性、延迟、上下文、输出长度、并发、限流、错误处理、Token 用量和流式规范性。EvalScope 服务已经封装为独立 API，可评测模型在代码、数学、知识、推理、QA、长文本等数据集上的表现。

本设计将 EvalScope 作为独立“智力评测能力模块”接入当前系统，而不是放入现有 `gateway_baseline_v1` 基础工程指标中。

## 2. 目标与非目标

### 目标

- 通过当前系统使用已有 `model_id` 发起 EvalScope 默认评测或自定义数据集评测。
- 支持查询 EvalScope 健康状态、本地数据集和支持数据集。
- 保存本系统智力评测任务与 EvalScope 任务 ID 的映射。
- 支持查询智力评测任务状态、获取结果并生成 Markdown 报告。
- 报告展示数据集分数、能力维度汇总、原始 `report_table` 和注意事项。

### 非目标

- 第一版不把智力评测合并进 `/api/tasks/run`。
- 第一版不把智力评测作为 `gateway_baseline_v1` 的普通 metric。
- 第一版不代理配置 EvalScope Judge，只检查并提示 Judge 状态。
- 第一版不重构现有基础评测任务为统一异步任务队列。
- 第一版不输出“上线通过 / 失败”的自动结论。

## 3. 推荐方案

采用独立模块：`/api/intelligence/*`。

理由：

- EvalScope 是异步长任务，生命周期与当前同步基础评测不同。
- EvalScope 输出是多数据集、多能力维度结果，结构与 `MetricResult` 不同。
- 独立模块能保持当前基础工程评测稳定，后续再做总报告聚合。

## 4. 模块结构

建议新增：

```text
app/
  intelligence/
    __init__.py
    schemas.py              # 智力评测请求、任务、结果模型
    evalscope_client.py     # EvalScope HTTP 客户端
    runner.py               # 智力评测提交、状态同步、结果拉取
    report.py               # 智力评测 Markdown 报告生成
  api/
    routes_intelligence.py  # /api/intelligence/* 路由
  storage/
    intelligence_task_store.py
```

继续复用：

- `app/storage/model_store.py`：读取被评测模型配置。
- `app/utils/masking.py`：脱敏 API Key。
- `app/reports/analyzer.py`：后续可复用报告分析模型生成摘要。

## 5. 配置与存储

### EvalScope 服务配置

新增本地配置文件：

```text
data/evalscope.json
```

示例：

```json
{
  "base_url": "http://localhost:8010/api/v1",
  "poll_interval_seconds": 5,
  "default_timeout_seconds": 14400
}
```

`data/evalscope.json` 属于运行配置，默认不提交。可在 `.env.example` 或文档中说明配置方式。

### 智力评测任务存储

```text
data/intelligence_tasks/intel_task_*.json
reports/intelligence/YYYY-MM-DD/intel_task_*.md
```

任务 JSON 保存：

- 本系统 `task_id`
- EvalScope `evalscope_task_id`
- `model_id`、`model_config_name`、`upstream_model_name`
- 数据集列表、请求参数、状态、进度
- 结果摘要、原始结果片段、报告路径
- 错误信息

## 6. API 设计

### 6.1 EvalScope 状态

```http
GET /api/intelligence/evalscope/health
GET /api/intelligence/evalscope/judge-config
```

用途：确认 EvalScope 是否可用、Judge 是否配置、数据集数量等。第一版只读，不代理写 Judge 配置。

### 6.2 数据集查询

```http
GET /api/intelligence/datasets
GET /api/intelligence/datasets/local
```

分别代理 EvalScope：

```http
GET /api/v1/datasets
GET /api/v1/datasets/local
```

### 6.3 提交默认智力评测

```http
POST /api/intelligence/tasks/default
```

请求：

```json
{
  "model_id": "tc-minimax-m3-lakala-real"
}
```

系统从 `data/models.json` 读取模型配置，并映射为 EvalScope 请求：

| 当前字段 | EvalScope 字段 |
|---|---|
| `ModelConfig.model` | `model` |
| `ModelConfig.base_url` | `api_url` |
| `ModelConfig.api_key` | `api_key` |

调用：

```http
POST /api/v1/eval/default
```

### 6.4 提交自定义智力评测

```http
POST /api/intelligence/tasks
```

请求：

```json
{
  "model_id": "tc-minimax-m3-lakala-real",
  "datasets": ["gsm8k", "humaneval", "mmlu_pro"],
  "limit": 100,
  "eval_batch_size": 20,
  "generation_config": {
    "temperature": 0.0,
    "max_tokens": 8192
  }
}
```

调用：

```http
POST /api/v1/eval
```

### 6.5 查询任务与结果

```http
GET /api/intelligence/tasks
GET /api/intelligence/tasks/{task_id}
GET /api/intelligence/tasks/{task_id}/result
GET /api/intelligence/reports/{task_id}
```

`GET /result` 行为：

1. 读取本地任务。
2. 查询 EvalScope 任务状态。
3. 若未完成，返回当前状态和进度。
4. 若已完成或失败，拉取 EvalScope result，标准化结果，写入本地任务 JSON。
5. 生成 Markdown 报告并返回结构化 JSON。

## 7. 状态模型

本系统智力评测任务状态建议与 EvalScope 对齐：

```text
pending -> running -> completed
                  └-> failed
```

可以额外支持：

- `submit_failed`：提交 EvalScope 失败。
- `sync_failed`：查询状态或拉取结果失败。

如果要保持简单，第一版可以统一映射为 `pending`、`running`、`completed`、`failed`，并用 `error` 字段记录细节。

## 8. 结果标准化

从 EvalScope result 提取：

```json
{
  "task_id": "intel_task_...",
  "evalscope_task_id": "eval-...",
  "status": "completed",
  "model_id": "tc-minimax-m3-lakala-real",
  "upstream_model_name": "TC-minimax-m3",
  "datasets": [
    {
      "dataset": "gsm8k",
      "pretty_name": "GSM8K",
      "categories": ["Math", "Reasoning"],
      "needs_judge": false,
      "score": 0.85,
      "metrics": []
    }
  ],
  "category_summary": [
    {
      "category": "Math",
      "dataset_count": 2,
      "average_score": 0.81
    }
  ],
  "report_table": "..."
}
```

能力维度汇总可基于数据集元数据中的 `categories` 计算；如果元数据缺失，则只展示数据集级结果。

## 9. 报告设计

智力评测 Markdown 报告建议包含：

1. 任务概览：模型配置、EvalScope 任务 ID、数据集、状态、耗时。
2. 一眼看懂：分数概览和关键注意事项。
3. 数据集分数表：dataset、能力维度、score、metrics 摘要。
4. 能力维度汇总：按代码、数学、知识、推理等聚合平均分。
5. EvalScope 原始 `report_table`。
6. Judge 状态提示：如果 Judge 未配置，则提示需要 Judge 的数据集可能不可用。
7. JSON 附录：标准化结果和脱敏后的原始结果摘要。

后续可复用当前 `ReportAnalyzer`，让固定报告分析模型对智力评测结果生成中文摘要。

## 10. 安全与边界

- 不在 API 响应、报告、日志中输出完整 API Key。
- 不提交 `data/evalscope.json`、`data/intelligence_tasks/`、`reports/intelligence/`。
- 第一版不把 Judge API Key 从当前系统转存到 EvalScope，避免扩大密钥持久化范围。
- EvalScope 调用失败时保存脱敏错误摘要，便于排查。

## 11. 文档与测试要求

实现时需要更新：

- `docs/api.md`：新增 `/api/intelligence/*` 接口说明。
- `docs/architecture.md`：加入智力评测模块和数据流。
- `README.md`：增加智力评测使用入口。
- `AGENTS.md`：如果目录或开发命令发生变化，补充说明。

测试建议：

- EvalScope client 请求构造与错误处理。
- 智力评测任务提交、状态同步、结果拉取。
- 模型配置字段到 EvalScope 请求字段的映射。
- 报告生成和脱敏。
- API 文档覆盖检查。

## 12. 分阶段实施

### 第一阶段：最小可用接入

- 新增配置、client、任务存储和 API。
- 支持默认评测、自定义评测、状态查询、结果拉取和 Markdown 报告。
- 不代理 Judge 配置。

### 第二阶段：报告增强

- 复用报告分析模型生成智力评测摘要。
- 优化能力维度汇总和数据集展示。
- 与基础工程评测报告形成统一视觉风格。

### 第三阶段：上线总报告

- 聚合基础工程评测结果和智力评测结果。
- 形成单个模型上线前总报告，但仍不输出自动上线准入结论。

## 13. 已确认决策

- 采用独立智力评测模块 `/api/intelligence/*`。
- 第一版不合并进现有 `/api/tasks/run`。
- 第一版不自动配置 EvalScope Judge，只检查并提示。
- 使用现有模型配置作为 EvalScope 被评测模型来源，避免重复填写 URL、Key、模型名。
