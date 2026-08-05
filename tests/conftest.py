from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def temp_data_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("LLM_BENCHMARK_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LLM_BENCHMARK_REPORTS_DIR", str(reports_dir))
    return data_dir, reports_dir
