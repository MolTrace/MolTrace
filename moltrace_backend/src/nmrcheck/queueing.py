from __future__ import annotations

from dataclasses import dataclass

from fastapi import BackgroundTasks

from .jobs import process_job_items, process_job_items_from_url
from .models import AnalysisInputs
from .settings import Settings

try:  # pragma: no cover - import depends on optional package
    from redis import Redis
    from rq import Queue
except Exception:  # pragma: no cover
    Redis = None
    Queue = None


@dataclass(frozen=True)
class EnqueueResult:
    backend: str
    backend_job_id: str | None = None



def enqueue_job_processing(
    *,
    settings: Settings,
    database_url: str,
    session_factory,
    background_tasks: BackgroundTasks,
    job_id: int,
    items: list[AnalysisInputs],
    user_id: int | None = None,
) -> EnqueueResult:
    if settings.redis_url and Redis is not None and Queue is not None:
        redis_conn = Redis.from_url(settings.redis_url)
        queue = Queue(name=settings.queue_name, connection=redis_conn)
        job = queue.enqueue(
            process_job_items_from_url,
            database_url,
            job_id=job_id,
            items_payload=[item.model_dump(mode="json") for item in items],
            user_id=user_id,
        )
        return EnqueueResult(backend="rq", backend_job_id=job.id)

    background_tasks.add_task(
        process_job_items,
        session_factory,
        job_id=job_id,
        items=items,
        user_id=user_id,
    )
    return EnqueueResult(backend="fastapi-background")
