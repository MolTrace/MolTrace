"""Structure-constrained global assignment of observed 1H signal to protons.

The existing classifier asks, per peak, "which ppm window is this in?" That
question has no notion of how many protons the molecule actually has, so a
molecule with two anomeric protons could be reported as having ten. Caps and
refinements were bolted on afterwards to catch that, each gated on some
structural heuristic, and each gate is a place the correction can fail to fire.

This module asks the opposite question, once, globally:

    given THIS molecule's proton environments and THESE observed signals,
    what is the most probable assignment of signal to protons?

It is solved as a balanced transportation problem: observed integral mass is
supply, each symmetry-unique proton environment is a demand equal to its proton
count, and the cost of routing signal to an environment is the negative
log-likelihood of that environment producing a peak at that shift. Solvent,
contaminant and exchanged-labile sinks absorb the remainder.

The decisive property is that conservation is a HARD CONSTRAINT rather than a
post-hoc correction: an environment cannot receive more protons than it has, so
over-assignment is structurally impossible instead of being something a cap has
to notice. The anomeric defect this replaces could not arise here, and neither
can the same shape of defect in molecule classes nobody has written a special
case for.

Default OFF. Enable with MOLTRACE_STRUCTURE_ASSIGNMENT=1.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from rdkit import Chem

from .chemistry import mol_from_smiles
from .nmr_prediction import _predict_proton_shift_for_carbon
from .solvents import solvent_exchanges_labile_protons

ENV_FLAG = "MOLTRACE_STRUCTURE_ASSIGNMENT"

# Sink identifiers. These are not proton environments of the analyte; they
# absorb signal that the structure cannot account for.
SINK_CONTAMINANT = "__contaminant__"
SINK_EXCHANGED = "__exchanged__"

# Cost (negative log-likelihood units) of routing signal to the contaminant
# sink. Set so that a peak lands on a real environment when it is within a few
# sigma of that environment's predicted shift, and falls through to the sink
# when it is nowhere near anything the structure predicts.
CONTAMINANT_COST = 12.0

# Labile protons are given a broad prior: OH and NH shifts are strongly
# concentration-, temperature- and solvent-dependent, so a narrow Gaussian
# would be false precision.
_LABILE_PRIORS: dict[str, tuple[float, float]] = {
    "O": (4.0, 2.5),  # OH
    "N": (4.0, 3.0),  # NH
    "S": (2.0, 1.5),  # SH
}


def structure_assignment_enabled(environ: dict[str, str] | None = None) -> bool:
    source = environ if environ is not None else os.environ
    return str(source.get(ENV_FLAG, "")).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProtonEnvironment:
    """A symmetry-unique set of equivalent protons."""

    key: str
    proton_count: int
    predicted_ppm: float
    sigma_ppm: float
    kind: str
    exchangeable: bool = False

    def cost_for(self, shift_ppm: float) -> float:
        """Negative log-likelihood of this environment producing that shift."""
        sigma = max(self.sigma_ppm, 0.05)
        z = (float(shift_ppm) - self.predicted_ppm) / sigma
        return 0.5 * z * z + math.log(sigma)


@dataclass
class AssignmentResult:
    environments: list[ProtonEnvironment] = field(default_factory=list)
    # environment key -> assigned proton mass
    assigned: dict[str, float] = field(default_factory=dict)
    # (signal index, environment key) -> mass
    flows: list[dict[str, Any]] = field(default_factory=list)
    contaminant_h: float = 0.0
    exchanged_h: float = 0.0
    unexplained_h: float = 0.0
    total_cost: float = 0.0
    feasible: bool = True
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "total_cost": round(self.total_cost, 4),
            "contaminant_h": round(self.contaminant_h, 3),
            "exchanged_h": round(self.exchanged_h, 3),
            "unexplained_h": round(self.unexplained_h, 3),
            "environments": [
                {
                    "key": env.key,
                    "proton_count": env.proton_count,
                    "predicted_ppm": env.predicted_ppm,
                    "sigma_ppm": env.sigma_ppm,
                    "kind": env.kind,
                    "exchangeable": env.exchangeable,
                    "assigned_h": round(self.assigned.get(env.key, 0.0), 3),
                }
                for env in self.environments
            ],
            "flows": self.flows,
            "notes": list(self.notes),
        }


def enumerate_proton_environments(smiles: str) -> list[ProtonEnvironment]:
    """Symmetry-unique proton environments with predicted shifts.

    Equivalent protons are grouped by RDKit's canonical ranking with ties
    unbroken, so the nine protons of a tert-butyl group form ONE environment of
    count 9 rather than nine environments of count 1. That grouping is what
    makes the proton-count demand meaningful.
    """
    mol = mol_from_smiles(smiles)
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))

    grouped: dict[int, list[Chem.Atom]] = {}
    for atom in mol.GetAtoms():
        if atom.GetTotalNumHs(includeNeighbors=False) <= 0:
            continue
        grouped.setdefault(ranks[atom.GetIdx()], []).append(atom)

    environments: list[ProtonEnvironment] = []
    for rank, atoms in sorted(grouped.items()):
        proton_count = sum(a.GetTotalNumHs(includeNeighbors=False) for a in atoms)
        if proton_count <= 0:
            continue
        head = atoms[0]
        symbol = head.GetSymbol()
        if head.GetAtomicNum() == 6:
            shift, sigma, kind, _mult, _warn = _predict_proton_shift_for_carbon(head)
            if not kind:
                shift, sigma, kind = 1.5, 1.0, "aliphatic_proton"
            environments.append(
                ProtonEnvironment(
                    key=f"env{rank}_{symbol}{head.GetIdx()}",
                    proton_count=proton_count,
                    predicted_ppm=round(float(shift), 3),
                    sigma_ppm=round(float(sigma), 3),
                    kind=kind,
                    exchangeable=False,
                )
            )
        elif symbol in _LABILE_PRIORS:
            shift, sigma = _LABILE_PRIORS[symbol]
            environments.append(
                ProtonEnvironment(
                    key=f"env{rank}_{symbol}{head.GetIdx()}",
                    proton_count=proton_count,
                    predicted_ppm=shift,
                    sigma_ppm=sigma,
                    kind=f"labile_{symbol}H",
                    exchangeable=True,
                )
            )
    return environments


def assign_signals(
    *,
    environments: Sequence[ProtonEnvironment],
    signals: Sequence[tuple[float, float]],
    solvent: str | None = None,
) -> AssignmentResult:
    """Solve the transportation problem routing signal mass to environments.

    ``signals`` are (shift_ppm, integral_h) pairs. Conservation is enforced as
    an equality constraint per environment, so no environment can absorb more
    protons than it contains.
    """
    result = AssignmentResult(environments=list(environments))
    if not environments or not signals:
        result.feasible = False
        result.notes.append("No environments or no signals to assign.")
        return result

    exchanging = solvent_exchanges_labile_protons(solvent)
    visible = [env for env in environments if not (exchanging and env.exchangeable)]
    exchanged = [env for env in environments if exchanging and env.exchangeable]
    result.exchanged_h = float(sum(env.proton_count for env in exchanged))
    if exchanged:
        result.notes.append(
            f"{solvent} exchanges OH/NH/SH, so {result.exchanged_h:.0f} labile H are "
            "expected to be absent and are excluded from the assignment."
        )

    if not visible:
        result.feasible = False
        result.notes.append("Every proton environment is exchanged away.")
        return result

    supply = [float(mass) for _shift, mass in signals]
    total_supply = sum(supply)
    demand = [float(env.proton_count) for env in visible]
    total_demand = sum(demand)
    if total_supply <= 0:
        result.feasible = False
        result.notes.append("Observed signal carries no integral mass.")
        return result

    # Balance the problem. Excess observed signal goes to a contaminant sink;
    # missing observed signal is modelled as a dummy supply so environments can
    # still be filled (an unobserved resonance is not a contradiction).
    columns = list(visible)
    sink_index: int | None = None
    if total_supply > total_demand:
        sink_index = len(columns)
        demand.append(total_supply - total_demand)
    dummy_supply = max(0.0, total_demand - total_supply)
    if dummy_supply > 0:
        supply.append(dummy_supply)

    n_rows, n_cols = len(supply), len(demand)
    costs: list[float] = []
    for i in range(n_rows):
        is_dummy = dummy_supply > 0 and i == n_rows - 1
        shift = None if is_dummy else float(signals[i][0])
        for j in range(n_cols):
            if sink_index is not None and j == sink_index:
                # Dummy supply must not be routed into the contaminant sink;
                # that would invent contamination out of missing signal.
                costs.append(0.0 if is_dummy else CONTAMINANT_COST)
            elif is_dummy:
                costs.append(0.0)
            else:
                costs.append(columns[j].cost_for(shift))

    try:
        from scipy.optimize import linprog
    except Exception:  # pragma: no cover - scipy is a hard dependency in practice
        result.feasible = False
        result.notes.append("Linear solver unavailable; assignment not attempted.")
        return result

    # Equality constraints: every row's mass is fully distributed and every
    # column receives exactly its demand.
    a_eq: list[list[float]] = []
    b_eq: list[float] = []
    for i in range(n_rows):
        row = [0.0] * (n_rows * n_cols)
        for j in range(n_cols):
            row[i * n_cols + j] = 1.0
        a_eq.append(row)
        b_eq.append(supply[i])
    for j in range(n_cols):
        row = [0.0] * (n_rows * n_cols)
        for i in range(n_rows):
            row[i * n_cols + j] = 1.0
        a_eq.append(row)
        b_eq.append(demand[j])

    solution = linprog(
        c=costs, A_eq=a_eq, b_eq=b_eq, bounds=(0.0, None), method="highs"
    )
    if not solution.success:
        result.feasible = False
        result.notes.append(f"Assignment infeasible: {solution.message}")
        return result

    result.total_cost = float(solution.fun)
    for i in range(n_rows):
        is_dummy = dummy_supply > 0 and i == n_rows - 1
        for j in range(n_cols):
            mass = float(solution.x[i * n_cols + j])
            if mass <= 1e-6:
                continue
            if sink_index is not None and j == sink_index:
                if not is_dummy:
                    result.contaminant_h += mass
                continue
            env = columns[j]
            if is_dummy:
                result.unexplained_h += mass
                continue
            result.assigned[env.key] = result.assigned.get(env.key, 0.0) + mass
            result.flows.append(
                {
                    "signal_index": i,
                    "shift_ppm": round(float(signals[i][0]), 3),
                    "environment": env.key,
                    "kind": env.kind,
                    "assigned_h": round(mass, 3),
                }
            )
    return result


def assign_from_smiles(
    *,
    smiles: str,
    signals: Sequence[tuple[float, float]],
    solvent: str | None = None,
) -> AssignmentResult:
    """Convenience entry: enumerate environments then assign."""
    return assign_signals(
        environments=enumerate_proton_environments(smiles),
        signals=signals,
        solvent=solvent,
    )
