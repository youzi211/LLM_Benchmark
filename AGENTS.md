# Repository Guidelines

## Project Structure & Module Organization

This repository is an internal LLM API gateway baseline benchmark service built with FastAPI. Source code lives in `app/`:

- `app/main.py` and `app/api/`: FastAPI app and public routes.
- `app/core/`: Pydantic models, plans, registry, and `TaskRunner` orchestration.
- `app/adapters/`: OpenAI-compatible protocol adapters for `chat_completions` and `responses`.
- `app/metrics/`: benchmark probe implementations.
- `app/reports/`: fact pack extraction, LLM report analysis, and Markdown rendering.
- `app/storage/`: local JSON persistence.
- `app/utils/`: IDs, masking, SSE, timing, and token estimation helpers.

Tests are in `tests/`. Local fake upstream assets are in `examples/`. Project documentation is in `docs/`, especially `docs/architecture.md`, `docs/api.md`, and `docs/metric-test-methods.md`.

## Build, Test, and Development Commands

Use `uv` for all Python environment and dependency operations.

```powershell
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run uvicorn examples.fake_openai_server:app --host 127.0.0.1 --port 9001
uv run pytest -q
```

`uv sync` installs dependencies. The first `uvicorn` command starts the benchmark API. The fake upstream server helps verify end-to-end flows without real model credentials. `pytest` runs the full test suite.

## Coding Style & Naming Conventions

Use Python 3.11+, 4-space indentation, type hints, and Pydantic models for request/response structures. Keep metric IDs stable and English-like, for example `context_length`; user-facing names and explanations should be Chinese-friendly. Prefer small functions with clear return models such as `MetricResult`, `AdapterResponse`, and `ReportAnalysis`.

## Testing Guidelines

Tests use `pytest` and `pytest-asyncio`. Name files `test_*.py` and keep tests close to the behavior being protected: adapters, registry, probes, reports, API routes, and docs coverage. When changing routes, metrics, or report structure, update tests and run:

```powershell
uv run pytest -q
```

## Commit & Pull Request Guidelines

Follow Conventional Commits as used in history, for example `fix: ...`, `docs: ...`, `test: ...`, `merge: ...`. Stage explicit files only; avoid `git add .` because runtime directories may contain sensitive data. PRs should describe the change, list verification commands, and mention documentation updates when APIs, metrics, architecture, or reports change.

## Security & Configuration Tips

Do not commit `data/models.json`, `data/tasks/`, `reports/`, `.env`, or `.venv/`. `data/models.json` may contain plaintext upstream API keys. API responses and reports should remain redacted; never paste secrets into commits, reports, or logs.
