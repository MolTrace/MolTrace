"""Phase 3 public-datasets pipeline (Prompt 20).

Ingest the canonical public scientific datasets into a normalized, versioned,
validated, **licence-aware** corpus with **frozen** train/val/test splits. This
is both the honest evaluation baseline and the fine-tuning corpus (Prompt 15);
the holdout **test** split is sacred and is never trained on.

Stages
------
* :func:`ingest` -- per-source adapter: parse to a common :class:`RawRecord`
  schema, pin the upstream version, record the licence, and content-hash the
  payload. A changed upstream hash raises :class:`UpstreamChangedError` rather
  than being silently accepted.
* :func:`normalize` -- canonicalise chemistry with RDKit (standardised SMILES +
  InChIKey), normalise spectra deterministically (optionally via matchms for
  MS), deduplicate by ``(InChIKey, spectral-hash)``, and tag every record with
  its source, licence, and provenance kind (experimental vs **computed**).
* :func:`validate` -- run the Prompt 19 validation gate (native always; Great
  Expectations when the optional ``infra`` extra is installed) and **quarantine**
  records that fail (unparseable structures, out-of-range shifts, missing
  fields) rather than dropping them silently.
* :func:`build_corpus` -- ingest+normalize+validate and **enforce licences**:
  non-redistributable sources (AIST SDBS; METLIN) are excluded from the corpus.
* :func:`freeze_splits` -- deterministic, leakage-free, seeded splits. The
  **test** split is the Prompt 17 holdout: it is experimental-only, checksummed,
  and its record hashes are returned as a hash-exclusion set that Prompt 15
  training must honour (:func:`assert_training_excludes_holdout`). Computed
  (QM9-NMR) data is never placed in val/test, and computed records that share a
  molecule with the eval set are excluded from training too.
* :func:`version_splits` -- pin each split into a content-addressed store / DVC
  remote (Prompt 19). No dataset blobs are ever committed to git.

Heavy / registration-gated extraction (per-source downloaders, real file-format
parsers) is wired by passing ``records=`` or a ``loader=`` callable to
:func:`ingest`; the existing repo loaders (e.g. ``predict.qm9nmr`` for QM9-NMR,
the NMRShiftDB2 / HMDB harness fixtures) are the reference adapters. matchms is
optional and lazily imported; the deterministic corpus hash never depends on it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from moltrace.spectroscopy.infra.contract import content_hash
from moltrace.spectroscopy.infra.validation import (
    ALLOWED_NUCLEI,
    FIELD_MHZ_RANGE,
    great_expectations_available,
    validate_spectrum_input,
    validate_with_great_expectations,
)
from moltrace.spectroscopy.infra.versioning import DatasetVersion, current_git_sha

__all__ = [
    "SOURCES",
    "CorpusBuild",
    "DatasetsPipelineError",
    "HoldoutLeakageError",
    "Licence",
    "LicenceViolationError",
    "Modality",
    "Normalized",
    "NormalizedRecord",
    "ProvenanceKind",
    "QuarantineItem",
    "RawDataset",
    "RawRecord",
    "SourceSpec",
    "Splits",
    "UpstreamChangedError",
    "ValidationOutcome",
    "assert_training_excludes_holdout",
    "build_corpus",
    "enforce_licences",
    "freeze_splits",
    "ingest",
    "matchms_available",
    "normalize",
    "validate",
    "version_splits",
]


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
class ProvenanceKind(StrEnum):
    """Whether a record is measured or computed. Computed data is never mixed
    into the experimental ground truth (it is train-only, clearly labelled)."""

    EXPERIMENTAL = "experimental"
    COMPUTED = "computed"


class Modality(StrEnum):
    NMR_1H = "nmr_1h"
    NMR_13C = "nmr_13c"
    NMR_2D_HSQC = "nmr_2d_hsqc"
    MS = "ms"
    MSMS = "msms"
    RETENTION_TIME = "retention_time"


_NMR_1D = (Modality.NMR_1H, Modality.NMR_13C)
_MS_MODALITIES = (Modality.MS, Modality.MSMS)

# Per-nucleus ppm windows for the light validation path (mirrors infra defaults).
_PPM_WINDOWS: dict[str, tuple[float, float]] = {
    "1H": (-20.0, 40.0),
    "13C": (-50.0, 300.0),
}
_DEFAULT_PPM_WINDOW = (-2000.0, 2000.0)
_MODALITY_NUCLEUS = {Modality.NMR_1H: "1H", Modality.NMR_13C: "13C"}


# --------------------------------------------------------------------------- #
# Licences
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Licence:
    """A source licence. ``redistributable=False`` means the records may be used
    for internal validation only and are NEVER copied into a corpus that could be
    redistributed. ``share_alike=True`` (e.g. CC-BY-SA) obliges any redistributed
    derivative / index to carry the same licence."""

    name: str
    redistributable: bool
    share_alike: bool
    attribution_required: bool
    url: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "redistributable": self.redistributable,
            "share_alike": self.share_alike,
            "attribution_required": self.attribution_required,
            "url": self.url,
            "notes": self.notes,
        }


# Best-effort licence metadata. Verify the current upstream terms before any
# redistribution; per-record licences can vary within a source.
_CC_BY_SA = Licence(
    "CC-BY-SA-4.0", True, True, True, "https://creativecommons.org/licenses/by-sa/4.0/"
)
_CC_BY = Licence("CC-BY-4.0", True, False, True, "https://creativecommons.org/licenses/by/4.0/")
_OPEN_ATTRIB = Licence("open (attribution; verify terms)", True, False, True)
_NO_REDIST = Licence(
    "no-redistribution (internal validation only)",
    redistributable=False,
    share_alike=False,
    attribution_required=True,
    notes="never copied into the corpus; internal validation only",
)


# --------------------------------------------------------------------------- #
# Source registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceSpec:
    key: str
    display_name: str
    licence: Licence
    provenance_kind: ProvenanceKind
    modalities: tuple[Modality, ...]
    homepage: str | None = None
    approx_size: str | None = None
    notes: str | None = None


SOURCES: dict[str, SourceSpec] = {
    "nmrshiftdb2": SourceSpec(
        "nmrshiftdb2",
        "NMRShiftDB2",
        _CC_BY_SA,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.NMR_1H, Modality.NMR_13C),
        homepage="https://nmrshiftdb.nmr.uni-koeln.de/",
        approx_size="~44,909 molecules / ~53,954 1H+13C spectra",
        notes="CC-BY-SA: share-alike applies to any redistributed derivative / index",
    ),
    "hmdb": SourceSpec(
        "hmdb",
        "Human Metabolome Database (HMDB)",
        Licence(
            "HMDB (free academic; non-commercial)",
            redistributable=True,
            share_alike=False,
            attribution_required=True,
            url="https://hmdb.ca/",
            notes="non-commercial academic use; verify HMDB terms before commercial redistribution",
        ),
        ProvenanceKind.EXPERIMENTAL,
        (Modality.NMR_1H, Modality.NMR_13C, Modality.MS, Modality.MSMS),
        homepage="https://hmdb.ca/",
        notes="metabolites with NMR + MS",
    ),
    "bmrb": SourceSpec(
        "bmrb",
        "Biological Magnetic Resonance Bank (BMRB)",
        _OPEN_ATTRIB,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.NMR_1H, Modality.NMR_13C),
        homepage="https://bmrb.io/",
        notes="freely available; cite BMRB",
    ),
    "massbank_eu": SourceSpec(
        "massbank_eu",
        "MassBank EU",
        _CC_BY,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.MSMS,),
        homepage="https://massbank.eu/",
        notes="per-record licences vary (CC-BY / CC0); check record-level licence",
    ),
    "gnps": SourceSpec(
        "gnps",
        "GNPS (UCSD)",
        _OPEN_ATTRIB,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.MSMS,),
        homepage="https://gnps.ucsd.edu/",
        notes="per-dataset licences vary; verify before redistribution",
    ),
    "metlin": SourceSpec(
        "metlin",
        "METLIN",
        _NO_REDIST,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.RETENTION_TIME, Modality.MSMS),
        homepage="https://metlin.scripps.edu/",
        notes="registration-gated; redistribution restricted -> internal validation only",
    ),
    "qm9nmr": SourceSpec(
        "qm9nmr",
        "QM9-NMR (DFT-computed)",
        _CC_BY,
        ProvenanceKind.COMPUTED,
        (Modality.NMR_1H, Modality.NMR_13C),
        homepage="https://doi.org/10.1039/D0SC04075G",
        approx_size="~130k molecules (DFT-calculated shifts)",
        notes="SYNTHETIC: computed shifts; never mixed into experimental ground truth",
    ),
    "2dnmrgym": SourceSpec(
        "2dnmrgym",
        "2DNMRGym",
        _CC_BY,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.NMR_2D_HSQC,),
        approx_size="~22k annotated HSQC spectra",
        notes="verify upstream licence before redistribution",
    ),
    "sdbs": SourceSpec(
        "sdbs",
        "AIST SDBS",
        _NO_REDIST,
        ProvenanceKind.EXPERIMENTAL,
        (Modality.NMR_1H, Modality.NMR_13C, Modality.MS),
        homepage="https://sdbs.db.aist.go.jp/",
        notes="NOT redistributable: internal validation only, never copied into the corpus",
    ),
}


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RawRecord:
    """A source-local record in the common schema, before normalization.

    ``spectrum`` is a free-form mapping: NMR uses ``{nucleus, field_mhz, ppm,
    intensity}`` (intensity optional for shift lists); MS uses
    ``{peaks: [(mz, intensity), ...], precursor_mz?}``.
    """

    source_key: str
    identifier: str
    modality: Modality
    smiles: str | None = None
    spectrum: Mapping[str, Any] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawDataset:
    source_key: str
    version: str
    licence: Licence
    provenance_kind: ProvenanceKind
    content_hash: str
    records: tuple[RawRecord, ...]
    ingested_utc: str
    git_sha: str


@dataclass(frozen=True)
class NormalizedRecord:
    source_key: str
    identifier: str
    modality: Modality
    provenance_kind: ProvenanceKind
    licence: Licence
    canonical_smiles: str | None
    inchikey: str | None
    spectrum: Mapping[str, Any] | None
    spectral_hash: str
    record_hash: str


@dataclass(frozen=True)
class Normalized:
    records: tuple[NormalizedRecord, ...]
    sources: tuple[str, ...]
    n_input: int
    n_duplicates_removed: int
    n_structure_failures: int


@dataclass(frozen=True)
class QuarantineItem:
    record: NormalizedRecord
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ValidationOutcome:
    clean: tuple[NormalizedRecord, ...]
    quarantined: tuple[QuarantineItem, ...]
    backend: str
    n_checked: int

    @property
    def n_clean(self) -> int:
        return len(self.clean)

    @property
    def n_quarantined(self) -> int:
        return len(self.quarantined)


@dataclass(frozen=True)
class CorpusBuild:
    corpus: tuple[NormalizedRecord, ...]
    quarantined: tuple[QuarantineItem, ...]
    licence_blocked: tuple[NormalizedRecord, ...]
    normalized: Normalized
    validation: ValidationOutcome


@dataclass(frozen=True)
class Splits:
    seed: int
    ratios: tuple[float, float, float]
    train: tuple[NormalizedRecord, ...]
    val: tuple[NormalizedRecord, ...]
    test: tuple[NormalizedRecord, ...]
    test_checksum: str
    holdout_exclusion_hashes: frozenset[str]
    n_computed_excluded_for_holdout: int
    created_utc: str


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class DatasetsPipelineError(RuntimeError):
    """Base class for datasets-pipeline errors."""


class UpstreamChangedError(DatasetsPipelineError):
    """Raised when an upstream content hash differs from the pinned value."""


class LicenceViolationError(DatasetsPipelineError):
    """Raised when a non-redistributable source would enter a redistributable corpus."""


class HoldoutLeakageError(DatasetsPipelineError):
    """Raised when a training set intersects the sacred test holdout."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def matchms_available() -> bool:
    return importlib.util.find_spec("matchms") is not None


def _resolve_spec(source: str | SourceSpec) -> SourceSpec:
    if isinstance(source, SourceSpec):
        return source
    try:
        return SOURCES[str(source)]
    except KeyError as exc:
        raise DatasetsPipelineError(
            f"unknown source {source!r}; known: {', '.join(sorted(SOURCES))}"
        ) from exc


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #
def _raw_record_identity(record: RawRecord) -> dict[str, Any]:
    return {
        "identifier": record.identifier,
        "modality": record.modality.value,
        "smiles": record.smiles,
        "spectrum": record.spectrum,
    }


def _records_content_hash(source_key: str, version: str, records: Sequence[RawRecord]) -> str:
    ordered = sorted(records, key=lambda r: (r.identifier, r.modality.value))
    payload = {
        "source": source_key,
        "version": version,
        "records": [_raw_record_identity(r) for r in ordered],
    }
    return content_hash(payload)


def ingest(
    source: str | SourceSpec,
    *,
    version: str,
    records: Iterable[RawRecord] | None = None,
    loader: Callable[[], Iterable[RawRecord]] | None = None,
    expected_content_hash: str | None = None,
    git_sha: str | None = None,
    ingested_utc: str | None = None,
) -> RawDataset:
    """Ingest one source into a pinned, licence-tagged, content-hashed dataset.

    Supply records via ``records=`` (pre-parsed) or ``loader=`` (a callable that
    downloads + parses). There is intentionally no built-in silent auto-download:
    pass ``expected_content_hash`` to pin the upstream version; a mismatch raises
    :class:`UpstreamChangedError` instead of accepting a changed upstream.
    """

    spec = _resolve_spec(source)
    if records is not None:
        parsed = tuple(records)
    elif loader is not None:
        parsed = tuple(loader())
    else:
        raise DatasetsPipelineError(
            f"no data for {spec.key!r}: pass records= or loader= (per-source adapter). "
            "Built-in auto-download is intentionally disabled to keep versions pinned."
        )

    digest = _records_content_hash(spec.key, version, parsed)
    if expected_content_hash is not None and digest != expected_content_hash:
        raise UpstreamChangedError(
            f"{spec.key} content hash {digest} != pinned {expected_content_hash}; "
            "refusing to silently accept a changed upstream -- re-pin deliberately."
        )

    return RawDataset(
        source_key=spec.key,
        version=version,
        licence=spec.licence,
        provenance_kind=spec.provenance_kind,
        content_hash=digest,
        records=parsed,
        ingested_utc=ingested_utc or _now_iso(),
        git_sha=git_sha or current_git_sha(),
    )


# --------------------------------------------------------------------------- #
# Normalize
# --------------------------------------------------------------------------- #
def _standardize_structure(smiles: str | None) -> tuple[str | None, str | None]:
    """Return ``(canonical_smiles, inchikey)`` via RDKit, or ``(None, None)``."""

    if not smiles:
        return None, None
    try:
        from rdkit import Chem, RDLogger

        RDLogger.DisableLog("rdApp.*")
    except Exception:  # pragma: no cover - rdkit is a core dependency
        return None, None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, None
    try:
        canonical = Chem.MolToSmiles(mol)
        inchi = Chem.MolToInchi(mol)
        inchikey = Chem.InchiToInchiKey(inchi) if inchi else None
    except Exception:
        return None, None
    return canonical, (inchikey or None)


def _normalize_intensities(values: Sequence[float]) -> list[float]:
    vals = [float(v) for v in values]
    peak = max((abs(v) for v in vals), default=0.0)
    if peak <= 0:
        return [0.0 for _ in vals]
    return [round(v / peak, 6) for v in vals]


def _normalize_peaks_matchms(peaks: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    # pragma: no cover - exercised only when the optional matchms extra is installed
    import numpy as np  # pragma: no cover
    from matchms import Spectrum  # pragma: no cover
    from matchms.filtering import normalize_intensities  # pragma: no cover

    if not peaks:  # pragma: no cover
        return []
    mz = np.array([p[0] for p in peaks], dtype=float)  # pragma: no cover
    inten = np.array([p[1] for p in peaks], dtype=float)  # pragma: no cover
    order = np.argsort(mz)  # pragma: no cover
    spec = Spectrum(mz=mz[order], intensities=inten[order])  # pragma: no cover
    spec = normalize_intensities(spec)  # pragma: no cover
    pairs = zip(spec.peaks.mz, spec.peaks.intensities, strict=False)  # pragma: no cover
    return [(float(m), float(i)) for m, i in pairs]  # pragma: no cover


def _normalize_peaks(
    peaks: Sequence[Sequence[float]], *, use_matchms: bool
) -> list[list[float]]:
    cleaned = [(round(float(mz), 6), float(i)) for mz, i in peaks if float(i) > 0]
    if use_matchms and matchms_available():  # pragma: no cover - optional path
        cleaned = [(round(float(m), 6), float(i)) for m, i in _normalize_peaks_matchms(cleaned)]
    mz_vals = [mz for mz, _ in cleaned]
    norm_i = _normalize_intensities([i for _, i in cleaned])
    out = [[mz, ni] for mz, ni in zip(mz_vals, norm_i, strict=True)]
    out.sort(key=lambda p: p[0])
    return out


def _normalize_spectrum(
    spectrum: Mapping[str, Any] | None, modality: Modality, *, use_matchms: bool
) -> dict[str, Any] | None:
    """Deterministic spectral normalization. The result (and therefore the corpus
    hash) never depends on whether matchms is installed -- matchms only refines MS
    peaks when explicitly requested via ``use_matchms``."""

    if not spectrum:
        return None
    if modality in _MS_MODALITIES:
        peaks = _normalize_peaks(spectrum.get("peaks") or [], use_matchms=use_matchms)
        out: dict[str, Any] = {"peaks": peaks}
        if spectrum.get("precursor_mz") is not None:
            out["precursor_mz"] = round(float(spectrum["precursor_mz"]), 6)
        return out
    if modality in _NMR_1D:
        out = {}
        if spectrum.get("nucleus"):
            out["nucleus"] = str(spectrum["nucleus"])
        if spectrum.get("field_mhz") is not None:
            out["field_mhz"] = round(float(spectrum["field_mhz"]), 6)
        ppm = spectrum.get("ppm")
        if ppm is not None:
            inten = spectrum.get("intensity")
            if inten is not None and len(inten) == len(ppm):
                pairs = sorted(
                    ((round(float(p), 6), float(i)) for p, i in zip(ppm, inten, strict=True)),
                    key=lambda x: x[0],
                )
                out["ppm"] = [p for p, _ in pairs]
                out["intensity"] = _normalize_intensities([i for _, i in pairs])
            else:
                out["ppm"] = sorted(round(float(p), 6) for p in ppm)
        return out
    if modality is Modality.NMR_2D_HSQC:
        pairs = spectrum.get("peaks_2d") or []
        norm = sorted([round(float(a), 6), round(float(b), 6)] for a, b in pairs)
        return {"peaks_2d": norm}
    return {k: spectrum[k] for k in sorted(spectrum)}


def _spectral_hash(spectrum_norm: Mapping[str, Any] | None, modality: Modality) -> str:
    return content_hash({"modality": modality.value, "spectrum": spectrum_norm})


def _record_hash(
    record: RawRecord, inchikey: str | None, canonical: str | None, spectral_hash: str
) -> str:
    identity = inchikey or canonical or f"{record.source_key}:{record.identifier}"
    return content_hash(
        {"identity": identity, "spectral_hash": spectral_hash, "modality": record.modality.value}
    )


def normalize(*raws: RawDataset, use_matchms: bool = False) -> Normalized:
    """Canonicalise chemistry + spectra, dedup by ``(InChIKey, spectral-hash)``,
    tag each record with source / licence / provenance kind."""

    seen: dict[tuple[str | None, str], NormalizedRecord] = {}
    n_input = 0
    n_dupes = 0
    n_struct_fail = 0
    for raw in raws:
        for rec in raw.records:
            n_input += 1
            canonical, inchikey = _standardize_structure(rec.smiles)
            if rec.smiles and inchikey is None:
                n_struct_fail += 1
            spectrum_norm = _normalize_spectrum(rec.spectrum, rec.modality, use_matchms=use_matchms)
            shash = _spectral_hash(spectrum_norm, rec.modality)
            rhash = _record_hash(rec, inchikey, canonical, shash)
            nrec = NormalizedRecord(
                source_key=raw.source_key,
                identifier=rec.identifier,
                modality=rec.modality,
                provenance_kind=raw.provenance_kind,
                licence=raw.licence,
                canonical_smiles=canonical,
                inchikey=inchikey,
                spectrum=spectrum_norm,
                spectral_hash=shash,
                record_hash=rhash,
            )
            dedup_key = (inchikey, shash)
            if dedup_key in seen:
                n_dupes += 1
                continue
            seen[dedup_key] = nrec
    records = tuple(seen.values())
    sources = tuple(sorted({r.source_key for r in records}))
    return Normalized(
        records=records,
        sources=sources,
        n_input=n_input,
        n_duplicates_removed=n_dupes,
        n_structure_failures=n_struct_fail,
    )


# --------------------------------------------------------------------------- #
# Validate (Prompt 19 gate)
# --------------------------------------------------------------------------- #
def _ppm_window(nucleus: str | None) -> tuple[float, float]:
    return _PPM_WINDOWS.get(str(nucleus), _DEFAULT_PPM_WINDOW)


def _nmr_record_reasons(rec: NormalizedRecord) -> list[str]:
    reasons: list[str] = []
    sp = rec.spectrum or {}
    nucleus = sp.get("nucleus") or _MODALITY_NUCLEUS.get(rec.modality)
    if nucleus is not None and nucleus not in ALLOWED_NUCLEI:
        reasons.append(f"nucleus: unrecognised nucleus {nucleus!r}")
    field_mhz = sp.get("field_mhz")
    if field_mhz is not None:
        lo_f, hi_f = FIELD_MHZ_RANGE
        if not (lo_f <= float(field_mhz) <= hi_f):
            reasons.append(f"field_range: field_mhz {field_mhz} outside [{lo_f}, {hi_f}]")
    ppm = sp.get("ppm")
    if not ppm:
        reasons.append("schema: missing NMR shift axis (ppm)")
        return reasons
    values = [float(p) for p in ppm]
    if any(not _is_finite(v) for v in values):
        reasons.append("nan: ppm axis contains NaN/Inf")
    else:
        lo_p, hi_p = _ppm_window(nucleus)
        if min(values) < lo_p or max(values) > hi_p:
            reasons.append(
                f"ppm_range: span [{min(values):.3f}, {max(values):.3f}] outside "
                f"[{lo_p}, {hi_p}] for {nucleus}"
            )
    # When the record carries a full spectrum, also run the native Prompt 19 gate.
    inten = sp.get("intensity")
    if field_mhz is not None and inten is not None and len(inten) == len(ppm):
        report = validate_spectrum_input(
            {"nucleus": nucleus, "field_mhz": field_mhz, "ppm_axis": ppm, "intensity": inten}
        )
        reasons += [f"{f.check}: {f.detail}" for f in report.failures]
    return reasons


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def validate(normalized: Normalized, *, use_great_expectations: bool = False) -> ValidationOutcome:
    """Gate the corpus with the Prompt 19 checks; quarantine failures with reasons."""

    clean: list[NormalizedRecord] = []
    quarantined: list[QuarantineItem] = []
    for rec in normalized.records:
        reasons: list[str] = []
        if rec.canonical_smiles is None and rec.inchikey is None:
            reasons.append("structure: SMILES missing or could not be standardised")
        if rec.modality in _NMR_1D:
            reasons += _nmr_record_reasons(rec)
        if reasons:
            quarantined.append(QuarantineItem(rec, tuple(dict.fromkeys(reasons))))
        else:
            clean.append(rec)

    backend = "native"
    if use_great_expectations and great_expectations_available():
        backend = _run_great_expectations(tuple(clean))

    return ValidationOutcome(
        clean=tuple(clean),
        quarantined=tuple(quarantined),
        backend=backend,
        n_checked=len(normalized.records),
    )


def _run_great_expectations(records: Sequence[NormalizedRecord]) -> str:  # pragma: no cover
    # pragma: no cover - exercised only when the optional infra (GE) extra is installed
    rows: list[dict[str, Any]] = []
    for rec in records:
        sp = rec.spectrum or {}
        nucleus = sp.get("nucleus") or _MODALITY_NUCLEUS.get(rec.modality)
        ppm = sp.get("ppm") or []
        inten = sp.get("intensity") or [1.0] * len(ppm)
        field_mhz = sp.get("field_mhz")
        if nucleus is None or field_mhz is None or not ppm:
            continue
        for p, i in zip(ppm, inten, strict=True):
            rows.append({
                "ppm": float(p),
                "intensity": float(i),
                "nucleus": nucleus,
                "field_mhz": float(field_mhz),
            })
    if rows:
        validate_with_great_expectations(rows)
    return "great_expectations"


# --------------------------------------------------------------------------- #
# Licence enforcement + corpus build
# --------------------------------------------------------------------------- #
def enforce_licences(
    records: Sequence[NormalizedRecord],
) -> tuple[tuple[NormalizedRecord, ...], tuple[NormalizedRecord, ...]]:
    """Split records into ``(redistributable, blocked)``. Blocked records (e.g.
    AIST SDBS, METLIN) are never written into a redistributable corpus."""

    allowed = tuple(r for r in records if r.licence.redistributable)
    blocked = tuple(r for r in records if not r.licence.redistributable)
    return allowed, blocked


def build_corpus(
    *raws: RawDataset,
    use_matchms: bool = False,
    use_great_expectations: bool = False,
    allow_non_redistributable: bool = False,
) -> CorpusBuild:
    """Ingest-normalised datasets -> normalize -> validate -> enforce licences.

    By default, non-redistributable sources are excluded from the corpus. Set
    ``allow_non_redistributable=True`` only for an explicitly internal-use build.
    """

    normalized = normalize(*raws, use_matchms=use_matchms)
    outcome = validate(normalized, use_great_expectations=use_great_expectations)
    if allow_non_redistributable:
        corpus, blocked = outcome.clean, ()
    else:
        corpus, blocked = enforce_licences(outcome.clean)
    return CorpusBuild(
        corpus=corpus,
        quarantined=outcome.quarantined,
        licence_blocked=blocked,
        normalized=normalized,
        validation=outcome,
    )


# --------------------------------------------------------------------------- #
# Frozen, leakage-free, seeded splits
# --------------------------------------------------------------------------- #
def _normalize_ratios(ratios: Sequence[float]) -> tuple[float, float, float]:
    if len(ratios) != 3:
        raise ValueError("ratios must be (train, val, test)")
    total = sum(ratios)
    if total <= 0 or any(r < 0 for r in ratios):
        raise ValueError("ratios must be non-negative and sum to a positive value")
    return (ratios[0] / total, ratios[1] / total, ratios[2] / total)


def _skeleton(rec: NormalizedRecord) -> str | None:
    """Molecule identity for leakage-free grouping: the InChIKey connectivity
    block (first 14 chars), so stereoisomers / salts never straddle splits."""

    return rec.inchikey[:14] if rec.inchikey else None


def _split_fraction(key: str, seed: int) -> float:
    digest = hashlib.sha256(f"{key}|{seed}".encode()).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


def freeze_splits(
    corpus: Sequence[NormalizedRecord],
    *,
    seed: int,
    ratios: Sequence[float] = (0.8, 0.1, 0.1),
) -> Splits:
    """Create deterministic, leakage-free train/val/test splits.

    Experimental records are grouped by molecule skeleton and assigned by a
    seeded hash, so every spectrum of a molecule lands in exactly one split.
    Computed (QM9) records are train-only and are dropped from training when they
    share a molecule with the eval (val/test) set. The **test** split is the
    sacred Prompt 17 holdout: experimental-only, checksummed, with its record
    hashes returned as a hash-exclusion set for Prompt 15 training.
    """

    tr, vr, _te = _normalize_ratios(ratios)
    experimental = [r for r in corpus if r.provenance_kind is ProvenanceKind.EXPERIMENTAL]
    computed = [r for r in corpus if r.provenance_kind is ProvenanceKind.COMPUTED]

    groups: dict[str, list[NormalizedRecord]] = {}
    for rec in experimental:
        key = _skeleton(rec) or f"rh:{rec.record_hash}"
        groups.setdefault(key, []).append(rec)

    train: list[NormalizedRecord] = []
    val: list[NormalizedRecord] = []
    test: list[NormalizedRecord] = []
    for key in sorted(groups):
        frac = _split_fraction(key, seed)
        if frac < tr:
            train.extend(groups[key])
        elif frac < tr + vr:
            val.extend(groups[key])
        else:
            test.extend(groups[key])

    eval_skeletons = {_skeleton(r) for r in (*val, *test)}
    eval_skeletons.discard(None)
    n_excluded = 0
    for rec in computed:
        if _skeleton(rec) in eval_skeletons:
            n_excluded += 1  # synthetic copy of an eval molecule -> never train on it
        else:
            train.append(rec)

    train.sort(key=lambda r: r.record_hash)
    val.sort(key=lambda r: r.record_hash)
    test.sort(key=lambda r: r.record_hash)

    test_hashes = [r.record_hash for r in test]
    test_checksum = content_hash({"seed": seed, "test_record_hashes": sorted(test_hashes)})
    return Splits(
        seed=seed,
        ratios=(tr, vr, _te),
        train=tuple(train),
        val=tuple(val),
        test=tuple(test),
        test_checksum=test_checksum,
        holdout_exclusion_hashes=frozenset(test_hashes),
        n_computed_excluded_for_holdout=n_excluded,
        created_utc=_now_iso(),
    )


def assert_training_excludes_holdout(
    training_record_hashes: Iterable[str], splits: Splits
) -> None:
    """Raise :class:`HoldoutLeakageError` if any training hash is in the holdout.

    Prompt 15 must call this on every training snapshot: the test set is sacred.
    """

    leaked = set(training_record_hashes) & splits.holdout_exclusion_hashes
    if leaked:
        raise HoldoutLeakageError(
            f"{len(leaked)} holdout record hash(es) present in the training set; "
            "the Prompt 17 test holdout must never be trained on"
        )


# --------------------------------------------------------------------------- #
# DVC / content-addressed versioning of splits
# --------------------------------------------------------------------------- #
def _record_to_dict(rec: NormalizedRecord) -> dict[str, Any]:
    return {
        "source_key": rec.source_key,
        "identifier": rec.identifier,
        "modality": rec.modality.value,
        "provenance_kind": rec.provenance_kind.value,
        "licence": rec.licence.as_dict(),
        "canonical_smiles": rec.canonical_smiles,
        "inchikey": rec.inchikey,
        "spectrum": rec.spectrum,
        "spectral_hash": rec.spectral_hash,
        "record_hash": rec.record_hash,
    }


def _write_jsonl(path: Path, records: Sequence[NormalizedRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(_record_to_dict(r), sort_keys=True, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def version_splits(
    splits: Splits,
    remote: Any,
    *,
    workdir: str | Path,
    tag_prefix: str = "moltrace-corpus",
) -> dict[str, DatasetVersion]:
    """Write each split to JSONL and pin it into a content-addressed remote.

    ``remote`` is an ``infra.versioning`` remote (``LocalDatasetRemote`` -- always
    available -- or ``DvcS3Remote``). Returns a ``DatasetVersion`` per split. The
    JSONL lives under ``workdir`` (an artifact directory, never committed to git).
    """

    work = Path(workdir)
    out: dict[str, DatasetVersion] = {}
    for name, recs in (("train", splits.train), ("val", splits.val), ("test", splits.test)):
        path = work / f"{name}.jsonl"
        _write_jsonl(path, recs)
        tag = f"{tag_prefix}-{name}-seed{splits.seed}"
        out[name] = remote.pin(path, tag)
    return out
