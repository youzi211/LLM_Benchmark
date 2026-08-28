import pytest
from pydantic import ValidationError

from app.evalscope_defaults import (
    DEFAULT_STRESS_DATASET,
    DEFAULT_STRESS_MAX_PROMPT_LENGTH,
    DEFAULT_STRESS_MIN_PROMPT_LENGTH,
)
from app.stress.runner import StressRunner
from app.stress.schemas import StressRemoteSubmitPayload, StressTask


def test_stress_normalizer_accepts_evalscope_perf_mapping_without_service_wrapper():
    runner = StressRunner.__new__(StressRunner)
    task = StressTask(task_id="stress_task_20260806120000_aaaaaaaa", model_id="m1", evalscope_base_url="in-process")
    raw = {
        "task_id": "stress_task_20260806120000_aaaaaaaa",
        "status": "completed",
        "parallel_1_number_2": {
            "metrics": {
                "concurrency": 1,
                "total_requests": 2,
                "succeed_requests": 2,
                "failed_requests": 0,
                "request_throughput": 4.2,
                "output_token_throughput": 12.5,
            },
            "percentiles": {"rows": [{"percentile": "95%", "latency": 0.4, "ttft": 200.0}]},
        },
    }

    result = StressRunner._normalize(runner, task, raw)

    assert result.runs[0].parallel == 1
    assert result.runs[0].success == 2
    assert result.runs[0].p95_latency_seconds == 0.4
    assert result.summary["best_output_throughput"] == 12.5


def test_stress_payload_schema_remains_evalscope_arguments_friendly():
    payload = StressRemoteSubmitPayload(model="demo", url="http://model/v1/chat/completions", api_key="dummy-secret-key")
    data = payload.model_dump(mode="json")

    assert data["api"] == "openai"
    # 默认数据集已切到 longalpaca（本地离线复用），并按 EvalScope 官方默认放宽长度过滤：
    # min_prompt_length=0、max_prompt_length=131072、tokenizer_path=None，避免 1024 token
    # 过滤把长文本语料全部丢弃。
    assert data["dataset"] == DEFAULT_STRESS_DATASET
    assert "dataset_path" in data
    assert data["dataset_path"] is None
    assert data["min_prompt_length"] == DEFAULT_STRESS_MIN_PROMPT_LENGTH
    assert data["max_prompt_length"] == DEFAULT_STRESS_MAX_PROMPT_LENGTH
    assert data["tokenizer_path"] is None
    assert data["parallel"]
    assert data["number"]


def test_stress_request_rejects_mismatched_parallel_number_lists():
    with pytest.raises(ValidationError) as exc_info:
        StressRemoteSubmitPayload(
            model="demo",
            url="http://model/v1/chat/completions",
            parallel=[5, 10, 20, 30, 40, 50],
            number=[10, 20, 30, 50],
        )

    assert "parallel and number must have the same length" in str(exc_info.value)
