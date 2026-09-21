import time
from datetime import datetime


def now_monotonic() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def timestamp_elapsed_ms(start: datetime, end: datetime | None) -> float | None:
    if end is None:
        return None
    return round(max(0.0, (end - start).total_seconds() * 1000), 3)
