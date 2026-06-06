"""Versioned, content-addressed SpectraCheck output contract.

The pipeline (Prompts 1-9) produces rich Python objects; downstream consumers
(the Regulatory Hub, ICH reports, regression gates, the experiment tracker)
need a *stable, versioned, byte-reproducible* representation of that output.
This module provides:

* :data:`SCHEMA_VERSION` -- the contract schema version (bump on any breaking
  shape change).
* :func:`canonical_json` -- deterministic JSON serialisation (sorted keys, fixed
  float precision, no whitespace variance, NaN/Inf rejected).  This is the
  determinism kernel the end-to-end smoke test relies on: the same input must
  serialise byte-for-byte identically every run.
* :func:`content_hash` -- ``sha256:<hex>`` over the canonical JSON.
* :class:`SpectraCheckContract` -- the structured contract plus
  :meth:`~SpectraCheckContract.to_envelope` (schema version + content hash +
  payload) and :func:`contract_from_pipeline` to build one from live pipeline
  objects via duck typing (no hard import of the pipeline classes).

Only the standard library + numpy are used, so the contract layer is importable
and testable in complete isolation.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

import numpy as np

__all__ = [
    "DEFAULT_FLOAT_PRECISION",
    "DEFAULT_PIPELINE_VERSION",
    "SCHEMA_VERSION",
    "SpectraCheckContract",
    "canonical_json",
    "content_hash",
    "contract_from_pipeline",
    "build_spectracheck_contract",
]

# Bump when the contract shape changes in a backward-incompatible way.
SCHEMA_VERSION = "1.0.0"
CONTRACT_ID = "moltrace.spectracheck.contract"
DEFAULT_PIPELINE_VERSION = "spectracheck/1.0"

# Round floats to this many decimals before hashing.  Well below the noise floor
# of the (deterministic) numeric pipeline, but it normalises -0.0 vs 0.0 and any
# last-bit platform jitter so the content hash is reproducible.
DEFAULT_FLOAT_PRECISION = 6


# --------------------------------------------------------------------------- #
# Canonical serialisation
# --------------------------------------------------------------------------- #
def _normalize(obj: Any, fp: int) -> Any:
    """Recursively coerce ``obj`` into JSON-canonical primitives.

    Floats are rounded to ``fp`` decimals (and -0.0 collapsed to 0.0); numpy
    scalars/arrays, tuples, mappings, and dataclasses are converted; non-finite
    floats are rejected so a broken pipeline fails loudly instead of emitting an
    invalid contract.
    """

    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"non-finite float in contract: {obj!r}")
        rounded = round(obj, fp)
        return 0.0 if rounded == 0 else rounded
    if isinstance(obj, str):
        return obj
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return _normalize(float(obj), fp)
    if isinstance(obj, np.ndarray):
        return [_normalize(x, fp) for x in obj.tolist()]
    if isinstance(obj, Mapping):
        return {str(k): _normalize(v, fp) for k, v in obj.items()}
    if is_dataclass(obj) and not isinstance(obj, type):
        return _normalize(asdict(obj), fp)
    if isinstance(obj, (list, tuple, set, frozenset)):
        seq = sorted(obj, key=repr) if isinstance(obj, (set, frozenset)) else obj
        return [_normalize(x, fp) for x in seq]
    raise TypeError(f"cannot canonicalise object of type {type(obj)!r}")


def canonical_json(obj: Any, *, float_precision: int = DEFAULT_FLOAT_PRECISION) -> str:
    """Deterministic JSON: sorted keys, fixed float precision, compact separators.

    Two structurally-equal payloads always produce byte-identical strings,
    regardless of dict insertion order or float sign-of-zero.  Raises on
    NaN/Inf or unsupported types.
    """

    normalized = _normalize(obj, float_precision)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def content_hash(obj: Any, *, float_precision: int = DEFAULT_FLOAT_PRECISION) -> str:
    """``sha256:<hex>`` digest of :func:`canonical_json` of ``obj``."""

    payload = canonical_json(obj, float_precision=float_precision).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
# Structured contract
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SpectraCheckContract:
    """The versioned SpectraCheck output contract.

    Lists are stored already-sorted (peaks by ppm, multiplets by centre) so two
    runs that detect the same features always produce the same contract,
    independent of detection order.
    """

    nucleus: str
    solvent: str
    field_mhz: float
    ppm_range: tuple[float, float]
    n_points: int
    peaks: tuple[dict[str, Any], ...]
    multiplets: tuple[dict[str, Any], ...]
    classification_summary: dict[str, int]
    integration: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """The canonical contract body (schema version embedded)."""

        return {
            "schema_version": SCHEMA_VERSION,
            "contract_id": CONTRACT_ID,
            "spectrum": {
                "nucleus": self.nucleus,
                "solvent": self.solvent,
                "field_mhz": self.field_mhz,
                "ppm_range": list(self.ppm_range),
                "n_points": self.n_points,
            },
            "peaks": list(self.peaks),
            "multiplets": list(self.multiplets),
            "classification_summary": dict(self.classification_summary),
            "integration": dict(self.integration),
            "provenance": dict(self.provenance),
        }

    def content_hash(self) -> str:
        """Content hash of the contract body (excludes the envelope)."""

        return content_hash(self.to_dict())

    def to_envelope(self) -> dict[str, Any]:
        """The wire form: schema version + content hash + payload."""

        return {
            "schema_version": SCHEMA_VERSION,
            "content_hash": self.content_hash(),
            "contract": self.to_dict(),
        }

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_envelope())


def build_spectracheck_contract(
    *,
    nucleus: str,
    solvent: str,
    field_mhz: float,
    ppm_range: tuple[float, float],
    n_points: int,
    peaks: Sequence[Mapping[str, Any]],
    multiplets: Sequence[Mapping[str, Any]] = (),
    integration: Mapping[str, Any] | None = None,
    fingerprint_hash: str = "",
    pipeline_version: str = DEFAULT_PIPELINE_VERSION,
) -> SpectraCheckContract:
    """Assemble a :class:`SpectraCheckContract` from primitive peak/multiplet data.

    ``peaks`` entries are normalised to the canonical key set
    (``ppm``, ``intensity``, ``area``, ``width_hz``, ``category``,
    ``confidence``); the classification summary is derived from peak categories.
    Both lists are sorted to make the contract order-independent.
    """

    norm_peaks: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for raw in peaks:
        category = str(raw.get("category", "unknown"))
        norm_peaks.append(
            {
                "ppm": float(raw["ppm"]),
                "intensity": float(raw.get("intensity", 0.0)),
                "area": float(raw.get("area", 0.0)),
                "width_hz": float(raw.get("width_hz", 0.0)),
                "category": category,
                "confidence": float(raw.get("confidence", 0.0)),
            }
        )
        summary[category] = summary.get(category, 0) + 1
    norm_peaks.sort(key=lambda p: (p["ppm"], p["intensity"], p["category"]))

    norm_multiplets: list[dict[str, Any]] = []
    for raw in multiplets:
        norm_multiplets.append(
            {
                "name": str(raw.get("name", "")),
                "center_ppm": float(raw["center_ppm"]),
                "range_ppm": [float(v) for v in raw.get("range_ppm", (0.0, 0.0))],
                "multiplicity": str(raw.get("multiplicity", "")),
                "j_couplings_hz": [float(v) for v in raw.get("j_couplings_hz", ())],
                "num_nuclides": int(raw.get("num_nuclides", 0)),
            }
        )
    norm_multiplets.sort(key=lambda m: (m["center_ppm"], m["name"]))

    lo, hi = float(ppm_range[0]), float(ppm_range[1])
    if lo > hi:
        lo, hi = hi, lo

    return SpectraCheckContract(
        nucleus=str(nucleus),
        solvent=str(solvent or ""),
        field_mhz=float(field_mhz),
        ppm_range=(lo, hi),
        n_points=int(n_points),
        peaks=tuple(norm_peaks),
        multiplets=tuple(norm_multiplets),
        classification_summary=dict(sorted(summary.items())),
        integration=dict(integration or {}),
        provenance={
            "fingerprint_hash": str(fingerprint_hash or ""),
            "pipeline_version": str(pipeline_version),
            "schema_version": SCHEMA_VERSION,
        },
    )


def contract_from_pipeline(
    spectrum: Any,
    peaks: Sequence[Any],
    multiplets: Sequence[Any] = (),
    integration: Any = None,
    *,
    fingerprint_hash: str | None = None,
    pipeline_version: str = DEFAULT_PIPELINE_VERSION,
) -> SpectraCheckContract:
    """Build a contract from live pipeline objects (duck-typed, no hard imports).

    ``spectrum`` is expected to expose ``nucleus`` / ``solvent`` / ``field_mhz``
    / ``ppm_axis`` / ``fingerprint_hash``; ``peaks`` are GSD ``Peak`` objects;
    ``multiplets`` are ``Multiplet`` objects; ``integration`` is an
    ``IntegrationResult`` (or ``None``).  Only attribute access is used, so the
    contract layer stays decoupled from the pipeline's concrete classes.
    """

    ppm_axis = np.asarray(getattr(spectrum, "ppm_axis", []), dtype=float)
    if ppm_axis.size:
        ppm_range = (float(ppm_axis.min()), float(ppm_axis.max()))
    else:
        ppm_range = (0.0, 0.0)

    peak_dicts = [
        {
            "ppm": p.position_ppm,
            "intensity": getattr(p, "intensity", 0.0),
            "area": getattr(p, "area", 0.0),
            "width_hz": getattr(p, "width_hz", 0.0),
            "category": getattr(p, "category", "unknown"),
            "confidence": getattr(p, "confidence", 0.0),
        }
        for p in peaks
    ]

    multiplet_dicts = [
        {
            "name": getattr(m, "name", ""),
            "center_ppm": m.center_ppm,
            "range_ppm": tuple(getattr(m, "range_ppm", (0.0, 0.0))),
            "multiplicity": getattr(m, "multiplicity_label", ""),
            "j_couplings_hz": list(getattr(m, "j_couplings_hz", ())),
            "num_nuclides": getattr(m, "num_nuclides", 0),
        }
        for m in multiplets
    ]

    integration_dict: dict[str, Any] = {}
    if integration is not None:
        integration_dict = {
            "value": float(getattr(integration, "value", 0.0)),
            "method_used": str(getattr(integration, "method_used", "")),
            "confidence": float(getattr(integration, "confidence", 0.0)),
            "n_peaks_used": len(getattr(integration, "peaks_used", []) or []),
            "n_excluded_peaks": len(getattr(integration, "excluded_peaks", []) or []),
        }

    resolved_fingerprint = (
        fingerprint_hash
        if fingerprint_hash is not None
        else str(getattr(spectrum, "fingerprint_hash", "") or "")
    )

    return build_spectracheck_contract(
        nucleus=str(getattr(spectrum, "nucleus", "")),
        solvent=str(getattr(spectrum, "solvent", "") or ""),
        field_mhz=float(getattr(spectrum, "field_mhz", 0.0) or 0.0),
        ppm_range=ppm_range,
        n_points=int(ppm_axis.size),
        peaks=peak_dicts,
        multiplets=multiplet_dicts,
        integration=integration_dict,
        fingerprint_hash=resolved_fingerprint,
        pipeline_version=pipeline_version,
    )
