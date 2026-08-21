"""The project dashboard renders twelve activity rows; it used to cost 101 queries.

``build_project_dashboard`` asked the audit log about one entity at a time — the
project, then every sample, then every analysis — and each of those calls opened
its OWN ``session_scope`` nested inside the dashboard's. On a 50-sample project
that is 101 connection checkouts (each with a pool pre-ping round trip) against a
pool of 15, and up to 5,050 rows fetched to display ``activity[:12]``.

Counting queries is the only way this stays fixed: the endpoint returns the same
payload either way, so a regression is invisible to every other test.
"""

from __future__ import annotations

from sqlalchemy import event

from nmrcheck.database import (
    build_project_dashboard,
    create_project,
    create_project_sample,
    create_session_factory,
    create_user,
    init_db,
)
from nmrcheck.models import ProjectSampleCreate


def _factory(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'dash.sqlite3'}")
    init_db(factory)
    return factory


class _QueryCounter:
    """Counts SELECTs issued against the engine while active."""

    def __init__(self, factory):
        self.engine = factory.kw["bind"]
        self.selects = 0

    def _before(self, _conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            self.selects += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._before)
        return self

    def __exit__(self, *_exc):
        event.remove(self.engine, "before_cursor_execute", self._before)
        return False


def _seed(factory, *, sample_count: int):
    user = create_user(factory, email="dash@example.com", password="correct-horse-1")
    project = create_project(factory, user_id=user.id, name="P", description=None)
    for index in range(sample_count):
        create_project_sample(
            factory,
            project_id=project.id,
            user_id=user.id,
            payload=ProjectSampleCreate(
                sample_id=f"S{index}",
                smiles="CCO",
                nmr_text="1H NMR (400 MHz, CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
                solvent="CDCl3",
            ),
        )
    return user, project


def test_dashboard_query_count_does_not_scale_with_sample_count(tmp_path):
    factory = _factory(tmp_path)
    user, project = _seed(factory, sample_count=25)

    with _QueryCounter(factory) as counter:
        dashboard = build_project_dashboard(factory, project_id=project.id, user_id=user.id)

    assert dashboard is not None
    assert dashboard.sample_count == 25
    # Three audit queries (project / sample / analysis) plus the project, sample
    # and analysis loads. The precise floor is not the point — the point is that
    # it must not grow with the number of samples, which is what 101 queries was.
    assert counter.selects < 20, (
        f"{counter.selects} SELECTs for a 25-sample dashboard — the audit log is "
        "being queried per entity again"
    )


def test_dashboard_query_count_is_flat_as_samples_grow(tmp_path):
    """The shape of the bug, pinned: doubling the samples must not move the count."""
    small = create_session_factory(f"sqlite:///{tmp_path / 'small.sqlite3'}")
    init_db(small)
    u1, p1 = _seed(small, sample_count=5)
    with _QueryCounter(small) as c1:
        build_project_dashboard(small, project_id=p1.id, user_id=u1.id)

    big = create_session_factory(f"sqlite:///{tmp_path / 'big.sqlite3'}")
    init_db(big)
    u2, p2 = _seed(big, sample_count=40)
    with _QueryCounter(big) as c2:
        build_project_dashboard(big, project_id=p2.id, user_id=u2.id)

    assert c2.selects == c1.selects, (
        f"query count grew with sample count: {c1.selects} at 5 samples, "
        f"{c2.selects} at 40 — that is the per-entity N+1 returning"
    )
