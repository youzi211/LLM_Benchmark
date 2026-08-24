from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes_suites
from app.main import app
from app.suites.schemas import SuiteDefaultRunRequest, SuiteRun
from app.suites.store import SuiteRunStore



def test_evalscope_profiles_route_lists_builtin_profiles(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.get("/api/evalscope/profiles")

    assert response.status_code == 200, response.text
    profiles = response.json()
    profile_ids = {item["profile_id"] for item in profiles}
    assert "scheduled_light" in profile_ids
    assert "scheduled_code" in profile_ids
    scheduled_light = next(item for item in profiles if item["profile_id"] == "scheduled_light")
    assert scheduled_light["requires_sandbox"] is False
    assert scheduled_light["run_intelligence"] is True
    assert scheduled_light["intelligence_datasets"] == ["gsm8k", "math_500", "ceval"]
    assert scheduled_light["stress_options"]["dataset"] == "openqa"


def test_suite_schedule_uses_scheduled_light_profile_by_default(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-light",
            "model_id": "demo-chat",
            "time_of_day": "02:00",
            "timezone": "Asia/Shanghai",
        },
    )

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["profile"] == "scheduled_light"
    assert schedule["request"]["run_gateway"] is True
    assert schedule["request"]["run_intelligence"] is True
    assert schedule["request"]["run_stress"] is True
    assert schedule["request"]["intelligence_datasets"] == ["gsm8k", "math_500", "ceval"]
    assert schedule["request"]["intelligence_limit"] == 50
    assert schedule["request"]["intelligence_eval_batch_size"] == 5
    assert schedule["request"]["stress_options"]["dataset"] == "openqa"
    assert schedule["request"]["stress_options"]["parallel"] == [1, 2, 5]
    assert schedule["request"]["stress_options"]["number"] == [10, 20, 50]


def test_suite_schedule_explicit_fields_override_profile_defaults(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-custom",
            "model_id": "demo-chat",
            "profile": "scheduled_light",
            "run_stress": False,
            "intelligence_datasets": ["bbh"],
            "intelligence_limit": 7,
            "stress_options": {"dataset": "longalpaca"},
        },
    )

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["profile"] == "scheduled_light"
    assert schedule["request"]["run_stress"] is False
    assert schedule["request"]["intelligence_datasets"] == ["bbh"]
    assert schedule["request"]["intelligence_limit"] == 7
    assert schedule["request"]["stress_options"]["dataset"] == "longalpaca"
    assert schedule["request"]["stress_options"]["parallel"] == [1, 2, 5]


def test_suite_schedule_code_profile_requires_sandbox(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-code",
            "model_id": "demo-chat",
            "profile": "scheduled_code",
        },
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "profile_requires_sandbox"
    assert "scheduled_code" in body["error"]["message"]


def test_suite_schedule_code_profile_allowed_when_sandbox_enabled(temp_data_dirs, monkeypatch):
    data_dir, _ = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "evalscope.json").write_text(
        '{"sandbox_enabled": true, "sandbox_type": "docker", "sandbox_manager_config": {"base_url": "http://sandbox.local:1234"}}',
        encoding="utf-8",
    )
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-code",
            "model_id": "demo-chat",
            "profile": "scheduled_code",
        },
    )

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["profile"] == "scheduled_code"
    assert schedule["request"]["run_gateway"] is False
    assert schedule["request"]["run_stress"] is False
    assert schedule["request"]["run_intelligence"] is True
    assert schedule["request"]["intelligence_datasets"] == ["humaneval", "mbpp"]
    assert schedule["request"]["intelligence_limit"] == 20


def test_suite_schedule_routes_are_not_swallowed_by_suite_id(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-demo",
            "model_id": "demo-chat",
            "time_of_day": "02:00",
            "timezone": "Asia/Shanghai",
            "stress_parallel": [1, 5],
            "stress_number": [10, 50],
        },
    )

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["schedule_id"].startswith("suite_schedule_")
    assert schedule["run_once"] is False
    assert schedule["request"]["wait_for_completion"] is False
    assert schedule["request"]["stress_options"]["parallel"] == [1, 5]
    assert schedule["request"]["intelligence_limit"] == 50

    listed = client.get("/api/suites/schedules")
    assert listed.status_code == 200
    assert listed.json()[0]["schedule_id"] == schedule["schedule_id"]

    fetched = client.get(f"/api/suites/schedules/{schedule['schedule_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["schedule_id"] == schedule["schedule_id"]

    deleted = client.delete(f"/api/suites/schedules/{schedule['schedule_id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "schedule_id": schedule["schedule_id"]}


def test_suite_schedule_accepts_one_shot_run_date(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "tonight-demo",
            "model_id": "demo-chat",
            "time_of_day": "00:00",
            "timezone": "Asia/Shanghai",
            "run_once": True,
            "run_date": "2099-01-02",
            "stress_parallel": [1],
            "stress_number": [1],
            "intelligence_limit": 50,
        },
    )

    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["run_once"] is True
    assert schedule["run_date"] == "2099-01-02"
    assert schedule["enabled"] is True
    assert schedule["next_run_at"].startswith("2099-01-01T16:00:00")
    assert schedule["request"]["intelligence_limit"] == 50



def test_suite_schedule_last_run_route_returns_schedule_without_suite(temp_data_dirs, monkeypatch):
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-demo",
            "model_id": "demo-chat",
            "time_of_day": "02:00",
            "timezone": "Asia/Shanghai",
            "stress_parallel": [1],
            "stress_number": [1],
        },
    )
    assert response.status_code == 200, response.text
    schedule = response.json()

    last_run = client.get(f"/api/suites/schedules/{schedule['schedule_id']}/last-run")

    assert last_run.status_code == 200, last_run.text
    data = last_run.json()
    assert data["schedule"]["schedule_id"] == schedule["schedule_id"]
    assert data["suite"] is None
    assert data["last_suite_status"] is None
    assert data["last_suite_error_count"] == 0
    assert data["last_suite_errors"] == []


def test_suite_schedule_last_run_route_summarizes_last_suite(temp_data_dirs, monkeypatch):
    data_dir, _ = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    client = TestClient(app)

    response = client.post(
        "/api/suites/schedules",
        json={
            "name": "nightly-demo",
            "model_id": "demo-chat",
            "time_of_day": "02:00",
            "timezone": "Asia/Shanghai",
            "stress_parallel": [1],
            "stress_number": [1],
        },
    )
    assert response.status_code == 200, response.text
    schedule = response.json()
    suite = SuiteRun(
        suite_id="suite_last_run_demo",
        model_id="demo-chat",
        title="demo failed run",
        status="partial",
        current_step=None,
        request=SuiteDefaultRunRequest(model_id="demo-chat"),
        schedule_id=schedule["schedule_id"],
        errors=[{"step": "stress", "message": "boom"}],
    )
    SuiteRunStore(data_dir / "suite_runs").save(suite)
    schedule["last_suite_id"] = suite.suite_id
    from app.suites.schemas import SuiteSchedule
    from app.suites.store import SuiteScheduleStore

    SuiteScheduleStore(data_dir / "suite_schedules").save(SuiteSchedule.model_validate(schedule))

    last_run = client.get(f"/api/suites/schedules/{schedule['schedule_id']}/last-run")

    assert last_run.status_code == 200, last_run.text
    data = last_run.json()
    assert data["schedule"]["last_suite_id"] == "suite_last_run_demo"
    assert data["suite"]["suite_id"] == "suite_last_run_demo"
    assert data["last_suite_status"] == "partial"
    assert data["last_suite_current_step"] is None
    assert data["last_suite_error_count"] == 1
    assert data["last_suite_errors"] == [{"step": "stress", "message": "boom"}]



def test_default_suite_background_uses_job_executor(temp_data_dirs, monkeypatch):
    data_dir, _ = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    captured = {}

    class FakeRunner:
        suite_store = SuiteRunStore(data_dir / "suite_runs")

        async def start_default(self, request: SuiteDefaultRunRequest, schedule_id: str | None = None):
            suite = SuiteRun(model_id=request.model_id, title=request.title, request=request, schedule_id=schedule_id)
            self.suite_store.save(suite)
            return suite

        async def execute(self, suite_id: str):
            captured["executed"] = suite_id

    class FakeJobExecutor:
        def submit_async(self, *, job_type: str, target_id: str, payload: dict, func):
            captured["job"] = {"job_type": job_type, "target_id": target_id, "payload": payload, "func": func}
            return type("Job", (), {"job_id": "job_suite_route"})()

    monkeypatch.setattr(routes_suites, "_runner", lambda: FakeRunner())
    monkeypatch.setattr(routes_suites, "_job_executor", lambda: FakeJobExecutor())
    client = TestClient(app)

    response = client.post("/api/suites/default", json={"model_id": "demo-chat"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["job_id"] == "job_suite_route"
    assert captured["job"]["job_type"] == "suite"
    assert captured["job"]["target_id"] == data["suite_id"]
    assert "executed" not in captured


def test_jobs_routes_return_job_records(temp_data_dirs, monkeypatch):
    data_dir, _ = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    from app.jobs.schemas import JobRecord
    from app.jobs.store import JobStore

    job = JobRecord(job_id="job_demo", job_type="suite", target_id="suite_demo", payload={"suite_id": "suite_demo"})
    JobStore(data_dir / "jobs").save(job)
    client = TestClient(app)

    listed = client.get("/api/jobs")
    fetched = client.get("/api/jobs/job_demo")

    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["job_id"] == "job_demo"
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["target_id"] == "suite_demo"


def test_suite_default_and_report_routes(temp_data_dirs, monkeypatch):
    data_dir, reports_dir = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    report_path = reports_dir / "overview" / "2026-08-06" / "suite-overview.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# 模型评测总览报告\n", encoding="utf-8")

    class FakeRunner:
        async def start_default(self, request: SuiteDefaultRunRequest, schedule_id: str | None = None):
            suite = SuiteRun(
                suite_id="suite_route_demo",
                model_id=request.model_id,
                title=request.title,
                status="completed",
                request=request,
                schedule_id=schedule_id,
                overview_id="overview_route_demo",
                overview_report_path=str(report_path),
            )
            SuiteRunStore(data_dir / "suite_runs").save(suite)
            return suite

    monkeypatch.setattr(routes_suites, "_runner", lambda: FakeRunner())
    client = TestClient(app)

    created = client.post(
        "/api/suites/default",
        json={"model_id": "demo-chat", "wait_for_completion": True},
    )

    assert created.status_code == 200, created.text
    assert created.json()["suite_id"] == "suite_route_demo"

    fetched = client.get("/api/suites/suite_route_demo")
    assert fetched.status_code == 200
    assert fetched.json()["overview_id"] == "overview_route_demo"

    markdown = client.get("/api/suites/suite_route_demo/report")
    assert markdown.status_code == 200
    assert "模型评测总览报告" in markdown.text

def test_suite_quick_route_uses_inline_model_without_persisting_key(temp_data_dirs, monkeypatch):
    data_dir, _ = temp_data_dirs
    monkeypatch.setenv("LLM_BENCHMARK_SCHEDULER_DISABLED", "1")
    captured = {}

    class FakeQuickRunner:
        async def start_default(self, request: SuiteDefaultRunRequest, schedule_id: str | None = None):
            captured["suite_request"] = request
            suite = SuiteRun(
                suite_id="suite_quick_demo",
                model_id=request.model_id,
                title=request.title,
                status="queued",
                request=request,
                schedule_id=schedule_id,
            )
            SuiteRunStore(data_dir / "suite_runs").save(suite)
            return suite

        async def execute(self, suite_id: str):
            captured["executed"] = suite_id

    def fake_quick_runner(request):
        captured["quick_request"] = request
        suite_request = SuiteDefaultRunRequest(
            model_id="inline_test_model",
            title=request.title or f"{request.model} 一键评测",
            run_gateway=request.run_gateway,
            run_intelligence=request.run_intelligence,
            run_stress=request.run_stress,
            gateway_metric_ids=request.gateway_metric_ids,
            wait_for_completion=request.wait_for_completion,
        )
        return FakeQuickRunner(), suite_request

    monkeypatch.setattr(routes_suites, "_quick_runner", fake_quick_runner)
    client = TestClient(app)

    response = client.post(
        "/api/suites/quick",
        json={
            "url": "http://127.0.0.1:9001/v1",
            "key": "dummy-key-should-not-be-persisted",
            "model": "demo-model",
            "run_intelligence": False,
            "run_stress": False,
            "gateway_metric_ids": ["connectivity"],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["suite_id"] == "suite_quick_demo"
    assert data["model_id"] == "inline_test_model"
    assert data["request"]["model_id"] == "inline_test_model"
    assert "dummy-key-should-not-be-persisted" not in response.text
    assert captured["quick_request"].key == "dummy-key-should-not-be-persisted"
    assert captured["suite_request"].gateway_metric_ids == ["connectivity"]
    assert not (data_dir / "models.json").exists()
    suite_file = data_dir / "suite_runs" / "suite_quick_demo.json"
    assert suite_file.exists()
    assert "dummy-key-should-not-be-persisted" not in suite_file.read_text(encoding="utf-8")


def test_suite_quick_request_builds_transient_model_from_url_key_model(temp_data_dirs):
    from app.suites.schemas import SuiteQuickRunRequest

    request = SuiteQuickRunRequest(
        base_url="http://gateway.example/v1/chat/completions",
        api_key="<test-key>",
        model="demo-model",
        context_window_tokens=8192,
        max_output_tokens=2048,
        run_stress=False,
    )

    model_config = request.to_inline_model_config()
    suite_request = request.to_suite_request(model_config.id)

    assert model_config.id.startswith("inline_")
    assert model_config.base_url == "http://gateway.example/v1"
    assert model_config.api_key == "<test-key>"
    assert model_config.model == "demo-model"
    assert model_config.declared_context_tokens == 8192
    assert model_config.declared_max_output_tokens == 2048
    assert suite_request.model_id == model_config.id
    assert suite_request.title == "demo-model 一键评测"
    assert suite_request.run_stress is False
