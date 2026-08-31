# 自定义数据集接入指南

> 本文档说明如何在 LLM Benchmark 能力评测系统中接入自定义数据集。从 EvalScope 1.10.0 起，数据集元信息（名称、标签、Judge/代码执行需求等）由 EvalScope BENCHMARK_REGISTRY 动态获取，**绝大多数场景无需修改代码**。

---

## 目录

1. [核心概念](#1-核心概念)
2. [接入方式选型](#2-接入方式选型)
3. [方式一：使用通用适配器（推荐）](#3-方式一使用通用适配器推荐)
4. [方式二：使用 EvalScope 内置数据集](#4-方式二使用-evalscope-内置数据集)
5. [方式三：编写自定义 Adapter](#5-方式三编写自定义-adapter)
6. [数据集目录结构](#6-数据集目录结构)
7. [评测提交与 Judge 配置](#7-评测提交与-judge-配置)
8. [常见问题](#8-常见问题)
9. [注意事项](#9-注意事项)

---

## 1. 核心概念

### 1.1 系统如何发现数据集

评测服务启动后，通过以下链路发现可用数据集：

```
API: GET /api/intelligence/datasets
  -> local_dataset_metadata()
       -> 扫描 data/evalscope_datasets/ 下的子目录
            -> 子目录名必须在 EvalScope BENCHMARK_REGISTRY 中已注册
                 -> 动态获取元信息：pretty_name、tags、needs_judge、needs_code_exec、subsets...
```

**关键约束**：data/evalscope_datasets/ 下的目录名必须与 EvalScope 注册的 benchmark 名称匹配，否则会被忽略。

### 1.2 元信息来源

| 信息 | 旧方案（已废弃） | 新方案（当前） |
|---|---|---|
| 数据集展示名 | evalscope_defaults.py 硬编码 | EvalScope BENCHMARK_REGISTRY 动态获取 |
| 是否需要 Judge | LLM_JUDGE_DATASETS 硬编码集合 | data_adapter.llm_judge_default 属性 |
| 是否需要代码沙箱 | CODE_EXECUTION_DATASETS 硬编码集合 | Tags.CODING 标签 |
| 子集列表 | 手动维护 | meta.subset_list |
| 评测指标 | 手动维护 | meta.metric_list |

**优势**：EvalScope 升级新增数据集时，本系统自动可见，无需改代码。

---

## 2. 接入方式选型

```
你的数据集是什么？
|
+-- 标准格式（问答 / 选择题 / 视觉问答）
|   +-> 方式一：使用通用适配器（零代码）
|
+-- EvalScope 内置但不在默认列表（如 gpqa、aime、agieval...）
|   +-> 方式二：直接下载数据到本地目录（零代码）
|
+-- 非标准格式（需要自定义 prompt 模板或评分逻辑）
    +-> 方式三：编写 EvalScope Adapter（需开发）
```

---

## 3. 方式一：使用通用适配器（推荐）

EvalScope 内置 8 个带 Custom 标签的通用适配器，覆盖最常见的自定义评测场景：

### 3.1 适配器一览

| 适配器名称 | 适用场景 | 输入格式 | 评测指标 | 需要 Judge |
|---|---|---|---|---|
| general_qa | 开放式问答（文本到文本） | query + answer 或 messages | BLEU、Rouge-L | 否 |
| general_mcq | 选择题（2-10 个选项） | question + A/B/C/D + answer | Accuracy | 否 |
| general_vqa | 视觉问答（图片+文本到文本） | OpenAI messages 格式 | BLEU、Rouge-L | 否 |
| general_vmcq | 视觉选择题 | 图片 + 选项 | Accuracy | 否 |
| general_fc | 函数调用 / 工具使用 | 工具定义 + 对话 | 自定义 | 否 |
| general_arena | 对战评测（两个模型对比） | 对话 | LLM Judge | 是 |
| general_t2i | 文生图 | 文本提示到图片 | 自定义 | 否 |
| data_collection | 纯数据收集（不评测） | 任意 | 无 | 否 |

### 3.2 General-QA 数据格式

**文件位置**：data/evalscope_datasets/general_qa/default_test.jsonl

**JSONL 格式**（每行一条记录）：

```jsonl
{"question": "中国四大发明是什么？", "answer": "造纸术、印刷术、火药、指南针"}
{"question": "什么是 Transformer 架构？", "answer": "Transformer 是一种基于自注意力机制的深度学习架构..."}
```

**字段说明**：

| 字段 | 必填 | 说明 |
|---|---|---|
| question 或 query | 是 | 问题文本（二选一） |
| answer 或 response | 是 | 参考答案 |
| system | 否 | 系统提示词 |
| messages | 否 | 完整对话历史（OpenAI 格式，与 question/system 互斥） |

**提交评测**：

```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{"model_id": "my_model", "datasets": ["general_qa"], "limit": 100}'
```

### 3.3 General-MCQ 数据格式

**文件位置**：data/evalscope_datasets/general_mcq/default_val.jsonl

> 注意：General-MCQ 的评测 split 是 val（不是 test），文件名必须为 default_val.jsonl。

**JSONL 格式**：

```jsonl
{"question": "以下哪个不是排序算法？", "A": "冒泡排序", "B": "快速排序", "C": "二分查找", "D": "归并排序", "answer": "C"}
{"question": "Python 中哪个关键字用于定义函数？", "A": "func", "B": "def", "C": "function", "D": "define", "answer": "B"}
```

**可选参数**（通过 data/evalscope.json 的 dataset_args 配置）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| multiple_correct | false | 多答案模式，answer 需为列表如 ["A", "C"] |
| use_cot | false | 使用思维链提示模板 |

**多答案配置示例**（data/evalscope.json）：

```json
{
  "dataset_args": {
    "general_mcq": {
      "multiple_correct": true,
      "use_cot": true
    }
  }
}
```

### 3.4 General-VQA 数据格式

**文件位置**：data/evalscope_datasets/general_vqa/default_test.jsonl（或 .tsv）

**JSONL 格式**（OpenAI 消息格式）：

```jsonl
{"messages": [{"role": "user", "content": [{"type": "text", "text": "这张图中有多少人？"}, {"type": "image_url", "image_url": {"url": "file:///path/to/image.jpg"}}]}], "answer": "3人"}
```

**图片输入支持**：
- 本地文件路径：file:///abs/path/image.jpg
- HTTP URL：https://example.com/image.jpg
- Base64：data:image/jpeg;base64,/9j/4AAQ...

### 3.5 文件命名规则

LocalDataLoader 按以下顺序查找文件（以 general_qa 为例）：

```
data/evalscope_datasets/general_qa/
|-- default_test.jsonl    <- 优先查找（subset_split 格式）
|-- default_test.csv
|-- default_test.tsv
|-- default.jsonl         <- 回退查找（仅 subset 格式）
|-- default.csv
+-- default.tsv
```

| 适配器 | subset | split | 文件名模式 |
|---|---|---|---|
| general_qa | default | test | default_test.jsonl |
| general_vqa | default | test | default_test.jsonl |
| general_mcq | default | val | default_val.jsonl |
| general_fc | default | test | default_test.jsonl |

> 支持的文件格式：.jsonl、.csv、.tsv

---

## 4. 方式二：使用 EvalScope 内置数据集

EvalScope 1.10.0 注册了 219 个数据集。除默认 10 个外，其余 209 个也可直接使用。

**操作步骤**：

1. 确认 EvalScope 可用：

```bash
curl http://10.182.17.2:8020/api/intelligence/evalscope/health
# 确认 "status": "ok"
```

2. 在服务器上下载数据集到本地目录：

```bash
cd D:\lakala\LLM_Benchmark
uv run python -c "from evalscope.api.benchmark import get_benchmark; get_benchmark('gpqa_diamond')"
```

或手动将数据放到 data/evalscope_datasets/<dataset_name>/ 下。

3. 验证数据集可见：

```bash
curl http://10.182.17.2:8020/api/intelligence/datasets
```

4. 提交评测：

```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{"model_id": "my_model", "datasets": ["gpqa_diamond", "aime25"]}'
```

**注意事项**：
- 部分 EvalScope 数据集需要 LLM Judge（如 hle、simple_qa），需先配置 Judge 模型。
- 部分数据集需要代码执行沙箱（如 humaneval、live_code_bench），需启用沙箱。
- 系统会自动从 BENCHMARK_REGISTRY 判断是否需要 Judge / 沙箱，无需手动指定。

---

## 5. 方式三：编写自定义 Adapter

当通用适配器无法满足需求（如需要自定义 prompt 模板、评分逻辑或多轮对话评测）时，需要编写 EvalScope Adapter。

### 5.1 基本结构

在 EvalScope 的 benchmarks 目录下创建新模块：

```
evalscope/benchmarks/my_benchmark/
|-- __init__.py
+-- my_benchmark_adapter.py
```

**my_benchmark_adapter.py 示例**：

```python
from typing import Any, Dict
from evalscope.api.benchmark import BenchmarkMeta, DefaultDataAdapter
from evalscope.api.dataset import Sample
from evalscope.api.evaluator import TaskState
from evalscope.api.metric import Score
from evalscope.api.registry import register_benchmark
from evalscope.constants import Tags

@register_benchmark(
    BenchmarkMeta(
        name='my_benchmark',
        pretty_name='My-Benchmark',
        tags=[Tags.QA, Tags.CUSTOM],
        description='我的自定义评测',
        dataset_id='my_benchmark',
        subset_list=['default'],
        metric_list=['acc'],
        eval_split='test',
        prompt_template='请回答以下问题：\n{question}',
    )
)
class MyBenchmarkAdapter(DefaultDataAdapter):

    def load_from_disk(self, **kwargs):
        return super().load_from_disk(use_local_loader=True)

    def record_to_sample(self, record: Dict[str, Any]) -> Sample:
        return Sample(
            input=record['question'],
            target=record['answer'],
        )

    def match_score(self, original_prediction, filtered_prediction, reference, task_state) -> Score:
        score = Score(
            extracted_prediction=filtered_prediction,
            prediction=original_prediction,
        )
        is_correct = filtered_prediction.strip().lower() == reference.strip().lower()
        score.value = {'acc': 1.0 if is_correct else 0.0}
        score.main_score_name = 'acc'
        return score
```

### 5.2 注册后使用

Adapter 注册到 BENCHMARK_REGISTRY 后，本系统会自动发现它。按方式二将数据放到 data/evalscope_datasets/my_benchmark/ 即可。

### 5.3 需要 LLM Judge 的 Adapter

如果评测需要 LLM 判断答案正确性（如开放式问答）：

```python
class MyJudgeAdapter(DefaultDataAdapter):
    llm_judge_default = True  # 关键：标记需要 Judge

    def llm_match_score(self, original_prediction, filtered_prediction, reference, task_state) -> Score:
        judge_prompt = f"判断回答是否正确...\n问题: {task_state.input_text}\n回答: {filtered_prediction}\n标准答案: {reference}"
        judge_response = self.llm_judge.judge(prompt=judge_prompt)
        score = Score(...)
        score.value = {'acc': 1.0 if '正确' in judge_response else 0.0}
        return score
```

设置 llm_judge_default = True 后，系统会自动要求配置 Judge 模型。

---

## 6. 数据集目录结构

所有数据集统一存放在 data/evalscope_datasets/ 下：

```
data/evalscope_datasets/
|-- humaneval/                    # EvalScope 内置，代码评测
|   +-- openai_humaneval_test.jsonl
|-- gsm8k/                        # EvalScope 内置，数学推理
|   |-- main_test.jsonl
|   +-- socratic_test.jsonl
|-- general_qa/                   # 通用适配器，自定义问答
|   +-- default_test.jsonl
|-- general_mcq/                  # 通用适配器，自定义选择题
|   +-- default_val.jsonl
|-- general_vqa/                  # 通用适配器，视觉问答
|   +-- default_test.jsonl
|-- my_benchmark/                 # 自定义 Adapter
|   +-- default_test.jsonl
+-- ...
```

可通过 data/evalscope.json 的 datasets_dir 字段修改数据集根目录。

---

## 7. 评测提交与 Judge 配置

### 7.1 提交评测

```bash
curl -X POST http://10.182.17.2:8020/api/intelligence/tasks \
  -H "Content-Type: application/json" \
  -d '{"model_id": "my_model", "datasets": ["general_qa", "gsm8k", "mmlu_pro"], "limit": 50}'
```

### 7.2 Judge 模型配置

当数据集需要 LLM Judge 时（如 general_arena、hle、simple_qa），必须配置 Judge 模型，否则会返回 400 错误。

**配置方式一**：在模型配置中设置 analysis_model_id（data/models.json）

```json
{"id": "my_model", "analysis_model_id": "judge_model"}
```

**配置方式二**：在 data/evalscope.json 中配置

```json
{"judge_model_config_id": "judge_model"}
```

系统通过 data_adapter.llm_judge_default 属性动态判断数据集是否需要 Judge，无需手动维护列表。

### 7.3 代码沙箱配置

当代码评测数据集（如 humaneval、mbpp、live_code_bench）需要沙箱时：

```json
{"sandbox_enabled": true, "sandbox_type": "docker", "sandbox_manager_config": {}}
```

系统通过 Tags.CODING 标签动态判断是否需要沙箱。

---

## 8. 常见问题

### Q1: 放了数据但 API 返回 dataset_not_local

**原因**：目录名不在 EvalScope BENCHMARK_REGISTRY 中。

**排查**：
1. 检查目录名拼写：data/evalscope_datasets/<name>/
2. 确认该名称在 EvalScope 已注册：
   `uv run python -c "from evalscope.api.registry import BENCHMARK_REGISTRY; print('<name>' in BENCHMARK_REGISTRY)"`
3. 如果是完全自定义的数据集，使用 general_qa / general_mcq 等通用适配器。

### Q2: 数据集可见但评测报错 No dataset file found

**原因**：文件命名不符合 LocalDataLoader 的查找规则。

**排查**：
- 确认文件名格式：<subset>_<split>.jsonl（如 default_test.jsonl）
- 确认 split 名称正确：general_qa 用 test，general_mcq 用 val
- 支持的格式：.jsonl、.csv、.tsv

### Q3: 评测返回 judge_required

**原因**：数据集需要 LLM Judge 但未配置 Judge 模型。

**解决**：在 data/evalscope.json 中配置 judge_model_config_id，或在模型配置中设置 analysis_model_id。

### Q4: 评测返回 sandbox_required

**原因**：代码评测数据集需要沙箱但未启用。

**解决**：在 data/evalscope.json 中设置 sandbox_enabled: true 并配置沙箱。

### Q5: 如何查看所有 EvalScope 支持的数据集？

```bash
uv run python -c "
from evalscope.api.registry import BENCHMARK_REGISTRY
for name, meta in sorted(BENCHMARK_REGISTRY.items()):
    tags = [t if isinstance(t, str) else t.value for t in (meta.tags or [])]
    judge = getattr(meta.data_adapter, 'llm_judge_default', False) if meta.data_adapter else False
    print(name, judge, tags)
"
```

### Q6: 如何确认某个数据集需要 Judge 还是沙箱？

```bash
uv run python -c "
from app.intelligence.evalscope_direct import _dataset_needs_judge, _dataset_needs_code_exec
print('needs_judge:', _dataset_needs_judge('hle'))
print('needs_code_exec:', _dataset_needs_code_exec('humaneval'))
"
```

---

## 9. 注意事项

### 9.1 数据安全

- 不要提交 data/evalscope_datasets/ 下的数据文件到 Git。
- 自定义数据集中的答案字段可能包含敏感信息，注意脱敏。
- .gitignore 已包含 data/ 目录。

### 9.2 文件编码

- 所有 JSONL/CSV/TSV 文件使用 UTF-8 编码。
- 中文数据确保无 BOM 头（除非 EvalScope 明确要求）。

### 9.3 数据量与评测时间

- limit 参数控制每个 subset 的评测样本数。
- 多 subset 数据集（如 bbh 有 27 个子集），limit 对每个子集独立截断。
- 建议先用 limit: 10 验证流程，再全量评测。

### 9.4 通用适配器的局限

- general_qa 使用 BLEU/Rouge 评测，适合参考答案明确的场景；对于开放式生成质量评测，建议使用 general_arena（需 LLM Judge）。
- general_mcq 的 split 是 val（不是 test），文件名必须为 default_val.jsonl。
- 通用适配器的 prompt 模板是固定的，如需自定义 prompt 请使用方式三。

### 9.5 EvalScope 版本兼容

- 当前系统使用 EvalScope 1.10.0，注册了 219 个数据集。
- EvalScope 升级后新增的数据集会被自动发现，无需改代码。
- 自定义 Adapter 需跟随 EvalScope 版本升级做兼容性测试。

### 9.6 多 subset 数据集

- 部分数据集（如 bbh、live_code_bench）有多个子集。
- 可通过 data/evalscope.json 的 dataset_args 限制子集：

```json
{"dataset_args": {"live_code_bench": {"subset_list": ["release_latest"]}}}
```

### 9.7 性能影响

- _load_evalscope_benchmarks() 在首次调用时加载 BENCHMARK_REGISTRY 并缓存，后续调用无性能开销。
- 缓存是进程级的，服务重启后会重新加载。

---

## 附录：快速接入检查清单

- [ ] 确认数据集类型，选择接入方式（通用适配器 / 内置数据集 / 自定义 Adapter）
- [ ] 准备数据文件，按命名规则放置到 data/evalscope_datasets/<name>/
- [ ] 确认文件编码为 UTF-8
- [ ] 如果需要 Judge：配置 judge_model_config_id 或 analysis_model_id
- [ ] 如果需要沙箱：配置 sandbox_enabled: true
- [ ] 调用 GET /api/intelligence/datasets 验证数据集可见
- [ ] 用 limit: 10 先跑小批量验证
- [ ] 确认评测结果正常后全量提交
