#!/usr/bin/env python
"""Check a single-process LLM_Benchmark deployment."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import urlopen


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str


def _join(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _get_json(url: str, timeout: float) -> tuple[int, object]:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - deployment helper
        body = response.read().decode("utf-8")
        data = json.loads(body) if body else None
        return response.status, data


def _check_once(endpoints: list[Endpoint], request_timeout: float) -> tuple[bool, list[str]]:
    messages: list[str] = []
    ok = True
    for endpoint in endpoints:
        try:
            status, data = _get_json(endpoint.url, request_timeout)
            if 200 <= status < 300:
                messages.append(f"[OK] {endpoint.name}: HTTP {status} {data}")
            else:
                ok = False
                messages.append(f"[FAIL] {endpoint.name}: HTTP {status} {data}")
        except HTTPError as exc:
            ok = False
            messages.append(f"[FAIL] {endpoint.name}: HTTP {exc.code} {exc.reason}")
        except (URLError, TimeoutError, OSError) as exc:
            ok = False
            messages.append(f"[WAIT] {endpoint.name}: {exc}")
    return ok, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="验证单服务部署是否可用")
    parser.add_argument("--main-url", default="http://127.0.0.1:8020", help="LLM_Benchmark 主服务地址")
    parser.add_argument("--timeout", type=float, default=60.0, help="整体等待超时时间，秒")
    parser.add_argument("--request-timeout", type=float, default=5.0, help="单次 HTTP 请求超时时间，秒")
    parser.add_argument("--interval", type=float, default=1.0, help="重试间隔，秒")
    args = parser.parse_args()

    endpoints = [
        Endpoint("LLM_Benchmark health", _join(args.main_url, "/health")),
        Endpoint("LLM_Benchmark EvalScope intelligence health", _join(args.main_url, "/api/intelligence/evalscope/health")),
        Endpoint("LLM_Benchmark EvalScope stress health", _join(args.main_url, "/api/stress/evalscope/health")),
    ]

    deadline = time.monotonic() + args.timeout
    last_messages: list[str] = []
    while True:
        ok, messages = _check_once(endpoints, args.request_timeout)
        last_messages = messages
        if ok:
            print("部署健康检查通过：")
            print("\n".join(messages))
            return 0
        if time.monotonic() >= deadline:
            print("部署健康检查失败：")
            print("\n".join(last_messages))
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
