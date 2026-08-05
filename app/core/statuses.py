from typing import Literal

MetricStatus = Literal["completed", "error", "skipped"]
TaskStatus = Literal["completed", "error"]
Protocol = Literal["chat_completions", "responses"]

STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"
SUPPORTED_PROTOCOLS = {"chat_completions", "responses"}
