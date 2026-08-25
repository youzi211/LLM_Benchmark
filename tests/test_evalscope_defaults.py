from app.evalscope_defaults import (
    CODE_EXECUTION_DATASETS,
    DEFAULT_INTELLIGENCE_DATASETS,
    DEFAULT_STRESS_DATASET,
    FULL_OFFLINE_INTELLIGENCE_DATASETS,
    SCHEDULED_CODE_INTELLIGENCE_DATASETS,
    SCHEDULED_LIGHT_INTELLIGENCE_DATASETS,
)
from app.intelligence import evalscope_direct
from app.stress.schemas import StressRemoteSubmitPayload
from app.suites.profiles import BUILTIN_PROFILES


def test_evalscope_dataset_defaults_are_shared_by_profiles_and_runners():
    payload = StressRemoteSubmitPayload(model="demo", url="http://model/v1/chat/completions")

    assert payload.dataset == DEFAULT_STRESS_DATASET
    assert BUILTIN_PROFILES["scheduled_light"].stress_options.dataset == DEFAULT_STRESS_DATASET
    assert BUILTIN_PROFILES["full_offline"].stress_options.dataset == DEFAULT_STRESS_DATASET
    assert BUILTIN_PROFILES["scheduled_light"].intelligence_datasets == list(SCHEDULED_LIGHT_INTELLIGENCE_DATASETS)
    assert BUILTIN_PROFILES["scheduled_code"].intelligence_datasets == list(SCHEDULED_CODE_INTELLIGENCE_DATASETS)
    assert BUILTIN_PROFILES["full_offline"].intelligence_datasets == list(FULL_OFFLINE_INTELLIGENCE_DATASETS)
    assert evalscope_direct.DEFAULT_DATASETS == list(DEFAULT_INTELLIGENCE_DATASETS)
    assert evalscope_direct.CODE_EXECUTION_DATASETS == CODE_EXECUTION_DATASETS
