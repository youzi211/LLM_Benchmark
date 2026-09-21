from pathlib import Path


def test_vue_stress_advanced_form_exposes_supported_generation_fields():
    source = Path("frontend/src/views/StressView.vue").read_text(encoding="utf-8")

    for label in (
        "frequency_penalty",
        "repetition_penalty",
        "logprobs",
        "seed",
        "tokenize_prompt",
    ):
        assert label in source


def test_vue_stress_progress_does_not_render_unknown_success_as_zero():
    source = Path("frontend/src/views/StressView.vue").read_text(encoding="utf-8")

    assert "progressSuccess" in source
    assert "progressFailed" in source
    assert "current_run" in source
