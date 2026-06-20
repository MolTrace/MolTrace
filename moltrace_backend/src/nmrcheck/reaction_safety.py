"""Predictive process-safety screening for the Repho reaction optimizer (R6, engine slice).

Structural screening for energetic / reactive functional groups via RDKit SMARTS, with a
conservative risk tier and an always-on expert-review gate. Decision-support ONLY — never
the sole basis for a safety decision; anything flagged medium or above (and any energetic
group) requires a qualified process-safety professional and a formal Process Hazard
Analysis (PHA) before execution.

The hazard motifs below are well-known explosophore / reactive classes encoded from public
GHS and structural-chemistry knowledge — NOT the copyrighted Bretherick's compiled dataset.
Quantitative predictions (exothermicity, gas evolution, DSC onset) are deliberately out of
this slice; they require thermochemical data and land in a follow-up.

The screening functions (``screen_smiles`` / ``screen_reaction``) are pure RDKit/stdlib and
deterministic. A thin persistence/store layer below adds the ORM access needed for the
human-in-the-loop review gate (persist a screen, record an expert verdict, report whether the
project is blocked) — it does not touch the screening math.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ReactionSafetyGateStatus,
    ReactionSafetyReviewRequest,
    ReactionSafetyScreening,
    ReactionSafetyScreenRequest,
)
from .orm import (
    AuditEventORM,
    ReactionProjectORM,
    ReactionSafetyScreeningORM,
    utcnow,
)
from .reaction_store import ReactionActor, ReactionError

_DISCLAIMER = (
    "Decision-support only; NOT a safety determination and never the sole basis for one. "
    "Any reaction flagged medium or above, and any energetic or reactive group, requires "
    "review by a qualified process-safety professional and a formal Process Hazard Analysis "
    "(PHA) before execution."
)
_SCREEN_VERSION = "reaction_safety.v1"

# (key, label, SMARTS, severity, mitigation note). Severity in {critical, high, medium}.
_ENERGETIC_GROUPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("azide", "Organic azide", "[NX2,NX1]=[N+]=[N-]", "critical",
     "Shock/heat/friction-sensitive; avoid heavy-metal contact; keep dilute and cold."),
    ("organic_peroxide", "Organic peroxide / hydroperoxide", "[OX2][OX2]", "critical",
     "Peroxide-forming/explosive; test for peroxides, avoid concentration to dryness."),
    ("peroxy_acid", "Peroxy acid", "[CX3](=[OX1])[OX2][OX2H1,OX2H0]", "critical",
     "Strong oxidizer, shock/heat-sensitive; keep cold and dilute."),
    ("diazo", "Diazo compound", "[CX3,CX2]=[N+]=[N-]", "critical",
     "Highly energetic and toxic; generate in situ, keep cold, avoid accumulation."),
    ("diazonium", "Diazonium salt", "[#6]-[NX2+]#[NX1]", "critical",
     "Explosive when dry; keep in solution, cold, never isolate dry."),
    ("nitrate_ester", "Nitrate ester", "[#6][OX2][NX3+](=[OX1])[O-]", "critical",
     "Explosive; avoid heat, shock, and acid."),
    ("perchlorate", "Perchlorate", "[Cl](=O)(=O)(=O)[O-,OX2H1,OX2]", "critical",
     "Strong oxidizer; explosive with organics/heavy metals."),
    ("fulminate", "Fulminate", "[C-]#[N+][O-]", "critical",
     "Primary explosive; extreme shock sensitivity."),
    ("nitro", "Nitro group", "[$([NX3](=O)=O),$([NX3+](=O)[O-])]", "high",
     "Energetic, especially poly-nitro / electron-poor arenes; assess thermal stability."),
    ("nitroso", "Nitroso / N-nitroso", "[#6,#7][NX2]=[OX1]", "high",
     "Reactive and frequently mutagenic (cf. nitrosamine control); minimize and contain."),
    ("azo", "Azo compound", "[#6][NX2]=[NX2][#6]", "high",
     "Gas-evolving (N2) on decomposition; can be energetic — control temperature."),
    ("tetrazole", "Tetrazole", "[$(c1nnnn1),$(C1=NN=NN1),$([NX3]1[NX2]=[NX2][NX2]=[CX3]1)]", "high",
     "High nitrogen content; energetic, particularly when substituted with other explosophores."),
    ("n_oxide", "Amine N-oxide", "[$([NX4+][OX1-]),$([nX3+][OX1-])]", "medium",
     "Can be a peroxide/oxidant source; assess thermal stability on scale."),
    ("hydrazine", "Hydrazine / hydrazide", "[NX3;!$(N=*)][NX3;!$(N=*)]", "medium",
     "Reducing and potentially energetic/toxic; handle with engineering controls."),
)

_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _load_rdkit():
    try:
        from rdkit import Chem  # noqa: PLC0415

        return Chem
    except Exception:  # pragma: no cover - rdkit is a hard dependency
        return None


def _compiled_groups(chem) -> list[tuple[str, str, str, str, str, Any]]:
    compiled = []
    for key, label, smarts, severity, note in _ENERGETIC_GROUPS:
        pattern = chem.MolFromSmarts(smarts)
        if pattern is not None:
            compiled.append((key, label, smarts, severity, note, pattern))
    return compiled


def _worst(severities: list[str]) -> str:
    if not severities:
        return "low"
    return max(severities, key=lambda s: _RANK.get(s, 0))


def screen_smiles(smiles: str | None) -> dict[str, Any]:
    """Screen one structure for energetic/reactive groups.

    Returns ``{smiles, parsed, flagged_groups[], overall_risk, requires_expert_review,
    disclaimer, screen_version}``. A missing/unparseable SMILES yields ``parsed=False`` and
    ``requires_expert_review=True`` (fail safe — never silently 'clear' an unknown structure).
    """
    chem = _load_rdkit()
    if not smiles or chem is None:
        return {
            "smiles": smiles,
            "parsed": False,
            "flagged_groups": [],
            "overall_risk": "unknown",
            "requires_expert_review": True,
            "disclaimer": _DISCLAIMER,
            "screen_version": _SCREEN_VERSION,
        }
    mol = chem.MolFromSmiles(smiles)
    if mol is None:
        return {
            "smiles": smiles,
            "parsed": False,
            "flagged_groups": [],
            "overall_risk": "unknown",
            "requires_expert_review": True,
            "disclaimer": _DISCLAIMER,
            "screen_version": _SCREEN_VERSION,
        }
    flagged: list[dict[str, Any]] = []
    for key, label, _smarts, severity, note, pattern in _compiled_groups(chem):
        matches = mol.GetSubstructMatches(pattern)
        if matches:
            flagged.append(
                {
                    "key": key,
                    "label": label,
                    "severity": severity,
                    "count": len(matches),
                    "mitigation": note,
                }
            )
    # Escalation: multiple independent nitro groups (poly-nitro) are notably more energetic.
    nitro = next((f for f in flagged if f["key"] == "nitro"), None)
    if nitro is not None and nitro["count"] >= 2:
        nitro["severity"] = "critical"
        nitro["mitigation"] = "Poly-nitro motif — treat as high-energy; mandatory PHA before use."
    overall = _worst([f["severity"] for f in flagged])
    return {
        "smiles": smiles,
        "parsed": True,
        "flagged_groups": flagged,
        "overall_risk": overall,
        "requires_expert_review": overall != "low",
        "disclaimer": _DISCLAIMER,
        "screen_version": _SCREEN_VERSION,
    }


def screen_reaction(
    *,
    reactant_smiles: list[str] | None = None,
    product_smiles: str | None = None,
    reagent_smiles: list[str] | None = None,
) -> dict[str, Any]:
    """Screen every species in a reaction and aggregate to an overall verdict.

    ``overall_risk`` is the worst across species; ``requires_expert_review`` is True if any
    species is flagged, any SMILES fails to parse, or no structures were provided (fail safe).
    """
    species: list[dict[str, Any]] = []

    def _add(role: str, smiles: str) -> None:
        result = screen_smiles(smiles)
        result["role"] = role
        species.append(result)

    for smiles in reactant_smiles or []:
        _add("reactant", smiles)
    for smiles in reagent_smiles or []:
        _add("reagent", smiles)
    if product_smiles:
        _add("product", product_smiles)

    risks = [s["overall_risk"] for s in species if s["overall_risk"] != "unknown"]
    overall = _worst(risks) if risks else "low"
    any_unparsed = any(not s["parsed"] for s in species)
    any_flagged = any(s["flagged_groups"] for s in species)
    return {
        "species": species,
        "overall_risk": "unknown" if (not species) else overall,
        "requires_expert_review": (not species) or any_unparsed or any_flagged or overall != "low",
        "energetic_groups_found": sorted(
            {f["key"] for s in species for f in s["flagged_groups"]}
        ),
        "disclaimer": _DISCLAIMER,
        "screen_version": _SCREEN_VERSION,
    }


# --------------------------------------------------------------------------------------
# Persistence / store layer (R6 wiring): persist a screen + a human-in-the-loop verdict,
# and report a fail-safe project gate. The screening math above stays import-pure.
# --------------------------------------------------------------------------------------

import json  # noqa: E402  (kept beside the store layer it serves)

# A screening still awaiting a decision, or one a reviewer rejected, blocks the project gate.
_BLOCKING_REVIEW_STATES = ("pending", "rejected")


def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {}, sort_keys=True, separators=(",", ":"), default=str
    )


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _project_or_raise(session: Session, project_id: int) -> ReactionProjectORM:
    row = session.get(ReactionProjectORM, project_id)
    if row is None:
        raise KeyError("Reaction project not found.")
    return row


def _audit(
    session: Session,
    *,
    actor: ReactionActor,
    event_type: str,
    message: str,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type="reaction_safety_screening",
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _screening_to_record(row: ReactionSafetyScreeningORM) -> ReactionSafetyScreening:
    return ReactionSafetyScreening(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        label=row.label or None,
        overall_risk=row.overall_risk,
        requires_expert_review=row.requires_expert_review,
        review_status=row.review_status,
        review_note=row.review_note or None,
        reviewed_by_user_id=row.reviewed_by_user_id,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        input_json=_json_dict(row.input_json),
        result_json=_json_dict(row.result_json),
        disclaimer=_DISCLAIMER,
        metadata_json=_json_dict(row.metadata_json),
    )


def create_screening(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionSafetyScreenRequest,
    *,
    actor: ReactionActor,
) -> ReactionSafetyScreening:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        result = screen_reaction(
            reactant_smiles=payload.reactant_smiles,
            reagent_smiles=payload.reagent_smiles,
            product_smiles=payload.product_smiles,
        )
        requires_review = bool(result["requires_expert_review"])
        row = ReactionSafetyScreeningORM(
            reaction_project_id=project_id,
            label=payload.label or "",
            input_json=_json_dump(payload.model_dump(mode="json")),
            result_json=_json_dump(result),
            overall_risk=str(result["overall_risk"]),
            requires_expert_review=requires_review,
            review_status="pending" if requires_review else "not_required",
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.safety.screen.create",
            message="Reaction safety screening recorded.",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "overall_risk": row.overall_risk,
                "requires_expert_review": requires_review,
                "energetic_groups_found": result["energetic_groups_found"],
            },
        )
        return _screening_to_record(row)


def list_screenings(
    session_factory: sessionmaker[Session], project_id: int
) -> list[ReactionSafetyScreening]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionSafetyScreeningORM)
            .where(ReactionSafetyScreeningORM.reaction_project_id == project_id)
            .order_by(ReactionSafetyScreeningORM.id.desc())
        ).all()
        return [_screening_to_record(row) for row in rows]


def get_screening(
    session_factory: sessionmaker[Session], project_id: int, screening_id: int
) -> ReactionSafetyScreening | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionSafetyScreeningORM, screening_id)
        if row is None or row.reaction_project_id != project_id:
            return None
        return _screening_to_record(row)


def review_screening(
    session_factory: sessionmaker[Session],
    project_id: int,
    screening_id: int,
    payload: ReactionSafetyReviewRequest,
    *,
    actor: ReactionActor,
) -> ReactionSafetyScreening | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionSafetyScreeningORM, screening_id)
        if row is None or row.reaction_project_id != project_id:
            return None
        row.review_status = payload.decision
        row.review_note = payload.note or ""
        row.reviewed_by_user_id = actor.user_id
        row.reviewed_at = utcnow()
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.safety.screen.review",
            message=f"Reaction safety screening {payload.decision} by reviewer.",
            entity_id=row.id,
            metadata={"project_id": project_id, "decision": payload.decision},
        )
        return _screening_to_record(row)


def gate_status(
    session_factory: sessionmaker[Session], project_id: int
) -> ReactionSafetyGateStatus:
    """Fail-safe project gate: blocked if any screen is rejected, else pending if any awaits
    review, else clear. A rejected screen is a definitive 'do not proceed'."""
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionSafetyScreeningORM).where(
                ReactionSafetyScreeningORM.reaction_project_id == project_id
            )
        ).all()
        blocking = [r for r in rows if r.review_status in _BLOCKING_REVIEW_STATES]
        rejected = [r for r in blocking if r.review_status == "rejected"]
        if rejected:
            status_value = "blocked"
            summary = (
                f"{len(rejected)} screening(s) rejected by review — do not proceed without a "
                "qualified process-safety sign-off."
            )
        elif blocking:
            status_value = "review_pending"
            summary = f"{len(blocking)} screening(s) await expert review before execution."
        else:
            status_value = "clear"
            summary = "No screenings require review."
        return ReactionSafetyGateStatus(
            reaction_project_id=project_id,
            status=status_value,
            screenings_total=len(rows),
            blocking_screening_ids=sorted(r.id for r in blocking),
            summary=summary,
        )


class ReactionSafetyGateBlockedError(ReactionError):
    """A rejected safety screening blocks committing the project's reactions to execution.

    Subclasses ``ReactionError`` but is mapped to HTTP **409 (conflict)** at the API boundary
    (not the plain 400) — the request is well-formed; the project is simply under a safety hold.
    Only the execution-gate check raises this; the screening math never does.
    """


def assert_execution_allowed(session: Session, project_id: int) -> None:
    """Fail-safe execution gate: raise if any of the project's safety screenings was *rejected*.

    A reviewer's rejection is a definitive "do not proceed", so it hard-blocks committing the
    project's reactions to the bench (an execution batch moving to ``planned``/``running``). A
    merely *pending* screening does **not** block here — that stays advisory (the project
    safety-gate banner nudges, but does not halt work). Operates on the caller's open ``Session``
    so it never nests a second ``session_scope``.
    """
    rejected = session.scalars(
        select(ReactionSafetyScreeningORM.id)
        .where(
            ReactionSafetyScreeningORM.reaction_project_id == project_id,
            ReactionSafetyScreeningORM.review_status == "rejected",
        )
        .order_by(ReactionSafetyScreeningORM.id)
    ).all()
    if rejected:
        raise ReactionSafetyGateBlockedError(
            f"Execution is blocked by the safety gate: {len(rejected)} screening(s) were "
            "rejected in review. Obtain process-safety clearance (or revise and re-review the "
            "screening) before committing reactions to the bench. Rejected screening id(s): "
            f"{list(rejected)}."
        )
