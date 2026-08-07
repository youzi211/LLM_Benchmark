#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/.tmp/logs"
mkdir -p "$LOG_DIR"

MAIN_PORT="${MAIN_PORT:-8000}"

HOST_ADDRESS=0.0.0.0 PORT="$MAIN_PORT" "$ROOT/scripts/start_main.sh" >"$LOG_DIR/main.out.log" 2>"$LOG_DIR/main.err.log" &
main_pid=$!

cleanup() {
  kill "$main_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "LLM_Benchmark 主服务 PID: $main_pid, 地址: http://127.0.0.1:$MAIN_PORT"
echo "EvalScope 执行模式: in-process（主服务内直接 import evalscope）"
echo "Sandbox 提醒: 本脚本不会启动 ms-enclave；代码评分请提前独立启动 sandbox server。"
echo "日志目录: $LOG_DIR"
wait "$main_pid"
