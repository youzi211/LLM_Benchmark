from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_web_console_static_assets_are_served(monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {307, 308}
    assert root.headers["location"] == "/ui/"

    page = client.get("/ui/")
    assert page.status_code == 200
    assert "LLM Benchmark 控制台" in page.text
    assert "大模型测试平台" in page.text
    assert "指标曲线" in page.text
    assert "定时一键评测" in page.text
    assert "只执行一次" in page.text
    assert "周期执行" in page.text
    assert "保存模型并创建定时计划" in page.text
    assert "/api/suites/quick" not in page.text  # API path lives in JS, not duplicated in markup.

    script = client.get("/ui/app.js")
    assert script.status_code == 200
    assert "apiFetch(\"/suites/quick\"" in script.text
    assert "apiFetch(\"/suites/schedules\"" in script.text
    assert "createScheduleFromQuick" in script.text
    assert "triggerSchedule" in script.text
    assert "run_once" in script.text
    assert "run_date" in script.text
    assert "buildStressCards" in script.text
    assert "createLineChart" in script.text
    assert "/stress/tasks/" in script.text

    style = client.get("/ui/styles.css")
    assert style.status_code == 200
    assert "评测" not in style.text
    assert ".insights-grid" in style.text
    assert ".schedule-list" in style.text
    assert ".hidden-field" in style.text
