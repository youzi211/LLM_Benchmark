import pytest
from scripts import prepare_swebench_images as prep


def test_retired_pro_v1_preparation_is_rejected_before_network(tmp_path):
    with pytest.raises(SystemExit, match="dataset_retired"):
        prep._load_samples("swe_bench_pro", 1, tmp_path)


@pytest.mark.asyncio
async def test_retired_pro_v1_submission_is_rejected_before_model_lookup():
    from app.intelligence.runner import IntelligenceRunner

    runner = object.__new__(IntelligenceRunner)
    with pytest.raises(ValueError, match="dataset_retired"):
        await runner.submit_custom(model_id="unused", datasets=["swe_bench_pro"])
