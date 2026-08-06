"""Persistence for spectral impurity observations — the SpectraCheck -> Regentry audit record.

**Scoped by the analysis owner, and only by that.** ``user_id`` is copied from the source analysis
at write time and is the sole authorizing column. ``reaction_project_id`` is provenance: reaction
projects widen to active organization members (``reaction_access.project_scope_predicate``) while
``analyses`` has no organization column, so scoping these rows by the project would expose a
compound name and chemical shift from a spectrum the reader cannot open. Any reaction-side reader
must gate on the INTERSECTION of both, never the union.

``user_id=None`` means an unrestricted caller (a system key), matching ``get_analysis_by_id``.
Missing and not-yours both return ``None`` so the route's 404 cannot leak existence.

Identity is re-derived server-side from the stored analysis by the pure resolver — never taken
from the caller, since a client-supplied compound name would let someone fabricate a regulatory
identity and the citation that comes with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .orm import AnalysisORM, SpectralImpurityObservationORM
from .spectral_impurity_q3c import resolve_observed_impurity

Nucleus = Literal["1H", "13C"]


@dataclass(frozen=True)
class SpectralImpurityObservationRecord:
    id: int
    analysis_id: int | None
    user_id: int | None
    reaction_project_id: int | None
    observed_shift_ppm: float
    solvent: str | None
    observed_label: str | None
    compound: str | None
    expected_ppm: float | None
    delta_ppm: float | None
    match_kind: str | None
    identity_status: str
    unresolved_reason: str | None
    unresolved_detail: str | None
    q3c_class_number: int | None
    q3c_class_description: str | None
    concentration_limit_ppm: float | None
    pde_mg_per_day: float | None
    regulatory_basis: str | None
    table_reference: str | None
    rule_set_version: str | None
    quantitation_available: bool
    observed_level_ppm: float | None
    compliance_note: str
    human_review_required: bool


def _to_record(row: SpectralImpurityObservationORM) -> SpectralImpurityObservationRecord:
    return SpectralImpurityObservationRecord(
        id=int(row.id),
        analysis_id=row.analysis_id,
        user_id=row.user_id,
        reaction_project_id=row.reaction_project_id,
        observed_shift_ppm=float(row.observed_shift_ppm),
        solvent=row.solvent,
        observed_label=row.observed_label,
        compound=row.compound,
        expected_ppm=row.expected_ppm,
        delta_ppm=row.delta_ppm,
        match_kind=row.match_kind,
        identity_status=row.identity_status,
        unresolved_reason=row.unresolved_reason,
        unresolved_detail=row.unresolved_detail,
        q3c_class_number=row.q3c_class_number,
        q3c_class_description=row.q3c_class_description,
        concentration_limit_ppm=row.concentration_limit_ppm,
        pde_mg_per_day=row.pde_mg_per_day,
        regulatory_basis=row.regulatory_basis,
        table_reference=row.table_reference,
        rule_set_version=row.rule_set_version,
        quantitation_available=bool(row.quantitation_available),
        observed_level_ppm=row.observed_level_ppm,
        compliance_note=row.compliance_note,
        human_review_required=bool(row.human_review_required),
    )


def _readable(row: SpectralImpurityObservationORM | None, user_id: int | None) -> bool:
    """Deliberately NOT ``row.user_id in {None, user_id}``.

    A NULL owner is an orphan, not a public record; treating it as world-readable is the trap in
    the neighbouring 2D-evidence reader. An unrestricted caller passes ``user_id=None``.
    """
    if row is None:
        return False
    return user_id is None or row.user_id == user_id


def record_spectral_impurity_observation(
    session_factory: sessionmaker[Session],
    *,
    analysis_id: int,
    nucleus: Nucleus,
    shift_ppm: float,
    solvent: str | None,
    route: str = "oral",
    reaction_project_id: int | None = None,
    user_id: int | None = None,
) -> SpectralImpurityObservationRecord | None:
    """Resolve a contaminant seen in a stored analysis and persist the observation.

    Returns ``None`` when the analysis does not exist *or* the caller may not read it — the same
    value for both, so a caller cannot probe for existence.
    """
    with session_scope(session_factory) as session:
        analysis = session.get(AnalysisORM, analysis_id)
        if analysis is None:
            return None
        if user_id is not None and analysis.user_id != user_id:
            return None

        resolution = resolve_observed_impurity(
            nucleus=nucleus, shift_ppm=shift_ppm, solvent=solvent, route=route
        )
        row = SpectralImpurityObservationORM(
            analysis_id=analysis.id,
            # Denormalized from the analysis, never from the caller: the record inherits the
            # source spectrum's scope rather than asserting its own.
            user_id=analysis.user_id,
            reaction_project_id=reaction_project_id,
            observed_shift_ppm=resolution.observed_shift_ppm,
            solvent=resolution.solvent,
            observed_label=resolution.observed_label,
            compound=resolution.compound,
            expected_ppm=resolution.expected_ppm,
            delta_ppm=resolution.delta_ppm,
            match_kind=resolution.match_kind,
            identity_status=resolution.identity_status,
            unresolved_reason=resolution.unresolved_reason,
            unresolved_detail=resolution.unresolved_detail,
            q3c_class_number=resolution.q3c_class_number,
            q3c_class_description=resolution.q3c_class_description,
            concentration_limit_ppm=resolution.concentration_limit_ppm,
            pde_mg_per_day=resolution.pde_mg_per_day,
            regulatory_basis=resolution.regulatory_basis,
            table_reference=resolution.table_reference,
            rule_set_version=resolution.rule_set_version,
            quantitation_available=resolution.quantitation_available,
            observed_level_ppm=resolution.observed_level_ppm,
            compliance_note=resolution.compliance_note,
            human_review_required=resolution.human_review_required,
        )
        session.add(row)
        session.flush()
        return _to_record(row)


def get_spectral_impurity_observation(
    session_factory: sessionmaker[Session],
    observation_id: int,
    *,
    user_id: int | None = None,
) -> SpectralImpurityObservationRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(SpectralImpurityObservationORM, observation_id)
        if not _readable(row, user_id):
            return None
        assert row is not None  # narrowed by _readable
        return _to_record(row)


def list_spectral_impurity_observations(
    session_factory: sessionmaker[Session],
    *,
    user_id: int | None = None,
    analysis_id: int | None = None,
    limit: int = 200,
) -> list[SpectralImpurityObservationRecord]:
    with session_scope(session_factory) as session:
        stmt = select(SpectralImpurityObservationORM)
        if user_id is not None:
            stmt = stmt.where(SpectralImpurityObservationORM.user_id == user_id)
        if analysis_id is not None:
            stmt = stmt.where(SpectralImpurityObservationORM.analysis_id == analysis_id)
        stmt = stmt.order_by(SpectralImpurityObservationORM.id.desc()).limit(limit)
        return [_to_record(row) for row in session.scalars(stmt).all()]
