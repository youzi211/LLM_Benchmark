#!/usr/bin/env python
"""Start the local LLM_Benchmark service and run deployment health checks."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
HEALTH_PATHS = ("/health", "/api/intelligence/evalscope/health", "/api/stress/evalscope/health")


def _start_main(port: int, env: dict[str, str], log_dir: Path) -> subprocess.Popen[str]:
    stdout = (log_dir / "main.out.log").open("w", encoding="utf-8")
    stderr = (log_dir / "main.err.log").open("w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=stdout,
        stderr=stderr,
        text=True,
    )


def _terminate(processes: list[subprocess.Popen[str]]) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    deadline = time.monotonic() + 10
    for proc in processes:
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            proc.kill()


def _get_json(url: str, timeout: float) -> tuple[int, object]:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - local smoke helper
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else None


def main() -> int:
    parser = argparse.ArgumentParser(description="本地启动单服务并执行健康检查")
    parser.add_argument("--main-port", type=int, default=18000)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--keep-temp", action="store_true", help="保留临时 data/reports/logs 目录用于排查")
    args = parser.parse_args()

    temp_root = Path(tempfile.mkdtemp(prefix="llm-benchmark-deploy-smoke-"))
    data_dir = temp_root / "data"
    reports_dir = temp_root / "reports"
    outputs_dir = temp_root / "outputs" / "evalscope"
    log_dir = temp_root / "logs"
    data_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    (data_dir / "evalscope.json").write_text(
        json.dumps(
            {
                "outputs_dir": str(outputs_dir),
                "datasets_dir": str(data_dir / "evalscope_datasets"),
                "poll_interval_seconds": 1,
                "default_timeout_seconds": 60,
                "stress_timeout_seconds": 60,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["LLM_BENCHMARK_DATA_DIR"] = str(data_dir)
    env["LLM_BENCHMARK_REPORTS_DIR"] = str(reports_dir)
    env["LLM_BENCHMARK_SCHEDULER_DISABLED"] = "1"

    processes: list[subprocess.Popen[str]] = []
    try:
        processes.append(_start_main(args.main_port, env, log_dir))
        deadline = time.monotonic() + args.timeout
        last_error = ""
        urls = [f"http://127.0.0.1:{args.main_port}{path}" for path in HEALTH_PATHS]
        while time.monotonic() < deadline:
            try:
                statuses = [_get_json(url, args.request_timeout) for url in urls]
                if all(200 <= status < 300 for status, _ in statuses):
                    print("部署 smoke 检查通过：")
                    for url, (status, body) in zip(urls, statuses, strict=True):
                        print(f"[OK] {url}: HTTP {status} {body}")
                    return 0
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_error = str(exc)
            time.sleep(1)
        print(f"部署 smoke 检查失败，最后错误：{last_error}", file=sys.stderr)
        print(f"日志目录：{log_dir}", file=sys.stderr)
        return 1
    finally:
        _terminate(processes)
        if args.keep_temp:
            print(f"临时目录已保留：{temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
