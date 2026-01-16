import os
import yaml
from pathlib import Path
from typing import List, Optional

# Base directory should be absolute to avoid CWD issues
BASE_DIR = Path.cwd().resolve()
STRATEGY_DIR = BASE_DIR / "strategies"


def list_strategies() -> List[str]:
    """List all YAML files in strategies/. (strategies/generated는 legacy)"""
    if not STRATEGY_DIR.exists():
        return []

    # Use rglob or combined glob
    files = list(STRATEGY_DIR.glob("*.yaml"))

    relative_files = []
    for f in files:
        try:
            # Use os.path.relpath which is more robust for relative path calculation
            rel_path = os.path.relpath(f.resolve(), BASE_DIR)
            relative_files.append(rel_path)
        except Exception:
            # Fallback to name if relpath fails
            relative_files.append(f.name)

    return sorted(list(set(relative_files)))


def load_strategy_content(file_path: str) -> Optional[str]:
    """Read full text of a strategy file."""
    try:
        # ensure file_path is treated relative to BASE_DIR if it's not absolute
        path = Path(file_path)
        if not path.is_absolute():
            path = BASE_DIR / file_path

        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def save_strategy_as(new_filename: str, content: str) -> bool:
    """Save content to strategies/ folder (human-authored source of truth)."""
    try:
        if not new_filename.endswith(".yaml"):
            new_filename += ".yaml"

        STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
        # Use basename to prevent directory traversal
        target_path = STRATEGY_DIR / os.path.basename(new_filename)

        target_path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False
