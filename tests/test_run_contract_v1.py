import json
import os
import subprocess
from pathlib import Path


def _run_quant_pipeline_dry_run(
    *,
    tmp_runs_dir: Path,
    extra_args: list[str],
) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["QUANT_ARTIFACTS_DIR"] = str(tmp_runs_dir.parent)
    env["QUANT_RUNS_DIR"] = str(tmp_runs_dir)

    cmd = [
        "uv",
        "run",
        "quant",
        "pipeline",
        "run",
        "--strategy",
        "strategies/example.yaml",
        "--from",
        "2024-01-01",
        "--to",
        "2024-01-10",
        "--dry-run",
    ] + extra_args

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _extract_plan(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("PLAN_JSON:"):
            return json.loads(line.split("PLAN_JSON:", 1)[1].strip())
    raise AssertionError("PLAN_JSON line not found")


def test_dry_run_emits_plan_json_and_writes_plan_file(tmp_path: Path):
    runs_dir = tmp_path / "artifacts" / "runs"

    rc, out, err = _run_quant_pipeline_dry_run(tmp_runs_dir=runs_dir, extra_args=[])
    assert rc == 0, f"dry-run should succeed. stderr={err}"

    plan = _extract_plan(out)
    assert plan["dry_run"] is True

    artifacts_dir = Path(str(plan["artifacts_dir"]).rstrip("/"))
    assert str(artifacts_dir).startswith(
        str(runs_dir)
    ), "artifacts_dir must be under artifacts/runs"

    plan_path = artifacts_dir / "plan.json"
    assert (
        plan_path.exists()
    ), "plan.json must be created under artifacts/runs/<run_id>/plan.json"


def test_dry_run_symbols_override_reflected_in_symbols_resolved(tmp_path: Path):
    runs_dir = tmp_path / "artifacts" / "runs"

    rc, out, err = _run_quant_pipeline_dry_run(
        tmp_runs_dir=runs_dir,
        extra_args=["--symbols", "AAPL,PLTR,QQQM"],
    )
    assert rc == 0, f"dry-run should succeed. stderr={err}"

    plan = _extract_plan(out)
    assert plan["symbols_resolved"] == ["AAPL", "PLTR", "QQQM"]


def test_dry_run_stages_subset(tmp_path: Path):
    runs_dir = tmp_path / "artifacts" / "runs"

    rc, out, err = _run_quant_pipeline_dry_run(
        tmp_runs_dir=runs_dir,
        extra_args=["--stages", "recommend,backtest"],
    )
    assert rc == 0, f"dry-run should succeed. stderr={err}"

    plan = _extract_plan(out)
    assert plan["stages_resolved"] == ["recommend", "backtest"]


def test_invalid_stage_fails_before_start(tmp_path: Path):
    runs_dir = tmp_path / "artifacts" / "runs"

    rc, out, err = _run_quant_pipeline_dry_run(
        tmp_runs_dir=runs_dir,
        extra_args=["--stages", "foo"],
    )
    assert rc != 0
    assert "Invalid stage" in (out + err)
