"""``create_all`` in ``init_db`` is the schema mechanism, not a dev convenience.

It is an obvious-looking performance target: ``Base.metadata.create_all`` issues
one existence probe PER TABLE — 271 of them, measured — and ``init_db`` runs on
every process start, so on Cloud SQL that is roughly 0.3-0.8 s of serialized
network before an instance accepts traffic, repeated on every autoscale-out.
Two plausible ways to remove it both break production, and this file exists to
say so before someone (again) tries:

* Gating on ``APP_ENV != "production"`` breaks a FRESH database. Alembic here is
  a set of Postgres deltas over an ORM-created schema, so a new database is
  bootstrapped by this call and then stamped — migrations cannot bootstrap it.

* Gating on EMPTINESS (skip when a sentinel table already exists) breaks an
  EXISTING database, which is the subtler and worse failure. Most of this
  schema has never had a ``create_table`` migration: those tables reach
  production only because ``create_all`` runs on every start. Freeze that and
  the next release to add a table silently ships without it, failing at the
  first request that touches it rather than at deploy time.

If the startup cost is ever worth attacking, the honest routes are to give the
un-migrated tables real migrations first, or to move the probe off the critical
path — not to make the call conditional.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import event, inspect

from nmrcheck.database import create_session_factory, init_db
from nmrcheck.orm import Base

_MIGRATIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _tables_created_by_migrations() -> set[str]:
    created: set[str] = set()
    for path in _MIGRATIONS.glob("*.py"):
        created.update(
            match.group(1)
            for match in re.finditer(
                r"""create_table\(\s*["']([a-z0-9_]+)["']""", path.read_text(encoding="utf-8")
            )
        )
    return created


def test_most_tables_exist_only_because_create_all_runs() -> None:
    """The measurement behind the docstring, kept live.

    If this ever inverts — every mapped table having a creating migration —
    then gating create_all becomes a real option and this test should be
    revisited deliberately rather than deleted in passing.
    """
    mapped = set(Base.metadata.tables)
    migrated = _tables_created_by_migrations() & mapped
    unmigrated = mapped - migrated

    assert len(unmigrated) > len(migrated), (
        "most mapped tables now have creating migrations "
        f"({len(migrated)} migrated vs {len(unmigrated)} not) — the premise that "
        "create_all is load-bearing may no longer hold; re-derive it before acting"
    )


def test_create_all_is_called_unconditionally() -> None:
    """No emptiness/APP_ENV gate may creep back in front of the bootstrap."""
    source = (
        Path(__file__).resolve().parents[1] / "src" / "nmrcheck" / "database.py"
    ).read_text(encoding="utf-8")
    body = source.split("def init_db(", 1)[1].split("\ndef ", 1)[0]
    call_line = next(
        line for line in body.splitlines() if "Base.metadata.create_all" in line
    )
    indent = len(call_line) - len(call_line.lstrip())
    assert indent == 4, (
        "Base.metadata.create_all is nested inside a conditional in init_db. "
        "See this module's docstring: most tables have no creating migration, so "
        "skipping it strands them on an existing database."
    )


def test_a_fresh_database_is_bootstrapped(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'fresh.sqlite3'}")
    init_db(factory)
    tables = set(inspect(factory.kw["bind"]).get_table_names())
    for table in ("users", "analyses", "audit_events", "projects"):
        assert table in tables, f"{table} was not created on a fresh database"


def test_init_db_is_idempotent(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'idem.sqlite3'}")
    init_db(factory)
    init_db(factory)
    tables = set(inspect(factory.kw["bind"]).get_table_names())
    assert {"users", "analyses"} <= tables


def test_the_startup_cost_is_recorded_not_forgotten(tmp_path) -> None:
    """Pins the number the docstring cites, so it stays honest."""
    factory = create_session_factory(f"sqlite:///{tmp_path / 'cost.sqlite3'}")
    init_db(factory)
    engine = factory.kw["bind"]

    counted = [0]

    def before(_conn, _cursor, _statement, *_args):
        counted[0] += 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        Base.metadata.create_all(engine)
    finally:
        event.remove(engine, "before_cursor_execute", before)

    # One probe per mapped table on an already-built schema.
    assert counted[0] >= len(Base.metadata.tables) * 0.9, (
        f"{counted[0]} probes for {len(Base.metadata.tables)} tables — the cost "
        "this file documents has changed shape; re-measure before relying on it"
    )
