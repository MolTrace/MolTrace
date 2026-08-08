"""Sources are superseded, never edited: add revisions and bind records to them

Revision ID: 0045_knowledge_source_revisions
Revises: 0044_model_artifact_registry_link
Create Date: 2026-08-08

Additive. New ``knowledge_source_revisions`` table; ``knowledge_sources`` gains
``current_revision_id``; the three extracted-record tables and
``extracted_citations`` each gain ``source_revision_id``.

The gap this closes: ``update_source`` wrote over the existing row. But
``publication_date``, ``doi`` and ``reliability_label`` are exactly the fields a
downstream extraction was justified by, so editing them in place left records
citing a source that now said something else, with nothing anywhere to reveal
that it had changed. A corpus that cannot show what a fact was justified by at
the time is not a provenance system.

Revision 1 IS backfilled, and that is deliberate: a snapshot of what each source
says right now is true today, and without it the first supersede would have no
predecessor to point at, losing the pre-change state at exactly the moment it
becomes interesting.

``source_revision_id`` on existing records is deliberately NOT backfilled.
Setting it to the backfilled revision 1 would assert that those records were
extracted from what the source says now -- unknowable, and most likely false
precisely where in-place editing already happened. NULL means "extracted before
revisions existed", and the supersede cascade treats NULL as a reason to flag a
record for review rather than to skip it: unknown provenance plus a changed
source is the case a human is most needed for.

Nullable throughout because this is a delta over rows that already exist, and
because a NOT NULL binding would force the false backfill above.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0045_knowledge_source_revisions"
down_revision = "0044_model_artifact_registry_link"
branch_labels = None
depends_on = None

_REVISIONS = "knowledge_source_revisions"
_SOURCES = "knowledge_sources"
_CURRENT = "current_revision_id"
_BINDING = "source_revision_id"
_BOUND_TABLES = (
    "extracted_reaction_records",
    "extracted_analytical_records",
    "extracted_regulatory_records",
    "extracted_citations",
)


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if _SOURCES not in tables:
        return

    if _REVISIONS not in tables:
        op.create_table(
            _REVISIONS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "source_id",
                sa.Integer(),
                sa.ForeignKey(f"{_SOURCES}.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("supersedes_revision_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("doi", sa.String(length=200), nullable=True),
            sa.Column("patent_number", sa.String(length=120), nullable=True),
            sa.Column("jurisdiction_id", sa.Integer(), nullable=True),
            sa.Column("publisher", sa.String(length=240), nullable=True),
            sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column(
                "reliability_label", sa.String(length=32), nullable=False, server_default="unknown"
            ),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("changed_fields_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("change_reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=200), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_knowledge_source_revisions_source", _REVISIONS, ["source_id", "revision_number"]
        )

    if _CURRENT not in _columns(inspector, _SOURCES):
        op.add_column(_SOURCES, sa.Column(_CURRENT, sa.Integer(), nullable=True))
        op.create_index(f"ix_{_SOURCES}_{_CURRENT}", _SOURCES, [_CURRENT])

    for table in _BOUND_TABLES:
        if table in tables and _BINDING not in _columns(inspector, table):
            op.add_column(table, sa.Column(_BINDING, sa.Integer(), nullable=True))
            op.create_index(f"ix_{table}_{_BINDING}", table, [_BINDING])

    # Revision 1 for every source that predates revisions: what it says today, recorded
    # so the next change has a predecessor to supersede instead of overwriting it.
    op.execute(
        sa.text(
            f"""
            INSERT INTO {_REVISIONS} (
                source_id, revision_number, supersedes_revision_id, title, source_type,
                source_url, doi, patent_number, jurisdiction_id, publisher, publication_date,
                status, reliability_label, metadata_json, changed_fields_json, change_reason
            )
            SELECT id, 1, NULL, title, source_type, source_url, doi, patent_number,
                   jurisdiction_id, publisher, publication_date, status, reliability_label,
                   COALESCE(metadata_json, '{{}}'), '[]',
                   'Recorded when source revisions were introduced.'
            FROM {_SOURCES}
            WHERE {_CURRENT} IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {_SOURCES}
               SET {_CURRENT} = (
                   SELECT r.id FROM {_REVISIONS} r
                    WHERE r.source_id = {_SOURCES}.id AND r.revision_number = 1
               )
             WHERE {_CURRENT} IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table in _BOUND_TABLES:
        if table in tables and _BINDING in _columns(inspector, table):
            op.drop_index(f"ix_{table}_{_BINDING}", table_name=table)
            op.drop_column(table, _BINDING)

    if _SOURCES in tables and _CURRENT in _columns(inspector, _SOURCES):
        op.drop_index(f"ix_{_SOURCES}_{_CURRENT}", table_name=_SOURCES)
        op.drop_column(_SOURCES, _CURRENT)

    if _REVISIONS in tables:
        op.drop_index("ix_knowledge_source_revisions_source", table_name=_REVISIONS)
        op.drop_table(_REVISIONS)
