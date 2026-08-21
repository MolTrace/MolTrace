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


def test_admin_user_list_counts_are_grouped_not_per_user(tmp_path):
    """The admin user page issued 1 + 2N queries — 201 at its default limit.

    Correctness matters as much as the count here: a grouped aggregate omits
    users with no rows entirely, so a naive rewrite silently drops them or
    mis-maps counts between users.
    """
    from nmrcheck.analysis import analyze_inputs
    from nmrcheck.database import list_admin_users, save_analysis
    from nmrcheck.models import AnalysisInputs

    factory = create_session_factory(f"sqlite:///{tmp_path / 'admin.sqlite3'}")
    init_db(factory)

    busy = create_user(factory, email="busy@example.com", password="correct-horse-1")
    # `busy` gets analyses; this one deliberately gets none.
    create_user(factory, email="quiet@example.com", password="correct-horse-2")

    for _ in range(3):
        payload = AnalysisInputs(
            smiles="CCO",
            nmr_text="1H NMR (400 MHz, CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
            solvent="CDCl3",
        )
        save_analysis(factory, analyze_inputs(payload), payload, user_id=busy.id)

    with _QueryCounter(factory) as counter:
        rows = list_admin_users(factory, limit=100)

    by_email = {row.email: row for row in rows}
    assert by_email["busy@example.com"].analyses_count == 3
    # The user with no analyses must appear with a zero, not vanish and not
    # inherit another user's count.
    assert by_email["quiet@example.com"].analyses_count == 0
    assert by_email["quiet@example.com"].jobs_count == 0
    assert counter.selects <= 5, (
        f"{counter.selects} SELECTs for 2 users — the per-user counts are back"
    )


def test_sample_timeline_does_not_open_a_session_per_analysis(tmp_path):
    """The timeline looped over analyses, querying decisions AND audit events
    for each — 2N sessions with no cap on N."""
    from nmrcheck.analysis import analyze_inputs
    from nmrcheck.database import get_sample_timeline, save_analysis
    from nmrcheck.models import AnalysisInputs, ProjectSampleCreate

    factory = create_session_factory(f"sqlite:///{tmp_path / 'timeline.sqlite3'}")
    init_db(factory)
    user = create_user(factory, email="tl@example.com", password="correct-horse-1")
    project = create_project(factory, user_id=user.id, name="P", description=None)

    analysis_id = None
    for index in range(6):
        payload = AnalysisInputs(
            smiles="CCO",
            nmr_text="1H NMR (400 MHz, CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
            solvent="CDCl3",
        )
        stored_id = save_analysis(factory, analyze_inputs(payload), payload, user_id=user.id)
        if index == 0:
            analysis_id = stored_id
        create_project_sample(
            factory,
            project_id=project.id,
            user_id=user.id,
            payload=ProjectSampleCreate(
                sample_id="S-1",
                smiles="CCO",
                nmr_text="1H NMR (400 MHz, CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
                solvent="CDCl3",
                analysis_id=analysis_id if index == 0 else None,
            ),
        )

    with _QueryCounter(factory) as counter:
        timeline = get_sample_timeline(factory, user_id=user.id, sample_identity="S-1")

    assert timeline is not None
    assert counter.selects < 20, (
        f"{counter.selects} SELECTs for a 6-analysis timeline — the per-analysis "
        "decision/audit loop is back"
    )
