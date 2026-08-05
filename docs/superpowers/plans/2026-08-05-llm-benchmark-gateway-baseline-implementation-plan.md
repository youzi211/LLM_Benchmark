
# LLM Benchmark Gateway Baseline V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a usable internal FastAPI service that runs `gateway_baseline_v1` against OpenAI Chat Completions-compatible and Responses-compatible model APIs, returns structured JSON, persists task history, and generates Markdown reports.

**Architecture:** API routes only handle HTTP concerns; `TaskRunner` orchestrates plans, metrics, adapters, storage, and reports. Model configs are persisted in `data/models.json`, task results in `data/tasks/*.json`, and reports in `reports/YYYY-MM-DD/*.md`.

**Tech Stack:** Python 3.11+, uv, FastAPI, Pydantic v2, httpx, uvicorn, pytest, local JSON, Markdown.

---

## Source Requirements

- Spec: `D:/lakala/LLM_Benchmark/docs/superpowers/specs/2026-08-05-llm-benchmark-gateway-baseline-design.md`
- No SQL, no platform auth, no formal frontend, no OpenAI Python SDK.
- Support protocols: `chat_completions` and `responses`, each explicitly configured per model.
- Derive paths from `base_url`: `/chat/completions` or `/responses`.
- Default plan: `gateway_baseline_v1`.
- Metrics: `connectivity`, `latency_breakdown`, `context_length`, `output_length`, `concurrency`, `rate_limit`, `error_handling`, `token_usage_accuracy`, `stream_spec`.
- Status vocabulary: `completed`, `error`, `skipped`; do not introduce `passed` or `failed`.
- API responses and reports must mask `api_key`; local `data/models.json` may store plaintext for internal deployment.

## File Structure Map

Create:

```text
D:/lakala/LLM_Benchmark/.gitignore
D:/lakala/LLM_Benchmark/.env.example
D:/lakala/LLM_Benchmark/README.md
D:/lakala/LLM_Benchmark/pyproject.toml
D:/lakala/LLM_Benchmark/app/main.py
D:/lakala/LLM_Benchmark/app/api/errors.py
D:/lakala/LLM_Benchmark/app/api/routes_models.py
D:/lakala/LLM_Benchmark/app/api/routes_metrics.py
D:/lakala/LLM_Benchmark/app/api/routes_tasks.py
D:/lakala/LLM_Benchmark/app/api/routes_reports.py
D:/lakala/LLM_Benchmark/app/core/models.py
D:/lakala/LLM_Benchmark/app/core/statuses.py
D:/lakala/LLM_Benchmark/app/core/plans.py
D:/lakala/LLM_Benchmark/app/core/registry.py
D:/lakala/LLM_Benchmark/app/core/runner.py
D:/lakala/LLM_Benchmark/app/adapters/base.py
D:/lakala/LLM_Benchmark/app/adapters/chat_completions.py
D:/lakala/LLM_Benchmark/app/adapters/responses.py
D:/lakala/LLM_Benchmark/app/metrics/base.py
D:/lakala/LLM_Benchmark/app/metrics/probes.py
D:/lakala/LLM_Benchmark/app/storage/file_utils.py
D:/lakala/LLM_Benchmark/app/storage/model_store.py
D:/lakala/LLM_Benchmark/app/storage/task_store.py
D:/lakala/LLM_Benchmark/app/reports/markdown.py
D:/lakala/LLM_Benchmark/app/utils/ids.py
D:/lakala/LLM_Benchmark/app/utils/masking.py
D:/lakala/LLM_Benchmark/app/utils/sse.py
D:/lakala/LLM_Benchmark/app/utils/timing.py
D:/lakala/LLM_Benchmark/app/utils/token_estimator.py
D:/lakala/LLM_Benchmark/tests/conftest.py
D:/lakala/LLM_Benchmark/tests/test_models_api.py
D:/lakala/LLM_Benchmark/tests/test_registry.py
D:/lakala/LLM_Benchmark/tests/test_sse.py
D:/lakala/LLM_Benchmark/tests/test_adapters.py
D:/lakala/LLM_Benchmark/tests/test_runner_fake_upstream.py
```

Package marker `__init__.py` files must exist under every `app/*` package and `tests/`.

---

## Task 1: Scaffold uv/FastAPI Project

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, package marker files.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "llm-benchmark"
version = "0.1.0"
description = "Internal LLM API gateway baseline benchmark service"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
    "pydantic>=2.8.0",
    "python-dotenv>=1.0.1"
]

[dependency-groups]
dev = ["pytest>=8.2.0", "pytest-asyncio>=0.23.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["."]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
.env
data/models.json
data/tasks/
reports/
__pycache__/
.venv/
.pytest_cache/
*.pyc
```

- [ ] **Step 3: Create `.env.example`**

```dotenv
LLM_BENCHMARK_DATA_DIR=data
LLM_BENCHMARK_REPORTS_DIR=reports
```

- [ ] **Step 4: Create package dirs**

Run:

```powershell
$dirs = @('app','app/api','app/core','app/adapters','app/metrics','app/storage','app/reports','app/utils','tests')
foreach ($dir in $dirs) { New-Item -ItemType Directory -Force -Path $dir | Out-Null; New-Item -ItemType File -Force -Path (Join-Path $dir '__init__.py') | Out-Null }
```

- [ ] **Step 5: Install and smoke test**

Run:

```powershell
uv sync
uv run pytest -q
```

Expected: dependencies install; pytest has no environment/import failure.

---

## Task 2: Core Models, Statuses, and Utilities

**Files:** `app/core/statuses.py`, `app/core/models.py`, `app/api/errors.py`, `app/utils/masking.py`, `app/utils/ids.py`, `app/utils/timing.py`, `app/utils/token_estimator.py`.

- [ ] **Step 1: Define statuses**

`app/core/statuses.py`:

```python
from typing import Literal

MetricStatus = Literal["completed", "error", "skipped"]
TaskStatus = Literal["completed", "error"]
Protocol = Literal["chat_completions", "responses"]
STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"
SUPPORTED_PROTOCOLS = {"chat_completions", "responses"}
```

- [ ] **Step 2: Define Pydantic models**

`app/core/models.py` must include these model classes: `ModelConfigCreate`, `ModelConfigUpdate`, `ModelConfig`, `ModelConfigPublic`, `MetricInfo`, `PlanInfo`, `RunTaskRequest`, `AdapterRequest`, `AdapterResponse`, `StreamChunk`, `StreamAdapterResponse`, `MetricResult`, `TaskResult`.

Key fields for `ModelConfigCreate`:

```python
id: str
name: str
protocol: Literal["chat_completions", "responses"]
base_url: str
api_key: str
model: str
timeout_seconds: int = 60
enabled: bool = True
declared_context_tokens: int | None = None
declared_max_output_tokens: int | None = None
concurrency_levels: list[int] = [1, 5, 10, 20]
```

Validation requirements:

- Strip trailing slash from `base_url`.
- `id` allows letters, digits, `_`, `.`, `-`.
- Empty concurrency config becomes `[1, 5, 10, 20]`; values must be 1 to 200.

- [ ] **Step 3: Implement API error shape**

`app/api/errors.py` exposes `api_error(status_code, code, message, details=None)` returning FastAPI `HTTPException` detail shaped as:

```json
{"error":{"code":"model_not_found","message":"Model config not found: xxx","details":{}}}
```

- [ ] **Step 4: Implement small utilities**

`masking.py`:

```python
def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
```

Also add `mask_model_config(config)` returning a model dump/copy with masked `api_key`.

`ids.py` creates task IDs like `task_20260805123000_ab12cd34`.

`timing.py` exposes `now_monotonic()` and `elapsed_ms(start)` using `time.perf_counter()`.

`token_estimator.py` exposes `ESTIMATOR_NAME = "simple_mixed_heuristic_v1"` and `estimate_tokens(text)` using CJK characters, words/numbers, and punctuation groups.

- [ ] **Step 5: Import smoke test**

```powershell
uv run python -c "from app.core.models import ModelConfigCreate; from app.utils.masking import mask_secret; print(mask_secret('sk-1234567890')); print(ModelConfigCreate(id='m1', name='M1', protocol='chat_completions', base_url='http://x/v1/', api_key='sk', model='m').base_url)"
```

Expected output includes `sk-1...7890` and `http://x/v1`.

---
## Task 3: Local JSON Storage

**Files:** `app/storage/file_utils.py`, `app/storage/model_store.py`, `app/storage/task_store.py`, `tests/test_models_api.py`.

- [ ] **Step 1: Implement file utilities**

`file_utils.py` must provide `read_json_file(path, default)`, `write_json_file_atomic(path, data)`, and `ensure_parent(path)`. Use UTF-8, `ensure_ascii=False`, `indent=2`, and `os.replace` for atomic writes.

- [ ] **Step 2: Implement `ModelStore`**

Requirements:

- Default file: `Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "models.json"`.
- JSON shape: `{"models": [...]}`.
- Methods: `list()`, `get(model_id)`, `create(config)`, `update(model_id, patch)`, `delete(model_id)`.
- `create` rejects duplicate IDs with `ValueError("model_already_exists:<id>")`.
- `update` raises `KeyError("model_not_found:<id>")` when missing.
- Disk keeps plaintext `api_key`; callers mask responses.

- [ ] **Step 3: Implement `TaskStore`**

Requirements:

- Default dir: `Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "tasks"`.
- Methods: `save(result)`, `get(task_id)`, `list(limit=100)`.
- File path: `data/tasks/<task_id>.json`.
- List sorted by `started_at` descending.

- [ ] **Step 4: Add storage test**

`tests/test_models_api.py` first test:

```python
def test_model_store_create_get_update_delete(tmp_path):
    from app.core.models import ModelConfigCreate, ModelConfigUpdate
    from app.storage.model_store import ModelStore

    store = ModelStore(tmp_path / "models.json")
    created = store.create(ModelConfigCreate(
        id="m1", name="M1", protocol="chat_completions",
        base_url="http://upstream/v1/", api_key="sk-secret-123456", model="model-a"
    ))
    assert created.base_url == "http://upstream/v1"
    assert store.get("m1").api_key == "sk-secret-123456"

    updated = store.update("m1", ModelConfigUpdate(enabled=False, timeout_seconds=30))
    assert updated.enabled is False
    assert updated.timeout_seconds == 30
    assert store.delete("m1") is True
    assert store.get("m1") is None
```

- [ ] **Step 5: Verify**

```powershell
uv run pytest tests/test_models_api.py -q
```

Expected: storage test passes.

---

## Task 4: Plans and Metric Registry

**Files:** `app/core/plans.py`, `app/core/registry.py`, `tests/test_registry.py`.

- [ ] **Step 1: Implement metric catalog**

`app/core/plans.py` defines:

```python
GATEWAY_BASELINE_V1_METRICS = [
    "connectivity", "latency_breakdown", "context_length", "output_length",
    "concurrency", "rate_limit", "error_handling", "token_usage_accuracy", "stream_spec",
]
```

Also define `METRICS: dict[str, MetricInfo]` and `PLANS: dict[str, PlanInfo]`; `stream_spec` priority is `P1`, all other V1 metrics are `P0`.

- [ ] **Step 2: Implement registry lookup**

`app/core/registry.py` functions:

Expose these exact functions with the described behavior:

```text
list_metrics() -> list[MetricInfo]
get_metric(metric_id: str) -> MetricInfo | None
list_plans() -> list[PlanInfo]
get_plan(plan_id: str) -> PlanInfo | None
resolve_metric_ids(plan_id: str, metric_ids: list[str] | None) -> list[str]
```

Invalid input raises `ValueError("invalid_plan:<id>")` or `ValueError("invalid_metric:<id>")`.

- [ ] **Step 3: Add tests**

`tests/test_registry.py`:

```python
def test_gateway_plan_contains_expected_metrics():
    from app.core.registry import resolve_metric_ids
    assert resolve_metric_ids("gateway_baseline_v1", None) == [
        "connectivity", "latency_breakdown", "context_length", "output_length",
        "concurrency", "rate_limit", "error_handling", "token_usage_accuracy", "stream_spec",
    ]


def test_invalid_metric_is_rejected():
    from app.core.registry import resolve_metric_ids
    try:
        resolve_metric_ids("gateway_baseline_v1", ["not_exist"])
    except ValueError as exc:
        assert str(exc) == "invalid_metric:not_exist"
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 4: Verify**

```powershell
uv run pytest tests/test_registry.py -q
```

Expected: registry tests pass.

---

## Task 5: SSE Parser and HTTP Adapters

**Files:** `app/utils/sse.py`, `app/adapters/base.py`, `app/adapters/chat_completions.py`, `app/adapters/responses.py`, `tests/test_sse.py`, `tests/test_adapters.py`.

- [ ] **Step 1: Implement SSE parser**

`parse_sse_events(raw_lines: list[str]) -> list[str]` behavior:

- Collect `data:` lines into event payloads.
- Ignore lines beginning with `:`.
- Blank line ends one event.
- Preserve `[DONE]` as a payload.

Test:

```python
def test_parse_sse_events_with_done():
    from app.utils.sse import parse_sse_events
    assert parse_sse_events(['data: {"a":1}', '', 'data: [DONE]', '']) == ['{"a":1}', '[DONE]']
```

- [ ] **Step 2: Implement adapter base**

`BaseAdapter(config)` has async `complete(request)` and `stream(request)` methods. `create_adapter(config)` returns `ChatCompletionsAdapter` or `ResponsesAdapter`, else raises `ValueError("invalid_protocol:<protocol>")`.

- [ ] **Step 3: Implement Chat Completions adapter**

Non-stream request:

- URL: `{base_url}/chat/completions`.
- Body: `model`, `messages`, `temperature`, `stream=false`, optional `max_tokens`, merged `extra_body`.
- Extract: `choices[0].message.content`, `choices[0].finish_reason`, top-level `usage`.

Stream request:

- Body same but `stream=true`.
- Parse SSE `data:` chunks.
- Extract delta content from `choices[0].delta.content`.
- Track TTFT, end-to-end latency, event count, parse errors, `[DONE]`, finish reason, usage.

- [ ] **Step 4: Implement Responses adapter**

Non-stream request:

- URL: `{base_url}/responses`.
- Body: `model`, `input`, `temperature`, `stream=false`, optional `max_output_tokens`, merged `extra_body`.
- Extract content from `output_text`, or fallback to `output[*].content[*].text`.
- Extract usage from top-level `usage`.

Stream request:

- Body same but `stream=true`.
- Handle event shapes such as `response.output_text.delta`, `response.completed`, `response.output_item.done`, plus generic `delta`/`text` fields.

- [ ] **Step 5: Add adapter tests using `httpx.MockTransport`**

Tests assert:

- Chat URL path is `/chat/completions`.
- Responses URL path is `/responses`.
- Header has `Authorization: Bearer <key>`.
- Content, finish reason, status, and usage normalize into adapter response objects.

- [ ] **Step 6: Verify**

```powershell
uv run pytest tests/test_sse.py tests/test_adapters.py -q
```

Expected: all parser and adapter tests pass without real API calls.

---
## Task 6: Metric Probes

**Files:** `app/metrics/base.py`, `app/metrics/probes.py`.

- [ ] **Step 1: Implement result helpers**

`app/metrics/base.py` exposes:

Expose these exact helper functions:

```text
completed(metric_id: str, summary: str, observations: dict) -> MetricResult
errored(metric_id: str, summary: str, observations: dict, errors: list[dict]) -> MetricResult
skipped(metric_id: str, summary: str, observations: dict | None = None) -> MetricResult
```

- [ ] **Step 2: Implement `run_connectivity_probe`**

Prompt: `请用一句话说明大模型 API 验证服务的作用。`

Observations: `http_status`, `latency_ms`, `response_json_parseable`, `content_present`, `content_excerpt`, `finish_reason`, `usage_present`.

Error when request fails, HTTP status is >= 400, JSON is not parseable, or content is empty.

- [ ] **Step 3: Implement `run_usage_probe` for `token_usage_accuracy`**

Prompt: `请用三句话解释什么是 API 网关。`

Observations: `usage_present`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_prompt_tokens`, `estimated_completion_tokens`, `prompt_token_delta`, `completion_token_delta`, `token_error_ratio`, `estimator`.

Missing `usage` is `error` for this metric.

- [ ] **Step 4: Implement `run_stream_probe` for `latency_breakdown` and `stream_spec`**

Prompt: `请用中文分 5 点简要说明：为什么大模型 API 上线前需要做工程验证。`

`latency_breakdown` observations: `ttft_ms`, `end_to_end_latency_ms`, `stream_duration_ms`, `output_char_count`, `estimated_output_tokens`, `tps_estimated`, `stream_event_count`, `first_content_at`, `finished_at`.

`stream_spec` observations: `sse_parseable`, `data_line_count`, `event_count`, `parse_error_count`, `done_event_present`, `finish_reason`, `finish_reason_present`, `stream_usage_present`, `raw_event_excerpt`.

`stream_usage_present=false` does not become `error` by itself.

- [ ] **Step 5: Implement `run_output_length_probe`**

Prompt: `请生成一篇结构化中文说明文，主题是“大模型 API 网关上线前验证”，尽量详细展开，不要提前结束。`

Use `declared_max_output_tokens`; if missing use `1024` and set `used_default_max_tokens=true`.

Observations: `requested_max_tokens`, `used_default_max_tokens`, `output_char_count`, `estimated_output_tokens`, `finish_reason`, `usage_completion_tokens`, `content_excerpt`.

- [ ] **Step 6: Implement `run_context_length_probe`**

If `declared_context_tokens` is missing, return `skipped`.

Test points:

- declared <= 8192: `[4096, declared]`
- declared <= 32768: `[4096, declared]` with declared usually 32768
- declared > 32768: `[4096, 32768, declared]`

Insert marker `[CONTEXT_MARKER_7F3A9C]` near tail and ask: `请回答上文最后出现的 CONTEXT_MARKER 是什么，只输出标记本身。`

Observations: `declared_context_tokens`, `test_points`, `marker`, `point_results`.

- [ ] **Step 7: Implement `run_error_handling_probe`**

Cases: `invalid_api_key`, `invalid_model`, `empty_input`, `invalid_parameter`, `context_overflow`.

Record actual behavior only: `case_id`, `http_status`, `latency_ms`, `error_shape_present`, `error_code`, `error_message_excerpt`, `raw_excerpt`.

Do not require exact 401/404/429 status codes.

- [ ] **Step 8: Implement `run_concurrency_probe` and derive `rate_limit`**

For each configured level, send short non-stream requests with `asyncio.gather(return_exceptions=True)`.

`concurrency` observations: `levels`, `per_level`, `total_requests`, `success_count`, `error_count`, `rate_limited_count`.

`rate_limit` observations: `rate_limited_count`, `rate_limited_http_statuses`, `first_rate_limit_observed_at_level`, `examples`.

429 is an observation, not automatic metric failure. If all concurrency requests fail, mark `concurrency` as `error`.

- [ ] **Step 9: Verify imports**

```powershell
uv run python -c "from app.metrics.probes import run_connectivity_probe, run_usage_probe, run_stream_probe; print('ok')"
```

Expected: `ok`.

---

## Task 7: Task Runner and Markdown Reports

**Files:** `app/core/runner.py`, `app/reports/markdown.py`, `tests/test_runner_fake_upstream.py`.

- [ ] **Step 1: Implement `TaskRunner`**

Behavior:

- Validate model exists, `enabled=true`, and protocol is supported.
- Resolve metric list from `plan_id` or explicit `metric_ids`.
- Create adapter through `create_adapter(config)`.
- Execute probes in order: connectivity; token usage; stream latency/spec; output length; context length; error handling; concurrency/rate limit.
- Continue metric-level execution after metric errors to collect more observations.
- Task-level `error` only for invalid model, disabled model, invalid protocol, adapter creation failure, or unrecoverable storage/report failure.
- Save task JSON before returning.
- Generate report and set `report_path`.

- [ ] **Step 2: Implement Markdown report**

Report sections:

1. Title and task metadata.
2. Model ID and plan ID.
3. Summary table: metric ID, status, summary.
4. Per-metric observations as fenced JSON.
5. Per-metric errors as fenced JSON.
6. `token_usage_accuracy` note: `本地 token 数为估算值，仅用于辅助观察，不作为自动判定依据。`

The report must not include plaintext API keys.

- [ ] **Step 3: Add fake upstream integration test**

`tests/test_runner_fake_upstream.py` must run full `gateway_baseline_v1` against a fake upstream implemented with `httpx.MockTransport` or a local FastAPI app. It returns normal non-stream JSON, stream SSE chunks, and controlled error responses.

Assertions:

```python
assert result.status == "completed"
assert {r.metric_id for r in result.results} == {
    "connectivity", "latency_breakdown", "context_length", "output_length",
    "concurrency", "rate_limit", "error_handling", "token_usage_accuracy", "stream_spec",
}
assert result.report_path is not None
assert Path(result.report_path).exists()
text = Path(result.report_path).read_text(encoding="utf-8")
assert "本地 token 数为估算值" in text
assert "sk-" not in text
```

- [ ] **Step 4: Verify**

```powershell
uv run pytest tests/test_runner_fake_upstream.py -q
```

Expected: full plan executes against fake upstream and creates task JSON/report.

---

## Task 8: FastAPI Routes

**Files:** `app/main.py`, `app/api/routes_models.py`, `app/api/routes_metrics.py`, `app/api/routes_tasks.py`, `app/api/routes_reports.py`, `tests/test_models_api.py`.

- [ ] **Step 1: Implement app wiring**

`app/main.py`:

- `FastAPI(title="LLM Benchmark", version="0.1.0")`.
- Include routers under `/api`.
- `GET /health` returns `{"status":"ok"}`.

- [ ] **Step 2: Model routes**

Endpoints:

```http
POST   /api/models
GET    /api/models
GET    /api/models/{model_id}
PUT    /api/models/{model_id}
DELETE /api/models/{model_id}
```

Responses mask `api_key`. Errors: `model_not_found`, `model_already_exists`, `storage_error`.

- [ ] **Step 3: Metrics and plans routes**

Endpoints:

```http
GET /api/metrics
GET /api/plans
GET /api/plans/{plan_id}
```

Missing plan returns 404 with `plan_not_found`.

- [ ] **Step 4: Task routes**

Endpoints:

```http
POST /api/tasks/run
GET  /api/tasks
GET  /api/tasks/{task_id}
```

`POST /api/tasks/run` executes synchronously and returns the `TaskResult` JSON.

- [ ] **Step 5: Report route**

Endpoint:

```http
GET /api/reports/{task_id}
```

Return Markdown as `text/markdown; charset=utf-8`; missing report returns 404 with `report_not_found`.

- [ ] **Step 6: API tests**

Update `tests/test_models_api.py` to use FastAPI `TestClient` and temp data dir. Assert:

- Create model response masks `api_key`.
- Get model response masks `api_key`.
- `data/models.json` contains plaintext key.
- Delete removes the record.

- [ ] **Step 7: Verify**

```powershell
uv run pytest tests/test_models_api.py tests/test_registry.py -q
```

Expected: API route tests pass.

---
## Task 9: End-to-End Verification and README

**Files:** `README.md`; generated `data/tasks/*.json`; generated `reports/YYYY-MM-DD/*.md`.

- [ ] **Step 1: Run full test suite**

```powershell
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Start service**

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: uvicorn starts; `/docs` is accessible.

- [ ] **Step 3: Verify health**

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -Method Get
```

Expected: `status` is `ok`.

- [ ] **Step 4: Verify built-in plan**

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/plans/gateway_baseline_v1' -Method Get | ConvertTo-Json -Depth 10
```

Expected: response includes all nine metric IDs.

- [ ] **Step 5: Verify model config API**

```powershell
$body = @{
  id = 'demo-chat'
  name = 'Demo Chat'
  protocol = 'chat_completions'
  base_url = 'http://127.0.0.1:9001/v1'
  api_key = 'sk-demo-secret'
  model = 'demo-model'
  timeout_seconds = 60
  enabled = $true
  declared_context_tokens = 8192
  declared_max_output_tokens = 1024
  concurrency_levels = @(1, 2)
} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/models' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 10
```

Expected: API response masks the key; `data/models.json` stores local plaintext.

- [ ] **Step 6: Verify task run against fake upstream**

Start the fake upstream used by tests or run the test suite's fake upstream helper on port `9001`. Then:

```powershell
$runBody = @{ model_id = 'demo-chat'; plan_id = 'gateway_baseline_v1' } | ConvertTo-Json
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/tasks/run' -Method Post -ContentType 'application/json' -Body $runBody
$result | ConvertTo-Json -Depth 20
$taskId = $result.task_id
```

Expected:

- Response has `task_id`, `status`, `results`, and `report_path`.
- Results include all nine metrics.
- `data/tasks/<task_id>.json` exists.
- `reports/YYYY-MM-DD/<task_id>.md` exists.

- [ ] **Step 7: Verify report endpoint**

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/reports/$taskId" -OutFile report.md
Get-Content .\report.md -Encoding UTF8 | Select-Object -First 40
```

Expected: Markdown includes metric tables and observations, includes the token-estimator note, and does not expose `sk-demo-secret`.

- [ ] **Step 8: Update README**

README must include:

- Startup commands.
- API list.
- Example model config JSON.
- Example task run JSON.
- Storage layout.
- Explanation that V1 does not output上线通过/失败; personnel analyze the observations.

---

## Self-Review Checklist

- [ ] Every V1 metric in `gateway_baseline_v1` has a probe and a `MetricResult`.
- [ ] Chat Completions and Responses adapters both append the correct endpoint path from `base_url`.
- [ ] `data/models.json`, `data/tasks/*.json`, and `reports/YYYY-MM-DD/*.md` are written.
- [ ] API key is masked in API responses and Markdown reports.
- [ ] Code and docs do not introduce SQL, platform auth, OpenAI SDK, or formal frontend.
- [ ] Status values are limited to `completed`, `error`, and `skipped` for metrics.
- [ ] `uv run pytest -q` passes.
- [ ] Local FastAPI service starts and `/health` returns `{"status":"ok"}`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-llm-benchmark-gateway-baseline-implementation-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh implementation worker per task, review between tasks, faster iteration.
2. **Inline Execution** - execute tasks in this session using the plan, with verification checkpoints.

Which approach?
