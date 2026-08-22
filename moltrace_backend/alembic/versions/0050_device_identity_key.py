"""Device identity key for offline entitlement statements

Revision ID: 0050_device_identity_key
Revises: 0049_hot_path_indexes
Create Date: 2026-08-22

Additive. A signed offline entitlement statement binds to a device's identity key; without a
column to hold it there is nothing for the statement to bind to, and device binding is the
anti-replay control (a nonce cannot be, because the statement must verify from local storage
across offline restarts).

Nullable and NOT backfilled, for 0043's reason: a device enrolled before this column existed has
no provable identity, and inventing one would assert something that never happened. NULL means
"predates offline enrolment" and is refused, never implicitly granted.

GUARDED, following 0043/0049: most mapped tables come from the ORM via create_all rather than
from a migration, so against an empty database this revision can be reached before the table
exists. On that path create_all builds the column anyway, since it is declared in orm.py.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0050_device_identity_key"
down_revision = "0049_hot_path_indexes"
branch_labels = None
depends_on = None

_TABLE = "mobile_device_sessions"
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("identity_public_key", sa.String(length=80)),
    ("identity_key_enrolled_at", sa.DateTime(timezone=True)),
)


def _existing(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return  # create_all builds it WITH these columns
    present = _existing(bind)
    for name, column_type in _COLUMNS:
        if name not in present:
            op.add_column(_TABLE, sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    present = _existing(bind)
    for name, _ in _COLUMNS:
        if name in present:
            op.drop_column(_TABLE, name)
