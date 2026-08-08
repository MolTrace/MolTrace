"""Link a model artifact to the registry entry the inference router resolves

Revision ID: 0044_model_artifact_registry_link
Revises: 0043_managed_file_ownership
Create Date: 2026-08-08

Additive. ``model_artifacts`` gains ``registry_model_id``.

The gap this closes: ``InferenceRouter`` resolves what to serve from
``moltrace.spectroscopy.ai.registry`` -- its own append-only tables, keyed by
(role, nucleus) with a separate status log. Nothing in the product ever wrote
them. So approving a deployment candidate in ``/ml/*`` flipped a row's status
and changed **nothing** about which artifact the router actually used. The
governance surface and the serving path were two disconnected systems that both
called their subject "the deployed model".

Deliberately a link, not a merge. The obvious alternative -- point the registry
store at ``model_artifacts`` and delete one of the two tables -- would cost the
property that makes the registry worth having: entries are immutable and
lifecycle changes are *appended*, so a promotion is reconstructable and a
retirement cannot be edited away. ``model_artifacts.status`` is a mutable
column. Merging them would either destroy the append-only guarantee or require
rewriting a table 35 routes read. The link keeps each side's semantics and makes
the join explicit.

Nullable on purpose, and NOT backfilled. NULL means "approved for the product
surface, not promoted to serving" -- which is the truthful state of every
artifact approved before this existed, since none of them was ever registered.
Backfilling would assert that models had been serving traffic when they had not,
in exactly the records where provenance is the point.

Unique because a registry entry is a single artifact version. Two rows claiming
the same ``model_id`` would make "which artifact is production for this role"
ambiguous at the moment the router asks.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0044_model_artifact_registry_link"
down_revision = "0043_managed_file_ownership"
branch_labels = None
depends_on = None

_TABLE = "model_artifacts"
_COLUMN = "registry_model_id"
_INDEX = "ix_model_artifacts_registry_model_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=512), nullable=True))
    op.create_index(_INDEX, _TABLE, [_COLUMN], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
