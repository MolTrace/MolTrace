"""A batch that was killed mid-flight stops claiming it is still running.

`process_job_items` marks a job `processing`, loops, and marks it `completed` or
-- in an `except` -- `failed`. That covers a Python exception. It does not cover
the process being killed, and on Cloud Run being killed is the *expected* path:

* the work runs in FastAPI `BackgroundTasks`, i.e. **after the response is
  sent**, because with no `REDIS_URL` `enqueue_job_processing` falls back from RQ
  to in-process background tasks;
* the service deploys with `--min-instances 0` and no `--no-cpu-throttling`, so
  CPU is allocated during request processing only, and the instance can be
  reclaimed entirely once traffic stops.

A SIGKILL raises nothing, so nothing marks the job failed, and there was no
reaper anywhere in the codebase. The row sat at `processing` with partial
results saved, forever. For a regulated product a batch that says "running" and
silently never finishes is worse than a clean error: a reviewer waits on it.

**The deadline is per-job, not a flat age.** A one-item job and a hundred-item
job are not equally suspicious at ten minutes. It is derived from the job's own
`total_items`, so the bound scales with the work actually promised.

**The budget is deliberately generous, and the asymmetry is the reason.** One
batch item measures 0.9 ms (ethanol) to 50 ms (an erythromycin-sized structure)
locally. The shipped per-item budget is 30 s -- some 600x the measured worst
case -- because the two failure directions are not symmetric: too generous means
a dead job lingers a while longer, which costs nothing; too tight means killing a
job that is still working, which destroys a running batch. Under CPU throttling
the real throughput is not merely slower but effectively unbounded, so no
measured multiple of local speed would be a safe upper bound anyway. The number
is a floor on patience, not an estimate of duration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text as sa_text


def _engine(client):
    return client.app.state.session_factory.kw["bind"]


def _make_job(
    client,
    *,
    status: str,
    total_items: int,
    started_minutes_ago: float | None,
    created_minutes_ago: float = 600.0,
    completed_items: int = 0,
) -> int:
    now = datetime.now(UTC)
    created = now - timedelta(minutes=created_minutes_ago)
    started = None if started_minutes_ago is None else now - timedelta(minutes=started_minutes_ago)
    with _engine(client).begin() as conn:
        conn.execute(
            sa_text(
                "INSERT INTO jobs (created_at, started_at, status, total_items,"
                " completed_items, review_required)"
                " VALUES (:c, :s, :st, :t, :ci, 1)"
            ),
            {
                "c": created,
                "s": started,
                "st": status,
                "t": total_items,
                "ci": completed_items,
            },
        )
        return int(conn.execute(sa_text("SELECT MAX(id) FROM jobs")).scalar_one())


def _row(client, job_id: int) -> dict:
    with _engine(client).begin() as conn:
        r = conn.execute(
            sa_text(
                "SELECT status, completed_items, error_message, finished_at"
                " FROM jobs WHERE id = :i"
            ),
            {"i": job_id},
        ).one()
    return {
        "status": r[0],
        "completed_items": r[1],
        "error_message": r[2],
        "finished_at": r[3],
    }


class TestAnAbandonedJobIsMarkedFailed:
    def test_a_long_abandoned_job_stops_saying_processing(self, client, api_headers) -> None:
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(client, status="processing", total_items=5, started_minutes_ago=600)
        reaped = reap_stale_jobs(client.app.state.session_factory)

        assert job_id in reaped
        assert _row(client, job_id)["status"] == "failed"

    def test_the_failure_says_what_happened(self, client, api_headers) -> None:
        """"Unknown error" would send a reviewer looking for a bug that isn't there."""
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(client, status="processing", total_items=5, started_minutes_ago=600)
        reap_stale_jobs(client.app.state.session_factory)

        message = (_row(client, job_id)["error_message"] or "").lower()
        assert message, "the job failed with no explanation"
        assert "stop" in message or "interrupt" in message or "did not finish" in message, (
            f"the message does not say what happened: {message!r}"
        )

    def test_partial_progress_is_preserved(self, client, api_headers) -> None:
        """The analyses that did complete are real and stay attributable to the job."""
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(
            client,
            status="processing",
            total_items=10,
            completed_items=4,
            started_minutes_ago=600,
        )
        reap_stale_jobs(client.app.state.session_factory)

        row = _row(client, job_id)
        assert row["completed_items"] == 4, "the reaper discarded the progress that was made"
        assert "4" in (row["error_message"] or ""), (
            "the message does not tell the reviewer how far it got"
        )

    def test_a_finished_job_is_closed_out(self, client, api_headers) -> None:
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(client, status="processing", total_items=1, started_minutes_ago=600)
        reap_stale_jobs(client.app.state.session_factory)
        assert _row(client, job_id)["finished_at"] is not None


class TestALiveJobIsLeftAlone:
    """Killing a running batch is the expensive mistake; err toward patience."""

    def test_a_job_inside_its_budget_is_untouched(self, client, api_headers) -> None:
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(client, status="processing", total_items=5, started_minutes_ago=1)
        reaped = reap_stale_jobs(client.app.state.session_factory)

        assert job_id not in reaped
        assert _row(client, job_id)["status"] == "processing"

    def test_a_big_batch_gets_proportionally_longer(self, client, api_headers) -> None:
        """A 100-item job is not as suspicious as a 1-item job at the same age.

        Both are started 30 minutes ago. The small one is well past any credible
        budget; the large one has 100 items' worth of allowance and is still
        inside it.
        """
        from nmrcheck.database import reap_stale_jobs

        small = _make_job(client, status="processing", total_items=1, started_minutes_ago=30)
        large = _make_job(client, status="processing", total_items=100, started_minutes_ago=30)
        reaped = reap_stale_jobs(client.app.state.session_factory)

        assert small in reaped
        assert large not in reaped, "a large batch was killed on a small batch's clock"

    @pytest.mark.parametrize("status", ["completed", "failed"])
    def test_a_settled_job_is_never_touched(self, client, api_headers, status) -> None:
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(client, status=status, total_items=5, started_minutes_ago=600)
        reaped = reap_stale_jobs(client.app.state.session_factory)

        assert job_id not in reaped
        assert _row(client, job_id)["status"] == status

    def test_a_queued_job_is_measured_from_creation(self, client, api_headers) -> None:
        """A job killed before it ever started has no started_at to measure from."""
        from nmrcheck.database import reap_stale_jobs

        fresh = _make_job(
            client,
            status="queued",
            total_items=2,
            started_minutes_ago=None,
            created_minutes_ago=1,
        )
        old = _make_job(
            client,
            status="queued",
            total_items=2,
            started_minutes_ago=None,
            created_minutes_ago=600,
        )
        reaped = reap_stale_jobs(client.app.state.session_factory)

        assert fresh not in reaped
        assert old in reaped


class TestTheReaperRunsWithoutAnyInfrastructure:
    """It has to work on a service that scales to zero and has no worker."""

    def test_listing_jobs_reaps_first(self, client, api_headers) -> None:
        """Reap-on-read: a reviewer can never be shown a job that is secretly dead.

        A cron would need infrastructure this deployment does not have -- the
        whole point is that there is no always-on process. Doing it on the read
        costs one bounded UPDATE and needs nothing.
        """
        job_id = _make_job(client, status="processing", total_items=1, started_minutes_ago=600)

        res = client.get("/jobs", headers=api_headers)
        assert res.status_code == 200, res.text

        assert _row(client, job_id)["status"] == "failed", (
            "GET /jobs returned without reckoning with an abandoned job"
        )
        listed = [j for j in res.json() if j.get("id") == job_id]
        assert listed and listed[0]["status"] == "failed", (
            "the response still showed the job as running"
        )

    def test_fetching_one_job_reaps_it(self, client, api_headers) -> None:
        job_id = _make_job(client, status="processing", total_items=1, started_minutes_ago=600)

        res = client.get(f"/jobs/{job_id}", headers=api_headers)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "failed"

    def test_reaping_is_idempotent(self, client, api_headers) -> None:
        from nmrcheck.database import reap_stale_jobs

        job_id = _make_job(client, status="processing", total_items=1, started_minutes_ago=600)
        first = reap_stale_jobs(client.app.state.session_factory)
        second = reap_stale_jobs(client.app.state.session_factory)

        assert job_id in first
        assert second == [], "a second sweep re-reaped an already-failed job"

class TestTheOtherJobTableDoesNotNeedReaping:
    """`GET /jobs` returns two job types. Only one can be abandoned.

    `analysis_jobs` is served by the same endpoint as `jobs`, so "did you cover
    both?" is the obvious question — and the answer is that they are not the
    same shape. `create_analysis_job` runs the work **synchronously inside the
    request**, moving queued -> running -> succeeded/failed within one
    transaction, so there is no runner that can be killed while a row waits on
    it. Probed: a created analysis job comes back already settled with
    `finished_at` set and nothing left unsettled.

    This test exists so that stops being an assumption. If analysis jobs are ever
    moved to a background runner, this fails and says what to do about it —
    rather than the silent hang reappearing on a table the reaper never looked
    at.
    """

    def test_an_analysis_job_settles_before_the_response_returns(
        self, client, api_headers
    ) -> None:
        res = client.post("/jobs", headers=api_headers, json={"job_type": "processed_spectrum_parse"})
        assert res.status_code == 201, res.text

        body = res.json()
        assert body["status"] in {"succeeded", "failed", "canceled"}, (
            f"an analysis job returned unsettled as {body['status']!r}. If these now run in "
            "the background, they can be abandoned exactly like batch jobs and "
            "reap_stale_jobs must be extended to cover the analysis_jobs table."
        )
        assert body.get("finished_at") is not None

    def test_no_analysis_job_is_left_running(self, client, api_headers) -> None:
        client.post("/jobs", headers=api_headers, json={"job_type": "processed_spectrum_parse"})
        with _engine(client).begin() as conn:
            unsettled = conn.execute(
                sa_text("SELECT COUNT(*) FROM analysis_jobs WHERE status IN ('queued','running')")
            ).scalar_one()
        assert unsettled == 0, (
            f"{unsettled} analysis job(s) left unsettled — the reaper does not cover this table"
        )
