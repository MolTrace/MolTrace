"""Unit tests for the versioned SpectraCheck output contract (infra.contract)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from moltrace.spectroscopy.infra.contract import (
    SCHEMA_VERSION,
    build_spectracheck_contract,
    canonical_json,
    content_hash,
    contract_from_pipeline,
)


# --------------------------------------------------------------------------- #
# canonical_json
# --------------------------------------------------------------------------- #
def test_canonical_json_is_key_order_independent() -> None:
    a = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    b = {"c": {"x": 2, "y": 1}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_canonical_json_normalises_negative_zero() -> None:
    assert canonical_json({"v": -0.0}) == canonical_json({"v": 0.0})


def test_canonical_json_rounds_floats() -> None:
    # Beyond DEFAULT_FLOAT_PRECISION (6) the values collapse to the same string.
    assert canonical_json({"v": 1.2345671}) == canonical_json({"v": 1.2345669})


def test_canonical_json_handles_numpy() -> None:
    payload = {"arr": np.array([1.0, 2.0]), "i": np.int64(3), "f": np.float64(0.5)}
    text = canonical_json(payload)
    assert "1.0" in text and "2.0" in text and "3" in text


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json({"v": float("nan")})


def test_canonical_json_rejects_inf() -> None:
    with pytest.raises(ValueError):
        canonical_json({"v": float("inf")})


def test_canonical_json_rejects_unknown_type() -> None:
    with pytest.raises(TypeError):
        canonical_json({"v": object()})


# --------------------------------------------------------------------------- #
# content_hash
# --------------------------------------------------------------------------- #
def test_content_hash_is_stable_and_prefixed() -> None:
    h1 = content_hash({"a": 1, "b": 2})
    h2 = content_hash({"b": 2, "a": 1})
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_content_hash_changes_with_content() -> None:
    assert content_hash({"a": 1}) != content_hash({"a": 2})


# --------------------------------------------------------------------------- #
# build_spectracheck_contract
# --------------------------------------------------------------------------- #
def _peaks() -> list[dict]:
    return [
        {"ppm": 7.26, "intensity": 100.0, "category": "solvent"},
        {"ppm": 1.20, "intensity": 50.0, "category": "compound"},
        {"ppm": 3.40, "intensity": 80.0, "category": "compound"},
    ]


def test_build_contract_summary_and_sorting() -> None:
    contract = build_spectracheck_contract(
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=500.0,
        ppm_range=(0.0, 10.0),
        n_points=1024,
        peaks=_peaks(),
    )
    body = contract.to_dict()
    # Peaks sorted ascending by ppm regardless of input order.
    assert [p["ppm"] for p in body["peaks"]] == [1.20, 3.40, 7.26]
    assert body["classification_summary"] == {"compound": 2, "solvent": 1}
    assert body["schema_version"] == SCHEMA_VERSION


def test_build_contract_is_order_independent() -> None:
    forward = build_spectracheck_contract(
        nucleus="1H", solvent="CDCl3", field_mhz=500.0, ppm_range=(0.0, 10.0),
        n_points=1024, peaks=_peaks(),
    )
    reversed_ = build_spectracheck_contract(
        nucleus="1H", solvent="CDCl3", field_mhz=500.0, ppm_range=(0.0, 10.0),
        n_points=1024, peaks=list(reversed(_peaks())),
    )
    assert forward.content_hash() == reversed_.content_hash()


def test_envelope_hash_matches_body() -> None:
    contract = build_spectracheck_contract(
        nucleus="1H", solvent="CDCl3", field_mhz=500.0, ppm_range=(0.0, 10.0),
        n_points=1024, peaks=_peaks(),
    )
    envelope = contract.to_envelope()
    assert envelope["content_hash"] == content_hash(envelope["contract"])
    assert envelope["schema_version"] == SCHEMA_VERSION


def test_ppm_range_is_normalised_low_high() -> None:
    contract = build_spectracheck_contract(
        nucleus="13C", solvent="", field_mhz=125.0, ppm_range=(200.0, 0.0),
        n_points=512, peaks=[],
    )
    assert contract.to_dict()["spectrum"]["ppm_range"] == [0.0, 200.0]


# --------------------------------------------------------------------------- #
# contract_from_pipeline (duck-typed)
# --------------------------------------------------------------------------- #
def test_contract_from_pipeline_extracts_objects() -> None:
    spectrum = SimpleNamespace(
        nucleus="1H",
        solvent="DMSO",
        field_mhz=400.0,
        ppm_axis=np.linspace(0.0, 12.0, 64),
        fingerprint_hash="abc123",
    )
    peak = SimpleNamespace(
        position_ppm=2.5, intensity=42.0, area=10.0, width_hz=1.2,
        category="compound", confidence=0.9,
    )
    multiplet = SimpleNamespace(
        name="A", center_ppm=2.5, range_ppm=(2.4, 2.6),
        multiplicity_label="t", j_couplings_hz=[7.1], num_nuclides=3,
    )
    integration = SimpleNamespace(
        value=10.0, method_used="edited_sum", confidence=0.8,
        peaks_used=[peak], excluded_peaks=[],
    )
    contract = contract_from_pipeline(spectrum, [peak], [multiplet], integration)
    body = contract.to_dict()
    assert body["spectrum"]["nucleus"] == "1H"
    assert body["spectrum"]["ppm_range"] == [0.0, 12.0]
    assert body["peaks"][0]["category"] == "compound"
    assert body["multiplets"][0]["multiplicity"] == "t"
    assert body["integration"]["method_used"] == "edited_sum"
    assert body["integration"]["n_peaks_used"] == 1
    assert body["provenance"]["fingerprint_hash"] == "abc123"


def test_contract_from_pipeline_is_deterministic() -> None:
    spectrum = SimpleNamespace(
        nucleus="1H", solvent="DMSO", field_mhz=400.0,
        ppm_axis=np.linspace(0.0, 12.0, 64), fingerprint_hash="abc123",
    )
    peaks = [
        SimpleNamespace(position_ppm=p, intensity=1.0, area=1.0, width_hz=1.0,
                        category="compound", confidence=0.5)
        for p in (5.0, 1.0, 3.0)
    ]
    first = contract_from_pipeline(spectrum, peaks).to_canonical_json()
    second = contract_from_pipeline(spectrum, list(reversed(peaks))).to_canonical_json()
    assert first == second
