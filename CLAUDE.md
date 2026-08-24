# LLM_Benchmark — Claude Instructions

This repository is an internal FastAPI service for pre-release LLM gateway benchmarking. `AGENTS.md` is the repository source of truth; follow it in addition to these focused rules.

## Scope and architecture

- Gateway smoke checks live under `app/core/` and `app/metrics/`.
- EvalScope intelligence evaluation lives in `app/intelligence/` and must run in-process.
- EvalScope throughput/performance evaluation lives in `app/stress/` and must run in-process.
- One-click and scheduled orchestration lives in `app/suites/`, with overview reports in `app/overview/`.
- The service collects evidence and reports. It must not automatically decide whether a model is approved for production.

## EvalScope defaults

- General intelligence evaluation defaults to: `humaneval`, `mbpp`, `humaneval_plus`, `mbpp_plus`, `live_code_bench`, `gsm8k`, `math_500`, `mmlu_pro`, `ceval`, and `bbh`.
- Scheduled tasks default to `scheduled_light`: `gsm8k`, `math_500`, and `ceval`, with 50 samples per dataset.
- `scheduled_code` and `full_offline` contain code-execution datasets and require a configured EvalScope sandbox.
- For reliable comparisons, pass `intelligence_datasets`, `intelligence_limit`, `intelligence_eval_batch_size`, and `intelligence_generation_config` explicitly instead of relying on implicit defaults.
- A BBH stability run can take about ten minutes even at one sample per subset; use a suite timeout of at least 1200 seconds and inspect the underlying task status before diagnosing a hang.

## Result and report boundaries

- Keep `normalized_result` limited to UI/overview summaries: status, scores, categories, and safe error summaries.
- Preserve complete EvalScope output only in the task-level `raw_result` and task-scoped `raw_output_dir`.
- Markdown and overview reports should provide raw-result location/API pointers, not duplicate full `report_table`, metrics, or JSON payloads.
- Preserve backward compatibility when reading older task JSON files that contain removed normalized-result fields.

## Development workflow

Use `uv` for Python operations:

```powershell
uv sync
$env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
uv run pytest -q
```

Run the service with the scheduler enabled when validating schedules:

```powershell
Remove-Item Env:LLM_BENCHMARK_SCHEDULER_DISABLED -ErrorAction SilentlyContinue
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020
```

A scheduled task requires a persisted model configuration. The model key is stored in local `data/models.json`; never commit, print, or include it in fixtures, reports, documentation, or chat output.

## Git and review rules

- Use Conventional Commits.
- Stage explicit paths; never use `git add .` because runtime files may contain credentials or large outputs.
- Before committing, inspect `git status`, staged paths, `git diff --cached --check`, and scan staged content for secrets.
- For route, schema, report, EvalScope, or schedule changes, run the full pytest suite with the scheduler disabled and document the command/result.
