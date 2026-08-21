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


def test_a_matched_solvent_is_dose_scaled_without_a_measurement(client):
    """The permitted limit must follow the dose even when nothing was measured yet.

    ICH Q3C Option 1 is a concentration limit computed at a 10 g/day reference dose; Option 2
    scales the PDE to the actual dose. Reporting the Option-1 number unlabeled at a dose other
    than 10 g/day is wrong in both directions: at 50 g/day it is 5x too permissive, and at
    2 g/day it is 5x too strict (toluene PDE 8.9 mg/day -> Option-1 890 ppm vs Option-2 178 and
    4450 ppm). A caller pricing a specification off the wrong one either passes a batch it
    should not, or rejects a good one.
    """

    with client:
        high = _post(
            client,
            {"daily_dose_g": 50.0, "residual_solvents": [{"identifier": "toluene"}]},
        )
        low = _post(
            client,
            {"daily_dose_g": 2.0, "residual_solvents": [{"identifier": "toluene"}]},
        )
    assert high.status_code == 200, high.text
    assert low.status_code == 200, low.text

    hi = high.json()["residual_solvents"][0]
    lo = low.json()["residual_solvents"][0]

    # PDE 8.9 mg/day * 1000 / dose_g
    assert hi["permitted_ppm"] == 178.0
    assert lo["permitted_ppm"] == 4450.0
    assert hi["limit_basis"] == "option_2_dose_scaled"
    assert lo["limit_basis"] == "option_2_dose_scaled"

    # The Option-1 table value stays available and stays dose-independent.
    assert hi["concentration_limit_ppm"] == 890.0
    assert lo["concentration_limit_ppm"] == 890.0


def test_at_the_reference_dose_both_options_agree(client):
    """10 g/day is the dose Option 1 is defined at, so the two must coincide exactly."""

    with client:
        res = _post(client, {"daily_dose_g": 10.0, "residual_solvents": [{"identifier": "toluene"}]})
    assert res.status_code == 200, res.text
    sol = res.json()["residual_solvents"][0]
    assert sol["permitted_ppm"] == sol["concentration_limit_ppm"] == 890.0


def test_a_class_1_solvent_does_not_dose_scale(client):
    """Class 1 carries a fixed concentration limit; scaling it would invent a limit ICH does not give."""

    with client:
        tight = _post(client, {"daily_dose_g": 0.1, "residual_solvents": [{"identifier": "benzene"}]})
        loose = _post(client, {"daily_dose_g": 50.0, "residual_solvents": [{"identifier": "benzene"}]})
    assert tight.status_code == 200, tight.text
    assert loose.status_code == 200, loose.text

    for res in (tight, loose):
        sol = res.json()["residual_solvents"][0]
        assert sol["class_number"] == 1
        assert sol["permitted_ppm"] == 2.0
        assert sol["limit_basis"] == "class_1_fixed"


def test_an_unencoded_solvent_has_no_limit_basis(client):
    """No limit was applied, so no basis may be claimed for one."""

    with client:
        res = _post(client, {"daily_dose_g": 1.0, "residual_solvents": [{"identifier": "unobtainium"}]})
    assert res.status_code == 200, res.text
    sol = res.json()["residual_solvents"][0]
    assert sol["matched"] is False
    assert sol["permitted_ppm"] is None
    assert sol["limit_basis"] is None


def test_a_measured_solvent_still_reports_its_verdict(client):
    """Dose-scaling without a measurement must not disturb the measured path."""

    with client:
        res = _post(
            client,
            {
                "daily_dose_g": 50.0,
                "residual_solvents": [{"identifier": "toluene", "measured_ppm": 500.0}],
            },
        )
    assert res.status_code == 200, res.text
    sol = res.json()["residual_solvents"][0]
    assert sol["permitted_ppm"] == 178.0
    assert sol["passed"] is False  # 500 ppm against a 178 ppm limit
    assert sol["margin_ppm"] == -322.0
    assert sol["limit_basis"] == "option_2_dose_scaled"


def test_an_unencoded_solvent_warns_at_the_top_level(client):
    """A measured solvent outside the encoded table must warn, like every other gap here.

    The encoded Q3C table is a curated subset of Appendices 1-3, so routine modern solvents
    (DMAc, cumene, 2-MeTHF, sulfolane) return ``matched=false``. Every other unassessable
    condition on this endpoint -- unsupported route, unknown element, unparseable SMILES --
    raises a top-level warning; this one was silent, leaving "we have no limit encoded"
    indistinguishable from "ICH does not list it" unless the caller inspected a row flag.
    """

    with client:
        res = _post(
            client,
            {
                "daily_dose_g": 1.0,
                "residual_solvents": [{"identifier": "N,N-dimethylacetamide", "measured_ppm": 900.0}],
            },
        )
    assert res.status_code == 200, res.text
    j = res.json()

    # Still reported, still explicit, still not an error.
    sol = j["residual_solvents"][0]
    assert sol["matched"] is False
    assert sol["passed"] is None

    warning = next(
        (w for w in j["warnings"] if "N,N-dimethylacetamide" in w),
        None,
    )
    assert warning is not None, j["warnings"]
    # The warning must say the table is ours, not ICH's -- an absent row is not a finding
    # of "unregulated", and must never read as one.
    assert "not" in warning.lower()
    assert "appendices" in warning.lower() or "appendix" in warning.lower()


def test_an_unencoded_solvent_without_a_measurement_also_warns(client):
    """Classification-only lookups need the same caveat -- the gap is the table, not the dose."""

    with client:
        res = _post(client, {"daily_dose_g": 1.0, "residual_solvents": [{"identifier": "unobtainium"}]})
    assert res.status_code == 200, res.text
    j = res.json()
    assert any("unobtainium" in w for w in j["warnings"]), j["warnings"]


def test_an_encoded_solvent_raises_no_coverage_warning(client):
    """The warning must key on the table gap, not fire on every solvent."""

    with client:
        res = _post(
            client,
            {"daily_dose_g": 1.0, "residual_solvents": [{"identifier": "methanol", "measured_ppm": 100.0}]},
        )
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["residual_solvents"][0]["matched"] is True
    assert not [w for w in j["warnings"] if "methanol" in w.lower()], j["warnings"]


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


# --------------------------------------------------------------------------- #
# Jurisdiction: the Category-1 nitrosamine limit is not the same number
# everywhere, and the difference decides pass/fail.
# --------------------------------------------------------------------------- #
_NDMA = "CN(C)N=O"  # N-nitrosodimethylamine, a Category-1 nitrosamine


def _assess_nitrosamine(client, measured_ng_per_day: float, authority: str | None):
    body: dict = {
        "daily_dose_g": 1.0,
        "structural_impurities": [
            {"smiles": _NDMA, "name": "NDMA", "measured_ng_per_day": measured_ng_per_day}
        ],
    }
    if authority is not None:
        body["authority"] = authority
    response = _post(client, body)
    assert response.status_code == 200, response.text
    return response.json()


def test_ema_applies_the_stricter_category_1_limit(client):
    """26.5 (FDA) vs 18 (EMA) ng/day is a 47 % difference, and 20 sits between.

    Every shipped path called classify_cpca() with the FDA default, so an EU
    filing was assessed against a limit it will not be judged by — and the
    verdict flipped silently on the most scrutinised number this module computes.
    """
    fda = _assess_nitrosamine(client, 20.0, "FDA")
    ema = _assess_nitrosamine(client, 20.0, "EMA")

    fda_cpca = fda["structural_impurities"][0]["cpca"]
    ema_cpca = ema["structural_impurities"][0]["cpca"]
    assert fda_cpca["ai_limit_ng_per_day"] == 26.5
    assert ema_cpca["ai_limit_ng_per_day"] == 18.0
    assert fda_cpca["within_ai_limit"] is True
    assert ema_cpca["within_ai_limit"] is False


def test_the_applied_authority_is_echoed_on_the_report(client):
    # A reader must never have to assume which limit a verdict rests on.
    assert _assess_nitrosamine(client, 20.0, "EMA")["authority"] == "EMA"
    assert _assess_nitrosamine(client, 20.0, None)["authority"] == "FDA"


def test_cumulative_risk_uses_the_same_authority(client):
    """A sum of ratios computed against FDA limits cannot be read as an EMA verdict."""
    ema = _assess_nitrosamine(client, 20.0, "EMA")
    fda = _assess_nitrosamine(client, 20.0, "FDA")
    assert (
        ema["nitrosamine_cumulative_risk"]["total_risk_ratio"]
        > fda["nitrosamine_cumulative_risk"]["total_risk_ratio"]
    )


def test_an_unknown_authority_is_refused_not_defaulted(client):
    response = _post(client, {"daily_dose_g": 1.0, "authority": "MHRA"})
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# The engine's reasoning must survive the API seam, and a caveat that changes
# what a verdict MEANS must be visible at the top level.
# --------------------------------------------------------------------------- #
_DI_NITROSO = "O=NN1CCN(N=O)CC1"  # nitrosated piperazine: two N-nitroso centres


def test_m7_reports_which_alert_fired_not_just_the_class(client):
    """A Class arriving with no structural alert or reasoning is untraceable.

    ImpurityStructuralOut kept 8 of M7Classification's 18 fields, so a reviewer
    could read the verdict but never the basis — in a module whose selling
    point is traceability.
    """
    response = _post(
        client,
        {
            "daily_dose_g": 1.0,
            "structural_impurities": [{"smiles": _NDMA, "name": "NDMA"}],
        },
    )
    assert response.status_code == 200, response.text
    structural = response.json()["structural_impurities"][0]
    assert structural["structural_alerts"], "no structural alert reported for a nitrosamine"
    assert structural["reasoning"]
    assert structural["class_definition"]
    assert structural["rule_set_version"], "the verdict is not tied to a rule-set version"


def test_cpca_reports_the_features_behind_the_potency_score(client):
    response = _post(
        client,
        {
            "daily_dose_g": 1.0,
            "structural_impurities": [
                {"smiles": _NDMA, "name": "NDMA", "measured_ng_per_day": 20.0}
            ],
        },
    )
    cpca = response.json()["structural_impurities"][0]["cpca"]
    # Which limit applied, and what the categorisation rested on.
    assert cpca["authority"] == "FDA"
    assert cpca["category_description"]
    assert cpca["alpha_h_score"] is not None
    assert isinstance(cpca["feature_evidence"], dict)
    assert cpca["method_reference"]
    assert cpca["rule_set_version"]


def test_a_multi_centre_nitrosamine_says_so_at_the_top_level(client):
    """Only the FIRST N-nitroso centre is scored.

    That caveat lived in a nested notes list the seam dropped entirely, so a
    di-nitrosamine returned a confident category indistinguishable from a
    fully-assessed mono-nitrosamine. It must reach `warnings`, which every
    client already renders.
    """
    response = _post(
        client,
        {
            "daily_dose_g": 1.0,
            "structural_impurities": [
                {"smiles": _DI_NITROSO, "name": "di-nitrosopiperazine"}
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(
        "only the first" in warning.lower() for warning in body["warnings"]
    ), f"multi-centre caveat absent from warnings: {body['warnings']}"
    # And it names the impurity, so a multi-impurity request stays readable.
    assert any("di-nitrosopiperazine" in warning for warning in body["warnings"])
    # The nested notes still carry it too.
    assert any(
        "only the first" in note.lower()
        for note in body["structural_impurities"][0]["cpca"]["notes"]
    )


def test_a_single_centre_nitrosamine_raises_no_multi_centre_warning(client):
    body = _post(
        client,
        {"daily_dose_g": 1.0, "structural_impurities": [{"smiles": _NDMA, "name": "NDMA"}]},
    ).json()
    assert not any("only the first" in warning.lower() for warning in body["warnings"])
