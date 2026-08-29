# 能力评测接口使用文档

> 本文档面向需要调用 LLM Benchmark 能力评测服务的开发者。所有接口路径前缀为 `/api`，服务地址以 `http://10.182.17.2:8020` 为例。

---

## 目录

1. [前置准备](#1-前置准备)
2. [接口概览](#2-接口概览)
3. [数据集说明](#3-数据集说明)
4. [接口详细说明](#4-接口详细说明)
5. [典型使用流程](#5-典型使用流程)
6. [常见问题](#6-常见问题)

---

## 1. 前置准备

### 1.1 模型配置

评测前需要在服务中配置被评测的模型。通过模型管理接口添加：

```bash
curl -X POST http://10.182.17.2:8020/api/models \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my_model",
    "name": "我的模型",
    "protocol": "chat_completions",
    "base_url": "https://api.example.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4",
    "enabled": true
  }'
```

参数说明：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 模型唯一标识（字母、数字、下划线、点、短横线） |
| `name` | string | 是 | 显示名称 |
| `protocol` | string | 是 | 协议类型：`chat_completions` 或 `responses` |
| `base_url` | string | 是 | API 基础地址 |
| `api_key` | string | 是 | API 密钥 |
| `model` | string | 是 | 上游模型名 |
| `enabled` | bool | 否 | 是否启用，默认 `true` |
| `timeout_seconds` | int | 否 | 超时时间（1-600），默认 `60` |
| `declared_context_tokens` | int | 否 | 申明上下文窗口大小 |
| `declared_max_output_tokens` | int | 否 | 申明最大输出 tokens |
| `concurrency_levels` | list[int] | 否 | 并发级别（1-200），默认 `[1,5,10,20]` |

### 1.2 Judge 模型配置（可选）

部分数据集需要 LLM-as-Judge 打分（如 `simple_qa`、`alpaca_eval`、`arena_hard` 等）。需要满足以下任一条件：

- **方式一**：在模型配置中设置 `analysis_model_id`（`data/models.json` 中给已有模型加上该字段，值为另一个模型配置的 ID）
- **方式二**：在 `data/evalscope.json` 中配置 `judge_model_config_id`

不配置 Judge 模型时，提交需要 Judge 的数据集会返回 400 错误。

---

## 2. 接口概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/intelligence/evalscope/health` | 健康检查 |
| GET | `/api/intelligence/evalscope/judge-config` | 查看 Judge 配置 |
| GET | `/api/intelligence/datasets` | 查看所有可用数据集 |
| GET | `/api/intelligence/datasets/local` | 查看本地已下载数据集 |
| GET | `/api/intelligence/evalscope/tasks` | 查看 EvalScope 任务列表 |
| POST | `/api/intelligence/tasks/default` | 提交默认评测 |
| POST | `/api/intelligence/tasks` | 提交自定义评测 |
| GET | `/api/intelligence/tasks` | 查看评测任务列表 |
| GET | `/api/intelligence/tasks/{task_id}` | 获取任务状态 |
| GET | `/api/intelligence/tasks/{task_id}/result` | 获取任务结果 |
| POST | `/api/intelligence/tasks/{task_id}/cancel` | 取消任务 |
| GET | `/api/intelligence/reports/{task_id}` | 获取评测报告 |

---

## 3. 数据集说明

### 3.1 数据集列表

| key | 名称 | 分类 | 语言 | 需要 Judge | 说明 |
|---|---|---|---|---|---|
| `humaneval` | HumanEval | Code | Python | 否 | 代码生成 |
| `humaneval_plus` | HumanEval+ | Code | Python | 否 | HumanEval 增强版 |
| `mbpp` | MBPP | Code | Python | 否 | 基础编程题 |
| `mbpp_plus` | MBPP+ | Code | Python | 否 | MBPP 增强版 |
| `live_code_bench` | LiveCodeBench | Code | 多语言 | 否 | 实时代码评测（默认仅最新 release） |
| `gsm8k` | GSM8K | Math, Reasoning | 英文 | 否 | 小学数学多步推理 |
| `math_500` | MATH-500 | Math, Reasoning | 英文 | 否 | 数学竞赛题 |
| `mmlu_pro` | MMLU-Pro | Knowledge | 英文 | 否 | 综合知识增强评测 |
| `ceval` | C-Eval | Knowledge, Chinese | 中文 | 否 | 中文综合能力评测 |
| `bbh` | BBH | Reasoning | 英文 | 否 | Big-Bench Hard 复杂推理 |
| `mmlu` | MMLU | Knowledge | 英文 | 否 | 大规模多任务语言理解 |
| `cmmlu` | CMMLU | Knowledge, Chinese | 中文 | 否 | 中文多任务理解 |
| `ifeval` | IFEval | Instruction | 英文 | 否 | 指令遵循评测 |
| `simple_qa` | SimpleQA | QA, Knowledge | 英文 | **是** | 事实问答 |
| `chinese_simpleqa` | Chinese SimpleQA | QA, Knowledge | 中文 | **是** | 中文事实问答 |
| `truthful_qa` | TruthfulQA | QA, Truthfulness | 英文 | **是** | 真实性评测 |
| `alpaca_eval` | AlpacaEval | Instruction | 英文 | **是** | 指令遵循 |
| `arena_hard` | Arena-Hard | Instruction | 英文 | **是** | 对话质量 |
| `longbench_v2` | LongBench v2 | Long Context | 英文 | **是** | 长上下文评测 |

### 3.2 默认评测数据集

提交默认评测时，使用以下 10 个数据集：

```
humaneval, mbpp, humaneval_plus, mbpp_plus, live_code_bench,
gsm8k, math_500, mmlu_pro, ceval, bbh
```

### 3.3 代码执行数据集说明

以下数据集需要 **Sandbox 环境** 支持（用于执行生成的代码并验证正确性）：

- `humaneval`、`humaneval_plus`、`mbpp`、`mbpp_plus`、`live_code_bench`

如需使用，需在 `data/evalscope.json` 中配置 sandbox：

```json
{
  "sandbox_enabled": true,
  "sandbox_type": "docker",
  "sandbox_manager_config": {}
}
```

---

## 4. 接口详细说明

### 4.1 健康检查

```bash
GET /api/intelligence/evalscope/health
```

**示例**：
```bash
curl http://10.182.17.2:8020/api/intelligence/evalscope/health
```

**成功响应**：
```json
{
  "status": "ok",
  "mode": "in_process",
  "evalscope_version": "0.9.0"
}
```

**失败响应**（502）：
```json
{
  "error": {
    "code": "evalscope_error",
    "message": "EvalScope package is not available"
  }
}
```

---

### 4.2 查看 Judge 配置

```bash
GET /api/intelligence/evalscope/judge-config
```

**示例**：
```bash
curl http://10.182.17.2:8020/api/intelligence/evalscope/judge-config
```

**响应示例**：
```json
{
  "configured": true,
  "mode": "in_process",
  "model_config_id": "judge_model",
  "model_id": "gpt-4o",
  "source": "analysis_model",
  "required_datasets": ["simple_qa", "chinese_simpleqa", "truthful_qa", "alpaca_eval", "arena_hard", "longbench_v2"],
  "generation_config": {"temperature": 0.0, "max_tokens": 4096},
  "judge_worker_num": 5
}
```

---

### 4.3 查看可用数据集

```bash
# 查看所有可用数据集及其元数据
GET /api/intelligence/datasets

# 查看本地已下载的数据集
GET /api/intelligence/datasets/local
```

**示例**：
```bash
curl http://10.182.17.2:8020/api/intelligence/datasets
```

**响应示例**：
```json
{
  "total": 20,
  "default_datasets": ["humaneval", "mbpp", "humaneval_plus", "mbpp_plus", "live_code_bench", "gsm8k", "math_500", "mmlu_pro", "ceval", "bbh"],
  "datasets": {
    "gsm8k": {
      "pretty_name": "GSM8K",
      "description": "小学数学多步推理",
      "categories": ["Math", "Reasoning"],
      "needs_judge": false
    }
  }
}
```

---

### 4.4 提交默认评测

使用内置的 10 个默认数据集执行评测。

```bash
POST /api/intelligence/tasks/default
```

**请求体**：
```json
{
  "model_id": "my_model"
}
```

**示例**：
```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks/default \
  -H "Content-Type: application/json" \
  -d '{"model_id": "my_model"}'
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model_id` | string | 是 | 已配置的模型 ID |

**响应**（任务已创建，异步执行）：
```json
{
  "task_id": "intel_task_20260828_1a2b3c4d",
  "status": "pending",
  "progress": "任务已创建，等待本地 EvalScope 执行",
  "datasets": ["humaneval", "mbpp", "humaneval_plus", "mbpp_plus", "live_code_bench", "gsm8k", "math_500", "mmlu_pro", "ceval", "bbh"],
  "model_id": "my_model",
  "created_at": "2026-08-28T10:00:00"
}
```

---

### 4.5 提交自定义评测

自由选择数据集和参数。

```bash
POST /api/intelligence/tasks
```

**请求体**：
```json
{
  "model_id": "my_model",
  "datasets": ["gsm8k", "math_500", "mmlu_pro", "ceval"],
  "limit": 50,
  "eval_batch_size": 10,
  "generation_config": {
    "temperature": 0.0,
    "max_tokens": 4096
  }
}
```

**示例**：
```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "my_model",
    "datasets": ["gsm8k", "math_500", "mmlu_pro", "ceval"],
    "limit": 50,
    "eval_batch_size": 10
  }'
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model_id` | string | 是 | 已配置的模型 ID |
| `datasets` | array[string] | 是 | 数据集 key 列表（至少 1 个） |
| `limit` | int | 否 | 每个子集的采样上限。不传则不限 |
| `eval_batch_size` | int | 否 | 评测批大小，默认 `10` |
| `generation_config` | object | 否 | 生成参数，默认 `{"temperature": 0.0, "max_tokens": 8192}` |

**注意**：
- `live_code_bench` 默认只评测最新 release。如需指定子集，需在 `data/evalscope.json` 的 `dataset_args` 中配置 `subset_list`
- 需要 Judge 的数据集（如 `simple_qa`）必须在 Judge 模型已配置时才能使用，否则返回 400 错误

---

### 4.6 查看评测任务列表

```bash
GET /api/intelligence/tasks?limit=50
```

**示例**：
```bash
curl "http://10.182.17.2:8020/api/intelligence/tasks?limit=50"
```

**可选参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `limit` | int | 返回条数上限，默认 50 |

---

### 4.7 获取任务状态

```bash
GET /api/intelligence/tasks/{task_id}
```

**示例**：
```bash
curl http://10.182.17.2:8020/api/intelligence/tasks/intel_task_20260828_1a2b3c4d
```

**任务状态字段说明**：

| 字段 | 说明 |
|---|---|
| `status` | 任务状态：`pending` → `running` → `completed` / `failed` / `interrupted` |
| `progress` | 中文进度描述 |
| `datasets` | 评测数据集列表 |
| `normalized_result` | 结构化评测结果（任务完成后有值） |
| `raw_result` | EvalScope 原始返回（任务完成后有值） |
| `report_path` | 报告的本地路径 |
| `error` | 错误信息（失败时有值） |

---

### 4.8 获取任务结果

```bash
GET /api/intelligence/tasks/{task_id}/result
```

**示例**：
```bash
curl http://10.182.17.2:8020/api/intelligence/tasks/intel_task_20260828_1a2b3c4d/result
```

**响应结构**（`normalized_result` 字段）：

```json
{
  "task_id": "intel_task_20260828_1a2b3c4d",
  "model": "gpt-4",
  "datasets": ["gsm8k", "math_500"],
  "status": "completed",
  "dataset_results": [
    {
      "dataset": "gsm8k",
      "pretty_name": "GSM8K",
      "categories": ["Math", "Reasoning"],
      "needs_judge": false,
      "score": 0.95
    },
    {
      "dataset": "math_500",
      "pretty_name": "MATH-500",
      "categories": ["Math", "Reasoning"],
      "needs_judge": false,
      "score": 0.82
    }
  ],
  "category_summaries": [
    {
      "category": "Math",
      "dataset_count": 2,
      "scored_dataset_count": 2,
      "average_score": 0.885
    },
    {
      "category": "Reasoning",
      "dataset_count": 2,
      "scored_dataset_count": 2,
      "average_score": 0.885
    }
  ],
  "created_at": "2026-08-28T10:00:00",
  "completed_at": "2026-08-28T11:30:00"
}
```

---

### 4.9 获取评测报告

下载 Markdown 格式的评测报告。

```bash
GET /api/intelligence/reports/{task_id}
```

**示例**：
```bash
curl http://10.182.17.2:8020/api/intelligence/reports/intel_task_20260828_1a2b3c4d
```

---

### 4.10 取消任务

```bash
POST /api/intelligence/tasks/{task_id}/cancel
```

**示例**：
```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks/intel_task_20260828_1a2b3c4d/cancel
```

任务状态将变为 `interrupted`。

---

## 5. 典型使用流程

### 5.1 完整流程示例

```bash
# 0. 前置检查：服务是否可用
curl http://10.182.17.2:8020/health

# 1. 检查 EvalScope 是否可用
curl http://10.182.17.2:8020/api/intelligence/evalscope/health

# 2. 查看可用数据集
curl http://10.182.17.2:8020/api/intelligence/datasets

# 3. 添加模型配置（如已添加可跳过）
curl -X POST http://10.182.17.2:8020/api/models \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my_model",
    "name": "我的模型",
    "protocol": "chat_completions",
    "base_url": "https://api.example.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4"
  }'

# 4. 提交评测任务（默认数据集）
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks/default \
  -H "Content-Type: application/json" \
  -d '{"model_id": "my_model"}'

# 5. 记录返回的 task_id，轮询任务状态
TASK_ID="intel_task_20260828_1a2b3c4d"
curl http://10.182.17.2:8020/api/intelligence/tasks/$TASK_ID

# 6. 任务完成后获取结果
curl http://10.182.17.2:8020/api/intelligence/tasks/$TASK_ID/result

# 7. 下载评测报告
curl http://10.182.17.2:8020/api/intelligence/reports/$TASK_ID -o report.md
```

### 5.2 仅评测部分数据集

```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "my_model",
    "datasets": ["gsm8k", "math_500", "ceval"],
    "limit": 100
  }'
```

### 5.3 带 Judge 的评测

确保 Judge 模型已配置后：

```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "my_model",
    "datasets": ["simple_qa", "gsm8k"],
    "limit": 50
  }'
```

### 5.4 自定义生成参数

```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "my_model",
    "datasets": ["gsm8k", "math_500"],
    "generation_config": {
      "temperature": 0.7,
      "max_tokens": 2048,
      "top_p": 0.95
    }
  }'
```

---

## 6. 常见问题

### Q1: 返回 404 Not Found

请确认路径前缀为 `/api`，例如：
```
正确: /api/intelligence/datasets
错误: /intelligence/datasets
```

### Q2: 返回 404 并提示 model_not_found

模型配置不存在或 ID 错误。先查看已配置的模型：
```bash
curl http://10.182.17.2:8020/api/models
```

### Q3: 返回 400 并提示 model_disabled

模型配置被禁用，通过更新接口启用：
```bash
curl -X PUT http://10.182.17.2:8020/api/models/my_model \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### Q4: 返回 400 并提示 judge_required

提交的数据集需要 LLM Judge，但未配置 Judge 模型。请参考 [1.2 Judge 模型配置](#12-judge-模型配置可选)。

### Q5: 任务长时间停留在 pending 状态

评测任务在后台异步执行。大数据集（如 `bbh`）可能需要较长时间。可以查看后台任务状态：
```bash
curl http://10.182.17.2:8020/api/jobs?limit=50
```

### Q6: 如何获取所有任务的原始数据？

任务完成后，可以通过 `raw_result` 字段获取 EvalScope 的完整原始输出：
```bash
curl http://10.182.17.2:8020/api/intelligence/tasks/{task_id}/result
```

### Q7: 服务端错误码说明

| HTTP 状态码 | error code | 说明 |
|---|---|---|
| 400 | `model_disabled` | 模型已禁用 |
| 400 | `judge_required` | 需要 Judge 模型但未配置 |
| 400 | `invalid_intelligence_task_request` | 请求参数不合法 |
| 404 | `model_not_found` | 模型配置不存在 |
| 404 | `intelligence_task_not_found` | 任务 ID 不存在 |
| 404 | `intelligence_report_not_found` | 评测报告不存在 |
| 502 | `evalscope_error` | EvalScope 包不可用 |

---

## 附录：错误响应格式

所有错误响应遵循统一格式：

```json
{
  "error": {
    "code": "model_not_found",
    "message": "Model config not found: unknown_model",
    "details": {}
  }
}
```