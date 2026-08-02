"""What a collaboration record can be *about*, and who may act on it.

The collaboration layer — review tasks, and in time reviewers, comments, approvals, locks and
share links — was written when the only thing worth reviewing was a SpectraCheck session, so its
tables carry a required foreign key to one. That made team review a SpectraCheck-only feature:
Regentry could not say "someone look at this filing", and Repho could not say "someone check this
campaign", which is most of what a team does.

This module is the registry that makes those records address *any* of the three products. It
holds one entry per subject type: how to confirm the subject exists, and how to decide whether a
caller may act on it. Adding a fourth subject means adding one entry here, not a fourth copy of
the collaboration layer.

Authorization deliberately reuses each module's own rule rather than inventing a new one:

* ``spectracheck_session`` — the existing project-role model (owner / permissions / reviewers),
  which is richer than the others and stays untouched;
* ``regulatory_dossier`` — ``regulatory_intelligence.dossier_owned_by`` (creator or team);
* ``reaction_project`` — ``reaction_access.reaction_project_owned_by`` (owner or team).

So "may I act on this subject" is always the same question as "may I open this subject", answered
by the module that owns it. That is what keeps a review queue from ever showing — or accepting a
task against — something the caller cannot see.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from . import reaction_access, regulatory_intelligence
from .orm import ReactionProjectORM, RegulatoryDossierORM, SpectraCheckSessionORM

SubjectType = Literal["spectracheck_session", "regulatory_dossier", "reaction_project"]

SUBJECT_TYPES: tuple[SubjectType, ...] = (
    "spectracheck_session",
    "regulatory_dossier",
    "reaction_project",
)

#: Which product each subject belongs to, so a caller can be told plainly what a task is about.
SUBJECT_MODULE: dict[SubjectType, str] = {
    "spectracheck_session": "spectracheck",
    "regulatory_dossier": "regulatory_hub",
    "reaction_project": "reaction_optimization",
}

_SUBJECT_ORM = {
    "spectracheck_session": SpectraCheckSessionORM,
    "regulatory_dossier": RegulatoryDossierORM,
    "reaction_project": ReactionProjectORM,
}


class UnknownSubjectError(ValueError):
    """The subject type is not one this deployment knows how to address."""


def subject_exists(session: Session, subject_type: str, subject_id: int) -> bool:
    orm = _SUBJECT_ORM.get(subject_type)
    if orm is None:
        raise UnknownSubjectError(f"Unknown subject type: {subject_type}")
    return session.get(orm, subject_id) is not None


def can_access_subject(
    session: Session,
    subject_type: str,
    subject_id: int,
    *,
    owner_scope_id: int | None,
) -> bool:
    """Whether a caller scoped to ``owner_scope_id`` may act on this subject.

    ``owner_scope_id is None`` is an unrestricted caller (system api key or admin). A missing
    subject and one the caller cannot reach are both ``False``, so a route can map either to the
    same non-leaking 404 without disclosing which it was.
    """
    if subject_type not in _SUBJECT_ORM:
        raise UnknownSubjectError(f"Unknown subject type: {subject_type}")
    if not subject_exists(session, subject_type, subject_id):
        return False
    if owner_scope_id is None:
        return True
    if subject_type == "regulatory_dossier":
        return regulatory_intelligence.dossier_owned_by(session, subject_id, owner_scope_id)
    if subject_type == "reaction_project":
        return reaction_access.reaction_project_owned_by(session, subject_id, owner_scope_id)
    # SpectraCheck sessions carry the richer project-role model. Reaching it from here would mean
    # importing the collaboration store and creating a cycle, so the session-scoped routes keep
    # owning that decision and this registry only confirms the session exists — the generic route
    # refuses SpectraCheck subjects and points the caller at the session-scoped surface.
    return False


def is_generic_subject(subject_type: str) -> bool:
    """Whether the generic (subject-addressed) surface handles this type itself.

    SpectraCheck sessions are excluded: they already have a richer role-based review surface, and
    quietly accepting them here would create a second, weaker path to the same records.
    """
    return subject_type in {"regulatory_dossier", "reaction_project"}
