"""What a structure predicts a 2D spectrum should contain.

The 2D layer scored observed cross peaks against 1D reference shift lists, and
derived its denominator from the peaks it happened to find. Measured on
ibuprofen, withholding five of seven HSQC correlations scored *higher* than
showing all seven (0.8218 vs 0.8047), and `missing_reference_count` reported 0
throughout — see `docs/validation_playbook_2d_nmr.md`, C1 RESULT.

This module supplies the missing half: the **expected** correlations, derived
from the structure, so a denominator can exist that does not depend on the
observation.

Scope is deliberately one-bond HSQC/HMQC. HMBC is not here because its expected
set is a different problem — 2- and 3-bond correlations, frequently 4 through
conjugation, and 2-bond ones are often absent, so an expected-set denominator for
HMBC would punish correct structures. See C5.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ExpectedCorrelation",
    "CorrelationCoverage",
    "expected_hsqc_correlations",
    "match_expected_correlations",
]


@dataclass(frozen=True)
class ExpectedCorrelation:
    """One predicted one-bond H–C cross peak."""

    proton_ppm: float
    carbon_ppm: float
    attached_h: int
    carbon_type: str | None = None
    #: How many symmetry-equivalent atoms collapsed into this one expectation.
    #: 1 for a unique environment; 2 for a pair of equivalent methyls, and so on.
    equivalent_atoms: int = 1


@dataclass(frozen=True)
class CorrelationCoverage:
    """How much of what the structure predicts was actually observed."""

    expected_count: int
    matched_count: int
    missing_count: int
    unexpected_count: int
    #: matched / expected. 0.0 when nothing is expected — callers must check
    #: ``expected_count`` before reading this, exactly as an error statistic is
    #: meaningless without its denominator.
    coverage: float


def _symmetry_classes(smiles: str) -> dict[int, int] | None:
    """Map atom index -> symmetry class, from the molecular graph.

    Collapsing on *predicted shifts* was the first attempt and it was wrong: the
    heuristic predictor returns 14.00 ppm for all three ibuprofen methyls and
    129.0 for all four aromatic CH, so shift-based collapse merged chemically
    distinct environments and produced 5 expectations where a real HSQC shows 7.
    That would make the denominator too small — coverage could exceed 100 %, and
    two genuine cross peaks would compete for one expectation.

    Equivalence is a property of the molecule, not of the predictor's resolution.
    RDKit's canonical ranking with ``breakTies=False`` assigns one rank per
    symmetry class, which is exactly the constitutional equivalence that makes
    two protons give one cross peak.
    """
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
        return {index: int(rank) for index, rank in enumerate(ranks)}
    except Exception:
        return None


def expected_hsqc_correlations(smiles: str | None) -> list[ExpectedCorrelation]:
    """Predicted one-bond H–C correlations for ``smiles``.

    Returns ``[]`` when there is no structure, when it cannot be parsed, or when
    the structure genuinely has no C–H (CCl4). Those are different situations and
    the caller must not conflate them — check the structure separately rather
    than reading an empty list as "nothing expected".

    **Symmetry-equivalent atoms collapse to one expectation.** Ibuprofen has ten
    protonated carbons but its two isopropyl methyls, and each aromatic CH pair,
    are equivalent; a real HSQC shows about seven cross peaks. Counting atoms
    would make the denominator systematically too large and every correct
    structure look incomplete — the same "allocation rather than measurement"
    error that the 1D integration apportionment had.

    Quaternary carbons are absent by construction (``attached_h == 0``), so they
    never enter the denominator. Their absence from a spectrum is expected, and
    scoring them as misses would penalise every correct structure.
    """
    if not smiles or not str(smiles).strip():
        return []

    try:
        from .nmr_prediction import predict_nmr_from_smiles_fast

        report = predict_nmr_from_smiles_fast(str(smiles).strip(), name=None, solvent=None)
    except Exception:
        # An unparseable structure predicts nothing. It must not raise into a
        # scoring path -- but it must also not look like a confident zero.
        return []

    # atom_index on BOTH peak lists refers to the carbon, so a 1H peak and a 13C
    # peak sharing an index are the two halves of one correlation.
    proton_by_atom: dict[int, float] = {}
    for peak in report.proton_peaks:
        if peak.atom_index is not None and peak.atom_index not in proton_by_atom:
            proton_by_atom[peak.atom_index] = float(peak.shift_ppm)

    classes = _symmetry_classes(str(smiles).strip())
    by_class: dict[object, ExpectedCorrelation] = {}
    order: list[object] = []

    for carbon in report.carbon13_peaks:
        attached = int(carbon.attached_h or 0)
        if attached <= 0:
            continue  # quaternary: no one-bond correlation to expect
        if carbon.atom_index is None:
            continue
        proton_ppm = proton_by_atom.get(carbon.atom_index)
        if proton_ppm is None:
            continue

        # Fall back to the atom itself when symmetry perception is unavailable:
        # over-counting environments is the safer failure, because it makes a
        # spectrum look incomplete rather than making an incomplete one look full.
        key: object = (
            classes.get(carbon.atom_index, carbon.atom_index)
            if classes is not None
            else carbon.atom_index
        )
        existing = by_class.get(key)
        if existing is None:
            by_class[key] = ExpectedCorrelation(
                proton_ppm=proton_ppm,
                carbon_ppm=float(carbon.shift_ppm),
                attached_h=attached,
                carbon_type=carbon.carbon_type,
            )
            order.append(key)
        else:
            by_class[key] = ExpectedCorrelation(
                proton_ppm=existing.proton_ppm,
                carbon_ppm=existing.carbon_ppm,
                attached_h=existing.attached_h,
                carbon_type=existing.carbon_type,
                equivalent_atoms=existing.equivalent_atoms + 1,
            )

    collapsed = [by_class[k] for k in order]
    collapsed.sort(key=lambda c: (c.carbon_ppm, c.proton_ppm))
    return collapsed


def match_expected_correlations(
    expected: list[ExpectedCorrelation],
    observed: list[tuple[float, float]],
    *,
    proton_tolerance_ppm: float,
    carbon_tolerance_ppm: float,
) -> CorrelationCoverage:
    """Match observed ``(proton_ppm, carbon_ppm)`` pairs against ``expected``.

    The tolerance is **rectangular** — separate windows per axis — because the
    two dimensions do not have remotely comparable precision. A 1H shift is
    reproducible to a few hundredths of a ppm while a predicted 13C shift is
    routinely several ppm out. A single circular tolerance would have to be wide
    enough for the carbon axis and would then accept nearly anything on the
    proton axis, which is the "same ruler for every atom" error already corrected
    in the 1D verifier.

    Both tolerances are caller-supplied on purpose: they belong to the predictor's
    measured per-axis residual distribution, not to this function. Passing round
    numbers here is a caller bug, not a default this module should invent.

    Each expectation matches at most once, so a single observed peak sitting
    between two expectations cannot satisfy both.

    **Not used by the 2D analyzer, and that is deliberate.** ``nmr2d_analyzer``
    scores structural coverage by matching against the OBSERVED 1D shifts and takes
    only the denominator from the structure, because matching against predicted
    shifts is ambiguous at any window: measured over six molecules / 57 expectations,
    the share of predictions with at least one rival prediction inside the window is
    84.2 % at the pooled 90 % window, 80.7 % at the (tighter, measured) conformal 90 %
    window, and still 77.2 % at +/-0.15 / +/-2.0 ppm. Expected correlations cluster
    because the chemistry does.

    Two further properties matter to any future caller. The matching here is greedy
    first-fit in expectation order, not an optimal assignment and not even
    nearest-first, so with several candidates per expectation it can consume a peak a
    later expectation needed and undercount -- and the result depends on the order
    ``expected`` arrives in. That is fine for the sparse, well-separated cases the
    tests cover; it is not fine as a coverage metric on a crowded aliphatic region.
    """
    remaining = list(observed)
    matched = 0

    for want in expected:
        for index, (obs_h, obs_c) in enumerate(remaining):
            if (
                abs(obs_h - want.proton_ppm) <= proton_tolerance_ppm
                and abs(obs_c - want.carbon_ppm) <= carbon_tolerance_ppm
            ):
                matched += 1
                remaining.pop(index)
                break

    expected_count = len(expected)
    return CorrelationCoverage(
        expected_count=expected_count,
        matched_count=matched,
        missing_count=expected_count - matched,
        # Observed peaks that matched nothing expected. Not necessarily an
        # error -- impurities, artifacts and a wrong candidate all land here --
        # but it is the other half of the picture and must be visible.
        unexpected_count=len(remaining),
        coverage=(matched / expected_count) if expected_count else 0.0,
    )
