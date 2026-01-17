from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ..config import settings
from ..db.engine import get_session
from ..repos.run_registry import RunRegistry

log = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Shared context for pipeline execution."""

    strategy_path: Path
    from_date: str
    to_date: str
    symbols: list[str]
    dry_run: bool = False
    fail_fast: bool = True
    active_stages: list[str] = field(default_factory=list)

    # Optional override to align artifacts + run registry IDs
    requested_run_id: str | None = None

    # Optional human-friendly run slug override (does not affect run_id)
    requested_run_slug: str | None = None

    # For audit/replay
    invoked_command: str | None = None

    # Optional link to the dry-run plan artifacts (UI contract)
    plan_run_id: str | None = None
    plan_artifacts_dir: str | None = None

    # Runtime state
    pipeline_run_id: str | None = None
    artifacts_dir: Path | None = None
    run_slug: str | None = None
    display_name: str | None = None
    pipeline_started_at: str | None = None
    pipeline_ended_at: str | None = None
    pipeline_status: str | None = None
    exit_code: int | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    stage_meta: dict[str, Any] = field(default_factory=dict)
    duckdb_path: str = str(settings.quant_duckdb_path)
    sqlite_path: str = str(settings.quant_sqlite_path)


@dataclass
class StageResult:
    """Result of a single stage execution."""

    stage_name: str
    status: str  # "success" or "fail"
    duration_sec: float
    stage_exec_id: str | None = None
    error_text: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _is_uuid(s: str | None) -> bool:
    if not s:
        return False
    try:
        uuid.UUID(str(s))
        return True
    except Exception:
        return False


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _universe_hint(symbols: list[str], *, max_symbols: int = 3) -> tuple[str, str]:
    """Returns (display_hint, slug_hint)."""
    syms = [str(x).strip().upper() for x in (symbols or []) if str(x).strip()]
    syms = sorted(set(syms))
    if not syms:
        return "ALL", "all"
    if len(syms) <= max_symbols:
        disp = "-".join(syms)
        return disp, _slugify(disp)

    disp = "-".join(syms[:max_symbols]) + f"-n{len(syms)}"
    h = hashlib.sha1(",".join(syms).encode("utf-8")).hexdigest()[:8]
    slug = f"u{h}"
    return disp, slug


def _stages_short(stages: list[str]) -> tuple[str, str]:
    """Returns (display_short, slug_short)."""
    if not stages:
        return "all", "all"
    m = {
        "ingest": "ingest",
        "features": "feat",
        "labels": "lbl",
        "recommend": "rec",
        "backtest": "bt",
    }
    display = "-".join([m.get(s, s) for s in stages])
    slug = _slugify(display.replace("-", "-"))
    return display, slug


def _make_run_slug(
    *,
    strategy_id: str,
    date_from: str,
    date_to: str,
    stages_resolved: list[str],
    symbols_resolved: list[str],
    max_len: int = 120,
) -> tuple[str, str]:
    """Returns (run_slug, display_name) with deterministic, bounded naming."""
    strategy_part = _slugify(strategy_id)
    stages_disp, stages_part = _stages_short(stages_resolved)
    uni_disp, uni_part = _universe_hint(symbols_resolved)

    slug = f"{strategy_part}__{date_from}_{date_to}__{stages_part}__{uni_part}"
    display = f"{strategy_id} | {date_from}..{date_to} | {stages_disp} | {uni_disp}"

    if len(slug) <= max_len:
        return slug, display

    # If too long: shrink strategy_id and force universe to hash
    uni_disp2, uni_part2 = _universe_hint(symbols_resolved)
    if not uni_part2.startswith("u"):
        # force hash
        syms = [
            str(x).strip().upper() for x in (symbols_resolved or []) if str(x).strip()
        ]
        syms = sorted(set(syms))
        h = hashlib.sha1(",".join(syms).encode("utf-8")).hexdigest()[:8]
        uni_part2 = f"u{h}"

    # cap strategy part
    keep = max(
        12, max_len - (len(f"__{date_from}_{date_to}__{stages_part}__{uni_part2}") + 1)
    )
    strategy_part = (strategy_part[:keep]).rstrip("-")
    slug2 = f"{strategy_part}__{date_from}_{date_to}__{stages_part}__{uni_part2}"
    return slug2[:max_len], display


def _write_progress_json(artifacts_dir: Path | None, payload: dict[str, Any]) -> None:
    """Append machine-readable progress to pipeline.log without polluting stdout."""
    if artifacts_dir is None:
        return
    try:
        p = artifacts_dir / "pipeline.log"
        line = "PROGRESS_JSON: " + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        )
        p.write_text("", encoding="utf-8") if not p.exists() else None
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class PipelineRunner:
    """Orchestrates the sequential execution of stages."""

    STAGES = ["ingest", "features", "labels", "recommend", "backtest"]

    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx
        self.results: list[StageResult] = []
        self._file_handler: logging.Handler | None = None

    @contextlib.contextmanager
    def _suppress_service_loggers(self):
        """Temporarily suppress lower-level service logs for cleaner CLI output."""
        service_loggers = [
            "quant.data_curator",
            "quant.feature_store",
            "quant.strategy_lab",
            "quant.ml",
            "quant.portfolio_supervisor",
            "quant.backtest_engine",
        ]
        originals = {}
        target_level = logging.WARNING
        # If verbose, allow DEBUG/INFO
        if os.getenv("QUANT_VERBOSE", "0") == "1":
            yield
            return

        for name in service_loggers:
            l = logging.getLogger(name)
            originals[name] = l.level
            l.setLevel(target_level)
        try:
            yield
        finally:
            for name, level in originals.items():
                logging.getLogger(name).setLevel(level)

    def _attach_file_logger(self, log_path: Path) -> None:
        """Attach a FileHandler for this pipeline run (best-effort)."""

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setLevel(
                getattr(logging, settings.quant_log_level.upper(), logging.INFO)
            )
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

            root = logging.getLogger()
            root.addHandler(handler)
            self._file_handler = handler
        except Exception:
            # Logging should never break pipeline execution.
            self._file_handler = None

    def _detach_file_logger(self) -> None:
        handler = self._file_handler
        if handler is None:
            return
        try:
            logging.getLogger().removeHandler(handler)
            handler.close()
        finally:
            self._file_handler = None

    def _persist_run_json(self) -> None:
        if not self.ctx.artifacts_dir:
            return
        try:
            payload = {
                "run_id": self.ctx.pipeline_run_id,
                "run_slug": self.ctx.run_slug,
                "display_name": self.ctx.display_name,
                "kind": "pipeline",
                "invoked_command": self.ctx.invoked_command,
                "artifacts_dir": str(self.ctx.artifacts_dir) + "/",
                "plan_run_id": self.ctx.plan_run_id,
                "plan_artifacts_dir": self.ctx.plan_artifacts_dir,
                "status": self.ctx.pipeline_status,
                "started_at": self.ctx.pipeline_started_at,
                "ended_at": self.ctx.pipeline_ended_at,
                "exit_code": self.ctx.exit_code,
                "strategy_id": self.ctx.strategy_id,
                "strategy_version": self.ctx.strategy_version,
                "strategy_path": str(self.ctx.strategy_path),
                "date_from": self.ctx.from_date,
                "date_to": self.ctx.to_date,
                "symbols_resolved": self.ctx.symbols,
                "stages_resolved": self.ctx.active_stages or self.STAGES,
                "fail_fast": self.ctx.fail_fast,
                "dry_run": self.ctx.dry_run,
                "stage_results": [
                    {
                        "stage_name": r.stage_name,
                        "status": r.status,
                        "duration_sec": r.duration_sec,
                        "stage_exec_id": r.stage_exec_id,
                        "error_text": r.error_text,
                        "result_path": f"stages/{r.stage_name}/result.json",
                        "meta": r.meta,
                    }
                    for r in self.results
                ],
                "generated_at": datetime.now(UTC).isoformat(),
            }
            (self.ctx.artifacts_dir / "run.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            # Best-effort only
            pass

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for s in symbols:
            if s is None:
                continue
            sym = str(s).strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
        return out

    def _resolve_symbols_from_strategy(
        self, strategy_config: dict[str, Any]
    ) -> list[str]:
        universe = strategy_config.get("universe") or {}
        u_type = (universe.get("type") or "").strip().lower()
        if u_type == "symbols":
            symbols = universe.get("symbols") or []
            if not isinstance(symbols, list):
                raise ValueError("universe.symbols must be a list")
            return self._normalize_symbols([str(x) for x in symbols])
        raise ValueError(f"Unsupported universe.type: {universe.get('type')}")

    def build_plan(
        self,
        invoked_command: str,
        stages_requested: str | None,
        symbols_override_raw: list[str] | None,
        run_id_override: str | None = None,
    ) -> dict[str, Any]:
        """Build a structured execution plan without running stages."""
        plan_run_id = (
            run_id_override
            or f"plan_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        )
        artifacts_dir = settings.quant_runs_dir / plan_run_id

        validation_errors: list[str] = []
        validation_warnings: list[str] = []

        # Strategy parse
        strategy_id = None
        strategy_version = None
        strategy_config: dict[str, Any] | None = None
        try:
            from ..strategy_lab.loader import StrategyLoader

            strategy_config = StrategyLoader.load_yaml(self.ctx.strategy_path)
            strategy_id = strategy_config.get("strategy_id")
            strategy_version = strategy_config.get("version")
        except Exception as e:
            validation_errors.append(f"Strategy parse failed: {e}")

        # Stages resolve
        stages_resolved = (
            self.ctx.active_stages[:] if self.ctx.active_stages else self.STAGES[:]
        )

        # Symbols resolve
        symbols_override = None
        if symbols_override_raw:
            # raw list can contain comma-separated segments
            joined = ",".join([s for s in symbols_override_raw if s is not None])
            symbols_override = self._normalize_symbols(list(joined.split(",")))

        symbols_source = "strategy"
        symbols_resolved: list[str] = []
        if symbols_override is not None and len(symbols_override) > 0:
            symbols_source = "override"
            symbols_resolved = symbols_override
        elif strategy_config is not None:
            try:
                symbols_resolved = self._resolve_symbols_from_strategy(strategy_config)
            except Exception as e:
                validation_errors.append(f"Universe resolve failed: {e}")

        # Optional warnings: registry + OHLCV coverage (read-only queries)
        try:
            if symbols_resolved:
                sqlite_path = Path(self.ctx.sqlite_path)
                if not sqlite_path.exists():
                    validation_warnings.append(
                        f"Symbol registry check skipped: SQLite DB not found at {sqlite_path}"
                    )
                else:
                    with get_session() as session:
                        for sym in symbols_resolved:
                            from ..models.meta import Symbol

                            if not session.get(Symbol, sym):
                                validation_warnings.append(f"{sym} not registered")
        except Exception as e:
            validation_warnings.append(f"Symbol registry check skipped: {e}")

        try:
            if symbols_resolved:
                import duckdb

                duckdb_path = Path(self.ctx.duckdb_path)
                if not duckdb_path.exists():
                    validation_warnings.append(
                        f"OHLCV coverage check skipped: DuckDB not found at {duckdb_path}"
                    )
                else:

                    con = None
                    try:
                        try:
                            con = duckdb.connect(self.ctx.duckdb_path, read_only=True)
                        except Exception as e_ro:
                            # DuckDB can refuse a second connection if a different read_only setting exists.
                            # Retry in read-write mode but only run SELECTs.
                            validation_warnings.append(
                                f"OHLCV coverage check retrying without read_only: {e_ro}"
                            )
                            con = duckdb.connect(self.ctx.duckdb_path, read_only=False)

                        for sym in symbols_resolved:
                            row = con.execute(
                                "SELECT COUNT(*) FROM ohlcv WHERE symbol = ?",
                                [sym],
                            ).fetchone()
                            try:
                                n = (
                                    int(row[0])
                                    if row and len(row) > 0 and row[0] is not None
                                    else 0
                                )
                            except Exception:
                                n = 0
                            if not n:
                                validation_warnings.append(
                                    f"OHLCV coverage missing: {sym}"
                                )
                    finally:
                        if con is not None:
                            con.close()
        except Exception as e:
            validation_warnings.append(f"OHLCV coverage check skipped: {e}")

        ok = len(validation_errors) == 0

        plan: dict[str, Any] = {
            "run_id": plan_run_id,
            "invoked_command": invoked_command,
            "strategy_path": str(self.ctx.strategy_path),
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "date_from": self.ctx.from_date,
            "date_to": self.ctx.to_date,
            "stages_requested": stages_requested,
            "stages_resolved": stages_resolved,
            "symbols_override": symbols_override,
            "symbols_resolved": symbols_resolved,
            "symbols_source": symbols_source,
            "dry_run": True,
            "fail_fast": self.ctx.fail_fast,
            "validation": {
                "ok": ok,
                "errors": validation_errors,
                "warnings": validation_warnings,
            },
            "artifacts_dir": str(artifacts_dir) + "/",
        }

        log.info(
            f"[PLAN] symbols_resolved={symbols_resolved} (source={symbols_source})"
        )
        log.info(f"[PLAN] stages_resolved={stages_resolved}")
        return plan

    @staticmethod
    def print_and_persist_plan(plan: dict[str, Any]) -> None:
        """Print a single-line plan JSON and persist to artifacts/runs/<run_id>/plan.json."""
        import sys

        artifacts_dir = Path(
            plan.get("artifacts_dir", str(settings.quant_runs_dir))
            or str(settings.quant_runs_dir)
        )
        # artifacts_dir is a string with trailing '/', normalize safely
        if isinstance(artifacts_dir, Path):
            dir_path = artifacts_dir
        else:
            dir_path = Path(str(artifacts_dir).rstrip("/"))

        dir_path.mkdir(parents=True, exist_ok=True)

        plan_json = json.dumps(
            plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        # Use the real stdout to avoid rich/console soft-wrapping inserting newlines.
        sys.__stdout__.write(f"PLAN_JSON: {plan_json}\n")  # type: ignore
        sys.__stdout__.flush()  # type: ignore

        plan_path = dir_path / "plan.json"
        plan_path.write_text(plan_json + "\n", encoding="utf-8")

    def run(self) -> bool:
        """Run the pipeline. Returns True if all requested stages succeeded."""

        # Resolve symbols from strategy if none were provided
        if not self.ctx.symbols:
            try:
                from ..strategy_lab.loader import StrategyLoader

                cfg = StrategyLoader.load_yaml(self.ctx.strategy_path)
                self.ctx.symbols = self._resolve_symbols_from_strategy(cfg)
                log.info(f"Resolved symbols from strategy: {self.ctx.symbols}")
            except Exception as e:
                log.error(f"Failed to resolve symbols from strategy: {e}")
                return False

        # 1. Start Pipeline Run
        if not self.ctx.dry_run:
            self.ctx.pipeline_started_at = datetime.now(UTC).isoformat()
            config = {
                "strategy": str(self.ctx.strategy_path),
                "from": self.ctx.from_date,
                "to": self.ctx.to_date,
                "symbols": self.ctx.symbols,
                "stages": self.ctx.active_stages,
                "fail_fast": self.ctx.fail_fast,
                "invoked_command": self.ctx.invoked_command,
            }
            self.ctx.pipeline_run_id = RunRegistry.run_start(
                "pipeline", config, run_id=self.ctx.requested_run_id
            )
            log.info(f"Started pipeline run: {self.ctx.pipeline_run_id}")

            # Artifacts SSOT for this run
            self.ctx.artifacts_dir = settings.quant_runs_dir / str(
                self.ctx.pipeline_run_id
            )
            self.ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)
            (self.ctx.artifacts_dir / "stages").mkdir(parents=True, exist_ok=True)

            # Human-friendly naming (alias index) without changing run_id
            try:
                from ..strategy_lab.loader import StrategyLoader

                cfg = StrategyLoader.load_yaml(self.ctx.strategy_path)
                strategy_id = str(cfg.get("strategy_id") or "strategy")
                strategy_version = str(cfg.get("version") or "") or None
            except Exception:
                strategy_id = "strategy"
                strategy_version = None

            self.ctx.strategy_id = strategy_id
            self.ctx.strategy_version = strategy_version

            stages_for_slug = self.ctx.active_stages or self.STAGES
            if self.ctx.requested_run_slug:
                base_slug = _slugify(self.ctx.requested_run_slug)
                base_display = (
                    f"{strategy_id} | {self.ctx.from_date}..{self.ctx.to_date} | "
                    f"{','.join(stages_for_slug) if stages_for_slug else 'all'} | {','.join(self.ctx.symbols) if self.ctx.symbols else 'ALL'}"
                )
            else:
                base_slug, base_display = _make_run_slug(
                    strategy_id=strategy_id,
                    date_from=self.ctx.from_date,
                    date_to=self.ctx.to_date,
                    stages_resolved=stages_for_slug,
                    symbols_resolved=self.ctx.symbols,
                )

            # Collision handling: if slug exists for a different run, suffix with run_id prefix
            final_slug = base_slug
            try:
                index_dir = settings.quant_artifacts_dir / "index" / "runs"
                index_dir.mkdir(parents=True, exist_ok=True)
                idx_path = index_dir / f"{final_slug}.json"
                if idx_path.exists():
                    existing = json.loads(idx_path.read_text(encoding="utf-8"))
                    if existing.get("run_id") != self.ctx.pipeline_run_id:
                        suffix = "__" + str(self.ctx.pipeline_run_id)[:8]
                        max_len = 120
                        trimmed = final_slug[: max(0, max_len - len(suffix))]
                        final_slug = (trimmed.rstrip("_") + suffix)[:max_len]
            except Exception:
                pass

            self.ctx.run_slug = final_slug
            self.ctx.display_name = base_display

            # Alias index entry: artifacts/index/runs/<slug>.json
            try:
                if self.ctx.run_slug:
                    index_dir = settings.quant_artifacts_dir / "index" / "runs"
                    index_dir.mkdir(parents=True, exist_ok=True)
                    idx_path = index_dir / f"{self.ctx.run_slug}.json"
                    idx_payload = {
                        "run_id": self.ctx.pipeline_run_id,
                        "run_slug": self.ctx.run_slug,
                        "display_name": self.ctx.display_name,
                        "artifacts_dir": str(self.ctx.artifacts_dir) + "/",
                        "created_at": datetime.now(UTC).isoformat(),
                        "strategy_id": strategy_id,
                        "date_from": self.ctx.from_date,
                        "date_to": self.ctx.to_date,
                        "stages_resolved": stages_for_slug,
                    }
                    idx_path.write_text(
                        json.dumps(idx_payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass

            # Best-effort file log + run metadata snapshot
            self._attach_file_logger(self.ctx.artifacts_dir / "pipeline.log")
            with contextlib.suppress(Exception):
                (self.ctx.artifacts_dir / "config.json").write_text(
                    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

        success = True
        try:
            with self._suppress_service_loggers():
                for stage_name in self.STAGES:
                    # Filter stages if specific stages requested
                    if (
                        self.ctx.active_stages
                        and stage_name not in self.ctx.active_stages
                    ):
                        continue

                    if not self._run_stage_wrapper(stage_name):
                        success = False
                        if self.ctx.fail_fast:
                            log.error(f"Fail-fast triggered at stage: {stage_name}")
                            break
        except Exception as e:
            log.exception("Pipeline crashed")
            success = False
            if self.ctx.pipeline_run_id:
                RunRegistry.run_fail(self.ctx.pipeline_run_id, str(e))
            return False

        # 2. Finish Pipeline Run
        if not self.ctx.dry_run and self.ctx.pipeline_run_id:
            self.ctx.pipeline_ended_at = datetime.now(UTC).isoformat()
            self.ctx.exit_code = 0 if success else 1
            if success:
                self.ctx.pipeline_status = "success"
                RunRegistry.run_success(self.ctx.pipeline_run_id)
            else:
                self.ctx.pipeline_status = "fail"
                # If we're here, it means we handled the stage failure gracefully
                # but the overall pipeline is marked failed.
                # Find the first error
                failed_stages = [r for r in self.results if r.status == "fail"]
                err_msg = (
                    f"Failed stages: {', '.join([r.stage_name for r in failed_stages])}"
                )
                if failed_stages and failed_stages[0].error_text:
                    err_msg += f" | Error: {failed_stages[0].error_text}"
                RunRegistry.run_fail(self.ctx.pipeline_run_id, err_msg)

        # Always persist summary artifacts best-effort
        if not self.ctx.dry_run:
            self._persist_run_json()
            self._detach_file_logger()

        return success

    def _run_stage_wrapper(self, stage_name: str) -> bool:
        """Wraps stage execution with timing and logging."""
        from rich.console import Console

        console = Console(stderr=True)
        console.rule(f"[bold white]{stage_name.upper()}[/bold white]")

        log.info(f"[{stage_name.upper()}] Starting...")
        start_ts = datetime.now(UTC)

        stage_dir: Path | None = None
        if self.ctx.artifacts_dir is not None:
            try:
                stage_dir = self.ctx.artifacts_dir / "stages" / stage_name
                stage_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                stage_dir = None

        if self.ctx.dry_run:
            # Strict dry-run: no stage execution
            print(f"[PLAN] Would execute stage: {stage_name}")
            return True

        result = StageResult(stage_name=stage_name, status="running", duration_sec=0.0)

        # Reset stage meta; adapters may populate it.
        self.ctx.stage_meta = {}

        try:
            # Dispatch to adapter
            adapter = self._get_adapter(stage_name)

            # Execute Adapter
            # The adapter should return a run_id or we manage it here?
            # The requirement says: "pipeline sub-runs"
            # Adapters should use RunRegistry internally OR we pass parent_run_id?
            # The current services use RunRegistry internally.
            # We can capture the run_id if the adapter returns it, or if we modify services.
            # Requirement: "Simply use config_json.parent_run_id"
            # So we should pass parent_run_id to the adapter config.

            stage_exec_id = adapter(self.ctx)
            result.stage_exec_id = stage_exec_id
            result.status = "success"
            result.meta = self.ctx.stage_meta or {}

        except Exception as e:
            log.exception(f"[{stage_name.upper()}] Failed")
            result.status = "fail"
            result.error_text = str(e)
            return False
        finally:
            end_ts = datetime.now(UTC)
            result.duration_sec = (end_ts - start_ts).total_seconds()
            self.results.append(result)

            if stage_dir is not None:
                with contextlib.suppress(Exception):
                    (stage_dir / "result.json").write_text(
                        json.dumps(
                            {
                                "ok": result.status == "success",
                                "stage_name": result.stage_name,
                                "status": result.status,
                                "started_at": start_ts.isoformat(),
                                "ended_at": end_ts.isoformat(),
                                "elapsed_sec": result.duration_sec,
                                "stage_exec_id": result.stage_exec_id,
                                "meta": result.meta,
                                "errors": (
                                    [result.error_text] if result.error_text else []
                                ),
                                "warnings": [],
                                "generated_at": datetime.now(UTC).isoformat(),
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )

            status_icon = "✅" if result.status == "success" else "❌"
            log.info(
                f"[{stage_name.upper()}] {status_icon} Finished in {result.duration_sec:.2f}s"
            )
            if result.status == "fail":
                log.error(f"[{stage_name.upper()}] Error: {result.error_text}")

        return result.status == "success"

    def _get_adapter(self, stage_name: str) -> Callable[[PipelineContext], str]:
        """Returns the callable adapter for the stage."""
        adapters = {
            "ingest": run_ingest,
            "features": run_features,
            "labels": run_labels,
            "recommend": run_recommend,
            "backtest": run_backtest,
        }
        return adapters[stage_name]


# --- Stage Adapters ---


def run_ingest(ctx: PipelineContext) -> str:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
    )

    from ..data_curator.ingest import DataIngester
    from ..data_curator.provider import AlphaVantageProvider

    # Configuration with parent run context
    config = {
        "symbols": ctx.symbols,
        "force_full": False,
        "parent_run_id": ctx.pipeline_run_id,
    }
    run_id = RunRegistry.run_start("ingest", config)

    # Suppress service-level spam during pipeline run
    ingest_logger = logging.getLogger("quant.data_curator.ingest")
    original_level = ingest_logger.level
    ingest_logger.setLevel(logging.WARNING)

    try:
        api_key = settings.alpha_vantage_api_key
        if api_key is None:
            raise ValueError(
                "Alpha Vantage API key is not configured: set settings.alpha_vantage_api_key"
            )
        provider = AlphaVantageProvider(api_key=api_key)
        ingester = DataIngester(provider)

        console = Console(stderr=True)
        with Progress(
            TextColumn("[bold cyan]INGEST[/bold cyan]"),
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Ingesting symbols", total=len(ctx.symbols))
            for i, sym in enumerate(ctx.symbols, start=1):
                progress.update(task, description=f"Ingesting {sym}")
                ingester.ingest_symbol(sym, force_full=False)
                _write_progress_json(
                    ctx.artifacts_dir,
                    {
                        "run_id": ctx.pipeline_run_id,
                        "stage": "ingest",
                        "stage_exec_id": run_id,
                        "event": "symbol_done",
                        "current": i,
                        "total": len(ctx.symbols),
                        "symbol": sym,
                    },
                )
                progress.advance(task)

        ctx.stage_meta = {
            "n_symbols": len(ctx.symbols),
            "symbols": ctx.symbols,
        }

        RunRegistry.run_success(run_id)
        return run_id
    except Exception as e:
        RunRegistry.run_fail(run_id, str(e))
        raise e
    finally:
        ingest_logger.setLevel(original_level)


def run_features(ctx: PipelineContext) -> str:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
    )

    from ..feature_store.features import FeatureCalculator

    config = {
        "symbols": ctx.symbols,
        "version": "v1",  # Defaulting to v1 as per current baseline
        "parent_run_id": ctx.pipeline_run_id,
    }
    run_id = RunRegistry.run_start("features", config)

    # Suppress service-level spam
    feat_logger = logging.getLogger("quant.feature_store.features")
    original_level = feat_logger.level
    feat_logger.setLevel(logging.WARNING)

    try:
        calc = FeatureCalculator()

        console = Console(stderr=True)
        with Progress(
            TextColumn("[bold cyan]FEATURES[/bold cyan]"),
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Calculating features", total=len(ctx.symbols))
            for i, sym in enumerate(ctx.symbols, start=1):
                progress.update(task, description=f"Processing {sym}")
                calc.run_for_symbol(sym, version="v1")
                _write_progress_json(
                    ctx.artifacts_dir,
                    {
                        "run_id": ctx.pipeline_run_id,
                        "stage": "features",
                        "stage_exec_id": run_id,
                        "event": "symbol_done",
                        "current": i,
                        "total": len(ctx.symbols),
                        "symbol": sym,
                    },
                )
                progress.advance(task)

        ctx.stage_meta = {
            "n_symbols": len(ctx.symbols),
            "symbols": ctx.symbols,
            "feature_version": "v1",
        }

        RunRegistry.run_success(run_id)
        return run_id
    except Exception as e:
        RunRegistry.run_fail(run_id, str(e))
        raise e
    finally:
        feat_logger.setLevel(original_level)


def run_labels(ctx: PipelineContext) -> str:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
    )

    from ..feature_store.labels import LabelCalculator

    config = {
        "symbols": ctx.symbols,
        "version": "v1",
        "horizon": 60,  # Defaulting to 60 as per baseline
        "parent_run_id": ctx.pipeline_run_id,
    }
    run_id = RunRegistry.run_start("labels", config)

    # Suppress service-level spam
    lbl_logger = logging.getLogger("quant.feature_store.labels")
    original_level = lbl_logger.level
    lbl_logger.setLevel(logging.WARNING)

    try:
        calc = LabelCalculator()

        console = Console(stderr=True)
        with Progress(
            TextColumn("[bold cyan]LABELS[/bold cyan]"),
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Calculating labels", total=len(ctx.symbols))
            for i, sym in enumerate(ctx.symbols, start=1):
                progress.update(task, description=f"Processing {sym}")
                calc.run_for_symbol(sym, version="v1", horizon=60)
                _write_progress_json(
                    ctx.artifacts_dir,
                    {
                        "run_id": ctx.pipeline_run_id,
                        "stage": "labels",
                        "stage_exec_id": run_id,
                        "event": "symbol_done",
                        "current": i,
                        "total": len(ctx.symbols),
                        "symbol": sym,
                    },
                )
                progress.advance(task)

        ctx.stage_meta = {
            "n_symbols": len(ctx.symbols),
            "symbols": ctx.symbols,
            "label_version": "v1",
            "horizon": 60,
        }

        RunRegistry.run_success(run_id)
        return run_id
    except Exception as e:
        RunRegistry.run_fail(run_id, str(e))
        raise e
    finally:
        lbl_logger.setLevel(original_level)


def run_recommend(ctx: PipelineContext) -> str:
    import os
    import sys

    import pandas as pd
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    from ..portfolio_supervisor.engine import PortfolioSupervisor
    from ..repos.targets import save_targets
    from ..strategy_lab.loader import StrategyLoader
    from ..strategy_lab.recommender import Recommender

    # We are using 'to_date' as 'asof' date for recommendation?
    # Usually recommendation is done for a specific date (today or end of period).
    # Since we are running a pipeline which might be for backtest,
    # if it's backtesting, recommend stage might act differently (recommend for every day?)
    # OR, usually "Recommend" stage in this simple pipeline means "Generate target for the *end* date"
    # so we can inspect what to buy *now*.
    # BUT, if we run backtest afterwards, backtest engine usually generates signals internally or consumes targets?
    # V2 Spec says Backtest Engine runs on *Strategy YAML*.
    # V2 Backtest Engine (P5) seems to encompass signal generation internally for the backtest period.
    # The 'Recommend' stage (P4) is for generating *actionable targets* for a specific date (Production) or single date simulation.

    # If the user asks for backtest from 2025-01-01 to 2025-12-31,
    # The 'Recommend' stage usually means "recommendation at 2025-12-31".

    asof = ctx.to_date

    config_run = {
        "strategy": str(ctx.strategy_path),
        "asof": asof,
        "parent_run_id": ctx.pipeline_run_id,
    }
    run_id = RunRegistry.run_start("recommend", config_run)

    try:
        strategy_config = StrategyLoader.load_yaml(ctx.strategy_path)

        # Determine recommender identity for metadata (baseline vs plugin)
        rec_cfg = strategy_config.get("recommender") or {}
        rec_type = (rec_cfg.get("type") or "").strip().lower()
        if not rec_type:
            rec_type = "factor_rank"

        recommender = Recommender()
        df_raw = recommender.generate_targets_for_window(
            config=strategy_config,
            symbols=ctx.symbols,
            from_date=ctx.from_date,
            to_date=ctx.to_date,
            artifacts_dir=ctx.artifacts_dir,
        )

        if df_raw.empty:
            feature_version = (strategy_config.get("signal") or {}).get(
                "inputs", {}
            ).get("feature_version") or "v1"
            algo = None
            target = None
            featureset = None
            if rec_type == "ml_gbdt":
                model_cfg = rec_cfg.get("model") or {}
                algo = (model_cfg.get("algo") or "").strip().lower() or None
                target = (model_cfg.get("target") or "").strip() or None
                featureset = (model_cfg.get("featureset") or "").strip() or None
            ctx.stage_meta = {
                "n_dates": 0,
                "n_rows": 0,
                "date_min": None,
                "date_max": None,
                "top_k": None,
                "recommender": {
                    "type": rec_type,
                    "algo": algo,
                    "target": target,
                    "featureset": featureset,
                    "feature_version": feature_version,
                },
                "artifacts": {},
            }

        if not df_raw.empty:
            supervisor = PortfolioSupervisor(strategy_config)

            # Supervisor는 날짜별(리밸런싱 단위)로 감사해야 한다.
            if "asof" in df_raw.columns and df_raw["asof"].nunique() > 1:
                tmp = df_raw.copy()
                tmp["asof"] = pd.to_datetime(tmp["asof"]).dt.strftime("%Y-%m-%d")
                groups = list(tmp.groupby("asof"))

                use_progress = bool(
                    getattr(sys.stderr, "isatty", lambda: False)()
                    or getattr(sys.stdout, "isatty", lambda: False)()
                )

                total_dates = len(groups)
                total_rows = 0
                first_date = groups[0][0] if groups else None
                last_date = groups[-1][0] if groups else None

                if use_progress and total_dates:
                    console = Console(stderr=True)
                    progress = Progress(
                        TextColumn("[bold cyan]RECOMMEND[/bold cyan]"),
                        TextColumn("{task.description}"),
                        BarColumn(),
                        TextColumn("{task.completed}/{task.total}"),
                        TimeElapsedColumn(),
                        TimeRemainingColumn(),
                        console=console,
                        transient=True,
                    )
                    with progress:
                        task_id = progress.add_task(
                            "Saving targets (per date)", total=total_dates
                        )
                        for i, (asof_str, g) in enumerate(groups, start=1):
                            df_audited = supervisor.audit(g)
                            total_rows += len(df_audited)
                            save_targets(df_audited)
                            _write_progress_json(
                                ctx.artifacts_dir,
                                {
                                    "run_id": ctx.pipeline_run_id,
                                    "stage": "recommend",
                                    "stage_exec_id": run_id,
                                    "event": "targets_write",
                                    "current": i,
                                    "total": total_dates,
                                    "asof": asof_str,
                                    "rows": int(len(df_audited)),
                                },
                            )
                            progress.advance(task_id)
                else:
                    for i, (asof_str, g) in enumerate(groups, start=1):
                        df_audited = supervisor.audit(g)
                        total_rows += len(df_audited)
                        save_targets(df_audited)
                        _write_progress_json(
                            ctx.artifacts_dir,
                            {
                                "run_id": ctx.pipeline_run_id,
                                "stage": "recommend",
                                "stage_exec_id": run_id,
                                "event": "targets_write",
                                "current": i,
                                "total": total_dates,
                                "asof": asof_str,
                                "rows": int(len(df_audited)),
                            },
                        )

                # Single, aggregated INFO line (instead of per-date INFO spam)
                if total_dates:
                    log.info(
                        "[RECOMMEND] Saved targets: "
                        f"{total_dates} dates, {total_rows} rows"
                        + (
                            f" ({first_date}..{last_date})"
                            if first_date and last_date
                            else ""
                        )
                    )

                # Stage metadata for UI / run.json
                top_k = (
                    int(cast(int, rec_cfg.get("top_k")))
                    if rec_type == "ml_gbdt" and rec_cfg.get("top_k") is not None
                    else int((strategy_config.get("portfolio") or {}).get("top_k", 0))
                )

                feature_version = (strategy_config.get("signal") or {}).get(
                    "inputs", {}
                ).get("feature_version") or "v1"
                algo = None
                target = None
                featureset = None
                if rec_type == "ml_gbdt":
                    model_cfg = rec_cfg.get("model") or {}
                    algo = (model_cfg.get("algo") or "").strip().lower() or None
                    target = (model_cfg.get("target") or "").strip() or None
                    featureset = (model_cfg.get("featureset") or "").strip() or None

                artifacts: dict[str, Any] = {}
                lgbm_log_enabled = os.getenv("QUANT_LGBM_LOG", "0") == "1"
                if ctx.artifacts_dir is not None and rec_type == "ml_gbdt":
                    # Relative pointers (UI-friendly)
                    artifacts["model_path"] = (
                        f"models/model.{algo or 'lightgbm'}.joblib"
                    )
                    artifacts["metrics_path"] = "reports/ml_metrics.json"
                    artifacts["summary_path"] = "reports/ml_summary.md"
                    artifacts["predictions_path"] = "outputs/predictions.csv"
                    if lgbm_log_enabled:
                        artifacts["lightgbm_log_path"] = "stages/recommend/lightgbm.log"

                ctx.stage_meta = {
                    "n_dates": int(total_dates),
                    "n_rows": int(total_rows),
                    "date_min": first_date,
                    "date_max": last_date,
                    "top_k": int(top_k) if top_k else None,
                    "recommender": {
                        "type": rec_type,
                        "algo": algo,
                        "target": target,
                        "featureset": featureset,
                        "feature_version": feature_version,
                    },
                    "artifacts": artifacts,
                }
            else:
                df_final = supervisor.audit(df_raw)
                save_targets(df_final)

                # Single-date metadata
                asof_single = None
                if "asof" in df_final.columns and not df_final.empty:
                    asof_single = str(df_final.iloc[0]["asof"])
                top_k = int((strategy_config.get("portfolio") or {}).get("top_k", 0))
                feature_version = (strategy_config.get("signal") or {}).get(
                    "inputs", {}
                ).get("feature_version") or "v1"
                algo = None
                target = None
                featureset = None
                if rec_type == "ml_gbdt":
                    model_cfg = rec_cfg.get("model") or {}
                    algo = (model_cfg.get("algo") or "").strip().lower() or None
                    target = (model_cfg.get("target") or "").strip() or None
                    featureset = (model_cfg.get("featureset") or "").strip() or None
                ctx.stage_meta = {
                    "n_dates": 1 if asof_single else None,
                    "n_rows": int(len(df_final)),
                    "date_min": asof_single,
                    "date_max": asof_single,
                    "top_k": int(top_k) if top_k else None,
                    "recommender": {
                        "type": rec_type,
                        "algo": algo,
                        "target": target,
                        "featureset": featureset,
                        "feature_version": feature_version,
                    },
                    "artifacts": {},
                }

        RunRegistry.run_success(run_id)
        return run_id
    except Exception as e:
        RunRegistry.run_fail(run_id, str(e))
        raise e


def run_backtest(ctx: PipelineContext) -> str:
    from ..backtest_engine.engine import BacktestEngine
    from ..strategy_lab.loader import StrategyLoader

    config_run = {
        "strategy": str(ctx.strategy_path),
        "from": ctx.from_date,
        "to": ctx.to_date,
        "parent_run_id": ctx.pipeline_run_id,
    }
    run_id = RunRegistry.run_start("backtest", config_run)

    try:
        strategy_config = StrategyLoader.load_yaml(ctx.strategy_path)
        engine = BacktestEngine()
        # Backtest engine expects 'from' and 'to'
        metrics = engine.run(strategy_config, ctx.from_date, ctx.to_date)

        # Best-effort stage metadata (do not depend on schema)
        try:
            ctx.stage_meta = {
                "date_from": ctx.from_date,
                "date_to": ctx.to_date,
                "has_metrics": bool(metrics),
                "metrics_keys": (
                    sorted(metrics.keys()) if isinstance(metrics, dict) else []
                ),
            }
        except Exception:
            ctx.stage_meta = {}

        # Determine success based on metrics presence
        if metrics:
            RunRegistry.run_success(run_id)
        else:
            # Maybe warning? but techincally success call.
            RunRegistry.run_success(run_id)

        return run_id
    except Exception as e:
        RunRegistry.run_fail(run_id, str(e))
        raise e
