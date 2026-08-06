# EvalScope Intelligence Integration Implementation Plan (superseded by in-process design)

> **Status:** this original plan has been superseded by the 2026-08-06 simplification. It is kept as historical context only.

**Current goal:** expose `/api/intelligence/*` so this service can run EvalScope model intelligence evaluations, track local task state, normalize results, and generate Markdown reports.

**Current architecture:** keep baseline gateway engineering tests unchanged. `app/intelligence/` now calls EvalScope directly in the main service process via `evalscope.run_task(TaskConfig)`. Runtime state stays under ignored `data/` and `reports/` paths, while EvalScope raw artifacts go under `outputs/evalscope/`.

## Current file map

- `app/intelligence/schemas.py`: EvalScope config, request, task, and normalized result models.
- `app/intelligence/config_store.py`: load/save `data/evalscope.json`; historical `base_url` is accepted only for compatibility.
- `app/intelligence/evalscope_direct.py`: health check, dataset metadata, Judge status, and direct `run_task(TaskConfig)` execution.
- `app/storage/intelligence_task_store.py`: load/save/list `data/intelligence_tasks/*.json`.
- `app/intelligence/report.py`: Chinese Markdown report renderer under `reports/intelligence/`.
- `app/intelligence/runner.py`: model lookup, direct EvalScope execution, result normalization, report writing.
- `app/api/routes_intelligence.py`: FastAPI routes under `/api/intelligence/*`.
- `docs/api.md`, `docs/architecture.md`, `README.md`: document the current in-process capability.
- `tests/test_intelligence_*.py`, `tests/test_docs_coverage.py`: protect behavior and docs coverage.

## Maintenance notes

1. Confirm EvalScope API signatures from official docs or the installed package before changing invocation code.
2. Do not write plaintext `api_key` into task JSON, reports, logs, or documentation.
3. Keep `/api/tasks/run` as gateway smoke; ability evaluation belongs to `/api/intelligence/*`.
4. When result formats change, update `app/intelligence/runner.py`, report rendering, API docs, and tests together.
