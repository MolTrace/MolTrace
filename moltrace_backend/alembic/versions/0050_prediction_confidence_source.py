"""Record whether a prediction's confidence came from an engine or from the caller.

A confidence figure a client sent in ``request_json`` is not evidence the platform computed
anything, and until now nothing stored beside the number said which it was. Services with no
engine wired read their confidence straight out of the request, so an audit reading
``confidence_score`` back out could not distinguish a measured figure from an asserted one.

Nullable with no backfill, deliberately: rows written before this column existed genuinely do
not carry the fact, and inventing a value for them would assert provenance nobody recorded.
NULL reads as "not recorded", which is what it is.

Revision ID: 0050_prediction_confidence_source
Revises: 0049_hot_path_indexes
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0050_prediction_confidence_source"
down_revision = "0049_hot_path_indexes"
branch_labels = None
depends_on = None

_TABLES = ("prediction_runs", "prediction_results")


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(table_name))


def upgrade() -> None:
    # These migrations are Postgres deltas over an ORM-created schema, so a database the app
    # has just bootstrapped already has the column. Guarded both ways rather than assuming.
    for table in _TABLES:
        if _table_exists(table) and not _has_column(table, "confidence_source"):
            op.add_column(
                table, sa.Column("confidence_source", sa.String(length=32), nullable=True)
            )


def downgrade() -> None:
    for table in _TABLES:
        if _table_exists(table) and _has_column(table, "confidence_source"):
            op.drop_column(table, "confidence_source")
