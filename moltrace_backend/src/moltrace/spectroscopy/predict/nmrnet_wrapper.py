"""NMRNet chemical-shift prediction wrapper, with a HOSE-code fallback.

Prompt 6 — NMRNet wrapper
=========================

`predict_shifts(smiles, nuclei)` returns predicted ¹H / ¹³C chemical shifts (ppm)
per atom. Two backends sit behind one interface:

1. **NMRNet** (Xu et al., *Nat. Comput. Sci.* **5**, 292 (2025)) — an
   SE(3)-equivariant Transformer over a 3D conformer. Reported accuracy on the
   paper's benchmark: MAE ≈ 0.181 ppm (¹H) / 1.098 ppm (¹³C). NMRNet ships as a
   research codebase (Uni-Mol-based) plus downloadable weights, **not** as a
   pip-installable model, so this wrapper integrates it as an *optional,
   lazily-loaded* backend: it activates only when (a) `torch` is importable,
   (b) the NMRNet package is importable (configurable via
   ``MOLTRACE_NMRNET_MODULE``), and (c) a weights checkpoint is resolvable (via
   the ``model_path`` argument or ``MOLTRACE_NMRNET_WEIGHTS``). If any of those
   is missing the backend raises :class:`NMRNetUnavailable` and the wrapper
   falls back — it never fabricates a prediction. See ``_NMRNetBackend`` for the
   exact conformance interface a vendored NMRNet release must expose.

2. **HOSE-code fallback** — a topological nearest-environment predictor over a
   NMRShiftDB2-style knowledge base. For each atom it builds a HOSE-style
   spherical environment code (spheres 1–6) and looks the code up in the KB,
   **decreasing the sphere until a match is found** (sphere 6 = most specific →
   sphere 1 = most general); the prediction is the mean shift of the matching
   reference atoms and the uncertainty their spread. RDKit has no built-in HOSE
   generator, so :func:`hose_code` implements a deterministic, canonical
   HOSE-style code here. The bundled knowledge base is a small **curated
   literature seed** (common solvents / functional groups); a full NMRShiftDB2
   assignment export can be loaded via :func:`load_knowledge_base` for
   production-grade coverage.

Pipeline (per the spec): parse SMILES with RDKit → 3D embed (``EmbedMolecule`` +
``MMFFOptimizeMolecule``) → atom types + coordinates → NMRNet inference → per-atom
`{predicted_ppm, uncertainty_ppm}`. The 3D step feeds NMRNet only; the HOSE
fallback is topological and does not require a conformer.

Validation note
---------------
The "QM9-NMR MAE within 30 % of the paper" gate is implemented in the test
suite but **skips** unless both a real NMRNet checkpoint and the QM9-NMR test set
are present (neither ships in this repo); it never asserts a fabricated number.
The HOSE fallback's accuracy is validated directly against the curated seed KB.
"""

from __future__ import annotations

import importlib
import math
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from rdkit import Chem
from rdkit.Chem import AllChem

__all__ = [
    "AtomShiftPrediction",
    "ShiftPrediction",
    "NMRNetUnavailable",
    "predict_shifts",
    "hose_code",
    "load_knowledge_base",
    "build_seed_knowledge_base",
]

# Which element each NMR-active nucleus lives on.
_NUCLEUS_TO_ELEMENT: dict[str, str] = {"1H": "H", "13C": "C"}
_DEFAULT_NUCLEI: tuple[str, ...] = ("1H", "13C")
_MAX_SPHERE = 6
_EMBED_SEED = 0xC0FFEE

# Per-nucleus default uncertainty (ppm) when a prediction comes from a single
# reference atom (no spread to measure) or from the element-level prior.
_SINGLETON_UNCERTAINTY: dict[str, float] = {"1H": 0.30, "13C": 2.0}
_PRIOR_UNCERTAINTY: dict[str, float] = {"1H": 1.8, "13C": 35.0}


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AtomShiftPrediction:
    """One atom's predicted shift.

    ``predicted_ppm`` and ``uncertainty_ppm`` are the core read-outs; the rest is
    provenance so a reviewer can see *how* the number was produced.
    """

    atom_index: int
    element: str
    nucleus: str
    predicted_ppm: float
    uncertainty_ppm: float
    method: str  # "nmrnet" | "hose_nmrshiftdb2"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ShiftPrediction:
    """Predicted shifts for a molecule, keyed by RDKit atom index.

    ``shifts`` is the ``{atom_index: AtomShiftPrediction}`` mapping the spec asks
    for (each value exposing ``predicted_ppm`` + ``uncertainty_ppm``).
    """

    smiles: str
    nuclei: tuple[str, ...]
    backend: str  # "nmrnet" | "hose_nmrshiftdb2"
    shifts: dict[int, AtomShiftPrediction]
    notes: tuple[str, ...] = ()

    def for_nucleus(self, nucleus: str) -> dict[int, AtomShiftPrediction]:
        return {i: s for i, s in self.shifts.items() if s.nucleus == nucleus}


class NMRNetUnavailable(RuntimeError):
    """Raised when the optional NMRNet backend cannot be loaded or run.

    Callers catch this to fall back to the HOSE-code predictor; the message
    states exactly which prerequisite (torch / package / weights) was missing.
    """


# --------------------------------------------------------------------------- #
# HOSE-style spherical environment code
# --------------------------------------------------------------------------- #
_BOND_SYMBOL = {
    Chem.BondType.SINGLE: "-",
    Chem.BondType.DOUBLE: "=",
    Chem.BondType.TRIPLE: "#",
    Chem.BondType.AROMATIC: ":",
}


def _atom_token(atom: Chem.Atom) -> str:
    """Canonical per-atom token: element (+ aromatic / ring / charge flags)."""

    token = atom.GetSymbol()
    if atom.GetIsAromatic():
        token += "a"
    if atom.IsInRing():
        token += "R"
    charge = atom.GetFormalCharge()
    if charge:
        token += f"{charge:+d}"
    return token


def _bond_token(bond: Chem.Bond) -> str:
    return _BOND_SYMBOL.get(bond.GetBondType(), "?")


def hose_code(
    mol: Chem.Mol, atom_index: int, max_sphere: int = _MAX_SPHERE
) -> tuple[str, ...]:
    """A deterministic HOSE-style spherical environment code for one atom.

    Returns a tuple ``(center, shell₁, shell₂, …, shell_max)``: the center atom's
    token followed by one canonical (sorted) string per BFS sphere.  Truncating
    the tuple to the first ``s+1`` entries yields the environment out to sphere
    ``s`` — that is how the fallback "decreases the sphere until a match".

    This is a *HOSE-style* code (not the exact Bremser canonical string), but it
    is built identically for both the knowledge base and the query, so lookups
    are internally consistent — which is all the nearest-environment match needs.
    """

    center = mol.GetAtomWithIdx(atom_index)
    shells: list[str] = []
    visited = {atom_index}
    frontier = [atom_index]

    for _sphere in range(1, max_sphere + 1):
        next_frontier: list[int] = []
        tokens: list[str] = []
        for a_idx in frontier:
            atom = mol.GetAtomWithIdx(a_idx)
            for bond in atom.GetBonds():
                neighbor = bond.GetOtherAtom(atom)
                j = neighbor.GetIdx()
                if j in visited:
                    continue
                visited.add(j)
                tokens.append(_bond_token(bond) + _atom_token(neighbor))
                next_frontier.append(j)
        tokens.sort()
        shells.append(",".join(tokens))
        frontier = next_frontier
        if not frontier:
            # Pad the remaining spheres so codes have a uniform length; empty
            # shells simply never disambiguate, which is correct.
            shells.extend("" for _ in range(_sphere, max_sphere))
            break

    return (_atom_token(center), *shells)


def _truncate_code(code: tuple[str, ...], sphere: int) -> str:
    """The lookup key for ``code`` out to ``sphere`` (1-indexed)."""

    # code[0] is the center; code[1:sphere+1] are spheres 1..sphere.
    return "".join(code[: sphere + 1])


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
@dataclass
class KnowledgeBase:
    """HOSE-code → shift index for the fallback predictor.

    ``buckets[(nucleus, sphere)][truncated_code] -> [shifts]`` and per-nucleus
    element priors for the no-match case.
    """

    buckets: dict[tuple[str, int], dict[str, list[float]]]
    priors: dict[str, float]
    reference_count: int = 0

    def lookup(
        self, nucleus: str, code: tuple[str, ...]
    ) -> tuple[float, float, int, int] | None:
        """Return ``(predicted_ppm, uncertainty_ppm, sphere, n_ref)`` or ``None``.

        Tries sphere 6 first and decreases until a bucket matches.
        """

        for sphere in range(_MAX_SPHERE, 0, -1):
            table = self.buckets.get((nucleus, sphere))
            if not table:
                continue
            shifts = table.get(_truncate_code(code, sphere))
            if not shifts:
                continue
            predicted = float(statistics.fmean(shifts))
            if len(shifts) > 1:
                uncertainty = float(statistics.pstdev(shifts))
                # A zero spread (all-equal references) still warrants a floor.
                uncertainty = max(uncertainty, _SINGLETON_UNCERTAINTY[nucleus] * 0.5)
            else:
                uncertainty = _SINGLETON_UNCERTAINTY[nucleus]
            return predicted, uncertainty, sphere, len(shifts)
        return None


def _new_kb() -> KnowledgeBase:
    return KnowledgeBase(buckets=defaultdict(dict), priors={})


def _index_reference_atom(
    kb: KnowledgeBase, nucleus: str, code: tuple[str, ...], shift: float
) -> None:
    for sphere in range(1, _MAX_SPHERE + 1):
        table = kb.buckets[(nucleus, sphere)]
        table.setdefault(_truncate_code(code, sphere), []).append(shift)


def _finalize_priors(kb: KnowledgeBase) -> None:
    for nucleus in _NUCLEUS_TO_ELEMENT:
        # Sphere-1 buckets hold every reference shift for the nucleus exactly once
        # per environment occurrence — good enough for an element-level mean.
        all_shifts: list[float] = []
        for table_key, table in kb.buckets.items():
            if table_key[0] != nucleus or table_key[1] != 1:
                continue
            for shifts in table.values():
                all_shifts.extend(shifts)
        if all_shifts:
            kb.priors[nucleus] = float(statistics.fmean(all_shifts))


# Curated literature ¹H / ¹³C shifts (ppm, CDCl3-ish) for common solvents and
# functional groups. Each entry maps a SMARTS for the *heavy* atom that bears the
# environment to a shift; for ¹H the shift is assigned to that heavy atom's
# hydrogens. Values are standard textbook / SDBS reference shifts. This is a
# deliberately small SEED — load a full NMRShiftDB2 assignment export via
# ``load_knowledge_base`` for production coverage.
_SEED_REFERENCES: tuple[tuple[str, str, tuple[tuple[str, str, float], ...]], ...] = (
    ("benzene", "c1ccccc1", (("c", "13C", 128.4), ("c", "1H", 7.26))),
    ("cyclohexane", "C1CCCCC1", (("C", "13C", 26.9), ("C", "1H", 1.43))),
    ("chloroform", "ClC(Cl)Cl", (("[CX4]", "13C", 77.2), ("[CX4]", "1H", 7.26))),
    ("dichloromethane", "ClCCl", (("[CX4]", "13C", 53.5), ("[CX4]", "1H", 5.30))),
    ("acetone", "CC(C)=O", (("[CH3]", "13C", 30.9), ("[CH3]", "1H", 2.17),
                            ("[CX3]=O", "13C", 206.0))),
    ("methanol", "CO", (("[CH3]", "13C", 50.4), ("[CH3]", "1H", 3.49))),
    ("acetonitrile", "CC#N", (("[CH3]", "13C", 1.3), ("[CH3]", "1H", 1.99),
                              ("[CX2]#N", "13C", 118.3))),
    ("dimethyl_sulfoxide", "CS(C)=O", (("[CH3]", "13C", 40.8), ("[CH3]", "1H", 2.54))),
    ("ethanol", "CCO", (("[CH3]", "13C", 18.2), ("[CH3]", "1H", 1.22),
                        ("[CH2]", "13C", 58.0), ("[CH2]", "1H", 3.69))),
    ("acetic_acid", "CC(=O)O", (("[CH3]", "13C", 20.8), ("[CH3]", "1H", 2.10),
                                ("[CX3](=O)O", "13C", 178.1))),
    ("toluene_methyl", "Cc1ccccc1", (("[CH3]", "13C", 21.4), ("[CH3]", "1H", 2.34))),
    ("dimethyl_ether", "COC", (("[CH3]", "13C", 60.0), ("[CH3]", "1H", 3.27))),
    ("ethane", "CC", (("[CH3]", "13C", 6.5), ("[CH3]", "1H", 0.86))),
    ("tetramethylsilane", "C[Si](C)(C)C", (("[CH3]", "13C", 0.0), ("[CH3]", "1H", 0.0))),
)


def build_seed_knowledge_base() -> KnowledgeBase:
    """Build the bundled curated-literature knowledge base."""

    kb = _new_kb()
    n_ref = 0
    for _name, smiles, entries in _SEED_REFERENCES:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:  # pragma: no cover - curated SMILES are valid
            continue
        mol_h = Chem.AddHs(mol)  # heavy-atom indices are preserved
        for smarts, nucleus, shift in entries:
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:  # pragma: no cover
                continue
            element = _NUCLEUS_TO_ELEMENT[nucleus]
            for match in mol.GetSubstructMatches(pattern):
                heavy_idx = match[0]
                if element == "C":
                    targets = [heavy_idx]
                else:  # "H" -> the hydrogens on the matched heavy atom
                    targets = [
                        nbr.GetIdx()
                        for nbr in mol_h.GetAtomWithIdx(heavy_idx).GetNeighbors()
                        if nbr.GetSymbol() == "H"
                    ]
                for atom_index in targets:
                    code = hose_code(mol_h, atom_index)
                    _index_reference_atom(kb, nucleus, code, shift)
                    n_ref += 1
    kb.reference_count = n_ref
    _finalize_priors(kb)
    return kb


def load_knowledge_base(path: str | Path) -> KnowledgeBase:
    """Load a knowledge base from an NMRShiftDB2-style assignment export.

    Expected JSON shape::

        [{"smiles": "...", "assignments": [{"atom_index": int,
                                            "nucleus": "1H"|"13C",
                                            "shift_ppm": float}, ...]}, ...]

    ``atom_index`` indexes the molecule **with explicit hydrogens added** (RDKit
    ``AddHs`` order: heavy atoms first, then hydrogens). This is the hook to swap
    the small bundled seed for a full NMRShiftDB2 corpus.
    """

    import json

    data = json.loads(Path(path).read_text())
    kb = _new_kb()
    n_ref = 0
    for record in data:
        mol = Chem.MolFromSmiles(record["smiles"])
        if mol is None:
            continue
        mol_h = Chem.AddHs(mol)
        n_atoms = mol_h.GetNumAtoms()
        for assignment in record.get("assignments", []):
            nucleus = assignment["nucleus"]
            if nucleus not in _NUCLEUS_TO_ELEMENT:
                continue
            atom_index = int(assignment["atom_index"])
            if not (0 <= atom_index < n_atoms):
                continue
            code = hose_code(mol_h, atom_index)
            _index_reference_atom(kb, nucleus, code, float(assignment["shift_ppm"]))
            n_ref += 1
    kb.reference_count = n_ref
    _finalize_priors(kb)
    return kb


# Lazily-built bundled KB (cached after first use).
_SEED_KB: KnowledgeBase | None = None


def _seed_kb() -> KnowledgeBase:
    global _SEED_KB
    if _SEED_KB is None:
        _SEED_KB = build_seed_knowledge_base()
    return _SEED_KB


# --------------------------------------------------------------------------- #
# NMRNet backend (optional, lazily loaded)
# --------------------------------------------------------------------------- #
class _NMRNetBackend:
    """Adapter onto a vendored NMRNet release.

    NMRNet is a research codebase, so this wrapper does not reimplement the
    SE(3)-equivariant Transformer; it loads the real checkpoint and calls the
    release's inference entry point. A conformant NMRNet package (named by
    ``MOLTRACE_NMRNET_MODULE``, default ``"nmrnet"``) must expose **either**:

    * ``load_pretrained(weights_path) -> model`` (or ``load_model``), where
      ``model`` is callable as ``model(symbols, coords, nuclei) ->
      {atom_index: (predicted_ppm, uncertainty_ppm)}``; **or**
    * a module-level ``predict_shifts(symbols, coords, nuclei, weights_path)``
      returning the same mapping.

    Until such a package + checkpoint are installed, :meth:`load` raises
    :class:`NMRNetUnavailable` and the wrapper falls back. The featurisation
    below (element symbols + 3D coordinates from RDKit) is real and is what gets
    handed to NMRNet; the model itself is never stubbed or faked.
    """

    def __init__(self, model: Any, module: Any) -> None:
        self._model = model
        self._module = module

    @classmethod
    def load(cls, model_path: str | Path | None = None) -> "_NMRNetBackend":
        module_name = os.environ.get("MOLTRACE_NMRNET_MODULE", "nmrnet")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise NMRNetUnavailable(
                f"NMRNet backend module {module_name!r} is not importable ({exc})"
            ) from exc

        loader = getattr(module, "load_pretrained", None) or getattr(
            module, "load_model", None
        )
        if loader is None and not hasattr(module, "predict_shifts"):
            raise NMRNetUnavailable(
                f"NMRNet backend {module_name!r} exposes neither "
                "load_pretrained/load_model nor predict_shifts"
            )

        weights = model_path or os.environ.get("MOLTRACE_NMRNET_WEIGHTS")

        # An *in-process* backend needs a local torch + a local checkpoint. A
        # *remote* backend (e.g. an HTTP client to a GPU service) declares
        # ``REQUIRES_LOCAL_TORCH = False`` and enforces its own prerequisites
        # (such as a service URL) inside its loader — so the main backend stays
        # torch-free.
        if getattr(module, "REQUIRES_LOCAL_TORCH", True):
            if not weights:
                raise NMRNetUnavailable(
                    "no NMRNet weights configured "
                    "(pass model_path or set MOLTRACE_NMRNET_WEIGHTS)"
                )
            if not Path(weights).exists():
                raise NMRNetUnavailable(f"NMRNet weights not found at {weights!r}")
            try:
                import torch  # noqa: F401  (presence check; the NMRNet package uses it)
            except ImportError as exc:
                raise NMRNetUnavailable(f"PyTorch is not installed ({exc})") from exc

        model = (
            loader(str(weights) if weights else None) if loader is not None else None
        )
        return cls(model=model, module=module)

    def predict(
        self,
        mol_h: Chem.Mol,
        coords: list[tuple[float, float, float]],
        nuclei: Sequence[str],
    ) -> dict[int, AtomShiftPrediction]:
        symbols = [atom.GetSymbol() for atom in mol_h.GetAtoms()]
        if self._model is not None and callable(self._model):
            raw = self._model(symbols, coords, list(nuclei))
        else:  # module-level predict_shifts(...)
            raw = self._module.predict_shifts(
                symbols,
                coords,
                list(nuclei),
                os.environ.get("MOLTRACE_NMRNET_WEIGHTS"),
            )

        wanted = {_NUCLEUS_TO_ELEMENT[n] for n in nuclei if n in _NUCLEUS_TO_ELEMENT}
        out: dict[int, AtomShiftPrediction] = {}
        for atom_index, value in raw.items():
            predicted, uncertainty = value
            element = symbols[atom_index]
            if element not in wanted:
                continue
            nucleus = "1H" if element == "H" else "13C"
            out[atom_index] = AtomShiftPrediction(
                atom_index=atom_index,
                element=element,
                nucleus=nucleus,
                predicted_ppm=float(predicted),
                uncertainty_ppm=float(uncertainty),
                method="nmrnet",
                provenance={"model": "nmrnet"},
            )
        return out


def _embed_3d(mol_h: Chem.Mol) -> list[tuple[float, float, float]]:
    """EmbedMolecule + MMFFOptimizeMolecule; return Å coordinates per atom."""

    params = AllChem.ETKDGv3()
    params.randomSeed = _EMBED_SEED
    if AllChem.EmbedMolecule(mol_h, params) != 0:
        raise NMRNetUnavailable("3D embedding failed (EmbedMolecule)")
    try:
        AllChem.MMFFOptimizeMolecule(mol_h)
    except Exception:  # pragma: no cover - MMFF can decline exotic systems
        pass
    conf = mol_h.GetConformer()
    return [
        (conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z)
        for i in range(mol_h.GetNumAtoms())
    ]


# --------------------------------------------------------------------------- #
# HOSE fallback predictor
# --------------------------------------------------------------------------- #
def _predict_hose(
    mol_h: Chem.Mol, nuclei: Sequence[str], kb: KnowledgeBase
) -> dict[int, AtomShiftPrediction]:
    out: dict[int, AtomShiftPrediction] = {}
    for nucleus in nuclei:
        element = _NUCLEUS_TO_ELEMENT.get(nucleus)
        if element is None:
            continue
        for atom in mol_h.GetAtoms():
            if atom.GetSymbol() != element:
                continue
            atom_index = atom.GetIdx()
            code = hose_code(mol_h, atom_index)
            hit = kb.lookup(nucleus, code)
            if hit is not None:
                predicted, uncertainty, sphere, n_ref = hit
                out[atom_index] = AtomShiftPrediction(
                    atom_index=atom_index,
                    element=element,
                    nucleus=nucleus,
                    predicted_ppm=predicted,
                    uncertainty_ppm=uncertainty,
                    method="hose_nmrshiftdb2",
                    provenance={"hose_sphere": sphere, "n_reference": n_ref},
                )
            else:
                prior = kb.priors.get(nucleus, 0.0)
                out[atom_index] = AtomShiftPrediction(
                    atom_index=atom_index,
                    element=element,
                    nucleus=nucleus,
                    predicted_ppm=prior,
                    uncertainty_ppm=_PRIOR_UNCERTAINTY[nucleus],
                    method="hose_nmrshiftdb2",
                    provenance={"hose_sphere": 0, "n_reference": 0, "element_prior": True},
                )
    return out


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def predict_shifts(
    smiles: str,
    nuclei: Sequence[str] = _DEFAULT_NUCLEI,
    *,
    model_path: str | Path | None = None,
    knowledge_base: KnowledgeBase | None = None,
) -> ShiftPrediction:
    """Predict ¹H / ¹³C chemical shifts (ppm) per atom for ``smiles``.

    Pipeline: parse SMILES with RDKit → add explicit H → (for NMRNet) 3D embed
    via ``EmbedMolecule`` + ``MMFFOptimizeMolecule`` → atom types + coordinates →
    NMRNet inference. If the optional NMRNet backend is unavailable or its
    inference fails, fall back to the HOSE-code / NMRShiftDB2 predictor (spheres
    6→1, decreasing until a match is found).

    Target accuracy of the NMRNet path (paper benchmark): MAE ≈ 0.181 ppm (¹H),
    1.098 ppm (¹³C).

    Parameters
    ----------
    smiles:
        Molecule SMILES. A parse failure raises ``ValueError``.
    nuclei:
        Nuclei to predict; defaults to ``("1H", "13C")``.
    model_path:
        Optional NMRNet checkpoint path (else ``MOLTRACE_NMRNET_WEIGHTS``).
    knowledge_base:
        Optional fallback KB (else the bundled curated seed).

    Returns
    -------
    ShiftPrediction
        ``shifts`` maps each atom index to an :class:`AtomShiftPrediction`
        carrying ``predicted_ppm`` and ``uncertainty_ppm``.
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    mol_h = Chem.AddHs(mol)

    requested = tuple(nuclei)
    notes: list[str] = []
    unsupported = [n for n in requested if n not in _NUCLEUS_TO_ELEMENT]
    if unsupported:
        notes.append(f"Unsupported nuclei ignored: {unsupported}")
    active_nuclei = [n for n in requested if n in _NUCLEUS_TO_ELEMENT]

    # 1) Try the optional NMRNet backend (needs torch + package + weights + 3D).
    try:
        backend = _NMRNetBackend.load(model_path)
        coords = _embed_3d(mol_h)
        shifts = backend.predict(mol_h, coords, active_nuclei)
        return ShiftPrediction(
            smiles=smiles,
            nuclei=requested,
            backend="nmrnet",
            shifts=shifts,
            notes=tuple(notes),
        )
    except NMRNetUnavailable as exc:
        notes.append(
            f"NMRNet backend unavailable ({exc}); using HOSE-code/NMRShiftDB2 fallback."
        )
    except Exception as exc:  # NMRNet present but inference failed — never crash.
        notes.append(
            f"NMRNet inference failed ({exc!r}); using HOSE-code/NMRShiftDB2 fallback."
        )

    # 2) HOSE-code fallback.
    kb = knowledge_base if knowledge_base is not None else _seed_kb()
    shifts = _predict_hose(mol_h, active_nuclei, kb)
    return ShiftPrediction(
        smiles=smiles,
        nuclei=requested,
        backend="hose_nmrshiftdb2",
        shifts=shifts,
        notes=tuple(notes),
    )
