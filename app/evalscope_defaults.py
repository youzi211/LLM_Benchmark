from __future__ import annotations

from typing import Any

# 单一来源：所有 EvalScope 数据集、默认组合、代码执行/LLM Judge 分类，以及压测默认值
# 都集中在这里。后续更换默认压测数据集或定时 profile 数据集时，优先修改本文件；
# profile、runner、API schema 只引用这些常量，避免在多处重复硬编码。

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

DEFAULT_EVAL_BATCH_SIZE = 10
DEFAULT_GENERATION_CONFIG: dict[str, Any] = {"temperature": 0.0, "max_tokens": 8192}

LLM_JUDGE_DATASETS = frozenset(
    {
        "simple_qa",
        "chinese_simpleqa",
        "truthful_qa",
        "alpaca_eval",
        "arena_hard",
        "general_qa",
        "general_vqa",
        "halu_eval",
        "halueval",
        "longbench_v2",
    }
)

CODE_EXECUTION_DATASETS = frozenset(
    {
        "humaneval",
        "humaneval_plus",
        "mbpp",
        "mbpp_plus",
        "live_code_bench",
    }
)

DATASET_METADATA: dict[str, dict[str, Any]] = {
    "humaneval": {"pretty_name": "HumanEval", "description": "代码生成评测", "categories": ["Code"], "needs_judge": False},
    "humaneval_plus": {"pretty_name": "HumanEval+", "description": "HumanEval 增强版", "categories": ["Code"], "needs_judge": False},
    "mbpp": {"pretty_name": "MBPP", "description": "基础编程题评测", "categories": ["Code"], "needs_judge": False},
    "mbpp_plus": {"pretty_name": "MBPP+", "description": "MBPP 增强版", "categories": ["Code"], "needs_judge": False},
    "live_code_bench": {"pretty_name": "LiveCodeBench", "description": "实时代码评测", "categories": ["Code"], "needs_judge": False},
    "gsm8k": {"pretty_name": "GSM8K", "description": "小学数学多步推理", "categories": ["Math", "Reasoning"], "needs_judge": False},
    "math_500": {"pretty_name": "MATH-500", "description": "数学竞赛题", "categories": ["Math", "Reasoning"], "needs_judge": False},
    "mmlu_pro": {"pretty_name": "MMLU-Pro", "description": "综合知识增强评测", "categories": ["Knowledge"], "needs_judge": False},
    "ceval": {"pretty_name": "C-Eval", "description": "中文综合能力评测", "categories": ["Knowledge", "Chinese"], "needs_judge": False},
    "bbh": {"pretty_name": "BBH", "description": "Big-Bench Hard 复杂推理", "categories": ["Reasoning"], "needs_judge": False},
    "mmlu": {"pretty_name": "MMLU", "description": "大规模多任务语言理解", "categories": ["Knowledge"], "needs_judge": False},
    "cmmlu": {"pretty_name": "CMMLU", "description": "中文多任务理解", "categories": ["Knowledge", "Chinese"], "needs_judge": False},
    "ifeval": {"pretty_name": "IFEval", "description": "指令遵循评测", "categories": ["Instruction"], "needs_judge": False},
    "simple_qa": {"pretty_name": "SimpleQA", "description": "事实问答，需要 LLM Judge", "categories": ["QA", "Knowledge"], "needs_judge": True},
    "chinese_simpleqa": {"pretty_name": "Chinese SimpleQA", "description": "中文事实问答，需要 LLM Judge", "categories": ["QA", "Knowledge", "Chinese"], "needs_judge": True},
    "truthful_qa": {"pretty_name": "TruthfulQA", "description": "真实性评测", "categories": ["QA", "Truthfulness"], "needs_judge": True},
    "alpaca_eval": {"pretty_name": "AlpacaEval", "description": "指令遵循，需要 LLM Judge", "categories": ["Instruction"], "needs_judge": True},
    "arena_hard": {"pretty_name": "Arena-Hard", "description": "对话质量，需要 LLM Judge", "categories": ["Instruction"], "needs_judge": True},
    "longbench_v2": {"pretty_name": "LongBench v2", "description": "长上下文评测", "categories": ["Long Context"], "needs_judge": True},
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
