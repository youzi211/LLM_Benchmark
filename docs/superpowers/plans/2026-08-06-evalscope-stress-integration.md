# EvalScope stress integration plan (superseded by in-process design)

**Status:** superseded during the 2026-08-06 refactor.

**Current architecture:** `LLM_Benchmark` exposes `/api/stress/*`, reads local model config, maps protocol to EvalScope perf parameters, and executes EvalScope in the main service process via `evalscope.perf.main.run_perf_benchmark(Arguments)`. The system stores local task JSON and writes Chinese Markdown reports. No separate EvalScope HTTP wrapper is started.

## Current implementation checklist

1. Keep request/response schemas in `app/stress/schemas.py`.
2. Keep direct EvalScope invocation in `app/stress/evalscope_direct.py`.
3. Keep orchestration, normalization, task persistence, and report generation in `app/stress/runner.py`.
4. Keep public routes in `app/api/routes_stress.py`.
5. Verify with `tests/test_stress_runner.py`, `tests/test_stress_api.py`, and deployment asset tests.

## Rationale

The old two-process wrapper added unnecessary startup, polling, HTTP error handling, and duplicated state. The project now uses EvalScope as a Python dependency directly and leaves visualization/raw artifacts under `outputs/evalscope/`.
