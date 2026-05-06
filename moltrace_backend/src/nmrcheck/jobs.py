from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .analysis import analyze_inputs
from .database import create_session_factory, mark_job_started, save_analysis, update_job_progress
from .models import AnalysisInputs



def process_job_items(
    session_factory: sessionmaker[Session],
    *,
    job_id: int,
    items: list[AnalysisInputs],
    user_id: int | None = None,
) -> None:
    mark_job_started(session_factory, job_id)
    completed = 0
    try:
        for completed, item in enumerate(items, start=1):
            report = analyze_inputs(item)
            save_analysis(session_factory, report, item, user_id=user_id, job_id=job_id)
            update_job_progress(session_factory, job_id, completed_items=completed, status="processing")
        update_job_progress(session_factory, job_id, completed_items=completed, status="completed")
    except Exception as exc:  # pragma: no cover - defensive worker path
        update_job_progress(
            session_factory,
            job_id,
            completed_items=completed,
            status="failed",
            error_message=str(exc),
        )
        raise



def process_job_items_from_url(
    database_url: str,
    *,
    job_id: int,
    items_payload: list[dict[str, object]],
    user_id: int | None = None,
) -> None:
    session_factory = create_session_factory(database_url)
    items = [AnalysisInputs.model_validate(item) for item in items_payload]
    process_job_items(session_factory, job_id=job_id, items=items, user_id=user_id)
