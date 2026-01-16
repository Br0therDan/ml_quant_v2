from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.quant.config import settings


@dataclass(frozen=True)
class RunLookupResult:
    run_id: str
    run_slug: Optional[str] = None
    display_name: Optional[str] = None
    artifacts_dir: Optional[str] = None


def runs_dir() -> Path:
    return settings.quant_runs_dir


def index_runs_dir() -> Path:
    return settings.quant_artifacts_dir / "index" / "runs"


def get_run_dir(run_id: str) -> Path:
    return runs_dir() / str(run_id)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_run_json(run_id: str) -> Optional[dict[str, Any]]:
    p = get_run_dir(run_id) / "run.json"
    if not p.exists():
        return None
    try:
        return _read_json(p)
    except Exception:
        return None


def read_stage_result(run_id: str, stage: str) -> Optional[dict[str, Any]]:
    p = get_run_dir(run_id) / "stages" / stage / "result.json"
    if not p.exists():
        return None
    try:
        return _read_json(p)
    except Exception:
        return None


def list_stage_results(run_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    stages_dir = get_run_dir(run_id) / "stages"
    if not stages_dir.exists():
        return out
    for stage_dir in sorted([p for p in stages_dir.iterdir() if p.is_dir()]):
        p = stage_dir / "result.json"
        if not p.exists():
            continue
        try:
            out[stage_dir.name] = _read_json(p)
        except Exception:
            continue
    return out


def read_pipeline_log(run_id: str) -> Optional[str]:
    p = get_run_dir(run_id) / "pipeline.log"
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def tail_pipeline_log(run_id: str, *, lines: int = 200) -> str:
    text = read_pipeline_log(run_id)
    if not text:
        return "No pipeline.log found."
    all_lines = text.splitlines()
    return "\n".join(all_lines[-lines:])


def parse_stage_elapsed_sec(result: dict[str, Any]) -> Optional[float]:
    if not result:
        return None
    if isinstance(result.get("elapsed_sec"), (int, float)):
        return float(result["elapsed_sec"])
    if isinstance(result.get("duration_sec"), (int, float)):
        return float(result["duration_sec"])
    return None


def parse_stage_errors(result: dict[str, Any]) -> list[str]:
    if not result:
        return []
    errors = result.get("errors")
    if isinstance(errors, list):
        return [str(x) for x in errors if x]
    # legacy
    if result.get("error_text"):
        return [str(result.get("error_text"))]
    return []


def list_alias_index() -> list[dict[str, Any]]:
    idx_dir = index_runs_dir()
    if not idx_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in idx_dir.glob("*.json"):
        try:
            payload = _read_json(p)
            payload.setdefault("run_slug", p.stem)
            out.append(payload)
        except Exception:
            continue

    def _sort_key(x: dict[str, Any]) -> str:
        return str(x.get("created_at") or "")

    out.sort(key=_sort_key, reverse=True)
    return out


def list_runs_from_run_json() -> list[dict[str, Any]]:
    """Fallback SSOT: scan artifacts/runs/*/run.json (excludes plan_* dirs)."""
    out: list[dict[str, Any]] = []
    base = runs_dir()
    if not base.exists():
        return out
    for d in sorted([p for p in base.iterdir() if p.is_dir()]):
        if d.name.startswith("plan_"):
            continue
        p = d / "run.json"
        if not p.exists():
            continue
        try:
            payload = _read_json(p)
            out.append(payload)
        except Exception:
            continue

    def _sort_key(x: dict[str, Any]) -> str:
        return str(x.get("started_at") or x.get("generated_at") or "")

    out.sort(key=_sort_key, reverse=True)
    return out


def resolve_run_id_from_slug(run_slug: str) -> Optional[RunLookupResult]:
    slug = (run_slug or "").strip()
    if not slug:
        return None
    p = index_runs_dir() / f"{slug}.json"
    if not p.exists():
        return None
    try:
        payload = _read_json(p)
        rid = str(payload.get("run_id") or "").strip()
        if not rid:
            return None
        return RunLookupResult(
            run_id=rid,
            run_slug=str(payload.get("run_slug") or slug) or None,
            display_name=str(payload.get("display_name") or "") or None,
            artifacts_dir=str(payload.get("artifacts_dir") or "") or None,
        )
    except Exception:
        return None


def write_initial_run_json(
    *,
    run_id: str,
    artifacts_dir: Path,
    invoked_command: str,
    kind: str = "pipeline",
    plan_run_id: Optional[str] = None,
    plan_artifacts_dir: Optional[str] = None,
) -> Path:
    """Create initial run.json for a newly started run (status=running).

    This enables artifacts-first reconstruction while the subprocess is running.
    """

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "kind": str(kind),
        "status": "running",
        "started_at": now_utc,
        "invoked_command": str(invoked_command),
        "artifacts_dir": str(artifacts_dir) + "/",
        "plan_run_id": str(plan_run_id) if plan_run_id else None,
        "plan_artifacts_dir": str(plan_artifacts_dir) if plan_artifacts_dir else None,
        "generated_at": now_utc,
    }

    # Drop None fields for cleanliness
    payload = {k: v for k, v in payload.items() if v is not None}

    p = artifacts_dir / "run.json"
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return p
