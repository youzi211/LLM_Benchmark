# EvalScope Intelligence Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent `/api/intelligence/*` module that lets this service submit EvalScope model intelligence evaluations, track progress, fetch results, and generate Markdown reports.

**Architecture:** Keep baseline gateway engineering tests unchanged. Add a focused `app/intelligence/` package for EvalScope config, HTTP client, runner, schemas, and report rendering; expose it through `app/api/routes_intelligence.py`; persist runtime state under ignored `data/` and `reports/` paths.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, httpx, pytest, pytest-asyncio, local JSON storage, Markdown report files.

---

## File map

- `app/intelligence/schemas.py`: EvalScope config, request, task, and normalized result models.
- `app/intelligence/config_store.py`: load/save `data/evalscope.json`.
- `app/storage/intelligence_task_store.py`: load/save/list `data/intelligence_tasks/*.json`.
- `app/intelligence/evalscope_client.py`: async wrapper for the external EvalScope service.
- `app/intelligence/report.py`: Chinese Markdown report renderer under `reports/intelligence/`.
- `app/intelligence/runner.py`: model lookup, submit, poll/refresh, result normalization, report writing.
- `app/api/routes_intelligence.py`: FastAPI routes under `/api/intelligence/*`.
- `app/main.py`: include intelligence router.
- `docs/api.md`, `docs/architecture.md`, `README.md`: document the new capability.
- `tests/test_intelligence_*.py`, `tests/test_docs_coverage.py`: protect behavior and docs coverage.

## Tasks

### Task 1: Schemas and EvalScope config store

**Files:** create `app/intelligence/__init__.py`, `app/intelligence/schemas.py`, `app/intelligence/config_store.py`, `tests/test_intelligence_config_store.py`.

- [ ] Define `EvalScopeConfig` with `base_url`, `poll_interval_seconds`, `default_timeout_seconds`; strip trailing slash in a Pydantic validator.
- [ ] Define request models: `IntelligenceDefaultRunRequest(model_id)`, `IntelligenceRunRequest(model_id, datasets, limit, eval_batch_size, generation_config)`.
- [ ] Define result models: `IntelligenceDatasetResult`, `IntelligenceCategorySummary`, `IntelligenceNormalizedResult`, `IntelligenceTask`.
- [ ] Implement `EvalScopeConfigStore.load()` returning defaults when the file does not exist.
- [ ] Implement `EvalScopeConfigStore.save(config)` using `write_json_file`.
- [ ] Test default load, trailing slash normalization, and save/reload round trip.

### Task 2: Intelligence task store and ignore rules

**Files:** create `app/storage/intelligence_task_store.py`, `tests/test_intelligence_task_store.py`; modify `.gitignore`.

- [ ] Add ignore rules for `/data/evalscope.json`, `/data/intelligence_tasks/`, and `/reports/intelligence/`.
- [ ] Implement `save(task)`, `load(task_id)`, and `list(limit=50)` for `intel_task_*.json` files.
- [ ] Ensure `list()` returns newest first and skips malformed JSON files.
- [ ] Test save/load, missing task, newest-first list, and malformed-file skip.

### Task 3: EvalScope HTTP client

**Files:** create `app/intelligence/evalscope_client.py`, `tests/test_evalscope_client.py`.

- [ ] Implement `EvalScopeClientError` and `EvalScopeClient` with injectable `httpx.AsyncBaseTransport` for tests.
- [ ] Implement `health`, `judge_config`, `datasets`, `local_datasets`, `submit_default`, `submit_custom`, `task_status`, and `task_result`.
- [ ] Raise `EvalScopeClientError` for non-2xx responses and redact response text through `redact_text`.
- [ ] Test correct paths/payloads with `httpx.MockTransport`; test HTTP error redaction.

### Task 4: Runner, ID generation, normalization

**Files:** create `app/intelligence/runner.py`, `tests/test_intelligence_runner.py`.

- [ ] Implement `new_intelligence_task_id()` returning `intel_task_YYYYMMDDHHMMSS_xxxxxxxx`.
- [ ] Implement `IntelligenceRunner.submit_default()` and `submit_custom()` by reading the model from `ModelStore` and submitting to EvalScope.
- [ ] Persist local task status after submit, refresh, result fetch, failures, and report write.
- [ ] Implement `refresh_status(task_id)` and `fetch_result(task_id)`.
- [ ] Normalize EvalScope result rows into dataset score rows and category summaries, using local dataset metadata when available.
- [ ] Test model-not-found behavior, submit persistence, refresh updates, result normalization, and report path persistence.

### Task 5: Markdown intelligence report

**Files:** create `app/intelligence/report.py`, `tests/test_intelligence_report.py`.

- [ ] Render a Chinese report titled `大模型智力评测报告`.
- [ ] Include sections: `一眼看懂`, task overview, dataset score table, category summary, EvalScope raw `report_table`, and JSON appendix.
- [ ] Redact secrets with `redact_text` before writing.
- [ ] Test report file creation, Chinese sections, table content, and secret redaction.

### Task 6: FastAPI routes

**Files:** create `app/api/routes_intelligence.py`, `tests/test_intelligence_api.py`; modify `app/main.py`.

- [ ] Add routes: `GET /api/intelligence/evalscope/health`, `GET /api/intelligence/evalscope/judge-config`, `GET /api/intelligence/datasets`, `GET /api/intelligence/datasets/local`.
- [ ] Add task routes: `POST /api/intelligence/tasks/default`, `POST /api/intelligence/tasks`, `GET /api/intelligence/tasks`, `GET /api/intelligence/tasks/{task_id}`, `GET /api/intelligence/tasks/{task_id}/result`, `GET /api/intelligence/reports/{task_id}`.
- [ ] Map missing resources to `api_error(..., 404, ...)` and EvalScope failures to `evalscope_error` with status 502.
- [ ] Include the router in `app/main.py` with prefix `/api`.
- [ ] Test OpenAPI path presence and happy/error route behavior with monkeypatched runner/client factories.

### Task 7: Documentation updates

**Files:** modify `docs/api.md`, `docs/architecture.md`, `README.md`, `tests/test_docs_coverage.py`.

- [ ] Document all intelligence endpoints with purpose, request fields, response shape, and error semantics.
- [ ] Update architecture to show the new independent EvalScope intelligence path and runtime storage.
- [ ] Add README link/summary for the intelligence capability.
- [ ] Extend docs coverage tests for `/api/intelligence/tasks/default`, `/api/intelligence/tasks/{task_id}/result`, `智力评测`, and `EvalScope`.

### Task 8: Verification and commits

**Files:** all changed files.

- [ ] Run `uv run pytest -q`; expected: all tests pass.
- [ ] Run a small OpenAPI smoke script that prints paths starting with `/api/intelligence`.
- [ ] Run `git diff HEAD -- app docs tests README.md .gitignore | Select-String -Pattern 'sk-|api_key|secret' -Context 1,1`; expected: no real secrets.
- [ ] Stage explicit files only and commit with Conventional Commits.
