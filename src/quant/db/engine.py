from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, create_engine

from ..config import settings

# Global engine instance
_engine = None


def get_engine(path: Path | None = None, force_new: bool = False):
    global _engine
    if force_new:
        _engine = None

    if _engine is None or path is not None:
        db_path = Path(path or settings.quant_sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # SQLite handles file deletion/creation better with pool_pre_ping or by ensuring fresh engine
        engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        if path is None:
            _engine = engine
        return engine
    return _engine


def get_session(path: Path | None = None) -> Session:
    engine = get_engine(path)
    return Session(engine)
