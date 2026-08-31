from __future__ import annotations

from typing import Any

# 项目级评测配置：默认数据集组合、Profile 定义、以及压测默认值
# 都集中在这里。数据集元信息（名称、标签、Judge/代码执行需求）改由 EvalScope BENCHMARK_REGISTRY 动态获取，
# 不再在本文件中硬编码 DATASET_METADATA / LLM_JUDGE_DATASETS / CODE_EXECUTION_DATASETS。

DEFAULT_SCHEDULE_PROFILE = "scheduled_light"
DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT = 200

DEFAULT_INTELLIGENCE_DATASETS: tuple[str, ...] = (
    "humaneval",
    "mbpp",
    "humaneval_plus",
    "mbpp_plus",
    "live_code_bench",
    "gsm8k",
    "math_500",
    "mmlu_pro",
    "ceval",
    "bbh",
)

SCHEDULED_LIGHT_INTELLIGENCE_DATASETS: tuple[str, ...] = ("gsm8k", "math_500", "ceval")
SCHEDULED_LIGHT_INTELLIGENCE_LIMIT = 50
SCHEDULED_LIGHT_INTELLIGENCE_EVAL_BATCH_SIZE = 5

SCHEDULED_CODE_INTELLIGENCE_DATASETS: tuple[str, ...] = ("humaneval", "mbpp")
SCHEDULED_CODE_INTELLIGENCE_LIMIT = 20
SCHEDULED_CODE_INTELLIGENCE_EVAL_BATCH_SIZE = 2

FULL_OFFLINE_INTELLIGENCE_DATASETS: tuple[str, ...] = DEFAULT_INTELLIGENCE_DATASETS
FULL_OFFLINE_INTELLIGENCE_EVAL_BATCH_SIZE = 5

# EvalScope 的 limit 对多 subset 数据集是“每个 subset 各截断一次”。
# live_code_bench 默认包含多个 release/vX 组合子集；若不显式限制 subset，
# intelligence_limit=200 会放大为数千条样本。默认只评测最新 release，
# 如需固定版本或多子集覆盖，可在 data/evalscope.json 的 dataset_args 中覆盖。
LIVE_CODE_BENCH_DEFAULT_SUBSETS: tuple[str, ...] = ("release_latest",)
DEFAULT_INTELLIGENCE_DATASET_ARGS: dict[str, dict[str, Any]] = {
    "live_code_bench": {"subset_list": list(LIVE_CODE_BENCH_DEFAULT_SUBSETS)},
}

DEFAULT_EVAL_BATCH_SIZE = 10
DEFAULT_GENERATION_CONFIG: dict[str, Any] = {"temperature": 0.0, "max_tokens": 8192}




# 压测数据集的展示元信息。与智力评测的 DATASET_METADATA 分开维护，
# 因为压测数据集（longalpaca、speed_benchmark 等）和智力评测数据集
# 完全不同，混在一个 dict 里容易误导。只列出可用的已知数据集；
# random / speed_benchmark 等不下载的内置数据集也纳入展示。
STRESS_DATASET_METADATA: dict[str, dict[str, Any]] = {
    "longalpaca": {
        "pretty_name": "LongAlpaca",
        "description": "长文本语料，适合测试长上下文吞吐与延迟",
        "categories": ["Long Context"],
        "is_local_resolvable": True,
    },
    "openqa": {
        "pretty_name": "OpenQA",
        "description": "开放问答语料，通用对话场景",
        "categories": ["QA"],
        "is_local_resolvable": True,
    },
    "share_gpt_zh": {
        "pretty_name": "ShareGPT 中文",
        "description": "中文多轮对话语料",
        "categories": ["Conversation", "Chinese"],
        "is_local_resolvable": True,
    },
    "share_gpt_en": {
        "pretty_name": "ShareGPT 英文",
        "description": "英文多轮对话语料",
        "categories": ["Conversation"],
        "is_local_resolvable": True,
    },
    "share_gpt_zh_multi_turn": {
        "pretty_name": "ShareGPT 中文多轮",
        "description": "中文多轮对话，适合多轮交互压测",
        "categories": ["Conversation", "Chinese"],
        "is_local_resolvable": True,
    },
    "share_gpt_en_multi_turn": {
        "pretty_name": "ShareGPT 英文多轮",
        "description": "英文多轮对话，适合多轮交互压测",
        "categories": ["Conversation"],
        "is_local_resolvable": True,
    },
    "flickr8k": {
        "pretty_name": "Flickr8K",
        "description": "图像描述语料，可测多模态压测",
        "categories": ["Multimodal"],
        "is_local_resolvable": True,
    },
    "kontext_bench": {
        "pretty_name": "KontextBench",
        "description": "上下文依赖评测语料",
        "categories": ["Context"],
        "is_local_resolvable": True,
    },
    "swe_smith": {
        "pretty_name": "SWE-Smith",
        "description": "软件工程任务语料",
        "categories": ["Code"],
        "is_local_resolvable": True,
    },
    "random": {
        "pretty_name": "Random",
        "description": "随机生成 Token，不依赖外部数据集，快速验证吞吐",
        "categories": ["Synthetic"],
        "is_local_resolvable": False,
    },
    "speed_benchmark": {
        "pretty_name": "Speed Benchmark",
        "description": "EvalScope 内置速度基准",
        "categories": ["Benchmark"],
        "is_local_resolvable": False,
    },
}
DEFAULT_STRESS_DATASET = "longalpaca"
DEFAULT_STRESS_PARALLEL: tuple[int, ...] = (1, 5, 10, 20)
DEFAULT_STRESS_NUMBER: tuple[int, ...] = (10, 50, 100, 200)
DEFAULT_STRESS_STREAM = True
DEFAULT_STRESS_MIN_PROMPT_LENGTH = 0
DEFAULT_STRESS_MAX_PROMPT_LENGTH = 131072
DEFAULT_STRESS_MIN_TOKENS = 512
DEFAULT_STRESS_MAX_TOKENS = 512
DEFAULT_STRESS_RATE = -1.0
DEFAULT_STRESS_PREFIX_LENGTH = 0

SCHEDULED_LIGHT_STRESS_PARALLEL: tuple[int, ...] = (1, 2, 5)
SCHEDULED_LIGHT_STRESS_NUMBER: tuple[int, ...] = (10, 20, 50)
SCHEDULED_LIGHT_STRESS_MIN_TOKENS = 128
SCHEDULED_LIGHT_STRESS_MAX_TOKENS = 128
SCHEDULED_LIGHT_STRESS_EXTRA_ARGS: dict[str, Any] = {"ignore_eos": True}

FULL_OFFLINE_STRESS_PARALLEL: tuple[int, ...] = (1, 5)
FULL_OFFLINE_STRESS_NUMBER: tuple[int, ...] = (10, 50)

# 已知会从 ModelScope 下载的真实语料数据集。当本地 data/stress_datasets 下
# 存在同名目录、.json 或 .jsonl 文件时，runner 会自动补齐 dataset_path。
LOCAL_RESOLVABLE_STRESS_DATASETS = frozenset(
    {
        "longalpaca",
        "openqa",
        "share_gpt_zh",
        "share_gpt_en",
        "share_gpt_zh_multi_turn",
        "share_gpt_en_multi_turn",
        "flickr8k",
        "kontext_bench",
        "swe_smith",
    }
)

