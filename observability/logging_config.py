from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from config import settings
from observability.context import get_request_id, get_run_id


class JsonFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    payload: dict[str, Any] = {
      "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      "level": record.levelname,
      "logger": record.name,
      "message": record.getMessage(),
    }
    req_id = get_request_id()
    run_id = get_run_id()
    if req_id:
      payload["request_id"] = req_id
    if run_id:
      payload["run_id"] = run_id
    if record.exc_info:
      payload["exception"] = self.formatException(record.exc_info)
    for key in ("agent", "duration_ms", "path", "status_code", "tool", "tokens_total"):
      if hasattr(record, key):
        payload[key] = getattr(record, key)
    return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
  level_name = (settings.LOG_LEVEL or "INFO").upper()
  level = getattr(logging, level_name, logging.INFO)
  root = logging.getLogger()
  root.handlers.clear()
  handler = logging.StreamHandler(sys.stdout)
  if settings.LOG_JSON:
    handler.setFormatter(JsonFormatter())
  else:
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
  root.addHandler(handler)
  root.setLevel(level)
  logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
