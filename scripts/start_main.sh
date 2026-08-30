#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
PORT="${PORT:-8020}"

# EvalScope SandboxService 是进程级单例，并发智力评测任务会在各自 run_task 的 finally
# 里互相 shutdown 共享沙箱，导致代码类数据集（mbpp/humaneval 等）批量执行失败。
# 因此智力评测任务默认串行执行（并发=1）。如确需并发，显式覆盖该变量即可。
export LLM_BENCHMARK_EVALSCOPE_JOB_MAX_CONCURRENCY="${LLM_BENCHMARK_EVALSCOPE_JOB_MAX_CONCURRENCY:-1}"

cd "$ROOT"
cmd=(uv run)
if [[ "${NO_SYNC:-0}" == "1" ]]; then
  cmd+=(--no-sync)
fi
cmd+=(uvicorn app.main:app --host "$HOST_ADDRESS" --port "$PORT")
exec "${cmd[@]}"
