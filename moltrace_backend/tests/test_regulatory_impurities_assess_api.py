"""Wire-level contract for ``POST /regulatory/impurities/assess`` (Impurity Assessment).

Pins the unified report over all five deterministic engines (ICH Q3A/B, Q3C, Q3D,
M7, FDA CPCA) + nitrosamine cumulative risk: the request/response shape, the
per-impurity graceful-degradation (unknown solvent/element/structure -> warning,
never 500), the decision-support disclaimer + ``human_review_required``, auth, and
OpenAPI registration (so the FE's ``pnpm generate:openapi`` picks up the typed
contract). The engine numerics themselves are covered by the per-engine unit suites.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

def _post(client: TestClient, body: dict, key: str | None = "test-key"):
    headers = {"x-api-key": key} if key else {}
    return client.post("/regulatory/impurities/assess", headers=headers, json=body)


def test_full_assessment_exercises_all_five_engines(client):
    body = {
        "daily_dose_g": 1.0,
        "route": "oral",
        "substance_type": "drug_substance",
        "duration_months": 120,
        "residual_solvents": [
            {"identifier": "methanol", "measured_ppm": 2000.0},
            {"identifier": "acetonitrile", "measured_ppm": 500.0},
        ],
        "elemental_impurities": [{"element": "Pb", "measured_ppm": 0.3}, {"element": "As"}],
        "structural_impurities": [
            {"smiles": "CN(C)N=O", "name": "NDMA", "measured_ng_per_day": 50.0},
            {"smiles": "Nc1ccccc1", "name": "aniline"},
        ],
    }
    with client:
        res = _post(client, body)
    assert res.status_code == 200, res.text
    j = res.json()

    # ICH Q3A/B thresholds for 1 g/day drug substance.
    assert j["thresholds"]["reporting_percent"] == 0.05
    assert j["thresholds"]["identification_percent"] == 0.10
    assert j["thresholds"]["qualification_percent"] == 0.10

    # Q3C: methanol class 2, dose-scaled permitted 30 mg/day / 1 g = 30000 ppm.
    methanol = next(s for s in j["residual_solvents"] if s["solvent_name"] == "Methanol")
    assert methanol["class_number"] == 2
    assert methanol["permitted_ppm"] == 30000.0
    assert methanol["passed"] is True

    # Q3D: Pb oral PDE 5 microg/day / 1 g = 5 ppm; measured 0.3 -> pass.
    pb = next(e for e in j["elemental_impurities"] if e["element"] == "Pb")
    assert pb["element_class"] == "1"
    assert pb["permitted_concentration_ppm"] == 5.0
    assert pb["passed"] is True

    # M7 + CPCA: NDMA is a Cohort-of-Concern nitrosamine, CPCA Category 1 (AI 26.5);
    # 50 ng/day exceeds the AI -> within_ai_limit False.
    ndma = next(s for s in j["structural_impurities"] if s["name"] == "NDMA")
    assert ndma["coc_flag"] is True
    assert ndma["cpca"]["category"] == 1
    assert ndma["cpca"]["ai_limit_ng_per_day"] == 26.5
    assert ndma["cpca"]["within_ai_limit"] is False

    # aniline is not a nitrosamine -> no CPCA block, M7 Class 3 (alerting, no data).
    aniline = next(s for s in j["structural_impurities"] if s["name"] == "aniline")
    assert aniline["cpca"] is None
    assert aniline["m7_class"] == 3

    # Cumulative nitrosamine risk fails (50 / 26.5 > 1).
    assert j["nitrosamine_cumulative_risk"]["passes"] is False
    assert j["nitrosamine_cumulative_risk"]["n_components"] == 1

    # Traceability + disclaimer.
    assert set(j["rule_set_versions"]) == {"q3ab", "q3c", "q3d", "m7", "cpca"}
    assert j["human_review_required"] is True
    assert "decision-support" in j["disclaimer"].lower()


def test_empty_request_returns_thresholds_only(client):
    with client:
        res = _post(client, {"daily_dose_g": 0.5})
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["thresholds"]["reporting_percent"] == 0.05
    assert j["residual_solvents"] == []
    assert j["elemental_impurities"] == []
    assert j["structural_impurities"] == []
    assert j["nitrosamine_cumulative_risk"] is None


def test_unknown_solvent_is_explicit_not_an_error(client):
    with client:
        res = _post(
            client, {"daily_dose_g": 1.0, "residual_solvents": [{"identifier": "unobtainium"}]}
        )
    assert res.status_code == 200, res.text
    sol = res.json()["residual_solvents"][0]
    assert sol["matched"] is False
    assert sol["class_number"] is None


def test_unknown_element_degrades_to_warning(client):
    with client:
        res = _post(client, {"daily_dose_g": 1.0, "elemental_impurities": [{"element": "Fe"}]})
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["elemental_impurities"] == []
    assert any("Fe" in w for w in j["warnings"])


def test_invalid_smiles_degrades_to_warning(client):
    with client:
        res = _post(
            client,
            {"daily_dose_g": 1.0, "structural_impurities": [{"smiles": "not_a_smiles"}]},
        )
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["structural_impurities"] == []
    assert len(j["warnings"]) == 1


def test_cutaneous_route_skips_q3c_with_warning(client):
    with client:
        res = _post(
            client,
            {
                "daily_dose_g": 1.0,
                "route": "cutaneous",
                "residual_solvents": [{"identifier": "methanol", "measured_ppm": 100.0}],
            },
        )
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["residual_solvents"] == []
    assert any("q3c" in w.lower() and "cutaneous" in w.lower() for w in j["warnings"])


def test_cumulative_risk_passes_when_below_one(client):
    with client:
        res = _post(
            client,
            {
                "daily_dose_g": 1.0,
                "structural_impurities": [
                    {"smiles": "CN(C)N=O", "measured_ng_per_day": 10.0},
                    {"smiles": "CCN(CC)N=O", "measured_ng_per_day": 10.0},
                ],
            },
        )
    assert res.status_code == 200, res.text
    cr = res.json()["nitrosamine_cumulative_risk"]
    assert cr["n_components"] == 2
    assert cr["passes"] is True  # 10/26.5 + 10/26.5 < 1


def test_requires_auth(client):
    with client:
        res = _post(client, {"daily_dose_g": 1.0}, key=None)
    assert res.status_code == 401


def test_nonpositive_dose_is_422(client):
    with client:
        res = _post(client, {"daily_dose_g": 0.0})
    assert res.status_code == 422  # Field(gt=0.0)


def test_openapi_registers_the_contract(client):
    with client:
        spec = client.get("/openapi.json").json()
    assert "/regulatory/impurities/assess" in spec["paths"]
    assert "post" in spec["paths"]["/regulatory/impurities/assess"]
    schemas = spec["components"]["schemas"]
    assert "ImpurityAssessRequest" in schemas
    assert "ImpurityAssessResult" in schemas
    assert "ImpurityCPCAOut" in schemas
