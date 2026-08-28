from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
    assert "三线评测中心" in page.text
    assert "基础评测" in page.text
    assert "压测评测" in page.text
    assert "能力评测" in page.text
    assert "一键完整评测" in page.text
    assert "定时任务" in page.text
    assert "只执行一次" in page.text
    assert "周期执行" in page.text
    assert "/api/suites/quick" not in page.text  # API path lives in JS, not duplicated in markup.

    script = client.get("/ui/app.js")
    assert script.status_code == 200
    assert "apiFetch(\"/suites/quick\"" in script.text
    assert "apiFetch(\"/suites/schedules\"" in script.text
    assert "startQuickSuite" in script.text
    assert "startBasicTask" in script.text
    assert "startStressTask" in script.text
    assert "startIntelligenceTask" in script.text
    assert "triggerSchedule" in script.text
    assert "run_once" in script.text
    assert "run_date" in script.text
    assert "scheduled_light" in script.text
    assert "schedule-profile" in page.text
    assert "global-model-select" in page.text
    assert "buildStressCards" in script.text
    assert "createProgressCard" in script.text
    assert "progress_detail" in script.text
    assert "本地可用" in script.text
    assert "renderDatasetSubsetInfo" in script.text
    assert "configured_subset_list" in script.text
    assert "createLineChart" in script.text
    assert "/stress/tasks/" in script.text

    style = client.get("/ui/styles.css")
    assert style.status_code == 200
    assert "评测" not in style.text
    assert ".insights-grid" in style.text
    assert ".progress-bar" in style.text
    assert ".schedule-list" in style.text
    assert ".main-tabs" in style.text
    assert ".lane-layout" in style.text

def test_web_vue_optional_mount_helper_skips_when_directory_missing(tmp_path):
    """When the Vue build output directory is absent, the helper returns False and never touches the app."""
    from fastapi import FastAPI

    from app.main import _mount_optional_static

    fastapi_app = FastAPI(title="missing-vue-test")
    mounted = _mount_optional_static(fastapi_app, "/ui-vue-test", tmp_path / "no-such-vue", "ui-vue-test")

    assert mounted is False
    routes = [route.path for route in fastapi_app.routes]
    assert "/ui-vue-test" not in routes
    assert "/ui-vue-test/" not in routes


def test_web_vue_optional_mount_helper_serves_placeholder_assets(tmp_path):
    """When the Vue directory exists with a placeholder, /ui-vue serves index.html and assets."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import _mount_optional_static

    vue_dir = tmp_path / "vue_assets"
    vue_dir.mkdir()
    (vue_dir / "index.html").write_text(

        "<html><body><h1>Vue 控制台占位</h1><script type=\"module\" src=\"./app.js\"></script></body></html>",
        encoding="utf-8",
    )
    (vue_dir / "app.js").write_text("console.log(\"vue placeholder\")", encoding="utf-8")
    (vue_dir / "styles.css").write_text(".vue-placeholder { color: red; }", encoding="utf-8")

    fastapi_app = FastAPI(title="vue-test")
    mounted = _mount_optional_static(fastapi_app, "/ui-vue", vue_dir, "ui-vue")

    assert mounted is True
    client = TestClient(fastapi_app)

    page = client.get("/ui-vue/")
    assert page.status_code == 200
    assert "Vue 控制台占位" in page.text
    assert "app.js" in page.text

    script = client.get("/ui-vue/app.js")
    assert script.status_code == 200
    assert "vue placeholder" in script.text

    style = client.get("/ui-vue/styles.css")
    assert style.status_code == 200
    assert ".vue-placeholder" in style.text

    missing = client.get("/ui-vue/nope.js")
    assert missing.status_code == 404


def test_legacy_ui_still_served_when_vue_directory_missing(monkeypatch, tmp_path):
    """The existing /ui page keeps working regardless of whether app/web_vue exists."""
    # Build a temporary repository layout where app/web exists but app/web_vue does not.
    fake_app = tmp_path / "app_vue_check"
    (fake_app / "web").mkdir(parents=True)
    (fake_app / "web" / "index.html").write_text("<html>legacy</html>", encoding="utf-8")

    # Point app.main at this fake layout via monkeypatching the WEB_DIR/WEB_VUE_DIR constants.
    monkeypatch.setattr("app.main.WEB_DIR", fake_app / "web")
    monkeypatch.setattr("app.main.WEB_VUE_DIR", fake_app / "web_vue")  # does not exist on purpose

    # Build a fresh FastAPI instance mirroring app/main.py layout to avoid triggering
    # the global scheduler/executor startup during module import.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import _mount_optional_static, WEB_DIR

    fastapi_app = FastAPI(title="legacy-still-served")
    fastapi_app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")
    mounted_vue = _mount_optional_static(fastapi_app, "/ui-vue", fake_app / "web_vue", "ui-vue")
    assert mounted_vue is False

    client = TestClient(fastapi_app)
    legacy = client.get("/ui/")
    assert legacy.status_code == 200
    assert "legacy" in legacy.text

    # /ui-vue is not mounted at all, so even its root path is not registered.
    vue_attempt = client.get("/ui-vue/")
    assert vue_attempt.status_code in {404, 307}


def test_public_app_serves_legacy_ui_and_optional_vue_mount():
    """Importing app.main succeeds; /ui/ always works, /ui-vue is mounted only when app/web_vue exists."""
    from starlette.routing import Mount

    from app.main import WEB_VUE_DIR, app
    from fastapi.testclient import TestClient

    mount_paths = [route.path for route in app.routes if isinstance(route, Mount)]
    assert "/ui" in mount_paths

    vue_routes = [p for p in mount_paths if p.startswith("/ui-vue")]
    if WEB_VUE_DIR.is_dir():
        # The Vue build output is present (e.g. after `npm run build` in frontend/),
        # so the mount is added and serves the real Vue index.
        assert vue_routes, "expected /ui-vue to be mounted when app/web_vue exists"
        client = TestClient(app)
        page = client.get("/ui-vue/")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        # Vite emits an index.html that loads the hashed JS bundle; assert structure rather than copy.
        assert "/assets/" in page.text or "LLM Benchmark" in page.text
    else:
        # The Vue build output is not present, so the conditional mount is skipped.
        assert vue_routes == []

    # The legacy /ui page always works regardless of the Vue mount state.
    client = TestClient(app)
    legacy = client.get("/ui/")
    assert legacy.status_code == 200
    assert "LLM Benchmark 控制台" in legacy.text
