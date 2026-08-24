from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.models import utc_now
from app.storage.file_utils import read_json_file, write_json_file_atomic
from app.suites.schemas import SuiteRun, SuiteSchedule, SuiteScheduleCreate
from app.suites.profiles import apply_profile_to_schedule_request


class SuiteRunStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "suite_runs")

    def _path(self, suite_id: str) -> Path:
        return self.directory / f"{suite_id}.json"

    def save(self, suite: SuiteRun) -> SuiteRun:
        write_json_file_atomic(self._path(suite.suite_id), suite.model_dump(mode="json"))
        return suite

    def get(self, suite_id: str) -> SuiteRun | None:
        path = self._path(suite_id)
        if not path.exists():
            return None
        return SuiteRun.model_validate(read_json_file(path, {}))

    def list(self, limit: int = 50) -> list[SuiteRun]:
        if not self.directory.exists():
            return []
        suites: list[SuiteRun] = []
        for path in self.directory.glob("suite_*.json"):
            try:
                suites.append(SuiteRun.model_validate(read_json_file(path, {})))
            except Exception:
                continue
        suites.sort(key=lambda item: (item.created_at, item.suite_id), reverse=True)
        return suites[:limit]


class SuiteScheduleStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (Path(os.getenv("LLM_BENCHMARK_DATA_DIR", "data")) / "suite_schedules")

    def _path(self, schedule_id: str) -> Path:
        return self.directory / f"{schedule_id}.json"

    def create(self, request: SuiteScheduleCreate) -> SuiteSchedule:
        request = apply_profile_to_schedule_request(request)
        if request.next_run_at is not None:
            next_run_at = ensure_aware_utc(request.next_run_at)
        elif request.run_once and request.run_date is not None:
            next_run_at = compute_one_shot_run_at(request.run_date, request.time_of_day, request.timezone)
        else:
            next_run_at = compute_next_run_at(request.time_of_day, request.timezone, now=utc_now(), interval_days=request.interval_days)
        schedule = SuiteSchedule(
            name=request.name,
            model_id=request.model_id,
            profile=request.profile,
            enabled=request.enabled,
            title=request.title,
            time_of_day=request.time_of_day,
            timezone=request.timezone,
            interval_days=request.interval_days,
            run_once=request.run_once,
            run_date=request.run_date,
            request=request.to_run_request(),
            next_run_at=next_run_at,
        )
        return self.save(schedule)

    def save(self, schedule: SuiteSchedule) -> SuiteSchedule:
        schedule.updated_at = utc_now()
        write_json_file_atomic(self._path(schedule.schedule_id), schedule.model_dump(mode="json"))
        return schedule

    def get(self, schedule_id: str) -> SuiteSchedule | None:
        path = self._path(schedule_id)
        if not path.exists():
            return None
        return SuiteSchedule.model_validate(read_json_file(path, {}))

    def list(self, limit: int = 50) -> list[SuiteSchedule]:
        if not self.directory.exists():
            return []
        schedules: list[SuiteSchedule] = []
        for path in self.directory.glob("suite_schedule_*.json"):
            try:
                schedules.append(SuiteSchedule.model_validate(read_json_file(path, {})))
            except Exception:
                continue
        schedules.sort(key=lambda item: (item.next_run_at, item.schedule_id))
        return schedules[:limit]

    def delete(self, schedule_id: str) -> bool:
        path = self._path(schedule_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def due(self, now: datetime | None = None) -> list[SuiteSchedule]:
        now = now or utc_now()
        return [item for item in self.list(limit=1000) if item.enabled and item.next_run_at <= now]


def compute_next_run_at(time_of_day: str, timezone_name: str, *, now: datetime | None = None, interval_days: int = 1) -> datetime:
    now = now or utc_now()
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    local_now = now.astimezone(tz)
    hour_text, minute_text = time_of_day.split(":", 1)
    candidate = local_now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if candidate <= local_now:
        candidate = candidate + timedelta(days=interval_days)
    return candidate.astimezone(timezone.utc)


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timezone_or_utc(timezone_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def compute_one_shot_run_at(run_date: date, time_of_day: str, timezone_name: str) -> datetime:
    tz = _timezone_or_utc(timezone_name)
    hour_text, minute_text = time_of_day.split(":", 1)
    local_run_at = datetime.combine(run_date, time(hour=int(hour_text), minute=int(minute_text)), tzinfo=tz)
    return local_run_at.astimezone(timezone.utc)


def compute_following_run_at(schedule: SuiteSchedule, *, now: datetime | None = None) -> datetime:
    base = now or utc_now()
    next_run = schedule.next_run_at
    while next_run <= base:
        next_run = next_run + timedelta(days=schedule.interval_days)
    return next_run
