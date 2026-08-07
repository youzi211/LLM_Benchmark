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


def test_docs_and_start_scripts_explicitly_say_sandbox_is_external() -> None:
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    api = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    metric_methods = (ROOT / "docs" / "metric-test-methods.md").read_text(encoding="utf-8")
    start_all_sh = (ROOT / "scripts" / "start_all.sh").read_text(encoding="utf-8")
    start_all_ps1 = (ROOT / "scripts" / "start_all.ps1").read_text(encoding="utf-8")

    assert "不会自动启动 EvalScope sandbox" in deployment
    assert "启动 `scripts/start_all.*` 或 `uvicorn app.main:app` 不会自动执行它" in deployment
    assert "主服务启动时不会自动启动 sandbox" in api
    assert "主服务启动时不会自动启动 sandbox" in architecture
    assert "主服务启动时不会自动启动 sandbox" in metric_methods
    assert "不会启动 ms-enclave" in start_all_sh
    assert "不会启动 ms-enclave" in start_all_ps1



def test_readme_documents_startup_deployment_and_sandbox_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uv sync --group evalscope" in readme
    assert "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000" in readme
    assert "scripts/start_all.sh" in readme
    assert "scripts\\start_all.ps1" in readme
    assert "主服务不会自动启动 EvalScope sandbox" in readme
    assert "ms-enclave server --host 0.0.0.0 --port 1234" in readme
    assert "LLM_BENCHMARK_SCHEDULER_DISABLED=1" in readme
    assert "data/models.json" in readme
    assert "data/evalscope.json" in readme
