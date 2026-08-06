from __future__ import annotations

from pathlib import Path

from fastapi.routing import APIRoute

from app.core.registry import get_plan, list_metrics
from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def _read_doc(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_api_document_covers_all_public_routes():
    api_doc = _read_doc("docs/api.md")
    documented_routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.include_in_schema:
            continue
        for method in sorted(route.methods - {"HEAD"}):
            documented_routes.append((method, route.path))

    missing = [f"{method} `{path}`" for method, path in documented_routes if f"{method} `{path}`" not in api_doc]

    assert missing == []


def test_metric_method_document_covers_gateway_baseline_metrics():
    metric_doc = _read_doc("docs/metric-test-methods.md")
    metrics = {metric.id: metric for metric in list_metrics()}
    plan = get_plan("gateway_baseline_v1")

    assert plan is not None
    for metric_id in plan.metric_ids:
        metric = metrics[metric_id]
        assert f"`{metric.id}`" in metric_doc
        assert metric.name in metric_doc


def test_readme_links_project_documents():
    readme = _read_doc("README.md")

    assert "[系统架构说明](docs/architecture.md)" in readme
    assert "[API 接口文档](docs/api.md)" in readme
    assert "[指标测试方法文档](docs/metric-test-methods.md)" in readme
    assert "必须同步更新" in readme


def test_intelligence_docs_are_linked_and_described():
    api_doc = _read_doc("docs/api.md")
    architecture_doc = _read_doc("docs/architecture.md")
    metric_doc = _read_doc("docs/metric-test-methods.md")
    readme = _read_doc("README.md")

    assert "/api/intelligence/tasks/default" in api_doc
    assert "/api/intelligence/tasks/{task_id}/result" in api_doc
    assert "智力评测" in architecture_doc
    assert "EvalScope" in architecture_doc
    assert "EvalScope 智力评测" in metric_doc
    assert "智力评测" in readme
