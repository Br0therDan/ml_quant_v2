import subprocess
import os
import signal
from pathlib import Path
from datetime import datetime
from typing import List, Optional

RUNS_DIR = Path("artifacts/runs")


class PipelineRunner:
    @staticmethod
    def start_pipeline(
        strategy_path: str,
        start_date: str,
        end_date: str,
        symbols: List[str] = None,
        dry_run: bool = False,
        stages: List[str] = None,
    ) -> Optional[str]:
        """
        Start pipeline via 'uv run quant pipeline run'.
        Returns run_id.
        """
        run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_UI"
        log_dir = RUNS_DIR / run_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "pipeline.log"

        cmd = ["uv", "run", "quant", "pipeline", "run", "--strategy", strategy_path]
        cmd += ["--from", start_date, "--to", end_date]

        if symbols:
            cmd += ["--symbols"] + symbols
        if dry_run:
            cmd += ["--dry-run"]
        if stages:
            cmd += ["--stages", ",".join(stages)]

        try:
            with open(log_file, "w") as f:
                f.write(f"--- UI Execution Start: {datetime.now()} ---\n")
                f.write(f"--- Command: {' '.join(cmd)} ---\n\n")
                f.flush()

                # Start in background
                subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    env=os.environ.copy(),
                )
            return run_id
        except Exception:
            return None

    @staticmethod
    def get_log_tail(run_id: str, n_lines: int = 300) -> str:
        """Tail last N lines of the pipeline log."""
        log_file = RUNS_DIR / run_id / "pipeline.log"
        if not log_file.exists():
            return "Log file not found."

        try:
            with open(log_file, "r") as f:
                lines = f.readlines()
                return "".join(lines[-n_lines:])
        except Exception as e:
            return f"Error reading log: {e}"
