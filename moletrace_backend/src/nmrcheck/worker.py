from __future__ import annotations

from redis import Redis
from rq import Queue, Worker

from .settings import get_settings


def main() -> None:
    settings = get_settings()

    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not set. Configure Redis before starting the worker.")

    redis_conn = Redis.from_url(settings.redis_url)
    queue_names = [getattr(settings, "queue_name", "nmrcheck")]
    queues = [Queue(name, connection=redis_conn) for name in queue_names]

    worker = Worker(queues=queues, connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
