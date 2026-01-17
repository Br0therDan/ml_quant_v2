import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from quant.config import settings


def _legacy_log_dir() -> Path:
    """Legacy UI log dir (disabled by default).

    V2 GUI Contract requires artifacts SSOT only. We keep this for backward
    compatibility but do not create the directory unless explicitly enabled.
    """

    enabled = os.getenv("QUANT_UI_ENABLE_LEGACY_LOGS", "0") == "1"
    p = settings.quant_data_dir.parent / "logs" / "ui_exec"
    if enabled:
        p.mkdir(parents=True, exist_ok=True)
    return p


class ExecutionManager:
    """Manages CLI subprocess execution from Streamlit UI."""

    @staticmethod
    def get_log_path(run_key: str) -> Path:
        return _legacy_log_dir() / f"{run_key}.log"

    @staticmethod
    def run_command_async(
        command: list[str],
        run_key: str,
        cwd: Path | None = None,
        env: dict | None = None,
    ) -> bool:
        """
        Runs a command asynchronously, redirecting stdout/stderr to a log file.
        Returns True if process started successfully.
        """
        log_file = ExecutionManager.get_log_path(run_key)

        try:
            # Prepare environment
            proc_env = os.environ.copy()
            if env:
                proc_env.update(env)

            # Using 'uv run' might require full path or shell=False if 'uv' is in PATH
            # We assume 'uv' is in PATH.

            with open(log_file, "w") as f:
                # Write header
                f.write(f"--- UI Execution Start: {datetime.now()} ---\n")
                f.write(f"--- Command: {' '.join(command)} ---\n\n")
                f.flush()

                # Start subprocess detached
                subprocess.Popen(
                    command,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=cwd or settings.quant_data_dir.parent,
                    env=proc_env,
                    # preexec_fn=os.setsid # setsid to detach process group?
                    # Streamlit lifecycle might kill it?
                    # Generally Popen allows it to continue unless explicit kill.
                )
            return True
        except Exception as e:
            st.error(f"Failed to start process: {e}")
            return False

    @staticmethod
    def is_running(run_key: str) -> bool:
        """
        Check if a run is active.
        Since we don't store PID persistently, we might rely on a 'lock' file
        or just check if the log file was updated recently?

        Actually, for a robust solution without a DB, we can't easily track PIDs across Streamlit reruns
        unless we store them in Session State (which is per-session) or a shared file.

        For V2 simple implementation:
        We will rely on DuckDB lock check for global concurrency.
        For identifying if specific 'run_key' is finished, we can check if log file says "Finished" or "Failed"?
        Or finding if a process with that signature exists?

        Let's implement a simple PID file mechanism.
        """
        pid_file = _legacy_log_dir() / f"{run_key}.pid"
        if not pid_file.exists():
            return False

        try:
            pid = int(pid_file.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
        except OSError:
            return False
        except ValueError:
            return False

        return True

    @staticmethod
    def start_run(command: list[str], run_key: str) -> bool:
        """Start run with PID tracking."""
        log_file = ExecutionManager.get_log_path(run_key)
        pid_file = _legacy_log_dir() / f"{run_key}.pid"

        # Check if already running?

        try:
            with open(log_file, "w") as f:
                f.write(f"--- UI Execution Start: {datetime.now()} ---\n")
                f.write(f"--- Command: {' '.join(command)} ---\n\n")
                f.flush()

                proc = subprocess.Popen(
                    command,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=settings.quant_data_dir.parent,
                    env=os.environ.copy(),
                )

                # Save PID
                pid_file.write_text(str(proc.pid))

            return True
        except Exception as e:
            st.error(f"Failed to start process: {e}")
            return False

    @staticmethod
    def start_run_with_artifacts(
        command: list[str],
        *,
        artifacts_dir: Path,
        cwd: Path | None = None,
        env: dict | None = None,
    ) -> bool:
        """Start a run and write logs+status files under artifacts/runs/<run_id>/.

        - stdout/stderr -> pipeline.log
        - exit code -> exit_code.txt
        - pid -> pipeline.pid
        """
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        log_file = artifacts_dir / "pipeline.log"
        exit_code_file = artifacts_dir / "exit_code.txt"
        pid_file = artifacts_dir / "pipeline.pid"
        wrapper_log_file = artifacts_dir / "ui_wrapper.log"

        runner_script = (
            settings.quant_data_dir.parent / "app" / "ui" / "subprocess_runner.py"
        )
        if not runner_script.exists():
            st.error(f"Missing runner script: {runner_script}")
            return False

        wrapper_cmd = [
            sys.executable,
            str(runner_script),
            "--log-file",
            str(log_file),
            "--exit-code-file",
            str(exit_code_file),
            "--pid-file",
            str(pid_file),
            "--cwd",
            str(cwd or settings.quant_data_dir.parent),
            "--",
        ] + command

        try:
            proc_env = os.environ.copy()
            if env:
                proc_env.update(env)
            with open(wrapper_log_file, "w", encoding="utf-8") as wf:
                subprocess.Popen(
                    wrapper_cmd,
                    stdout=wf,
                    stderr=subprocess.STDOUT,
                    cwd=str(cwd or settings.quant_data_dir.parent),
                    env=proc_env,
                )

            # Best-effort sanity check: the wrapper should create pid/log quickly.
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if pid_file.exists() and log_file.exists():
                    return True
                time.sleep(0.05)

            st.error(
                "Subprocess runner did not initialize (pid/log not created). "
                f"Check: {wrapper_log_file}"
            )
            return False
        except Exception as e:
            st.error(f"Failed to start process: {e}")
            return False

    @staticmethod
    def read_exit_code(artifacts_dir: Path) -> int | None:
        p = artifacts_dir / "exit_code.txt"
        if not p.exists():
            return None
        try:
            return int(p.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    @staticmethod
    def is_running_pidfile(pid_file: Path) -> bool:
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    @staticmethod
    def get_log_tail_path(log_file: Path, lines: int = 200) -> str:
        if not log_file.exists():
            return "No log file found."
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            all_lines = content.splitlines()
            return "\n".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading log: {e}"

    @staticmethod
    def get_log_tail(run_key: str, lines: int = 50) -> str:
        log_file = ExecutionManager.get_log_path(run_key)
        if not log_file.exists():
            return "No log file found."

        try:
            # Simple tail implementation
            # For very large files this is inefficient, but logs are usually small < 1MB
            content = log_file.read_text(encoding="utf-8", errors="replace")
            all_lines = content.splitlines()
            return "\n".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading log: {e}"

    @staticmethod
    def check_duckdb_lock(db_path: str = str(settings.quant_duckdb_path)) -> bool:
        """Returns True if DuckDB is likely locked (Streamlit accessing it?)."""
        # It's hard to check efficiently without trying to connect.
        # But for 'concurrency warning', we assume if Streamlit is running, it might hold read lock.
        # Actually, if we launch a subprocess, it will try to acquire WRITE lock.
        # If Streamlit holds READ lock, WRITE might fail or block.
        # This function acts as a warning helper.
        return False  # Placeholder: currently just relying on user discretion
