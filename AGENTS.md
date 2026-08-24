# Repository Guidelines

## Codex Fast Context

This repository is an internal FastAPI service for pre-release LLM gateway benchmarking. It has three evaluation lanes and one orchestration layer:

1. **Gateway smoke / engineering checks**: `/api/tasks/run`, implemented by `app/core/runner.py` + `app/metrics/probes.py`. These are lightweight OpenAI-compatible API checks and Markdown reports.
2. **EvalScope intelligence evaluation**: `/api/intelligence/*`, implemented by `app/intelligence/*`. The service imports EvalScope directly in-process; do not reintroduce an EvalScope sidecar service wrapper.
3. **EvalScope stress/perf testing**: `/api/stress/*`, implemented by `app/stress/*`. This is the formal throughput/latency pressure-test path; `concurrency` and `rate_limit` in `/api/tasks/run` are only compatibility smoke metrics.
4. **One-click and scheduled evaluation**: `/api/suites/*`, implemented by `app/suites/*`, orchestrates the three lanes and writes an overview report via `app/overview/*`.

Current product boundary: the system collects evidence and reports; it does **not** automatically decide whether a model can go live. Prefer small, direct integrations over extra services or heavy abstractions.

## Project Structure & Module Organization

Source code lives in `app/`:

- `app/main.py` and `app/api/`: FastAPI app and public routes.
- `app/core/`: Pydantic models, plans, registry, and `TaskRunner` orchestration for gateway smoke tasks.
- `app/adapters/`: OpenAI-compatible protocol adapters for `chat_completions` and `responses`.
- `app/metrics/`: gateway smoke probe implementations.
- `app/reports/`: fact pack extraction, LLM report analysis, and Markdown rendering for gateway smoke tasks.
- `app/intelligence/`: in-process EvalScope model-capability evaluation and reports.
- `app/stress/`: in-process EvalScope `perf` pressure testing and reports.
- `app/overview/`: unified overview reports that link gateway, intelligence, and stress outputs.
- `app/suites/`: one-click suite runs and lightweight scheduled execution.
- `app/storage/`: local JSON persistence.
- `app/utils/`: IDs, masking, SSE, timing, and token estimation helpers.

Tests are in `tests/`. Local fake upstream assets are in `examples/`. Project documentation is in `docs/`, especially `docs/architecture.md`, `docs/api.md`, and `docs/metric-test-methods.md`.

## Build, Test, and Development Commands

Use `uv` for all Python environment and dependency operations.

```powershell
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020
uv run uvicorn examples.fake_openai_server:app --host 127.0.0.1 --port 9001
uv run pytest -q
```

`uv sync` installs dependencies. The first `uvicorn` command starts the benchmark API and the suite scheduler unless `LLM_BENCHMARK_SCHEDULER_DISABLED=1` is set. The fake upstream server helps verify end-to-end flows without real model credentials. `pytest` runs the full test suite.

For test runs in development, prefer:

```powershell
$env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
uv run pytest -q
```

## Configuration and Runtime Files

- `data/models.json` stores model configs and may contain plaintext upstream API keys. Never commit or paste it.
- `analysis_model_id` in `data/models.json` is reused as the default built-in EvalScope Judge model.
- Optional `data/evalscope.json` is intentionally small: use it only for EvalScope dataset/output directories and optional Judge override knobs such as `judge_model_config_id`, `judge_generation_config`, and `judge_worker_num`. Do not store Judge URLs or keys there.
- Runtime output directories include `data/tasks/`, `data/jobs/`, `data/intelligence_tasks/`, `data/stress_tasks/`, `data/overview_reports/`, `data/suite_runs/`, `data/suite_schedules/`, `reports/`, and `outputs/`.

## Coding Style & Naming Conventions

Use Python 3.11+, 4-space indentation, type hints, and Pydantic models for request/response structures. Keep metric IDs stable and English-like, for example `context_length`; user-facing names and explanations should be Chinese-friendly. Prefer small functions with clear return models such as `MetricResult`, `AdapterResponse`, and `ReportAnalysis`.

When changing EvalScope integration, keep the main service in-process and direct. Validate EvalScope API changes against the installed package or official docs before changing runner code.

## Testing Guidelines

Tests use `pytest` and `pytest-asyncio`. Name files `test_*.py` and keep tests close to the behavior being protected: adapters, registry, probes, reports, API routes, EvalScope direct execution wrappers, suite orchestration, and docs coverage. When changing routes, metrics, report structure, suite behavior, or EvalScope config semantics, update tests and run:

```powershell
$env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
uv run pytest -q
```

## Commit & Pull Request Guidelines

Follow Conventional Commits as used in history, for example `fix: ...`, `docs: ...`, `test: ...`, `refactor: ...`. Stage explicit files only; avoid `git add .` because runtime directories may contain sensitive data. PRs should describe the change, list verification commands, and mention documentation updates when APIs, metrics, architecture, or reports change.

## Security & Configuration Tips

Do not commit `data/models.json`, `data/evalscope.json`, `data/tasks/`, `data/jobs/`, `data/intelligence_tasks/`, `data/stress_tasks/`, `data/overview_reports/`, `data/suite_runs/`, `data/suite_schedules/`, `reports/`, `outputs/`, `.env`, or `.venv/`. API responses and reports should remain redacted; never paste secrets into commits, reports, logs, or documentation examples.

Before committing, explicitly inspect staged paths and check for secrets. Dummy test strings are fine, but real `sk-...` or `ark-...` keys are not.