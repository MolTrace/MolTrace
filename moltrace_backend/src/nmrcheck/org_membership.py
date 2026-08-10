"""Resolving which organizations a user actively belongs to.

Ownership in MolTrace started per-user, which is right for a single analyst and wrong for every
regulated workflow: a filing is worked by a reviewer, a toxicologist and a QA lead, and a campaign
by a process-chemistry team. This module is the shared membership lookup those team-scoped access
checks funnel through, so "who is on this team" has one answer rather than one per module.

Membership lives on ``team_members``, keyed by **email** rather than user id, so a user id has to
be resolved to an email first. Only ``status == "active"`` counts — an invited-but-not-accepted or
a disabled member is not a member.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .orm import TeamMemberORM, UserORM


def email_for_user(session: Session, user_id: int | None) -> str | None:
    """The normalized email for ``user_id``, or ``None`` if there is no such user."""
    if user_id is None:
        return None
    row = session.get(UserORM, user_id)
    if row is None or not row.email:
        return None
    return row.email.strip().lower()


def active_org_ids_for_email(session: Session, email: str | None) -> set[int]:
    """Organization ids where ``email`` is an *active* member."""
    if not email:
        return set()
    rows = session.scalars(
        select(TeamMemberORM.organization_id)
        .where(TeamMemberORM.user_email == email.strip().lower())
        .where(TeamMemberORM.status == "active")
    ).all()
    return {int(row) for row in rows}


def active_org_ids_for_user(session: Session, user_id: int | None) -> set[int]:
    """Organization ids where ``user_id`` is an active member."""
    return active_org_ids_for_email(session, email_for_user(session, user_id))


def sole_active_org_id(session: Session, user_id: int | None) -> int | None:
    """The user's organization when they have exactly one active membership, else ``None``.

    Used to stamp ownership at create time. Deliberately conservative: with no membership there is
    no team to share with, and with several there is no way to tell which one a new record belongs
    to, so both cases fall back to creator-only ownership rather than guessing and over-sharing.
    """
    org_ids = active_org_ids_for_user(session, user_id)
    return next(iter(org_ids)) if len(org_ids) == 1 else None


def user_shares_org(session: Session, user_id: int | None, organization_id: int | None) -> bool:
    """Whether ``user_id`` is an active member of ``organization_id``."""
    if organization_id is None or user_id is None:
        return False
    return organization_id in active_org_ids_for_user(session, user_id)


def active_member_user_ids(session: Session, org_ids: set[int] | frozenset[int]) -> set[int]:
    """User ids of every *active* member of any organization in ``org_ids``.

    The inverse direction of :func:`active_org_ids_for_user`: given the teams a caller is on,
    who are their colleagues. Needed where the access rule is stated over *people* rather than
    over a record's stamped ``organization_id`` — a FID run has no organization column, so
    "runs my colleagues produced" has to be resolved through the authors.

    ``team_members`` is keyed by email and ``users.email`` is not guaranteed normalized, so the
    join is on lowered email on both sides — the same normalization :func:`email_for_user` and
    :func:`active_org_ids_for_email` already apply, kept here rather than at each call site so
    a membership lookup cannot silently miss a mixed-case address.
    """
    if not org_ids:
        return set()
    rows = session.execute(
        select(UserORM.id)
        .join(
            TeamMemberORM,
            func.lower(func.trim(TeamMemberORM.user_email)) == func.lower(func.trim(UserORM.email)),
        )
        .where(TeamMemberORM.status == "active")
        .where(TeamMemberORM.organization_id.in_(sorted(int(o) for o in org_ids)))
    ).all()
    return {int(row[0]) for row in rows}


def colleague_user_ids(session: Session, user_id: int | None) -> set[int]:
    """Everyone who shares at least one active organization with ``user_id``, including them.

    Returns an empty set when the user is on no team — a solo account has no colleagues, so
    every team-scoped rule built on this correctly grants nothing rather than everything.
    """
    if user_id is None:
        return set()
    org_ids = active_org_ids_for_user(session, user_id)
    if not org_ids:
        return set()
    return active_member_user_ids(session, org_ids)
