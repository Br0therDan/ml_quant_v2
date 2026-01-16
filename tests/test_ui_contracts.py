import json
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest


def test_progress_events_parser():
    from app.ui.progress_events import parse_progress_events, latest_progress_by_stage

    log_text = "\n".join(
        [
            "hello",
            'PROGRESS_JSON: {"stage":"ingest","event":"start","current":0,"total":3}',
            'PROGRESS_JSON: {"stage":"ingest","event":"tick","current":1,"total":3}',
            'PROGRESS_JSON: {"stage":"features","event":"start","current":0,"total":1}',
            "bye",
        ]
    )

    events = parse_progress_events(log_text)
    assert len(events) == 3

    latest = latest_progress_by_stage(events)
    assert latest["ingest"].current == 1
    assert latest["ingest"].total == 3
    assert latest["features"].event == "start"


def test_subprocess_runner_writes_artifacts(tmp_path: Path):
    runner = Path(__file__).resolve().parents[1] / "app" / "ui" / "subprocess_runner.py"
    assert runner.exists()

    artifacts_dir = tmp_path / "artifacts"
    log_file = artifacts_dir / "pipeline.log"
    exit_code_file = artifacts_dir / "exit_code.txt"
    pid_file = artifacts_dir / "pipeline.pid"

    cmd = [
        sys.executable,
        str(runner),
        "--log-file",
        str(log_file),
        "--exit-code-file",
        str(exit_code_file),
        "--pid-file",
        str(pid_file),
        "--cwd",
        str(tmp_path),
        "--",
        sys.executable,
        "-c",
        'print(\'PROGRESS_JSON: {\\"stage\\":\\"ingest\\",\\"event\\":\\"tick\\",\\"current\\":1,\\"total\\":2}\')',
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0

    assert log_file.exists()
    assert exit_code_file.exists()
    assert pid_file.exists()

    assert exit_code_file.read_text(encoding="utf-8").strip() == "0"
    log_text = log_file.read_text(encoding="utf-8", errors="replace")
    assert "PROGRESS_JSON:" in log_text


def test_write_initial_run_json_contains_plan_links(tmp_path: Path):
    from app.ui.run_artifacts import write_initial_run_json

    run_id = str(uuid.uuid4())
    artifacts_dir = tmp_path / "runs" / run_id

    p = write_initial_run_json(
        run_id=run_id,
        artifacts_dir=artifacts_dir,
        invoked_command="uv run quant pipeline run ...",
        plan_run_id="plan_123",
        plan_artifacts_dir=str(tmp_path / "runs" / "plan_123") + "/",
    )

    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert payload["status"] == "running"
    assert payload["plan_run_id"] == "plan_123"
    assert "plan_artifacts_dir" in payload


def test_pipeline_dry_run_persists_plan_json(tmp_path: Path):
    # Run the CLI in a subprocess to respect env-based settings.
    artifacts_dir = tmp_path / "artifacts"
    runs_dir = artifacts_dir / "runs"
    data_dir = tmp_path / "data"

    strategy_path = tmp_path / "strategy.yaml"
    strategy_path.write_text(
        textwrap.dedent(
            """
            strategy_id: demo
            version: v1
            universe:
              type: symbols
              symbols: [AAPL]
            signal:
              type: factor_rank
              inputs:
                feature_name: ret_1d
                feature_version: v1
            rebalance:
              frequency: daily
            portfolio:
              top_k: 3
            supervisor:
              max_positions: 3
            """
        ).lstrip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "QUANT_ARTIFACTS_DIR": str(artifacts_dir),
            "QUANT_RUNS_DIR": str(runs_dir),
            "QUANT_DATA_DIR": str(data_dir),
            "QUANT_DUCKDB_PATH": str(data_dir / "quant.duckdb"),
            "QUANT_SQLITE_PATH": str(data_dir / "meta.db"),
        }
    )

    cmd = [
        sys.executable,
        "-m",
        "quant.cli",
        "pipeline",
        "run",
        "--strategy",
        str(strategy_path),
        "--from",
        "2025-01-01",
        "--to",
        "2025-01-10",
        "--run-id",
        "plan_test",
        "--dry-run",
        "--stages",
        "features",
    ]

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    plan_path = runs_dir / "plan_test" / "plan.json"
    assert plan_path.exists()

    plan = json.loads(plan_path.read_text(encoding="utf-8").strip())
    assert plan["run_id"] == "plan_test"
    assert plan["validation"]["ok"] is True


def test_no_sql_fstrings_in_data_access():
    # Guardrail: UI SQL must use parameter binding, not f-strings.
    p = Path(__file__).resolve().parents[1] / "app" / "ui" / "data_access.py"
    text = p.read_text(encoding="utf-8")

    forbidden = [
        'pd.read_sql(\n            f"SELECT',
        'pd.read_sql(f"SELECT',
        'conn.execute(f"SELECT',
        'run_query(f"SELECT',
        'run_query(f"\n        SELECT',
    ]
    for pat in forbidden:
        assert pat not in text


def test_no_sql_fstrings_in_data_center_page():
    # Guardrail: pages should not build SQL via f-strings.
    p = Path(__file__).resolve().parents[1] / "app" / "pages" / "3_Data_Center.py"
    text = p.read_text(encoding="utf-8")
    forbidden = [
        "SELECT * FROM ohlcv",
        "WHERE symbol = '{symbol}'",
        'f"""\n            SELECT',
        'f"SELECT',
        "conn.execute(query)",
    ]
    for pat in forbidden:
        assert pat not in text
