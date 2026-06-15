"""Tests for Repho R1: green-chemistry metrics engine.

Covers the frozen pure-maths core (hand-verified), the green objective scoring
branches, and the API surface (profile CRUD, per-experiment metrics, persist-to-
outcome, route comparison, and the new green optimization objectives).
"""

import pytest
from fastapi.testclient import TestClient

from nmrcheck.models import ReactionGreenComponent, ReactionGreenMetricsRequest
from nmrcheck.reaction_bo import _e_factor_to_score, _score_outcome
from nmrcheck.reaction_green import (
    _compute_green_metrics,
    _outcome_payload_from_metrics,
    greenness_from_she,
)


# --------------------------------------------------------------------------- #
# Pure-maths unit tests (deterministic, no DB)
# --------------------------------------------------------------------------- #
def test_greenness_from_she_bounds_and_monotonicity():
    assert greenness_from_she(1, 1, 1) == 100.0
    assert greenness_from_she(10, 10, 10) == 0.0
    # worse scores -> lower greenness
    assert greenness_from_she(1, 1, 1) > greenness_from_she(4, 3, 3)
    assert greenness_from_she(4, 3, 3) > greenness_from_she(8, 7, 7)
    # THF (S6, H7, E5): worst=7, mean=6 -> 100*(1-(0.6*7+0.4*6-1)/9) = 37.78
    assert greenness_from_she(6, 7, 5) == pytest.approx(37.78, abs=0.1)


def test_e_factor_to_score_transform():
    assert _e_factor_to_score(0.0) == 100.0
    assert _e_factor_to_score(1.0) == 50.0
    assert _e_factor_to_score(9.0) == 10.0
    # lower E-factor -> higher score
    assert _e_factor_to_score(2.0) > _e_factor_to_score(20.0)


def test_compute_green_metrics_hand_calculated():
    # Ethanol from acetaldehyde + H2 (100% atom economy reduction).
    payload = ReactionGreenMetricsRequest(
        product_smiles="CCO",
        product_mass_g=100.0,
        components=[
            ReactionGreenComponent(
                name="acetaldehyde", role="reactant", smiles="CC=O", equivalents=1.0, mass_g=120.0
            ),
            ReactionGreenComponent(
                name="hydrogen", role="reactant", smiles="[H][H]", equivalents=1.0, mass_g=80.0
            ),
            ReactionGreenComponent(name="THF", role="solvent", mass_g=500.0),
            ReactionGreenComponent(name="K2CO3", role="reagent", mass_g=50.0),
        ],
    )
    metrics, warnings, provenance = _compute_green_metrics(payload, solvent_overrides={})

    # total in = 120+80+500+50 = 750; product = 100
    assert metrics["e_factor"] == 6.5  # complete cEF = (750-100)/100
    assert metrics["e_factor_complete"] == 6.5
    assert metrics["e_factor_simple"] == 1.5  # excludes the 500 g solvent: (250-100)/100
    assert metrics["pmi"] == 7.5  # 750/100 (= cEF + 1)
    assert metrics["rme_percent"] == 50.0  # 100/200*100
    assert metrics["atom_economy_percent"] == 100.0  # clamped
    assert metrics["green_score"] == pytest.approx(37.78, abs=0.2)  # THF only
    assert provenance["formula_version"] == "green.v1"
    assert provenance["solvent_table_version"] == "chem21-2016"


def test_compute_green_metrics_missing_data_warns_not_crashes():
    payload = ReactionGreenMetricsRequest(
        components=[ReactionGreenComponent(name="mystery-solvent-xyz", role="solvent", mass_g=10.0)]
    )
    metrics, warnings, _ = _compute_green_metrics(payload, solvent_overrides={})
    assert "e_factor" not in metrics  # no product mass -> not computed
    assert any("E-factor" in w for w in warnings)
    assert any("not in greenness table" in w for w in warnings)


def test_compute_green_metrics_solvent_override():
    payload = ReactionGreenMetricsRequest(
        components=[ReactionGreenComponent(name="mystery", role="solvent", mass_g=10.0)]
    )
    metrics, _, _ = _compute_green_metrics(payload, solvent_overrides={"mystery": 88.0})
    assert metrics["green_score"] == 88.0


def test_score_outcome_green_objectives():
    assert _score_outcome({"atom_economy_percent": 81.0}, "maximize_atom_economy", {}) == 81.0
    assert _score_outcome({"green_score": 64.0}, "maximize_green_score", {}) == 64.0
    assert _score_outcome({"e_factor": 1.0}, "minimize_e_factor", {}) == 50.0
    # missing field -> None (dropped from training)
    assert _score_outcome({}, "maximize_green_score", {}) is None


def test_score_outcome_multi_objective_unchanged_without_green_weights():
    # Drift guard: a multi_objective score with no green weights must match the
    # legacy 4-term scalarization exactly (green terms contribute 0.0).
    outcome = {
        "yield_percent": 80.0,
        "selectivity_percent": 90.0,
        "impurity_percent": 5.0,
        "conversion_percent": 95.0,
    }
    expected = 80.0 * 0.45 + 90.0 * 0.25 + (100.0 - 5.0) * 0.20 + 95.0 * 0.10
    assert _score_outcome(outcome, "multi_objective", {}) == pytest.approx(expected)
    # Same outcome + green fields present but unweighted -> still unchanged.
    outcome_with_green = {
        **outcome,
        "e_factor": 3.0,
        "green_score": 40.0,
        "atom_economy_percent": 70.0,
    }
    assert _score_outcome(outcome_with_green, "multi_objective", {}) == pytest.approx(expected)


def test_score_outcome_multi_objective_with_green_weight_adds_term():
    outcome = {"yield_percent": 50.0, "green_score": 80.0}
    base = _score_outcome({"yield_percent": 50.0}, "multi_objective", {"yield_weight": 1.0})
    with_green = _score_outcome(
        outcome, "multi_objective", {"yield_weight": 1.0, "green_score_weight": 0.5}
    )
    assert with_green == pytest.approx(base + 80.0 * 0.5)


# --------------------------------------------------------------------------- #
# API tests
# --------------------------------------------------------------------------- #
def _sign_up(client: TestClient, email: str = "green@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(
    client: TestClient, headers: dict[str, str], *, objective: str = "maximize_green_score"
) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Green screen", "objective": objective, "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _experiment(
    client: TestClient, headers: dict[str, str], project_id: int, code: str, outcome: dict
) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/experiments",
        headers=headers,
        json={
            "experiment_code": code,
            "status": "completed",
            "conditions_json": {"solvent": "THF", "temperature_c": 60},
            "outcome_json": outcome,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _metrics_body(persist: bool = False) -> dict:
    return {
        "product_smiles": "CCO",
        "product_mass_g": 100.0,
        "persist_to_outcome": persist,
        "components": [
            {
                "name": "acetaldehyde",
                "role": "reactant",
                "smiles": "CC=O",
                "equivalents": 1.0,
                "mass_g": 120.0,
            },
            {
                "name": "hydrogen",
                "role": "reactant",
                "smiles": "[H][H]",
                "equivalents": 1.0,
                "mass_g": 80.0,
            },
            {"name": "THF", "role": "solvent", "mass_g": 500.0},
            {"name": "K2CO3", "role": "reagent", "mass_g": 50.0},
        ],
    }


def test_green_profile_crud(client):
    with client:
        headers = _sign_up(client)
        project = _project(client, headers)
        pid = project["id"]

        created = client.post(
            f"/reaction-projects/{pid}/green-profile",
            headers=headers,
            json={
                "solvent_greenness_json": {"mystery": 90},
                "solvent_table_version": "chem21-2016",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["solvent_greenness_json"] == {"mystery": 90}

        fetched = client.get(f"/reaction-projects/{pid}/green-profile", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["solvent_table_version"] == "chem21-2016"

        patched = client.patch(
            f"/reaction-projects/{pid}/green-profile",
            headers=headers,
            json={"solvent_greenness_json": {"mystery": 10}},
        )
        assert patched.status_code == 200
        assert patched.json()["solvent_greenness_json"] == {"mystery": 10}


def test_green_profile_get_missing_is_404(client):
    with client:
        headers = _sign_up(client, "green2@example.com")
        project = _project(client, headers)
        res = client.get(f"/reaction-projects/{project['id']}/green-profile", headers=headers)
        assert res.status_code == 404


def test_compute_green_metrics_endpoint(client):
    with client:
        headers = _sign_up(client, "green3@example.com")
        project = _project(client, headers)
        pid = project["id"]
        experiment = _experiment(client, headers, pid, "GRN-001", {"yield_percent": 70})

        res = client.post(
            f"/reaction-projects/{pid}/experiments/{experiment['id']}/green-metrics",
            headers=headers,
            json=_metrics_body(),
        )
        assert res.status_code == 201, res.text
        metrics = res.json()["metrics_json"]
        assert metrics["e_factor"] == 6.5
        assert metrics["pmi"] == 7.5
        assert metrics["atom_economy_percent"] == 100.0
        assert metrics["green_score"] == pytest.approx(37.78, abs=0.2)

        latest = client.get(
            f"/reaction-projects/{pid}/experiments/{experiment['id']}/green-metrics",
            headers=headers,
        )
        assert latest.status_code == 200
        assert latest.json()["metrics_json"]["pmi"] == 7.5


def test_compute_green_metrics_unknown_experiment_is_404(client):
    with client:
        headers = _sign_up(client, "green4@example.com")
        project = _project(client, headers)
        res = client.post(
            f"/reaction-projects/{project['id']}/experiments/999999/green-metrics",
            headers=headers,
            json=_metrics_body(),
        )
        assert res.status_code == 404


def test_persist_to_outcome_writes_green_fields(client):
    with client:
        headers = _sign_up(client, "green5@example.com")
        project = _project(client, headers)
        pid = project["id"]
        experiment = _experiment(client, headers, pid, "GRN-002", {"yield_percent": 70})

        res = client.post(
            f"/reaction-projects/{pid}/experiments/{experiment['id']}/green-metrics",
            headers=headers,
            json=_metrics_body(persist=True),
        )
        assert res.status_code == 201, res.text

        fetched = client.get(f"/reaction-experiments/{experiment['id']}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        outcome = fetched.json()["outcome_json"]
        assert outcome["green_score"] == pytest.approx(37.78, abs=0.2)
        assert outcome["e_factor"] == 6.5
        assert outcome["atom_economy_percent"] == 100.0
        # original field preserved
        assert outcome["yield_percent"] == 70


def test_green_compare(client):
    with client:
        headers = _sign_up(client, "green6@example.com")
        project = _project(client, headers)
        pid = project["id"]
        e1 = _experiment(client, headers, pid, "CMP-001", {"yield_percent": 60})
        e2 = _experiment(client, headers, pid, "CMP-002", {"yield_percent": 65})

        # Only e1 gets an assessment.
        client.post(
            f"/reaction-projects/{pid}/experiments/{e1['id']}/green-metrics",
            headers=headers,
            json=_metrics_body(),
        )

        res = client.post(
            f"/reaction-projects/{pid}/green-compare",
            headers=headers,
            json={"experiment_ids": [e1["id"], e2["id"]]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        by_id = {entry["reaction_experiment_id"]: entry for entry in body["entries"]}
        assert by_id[e1["id"]]["available"] is True
        assert by_id[e2["id"]]["available"] is False
        assert body["best_by_metric_json"]["e_factor"]["reaction_experiment_id"] == e1["id"]


def test_green_objective_bo_run_end_to_end(client):
    with client:
        headers = _sign_up(client, "green7@example.com")
        project = _project(client, headers, objective="maximize_green_score")
        pid = project["id"]

        client.post(
            f"/reaction-projects/{pid}/design-space",
            headers=headers,
            json={
                "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
                "categorical_variables_json": {"solvent": ["water", "THF", "DMF"]},
            },
        )
        obj = client.post(
            f"/reaction-projects/{pid}/objective-profile",
            headers=headers,
            json={"objective_type": "maximize_green_score"},
        )
        assert obj.status_code == 201, obj.text
        assert obj.json()["objective_type"] == "maximize_green_score"

        for idx, (solvent, score) in enumerate(
            [("water", 100), ("THF", 38), ("DMF", 26), ("water", 98), ("THF", 40)], start=1
        ):
            client.post(
                f"/reaction-projects/{pid}/experiments",
                headers=headers,
                json={
                    "experiment_code": f"GBO-{idx:03d}",
                    "status": "completed",
                    "conditions_json": {"temperature_c": 60, "solvent": solvent},
                    "outcome_json": {"yield_percent": 70, "green_score": score},
                },
            )

        run = client.post(
            f"/reaction-projects/{pid}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "gaussian_process_ei", "batch_size": 3},
        )
        assert run.status_code == 201, run.text
        body = run.json()
        assert body["status"] in {"succeeded", "requires_review"}
        # the green objective flowed through to the surrogate diagnostics
        assert body["diagnostics_json"]["objective_type"] == "maximize_green_score"


# --------------------------------------------------------------------------- #
# Hardening tests (from adversarial review)
# --------------------------------------------------------------------------- #
def test_compute_green_metrics_mass_conservation_warns():
    # Product heavier than all inputs is impossible -> warn, emit no E-factor/PMI.
    payload = ReactionGreenMetricsRequest(
        product_mass_g=100.0,
        components=[ReactionGreenComponent(name="A", role="reactant", mass_g=40.0)],
    )
    metrics, warnings, _ = _compute_green_metrics(payload, solvent_overrides={})
    assert "e_factor" not in metrics
    assert "pmi" not in metrics
    assert any("mass-conservation" in w for w in warnings)


def test_compute_green_metrics_solvent_dominated_skips_sef():
    # Non-solvent mass < product mass -> sEF not computed (warn); cEF still valid.
    payload = ReactionGreenMetricsRequest(
        product_mass_g=100.0,
        components=[
            ReactionGreenComponent(name="A", role="reactant", mass_g=80.0),
            ReactionGreenComponent(name="water", role="solvent", mass_g=400.0),
        ],
    )
    metrics, warnings, _ = _compute_green_metrics(payload, solvent_overrides={})
    assert metrics["e_factor"] == pytest.approx((480 - 100) / 100)  # cEF = 3.8
    assert "e_factor_simple" not in metrics
    assert any("Simple E-factor" in w for w in warnings)


def test_multi_solvent_mass_weighted_green_score():
    payload = ReactionGreenMetricsRequest(
        components=[
            ReactionGreenComponent(name="water", role="solvent", mass_g=100.0),
            ReactionGreenComponent(name="THF", role="solvent", mass_g=300.0),
        ]
    )
    metrics, _, _ = _compute_green_metrics(payload, solvent_overrides={})
    expected = (100.0 * 100.0 + 300.0 * greenness_from_she(6, 7, 5)) / 400.0
    assert metrics["green_score"] == pytest.approx(expected, abs=0.05)


def test_solvent_override_she_triple():
    payload = ReactionGreenMetricsRequest(
        components=[ReactionGreenComponent(name="mystery", role="solvent", mass_g=10.0)]
    )
    metrics, _, _ = _compute_green_metrics(payload, solvent_overrides={"mystery": [1, 1, 1]})
    assert metrics["green_score"] == 100.0


def test_atom_economy_omitted_when_rdkit_unavailable(monkeypatch):
    monkeypatch.setattr("nmrcheck.reaction_green._RDKIT_AVAILABLE", False)
    payload = ReactionGreenMetricsRequest(
        product_smiles="CCO",
        product_mass_g=100.0,
        components=[ReactionGreenComponent(name="A", role="reactant", smiles="CC=O", mass_g=200.0)],
    )
    metrics, warnings, _ = _compute_green_metrics(payload, solvent_overrides={})
    assert "atom_economy_percent" not in metrics
    assert any("RDKit unavailable" in w for w in warnings)


def test_outcome_payload_clamps_to_model_bounds():
    payload = _outcome_payload_from_metrics(
        {
            "atom_economy_percent": 150.0,  # clamp -> 100
            "rme_percent": -5.0,  # clamp -> 0
            "green_score": 42.0,  # keep
            "e_factor": -2.0,  # negative ratio -> dropped
            "pmi": 7.5,  # keep
        }
    )
    assert payload["atom_economy_percent"] == 100.0
    assert payload["rme_percent"] == 0.0
    assert payload["green_score"] == 42.0
    assert "e_factor" not in payload
    assert payload["pmi"] == 7.5


def test_green_metrics_cross_project_returns_404(client):
    # An experiment in project A must not be reachable via project B's URL.
    with client:
        headers = _sign_up(client, "green8@example.com")
        project_a = _project(client, headers)
        project_b = _project(client, headers)
        experiment = _experiment(
            client, headers, project_a["id"], "XPRJ-001", {"yield_percent": 70}
        )

        wrong = client.post(
            f"/reaction-projects/{project_b['id']}/experiments/{experiment['id']}/green-metrics",
            headers=headers,
            json=_metrics_body(),
        )
        assert wrong.status_code == 404, wrong.text

        right = client.post(
            f"/reaction-projects/{project_a['id']}/experiments/{experiment['id']}/green-metrics",
            headers=headers,
            json=_metrics_body(),
        )
        assert right.status_code == 201, right.text

        wrong_get = client.get(
            f"/reaction-projects/{project_b['id']}/experiments/{experiment['id']}/green-metrics",
            headers=headers,
        )
        assert wrong_get.status_code == 404
