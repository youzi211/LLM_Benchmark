import pytest

from app.intelligence.report_summary import primary_summary


def test_native_v2_primary_metric_and_display_contract():
    from evalscope.report.report import Report, Metric
    from evalscope.api.metric.semantics import MetricIdentity, MetricSemantics
    identity = MetricIdentity(name="accuracy", aggregation="mean")
    semantics = MetricSemantics(semantic_id="quality.accuracy.ratio", metric_name="accuracy", kind="quality", direction="higher_is_better", display_unit="%", display_multiplier=100)
    report = Report(metrics=[Metric(identity=identity, score=.75, num=4, semantics=semantics)], primary_metric_identity=identity,
                    execution_summary={"requested": 4, "succeeded": 4})
    payload = report.to_dict()
    assert "score" not in payload
    summary = primary_summary(payload)
    assert summary["score"] == .75
    assert summary["unit"] == "%"
    assert summary["display_multiplier"] == 100
    assert summary["sample_count"] == 4
    assert summary["complete"] is True


def test_v2_does_not_guess_missing_primary_metric():
    assert primary_summary({"schema_version": 2, "metrics": [], "primary_metric_unavailable_reason": "missing"})["score"] is None


def test_legacy_explicit_score_and_nonfinite_value():
    assert primary_summary({"score": 0})["score"] == 0
    assert primary_summary({"score": float("nan")})["score"] is None


def test_native_task_config_accepts_judge_contract(tmp_path):
    from evalscope import TaskConfig
    from app.intelligence.evalscope_direct import EvalScopeIntelligenceExecutor
    from app.intelligence.schemas import EvalScopeConfig
    executor = EvalScopeIntelligenceExecutor(EvalScopeConfig(judge_worker_num=3))
    data = executor._task_config_data(model="fake", api_url="http://127.0.0.1:9001/v1/chat/completions", api_key="test",
        dataset="simple_qa", local_paths={}, limit=1, eval_batch_size=None, generation_config=None, work_dir=str(tmp_path),
        judge_model_args={"model_id": "judge", "api_url": "http://127.0.0.1:9001/v1/chat/completions", "api_key": "test"})
    assert not {"judge_worker_num", "judge_strategy", "judge_model_args"} & data.keys()
    config = TaskConfig(**data)
    assert config.eval_batch_size == 3
    assert config.judge.models[0].model_id == "judge"
