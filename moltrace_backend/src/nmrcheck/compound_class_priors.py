"""Compound-class priors for candidate scoring.

When the SpectraCheck user picks a compound class on the session card, the
backend applies a class-specific *multiplier table* to the default evidence
weights used in :func:`nmrcheck.candidate.compare_candidates`. The result is a
re-weighted, then re-normalised, weight vector that biases the total score
toward whichever evidence layers are most diagnostic for that class.

These multipliers are **transparent heuristics** grounded in standard NMR
practice (see references below). They are not learned from data and should be
calibrated when datasets become available. Every applied override is echoed
in the response metadata under ``compound_class_prior_applied`` so reviewers
can audit what was changed and why.

Components in scope (same names as ``candidate.compare_candidates`` weights):
    structure  — RDKit parse / formula validity
    proton     — observed-vs-predicted 1H scoring
    carbon13   — observed-vs-predicted 13C scoring
    dept_apt   — DEPT/APT multiplicity-consistency scoring
    nmr2d      — 2D NMR (HSQC/HMBC/COSY/NOESY) cross-peak scoring

References shaping the multipliers (selected):
- Carbohydrates: anomeric 1H 4.4–5.5 ppm + 13C 90–110 ppm uniquely diagnostic
  (Duus, Carbohydr. Res. 2000); HSQC near-mandatory for assignment.
- Peptides/proteins: severe 1H amide-region overlap, 13C dispersion better;
  triple-resonance / 2D required for assignment (Cavanagh et al., Protein NMR
  Spectroscopy, 2007).
- Lipids/fatty acids: 1H congestion in aliphatic envelope; 13C and DEPT
  resolve chain and unsaturation patterns (Aursand, Lipids 2000).
- Macrocycles / new scaffolds: connectivity unknown a priori → 2D primary
  evidence (Williamson, Magn. Reson. Chem. 1985, and modern reviews).
- Macromolecules / polymers: ensemble-averaged broad lines → discrete-peak
  comparison loses discrimination (Bovey, Polymer NMR 1972).

Multipliers are intentionally conservative (mostly 0.5x–2.0x) so a wrong
class hint cannot dominate the score; the renormalisation step preserves the
score range and ensures comparability across classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping


# Identity baseline — the "unspecified" class produces no weight changes.
_NO_OVERRIDE: Final[dict[str, float]] = {
    "structure": 1.0,
    "proton": 1.0,
    "carbon13": 1.0,
    "dept_apt": 1.0,
    "nmr2d": 1.0,
}


# Per-class multiplier table. Each entry overrides a subset of components;
# anything not listed defaults to 1.0 (i.e. unchanged). After multipliers are
# applied, weights are renormalised so they sum back to 1.0.
# Keys sorted alphabetically by canonical identifier for findability.
COMPOUND_CLASS_WEIGHT_MULTIPLIERS: Final[Mapping[str, Mapping[str, float]]] = {
    "alkaloids": {
        # Nitrogen environments shift carbons distinctively; both 1H and 13C
        # useful; 2D resolves N-adjacent stereochemistry.
        "carbon13": 1.20,
        "nmr2d": 1.30,
    },
    "carbohydrates": {
        # Anomeric 1H + 13C are uniquely diagnostic; HSQC near-mandatory.
        "proton": 1.20,
        "carbon13": 1.30,
        "nmr2d": 1.50,
        "structure": 0.80,
    },
    "fatty_acids": {
        # Same rationale as lipids; methyl/terminal-CH₃ DEPT signature strong.
        "proton": 0.75,
        "carbon13": 1.25,
        "dept_apt": 1.70,
    },
    "flavonoids": {
        # Aromatic 1H + 13C distinctive; 2D for ring linkages and sugar attach.
        "proton": 1.10,
        "carbon13": 1.20,
        "nmr2d": 1.40,
    },
    "glycoproteins": {
        # Combines carbohydrate + protein NMR challenges; 2D primary evidence.
        "proton": 0.70,
        "carbon13": 1.20,
        "nmr2d": 1.80,
        "structure": 0.85,
    },
    "lipids": {
        # 1H crowding in aliphatic envelope; 13C and DEPT resolve chain & unsat.
        "proton": 0.70,
        "carbon13": 1.30,
        "dept_apt": 1.60,
    },
    "macrocycles": {
        # Unknown connectivity → 2D primary; structure validity is less
        # informative because of conformational ambiguity.
        "nmr2d": 1.80,
        "carbon13": 1.15,
        "structure": 0.75,
    },
    "macromolecules": {
        # Broad lines, ensemble averaging — discrete-peak comparison loses
        # discrimination; downweight peak-based layers, keep validity.
        "proton": 0.55,
        "carbon13": 0.65,
        "dept_apt": 0.70,
        "nmr2d": 0.85,
    },
    "natural_products": {
        # Diverse skeletons; connectivity from 2D often decisive, 13C diagnostic.
        "carbon13": 1.10,
        "nmr2d": 1.25,
    },
    "new_scaffolds": {
        # By definition unknown → connectivity from 2D is the only firm
        # ground; 1H and 13C still informative but not decisive.
        "nmr2d": 1.80,
        "carbon13": 1.20,
    },
    "nucleic_acids": {
        # Base aromatic 1H distinctive; 13C ribose/phosphate context useful;
        # 2D essential for through-bond / through-space assignment.
        "proton": 1.15,
        "carbon13": 1.15,
        "nmr2d": 1.40,
    },
    "organometallics": {
        # Paramagnetic / heavy-atom shifts can confound predicted spectra;
        # 13C/2D remain useful, 1H less reliable.
        "proton": 0.80,
        "carbon13": 1.15,
        "nmr2d": 1.25,
    },
    "peptides": {
        # Amide overlap → downweight 1H; 13C dispersion + 2D do the work.
        "proton": 0.65,
        "carbon13": 1.25,
        "nmr2d": 1.70,
    },
    "polymers": {
        # Same broad-line argument as macromolecules; cap reliance on peak
        # comparison; structure validity (formula match) is more meaningful.
        "proton": 0.45,
        "carbon13": 0.55,
        "dept_apt": 0.60,
        "nmr2d": 0.75,
        "structure": 1.30,
    },
    "proteins": {
        # Heavy overlap; 2D + isotope-edited experiments mandatory.
        "proton": 0.50,
        "carbon13": 1.20,
        "nmr2d": 2.00,
        "structure": 0.85,
    },
    "small_molecules": {
        # Standard organics: default weighting works well; tiny bump to 2D for
        # connectivity confirmation on close isomers.
        "nmr2d": 1.10,
    },
    "steroids": {
        # Characteristic angular-methyl signatures (DEPT); 13C very diagnostic.
        "carbon13": 1.30,
        "dept_apt": 1.55,
        "nmr2d": 1.20,
    },
    "terpenoids": {
        # Methyl multiplicity (DEPT) + 2D connectivity carry the assignment.
        "carbon13": 1.20,
        "dept_apt": 1.60,
        "nmr2d": 1.30,
    },
}


# Diagnostic chemical-shift windows per compound class, by nucleus. Peak
# detection applies a modestly lower (more sensitive) noise factor inside these
# windows: they hold each class's most diagnostic signals — anomeric
# carbohydrate resonances, peptide amide NH, steroid angular methyls, olefinic
# lipid carbons — which are frequently weak or congested and the first lost to a
# uniform threshold. Windows are ``(lo_ppm, hi_ppm)`` and intentionally broad;
# they are standard-practice heuristics grounded in the same references as the
# multiplier table above. Classes without a single tight diagnostic region are
# omitted (detection then uses its normal uniform noise threshold).
COMPOUND_CLASS_DIAGNOSTIC_REGIONS: Final[
    Mapping[str, Mapping[str, tuple[tuple[float, float], ...]]]
] = {
    "alkaloids": {
        "1H": ((2.2, 4.2),),  # N-adjacent CH
        "13C": ((40.0, 70.0),),
    },
    "carbohydrates": {
        "1H": ((4.3, 5.6),),  # anomeric protons
        "13C": ((90.0, 112.0),),  # anomeric carbons
    },
    "fatty_acids": {
        "1H": ((5.1, 5.6),),  # olefinic
        "13C": ((125.0, 132.0), (165.0, 180.0)),  # olefinic + carbonyl
    },
    "flavonoids": {
        "1H": ((6.0, 8.3),),  # aromatic / olefinic
        "13C": ((95.0, 165.0),),
    },
    "glycoproteins": {
        "1H": ((4.3, 5.6), (6.0, 8.8)),
        "13C": ((90.0, 112.0), (168.0, 182.0)),
    },
    "lipids": {
        "1H": ((5.1, 5.6),),  # olefinic
        "13C": ((125.0, 132.0), (165.0, 180.0)),
    },
    "nucleic_acids": {
        "1H": ((5.2, 8.5),),  # base + anomeric
        "13C": ((70.0, 160.0),),
    },
    "peptides": {
        "1H": ((6.0, 8.8),),  # amide NH
        "13C": ((168.0, 182.0),),  # carbonyl
    },
    "proteins": {
        "1H": ((6.0, 8.8),),
        "13C": ((168.0, 182.0),),
    },
    "steroids": {
        "1H": ((0.5, 1.3),),  # angular methyls
        "13C": ((10.0, 25.0),),
    },
    "terpenoids": {
        "1H": ((0.5, 1.8),),  # methyls
        "13C": ((10.0, 32.0),),
    },
}


def diagnostic_regions_for(
    compound_class: str | None,
    nucleus: str,
) -> tuple[tuple[float, float], ...]:
    """Return the diagnostic ppm windows for a compound class on a nucleus.

    ``nucleus`` is ``"1H"`` or ``"13C"``. Returns an empty tuple for an
    unspecified / unrecognised class, or one with no tight diagnostic region —
    in which case detection uses its normal uniform noise threshold.
    """
    if not compound_class:
        return ()
    by_nucleus = COMPOUND_CLASS_DIAGNOSTIC_REGIONS.get(compound_class.strip().lower())
    if not by_nucleus:
        return ()
    return tuple(by_nucleus.get(nucleus, ()))


@dataclass(frozen=True)
class CompoundClassPriorReport:
    """Audit record of a per-class prior application.

    Includes the original and post-renormalisation weights so a reviewer can
    see exactly how the class hint shifted the scoring without re-running.
    """

    compound_class: str
    original_weights: dict[str, float]
    multipliers: dict[str, float]
    renormalised_weights: dict[str, float]
    notes: list[str]

    def to_metadata(self) -> dict[str, object]:
        """Serialise into the shape used in CandidateComparisonResult metadata."""
        return {
            "compound_class": self.compound_class,
            "original_weights": dict(self.original_weights),
            "multipliers": dict(self.multipliers),
            "renormalised_weights": dict(self.renormalised_weights),
            "notes": list(self.notes),
        }


def apply_compound_class_weights(
    base_weights: Mapping[str, float],
    compound_class: str | None,
) -> tuple[dict[str, float], CompoundClassPriorReport | None]:
    """Return ``(adjusted_weights, report)``.

    If ``compound_class`` is falsy or not in the table, returns
    ``(dict(base_weights), None)`` — i.e. caller behaviour is unchanged.

    Otherwise the multiplier for each component is applied, the result is
    renormalised to sum to 1.0, and a :class:`CompoundClassPriorReport` is
    returned alongside for response metadata.
    """
    if not compound_class:
        return dict(base_weights), None
    multipliers_for_class = COMPOUND_CLASS_WEIGHT_MULTIPLIERS.get(compound_class)
    if multipliers_for_class is None:
        return dict(base_weights), None

    full_multipliers = {key: 1.0 for key in base_weights}
    for key, factor in multipliers_for_class.items():
        if key in full_multipliers:
            full_multipliers[key] = float(factor)

    adjusted: dict[str, float] = {
        key: float(base_weights[key]) * float(full_multipliers[key]) for key in base_weights
    }
    total = sum(adjusted.values()) or 1.0
    renormalised = {key: round(value / total, 6) for key, value in adjusted.items()}

    # Build human-readable notes for the audit metadata.
    moved_up = [
        f"{key} weight {base_weights[key]:.2f} → {renormalised[key]:.2f} (×{full_multipliers[key]:.2f})"
        for key in renormalised
        if full_multipliers[key] != 1.0 and renormalised[key] > base_weights[key]
    ]
    moved_down = [
        f"{key} weight {base_weights[key]:.2f} → {renormalised[key]:.2f} (×{full_multipliers[key]:.2f})"
        for key in renormalised
        if full_multipliers[key] != 1.0 and renormalised[key] < base_weights[key]
    ]
    notes: list[str] = [
        f"Class prior '{compound_class}' applied to candidate scoring weights.",
        "Multipliers are heuristic; calibrate per dataset before use as a regulatory deliverable.",
    ]
    if moved_up:
        notes.append("Up-weighted: " + "; ".join(moved_up))
    if moved_down:
        notes.append("Down-weighted: " + "; ".join(moved_down))

    report = CompoundClassPriorReport(
        compound_class=compound_class,
        original_weights={key: float(value) for key, value in base_weights.items()},
        multipliers=full_multipliers,
        renormalised_weights=renormalised,
        notes=notes,
    )
    return renormalised, report


def class_has_explicit_prior(compound_class: str | None) -> bool:
    """True iff the class has a non-trivial multiplier set defined."""
    if not compound_class:
        return False
    overrides = COMPOUND_CLASS_WEIGHT_MULTIPLIERS.get(compound_class)
    return overrides is not None and any(factor != 1.0 for factor in overrides.values())


# Silence unused-import lints when callers only need the identity baseline.
__all__ = [
    "COMPOUND_CLASS_WEIGHT_MULTIPLIERS",
    "CompoundClassPriorReport",
    "apply_compound_class_weights",
    "class_has_explicit_prior",
    "_NO_OVERRIDE",
]
