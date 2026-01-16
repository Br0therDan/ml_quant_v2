from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..config import settings


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path or settings.quant_sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def exec_sql(conn: sqlite3.Connection, sql: str, params: Any | None = None) -> None:
    cur = conn.cursor()
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)
    conn.commit()
