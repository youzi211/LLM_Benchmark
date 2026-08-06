from app.intelligence.report import write_intelligence_report
from app.intelligence.schemas import IntelligenceDatasetResult, IntelligenceNormalizedResult, IntelligenceTask


def test_write_intelligence_report_contains_sections_and_redacts(tmp_path):
    task = IntelligenceTask(
        task_id="intel_task_20260806120000_aaaaaaaa",
        evalscope_task_id="eval-1",
        model_id="m1",
        model_config_name="测试模型",
        upstream_model_name="upstream",
        evalscope_base_url="http://evalscope/api/v1",
        datasets=["gsm8k"],
        status="completed",
        raw_result={"api_key": "sk" + "-example-token"},
        normalized_result=IntelligenceNormalizedResult(
            task_id="intel_task_20260806120000_aaaaaaaa",
            evalscope_task_id="eval-1",
            model="upstream",
            datasets=["gsm8k"],
            status="completed",
            dataset_results=[IntelligenceDatasetResult(dataset="gsm8k", pretty_name="GSM8K", categories=["Math"], needs_judge=False, score=0.85)],
            report_table="Model Dataset Score\nupstream gsm8k 0.85",
        ),
    )

    path = write_intelligence_report(task, tmp_path, judge_status={"configured": True, "model_id": "judge"})

    text = path.read_text(encoding="utf-8")
    assert "大模型智力评测报告" in text
    assert "一眼看懂" in text
    assert "数据集分数表" in text
    assert "EvalScope 原始汇总表" in text
    assert "GSM8K" in text
    assert "sk" + "-example-token" not in text
    assert "sk" + "-***" in text
