"""A development database that predates the subject-addressing migrations still works.

Migrations 0035/0036 make ``session_id`` optional so a review task or a comment can be raised
against a filing or a campaign rather than a spectroscopy session. On PostgreSQL that is one
``ALTER COLUMN``; on SQLite it is impossible, so both migrations skip it there and rely on
``_ensure_sqlite_schema`` to bring pre-existing development databases forward.

That backfill only *added* the two subject columns. A dev database created before the migrations
therefore kept ``session_id NOT NULL``, and every subject-addressed insert — which has no session
by definition — died on an IntegrityError that the API could only report as an unavailable
service. The feature's own tests all passed, because they build the schema fresh from the ORM,
where the column is already nullable. Only a *pre-existing* database was broken, which is exactly
the database a developer runs against.

These tests reconstruct that legacy shape verbatim and assert the backfill repairs it without
losing what the table already held.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from nmrcheck.database import init_db

# The pre-0035/0036 schema, copied from a real development database: ``session_id`` required, no
# subject columns, no subject index.
_LEGACY_REVIEW_TASKS = """
CREATE TABLE review_tasks (
	id INTEGER NOT NULL,
	session_id INTEGER NOT NULL,
	title VARCHAR(300) NOT NULL,
	description TEXT,
	assigned_to VARCHAR(255),
	status VARCHAR(32) NOT NULL,
	priority VARCHAR(32) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	metadata_json TEXT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(session_id) REFERENCES spectracheck_sessions (id) ON DELETE CASCADE
)
"""
_LEGACY_REVIEW_TASK_INDEXES = (
    "CREATE INDEX ix_review_tasks_assigned_to ON review_tasks (assigned_to)",
    "CREATE INDEX ix_review_tasks_assignee_status ON review_tasks (assigned_to, status)",
    "CREATE INDEX ix_review_tasks_priority ON review_tasks (priority)",
    "CREATE INDEX ix_review_tasks_session_id ON review_tasks (session_id)",
    "CREATE INDEX ix_review_tasks_session_status ON review_tasks (session_id, status)",
    "CREATE INDEX ix_review_tasks_status ON review_tasks (status)",
)

_LEGACY_EVIDENCE_COMMENTS = """
CREATE TABLE evidence_comments (
	id INTEGER NOT NULL,
	session_id INTEGER NOT NULL,
	evidence_id INTEGER,
	artifact_id INTEGER,
	author_email VARCHAR(255),
	comment TEXT NOT NULL,
	comment_type VARCHAR(32) NOT NULL,
	resolved BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	metadata_json TEXT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(session_id) REFERENCES spectracheck_sessions (id) ON DELETE CASCADE,
	FOREIGN KEY(evidence_id) REFERENCES spectracheck_evidence_records (id) ON DELETE SET NULL,
	FOREIGN KEY(artifact_id) REFERENCES artifact_records (id) ON DELETE SET NULL
)
"""
_LEGACY_EVIDENCE_COMMENT_INDEXES = (
    "CREATE INDEX ix_evidence_comments_artifact_created ON evidence_comments (artifact_id, created_at)",
    "CREATE INDEX ix_evidence_comments_artifact_id ON evidence_comments (artifact_id)",
    "CREATE INDEX ix_evidence_comments_author_email ON evidence_comments (author_email)",
    "CREATE INDEX ix_evidence_comments_comment_type ON evidence_comments (comment_type)",
    "CREATE INDEX ix_evidence_comments_evidence_created ON evidence_comments (evidence_id, created_at)",
    "CREATE INDEX ix_evidence_comments_evidence_id ON evidence_comments (evidence_id)",
    "CREATE INDEX ix_evidence_comments_resolved ON evidence_comments (resolved)",
    "CREATE INDEX ix_evidence_comments_session_created ON evidence_comments (session_id, created_at)",
    "CREATE INDEX ix_evidence_comments_session_id ON evidence_comments (session_id)",
)

# One session-addressed row per table, as a developer's database would already hold. Foreign keys
# are off (SQLite's default, which this codebase never changes), so no parent row is needed.
_LEGACY_TASK_ROW = """
INSERT INTO review_tasks
    (id, session_id, title, description, assigned_to, status, priority,
     created_at, updated_at, metadata_json)
VALUES (901, 77, 'Check the integration', 'From before the migration', 'reviewer@example.com',
        'open', 'high', '2026-01-01 00:00:00', '2026-01-02 00:00:00', '{"origin":"legacy"}')
"""
_LEGACY_COMMENT_ROW = """
INSERT INTO evidence_comments
    (id, session_id, evidence_id, artifact_id, author_email, comment, comment_type, resolved,
     created_at, updated_at, metadata_json)
VALUES (902, 77, NULL, NULL, 'author@example.com', 'From before the migration', 'note', 0,
        '2026-01-01 00:00:00', '2026-01-02 00:00:00', '{"origin":"legacy"}')
"""

_TABLES = ("review_tasks", "evidence_comments")


def _regress_to_legacy(session_factory: sessionmaker[Session]) -> None:
    """Put both collaboration tables back the way a pre-migration database has them."""
    engine = session_factory.kw["bind"]
    with engine.begin() as connection:
        for table in _TABLES:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
        connection.exec_driver_sql(_LEGACY_REVIEW_TASKS)
        for statement in _LEGACY_REVIEW_TASK_INDEXES:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(_LEGACY_EVIDENCE_COMMENTS)
        for statement in _LEGACY_EVIDENCE_COMMENT_INDEXES:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(_LEGACY_TASK_ROW)
        connection.exec_driver_sql(_LEGACY_COMMENT_ROW)


def _schema(session_factory: sessionmaker[Session], table: str) -> dict:
    engine = session_factory.kw["bind"]
    with engine.begin() as connection:
        info = connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        indexes = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (table,),
        ).fetchall()
        return {
            "columns": [str(row[1]) for row in info],
            "session_id_required": any(
                str(row[1]) == "session_id" and int(row[3]) for row in info
            ),
            "indexes": sorted(str(row[0]) for row in indexes),
            "foreign_keys": sorted(
                connection.exec_driver_sql(f"PRAGMA foreign_key_list({table})").fetchall()
            ),
            "rows": connection.exec_driver_sql(f"SELECT * FROM {table} ORDER BY id").fetchall(),
        }


@pytest.fixture()
def legacy_app(app):
    """The app fixture's database, regressed to the pre-migration shape and reopened.

    The second ``init_db`` is the part under test: it stands in for a developer restarting the
    backend against a database they already had.
    """
    _regress_to_legacy(app.state.session_factory)
    assert _schema(app.state.session_factory, "review_tasks")["session_id_required"]
    init_db(app.state.session_factory)
    return app


# --------------------------------------------------------------------------- #
# The repair itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("table", _TABLES)
def test_a_session_stops_being_required(legacy_app, table: str):
    assert not _schema(legacy_app.state.session_factory, table)["session_id_required"]


@pytest.mark.parametrize("table", _TABLES)
def test_the_subject_columns_and_their_index_arrive(legacy_app, table: str):
    schema = _schema(legacy_app.state.session_factory, table)
    assert {"subject_type", "subject_id"} <= set(schema["columns"])
    assert f"ix_{table}_subject" in schema["indexes"]


_LEGACY_ROW_VALUES = {
    # Every column the legacy table had, in its own order; the two subject columns are appended
    # by the backfill and are NULL on a row that predates them.
    "review_tasks": (
        901, 77, "Check the integration", "From before the migration", "reviewer@example.com",
        "open", "high", "2026-01-01 00:00:00", "2026-01-02 00:00:00", '{"origin":"legacy"}',
    ),
    "evidence_comments": (
        902, 77, None, None, "author@example.com", "From before the migration", "note", 0,
        "2026-01-01 00:00:00", "2026-01-02 00:00:00", '{"origin":"legacy"}',
    ),
}


@pytest.mark.parametrize("table", _TABLES)
def test_the_rebuild_keeps_the_rows_the_table_already_held(legacy_app, table: str):
    """Rebuilding a table is a copy, not a reset: a developer's history has to survive it."""
    expected = _LEGACY_ROW_VALUES[table]
    rows = _schema(legacy_app.state.session_factory, table)["rows"]
    assert len(rows) == 1
    assert rows[0] == expected + (None, None)


@pytest.mark.parametrize("table", _TABLES)
def test_the_rebuild_keeps_the_indexes_and_foreign_keys(legacy_app, table: str):
    """Dropping the table drops its indexes; they have to be put back, or every lookup that used
    one silently degrades to a scan."""
    schema = _schema(legacy_app.state.session_factory, table)
    legacy_indexes = {
        statement.split()[2]
        for statement in (
            _LEGACY_REVIEW_TASK_INDEXES
            if table == "review_tasks"
            else _LEGACY_EVIDENCE_COMMENT_INDEXES
        )
    }
    assert legacy_indexes <= set(schema["indexes"])
    # ON DELETE behaviour is part of the contract and is easy to lose in a hand-written rebuild.
    assert schema["foreign_keys"], "the rebuilt table kept no foreign keys at all"
    assert {(row[2], row[3], row[6]) for row in schema["foreign_keys"]} == (
        {("spectracheck_sessions", "session_id", "CASCADE")}
        if table == "review_tasks"
        else {
            ("spectracheck_sessions", "session_id", "CASCADE"),
            ("spectracheck_evidence_records", "evidence_id", "SET NULL"),
            ("artifact_records", "artifact_id", "SET NULL"),
        }
    )


@pytest.mark.parametrize("table", _TABLES)
def test_reopening_an_already_repaired_database_changes_nothing(legacy_app, table: str):
    """The backfill runs on every start-up, so a repeat must not rebuild the table again."""
    before = _schema(legacy_app.state.session_factory, table)
    init_db(legacy_app.state.session_factory)
    assert _schema(legacy_app.state.session_factory, table) == before


# --------------------------------------------------------------------------- #
# What the repair is for
# --------------------------------------------------------------------------- #
def _dossier(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={"title": "Filing", "product_name": "Example", "intended_use": "Decision support"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_a_filing_can_carry_a_review_task_on_a_pre_existing_database(legacy_app, api_headers):
    """The end-to-end failure this repairs: an IntegrityError surfacing as HTTP 503."""
    client = TestClient(legacy_app)
    with client:
        dossier = _dossier(client, api_headers)
        created = client.post(
            "/review-tasks",
            headers=api_headers,
            json={"subject_type": "regulatory_dossier", "subject_id": dossier["id"], "title": "x"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["session_id"] is None
        assert created.json()["subject_type"] == "regulatory_dossier"


def test_a_filing_can_carry_a_comment_on_a_pre_existing_database(legacy_app, api_headers):
    client = TestClient(legacy_app)
    with client:
        dossier = _dossier(client, api_headers)
        created = client.post(
            "/comments",
            headers=api_headers,
            json={
                "subject_type": "regulatory_dossier",
                "subject_id": dossier["id"],
                "comment": "Looks fine to me",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["session_id"] is None
