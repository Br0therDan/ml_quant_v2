import uuid
import json
from datetime import datetime
from typing import Optional, Any
from sqlmodel import Session
from ..models.meta import Run
from ..db.engine import get_session


class RunRegistry:
    @staticmethod
    def run_start(
        kind: str,
        config: Optional[dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """Create a new run record in the SQLite meta database."""
        run_id = run_id or str(uuid.uuid4())
        run = Run(
            run_id=run_id,
            kind=kind,
            status="running",
            started_at=datetime.utcnow().isoformat(),
            config_json=json.dumps(config) if config else None,
        )
        with get_session() as session:
            session.add(run)
            session.commit()
        return run_id

    @staticmethod
    def run_success(run_id: str):
        """Mark a run as successful."""
        with get_session() as session:
            run = session.get(Run, run_id)
            if run:
                run.status = "success"
                run.ended_at = datetime.utcnow().isoformat()
                session.add(run)
                session.commit()

    @staticmethod
    def run_fail(run_id: str, error_text: str):
        """Mark a run as failed with error details."""
        with get_session() as session:
            run = session.get(Run, run_id)
            if run:
                run.status = "fail"
                run.ended_at = datetime.utcnow().isoformat()
                run.error_text = error_text
                session.add(run)
                session.commit()
