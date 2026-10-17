"""SSE event protocol used by interpretation operations."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterable
from typing import Any


EVENT_TYPES = {"started", "evidence_ready", "token", "tool_status", "validated", "completed", "error", "cancelled"}
_POSIX_LOCAL_PATH = re.compile(r"(?<![\w:])/(?:home|tmp|workspace|data|var|mnt|opt)/[^\s<>\"']+")
_WINDOWS_LOCAL_PATH = re.compile(r"(?<!\w)[A-Za-z]:\\[^\s<>\"']+")


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        value = _POSIX_LOCAL_PATH.sub("<local-path-redacted>", value)
        return _WINDOWS_LOCAL_PATH.sub("<local-path-redacted>", value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def encode_event(event: str, data: dict[str, Any], *, event_id: str | None = None) -> str:
    if event not in EVENT_TYPES:
        raise ValueError(f"Unsupported SSE event: {event}")
    payload = json.dumps(_redact(data), ensure_ascii=False, separators=(",", ":")).replace("\r", "\\r").replace("\n", "\\n")
    lines = [f"event: {event}"]
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


async def operation_events(events: Iterable[tuple[str, dict[str, Any]]], *, cancelled: Any = None) -> AsyncIterator[str]:
    """Yield a finite, ordered event stream and always emit a terminal event."""
    terminal = False
    try:
        for event, data in events:
            if cancelled is not None and getattr(cancelled, "is_set", lambda: False)():
                yield encode_event("cancelled", {"reason": "client_cancelled"})
                terminal = True
                return
            yield encode_event(event, data)
            terminal = event in {"completed", "error", "cancelled"}
    except Exception as exc:
        yield encode_event("error", {"code": "OPERATION_FAILED", "message": str(exc)})
        terminal = True
    finally:
        if not terminal:
            yield encode_event("completed", {"status": "completed"})
