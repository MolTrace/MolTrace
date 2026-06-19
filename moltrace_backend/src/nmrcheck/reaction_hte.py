"""HTE / DoE plate-design engine for the Repho reaction optimizer (R3).

Generates machine-readable high-throughput-experimentation plate maps (24/96/384 wells)
over a reaction design space, using space-filling (Sobol, Latin Hypercube), factorial, or
Bayesian-optimization-initialization strategies. Pure NumPy/SciPy/stdlib, deterministic
(seeded), no ORM/HTTP imports — so it stays decoupled and unit-testable in isolation.

The store/API layer (a later slice) translates the reaction design-space + safety profile
into the primitive inputs here and persists the result; this module owns only the math.
"""

from __future__ import annotations

import csv
import io
import json
import warnings
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import ReactionPlateDesign, ReactionPlateDesignRequest
from .orm import AuditEventORM, ReactionPlateDesignORM, ReactionProjectORM
from .reaction_store import ReactionActor

_PLATE_LAYOUTS: dict[str, tuple[int, int]] = {
    # plate_format -> (rows, cols)
    "24": (4, 6),
    "96": (8, 12),
    "384": (16, 24),
}
_ROW_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_STRATEGIES = ("sobol", "lhs", "factorial", "bo_init")
_BO_INIT_TARGET = 20  # typical Bayesian-optimization seed population (15-25)


def _well_ids(rows: int, cols: int) -> list[str]:
    return [f"{_ROW_LETTERS[r]}{c + 1}" for r in range(rows) for c in range(cols)]


def _excluded_match(conditions: Mapping[str, Any], excluded: Sequence[Mapping[str, Any]]) -> bool:
    """True if ``conditions`` matches any fully-specified excluded combination."""
    for combo in excluded:
        if combo and all(conditions.get(key) == value for key, value in combo.items()):
            return True
    return False


def _scale_numeric(unit: float, low: float, high: float) -> float:
    return round(low + float(unit) * (high - low), 6)


def _pick_categorical(unit: float, options: Sequence[Any]) -> Any:
    if not options:
        return None
    index = min(int(float(unit) * len(options)), len(options) - 1)
    return options[index]


def _qmc_sample(n: int, dims: int, strategy: str, seed: int) -> list[list[float]]:
    """n x dims low-discrepancy sample in [0, 1) via SciPy QMC (deterministic)."""
    if dims == 0 or n == 0:
        return [[] for _ in range(n)]
    from scipy.stats import qmc

    with warnings.catch_warnings():
        # Sobol balance is only guaranteed at powers of two; plate sizes (24/96/384)
        # are not, which is acceptable for screening — silence the advisory warning.
        warnings.simplefilter("ignore")
        engine = (
            qmc.Sobol(d=dims, seed=seed)
            if strategy in ("sobol", "bo_init")
            else qmc.LatinHypercube(d=dims, seed=seed)
        )
        return engine.random(n).tolist()


def _factorial_conditions(
    numeric: Mapping[str, tuple[float, float]],
    categorical: Mapping[str, Sequence[Any]],
    boolean: Sequence[str],
    *,
    numeric_levels: int = 3,
) -> list[dict[str, Any]]:
    """Full-factorial grid: numeric discretized to ``numeric_levels`` (lo/mid/hi), each
    categorical over its options, each boolean over (False, True). Row-major product."""
    import itertools

    axes: list[list[tuple[str, Any]]] = []
    for name, (low, high) in numeric.items():
        if numeric_levels <= 1:
            levels = [low]
        else:
            step = (high - low) / (numeric_levels - 1)
            levels = [round(low + i * step, 6) for i in range(numeric_levels)]
        axes.append([(name, v) for v in levels])
    for name, options in categorical.items():
        axes.append([(name, v) for v in options])
    for name in boolean:
        axes.append([(name, v) for v in (False, True)])
    if not axes:
        return []
    return [dict(combo) for combo in itertools.product(*axes)]


def generate_plate_design(
    *,
    numeric: Mapping[str, tuple[float, float]] | None = None,
    categorical: Mapping[str, Sequence[Any]] | None = None,
    boolean: Sequence[str] | None = None,
    fixed: Mapping[str, Any] | None = None,
    excluded: Sequence[Mapping[str, Any]] | None = None,
    plate_format: str = "96",
    strategy: str = "sobol",
    seed: int = 20260615,
) -> dict[str, Any]:
    """Generate a deterministic, machine-readable HTE plate design.

    Returns a dict: ``plate_format``, ``strategy``, ``well_count``, ``dimensions``,
    ``wells`` (each ``{well_id, conditions}``), ``warnings``, and a frozen ``provenance``.
    Excluded combinations are filtered; ``fixed`` conditions are applied to every well.
    Advisory; the design requires human review before execution.
    """
    numeric = dict(numeric or {})
    categorical = {k: list(v) for k, v in (categorical or {}).items()}
    boolean = list(boolean or [])
    fixed = dict(fixed or {})
    excluded = [dict(c) for c in (excluded or [])]
    warns: list[str] = []

    if plate_format not in _PLATE_LAYOUTS:
        raise ValueError(
            f"Unsupported plate_format {plate_format!r}; use one of {sorted(_PLATE_LAYOUTS)}."
        )
    if strategy not in _STRATEGIES:
        raise ValueError(f"Unsupported strategy {strategy!r}; use one of {list(_STRATEGIES)}.")

    rows, cols = _PLATE_LAYOUTS[plate_format]
    capacity = rows * cols
    target = min(_BO_INIT_TARGET, capacity) if strategy == "bo_init" else capacity

    numeric_names = list(numeric)
    categorical_names = list(categorical)

    candidate_conditions: list[dict[str, Any]] = []
    if strategy == "factorial":
        grid = _factorial_conditions(numeric, categorical, boolean)
        if len(grid) > capacity:
            warns.append(
                f"Factorial grid has {len(grid)} combinations but the plate holds {capacity}; "
                f"truncated to the first {capacity}."
            )
        candidate_conditions = grid[:capacity]
    else:
        dims = len(numeric_names) + len(categorical_names) + len(boolean)
        sample = _qmc_sample(target, dims, strategy, seed)
        for unit_row in sample:
            conditions: dict[str, Any] = {}
            cursor = 0
            for name in numeric_names:
                low, high = numeric[name]
                conditions[name] = _scale_numeric(unit_row[cursor], low, high)
                cursor += 1
            for name in categorical_names:
                conditions[name] = _pick_categorical(unit_row[cursor], categorical[name])
                cursor += 1
            for name in boolean:
                conditions[name] = bool(unit_row[cursor] >= 0.5)
                cursor += 1
            candidate_conditions.append(conditions)

    # Apply fixed conditions, drop excluded combinations.
    wells: list[dict[str, Any]] = []
    well_ids = _well_ids(rows, cols)
    for conditions in candidate_conditions:
        merged = {**conditions, **fixed}
        if _excluded_match(merged, excluded):
            continue
        wells.append({"well_id": well_ids[len(wells)], "conditions": merged})
        if len(wells) >= capacity:
            break

    if not wells:
        warns.append(
            "No wells generated: design space is empty (add numeric/categorical/boolean variables)."
        )

    dimensions = numeric_names + categorical_names + list(boolean) + list(fixed)
    return {
        "plate_format": plate_format,
        "strategy": strategy,
        "well_count": len(wells),
        "capacity": capacity,
        "dimensions": dimensions,
        "wells": wells,
        "warnings": warns,
        "provenance": {
            "engine": "reaction_hte.v1",
            "seed": seed,
            "rows": rows,
            "cols": cols,
            "note": "Advisory HTE plate design; requires human review before execution.",
        },
    }


def export_plate(design: Mapping[str, Any], target: str = "csv") -> str:
    """Serialize a plate design to a machine-readable string.

    ``target`` is ``"csv"`` (well_id + one column per condition key) or ``"json"``.
    Robot-vendor formats (Mettler-Toledo, Chemspeed, Unchained Labs) are thin adapters
    layered on these and are added when a target instrument is in scope.
    """
    if target == "json":
        return json.dumps(design, sort_keys=True, separators=(",", ":"), default=str)
    if target != "csv":
        raise ValueError(f"Unsupported export target {target!r}; use 'csv' or 'json'.")
    wells = list(design.get("wells", []))
    keys: list[str] = []
    for well in wells:
        for key in well.get("conditions", {}):
            if key not in keys:
                keys.append(key)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["well_id", *keys])
    for well in wells:
        conditions = well.get("conditions", {})
        writer.writerow([well.get("well_id"), *[conditions.get(k, "") for k in keys]])
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Persistence layer (store) — mirrors reaction_green's self-contained helpers
# ---------------------------------------------------------------------------
_SAFE_NOTE = (
    "HTE plate design is advisory; verify against the project's safety constraints and the "
    "target instrument's capability, and obtain human review before execution."
)


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


def _plate_to_record(row: ReactionPlateDesignORM) -> ReactionPlateDesign:
    return ReactionPlateDesign(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        plate_format=row.plate_format,
        strategy=row.strategy,
        well_count=row.well_count,
        design_json=_json_dict(row.design_json),
        inputs_json=_json_dict(row.inputs_json),
        warnings=[str(w) for w in _json_list(row.warnings_json)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def create_plate_design(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionPlateDesignRequest,
    *,
    actor: ReactionActor,
) -> ReactionPlateDesign:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        design = generate_plate_design(
            numeric={k: tuple(v) for k, v in payload.numeric_json.items()},
            categorical=payload.categorical_json,
            boolean=payload.boolean_json,
            fixed=payload.fixed_json,
            excluded=payload.excluded_json,
            plate_format=payload.plate_format,
            strategy=payload.strategy,
            seed=payload.seed,
        )
        row = ReactionPlateDesignORM(
            reaction_project_id=project_id,
            plate_format=payload.plate_format,
            strategy=payload.strategy,
            well_count=design["well_count"],
            design_json=_json_dump(design),
            inputs_json=_json_dump(payload.model_dump(mode="json")),
            warnings_json=_json_dump(design["warnings"]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.hte.plate_design.create",
            message="Reaction HTE plate design created.",
            entity_type="reaction_plate_design",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "well_count": design["well_count"],
                "strategy": payload.strategy,
            },
        )
        return _plate_to_record(row)


def list_plate_designs(
    session_factory: sessionmaker[Session], project_id: int
) -> list[ReactionPlateDesign]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionPlateDesignORM)
            .where(ReactionPlateDesignORM.reaction_project_id == project_id)
            .order_by(ReactionPlateDesignORM.id.desc())
        ).all()
        return [_plate_to_record(row) for row in rows]


def get_plate_design(
    session_factory: sessionmaker[Session], project_id: int, plate_design_id: int
) -> ReactionPlateDesign | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionPlateDesignORM, plate_design_id)
        if row is None or row.reaction_project_id != project_id:
            return None
        return _plate_to_record(row)


def export_plate_design(
    session_factory: sessionmaker[Session], project_id: int, plate_design_id: int, target: str
) -> str | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionPlateDesignORM, plate_design_id)
        if row is None or row.reaction_project_id != project_id:
            return None
        return export_plate(_json_dict(row.design_json), target)
