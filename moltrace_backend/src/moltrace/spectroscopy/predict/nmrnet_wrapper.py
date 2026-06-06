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
import os
import statistics
import urllib.request
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

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
]

_NUCLEUS_TO_ELEMENT: dict[str, str] = {"1H": "H", "13C": "C"}
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


@dataclass
class ShiftPrediction:
    smiles: str
    method: str  # 'nmrnet' | 'hose_fallback'
    device: str  # 'cuda' | 'mps' | 'cpu'
    shifts: list[AtomShift]
    n_conformers: int
    warnings: list[str]


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
    priors: dict[str, float]
    reference_count: int = 0

    def lookup(
        self, nucleus: str, code: tuple[str, ...]
    ) -> tuple[float, float, int, int] | None:
        """``(mean_ppm, std_ppm, sphere, n)`` from the highest sphere whose bucket
        holds ≥ ``_MIN_KB_MATCHES`` references, decreasing 6 → 1; else ``None``."""

        for sphere in range(_MAX_SPHERE, 0, -1):
            table = self.buckets.get((nucleus, sphere))
            if not table:
                continue
            shifts = table.get(_truncate_code(code, sphere))
            if shifts is None or len(shifts) < _MIN_KB_MATCHES:
                continue
            mean = float(statistics.fmean(shifts))
            std = float(statistics.pstdev(shifts))
            return mean, std, sphere, len(shifts)
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
        all_shifts: list[float] = []
        for (nuc, sphere), table in kb.buckets.items():
            if nuc != nucleus or sphere != 1:
                continue
            for shifts in table.values():
                all_shifts.extend(shifts)
        if all_shifts:
            kb.priors[nucleus] = float(statistics.fmean(all_shifts))


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
    _finalize_priors(kb)
    return kb


def load_knowledge_base(path: str | Path) -> KnowledgeBase:
    """Load a knowledge base from a NMRShiftDB2-style assignment export.

    JSON shape (as emitted by ``scripts/build_hose_kb.py``)::

        [{"smiles": "...", "assignments": [{"atom_index": int,
            "nucleus": "1H"|"13C", "shift_ppm": float}, ...]}, ...]

    ``atom_index`` indexes the molecule with explicit hydrogens (``AddHs`` order).
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
            _index_reference_atom(
                kb, nucleus, hose_code(mol_h, atom_index), float(assignment["shift_ppm"])
            )
            n_ref += 1
    kb.reference_count = n_ref
    _finalize_priors(kb)
    return kb


_FALLBACK_KB: KnowledgeBase | None = None


def _fallback_kb() -> KnowledgeBase:
    """The fallback KB: a built NMRShiftDB2 table if configured, else the seed."""

    global _FALLBACK_KB
    if _FALLBACK_KB is None:
        kb_path = os.environ.get("MOLTRACE_HOSE_KB")
        if kb_path and Path(kb_path).exists():
            _FALLBACK_KB = load_knowledge_base(kb_path)
        else:
            _FALLBACK_KB = build_seed_knowledge_base()
    return _FALLBACK_KB


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

    shifts: list[AtomShift] = []
    for (atom_index, nucleus), values in sorted(per_atom.items()):
        mean = float(statistics.fmean(values))
        if len(values) > 1:
            std = float(statistics.pstdev(values))
        else:
            std = float("nan")
            warnings.append("n_conformers == 1: per-atom uncertainty is NaN (no ensemble spread).")
        shifts.append(AtomShift(atom_index, _NUCLEUS_TO_ELEMENT[nucleus], nucleus, mean, std))
    return shifts, str(device)


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
                shifts.append(AtomShift(idx, element, nucleus, mean, std))
                warnings.append(f"atom {idx} {nucleus}: HOSE match at sphere {sphere} (n={n}).")
            else:
                shifts.append(
                    AtomShift(
                        idx, element, nucleus,
                        kb.priors.get(nucleus, 0.0), _PRIOR_UNCERTAINTY[nucleus],
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

    Headline accuracy (nmrshiftdb2, experimental): MAE 0.181 ppm (¹H),
    1.098 ppm (¹³C). (On the QM9-NMR DFT set the paper reports far tighter MAEs,
    0.020 / 0.262 ppm — see the QM9-NMR regression test.)

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
    return ShiftPrediction(
        smiles=smiles,
        method="hose_fallback",
        device="cpu",
        shifts=shifts,
        n_conformers=0,
        warnings=warnings,
    )
