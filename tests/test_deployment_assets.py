from __future__ import annotations

import json
import tomllib
from pathlib import Path

from app.intelligence.schemas import EvalScopeConfig


ROOT = Path(__file__).resolve().parents[1]


def test_evalscope_default_config_is_in_process_and_minimal() -> None:
    config = EvalScopeConfig()
    dumped = config.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    assert dumped == {}


def test_root_pyproject_has_evalscope_dependency_group() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = pyproject.get("dependency-groups", {})
    assert "evalscope" in groups
    deps = "\n".join(groups["evalscope"]).lower()
    assert "evalscope[perf,sandbox]" in deps
    assert "sse-starlette" not in deps


def test_local_evalscope_example_config_is_optional_minimal_override() -> None:
    example_path = ROOT / "data" / "evalscope.json.example"
    data = json.loads(example_path.read_text(encoding="utf-8"))
    assert data == {
        "datasets_dir": "data/evalscope_datasets",
        "outputs_dir": "outputs/evalscope",
    }


def test_remote_sandbox_evalscope_example_config_documents_option_a() -> None:
    example_path = ROOT / "data" / "evalscope.remote-sandbox.json.example"
    data = json.loads(example_path.read_text(encoding="utf-8"))
    assert data["sandbox_enabled"] is True
    assert data["sandbox_type"] == "docker"
    assert data["sandbox_manager_config"] == {"base_url": "http://sandbox-host:1234"}
    assert "api_key" not in json.dumps(data).lower()


def test_deployment_scripts_cover_single_process_and_smoke_check() -> None:
    required = [
        ROOT / "scripts" / "start_main.ps1",
        ROOT / "scripts" / "start_main.sh",
        ROOT / "scripts" / "start_all.ps1",
        ROOT / "scripts" / "start_all.sh",
        ROOT / "scripts" / "smoke_deploy.py",
        ROOT / "scripts" / "test_deployment.py",
    ]
    for path in required:
        assert path.exists(), f"missing deployment script: {path}"

    assert not (ROOT / "scripts" / "start_evalscope.ps1").exists()
    assert not (ROOT / "scripts" / "start_evalscope.sh").exists()

    smoke = (ROOT / "scripts" / "smoke_deploy.py").read_text(encoding="utf-8")
    assert "EvalScope_service" not in smoke
    assert "app.main:app" in smoke
    assert "/api/intelligence/evalscope/health" in smoke
    assert "/api/stress/evalscope/health" in smoke

    checker = (ROOT / "scripts" / "test_deployment.py").read_text(encoding="utf-8")
    assert "/api/intelligence/evalscope/health" in checker
    assert "/api/stress/evalscope/health" in checker
    assert "/health" in checker
