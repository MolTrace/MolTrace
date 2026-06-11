"""Wire-level contract for ``POST /spectrum/predict/shifts`` (Prompt 6).

Pins the request/response shape, the reported backend (the HOSE fallback in CI,
since NMRNet's deps are absent), the per-atom prediction fields, the 400
invalid-SMILES path, auth, and OpenAPI registration (so the FE session's
``npm run generate:openapi`` picks up the typed contract). The predictor's
numerical behaviour is covered in ``test_nmrnet_wrapper``; this file covers the
HTTP/Pydantic surface.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _post(client: TestClient, body: dict) -> object:
    return client.post(
        "/spectrum/predict/shifts",
        headers={"x-api-key": "test-key"},
        json=body,
    )


def test_predict_shifts_happy_path_reports_method_and_shifts(client) -> None:
    with client:
        res = _post(client, {"smiles": "c1ccccc1", "n_conformers": 4})  # benzene
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["smiles"] == "c1ccccc1"
    assert body["method"] == "hose_fallback"  # NMRNet deps absent in CI
    assert body["device"] == "cpu"
    assert "n_conformers" in body
    assert body["shift_count"] == len(body["shifts"]) > 0
    # A warning explains the fallback.
    assert any("fallback" in w.lower() for w in body["warnings"])
    # Benzene: every carbon recovered near 128.4 ppm.
    carbons = [s for s in body["shifts"] if s["element"] == "C"]
    assert carbons and all(abs(s["predicted_ppm"] - 128.4) < 0.5 for s in carbons)
    # Each shift carries the documented fields (no per-atom method/provenance now).
    sample = body["shifts"][0]
    assert set(sample) == {"atom_index", "element", "nucleus", "predicted_ppm", "uncertainty_ppm"}
    # uncertainty is a number (fallback) or null (single NMRNet conformer); never negative.
    assert sample["uncertainty_ppm"] is None or sample["uncertainty_ppm"] >= 0.0


def test_default_nuclei_predicts_both(client) -> None:
    with client:
        res = _post(client, {"smiles": "CCO"})  # ethanol has H and C
    assert res.status_code == 200, res.text
    nuclei = {s["nucleus"] for s in res.json()["shifts"]}
    assert nuclei == {"1H", "13C"}


def test_only_requested_nucleus_returned(client) -> None:
    with client:
        res = _post(client, {"smiles": "CCO", "nuclei": ["13C"]})
    assert res.status_code == 200, res.text
    shifts = res.json()["shifts"]
    assert shifts and all(s["nucleus"] == "13C" and s["element"] == "C" for s in shifts)


def test_invalid_smiles_returns_400(client) -> None:
    with client:
        res = _post(client, {"smiles": "not a molecule )("})
    assert res.status_code == 400, res.text


def test_unknown_nucleus_is_rejected_by_schema(client) -> None:
    with client:
        res = _post(client, {"smiles": "CCO", "nuclei": ["19F"]})
    assert res.status_code == 422  # not in the GSDPromptNucleus enum


def test_requires_auth(client) -> None:
    with client:
        res = client.post("/spectrum/predict/shifts", json={"smiles": "CCO"})
    assert res.status_code in (401, 403)


def test_openapi_registers_path_and_models(client) -> None:
    with client:
        spec = client.get("/openapi.json").json()
    assert "/spectrum/predict/shifts" in spec["paths"]
    assert "post" in spec["paths"]["/spectrum/predict/shifts"]
    schemas = spec["components"]["schemas"]
    assert "SpectrumPredictShiftsRequest" in schemas
    assert "SpectrumPredictShiftsResult" in schemas
    assert "AtomShiftPredictionOut" in schemas
