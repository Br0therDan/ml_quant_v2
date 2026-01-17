from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from ..config import settings


def connect(
    path: Path | None = None, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    db_path = Path(path or settings.quant_duckdb_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path), read_only=read_only)


def exec_sql(
    conn: duckdb.DuckDBPyConnection, sql: str, params: Any | None = None
) -> None:
    if params is None:
        conn.execute(sql)
    else:
        conn.execute(sql, params)
