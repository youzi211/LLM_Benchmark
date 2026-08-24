from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.models import ModelConfigCreate
from app.intelligence.runner import IntelligenceRunner
from app.intelligence.schemas import EvalScopeConfig, IntelligenceNormalizedResult, IntelligenceTask
from app.overview.report import build_overview_report
from app.overview.schemas import OverviewReportRequest
from app.storage.intelligence_task_store import IntelligenceTaskStore
from app.storage.model_store import ModelStore
from app.storage.stress_task_store import StressTaskStore
from app.stress.evalscope_direct import EvalScopeStressExecutor
from app.stress.runner import StressRunner
from app.stress.schemas import StressNormalizedResult, StressRemoteSubmitPayload, StressTask


class BoundaryIntelligenceExecutor:
    def __init__(self, outputs_dir: Path):
        self.outputs_dir = outputs_dir

    def run(self, **kwargs):
        return {
            "task_id": kwargs["task_id"],
            "model": kwargs["model"],
            "datasets": kwargs["datasets"],
            "status": "completed",
            "outputs_dir": str(self.outputs_dir),
            "results": [
                {
                    "dataset": "gsm8k",
                    "report": {
                        "dataset_name": "GSM8K",
                        "score": 80.0,
                        "metrics": [{"name": "acc", "score": 0.8}],
                    },
                }
            ],
            "report_table": "full EvalScope report table",
            "metrics": {"raw_metric": {"large": "payload"}},
        }


class BoundaryStressExecutor:
    def __init__(self, outputs_dir: Path):
        self.outputs_dir = outputs_dir

    def run(self, *, task_id, payload):
        return {
            "task_id": task_id,
            "status": "completed",
            "outputs_dir": str(self.outputs_dir),
            "runs": [{"parallel": 1, "number": 2, "total": 2, "success": 2, "failed": 0, "request_throughput": 3.5}],
            "raw_detail": {"very_large": ["payload"]},
        }


def _model_store(path: Path) -> ModelStore:
    store = ModelStore(path)
    store.create(
        ModelConfigCreate(
            id="m1",
            name="测试模型",
            protocol="chat_completions",
            base_url="http://model.local/v1",
            api_key="dummy-api-key",
            model="upstream-model",
        )
    )
    return store


def test_stress_executor_preserves_task_scoped_output_dir(tmp_path, monkeypatch):
    import evalscope.perf.main as perf_main

    monkeypatch.setattr(perf_main, "run_perf_benchmark", lambda args: {"parallel_1_number_1": {}})
    dataset_path = tmp_path / "prompts.txt"
    dataset_path.write_text("hello\n", encoding="utf-8")
    task_id = "stress_task_output_locator"
    payload = StressRemoteSubmitPayload(
        model="upstream-model",
        url="http://model.local/v1/chat/completions",
        api_key="EMPTY",
        parallel=[1],
        number=[1],
        dataset="custom",
        dataset_path=str(dataset_path),
        stream=False,
        min_prompt_length=1,
        max_prompt_length=20,
        min_tokens=1,
        max_tokens=1,
    )

    raw = EvalScopeStressExecutor(EvalScopeConfig(outputs_dir=str(tmp_path / "outputs"))).run(
        task_id=task_id,
        payload=payload,
    )

    assert raw["outputs_dir"] == str(tmp_path / "outputs" / "stress" / task_id)



def test_normalized_result_models_do_not_persist_duplicated_raw_payloads():
    intelligence = IntelligenceNormalizedResult.model_validate(
        {
            "task_id": "intel_task_boundary",
            "dataset_results": [
                {
                    "dataset": "gsm8k",
                    "score": 80.0,
                    "metrics": [{"name": "acc", "score": 0.8}],
                    "raw_report": {"secret": "payload"},
                }
            ],
            "report_table": "legacy table",
            "metrics": {"legacy": True},
            "raw_report": {"legacy": True},
        }
    )
    intelligence_dump = intelligence.model_dump(mode="json")
    assert "metrics" not in intelligence_dump
    assert "raw_report" not in intelligence_dump
    assert "report_table" not in intelligence_dump
    assert "metrics" not in intelligence_dump["dataset_results"][0]
    assert "raw_report" not in intelligence_dump["dataset_results"][0]

    stress = StressNormalizedResult.model_validate(
        {
            "task_id": "stress_task_boundary",
            "runs": [{"parallel": 1, "raw": {"legacy": "payload"}}],
            "raw_result": {"very_large": True},
        }
    )
    stress_dump = stress.model_dump(mode="json")
    assert "raw_result" not in stress_dump
    assert "raw" not in stress_dump["runs"][0]


@pytest.mark.asyncio
async def test_runners_keep_full_raw_result_at_task_level_and_save_output_dir(tmp_path):
    intel_output_dir = tmp_path / "outputs" / "intel"
    intelligence_runner = IntelligenceRunner(
        model_store=_model_store(tmp_path / "intel-models.json"),
        task_store=IntelligenceTaskStore(tmp_path / "intelligence_tasks"),
        executor=BoundaryIntelligenceExecutor(intel_output_dir),
        reports_dir=tmp_path / "reports",
        run_in_background=False,
    )
    intelligence_task = await intelligence_runner.submit_custom(model_id="m1", datasets=["gsm8k"])

    assert intelligence_task.raw_result["report_table"] == "full EvalScope report table"
    assert intelligence_task.raw_result["metrics"]["raw_metric"]["large"] == "payload"
    assert intelligence_task.raw_output_dir == str(intel_output_dir)
    intelligence_dump = intelligence_task.normalized_result.model_dump(mode="json")
    assert "report_table" not in intelligence_dump
    assert "metrics" not in intelligence_dump
    assert "raw_report" not in intelligence_dump
    persisted_intel = IntelligenceTaskStore(tmp_path / "intelligence_tasks").get(intelligence_task.task_id)
    assert persisted_intel is not None
    assert persisted_intel.raw_result["report_table"] == "full EvalScope report table"
    assert persisted_intel.raw_output_dir == str(intel_output_dir)

    stress_output_dir = tmp_path / "outputs" / "stress"
    stress_runner = StressRunner(
        model_store=_model_store(tmp_path / "stress-models.json"),
        task_store=StressTaskStore(tmp_path / "stress_tasks"),
        executor=BoundaryStressExecutor(stress_output_dir),
        reports_dir=tmp_path / "stress-reports",
        run_in_background=False,
    )
    stress_task = await stress_runner.submit_default("m1")

    assert stress_task.raw_result["raw_detail"]["very_large"] == ["payload"]
    assert stress_task.raw_output_dir == str(stress_output_dir)
    stress_dump = stress_task.normalized_result.model_dump(mode="json")
    assert "raw_result" not in stress_dump
    assert "raw" not in stress_dump["runs"][0]
    persisted_stress = StressTaskStore(tmp_path / "stress_tasks").get(stress_task.task_id)
    assert persisted_stress is not None
    assert persisted_stress.raw_result["raw_detail"]["very_large"] == ["payload"]
    assert persisted_stress.raw_output_dir == str(stress_output_dir)


def test_legacy_task_json_with_removed_fields_is_readable_and_overview_safe(tmp_path):
    intelligence_dir = tmp_path / "intelligence_tasks"
    stress_dir = tmp_path / "stress_tasks"
    intelligence_dir.mkdir()
    stress_dir.mkdir()
    (intelligence_dir / "intel_task_legacy.json").write_text(
        json.dumps(
            {
                "task_id": "intel_task_legacy",
                "model_id": "m1",
                "evalscope_base_url": "in-process",
                "status": "completed",
                "normalized_result": {
                    "task_id": "intel_task_legacy",
                    "status": "completed",
                    "dataset_results": [
                        {
                            "dataset": "gsm8k",
                            "score": 72.0,
                            "metrics": [{"legacy": True}],
                            "raw_report": {"legacy": True},
                        }
                    ],
                    "report_table": "legacy table",
                },
            }
        ),
        encoding="utf-8",
    )
    (stress_dir / "stress_task_legacy.json").write_text(
        json.dumps(
            {
                "task_id": "stress_task_legacy",
                "model_id": "m1",
                "evalscope_base_url": "in-process",
                "status": "completed",
                "normalized_result": {
                    "task_id": "stress_task_legacy",
                    "status": "completed",
                    "runs": [{"parallel": 1, "total": 1, "success": 1, "failed": 0, "raw": {"legacy": True}}],
                    "raw_result": {"legacy": True},
                },
            }
        ),
        encoding="utf-8",
    )

    intelligence_task = IntelligenceTaskStore(intelligence_dir).get("intel_task_legacy")
    stress_task = StressTaskStore(stress_dir).get("stress_task_legacy")
    assert intelligence_task is not None
    assert stress_task is not None
    assert "report_table" not in intelligence_task.normalized_result.model_dump(mode="json")
    assert "raw_result" not in stress_task.normalized_result.model_dump(mode="json")

    report = build_overview_report(
        OverviewReportRequest(intelligence_task_id="intel_task_legacy", stress_task_id="stress_task_legacy"),
        intelligence_store=IntelligenceTaskStore(intelligence_dir),
        stress_store=StressTaskStore(stress_dir),
    )
    assert report.components[1].status == "completed"
    assert report.components[2].status == "completed"
