#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/.tmp/logs"
mkdir -p "$LOG_DIR"

MAIN_PORT="${MAIN_PORT:-8000}"
START_SANDBOX="${START_SANDBOX:-0}"
SANDBOX_HOST="${SANDBOX_HOST:-0.0.0.0}"
SANDBOX_PORT="${SANDBOX_PORT:-1234}"

main_pid=""
sandbox_pid=""

cleanup() {
  if [[ -n "$main_pid" ]]; then
    kill "$main_pid" 2>/dev/null || true
  fi
  if [[ -n "$sandbox_pid" ]]; then
    kill "$sandbox_pid" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

if [[ "$START_SANDBOX" == "1" || "$START_SANDBOX" == "true" || "$START_SANDBOX" == "True" ]]; then
  if ! command -v ms-enclave >/dev/null 2>&1; then
    echo "未找到 ms-enclave 命令；请先安装 evalscope[sandbox] 或关闭 START_SANDBOX。" >&2
    exit 127
  fi
  ms-enclave server --host "$SANDBOX_HOST" --port "$SANDBOX_PORT" >>"$LOG_DIR/sandbox.out.log" 2>>"$LOG_DIR/sandbox.err.log" &
  sandbox_pid=$!
  printf '\n=== %s 启动 sandbox (PID %s, 端口 %s) ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$sandbox_pid" "$SANDBOX_PORT" | tee -a "$LOG_DIR/sandbox.out.log" "$LOG_DIR/sandbox.err.log" >/dev/null
  echo "EvalScope sandbox PID: $sandbox_pid, 地址: http://127.0.0.1:$SANDBOX_PORT"
else
  echo "Sandbox 模式: 默认不启动；如需随脚本启动，设置 START_SANDBOX=1。"
fi

HOST_ADDRESS=0.0.0.0 PORT="$MAIN_PORT" "$ROOT/scripts/start_main.sh" >>"$LOG_DIR/main.out.log" 2>>"$LOG_DIR/main.err.log" &
main_pid=$!
printf '\n=== %s 启动 main (PID %s, 端口 %s) ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$main_pid" "$MAIN_PORT" | tee -a "$LOG_DIR/main.out.log" "$LOG_DIR/main.err.log" >/dev/null

echo "LLM_Benchmark 主服务 PID: $main_pid, 地址: http://127.0.0.1:$MAIN_PORT"
echo "EvalScope 执行模式: in-process（主服务内直接 import evalscope）"
if [[ -n "$sandbox_pid" ]]; then
  echo "Sandbox 模式: 已随脚本启动 ms-enclave；日志: $LOG_DIR/sandbox.out.log / $LOG_DIR/sandbox.err.log"
else
  echo "Sandbox 提醒: 默认不会启动 ms-enclave；代码评分请提前独立启动，或设置 START_SANDBOX=1。"
fi
echo "日志目录: $LOG_DIR"

if [[ -n "$sandbox_pid" ]]; then
  while kill -0 "$main_pid" 2>/dev/null; do
    if ! kill -0 "$sandbox_pid" 2>/dev/null; then
      wait "$sandbox_pid" || true
      echo "EvalScope sandbox 已退出，正在停止主服务。请查看 $LOG_DIR/sandbox.err.log。" >&2
      kill "$main_pid" 2>/dev/null || true
      wait "$main_pid" || true
      exit 1
    fi
    sleep 2
  done
fi

wait "$main_pid"
