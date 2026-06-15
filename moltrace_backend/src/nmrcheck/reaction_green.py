"""Green-chemistry metrics engine for the Repho reaction-optimization module (R1).

Computes transparent, citeable green-chemistry metrics per experiment/route and
exposes them as both an optimization objective (via reaction_bo) and a regulatory/
scale-up deliverable. The maths are deterministic and frozen — an LLM never
produces these numbers (see the MolTrace "math frozen" principle).

Metrics implemented
--------------------
* E-factor (Sheldon): simple sEF (excludes solvents/water) and complete cEF
  (includes them). ``e_factor`` headline = cEF. Sheldon, *Green Chem.* 9, 1273 (2007).
* Atom economy (Trost): MW(product) / Σ(equiv·MW(reactant)) × 100.
  Trost, *Science* 254, 1471 (1991).
* PMI (Process Mass Intensity): total input mass / product mass = cEF + 1.
  ACS GCI Pharmaceutical Roundtable.
* RME (Reaction Mass Efficiency): product mass / reactant mass × 100.
  Constable/Curzons et al.
* Solvent green-score: mass-weighted greenness derived from the CHEM21 Safety/
  Health/Environment scores. Prat et al., *Green Chem.* 18, 288 (2016).

The CHEM21 S/H/E scores are factual published data (cited). The 0-100 ``green_score``
transform is a MolTrace-defined, frozen, documented function — not CHEM21's own
ranking — recorded in the assessment provenance as ``formula_version``.

This module mirrors ``reaction_bo.py``'s convention of defining its own small
JSON/audit/project helpers (rather than cross-importing private names), so it stays
self-contained with no new import cycles.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ReactionGreenAssessment,
    ReactionGreenCompareEntry,
    ReactionGreenCompareRequest,
    ReactionGreenCompareResult,
    ReactionGreenMetricsRequest,
    ReactionGreenProfile,
    ReactionGreenProfileCreate,
    ReactionGreenProfileUpdate,
)
from .orm import (
    AuditEventORM,
    ReactionExperimentORM,
    ReactionGreenAssessmentORM,
    ReactionGreenProfileORM,
    ReactionProjectORM,
    utcnow,
)
from .reaction_store import ReactionActor

try:  # pragma: no cover - exercised implicitly; guarded for portability
    import rdkit as _rdkit
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    _RDKIT_AVAILABLE = True
    _RDKIT_VERSION = getattr(_rdkit, "__version__", "unknown")
except Exception:  # pragma: no cover
    _RDKIT_AVAILABLE = False
    _RDKIT_VERSION = None


_SAFE_NOTE = (
    "Green-chemistry metrics are decision-support estimates computed from the inputs "
    "you provide; they are not a regulatory determination and require human review."
)
_SOLVENT_TABLE_VERSION = "chem21-2016"
_FORMULA_VERSION = "green.v1"
_CITATIONS = [
    "Sheldon RA. The E-factor: fifteen years on. Green Chem. 9, 1273 (2007).",
    "Trost BM. The atom economy. Science 254, 1471 (1991).",
    "ACS GCI Pharmaceutical Roundtable. Process Mass Intensity (PMI).",
    "Constable DJC, Curzons AD, et al. Reaction mass efficiency. Green Chem. 4, 521 (2002).",
    "Prat D et al. CHEM21 solvent selection guide. Green Chem. 18, 288 (2016).",
]

# CHEM21 (Prat et al., Green Chem. 2016, 18, 288) Safety/Health/Environment scores
# (each 1-10; higher = more concerning). Canonical lowercase keys.
_CHEM21_SHE: dict[str, tuple[int, int, int]] = {
    "water": (1, 1, 1),
    "ethanol": (4, 3, 3),
    "isopropanol": (4, 3, 3),
    "n-butanol": (3, 4, 3),
    "i-butanol": (3, 4, 3),
    "t-butanol": (4, 3, 3),
    "i-amyl alcohol": (3, 2, 3),
    "ethylene glycol": (1, 2, 5),
    "mek": (5, 3, 3),
    "mibk": (4, 2, 3),
    "ethyl acetate": (5, 3, 3),
    "n-propyl acetate": (4, 2, 3),
    "i-propyl acetate": (4, 2, 3),
    "n-butyl acetate": (4, 2, 3),
    "i-butyl acetate": (4, 2, 3),
    "i-amyl acetate": (3, 1, 5),
    "glycol diacetate": (1, 1, 5),
    "tame": (6, 2, 3),
    "anisole": (4, 1, 5),
    "acetonitrile": (4, 3, 3),
    "dimethyl carbonate": (4, 1, 3),
    "methanol": (4, 7, 5),
    "n-propanol": (4, 4, 3),
    "benzyl alcohol": (1, 2, 7),
    "1,3-propanediol": (1, 1, 7),
    "glycerol": (1, 1, 7),
    "acetone": (5, 3, 5),
    "cyclohexanone": (3, 2, 5),
    "methyl acetate": (5, 3, 5),
    "gamma-valerolactone": (1, 5, 7),
    "diethyl succinate": (1, 5, 7),
    "etbe": (7, 3, 3),
    "cpme": (7, 2, 5),
    "thf": (6, 7, 5),
    "2-methyltetrahydrofuran": (6, 5, 3),
    "1,4-dioxane": (7, 6, 3),
    "heptane": (6, 2, 7),
    "cyclohexane": (6, 3, 7),
    "methylcyclohexane": (6, 2, 7),
    "toluene": (5, 6, 3),
    "xylene": (4, 2, 5),
    "d-limonene": (4, 2, 7),
    "turpentine": (4, 2, 7),
    "p-cymene": (4, 5, 5),
    "chlorobenzene": (3, 2, 7),
    "formic acid": (3, 7, 3),
    "acetic acid": (3, 7, 3),
    "acetic anhydride": (3, 7, 3),
    "ethyl lactate": (3, 4, 5),
    "lactic acid": (1, 4, 7),
    "ethylene carbonate": (1, 2, 7),
    "propylene carbonate": (1, 2, 7),
    "cyrene": (1, 2, 7),
    "dmso": (1, 1, 5),
    "diisopropyl ether": (9, 3, 5),
    "mtbe": (8, 3, 5),
    "dme": (7, 9, 3),
    "pentane": (8, 3, 7),
    "hexane": (8, 7, 7),
    "dichloromethane": (1, 7, 7),
    "carbon tetrachloride": (2, 7, 10),
    "1,2-dichloroethane": (4, 10, 3),
    "dmf": (3, 9, 5),
    "dmac": (1, 9, 5),
    "nmp": (1, 9, 7),
    "sulfolane": (1, 9, 7),
    "nitromethane": (10, 2, 3),
    "2-methoxyethanol": (3, 9, 3),
    "tetrahydrofurfuryl alcohol": (1, 9, 5),
    "carbon disulfide": (9, 7, 7),
    "diethyl ether": (10, 3, 7),
    "chloroform": (2, 7, 5),
    "benzene": (6, 10, 3),
    "hmpa": (1, 9, 7),
}

# Common synonyms / abbreviations -> canonical CHEM21 key.
_SOLVENT_ALIASES: dict[str, str] = {
    "h2o": "water",
    "etoh": "ethanol",
    "meoh": "methanol",
    "ipa": "isopropanol",
    "2-propanol": "isopropanol",
    "isopropyl alcohol": "isopropanol",
    "iproh": "isopropanol",
    "mecn": "acetonitrile",
    "acn": "acetonitrile",
    "etoac": "ethyl acetate",
    "ea": "ethyl acetate",
    "ipac": "i-propyl acetate",
    "dcm": "dichloromethane",
    "methylene chloride": "dichloromethane",
    "chcl3": "chloroform",
    "ccl4": "carbon tetrachloride",
    "et2o": "diethyl ether",
    "ether": "diethyl ether",
    "tbme": "mtbe",
    "me-thf": "2-methyltetrahydrofuran",
    "2-methf": "2-methyltetrahydrofuran",
    "methf": "2-methyltetrahydrofuran",
    "2-me-thf": "2-methyltetrahydrofuran",
    "dioxane": "1,4-dioxane",
    "tol": "toluene",
    "xylenes": "xylene",
    "glyme": "dme",
    "dma": "dmac",
    "n,n-dimethylacetamide": "dmac",
    "n,n-dimethylformamide": "dmf",
    "gvl": "gamma-valerolactone",
    "cs2": "carbon disulfide",
}


# ---------------------------------------------------------------------------
# Local helpers (self-contained, mirroring reaction_bo.py's convention)
# ---------------------------------------------------------------------------
def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


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
    entity_type: str,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _round(value: float | None, ndigits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), ndigits)


def _mol_weight(smiles: str | None) -> float | None:
    if not smiles or not _RDKIT_AVAILABLE:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
    except Exception:
        return None
    if mol is None:
        return None
    try:
        return float(Descriptors.MolWt(mol))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Solvent greenness
# ---------------------------------------------------------------------------
def _normalize_solvent(name: str) -> str:
    key = " ".join(str(name).strip().lower().split())
    if key in _CHEM21_SHE:
        return key
    return _SOLVENT_ALIASES.get(key, key)


def greenness_from_she(safety: float, health: float, env: float) -> float:
    """Frozen 0-100 greenness from CHEM21 S/H/E scores (1-10, higher = worse).

    Worst-dimension-weighted (conservative) and tempered by the mean::

        greenness = 100 * (1 - (0.6*worst + 0.4*mean - 1) / 9)

    Maps (1,1,1) -> 100 and (10,10,10) -> 0; monotonic in each dimension.
    This is a MolTrace-defined index (formula_version ``green.v1``), not CHEM21's
    own four-tier ranking; it is derived from CHEM21's published S/H/E scores.
    """
    worst = max(safety, health, env)
    mean = (safety + health + env) / 3.0
    score = 100.0 * (1.0 - (0.6 * worst + 0.4 * mean - 1.0) / 9.0)
    return max(0.0, min(100.0, score))


def _solvent_greenness(name: str, overrides: dict[str, Any]) -> float | None:
    """Return the 0-100 greenness for a solvent, or None if unknown.

    ``overrides`` (from the project green profile) may map either a normalized
    solvent name -> numeric greenness (0-100), or -> [S, H, E] triple.
    """
    key = _normalize_solvent(name)
    if key in overrides:
        ov = overrides[key]
        if isinstance(ov, (int, float)):
            return max(0.0, min(100.0, float(ov)))
        if isinstance(ov, (list, tuple)) and len(ov) >= 3:
            return greenness_from_she(float(ov[0]), float(ov[1]), float(ov[2]))
    she = _CHEM21_SHE.get(key)
    if she is None:
        return None
    return greenness_from_she(*she)


def _normalized_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    return {_normalize_solvent(str(k)): v for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Pure metric computation (frozen, unit-tested)
# ---------------------------------------------------------------------------
def _compute_green_metrics(
    payload: ReactionGreenMetricsRequest,
    *,
    solvent_overrides: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    components = list(payload.components)
    solvents = [c for c in components if c.role == "solvent"]
    reactants = [c for c in components if c.role == "reactant"]

    def _mass(items: list[Any]) -> float:
        return sum(float(c.mass_g) for c in items if c.mass_g is not None)

    product_mass = payload.product_mass_g
    total_in_mass = _mass(components)
    nonsolvent_mass = _mass([c for c in components if c.role != "solvent"])
    reactant_mass = _mass(reactants)

    # --- mass-based metrics (E-factor / PMI / RME) ---
    # Mass conservation: total input must be >= product. A product heavier than all
    # inputs is physically impossible and signals bad data; warn instead of emitting
    # a negative E-factor / sub-1 PMI that the persist step would then silently drop.
    if product_mass is not None and product_mass > 0 and total_in_mass >= product_mass:
        cef = (total_in_mass - product_mass) / product_mass
        metrics["e_factor"] = _round(cef, 4)
        metrics["e_factor_complete"] = _round(cef, 4)
        metrics["pmi"] = _round(total_in_mass / product_mass, 4)
        metrics["total_input_mass_g"] = _round(total_in_mass, 4)
        metrics["product_mass_g"] = _round(product_mass, 4)
        if nonsolvent_mass >= product_mass:
            metrics["e_factor_simple"] = _round((nonsolvent_mass - product_mass) / product_mass, 4)
        else:
            warnings.append(
                "Simple E-factor not computed: non-solvent mass < product mass "
                "(solvent-dominated or inconsistent input)."
            )
        if reactant_mass > 0:
            metrics["rme_percent"] = _round(min(100.0, product_mass / reactant_mass * 100.0), 2)
        else:
            warnings.append("RME not computed: no reactant masses provided.")
    elif product_mass is not None and product_mass > 0 and 0 < total_in_mass < product_mass:
        warnings.append(
            "E-factor/PMI/RME not computed: total input mass < product mass "
            "(mass-conservation violation — check inputs)."
        )
    else:
        warnings.append(
            "E-factor/PMI/RME not computed: need product_mass_g (>0) and component mass_g."
        )

    # --- atom economy ---
    product_mw = payload.product_mw or _mol_weight(payload.product_smiles)
    reactant_mw_total = 0.0
    reactant_mw_known = False
    for c in reactants:
        mw = _mol_weight(c.smiles)
        if mw is None:
            if c.smiles:
                warnings.append(f"Atom economy: could not parse SMILES for reactant '{c.name}'.")
            continue
        equiv = float(c.equivalents) if c.equivalents is not None else 1.0
        reactant_mw_total += equiv * mw
        reactant_mw_known = True
    if product_mw and reactant_mw_known and reactant_mw_total > 0:
        ae = product_mw / reactant_mw_total * 100.0
        metrics["atom_economy_percent"] = _round(min(100.0, ae), 2)
        if ae > 100.5:
            warnings.append(
                "Atom economy exceeded 100% (check stoichiometry/SMILES); clamped to 100%."
            )
    else:
        if not _RDKIT_AVAILABLE and (payload.product_smiles or any(c.smiles for c in reactants)):
            warnings.append(
                "Atom economy not computed: RDKit unavailable for SMILES molecular weights."
            )
        else:
            warnings.append(
                "Atom economy not computed: provide product_smiles/product_mw and reactant SMILES."
            )

    # --- solvent green-score ---
    if solvents:
        weighted_sum = 0.0
        weight_total = 0.0
        for c in solvents:
            greenness = _solvent_greenness(c.name, solvent_overrides)
            if greenness is None:
                warnings.append(
                    f"Solvent '{c.name}' not in greenness table; excluded from green_score."
                )
                continue
            weight = float(c.mass_g) if c.mass_g is not None and c.mass_g > 0 else 1.0
            weighted_sum += greenness * weight
            weight_total += weight
        if weight_total > 0:
            green_score = weighted_sum / weight_total
            metrics["green_score"] = _round(green_score, 2)
            metrics["solvent_greenness_score"] = _round(green_score, 2)
        else:
            warnings.append("green_score not computed: no recognized solvents.")
    else:
        warnings.append("green_score not computed: no solvent components provided.")

    # --- optional pass-through process metrics (user-supplied, not derived) ---
    if payload.energy_intensity_kwh_per_kg is not None:
        metrics["energy_intensity_kwh_per_kg"] = _round(payload.energy_intensity_kwh_per_kg, 4)
    if payload.water_usage_l_per_kg is not None:
        metrics["water_usage_l_per_kg"] = _round(payload.water_usage_l_per_kg, 4)
    if payload.hazardous_waste_kg_per_kg is not None:
        metrics["hazardous_waste_kg_per_kg"] = _round(payload.hazardous_waste_kg_per_kg, 4)

    provenance = {
        "formula_version": _FORMULA_VERSION,
        "solvent_table_version": _SOLVENT_TABLE_VERSION,
        "rdkit_version": _RDKIT_VERSION,
        "rdkit_available": _RDKIT_AVAILABLE,
        "citations": list(_CITATIONS),
        "definitions": {
            "e_factor": "complete E-factor cEF = (total input mass - product mass) / product mass",
            "e_factor_simple": "sEF = (non-solvent - product) / product; excludes role='solvent'",
            "pmi": "total input mass / product mass (= cEF + 1)",
            "atom_economy_percent": "MW(product) / sum(equiv * MW(reactant)) * 100",
            "rme_percent": "product mass / reactant mass * 100",
            "green_score": "mass-weighted CHEM21 solvent greenness (0-100, higher is greener)",
        },
    }
    return metrics, warnings, provenance


# Outcome fields that may be written back onto an experiment (with model bounds).
# Percent fields are clamped to [0, 100]; ratio fields must be >= 0.
_OUTCOME_PERCENT_KEYS = ("atom_economy_percent", "rme_percent", "green_score")
_OUTCOME_RATIO_KEYS = ("e_factor", "pmi")


def _outcome_payload_from_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    payload: dict[str, float] = {}
    for key in _OUTCOME_PERCENT_KEYS:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            payload[key] = max(0.0, min(100.0, float(value)))
    for key in _OUTCOME_RATIO_KEYS:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            payload[key] = float(value)
    return payload


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
def _latest_green_profile(session: Session, project_id: int) -> ReactionGreenProfileORM | None:
    return session.scalar(
        select(ReactionGreenProfileORM)
        .where(ReactionGreenProfileORM.reaction_project_id == project_id)
        .order_by(ReactionGreenProfileORM.id.desc())
    )


def _latest_assessment(session: Session, experiment_id: int) -> ReactionGreenAssessmentORM | None:
    return session.scalar(
        select(ReactionGreenAssessmentORM)
        .where(ReactionGreenAssessmentORM.reaction_experiment_id == experiment_id)
        .order_by(ReactionGreenAssessmentORM.id.desc())
    )


def _resolve_solvent_overrides(profile: ReactionGreenProfileORM | None) -> dict[str, Any]:
    if profile is None:
        return {}
    return _normalized_overrides(_json_dict(profile.solvent_greenness_json))


def _green_profile_to_record(row: ReactionGreenProfileORM) -> ReactionGreenProfile:
    return ReactionGreenProfile(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        solvent_greenness_json=_json_dict(row.solvent_greenness_json),
        default_assumptions_json=_json_dict(row.default_assumptions_json),
        solvent_table_version=row.solvent_table_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _green_assessment_to_record(row: ReactionGreenAssessmentORM) -> ReactionGreenAssessment:
    return ReactionGreenAssessment(
        id=row.id,
        reaction_experiment_id=row.reaction_experiment_id,
        reaction_project_id=row.reaction_project_id,
        metrics_json=_json_dict(row.metrics_json),
        inputs_json=_json_dict(row.inputs_json),
        provenance_json=_json_dict(row.provenance_json),
        warnings=[str(item) for item in _json_list(row.warnings_json)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


# ---------------------------------------------------------------------------
# Green profile CRUD (mirrors reaction_bo cost/safety profile)
# ---------------------------------------------------------------------------
def create_green_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionGreenProfileCreate,
    *,
    actor: ReactionActor,
) -> ReactionGreenProfile:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionGreenProfileORM(
            reaction_project_id=project_id,
            solvent_greenness_json=_json_dump(payload.solvent_greenness_json),
            default_assumptions_json=_json_dump(payload.default_assumptions_json),
            solvent_table_version=payload.solvent_table_version,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.green.profile.create",
            message="Reaction green profile created.",
            entity_type="reaction_green_profile",
            entity_id=row.id,
            metadata={"project_id": project_id},
        )
        return _green_profile_to_record(row)


def get_green_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> ReactionGreenProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_green_profile(session, project_id)
        return _green_profile_to_record(row) if row is not None else None


def patch_green_profile(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionGreenProfileUpdate,
    *,
    actor: ReactionActor,
) -> ReactionGreenProfile | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = _latest_green_profile(session, project_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("solvent_greenness_json", "default_assumptions_json", "metadata_json"):
            if field in update:
                setattr(row, field, _json_dump(update[field] or {}))
        if "solvent_table_version" in update and update["solvent_table_version"]:
            row.solvent_table_version = update["solvent_table_version"]
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="reaction.green.profile.update",
            message="Reaction green profile updated.",
            entity_type="reaction_green_profile",
            entity_id=row.id,
            metadata={"project_id": project_id, "updated_fields": sorted(update)},
        )
        return _green_profile_to_record(row)


# ---------------------------------------------------------------------------
# Per-experiment green assessment
# ---------------------------------------------------------------------------
def compute_green_metrics(
    session_factory: sessionmaker[Session],
    project_id: int,
    experiment_id: int,
    payload: ReactionGreenMetricsRequest,
    *,
    actor: ReactionActor,
) -> ReactionGreenAssessment | None:
    with session_scope(session_factory) as session:
        experiment = session.get(ReactionExperimentORM, experiment_id)
        # The experiment must belong to the project named in the route path; a
        # mismatch returns None -> non-leaking 404 (mirrors compare_green).
        if experiment is None or experiment.reaction_project_id != project_id:
            return None
        profile = _latest_green_profile(session, project_id)
        overrides = _resolve_solvent_overrides(profile)
        metrics, warnings, provenance = _compute_green_metrics(payload, solvent_overrides=overrides)

        if payload.persist_to_outcome:
            outcome = _json_dict(experiment.outcome_json)
            outcome.update(_outcome_payload_from_metrics(metrics))
            experiment.outcome_json = _json_dump(outcome)
            experiment.updated_at = utcnow()

        row = ReactionGreenAssessmentORM(
            reaction_experiment_id=experiment_id,
            reaction_project_id=project_id,
            metrics_json=_json_dump(metrics),
            inputs_json=_json_dump(payload.model_dump(mode="json")),
            provenance_json=_json_dump(provenance),
            warnings_json=_json_dump(warnings),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.green.assessment.create",
            message="Reaction green assessment computed.",
            entity_type="reaction_green_assessment",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "experiment_id": experiment_id,
                "persisted_to_outcome": payload.persist_to_outcome,
            },
        )
        return _green_assessment_to_record(row)


def get_green_metrics(
    session_factory: sessionmaker[Session],
    project_id: int,
    experiment_id: int,
) -> ReactionGreenAssessment | None:
    with session_scope(session_factory) as session:
        experiment = session.get(ReactionExperimentORM, experiment_id)
        if experiment is None or experiment.reaction_project_id != project_id:
            return None
        row = _latest_assessment(session, experiment_id)
        return _green_assessment_to_record(row) if row is not None else None


_BETTER_LOWER = {"e_factor", "e_factor_complete", "e_factor_simple", "pmi"}
_BETTER_HIGHER = {"atom_economy_percent", "rme_percent", "green_score"}


def _best_by_metric(entries: list[ReactionGreenCompareEntry]) -> dict[str, Any]:
    best: dict[str, Any] = {}
    for metric in sorted(_BETTER_LOWER | _BETTER_HIGHER):
        candidates = [
            (e.reaction_experiment_id, float(e.metrics_json[metric]))
            for e in entries
            if e.available and isinstance(e.metrics_json.get(metric), (int, float))
        ]
        if not candidates:
            continue
        if metric in _BETTER_LOWER:
            winner = min(candidates, key=lambda item: item[1])
        else:
            winner = max(candidates, key=lambda item: item[1])
        best[metric] = {"reaction_experiment_id": winner[0], "value": winner[1]}
    return best


def compare_green(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionGreenCompareRequest,
) -> ReactionGreenCompareResult:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        entries: list[ReactionGreenCompareEntry] = []
        warnings: list[str] = []
        seen: set[int] = set()
        for experiment_id in payload.experiment_ids:
            if experiment_id in seen:
                continue
            seen.add(experiment_id)
            experiment = session.get(ReactionExperimentORM, experiment_id)
            if experiment is None or experiment.reaction_project_id != project_id:
                warnings.append(
                    f"Experiment {experiment_id} not found in project {project_id}; skipped."
                )
                continue
            row = _latest_assessment(session, experiment_id)
            if row is None:
                entries.append(
                    ReactionGreenCompareEntry(
                        reaction_experiment_id=experiment_id,
                        experiment_code=experiment.experiment_code,
                        available=False,
                    )
                )
                continue
            entries.append(
                ReactionGreenCompareEntry(
                    reaction_experiment_id=experiment_id,
                    experiment_code=experiment.experiment_code,
                    metrics_json=_json_dict(row.metrics_json),
                    available=True,
                )
            )
        return ReactionGreenCompareResult(
            reaction_project_id=project_id,
            entries=entries,
            best_by_metric_json=_best_by_metric(entries),
            warnings=warnings,
            notes=[_SAFE_NOTE],
            human_review_required=True,
        )
