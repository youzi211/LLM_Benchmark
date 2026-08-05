from datetime import datetime, timezone
from uuid import uuid4


def new_task_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"task_{stamp}_{uuid4().hex[:8]}"
