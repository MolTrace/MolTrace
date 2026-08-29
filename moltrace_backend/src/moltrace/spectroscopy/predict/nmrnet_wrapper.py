"""NMRNet chemical-shift prediction wrapper (with a HOSE-code fallback).

Attribution
-----------
NMRNet: Xu, F.; Guo, W.; Wang, F. et al. "Toward a unified benchmark and
framework for deep learning-based prediction of NMR chemical shifts."
Nat. Comput. Sci. 5, 292-300 (2025). DOI: 10.1038/s43588-025-00783-z.
Source: https://github.com/Colin-Jay/NMRNet (MIT License). NMRNet is a
Uni-Mol-based SE(3) Transformer running on the Uni-Core framework. It is used
here as an OPTIONAL, separately-installed dependency — its source is **not**
vendored — and pretrained weights are downloaded by the end user from the
official Zenodo release. The HOSE-code fallback knowledge base is built from
NMRShiftDB2 (Kuhn & Schlorer, Magn. Reson. Chem. 53, 582 (2015); CC BY-SA). See
the repository NOTICE file for the full third-party notices and the ShareAlike
obligation on any redistributed NMRShiftDB2-derived table.

Overview
--------
``predict_shifts(smiles, nuclei)`` returns predicted ¹H / ¹³C shifts (ppm) with a
per-atom uncertainty, via two backends behind one interface:

* **NMRNet** (``method='nmrnet'``) — the SE(3) Transformer over a 3D conformer
  ensemble. Optional and lazily loaded: it activates only when ``torch`` + the
  NMRNet package + per-nucleus weights are available, and **never fabricates a
  prediction**. Device resolution is CUDA → MPS → CPU; on Apple Silicon, MPS is
  best-effort (Uni-Core's fused kernels have no MPS path, so ops fall back to CPU
  via ``PYTORCH_ENABLE_MPS_FALLBACK``; total MPS failure re-runs on CPU). CPU is
  the supported baseline.
* **HOSE-code fallback** (``method='hose_fallback'``) — a topological
  nearest-environment predictor over a NMRShiftDB2 knowledge base: each atom's
  HOSE-style spherical code (spheres 1-6) is looked up, decreasing the sphere
  until a match with ≥ 3 references is found; the prediction is the mean shift of
  those references and the uncertainty their spread.

Uncertainty
-----------
NMRNet has no native calibrated uncertainty, so the NMRNet path reports the
**per-atom standard deviation across the conformer ensemble** (NaN with a
warning when ``n_conformers == 1``). The fallback reports the spread of the
matched knowledge-base references.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import math
import os
import statistics
import urllib.request
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Must be set before torch is imported anywhere (torch is imported lazily below).
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from rdkit import Chem  # noqa: E402  (RDKit is a core dependency; torch is not)
from rdkit.Chem import AllChem  # noqa: E402

__all__ = [
    "AtomShift",
    "ShiftPrediction",
    "NMRNetUnavailable",
    "predict_shifts",
    "hose_code",
    "build_seed_knowledge_base",
    "load_knowledge_base",
    "save_knowledge_base_index",
    "build_knowledge_base",
    "molecule_from_record",
]

_NUCLEUS_TO_ELEMENT: dict[str, str] = {"1H": "H", "13C": "C"}
_ELEMENT_TO_NUCLEUS: dict[str, str] = {v: k for k, v in _NUCLEUS_TO_ELEMENT.items()}
_MAX_SPHERE = 6
_MIN_KB_MATCHES = 3  # a HOSE bucket must hold ≥ this many references to be used
_DEFAULT_N_CONFORMERS = 8
_EMBED_BASE_SEED = 0xF00D

# Per-nucleus default uncertainty (ppm) used by the fallback's element-level prior.
_PRIOR_UNCERTAINTY: dict[str, float] = {"1H": 1.8, "13C": 35.0}

# NMRNet weights: per-nucleus checkpoint filenames in the cache, the Zenodo
# record they come from, and (optionally) their SHA-256 checksums for
# verification. Fill ``_WEIGHTS_SHA256`` with the official Zenodo checksums; when
# present they are enforced, when absent a warning is emitted instead.
_ZENODO_RECORD = "19142375"
_NUCLEUS_CHECKPOINTS: dict[str, str] = {"1H": "nmrnet_1h.pt", "13C": "nmrnet_13c.pt"}
_WEIGHTS_SHA256: dict[str, str] = {}  # e.g. {"13C": "<sha256>"} — fill from Zenodo


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class AtomShift:
    atom_index: int  # RDKit index in the H-added molecule
    element: str  # 'H' | 'C'
    nucleus: str  # '1H' | '13C'
    predicted_ppm: float
    uncertainty_ppm: float  # ensemble std (NMRNet) or KB spread (fallback); NaN if n_conf==1
    source: str = "unknown"
    """Where this specific number came from — ``'nmrnet'`` | ``'hose'`` | ``'element_prior'``.

    ``'element_prior'`` means *no environment was matched*: the value is the
    knowledge base's element-wide average and the uncertainty is the width of
    that element's whole shift range. It is an abstention wearing a number, and a
    caller weighting evidence must be able to see that without parsing warnings.

    The default is deliberately ``'unknown'`` rather than ``'nmrnet'``. Every
    production site sets this explicitly; a site that forgets should not inherit
    the *most* trusted label and silently claim to be a model prediction. Anything
    reaching a real prediction as ``'unknown'`` is a bug, and
    ``test_every_atom_shift_names_its_source`` fails on it.
    """
    match_sphere: int | None = None
    """How deep a HOSE environment matched (1-6), or ``None`` off the fallback path.

    **The strongest quality signal this predictor has, and it was not surfaced.**
    Measured on 36,856 held-out ¹³C atoms, MAE by matched sphere:

    ===========  ======  ============
    sphere        share   MAE (ppm)
    ===========  ======  ============
    1              8.7 %       9.59
    2             27.4 %       4.53
    3             25.9 %       2.51
    4-6           38.0 %       1.45
    ===========  ======  ============

    A shallow match means the lookup fell back to a generic environment whose
    bucket lumps chemically distinct atoms together, so its ``uncertainty_ppm``
    describes the width of a *mixture* rather than a unimodal uncertainty. 36 % of
    atoms match at sphere ≤ 2 and carry ~4x the error of a deep match. Gate on
    this before treating a shift as evidence — σ alone does not separate the two
    cases.
    """
    match_count: int | None = None
    """References in the matched bucket. Large *and* shallow means generic, not certain."""


@dataclass
class ShiftPrediction:
    smiles: str
    method: str  # 'nmrnet' | 'hose_fallback'
    device: str  # 'cuda' | 'mps' | 'cpu'
    shifts: list[AtomShift]
    n_conformers: int
    warnings: list[str]
    kb_source: str = "none"
    """Which knowledge base backed the fallback — ``'nmrshiftdb2'`` | ``'seed'`` | ``'none'``.

    ``'seed'`` is the bundled 16-molecule curated table. It covers common solvents
    and simple functional groups and is *not* production coverage for drug-like
    molecules; see :attr:`prior_fallback_fraction`.
    """
    kb_records: int = 0
    """Reference atoms indexed in that knowledge base (0 when NMRNet answered)."""

    @property
    def prior_fallback_fraction(self) -> float:
        """Share of atoms that matched nothing and fell back to the element prior.

        This is the number that was missing. Each fallback already appended a
        per-atom warning, but nothing aggregated them, so a prediction that was
        70 % element-averages looked — to every caller — exactly like one that
        was fully resolved. Gate on this before treating a prediction as evidence.
        """

        if not self.shifts:
            return 0.0
        return sum(1 for s in self.shifts if s.source == "element_prior") / len(self.shifts)

    @property
    def shallow_match_fraction(self) -> float:
        """Share of atoms matched only at a generic HOSE sphere (≤ 2).

        Companion to :attr:`prior_fallback_fraction`, and the same lesson a second
        time: coverage is not quality. An atom matched at sphere 1-2 *has* a
        prediction, so it does not show up as a fallback — but measured on 36,856
        held-out ¹³C atoms it carries **~4x the error** of a deep match (5.75 vs
        1.45 ppm MAE). A prediction that is 100 % "covered" but mostly shallow is
        not a good prediction, and nothing else in the result would say so.
        """

        if not self.shifts:
            return 0.0
        shallow = sum(
            1 for s in self.shifts if s.match_sphere is not None and s.match_sphere <= 2
        )
        return shallow / len(self.shifts)

    @property
    def median_uncertainty_ppm(self) -> dict[str, float]:
        """Median σ per nucleus, over atoms with a finite uncertainty.

        Compare against the error model that consumes it: DP4's published scales
        are 0.185 ppm (¹H) and 2.306 ppm (¹³C). A median σ far above those means
        the prediction cannot discriminate between candidates, however confident
        the surrounding pipeline looks.

        What a given σ is worth, measured on held-out NMRShiftDB2 (reproduce with
        ``scripts/measure_kb_match_quality.py``). σ is strictly monotone in the error it
        predicts, on both nuclei, which is what makes it the gate to use:

            ¹³C   σ ≤ 0.5 → MAE 0.780    ≤ 1.5 → 1.373    ≤ 3.0 → 2.405
                  σ ≤ 6.0 → MAE 3.931    > 6.0 → 8.801 ppm   (11.3x span)
            ¹H    σ ≤ 0.05 → MAE 0.075   ≤ 0.15 → 0.119   ≤ 0.3 → 0.216
                  σ ≤ 0.6 → MAE 0.389    > 0.6 → 0.952 ppm   (12.7x span)

        **Bucket size is not a substitute and was measured and rejected.** A HOSE bucket's
        reference count runs the wrong way once pooled over spheres -- ¹³C MAE 2.170 ppm at
        3-4 references against 5.802 at 100+, ¹H 0.216 against 0.566 -- because a large
        bucket means a generic environment matched at a shallow sphere, which
        :attr:`shallow_match_fraction` already catches. A gate on low reference counts would
        misfire in both directions: ibuprofen has 12 of 18 protons matched from ≤ 4
        references at a median σ of 0.051 ppm (excellent, and it would flag them), while
        paracetamol's worst protons include three matched from 19 references at σ 2.215
        (bad, and it would miss them). σ separates those cases; the count does not.
        """

        out: dict[str, float] = {}
        for nucleus in _NUCLEUS_TO_ELEMENT:
            sigmas = [
                float(s.uncertainty_ppm)
                for s in self.shifts
                if s.nucleus == nucleus and math.isfinite(s.uncertainty_ppm)
            ]
            if sigmas:
                out[nucleus] = float(statistics.median(sigmas))
        return out


class NMRNetUnavailable(RuntimeError):
    """Raised when the NMRNet backend cannot be loaded or run (→ HOSE fallback)."""


# --------------------------------------------------------------------------- #
# Device strategy
# --------------------------------------------------------------------------- #
def _select_device(prefer: str | None = None):  # -> torch.device
    """Resolve the inference device: explicit ``prefer`` else CUDA → MPS → CPU.

    Imports torch lazily; raises ``ImportError`` if torch is absent (the caller
    treats that as NMRNet being unavailable and falls back).
    """

    import torch

    if prefer:
        return torch.device(prefer)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# --------------------------------------------------------------------------- #
# Weights acquisition
# --------------------------------------------------------------------------- #
def _cache_dir() -> Path:
    return Path(
        os.environ.get(
            "MOLTRACE_NMRNET_CACHE", Path.home() / ".cache" / "moltrace" / "nmrnet"
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path) -> None:  # pragma: no cover - network I/O
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)


def _register_audit_checksum(name: str, path: Path) -> None:
    """Best-effort: record the weight checksum for audit reproducibility (Prompt 12).

    Captures the exact NMRNet checkpoint SHA-256 in the audit model registry so
    any NMRNet-assisted prediction is reproducible and traceable. Never breaks
    inference.
    """

    try:
        from moltrace.spectroscopy.audit.trail import register_model_weights

        register_model_weights(name, path)
    except Exception:  # audit capture must never break prediction
        pass


def _resolve_weights(nucleus: str, warnings: list[str]) -> Path:
    """Return the cached checkpoint path for ``nucleus``, downloading if needed.

    Raises ``NMRNetUnavailable`` if the weights are neither cached nor
    downloadable. Verifies SHA-256 when a checksum is configured.
    """

    if nucleus not in _NUCLEUS_CHECKPOINTS:
        raise NMRNetUnavailable(f"no NMRNet checkpoint mapped for nucleus {nucleus!r}")

    cache = _cache_dir()
    path = cache / _NUCLEUS_CHECKPOINTS[nucleus]
    expected = _WEIGHTS_SHA256.get(nucleus)

    if path.exists():
        if expected and _sha256(path) != expected:
            raise NMRNetUnavailable(f"checksum mismatch for cached {path.name}")
        if not expected:
            warnings.append(f"{path.name}: SHA-256 not verified (no checksum configured).")
        _register_audit_checksum(f"nmrnet:{nucleus}", path)
        return path

    base_url = os.environ.get("MOLTRACE_NMRNET_WEIGHTS_URL")
    if not base_url:
        raise NMRNetUnavailable(
            f"NMRNet weights for {nucleus} not cached at {path} and "
            f"MOLTRACE_NMRNET_WEIGHTS_URL is unset (download from Zenodo record "
            f"{_ZENODO_RECORD})"
        )
    cache.mkdir(parents=True, exist_ok=True)
    _download(f"{base_url.rstrip('/')}/{_NUCLEUS_CHECKPOINTS[nucleus]}", path)
    if expected and _sha256(path) != expected:
        path.unlink(missing_ok=True)
        raise NMRNetUnavailable(f"downloaded {path.name} failed SHA-256 verification")
    _register_audit_checksum(f"nmrnet:{nucleus}", path)
    return path


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

    Returns ``(center, shell₁, …, shell_max)``; truncating to the first ``s+1``
    entries gives the environment out to sphere ``s`` (how the fallback decreases
    the sphere). Built identically for the knowledge base and the query, so
    lookups are internally consistent.
    """

    center = mol.GetAtomWithIdx(atom_index)
    shells: list[str] = []
    visited = {atom_index}
    frontier = [atom_index]

    for sphere in range(1, max_sphere + 1):
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
            shells.extend("" for _ in range(sphere, max_sphere))
            break

    return (_atom_token(center), *shells)


def _truncate_code(code: tuple[str, ...], sphere: int) -> str:
    return "".join(code[: sphere + 1])


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
@dataclass
class KnowledgeBase:
    """HOSE-code → shift index. ``buckets[(nucleus, sphere)][code] -> [shifts]``."""

    buckets: dict[tuple[str, int], dict[str, list[float]]]
    """``buckets[(nucleus, sphere)][code] -> [n, mean, M2]`` — a Welford accumulator.

    Deliberately **not** the raw shift list. ``lookup`` only ever returns the mean,
    the population standard deviation and the count, so a running accumulator is
    lossless for the entire public contract while being O(1) per bucket instead of
    O(references). On the full NMRShiftDB2 table that is ~3 M stored floats
    collapsed to ~1 M three-element records — and, more importantly, it is
    serialisable without the molecules, which is what makes the table shippable
    (see :func:`save_knowledge_base_index`).

    Welford rather than (sum, sum-of-squares) because the latter loses precision
    to catastrophic cancellation when the variance is small relative to the mean —
    exactly the case here, where a tight bucket might hold shifts of 128.3, 128.4,
    128.4 ppm.
    """
    priors: dict[str, float]
    reference_count: int = 0
    source: str = "none"
    """Provenance of this table — ``'nmrshiftdb2'`` (built) | ``'seed'`` (bundled)."""

    def lookup(
        self, nucleus: str, code: tuple[str, ...]
    ) -> tuple[float, float, int, int] | None:
        """``(mean_ppm, std_ppm, sphere, n)`` from the highest sphere whose bucket
        holds ≥ ``_MIN_KB_MATCHES`` references, decreasing 6 → 1; else ``None``."""

        for sphere in range(_MAX_SPHERE, 0, -1):
            table = self.buckets.get((nucleus, sphere))
            if not table:
                continue
            acc = table.get(_truncate_code(code, sphere))
            if acc is None or acc[0] < _MIN_KB_MATCHES:
                continue
            n, mean, m2 = acc
            # Population standard deviation, matching statistics.pstdev.
            return float(mean), math.sqrt(max(m2, 0.0) / n), sphere, int(n)
        return None


def _new_kb() -> KnowledgeBase:
    return KnowledgeBase(buckets=defaultdict(dict), priors={})


def _index_reference_atom(
    kb: KnowledgeBase, nucleus: str, code: tuple[str, ...], shift: float
) -> None:
    """Fold one reference shift into every sphere's accumulator (Welford)."""

    for sphere in range(1, _MAX_SPHERE + 1):
        table = kb.buckets[(nucleus, sphere)]
        acc = table.get(_truncate_code(code, sphere))
        if acc is None:
            table[_truncate_code(code, sphere)] = [1, float(shift), 0.0]
            continue
        acc[0] += 1
        delta = shift - acc[1]
        acc[1] += delta / acc[0]
        acc[2] += delta * (shift - acc[1])


def _finalize_priors(kb: KnowledgeBase) -> None:
    """Element-wide mean shift, used when no environment matches.

    Computed as the count-weighted mean of the sphere-1 buckets, which is exactly
    the mean over all their references — the accumulator loses nothing here.
    """

    for nucleus in _NUCLEUS_TO_ELEMENT:
        total_n = 0
        total = 0.0
        for (nuc, sphere), table in kb.buckets.items():
            if nuc != nucleus or sphere != 1:
                continue
            for n, mean, _m2 in table.values():
                total_n += n
                total += n * mean
        if total_n:
            kb.priors[nucleus] = total / total_n


# Curated literature ¹H / ¹³C shifts (ppm, CDCl3-ish) for common solvents and
# functional groups — textbook reference values, NOT derived from NMRShiftDB2
# (so the seed carries no ShareAlike obligation). Each entry maps a SMARTS for
# the heavy atom bearing the environment to a shift; for ¹H the shift is assigned
# to that heavy atom's hydrogens. Build a full NMRShiftDB2 table for production
# coverage with ``scripts/build_hose_kb.py``.
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
    ("propane", "CCC", (("[CH3]", "13C", 15.8), ("[CH3]", "1H", 0.91),
                        ("[CH2]", "13C", 16.3), ("[CH2]", "1H", 1.32))),
    ("dimethyl_ether", "COC", (("[CH3]", "13C", 60.0), ("[CH3]", "1H", 3.27))),
    ("ethane", "CC", (("[CH3]", "13C", 6.5), ("[CH3]", "1H", 0.86))),
    ("isobutane", "CC(C)C", (("[CH3]", "13C", 24.3), ("[CH3]", "1H", 0.89),
                             ("[CH1]", "13C", 25.0), ("[CH1]", "1H", 1.56))),
    ("neopentane", "CC(C)(C)C", (("[CH3]", "13C", 31.7), ("[CH3]", "1H", 0.92))),
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
        mol_h = Chem.AddHs(mol)
        for smarts, nucleus, shift in entries:
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:  # pragma: no cover
                continue
            element = _NUCLEUS_TO_ELEMENT[nucleus]
            for match in mol.GetSubstructMatches(pattern):
                heavy_idx = match[0]
                if element == "C":
                    targets = [heavy_idx]
                else:
                    targets = [
                        nbr.GetIdx()
                        for nbr in mol_h.GetAtomWithIdx(heavy_idx).GetNeighbors()
                        if nbr.GetSymbol() == "H"
                    ]
                for atom_index in targets:
                    _index_reference_atom(kb, nucleus, hose_code(mol_h, atom_index), shift)
                    n_ref += 1
    kb.reference_count = n_ref
    kb.source = "seed"
    _finalize_priors(kb)
    return kb


_INDEX_FORMAT = "hose-index-v1"


def _open_maybe_gzip(path: Path, mode: str):
    """Open ``path``, transparently gzipped when the name ends in ``.gz``."""

    if path.suffix == ".gz":
        import gzip

        return gzip.open(path, mode + "t", encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def save_knowledge_base_index(kb: KnowledgeBase, path: str | Path) -> Path:
    """Serialise a built knowledge base as a **precomputed index**.

    This is the deployable artifact. The molecule-and-assignment form is an
    *input* format: loading it re-parses every molblock with RDKit and recomputes
    every HOSE code, which on the full NMRShiftDB2 table costs **51 s and 193 MB**
    — 83 % of it molblocks that are discarded as soon as the codes exist. A 51 s
    cold start is incompatible with a scale-to-zero service, so the table was
    effectively unshippable in that form.

    The index stores only what :meth:`KnowledgeBase.lookup` can return, so it is
    lossless for the public contract, and it loads with **no RDKit at all**.
    Write to a ``.gz`` path to compress — the loader detects it either way.
    """

    path = Path(path)
    payload = {
        "format": _INDEX_FORMAT,
        "source": kb.source,
        "reference_count": kb.reference_count,
        "priors": kb.priors,
        # "nucleus|sphere" -> {code: [n, mean, M2]}; JSON has no tuple keys.
        "buckets": {
            f"{nucleus}|{sphere}": table
            for (nucleus, sphere), table in kb.buckets.items()
            if table
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open_maybe_gzip(path, "w") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return path


def _load_index(payload: dict) -> KnowledgeBase:
    """Rebuild a knowledge base from a precomputed index. No RDKit."""

    kb = _new_kb()
    for key, table in payload["buckets"].items():
        nucleus, _, sphere = key.partition("|")
        kb.buckets[(nucleus, int(sphere))] = table
    kb.priors = dict(payload.get("priors", {}))
    kb.reference_count = int(payload.get("reference_count", 0))
    kb.source = str(payload.get("source", "none"))
    return kb


def load_knowledge_base(path: str | Path) -> KnowledgeBase:
    """Load a knowledge base from a NMRShiftDB2-style assignment export.

    JSON shape (as emitted by ``scripts/build_hose_kb.py``)::

        [{"smiles": "...", "assignments": [{"atom_index": int,
            "nucleus": "1H"|"13C", "shift_ppm": float}, ...]}, ...]

    ``atom_index`` indexes the molecule with explicit hydrogens (``AddHs`` order).

    A record may instead carry ``"molblock"``, which takes precedence. That is
    the exact route for assignment formats such as NMReDATA, whose atom numbers
    index the molfile's own atom block **including explicit hydrogens**. Rebuilding
    those through ``SMILES → AddHs`` would silently re-order the hydrogens and
    attach every ¹H shift to the wrong proton — a corruption that produces a
    plausible-looking knowledge base and is nearly undetectable downstream. When a
    source gives exact atom identity, keep it.
    """

    path = Path(path)
    with _open_maybe_gzip(path, "r") as handle:
        data = json.load(handle)

    # A precomputed index is a mapping with a format tag; the input format is a
    # list of molecules. Detect rather than switch on the filename, so a renamed
    # artifact cannot silently take the slow path.
    if isinstance(data, dict):
        fmt = data.get("format")
        if fmt != _INDEX_FORMAT:
            raise ValueError(
                f"{path}: unrecognised knowledge-base format {fmt!r} "
                f"(expected {_INDEX_FORMAT!r} or a list of molecule records)"
            )
        return _load_index(data)

    return build_knowledge_base(data)


def molecule_from_record(record: Mapping[str, Any]) -> Chem.Mol | None:
    """The H-explicit molecule a knowledge-base record describes, or ``None``.

    ``molblock`` takes precedence over ``smiles`` — see :func:`load_knowledge_base`
    for why that distinction is load-bearing rather than cosmetic.
    """

    if record.get("molblock"):
        mol = Chem.MolFromMolBlock(record["molblock"], removeHs=False)
        # ``removeHs=False`` keeps the hydrogens a molblock carries; it does not add the
        # ones it omits. A molblock written without explicit H therefore produced an
        # H-LESS molecule here, while the query path always AddHs -- and a HOSE code built
        # without hydrogens shares nothing with one built with them. Measured: every
        # comparable atom of such a record encodes differently from its own query (11/11,
        # 14/14, 10/10 across a panel), so those reference atoms could never be matched.
        #
        # AddHs is a no-op when the hydrogens are already explicit (same atom count,
        # identical codes), so this repairs the omitted case without touching any other.
        # On the NMRShiftDB2 export 100% of records take this branch and ~0.2% of them
        # were H-less, so the correction is small and the rest of the index is unchanged.
        return Chem.AddHs(mol) if mol is not None else None
    mol = Chem.MolFromSmiles(record.get("smiles", ""))
    return Chem.AddHs(mol) if mol is not None else None


def build_knowledge_base(
    records: Sequence[Mapping[str, Any]], source: str = "nmrshiftdb2"
) -> KnowledgeBase:
    """Index molecule+assignment records into a knowledge base, in memory.

    Split out from :func:`load_knowledge_base` so a *subset* of records can be
    indexed without a file — which is what held-out evaluation needs. The
    knowledge base is built from NMRShiftDB2, so scoring the predictor on
    NMRShiftDB2 molecules that are *in* it measures memorisation, not accuracy;
    an honest error bar requires training on one split and scoring on a disjoint
    one.
    """

    kb = _new_kb()
    n_ref = 0
    for record in records:
        mol_h = molecule_from_record(record)
        if mol_h is None:
            continue
        n_atoms = mol_h.GetNumAtoms()
        for assignment in record.get("assignments", []):
            nucleus = assignment["nucleus"]
            if nucleus not in _NUCLEUS_TO_ELEMENT:
                continue
            atom_index = int(assignment["atom_index"])
            if not (0 <= atom_index < n_atoms):
                continue
            _index_reference_atom(
                kb, nucleus, hose_code(mol_h, atom_index), float(assignment["shift_ppm"])
            )
            n_ref += 1
    kb.reference_count = n_ref
    kb.source = source
    _finalize_priors(kb)
    return kb


_FALLBACK_KB: KnowledgeBase | None = None


def _fallback_kb() -> KnowledgeBase:
    """The fallback KB: a built NMRShiftDB2 table if configured, else the seed.

    Unset ``MOLTRACE_HOSE_KB`` is a legitimate configuration — a dev checkout with
    no table — and quietly uses the seed. But **set-and-missing is a
    misconfiguration**, and it is logged at ERROR rather than absorbed: it is what
    a deploy that forgot to stage the table looks like, and the resulting service
    answers every request from a 16-molecule table with a ~35 ppm median ¹³C
    uncertainty. Silently substituting a far worse predictor for the one that was
    explicitly configured is the exact failure this module was fixed for.
    """

    global _FALLBACK_KB
    if _FALLBACK_KB is None:
        kb_path = os.environ.get("MOLTRACE_HOSE_KB")
        if kb_path and Path(kb_path).exists():
            _FALLBACK_KB = load_knowledge_base(kb_path)
        else:
            if kb_path:
                logging.getLogger(__name__).error(
                    "MOLTRACE_HOSE_KB is set to %r but no such file exists. Falling back "
                    "to the bundled 16-molecule seed table: shift predictions will be "
                    "far less certain (median 13C uncertainty ~35 ppm vs ~1.9 ppm) and "
                    "structure verification will discount its 13C evidence accordingly. "
                    "Build the table with scripts/build_hose_kb.py --index.",
                    kb_path,
                )
            _FALLBACK_KB = build_seed_knowledge_base()
    return _FALLBACK_KB


def knowledge_base_status() -> dict[str, object]:
    """Which knowledge base this process is (or would be) answering from.

    Cheap by design — reports configuration and file presence without loading
    anything, so health probes can call it on every hit. ``source`` /
    ``reference_count`` are populated only once :func:`_fallback_kb` has actually
    loaded a table (``loaded`` says which case you are looking at).
    """

    kb_path = os.environ.get("MOLTRACE_HOSE_KB")
    return {
        "configured": bool(kb_path),
        "path_present": bool(kb_path) and Path(kb_path).exists(),
        "loaded": _FALLBACK_KB is not None,
        "source": None if _FALLBACK_KB is None else _FALLBACK_KB.source,
        "reference_count": None if _FALLBACK_KB is None else _FALLBACK_KB.reference_count,
    }


# --------------------------------------------------------------------------- #
# Conformer generation
# --------------------------------------------------------------------------- #
def _embed_conformers(
    mol_h: Chem.Mol, n_conformers: int, warnings: list[str]
) -> list[int]:
    """ETKDGv3 ``EmbedMultipleConfs`` + MMFF (UFF fallback); retry on failure."""

    n = max(1, int(n_conformers))
    params = AllChem.ETKDGv3()
    params.randomSeed = _EMBED_BASE_SEED
    conf_ids = list(AllChem.EmbedMultipleConfs(mol_h, numConfs=n, params=params))

    if not conf_ids:
        for offset in (1, 7, 13):  # retry with fresh seeds
            params.randomSeed = _EMBED_BASE_SEED + offset
            conf_ids = list(AllChem.EmbedMultipleConfs(mol_h, numConfs=n, params=params))
            if conf_ids:
                warnings.append(f"conformer embedding succeeded after reseed (+{offset}).")
                break
    if not conf_ids:
        return []

    try:
        if AllChem.MMFFHasAllMoleculeParams(mol_h):
            AllChem.MMFFOptimizeMoleculeConfs(mol_h)
        else:
            AllChem.UFFOptimizeMoleculeConfs(mol_h)
            warnings.append("MMFF parameters unavailable; used UFF optimization.")
    except Exception as exc:  # pragma: no cover - optimisation is best-effort
        warnings.append(f"conformer optimisation failed ({exc}); using raw embeddings.")
    return conf_ids


# --------------------------------------------------------------------------- #
# NMRNet inference (optional; lazily loaded)
# --------------------------------------------------------------------------- #
def _run_nmrnet_remote(
    mol_h: Chem.Mol,
    conf_ids: list[int],
    nuclei: Sequence[str],
    warnings: list[str],
) -> dict[tuple[int, str], list[float]]:
    """Run NMRNet on the GPU sidecar, one call per conformer.

    This is the production route: the API host has no GPU and stays torch-free,
    so inference happens in ``nmrnet_service/``. Returns the same per-conformer
    value lists as the local path, so the ensemble mean/std aggregation upstream
    is identical either way.

    Raises ``NMRNetUnavailable`` on any service failure — the caller then falls
    back to HOSE *with the method recorded*. A partially-answered molecule is
    treated as a failure, not patched up with priors: mixing model shifts and
    element averages inside one result would make the uncertainty meaningless.
    """

    from moltrace.spectroscopy.predict import nmrnet_client

    try:
        base_url = nmrnet_client.service_url()
    except nmrnet_client.NMRNetServiceError as exc:
        raise NMRNetUnavailable(str(exc)) from exc
    if not base_url:
        raise NMRNetUnavailable("no NMRNet service configured")

    symbols = [atom.GetSymbol() for atom in mol_h.GetAtoms()]
    wanted = {n for n in nuclei}
    per_atom: dict[tuple[int, str], list[float]] = defaultdict(list)

    for conf_id in conf_ids:
        conformer = mol_h.GetConformer(conf_id)
        coordinates = [
            [p.x, p.y, p.z]
            for p in (conformer.GetAtomPosition(i) for i in range(mol_h.GetNumAtoms()))
        ]
        try:
            result = nmrnet_client.predict(
                symbols, coordinates, list(nuclei), base_url=base_url
            )
        except nmrnet_client.NMRNetServiceError as exc:
            raise NMRNetUnavailable(f"NMRNet service call failed: {exc}") from exc

        for atom_index, (ppm, _uncertainty) in result.items():
            element = symbols[atom_index]
            nucleus = _ELEMENT_TO_NUCLEUS.get(element)
            if nucleus is None or nucleus not in wanted:
                continue
            per_atom[(atom_index, nucleus)].append(float(ppm))

    if not per_atom:
        raise NMRNetUnavailable(
            "NMRNet service returned no shifts for the requested nuclei"
        )
    warnings.append(
        f"NMRNet: {len(conf_ids)} conformer(s) inferred on the configured service."
    )
    return dict(per_atom)


def _run_nmrnet(
    mol_h: Chem.Mol,
    conf_ids: list[int],
    nuclei: Sequence[str],
    device,  # torch.device
    warnings: list[str],
) -> dict[tuple[int, str], list[float]]:
    """Run NMRNet over each conformer → ``{(atom_index, nucleus): [ppm, ...]}``.

    Integration point: resolves per-nucleus weights (raising
    ``NMRNetUnavailable`` if unobtainable), loads them with
    ``map_location=device``, imports the NMRNet package, builds the Uni-Mol
    atoms+coords input per conformer, applies the target scaler, runs inference,
    and maps the model's atom order back to RDKit indices explicitly. The model
    forward itself comes from the NMRNet release (see ``nmrnet_service/``); this
    wrapper never fabricates outputs.
    """

    import torch

    for nucleus in nuclei:
        weights = _resolve_weights(nucleus, warnings)  # raises if absent
        try:
            importlib.import_module(os.environ.get("MOLTRACE_NMRNET_PACKAGE", "nmrnet"))
        except ImportError as exc:
            raise NMRNetUnavailable(f"NMRNet package not importable ({exc})") from exc
        torch.load(str(weights), map_location=device)  # real checkpoint load
        # Build Uni-Mol input from mol_h atoms + each conformer's coords, forward
        # through the 'nmrnet_head', inverse-transform the target scaler, and
        # align the model atom order back to RDKit indices.
        raise NMRNetUnavailable(  # integration point — fill from the NMRNet release
            "NMRNet model forward is an unfilled integration point "
            "(install the NMRNet package; see nmrnet_service/app.py for the recipe)."
        )
    return {}


def _nmrnet_predict(
    mol_h: Chem.Mol,
    conf_ids: list[int],
    nuclei: Sequence[str],
    device_pref: str | None,
    warnings: list[str],
) -> tuple[list[AtomShift], str]:
    # Remote first, and *before* importing torch: the production API host has no
    # GPU and no torch, so requiring torch to reach a remote GPU would rule out
    # the only deployment where NMRNet can actually run.
    from moltrace.spectroscopy.predict import nmrnet_client

    if nmrnet_client.service_url():
        per_atom = _run_nmrnet_remote(mol_h, conf_ids, nuclei, warnings)
        return _shifts_from_per_atom(per_atom, warnings), "remote"

    try:
        import torch  # noqa: F401
    except ImportError as exc:
        raise NMRNetUnavailable(f"PyTorch is not installed ({exc})") from exc

    device = _select_device(device_pref)
    try:
        per_atom = _run_nmrnet(mol_h, conf_ids, nuclei, device, warnings)
    except (NotImplementedError, RuntimeError) as exc:
        if getattr(device, "type", "") == "mps":  # MPS best-effort → CPU
            import torch

            warnings.append(f"MPS inference failed ({exc}); retrying on CPU.")
            device = torch.device("cpu")
            per_atom = _run_nmrnet(mol_h, conf_ids, nuclei, device, warnings)
        else:
            raise

    return _shifts_from_per_atom(per_atom, warnings), str(device)


def _shifts_from_per_atom(
    per_atom: dict[tuple[int, str], list[float]], warnings: list[str]
) -> list[AtomShift]:
    """Aggregate per-conformer values into one shift + ensemble spread per atom.

    Shared by the local and remote paths so the uncertainty means the same thing
    on both: the standard deviation across the conformer ensemble.
    """

    shifts: list[AtomShift] = []
    for (atom_index, nucleus), values in sorted(per_atom.items()):
        mean = float(statistics.fmean(values))
        if len(values) > 1:
            std = float(statistics.pstdev(values))
        else:
            std = float("nan")
            warnings.append("n_conformers == 1: per-atom uncertainty is NaN (no ensemble spread).")
        shifts.append(
            AtomShift(
                atom_index, _NUCLEUS_TO_ELEMENT[nucleus], nucleus, mean, std, source="nmrnet"
            )
        )
    return shifts


# --------------------------------------------------------------------------- #
# HOSE fallback predictor
# --------------------------------------------------------------------------- #
def _hose_predict(
    mol_h: Chem.Mol, nuclei: Sequence[str], warnings: list[str]
) -> list[AtomShift]:
    kb = _fallback_kb()
    shifts: list[AtomShift] = []
    for nucleus in nuclei:
        element = _NUCLEUS_TO_ELEMENT[nucleus]
        for atom in mol_h.GetAtoms():
            if atom.GetSymbol() != element:
                continue
            idx = atom.GetIdx()
            hit = kb.lookup(nucleus, hose_code(mol_h, idx))
            if hit is not None:
                mean, std, sphere, n = hit
                shifts.append(
                    AtomShift(
                        idx,
                        element,
                        nucleus,
                        mean,
                        std,
                        source="hose",
                        match_sphere=int(sphere),
                        match_count=int(n),
                    )
                )
                warnings.append(f"atom {idx} {nucleus}: HOSE match at sphere {sphere} (n={n}).")
            else:
                shifts.append(
                    AtomShift(
                        idx, element, nucleus,
                        kb.priors.get(nucleus, 0.0), _PRIOR_UNCERTAINTY[nucleus],
                        source="element_prior",
                    )
                )
                warnings.append(
                    f"atom {idx} {nucleus}: no HOSE match "
                    f"(n>={_MIN_KB_MATCHES}); used element prior."
                )
    return shifts


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def predict_shifts(
    smiles: str,
    nuclei: Sequence[str] = ("1H", "13C"),
    n_conformers: int = _DEFAULT_N_CONFORMERS,
    device: str | None = None,
    allow_fallback: bool = True,
) -> ShiftPrediction:
    """Predict ¹H / ¹³C chemical shifts (ppm) for ``smiles``.

    Pipeline: RDKit parse + sanitize → ``AddHs`` → ETKDGv3 ``EmbedMultipleConfs``
    (``n_conformers``) + MMFF/UFF optimise → per-conformer atom types + 3D coords
    → NMRNet inference on the resolved device → aggregate across conformers
    (mean = shift, std = uncertainty). If NMRNet is unavailable or fails (no
    torch / package / weights, embedding failure, kernel failure on both MPS and
    CPU) and ``allow_fallback`` is True, route to the HOSE-code / NMRShiftDB2
    fallback.

    Accuracy — read the method before quoting a number
    --------------------------------------------------
    The figures below are **NMRNet's published test-set MAEs**, and they apply
    only to a result with ``method == 'nmrnet'``: 0.181 ppm (¹H) / 1.098 ppm
    (¹³C) on nmrshiftdb2 experimental data, 0.020 / 0.262 ppm on the QM9-NMR DFT
    set. They are properties of that model on those benchmarks — **not** of this
    function, and not of MolTrace.

    On the ``'hose_fallback'`` path accuracy depends entirely on knowledge-base
    coverage, which :attr:`ShiftPrediction.prior_fallback_fraction` and
    :attr:`ShiftPrediction.median_uncertainty_ppm` report per call. With only the
    bundled seed table, drug-like molecules resolve ~55-75 % of atoms and the
    median ¹³C uncertainty is the 35 ppm element prior — an order of magnitude
    wider than DP4's own 2.306 ppm error scale. Never present a fallback result
    with the MAEs above.

    Raises ``ValueError`` if the SMILES cannot be parsed/sanitised.
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # pragma: no cover - MolFromSmiles usually pre-sanitises
        raise ValueError(f"Could not sanitise SMILES {smiles!r}: {exc}") from exc
    mol_h = Chem.AddHs(mol)

    warnings: list[str] = []
    active = [n for n in nuclei if n in _NUCLEUS_TO_ELEMENT]
    unsupported = [n for n in nuclei if n not in _NUCLEUS_TO_ELEMENT]
    if unsupported:
        warnings.append(f"Unsupported nuclei ignored: {unsupported}")

    if active:
        try:
            conf_ids = _embed_conformers(mol_h, n_conformers, warnings)
            if not conf_ids:
                raise NMRNetUnavailable("3D conformer embedding failed for all seeds")
            shifts, resolved_device = _nmrnet_predict(
                mol_h, conf_ids, active, device, warnings
            )
            return ShiftPrediction(
                smiles=smiles,
                method="nmrnet",
                device=resolved_device,
                shifts=shifts,
                n_conformers=len(conf_ids),
                warnings=warnings,
            )
        except NMRNetUnavailable as exc:
            if not allow_fallback:
                raise
            warnings.append(f"NMRNet unavailable ({exc}); using HOSE-code fallback.")
        except Exception as exc:  # never crash the request on an inference failure
            if not allow_fallback:
                raise
            warnings.append(f"NMRNet inference failed ({exc!r}); using HOSE-code fallback.")

    shifts = _hose_predict(mol_h, active, warnings)
    kb = _fallback_kb()
    prediction = ShiftPrediction(
        smiles=smiles,
        method="hose_fallback",
        device="cpu",
        shifts=shifts,
        n_conformers=0,
        warnings=warnings,
        kb_source=kb.source,
        kb_records=kb.reference_count,
    )

    # Summarise the degradation once, here, rather than leaving every caller to
    # sum per-atom warnings (which none of them did). A prediction that is mostly
    # element averages must announce that in one line a human or a gate can read.
    prior_fraction = prediction.prior_fallback_fraction
    if prior_fraction > 0.0:
        medians = ", ".join(
            f"{nucleus} {sigma:.2f} ppm"
            for nucleus, sigma in sorted(prediction.median_uncertainty_ppm.items())
        )
        warnings.append(
            f"Coverage: {prior_fraction:.0%} of atoms matched no environment in the "
            f"'{kb.source}' knowledge base ({kb.reference_count} reference atoms) and used "
            f"the element prior. Median uncertainty: {medians}. Treat as low-confidence."
        )
    return prediction
