import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from app.ui.data_access import load_pipeline_summary
from app.ui.execution import ExecutionManager
from app.ui.progress_events import latest_progress_by_stage, parse_progress_events
from app.ui.run_artifacts import (
    get_run_dir,
    list_alias_index,
    list_runs_from_run_json,
    list_stage_results,
    parse_stage_elapsed_sec,
    parse_stage_errors,
    read_pipeline_log,
    read_run_json,
    resolve_run_id_from_slug,
    tail_pipeline_log,
    write_initial_run_json,
)
from quant.config import settings

st.set_page_config(
    page_title="Run Center | Quant Lab V2",
    page_icon="▶️",
    layout="wide",
)

st.title("▶️ Run Center")
st.caption("이 페이지는 파이프라인(Batch/End-to-End) 오케스트레이션을 담당합니다.")

# --- Layout ---
col_controls, col_results = st.columns([0.3, 0.7], gap="small")


@st.dialog("Live Run Log", width="medium")
def _live_log_dialog(run_id: str) -> None:
    st.caption("실행 중인 로그를 artifacts(pipeline.log)에서 tail로 표시합니다.")

    @st.fragment(run_every="2s")
    def _render() -> None:
        st.code(tail_pipeline_log(run_id, lines=200), language="text")

    _render()

    if st.button("Close", width="stretch"):
        st.session_state["show_live_log_dialog"] = False
        st.session_state["live_log_run_id"] = None
        st.rerun()


def _build_pipeline_cmd(
    *,
    strategy_path: Path | None,
    start_date: str,
    end_date: str,
    run_id: str,
    symbols_input: str,
    stages: list[str],
    dry_run: bool,
    fail_fast: bool,
) -> list[str]:
    cmd = [
        "uv",
        "run",
        "quant",
        "pipeline",
        "run",
        "--from",
        start_date,
        "--to",
        end_date,
        "--run-id",
        run_id,
    ]

    # only include strategy flag when a strategy path is provided
    if strategy_path:
        cmd[5:5] = ["--strategy", str(strategy_path)]

    if symbols_input.strip():
        cmd.extend(["--symbols", symbols_input.strip()])

    if stages:
        cmd.extend(["--stages", ",".join(stages)])

    if dry_run:
        cmd.append("--dry-run")

    if not fail_fast:
        cmd.append("--no-fail-fast")

    return cmd


def _extract_plan_json(stdout_text: str) -> dict:
    for line in stdout_text.splitlines():
        if line.startswith("PLAN_JSON:"):
            raw = line.split("PLAN_JSON:", 1)[1].strip()
            return json.loads(raw)
    raise ValueError("PLAN_JSON line not found in stdout")


def _read_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --- Controls Panel ---
with col_controls:
    with st.container(border=True, height="stretch", gap="small"):
        st.subheader("Orchestration")

        # Strategy
        strategies_dir = settings.quant_data_dir.parent / "strategies"
        strategy_files = (
            list(strategies_dir.glob("*.yaml")) if strategies_dir.exists() else []
        )
        strategy_names = [f.name for f in strategy_files]

        selected_strategy = st.selectbox("Strategy config", strategy_names)

        # Date Range
        today = datetime.today()
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("From", today - timedelta(days=365))
        with c2:
            end_date = st.date_input("To", today)

        # Symbols (Optional)
        symbols_input = st.text_input(
            "Symbols (comma-separated, optional)", placeholder="e.g. AAPL, TSLA"
        )

        # Stages
        all_stages = ["ingest", "features", "labels", "recommend", "backtest"]
        selected_stages = st.multiselect("Stages (empty = all)", all_stages, default=[])

        # Options
        col_a, col_b = st.columns(2)
        with col_a:
            fail_fast = st.checkbox("Fail Fast", value=True)
        with col_b:
            dry_run = st.checkbox("Dry Run (Plan only)", value=False)

        if "plan" not in st.session_state:
            st.session_state["plan"] = None
        if "plan_run_id" not in st.session_state:
            st.session_state["plan_run_id"] = None
        if "active_run_id" not in st.session_state:
            st.session_state["active_run_id"] = None
        if "show_live_log_dialog" not in st.session_state:
            st.session_state["show_live_log_dialog"] = False
        if "live_log_run_id" not in st.session_state:
            st.session_state["live_log_run_id"] = None

        strategy_path = (
            strategies_dir / selected_strategy if selected_strategy else None
        )


        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Plan", width="stretch"):
                if not strategy_path:
                    st.error("Please select a strategy.")
                else:
                    plan_run_id = f"plan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_ui_{uuid.uuid4().hex[:6]}"
                    cmd = _build_pipeline_cmd(
                        strategy_path=strategy_path,
                        start_date=str(start_date),
                        end_date=str(end_date),
                        run_id=plan_run_id,
                        symbols_input=symbols_input,
                        stages=selected_stages,
                        dry_run=True,
                        fail_fast=fail_fast,
                    )

                    plan_dir = settings.quant_runs_dir / plan_run_id
                    plan_path = plan_dir / "plan.json"

                    proc = subprocess.run(
                        cmd,
                        cwd=str(settings.quant_data_dir.parent),
                        env={
                            **os.environ,
                            "PYTHONPATH": str(settings.quant_data_dir.parent),
                        },
                        capture_output=True,
                        text=True,
                    )

                    try:
                        # Artifacts SSOT: read plan.json from artifacts instead of stdout parsing.
                        if not plan_path.exists():
                            raise ValueError(f"plan.json not found: {plan_path}")
                        plan = _read_json_file(plan_path)
                        st.session_state["plan"] = plan
                        st.session_state["plan_run_id"] = plan.get("run_id")
                        st.session_state["active_run_id"] = None
                        st.session_state["active_run_artifacts_dir"] = None
                    except Exception as e:
                        st.session_state["plan"] = None
                        st.error(f"Plan parse failed: {e}")
                        st.code(
                            (proc.stdout or "") + "\n" + (proc.stderr or ""),
                            language="text",
                        )
                        st.stop()

        with col_b:
            plan = st.session_state.get("plan")
            plan_ok = bool(plan and plan.get("validation", {}).get("ok"))
            if st.button(
                "Execute",
                type="primary",
                width="stretch",
                disabled=not plan_ok,
            ):
                if not plan:
                    st.error("Run requires a valid plan.")
                else:
                    plan_run_id = str(plan.get("run_id") or "")
                    plan_artifacts_dir = str(plan.get("artifacts_dir") or "")

                    # Contract: Run has its own UUID identity (canonical artifacts folder)
                    run_id = str(uuid.uuid4())
                    artifacts_dir = settings.quant_runs_dir / run_id
                    cmd = _build_pipeline_cmd(
                        strategy_path=strategy_path,
                        start_date=str(start_date),
                        end_date=str(end_date),
                        run_id=run_id,
                        symbols_input=symbols_input,
                        stages=selected_stages,
                        dry_run=False,
                        fail_fast=fail_fast,
                    )

                    # Write initial run.json (RUNNING) for artifacts-first UI reconstruction.
                    write_initial_run_json(
                        run_id=run_id,
                        artifacts_dir=artifacts_dir,
                        invoked_command=" ".join(cmd),
                        plan_run_id=plan_run_id or None,
                        plan_artifacts_dir=plan_artifacts_dir or None,
                    )

                    started = ExecutionManager.start_run_with_artifacts(
                        cmd,
                        artifacts_dir=artifacts_dir,
                        cwd=settings.quant_data_dir.parent,
                        env={
                            "PYTHONPATH": str(settings.quant_data_dir.parent),
                            "QUANT_PLAN_RUN_ID": plan_run_id,
                            "QUANT_PLAN_ARTIFACTS_DIR": plan_artifacts_dir,
                        },
                    )
                    if started:
                        st.session_state["active_run_id"] = run_id
                        st.session_state["active_run_artifacts_dir"] = (
                            str(artifacts_dir) + "/"
                        )
                        st.query_params["run_id"] = run_id
                        st.session_state["show_live_log_dialog"] = True
                        st.session_state["live_log_run_id"] = run_id
                        st.success(f"Started run: {run_id}")
                        st.rerun()

        st.subheader("Utilities")
        with st.expander("Symbol Register (CLI 실행)", expanded=False):
            st.caption(
                "심볼 등록은 실행 행위이므로 Run Center에서만 트리거합니다. "
                "실제 수행은 `uv run quant symbol-register ...`를 subprocess로 실행합니다."
            )
            reg_symbol = (
                st.text_input("Symbol", placeholder="e.g. AAPL").strip().upper()
            )
            reg_ingest = st.checkbox(
                "Also ingest after register (external API)", value=False
            )
            if reg_ingest:
                st.warning(
                    "`--ingest`는 외부 시세 API 호출 + DuckDB write가 발생합니다. "
                    "동시 실행/락 충돌에 유의하세요."
                )

            if st.button("Register", type="secondary", width="stretch"):
                if not reg_symbol:
                    st.error("Symbol is required.")
                else:
                    util_run_id = str(uuid.uuid4())
                    util_dir = settings.quant_runs_dir / util_run_id
                    cmd = [
                        "uv",
                        "run",
                        "quant",
                        "symbol-register",
                        reg_symbol,
                    ]
                    if reg_ingest:
                        cmd.append("--ingest")

                    write_initial_run_json(
                        run_id=util_run_id,
                        artifacts_dir=util_dir,
                        invoked_command=" ".join(cmd),
                        kind="symbol-register",
                    )

                    started = ExecutionManager.start_run_with_artifacts(
                        cmd,
                        artifacts_dir=util_dir,
                        cwd=settings.quant_data_dir.parent,
                        env={
                            "PYTHONPATH": str(settings.quant_data_dir.parent),
                        },
                    )
                    if started:
                        st.session_state["active_run_id"] = util_run_id
                        st.query_params["run_id"] = util_run_id
                        st.success(f"Started symbol-register: {util_run_id}")
                        st.rerun()

    # --- Results Panel ---
with col_results:
    with st.container(border=True, height=800):
        st.subheader("Results")
        tab_plan, tab_run, tab_runs, tab_fail = st.tabs(
            ["Plan View", "Run View", "Recent Runs", "Failures"]
        )

        if st.session_state.get("show_live_log_dialog") and st.session_state.get(
            "live_log_run_id"
        ):
            _live_log_dialog(str(st.session_state.get("live_log_run_id")))

        with tab_plan:
            plan = st.session_state.get("plan")
            if not plan:
                st.info(
                    "Dry Run (Plan)을 실행하면 PLAN_JSON을 파싱해 구조적으로 표시합니다."
                )
            else:
                artifacts_dir = str(plan.get("artifacts_dir", ""))
                st.subheader("Parsed Plan")
                st.markdown(f"- Run ID: **{plan.get('run_id')}**")
                st.markdown(
                    f"- Strategy: **{plan.get('strategy_id')}@{plan.get('strategy_version')}**"
                )
                st.markdown(
                    f"- Date: **{plan.get('date_from')} → {plan.get('date_to')}**"
                )
                st.markdown(
                    f"- Stages: `{','.join(plan.get('stages_resolved') or [])}`"
                )
                sym_src = plan.get("symbols_source") or "unknown"
                st.markdown(
                    f"- Symbols ({sym_src}): `{','.join(plan.get('symbols_resolved') or [])}`"
                )

                v = plan.get("validation", {})
                ok = bool(v.get("ok"))
                st.markdown(f"- validation.ok: **{ok}**")

                st.markdown(f"- artifacts_dir: `{artifacts_dir}`")
                plan_path = Path(artifacts_dir.rstrip("/")) / "plan.json"
                st.markdown(f"- plan.json: `{plan_path}`")
                st.markdown(f"- plan.json exists: **{plan_path.exists()}**")

                if v.get("errors"):
                    st.error("Validation Errors")
                    for err in v.get("errors"):
                        st.write(f"- {err}")
                if v.get("warnings"):
                    st.warning("Validation Warnings")
                    for w in v.get("warnings"):
                        st.write(f"- {w}")

                with st.expander("Raw PLAN_JSON", expanded=False):
                    st.json(plan)

        with tab_run:
            # Artifacts-first Run Detail (no console text parsing)
            q = st.query_params.get("run_id")
            query_run_id = q[0] if isinstance(q, list) and q else (q or None)

            qs = st.query_params.get("run_slug")
            query_run_slug = qs[0] if isinstance(qs, list) and qs else (qs or None)

            resolved_from_slug = None
            if not query_run_id and query_run_slug:
                rr = resolve_run_id_from_slug(str(query_run_slug))
                resolved_from_slug = rr.run_id if rr else None

            run_id = (
                query_run_id
                or resolved_from_slug
                or st.session_state.get("active_run_id")
            )

            if not run_id:
                st.info("Run ID를 선택/입력하면 실행 상태(artifacts)를 표시합니다.")
            else:
                run_dir = get_run_dir(run_id)
                pid_file = run_dir / "pipeline.pid"
                log_file = run_dir / "pipeline.log"
                exit_code = ExecutionManager.read_exit_code(run_dir)
                running = ExecutionManager.is_running_pidfile(pid_file)

                run_json = read_run_json(run_id) or {}
                status = (run_json.get("status") or "").strip().lower() or None

                st.subheader(f"Run: {run_id}")
                st.markdown(f"- artifacts_dir: `{str(run_dir)}/`")

                derived_status = None
                if (
                    exit_code is not None
                    and not running
                    and (status in {None, "", "running"})
                ):
                    derived_status = "success" if int(exit_code) == 0 else "fail"

                effective_status = derived_status or status

                if effective_status == "success":
                    st.success("Status: SUCCEEDED")
                elif effective_status == "fail":
                    st.error("Status: FAILED")
                    # Pop-up for failure notification
                    if st.session_state.get("active_run_id") == run_id:
                        # Clear active_run_id after showing error once to prevent persistent popup if desired,
                        # but usually st.error is enough. The user specifically asked for "경고 팝업".
                        # Streamlit's toast could work, but a dialog is a "popup".
                        st.toast(f"Pipeline Failed: {run_id}", icon="❌")

                        # Show error details if available in run_json
                        err_text = run_json.get("error_text")
                        if err_text:
                            st.warning(f"Error Detail: {err_text}")

                elif effective_status == "running" or running:
                    st.info("Status: RUNNING")
                else:
                    st.warning("Status: UNKNOWN")

                if exit_code is not None:
                    st.markdown(f"- exit_code: **{exit_code}**")

                # Plan ↔ Run link (do not read run status from plan dir)
                if run_json.get("plan_run_id"):
                    st.markdown(f"- plan_run_id: `{run_json.get('plan_run_id')}`")
                if run_json.get("plan_artifacts_dir"):
                    st.markdown(
                        f"- plan_artifacts_dir: `{run_json.get('plan_artifacts_dir')}`"
                    )

                st.markdown("---")
                st.subheader("Run Summary (run.json)")
                if run_json:
                    cols = st.columns(4)
                    cols[0].metric("status", str(run_json.get("status") or "-"))
                    cols[1].metric("started_at", str(run_json.get("started_at") or "-"))
                    cols[2].metric("ended_at", str(run_json.get("ended_at") or "-"))
                    cols[3].metric("run_slug", str(run_json.get("run_slug") or "-"))
                else:
                    st.caption("run.json not found yet (run just started?)")

                st.markdown("---")
                st.subheader("Stage Results (stages/*/result.json)")
                stage_order = ["ingest", "features", "labels", "recommend", "backtest"]
                results = list_stage_results(run_id)
                cols = st.columns(len(stage_order))
                for i, s in enumerate(stage_order):
                    with cols[i]:
                        r = results.get(s)
                        ok = bool(r.get("ok")) if isinstance(r, dict) else None
                        icon = "⏳" if r is None else ("✅" if ok else "❌")
                        st.metric(s, icon)

                for s in stage_order:
                    r = results.get(s)
                    if not r:
                        continue
                    elapsed = parse_stage_elapsed_sec(r)
                    errors = parse_stage_errors(r)
                    with st.expander(f"{s} result.json", expanded=False):
                        st.markdown(f"- ok: **{bool(r.get('ok'))}**")
                        if elapsed is not None:
                            st.markdown(f"- elapsed_sec: **{elapsed:.2f}**")
                        if errors:
                            st.error("errors")
                            for err in errors:
                                st.write(f"- {err}")
                        st.json(r)

                st.markdown("---")
                st.subheader("Progress (PROGRESS_JSON)")
                log_text = read_pipeline_log(run_id) or ""
                events = parse_progress_events(log_text)
                latest = latest_progress_by_stage(events)
                if not latest:
                    st.caption("No PROGRESS_JSON events yet.")
                else:
                    for stage, ev in latest.items():
                        if ev.total and ev.current is not None:
                            st.write(f"{stage}: {ev.event or 'progress'}")
                            st.progress(
                                min(max(ev.current / max(ev.total, 1), 0.0), 1.0)
                            )
                            st.caption(f"{ev.current}/{ev.total}")

                st.markdown("---")
                st.subheader("pipeline.log (tail)")
                st.code(tail_pipeline_log(run_id, lines=200), language="text")

        with tab_runs:
            st.subheader("Run History (Artifacts SSOT)")

            show_legacy_sqlite = st.checkbox(
                "Show Legacy Index (SQLite) — NOT SSOT",
                value=False,
                help=(
                    "SQLite runs 테이블은 legacy/fallback 입니다. "
                    "기본은 artifacts SSOT(alias index → run.json scan)만 사용합니다."
                ),
            )

            c1, c2 = st.columns([0.6, 0.4])
            with c1:
                lookup = st.text_input(
                    "Open by run_id (UUID) or run_slug",
                    placeholder="e.g. 60f7b4e0-... or strategy__2024-01-01_...",
                ).strip()
            with c2:
                if st.button("Open", type="primary", width="stretch"):
                    resolved = None
                    if lookup:
                        if len(lookup) >= 32 and "-" in lookup:
                            resolved = lookup
                        else:
                            rr = resolve_run_id_from_slug(lookup)
                            resolved = rr.run_id if rr else None
                    if resolved:
                        st.session_state["active_run_id"] = resolved
                        st.query_params["run_id"] = resolved
                        st.rerun()
                    else:
                        st.warning("Could not resolve run_id.")

            idx = list_alias_index()
            if idx:
                st.markdown("**1) Alias index** (`artifacts/index/runs/*.json`)")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "run_slug": x.get("run_slug"),
                                "display_name": x.get("display_name"),
                                "run_id": x.get("run_id"),
                                "created_at": x.get("created_at"),
                            }
                            for x in idx
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("No alias index entries found.")

            st.markdown(
                "**2) Runs scanned from run.json** (`artifacts/runs/*/run.json`)"
            )
            runs_from_json = list_runs_from_run_json()
            if runs_from_json:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "run_id": x.get("run_id"),
                                "status": x.get("status"),
                                "started_at": x.get("started_at"),
                                "run_slug": x.get("run_slug"),
                                "display_name": x.get("display_name"),
                            }
                            for x in runs_from_json
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("No run.json found under artifacts/runs.")

            st.markdown("---")
            if show_legacy_sqlite:
                st.warning(
                    "Legacy index (SQLite) — optional fallback. "
                    "UI/관측은 artifacts SSOT가 우선이며, SQLite는 누락 보완용으로만 사용하세요."
                )
                try:
                    legacy_df = load_pipeline_summary(limit=30)
                    if not legacy_df.empty:
                        st.dataframe(
                            legacy_df[["run_id", "status", "started_at", "parent"]],
                            width="stretch",
                            hide_index=True,
                        )
                    else:
                        st.caption("SQLite runs table is empty or not available.")
                except Exception as e:
                    st.caption(f"SQLite legacy index unavailable: {e}")
            else:
                st.info(
                    "Legacy(SQLite) runs 인덱스는 기본 숨김입니다. "
                    "필요할 때만 위 토글로 표시하세요."
                )

        with tab_fail:
            st.subheader("Recent Failures")
            st.caption(
                "Failures는 SSOT(artifacts)에서 직접 재구성하는 것이 원칙입니다. "
                "현재 탭은 legacy SQLite fallback 기반입니다."
            )
            if show_legacy_sqlite:
                try:
                    legacy_df = load_pipeline_summary(limit=50)
                    if not legacy_df.empty:
                        fail_runs = legacy_df[legacy_df["status"] == "fail"]
                        if not fail_runs.empty:
                            st.dataframe(
                                fail_runs[["run_id", "started_at", "parent"]],
                                width="stretch",
                                hide_index=True,
                            )
                        else:
                            st.success("No recent failures!")
                except Exception:
                    pass
            else:
                st.info(
                    "Legacy(SQLite) fallback이 꺼져 있어 Failures 목록을 숨깁니다. "
                    "필요하면 Run History 탭의 토글을 켜세요."
                )
