"""Topological-empirical prediction of diagnostic 1H-1H J couplings.

This module mirrors the philosophy of ``nmr_prediction.py``: it uses RDKit to
read atom/bond *topology* and assigns empirical, literature-central coupling
magnitudes per coupling category.  By default it does **not** use Karplus
relations or 3D geometry — the house style is transparent empirical regions
with documented uncertainty.  An **opt-in** refinement (``use_karplus=True``)
replaces the flat empirical aliphatic vicinal value with a conformer-averaged
``3J`` read from an RDKit ETKDG ensemble.  Two equations are offered via
``karplus_method``: the default generic three-term Karplus relation
(:func:`karplus_3j`) and the electronegativity/orientation-corrected
Haasnoot–de Leeuw–Altona generalized Karplus relation
(:func:`haasnoot_altona_3j`, ``karplus_method="haasnoot_altona"``), which
adds substituent-electronegativity corrections that matter for sugars and
other heteroatom-rich vicinal couplings.  Both are decision-support only and
leave the alkene/aromatic categories untouched.

The output is a *compact, distinct* set of coupling magnitudes (Hz) that the
structure is expected to produce.  It feeds the multiplet -> unified-confidence
bridge (``multiplet_jcoupling_bridge.py``), which scores recovered observed J
values (from the Prompt 4 multiplet analyser) against this predicted set.

Empirical central values (Hz) are taken from standard references
(Silverstein 8e App. F; Pretsch 5e §H.4; Friebolin 5e Ch. 3):

* trans (E) alkene 3J ............ 12-18, central ~16.5 (terminal vinyl ~17.0)
* cis (Z) alkene 3J .............. 6-12, central ~11.0 (terminal vinyl ~10.8)
* aromatic ortho 3J .............. 6-9, central ~7.8
* aromatic meta 4J ............... 1-3, central ~2.0
* 6-membered N-heteroaromatic a-b 3J (e.g. pyridine H2-H3) ~4.8
* aliphatic vicinal 3J (freely rotating) ~7.0

Scope (v1): 6-membered aromatic / N-heteroaromatic rings, acyclic & ring
alkenes, and aliphatic vicinal couplings.  Geminal (2J) and long-range
(<1 Hz) couplings are intentionally not emitted as diagnostic couplings.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from rdkit import Chem

from .chemistry import mol_from_smiles
from .exceptions import StructureParseError

# Representative diagnostic 1H-1H coupling magnitudes (Hz) keyed by topological
# category.  Central empirical values; see module docstring for provenance.
COUPLING_HZ: dict[str, float] = {
    "vinyl_trans": 17.0,
    "vinyl_cis": 10.8,
    "alkene_trans": 16.5,
    "alkene_cis": 11.0,
    "aromatic_ortho": 7.8,
    "aromatic_meta": 2.0,
    "heteroaromatic_alpha_beta": 4.8,
    "aliphatic_vicinal": 7.0,
}

# Couplings below this magnitude (Hz) are not reliably resolvable in routine 1D
# 1H and are not emitted as diagnostic couplings.
MIN_DIAGNOSTIC_HZ = 1.0
# Couplings whose magnitudes fall within this window (Hz) are merged into one
# representative during compaction so the predicted set stays distinct/compact
# (and so the similarity denominator is not inflated by near-duplicates).
COMPACTION_TOLERANCE_HZ = 0.75

# --- Opt-in geometry-aware vicinal 3J refinement (Karplus) -----------------
# Generic three-term Karplus relation for vicinal 3J(H-C-C-H):
#     3J(theta) = A*cos^2(theta) + B*cos(theta) + C   (theta = H-C-C-H dihedral)
# Constants are a commonly-tabulated generic parameterization for H-C-C-H
# (Karplus, J. Chem. Phys. 1959, 30, 11; J. Am. Chem. Soc. 1963, 85, 2870; the
# A/B/C values as widely cited, e.g. Pretsch et al. 5e).  Curve check:
# 3J(0deg) ~ 8.1, 3J(90deg) ~ 1.4 (minimum), 3J(180deg) ~ 10.3 Hz -- the
# antiperiplanar coupling is largest, the textbook shape.  This refines ONLY
# aliphatic vicinal couplings; the default predictor stays topology-only.
KARPLUS_A = 7.76
KARPLUS_B = -1.10
KARPLUS_C = 1.40
# Size of the RDKit ETKDG conformer ensemble averaged per H-C-C-H pair.
KARPLUS_DEFAULT_MAX_CONFORMERS = 12
# Fixed embedding seed so the opt-in refinement is reproducible run-to-run.
KARPLUS_RANDOM_SEED = 0xC0FFEE

# --- Opt-in Haasnoot-de Leeuw-Altona generalized Karplus refinement ---------
# The generic three-term relation above ignores the electronegativity and
# relative orientation of the substituents on the two coupling carbons, so it
# under-predicts heteroatom-rich vicinal couplings (its 180-deg antiperiplanar
# value caps near 10.26 Hz).  Haasnoot, de Leeuw & Altona (Tetrahedron 1980,
# 36, 2783) generalized Karplus to:
#     3J = P1 cos^2(phi) + P2 cos(phi) + P3
#          + SUM_i d_chi_i * [P4 + P5 cos^2(xi_i*phi + P6*|d_chi_i|)]
# where d_chi_i is the Huggins electronegativity difference (chi_X - chi_H) of
# substituent i on the two coupling carbons and xi_i = +/-1 encodes its
# orientation relative to the coupling protons (read from 3D geometry).  We use
# the widely-cited six-parameter set; the second-shell (beta) "group
# electronegativity" P7 refinement is intentionally not applied in v1.  Sanity:
# the pure-hydrocarbon antiperiplanar value (only small d_chi=0.40 carbon
# corrections) is ~13 Hz, while a pyranose diaxial (two equatorial-oxygen
# corrections) is pulled down to ~9.5 Hz -- matching the sugar literature the
# generic relation misses.
HAASNOOT_P1 = 13.86
HAASNOOT_P2 = -0.81
HAASNOOT_P3 = 0.0
HAASNOOT_P4 = 0.56
HAASNOOT_P5 = -2.32
HAASNOOT_P6_DEG = 17.9

# Huggins electronegativities chi(X) keyed by atomic number; the HLA correction
# sums over d_chi = chi(X) - chi(H).  Elements absent from this table contribute
# no correction (d_chi treated as 0.0) so the refinement degrades safely.
_HUGGINS_ELECTRONEGATIVITY: dict[int, float] = {
    1: 2.20,   # H (reference)
    6: 2.60,   # C
    7: 3.05,   # N
    8: 3.50,   # O
    9: 4.00,   # F
    14: 1.90,  # Si
    15: 2.15,  # P
    16: 2.60,  # S
    17: 3.15,  # Cl
    35: 2.95,  # Br
    53: 2.65,  # I
}
_HUGGINS_HYDROGEN = 2.20

# Method selector values for the opt-in vicinal-3J refinement.
KARPLUS_METHOD_GENERIC = "generic"
KARPLUS_METHOD_HAASNOOT_ALTONA = "haasnoot_altona"
KARPLUS_METHODS = (KARPLUS_METHOD_GENERIC, KARPLUS_METHOD_HAASNOOT_ALTONA)
KARPLUS_DEFAULT_METHOD = KARPLUS_METHOD_GENERIC

# Detail-category labels emitted per refinement method, so a consumer can see
# which equation produced a refined coupling.
KARPLUS_CATEGORY_GENERIC = "aliphatic_vicinal_karplus"
KARPLUS_CATEGORY_HAASNOOT_ALTONA = "aliphatic_vicinal_haasnoot_altona"

# --- Opt-in Boltzmann conformer-population weighting -------------------------
# The refinement above averages each H-C-C-H dihedral *unweighted* across the
# ETKDG ensemble, which over-weights high-energy ring-flipped conformers and
# washes out the diagnostic ground-state diaxial of strongly-anchored systems.
# The opt-in ``conformer_weighting='boltzmann'`` setting replaces the uniform
# mean with a Boltzmann-weighted one, w_i = exp(-(E_i - E_min)/RT), using the
# per-conformer MMFF energies (kcal/mol) returned by MMFFOptimizeMoleculeConfs.
# It is orthogonal to ``karplus_method`` (it weights whichever relation is in
# use) and degrades safely to uniform averaging when energies are unavailable.
BOLTZMANN_GAS_CONSTANT_KCAL = 1.987204259e-3  # R, kcal/(mol*K)
BOLTZMANN_TEMPERATURE_K = 298.15  # standard ambient temperature
BOLTZMANN_RT_KCAL_MOL = BOLTZMANN_GAS_CONSTANT_KCAL * BOLTZMANN_TEMPERATURE_K  # ~0.5925
CONFORMER_WEIGHTING_UNIFORM = "uniform"
CONFORMER_WEIGHTING_BOLTZMANN = "boltzmann"
CONFORMER_WEIGHTINGS = (CONFORMER_WEIGHTING_UNIFORM, CONFORMER_WEIGHTING_BOLTZMANN)
CONFORMER_WEIGHTING_DEFAULT = CONFORMER_WEIGHTING_UNIFORM


def karplus_3j(
    theta_deg: float,
    *,
    a: float = KARPLUS_A,
    b: float = KARPLUS_B,
    c: float = KARPLUS_C,
) -> float:
    """Vicinal ``3J(H-C-C-H)`` in Hz from a dihedral angle (degrees).

    Generic three-term Karplus relation ``A*cos^2(t) + B*cos(t) + C``; the
    result is clamped at ``>= 0`` Hz.  Antiperiplanar (~180 deg) gives the
    largest coupling and the minimum sits near 90 deg -- the standard Karplus
    curve.
    """
    theta = math.radians(theta_deg)
    cos_t = math.cos(theta)
    return max(0.0, a * cos_t * cos_t + b * cos_t + c)


def _delta_chi(atomic_num: int) -> float:
    """Huggins electronegativity difference ``chi(X) - chi(H)`` for an element.

    Returns ``0.0`` for elements absent from :data:`_HUGGINS_ELECTRONEGATIVITY`
    so an exotic substituent simply contributes no Haasnoot-Altona correction.
    """
    chi = _HUGGINS_ELECTRONEGATIVITY.get(int(atomic_num))
    if chi is None:
        return 0.0
    return chi - _HUGGINS_HYDROGEN


def _wrap_180(angle_deg: float) -> float:
    """Wrap an angle (degrees) into ``[-180, 180)`` for relative-sign tests."""
    return (angle_deg + 180.0) % 360.0 - 180.0


def haasnoot_altona_3j(
    theta_deg: float,
    substituents: Iterable[tuple[float, float]] = (),
    *,
    p1: float = HAASNOOT_P1,
    p2: float = HAASNOOT_P2,
    p3: float = HAASNOOT_P3,
    p4: float = HAASNOOT_P4,
    p5: float = HAASNOOT_P5,
    p6_deg: float = HAASNOOT_P6_DEG,
) -> float:
    """Vicinal ``3J(H-C-C-H)`` in Hz from the Haasnoot-de Leeuw-Altona relation.

    The electronegativity/orientation-corrected generalized Karplus equation
    (Haasnoot, de Leeuw & Altona, Tetrahedron 1980, 36, 2783):

        3J = P1 cos^2(phi) + P2 cos(phi) + P3
             + SUM_i d_chi_i * [P4 + P5 cos^2(xi_i*phi + P6*|d_chi_i|)]

    ``theta_deg`` is the H-C-C-H dihedral ``phi`` (degrees).  ``substituents`` is
    an iterable of ``(delta_chi, xi)`` pairs -- one per non-hydrogen substituent
    on the two coupling carbons -- where ``delta_chi`` is the Huggins
    electronegativity difference ``chi_X - chi_H`` (see :func:`_delta_chi`) and
    ``xi`` is the orientation sign (``+1.0``/``-1.0``) of that substituent
    relative to the coupling protons.  With no substituents the relation reduces
    to a bare three-term Karplus curve with the HLA ``P1..P3`` constants.  The
    result is clamped at ``>= 0`` Hz.
    """
    theta = math.radians(theta_deg)
    cos_t = math.cos(theta)
    total = p1 * cos_t * cos_t + p2 * cos_t + p3
    for delta_chi, xi in substituents:
        arg = math.radians(xi * theta_deg + p6_deg * abs(delta_chi))
        cos_arg = math.cos(arg)
        total += delta_chi * (p4 + p5 * cos_arg * cos_arg)
    return max(0.0, total)


@dataclass(frozen=True)
class PredictedCoupling:
    """One predicted diagnostic coupling with its topological provenance."""

    category: str
    j_hz: float
    atom_indices: tuple[int, int]


@dataclass
class PredictedCouplingSet:
    """Compact set of distinct coupling magnitudes a structure can produce."""

    smiles: str
    couplings_hz: list[float] = field(default_factory=list)  # compacted, desc
    details: list[PredictedCoupling] = field(default_factory=list)
    max_predicted_hz: float = 0.0
    category_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    invalid_structure: bool = False


def _bonded_to_aromatic_nitrogen(atom: Chem.Atom) -> bool:
    return any(
        neighbor.GetAtomicNum() == 7 and neighbor.GetIsAromatic()
        for neighbor in atom.GetNeighbors()
    )


def _enumerate_couplings(mol: Chem.Mol) -> list[PredictedCoupling]:
    details: list[PredictedCoupling] = []

    # Pass 1 -- couplings carried directly by a bond between two protonated
    # carbons (vicinal 3J across single/double bonds; ortho/alpha-beta across
    # aromatic bonds).
    for bond in mol.GetBonds():
        begin = bond.GetBeginAtom()
        end = bond.GetEndAtom()
        if begin.GetAtomicNum() != 6 or end.GetAtomicNum() != 6:
            continue
        h_begin = int(begin.GetTotalNumHs(includeNeighbors=False))
        h_end = int(end.GetTotalNumHs(includeNeighbors=False))
        if h_begin <= 0 or h_end <= 0:
            continue
        pair = (begin.GetIdx(), end.GetIdx())
        bond_type = bond.GetBondType()

        if bond.GetIsAromatic() or bond_type == Chem.BondType.AROMATIC:
            # Exactly one carbon adjacent to a ring N -> alpha,beta coupling
            # (e.g. pyridine/quinoline H2-H3 ~4.8 Hz); otherwise standard ortho.
            if _bonded_to_aromatic_nitrogen(begin) ^ _bonded_to_aromatic_nitrogen(end):
                details.append(
                    PredictedCoupling(
                        "heteroaromatic_alpha_beta",
                        COUPLING_HZ["heteroaromatic_alpha_beta"],
                        pair,
                    )
                )
            else:
                details.append(
                    PredictedCoupling("aromatic_ortho", COUPLING_HZ["aromatic_ortho"], pair)
                )
        elif (
            bond_type == Chem.BondType.DOUBLE
            and not begin.GetIsAromatic()
            and not end.GetIsAromatic()
        ):
            terminal_vinyl = h_begin >= 2 or h_end >= 2
            stereo = bond.GetStereo()
            if terminal_vinyl:
                # Mono-substituted vinyl: both trans (~17) and cis (~10.8) are
                # observed across the =CH2 protons.
                details.append(
                    PredictedCoupling("vinyl_trans", COUPLING_HZ["vinyl_trans"], pair)
                )
                details.append(
                    PredictedCoupling("vinyl_cis", COUPLING_HZ["vinyl_cis"], pair)
                )
            elif stereo in (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOTRANS):
                details.append(
                    PredictedCoupling("alkene_trans", COUPLING_HZ["alkene_trans"], pair)
                )
            elif stereo in (Chem.BondStereo.STEREOZ, Chem.BondStereo.STEREOCIS):
                details.append(
                    PredictedCoupling("alkene_cis", COUPLING_HZ["alkene_cis"], pair)
                )
            else:
                # Undefined stereochemistry: the structure is *capable* of
                # either geometry, so emit both diagnostic magnitudes.
                details.append(
                    PredictedCoupling("alkene_trans", COUPLING_HZ["alkene_trans"], pair)
                )
                details.append(
                    PredictedCoupling("alkene_cis", COUPLING_HZ["alkene_cis"], pair)
                )
        elif (
            bond_type == Chem.BondType.SINGLE
            and not begin.GetIsAromatic()
            and not end.GetIsAromatic()
        ):
            details.append(
                PredictedCoupling("aliphatic_vicinal", COUPLING_HZ["aliphatic_vicinal"], pair)
            )

    # Pass 2 -- aromatic meta (4J) within 6-membered aromatic rings.  Enumerate
    # 1,3 protonated-carbon pairs; dedupe so each pair contributes once.
    ring_info = mol.GetRingInfo()
    seen_meta: set[frozenset[int]] = set()
    for ring in ring_info.AtomRings():
        if len(ring) != 6:
            continue
        if not all(mol.GetAtomWithIdx(idx).GetIsAromatic() for idx in ring):
            continue
        size = len(ring)
        for i in range(size):
            a_idx = ring[i]
            c_idx = ring[(i + 2) % size]
            atom_a = mol.GetAtomWithIdx(a_idx)
            atom_c = mol.GetAtomWithIdx(c_idx)
            if atom_a.GetAtomicNum() != 6 or atom_c.GetAtomicNum() != 6:
                continue
            if (
                int(atom_a.GetTotalNumHs(includeNeighbors=False)) <= 0
                or int(atom_c.GetTotalNumHs(includeNeighbors=False)) <= 0
            ):
                continue
            key = frozenset((a_idx, c_idx))
            if key in seen_meta:
                continue
            seen_meta.add(key)
            details.append(
                PredictedCoupling("aromatic_meta", COUPLING_HZ["aromatic_meta"], (a_idx, c_idx))
            )

    return details


def _compact(values: list[float], tolerance: float) -> list[float]:
    """Single-linkage cluster near-identical magnitudes into representatives."""
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    means = [round(sum(cluster) / len(cluster), 2) for cluster in clusters]
    return sorted(means, reverse=True)


def _boltzmann_weights(
    energies: list[float], *, rt_kcal_mol: float = BOLTZMANN_RT_KCAL_MOL
) -> list[float] | None:
    """Normalized Boltzmann weights from per-conformer MMFF energies (kcal/mol).

    ``w_i = exp(-(E_i - E_min) / RT)`` then normalized to sum to 1.  Returns
    ``None`` when the energies are unusable (empty or non-finite) so the caller
    can fall back to uniform averaging rather than crash or silently mis-weight.
    """
    if not energies or any(not math.isfinite(e) for e in energies):
        return None
    e_min = min(energies)
    weights = [math.exp(-(e - e_min) / rt_kcal_mol) for e in energies]
    total = math.fsum(weights)
    if not math.isfinite(total) or total <= 0.0:
        return None
    return [w / total for w in weights]


def _refine_vicinal_with_karplus(
    mol: Chem.Mol,
    details: list[PredictedCoupling],
    *,
    method: str = KARPLUS_DEFAULT_METHOD,
    weighting: str = CONFORMER_WEIGHTING_DEFAULT,
    max_conformers: int,
    seed: int,
    warnings: list[str],
) -> list[PredictedCoupling]:
    """Replace flat empirical ``aliphatic_vicinal`` couplings with conformer-
    averaged vicinal ``3J`` values read from an RDKit ETKDG ensemble.

    ``method`` selects the relation applied to each H-C-C-H dihedral: the
    default ``"generic"`` three-term Karplus (:func:`karplus_3j`) or
    ``"haasnoot_altona"``, which adds the Huggins-electronegativity /
    orientation corrections of :func:`haasnoot_altona_3j` for the non-hydrogen
    substituents on the two coupling carbons.  The refined couplings carry a
    method-specific category (``aliphatic_vicinal_karplus`` vs
    ``aliphatic_vicinal_haasnoot_altona``).

    Only ``aliphatic_vicinal`` details are refined; the geometry-insensitive
    alkene/aromatic categories pass through unchanged.  On any failure
    (embedding produces no conformers, or no measurable H-C-C-H pair exists)
    the original flat detail is preserved and a warning is recorded, so the
    refinement can only *add* geometric detail, never drop a topology-predicted
    coupling.
    """
    if method not in KARPLUS_METHODS:
        warnings.append(
            f"Unknown karplus_method {method!r}; falling back to the generic "
            "three-term Karplus relation."
        )
        method = KARPLUS_METHOD_GENERIC
    use_hla = method == KARPLUS_METHOD_HAASNOOT_ALTONA
    refined_category = (
        KARPLUS_CATEGORY_HAASNOOT_ALTONA if use_hla else KARPLUS_CATEGORY_GENERIC
    )
    if weighting not in CONFORMER_WEIGHTINGS:
        warnings.append(
            f"Unknown conformer_weighting {weighting!r}; falling back to uniform "
            "conformer averaging."
        )
        weighting = CONFORMER_WEIGHTING_UNIFORM
    use_boltzmann = weighting == CONFORMER_WEIGHTING_BOLTZMANN

    aliphatic = [d for d in details if d.category == "aliphatic_vicinal"]
    if not aliphatic:
        return details
    others = [d for d in details if d.category != "aliphatic_vicinal"]

    try:
        from rdkit.Chem import AllChem, rdMolTransforms
    except Exception:  # pragma: no cover - rdkit ships these
        warnings.append("RDKit conformer tools unavailable; Karplus refinement skipped.")
        return details

    mol_h = Chem.AddHs(mol)
    try:
        params = AllChem.ETKDGv3()
    except Exception:  # pragma: no cover - older rdkit
        params = AllChem.ETKDG()
    params.randomSeed = int(seed)
    conf_ids = list(
        AllChem.EmbedMultipleConfs(mol_h, numConfs=max(1, int(max_conformers)), params=params)
    )
    if not conf_ids:
        warnings.append(
            "3D embedding produced no conformers; aliphatic vicinal couplings kept the "
            "empirical freely-rotating value (~7.0 Hz)."
        )
        return details
    opt_res = None
    try:
        opt_res = AllChem.MMFFOptimizeMoleculeConfs(mol_h, maxIters=200)
    except Exception:  # pragma: no cover - best-effort geometry cleanup
        pass

    # Boltzmann population weights (opt-in) from the per-conformer MMFF energies.
    # MMFFOptimizeMoleculeConfs returns [(converged_flag, energy_kcal_mol), ...]
    # aligned with the conformer order; a flag of -1 means MMFF could not be set
    # up for this molecule, so those energies are unreliable -> uniform fallback.
    weight_by_cid: dict[int, float] | None = None
    if use_boltzmann:
        energies: list[float] | None = None
        if opt_res is not None and len(opt_res) == len(conf_ids):
            if not any(int(flag) == -1 for flag, _ in opt_res):
                energies = [float(energy) for _, energy in opt_res]
        norm = _boltzmann_weights(energies) if energies is not None else None
        if norm is None:
            warnings.append(
                "MMFF conformer energies unavailable; Boltzmann weighting fell back "
                "to uniform conformer averaging."
            )
        else:
            weight_by_cid = {conf_ids[i]: norm[i] for i in range(len(conf_ids))}

    refined: list[PredictedCoupling] = []
    measured_any = False
    for detail in aliphatic:
        c1, c2 = detail.atom_indices
        atom_c1 = mol_h.GetAtomWithIdx(c1)
        atom_c2 = mol_h.GetAtomWithIdx(c2)
        h1s = [n.GetIdx() for n in atom_c1.GetNeighbors() if n.GetAtomicNum() == 1]
        h2s = [n.GetIdx() for n in atom_c2.GetNeighbors() if n.GetAtomicNum() == 1]
        if not h1s or not h2s:
            refined.append(detail)
            continue
        # Non-hydrogen substituents on each coupling carbon (excluding the
        # partner carbon) drive the Haasnoot-Altona electronegativity sum; only
        # needed for the HLA method, so they are skipped for the generic path.
        subs_c1 = (
            [
                (n.GetIdx(), _delta_chi(n.GetAtomicNum()))
                for n in atom_c1.GetNeighbors()
                if n.GetAtomicNum() != 1 and n.GetIdx() != c2
            ]
            if use_hla
            else []
        )
        subs_c2 = (
            [
                (n.GetIdx(), _delta_chi(n.GetAtomicNum()))
                for n in atom_c2.GetNeighbors()
                if n.GetAtomicNum() != 1 and n.GetIdx() != c1
            ]
            if use_hla
            else []
        )
        for h1 in h1s:
            for h2 in h2s:
                values: list[float] = []
                for cid in conf_ids:
                    conf = mol_h.GetConformer(cid)
                    phi = rdMolTransforms.GetDihedralDeg(conf, h1, c1, c2, h2)
                    if use_hla:
                        terms: list[tuple[float, float]] = []
                        for s_idx, dchi in subs_c1:
                            phi_s = rdMolTransforms.GetDihedralDeg(conf, s_idx, c1, c2, h2)
                            xi = 1.0 if _wrap_180(phi_s - phi) >= 0.0 else -1.0
                            terms.append((dchi, xi))
                        for s_idx, dchi in subs_c2:
                            phi_s = rdMolTransforms.GetDihedralDeg(conf, s_idx, c2, c1, h1)
                            xi = 1.0 if _wrap_180(phi_s - phi) >= 0.0 else -1.0
                            terms.append((dchi, xi))
                        values.append(haasnoot_altona_3j(phi, terms))
                    else:
                        values.append(karplus_3j(phi))
                if values:
                    measured_any = True
                    if weight_by_cid is not None:
                        w = [weight_by_cid[cid] for cid in conf_ids]
                        mean = math.fsum(wi * vi for wi, vi in zip(w, values)) / math.fsum(w)
                    else:
                        mean = sum(values) / len(values)
                    refined.append(
                        PredictedCoupling(
                            refined_category,
                            round(mean, 2),
                            (c1, c2),
                        )
                    )
    if not measured_any:
        return details
    return others + refined


def predict_proton_couplings_from_smiles(
    smiles: str,
    *,
    use_karplus: bool = False,
    karplus_method: str = KARPLUS_DEFAULT_METHOD,
    karplus_max_conformers: int = KARPLUS_DEFAULT_MAX_CONFORMERS,
    karplus_conformer_weighting: str = CONFORMER_WEIGHTING_DEFAULT,
    karplus_seed: int = KARPLUS_RANDOM_SEED,
) -> PredictedCouplingSet:
    """Predict the compact set of diagnostic 1H-1H couplings (Hz) for a SMILES.

    Returns a :class:`PredictedCouplingSet`.  On an unparseable SMILES the
    result has ``invalid_structure=True`` and an empty coupling set rather than
    raising, so the bridge can score it as a contradiction-bearing candidate.

    When ``use_karplus`` is ``True`` the flat empirical aliphatic vicinal
    coupling is replaced by a conformer-averaged vicinal ``3J`` (an RDKit ETKDG
    ensemble of ``karplus_max_conformers`` conformers, seeded by
    ``karplus_seed`` for reproducibility).  ``karplus_method`` selects the
    relation: ``"generic"`` (default) uses the three-term Karplus curve, while
    ``"haasnoot_altona"`` applies the electronegativity/orientation-corrected
    Haasnoot-de Leeuw-Altona generalized Karplus relation.
    ``karplus_conformer_weighting`` selects how the per-conformer couplings are
    averaged: ``"uniform"`` (default) takes the plain ensemble mean, while
    ``"boltzmann"`` weights each conformer by ``exp(-(E-E_min)/RT)`` from its
    MMFF energy so the ground-state geometry dominates (falling back to uniform
    with a warning if energies are unavailable).  This is opt-in decision
    support: the default (topology-only) path is byte-for-byte unchanged, and
    ``use_karplus=True`` with the default ``"generic"`` method + ``"uniform"``
    weighting is identical to prior behaviour.
    """
    smiles_key = (smiles or "").strip()
    try:
        mol = mol_from_smiles(smiles_key)
    except StructureParseError as exc:
        return PredictedCouplingSet(
            smiles=smiles_key, invalid_structure=True, warnings=[str(exc)]
        )

    warnings: list[str] = []
    details = _enumerate_couplings(mol)
    if use_karplus:
        details = _refine_vicinal_with_karplus(
            mol,
            details,
            method=karplus_method,
            weighting=karplus_conformer_weighting,
            max_conformers=karplus_max_conformers,
            seed=karplus_seed,
            warnings=warnings,
        )
    raw = [detail.j_hz for detail in details if detail.j_hz >= MIN_DIAGNOSTIC_HZ]
    compacted = _compact(raw, COMPACTION_TOLERANCE_HZ)

    counts: dict[str, int] = {}
    for detail in details:
        counts[detail.category] = counts.get(detail.category, 0) + 1

    if not compacted:
        warnings.append(
            "No diagnostic 1H-1H couplings were predicted from topology "
            "(no adjacent protonated carbons, alkene, or aromatic CH-CH found)."
        )

    return PredictedCouplingSet(
        smiles=smiles_key,
        couplings_hz=compacted,
        details=details,
        max_predicted_hz=max(compacted) if compacted else 0.0,
        category_counts=counts,
        warnings=warnings,
    )
