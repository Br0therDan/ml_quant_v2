from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a command and tee output to a log file."
    )
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--exit-code-file", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise SystemExit("No command provided. Use: subprocess_runner.py -- ...")

    log_path = Path(args.log_file)
    exit_code_path = Path(args.exit_code_file)
    pid_path = Path(args.pid_file)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    exit_code_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    cwd = Path(args.cwd) if args.cwd else None

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"--- UI Execution Start: {datetime.now()} ---\n")
        f.write(f"--- Command: {' '.join(cmd)} ---\n\n")
        f.flush()

        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        rc = proc.wait()

    exit_code_path.write_text(str(rc), encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
