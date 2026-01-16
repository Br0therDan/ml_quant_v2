from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


PROGRESS_PREFIX = "PROGRESS_JSON:"


@dataclass(frozen=True)
class ProgressEvent:
    stage: Optional[str]
    event: Optional[str]
    current: Optional[int]
    total: Optional[int]
    payload: dict[str, Any]


def parse_progress_events(log_text: str) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    if not log_text:
        return events

    for line in log_text.splitlines():
        if not line.startswith(PROGRESS_PREFIX):
            continue
        raw = line.split(PROGRESS_PREFIX, 1)[1].strip()
        try:
            payload = json.loads(raw)
        except Exception:
            continue

        def _to_int(v: Any) -> Optional[int]:
            try:
                if v is None:
                    return None
                return int(v)
            except Exception:
                return None

        events.append(
            ProgressEvent(
                stage=(
                    str(payload.get("stage"))
                    if payload.get("stage") is not None
                    else None
                ),
                event=(
                    str(payload.get("event"))
                    if payload.get("event") is not None
                    else None
                ),
                current=_to_int(payload.get("current")),
                total=_to_int(payload.get("total")),
                payload=payload,
            )
        )

    return events


def latest_progress_by_stage(events: list[ProgressEvent]) -> dict[str, ProgressEvent]:
    out: dict[str, ProgressEvent] = {}
    for ev in events:
        if not ev.stage:
            continue
        out[ev.stage] = ev
    return out
