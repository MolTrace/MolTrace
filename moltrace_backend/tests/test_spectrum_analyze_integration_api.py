"""Wire-level contract for ``POST /spectrum/analyze/integration`` (Prompt 5).

Pins the request/response shape + the three integration methods + provenance
indices + relative-ratio normalisation + the 400 axis-mismatch path + the
OpenAPI registration (so the FE session's ``npm run generate:openapi`` picks up
the typed contract).  The numerical correctness of the methods themselves is
covered exhaustively in ``test_integration_methods``; this file covers the
HTTP/Pydantic surface.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

FIELD_MHZ = 500.0
HWHM_PPM = 0.006
COMPOUND_CENTER = 1.3
IMPURITY_CENTER = 1.7
REGION = (0.5, 2.5)
_PPM = np.linspace(4.0, 0.0, 16_384)  # descending, like NMRSpectrum


def _lorentzian(center: float, height: float) -> np.ndarray:
    return height * HWHM_PPM * HWHM_PPM / ((_PPM - center) ** 2 + HWHM_PPM * HWHM_PPM)


def _trapz(y: np.ndarray, x: np.ndarray) -> float:
    try:  # NumPy >= 2.0
        return float(abs(np.trapezoid(y, x=x)))
    except AttributeError:  # pragma: no cover - NumPy < 2.0
        return float(abs(np.trapz(y, x=x)))


def _region_integral(y: np.ndarray) -> float:
    lo, hi = REGION
    mask = (_PPM >= lo) & (_PPM <= hi)
    return _trapz(y[mask], _PPM[mask])


def _peak(center: float, height: float, area: float, category: str) -> dict[str, object]:
    return {
        "position_ppm": center,
        "position_hz": center * FIELD_MHZ,
        "intensity": height,
        "area": area,
        "width_hz": 2.0 * HWHM_PPM * FIELD_MHZ,
        "shape": "lorentzian",
        "category": category,
        "confidence": 0.95,
        "metadata": {},
    }


def _mixture(impurity_fraction: float = 0.25):
    """Synthetic compound+impurity spectrum with a known impurity area fraction.

    Returns ``(ppm_list, intensity_list, peaks_payload, true_compound)``.
    """

    compound_height = 100.0
    impurity_height = impurity_fraction / (1.0 - impurity_fraction) * compound_height
    compound_only = _lorentzian(COMPOUND_CENTER, compound_height)
    impurity_only = _lorentzian(IMPURITY_CENTER, impurity_height)

    true_compound = _region_integral(compound_only)
    impurity_area = _region_integral(impurity_only)

    peaks = [
        _peak(COMPOUND_CENTER, compound_height, true_compound, "compound"),
        _peak(IMPURITY_CENTER, impurity_height, impurity_area, "impurity"),
    ]
    intensity = (compound_only + impurity_only).tolist()
    return _PPM.tolist(), intensity, peaks, true_compound


def _post(client: TestClient, body: dict) -> object:
    return client.post(
        "/spectrum/analyze/integration",
        headers={"x-api-key": "test-key"},
        json=body,
    )


# ---------------------------------------------------------------------------
# Happy paths — the three methods
# ---------------------------------------------------------------------------
def test_edited_sum_excludes_impurity_and_recovers_compound(client) -> None:
    ppm, intensity, peaks, true_compound = _mixture(0.25)
    with client:
        res = _post(
            client,
            {
                "ppm_axis": ppm,
                "intensity": intensity,
                "peaks": peaks,
                "regions": [list(REGION)],
                "method": "edited_sum",
                "solvent": "CDCl3",
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["backend"] == "integration_prompt5"
    assert body["method"] == "edited_sum"
    assert body["region_count"] == 1
    region = body["regions"][0]
    assert abs(region["value"] - true_compound) / true_compound < 0.01
    assert region["method_used"] == "edited_sum"
    assert region["peaks_used_indices"] == [0]
    assert region["excluded_peaks_indices"] == [1]
    assert 0.0 <= region["confidence"] <= 1.0


def test_sum_method_counts_everything_and_excludes_nothing(client) -> None:
    ppm, intensity, peaks, true_compound = _mixture(0.25)
    with client:
        res = _post(
            client,
            {
                "ppm_axis": ppm,
                "intensity": intensity,
                "peaks": peaks,
                "regions": [list(REGION)],
                "method": "sum",
            },
        )
    assert res.status_code == 200, res.text
    region = res.json()["regions"][0]
    # Sum over-counts by the impurity: true_compound / (1 - 0.25).
    assert abs(region["value"] - true_compound / 0.75) / region["value"] < 0.02
    assert region["excluded_peaks_indices"] == []
    assert sorted(region["peaks_used_indices"]) == [0, 1]


def test_peaks_method_sums_compound_fitted_areas(client) -> None:
    ppm, intensity, peaks, true_compound = _mixture(0.25)
    with client:
        res = _post(
            client,
            {
                "ppm_axis": ppm,
                "intensity": intensity,
                "peaks": peaks,
                "regions": [list(REGION)],
                "method": "peaks",
            },
        )
    assert res.status_code == 200, res.text
    region = res.json()["regions"][0]
    # integrate_peaks returns the compound fitted area we supplied.
    assert abs(region["value"] - true_compound) / true_compound < 1e-6
    assert region["excluded_peaks_indices"] == [1]


def test_default_method_is_edited_sum(client) -> None:
    ppm, intensity, peaks, _true = _mixture(0.10)
    with client:
        res = _post(
            client,
            {"ppm_axis": ppm, "intensity": intensity, "peaks": peaks, "regions": [list(REGION)]},
        )
    assert res.status_code == 200, res.text
    assert res.json()["method"] == "edited_sum"
    assert res.json()["regions"][0]["method_used"] == "edited_sum"


# ---------------------------------------------------------------------------
# Multi-region behaviour + provenance
# ---------------------------------------------------------------------------
def test_relative_values_normalise_to_smallest_positive_region(client) -> None:
    ppm, intensity, peaks, _true = _mixture(0.0)  # compound only
    # A wide window (captures the whole compound) and a tight one (captures less).
    with client:
        res = _post(
            client,
            {
                "ppm_axis": ppm,
                "intensity": intensity,
                "peaks": peaks,
                "regions": [list(REGION), [1.1, 1.5]],
                "method": "sum",
            },
        )
    assert res.status_code == 200, res.text
    regions = res.json()["regions"]
    values = [r["value"] for r in regions]
    smallest = min(values)
    for r in regions:
        assert abs(r["relative_value"] - r["value"] / smallest) < 1e-9
    assert min(r["relative_value"] for r in regions) == 1.0


def test_out_of_range_region_yields_zero_with_note(client) -> None:
    ppm, intensity, peaks, _true = _mixture(0.10)
    with client:
        res = _post(
            client,
            {
                "ppm_axis": ppm,
                "intensity": intensity,
                "peaks": peaks,
                "regions": [[20.0, 25.0]],  # entirely outside the 0–4 ppm axis
                "method": "edited_sum",
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["regions"][0]["value"] == 0.0
    assert any("captured no spectrum points" in n for n in body["notes"])


# ---------------------------------------------------------------------------
# Validation + contract surface
# ---------------------------------------------------------------------------
def test_axis_length_mismatch_returns_400(client) -> None:
    ppm, intensity, peaks, _true = _mixture(0.10)
    with client:
        res = _post(
            client,
            {
                "ppm_axis": ppm,
                "intensity": intensity[:-1],  # one shorter
                "peaks": peaks,
                "regions": [list(REGION)],
            },
        )
    assert res.status_code == 400, res.text
    assert "same length" in res.json()["detail"]


def test_requires_authentication(client) -> None:
    ppm, intensity, peaks, _true = _mixture(0.10)
    with client:
        res = client.post(
            "/spectrum/analyze/integration",
            json={"ppm_axis": ppm, "intensity": intensity, "peaks": peaks, "regions": [list(REGION)]},
        )
    assert res.status_code in (401, 403)


def test_openapi_schema_includes_integration_endpoint(openapi_schema) -> None:
    schema = openapi_schema
    assert "/spectrum/analyze/integration" in schema["paths"], (
        "/spectrum/analyze/integration must appear in the OpenAPI schema so the "
        "FE session's `npm run generate:openapi` picks up the typed contract."
    )
    operation = schema["paths"]["/spectrum/analyze/integration"]["post"]
    assert "spectrum_analyze_integration" in operation["operationId"]
    assert "edited" in operation.get("description", "").lower()
