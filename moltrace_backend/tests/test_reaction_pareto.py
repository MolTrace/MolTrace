"""Tests for Repho R2: true multi-objective Pareto front + hypervolume.

Three layers: the frozen pure-maths core (`reaction_pareto`), the BO integration helper
(`_compute_pareto_front`), and an end-to-end multi_objective BO run that surfaces the
Pareto front in the run diagnostics.
"""

import pytest
from fastapi.testclient import TestClient

from nmrcheck import reaction_pareto as rp
from nmrcheck.reaction_bo import _compute_pareto_front, _TrainingExample


# --------------------------------------------------------------------------- #
# Pure-maths unit tests (deterministic, no DB)
# --------------------------------------------------------------------------- #
def test_non_dominated_basic():
    # maximize both; (1,1) is dominated by everything else
    assert rp.non_dominated_indices([(3, 1), (2, 2), (1, 3), (1, 1)], ["max", "max"]) == [0, 1, 2]


def test_non_dominated_with_min_direction():
    # maximize yield, minimize impurity; (70,10) is dominated by (80,5)
    assert rp.non_dominated_indices([(80, 5), (70, 10), (75, 3)], ["max", "min"]) == [0, 2]


def test_hypervolume_2d_exact_hand_value():
    # staircase area of {(3,1),(2,2),(1,3)} above origin = 6
    hv, method = rp.hypervolume([(3, 1), (2, 2), (1, 3)], ["max", "max"])
    assert hv == pytest.approx(6.0)
    assert method == "exact_2d"


def test_hypervolume_ignores_dominated_points():
    hv, _ = rp.hypervolume([(3, 3), (1, 1)], ["max", "max"])
    assert hv == pytest.approx(9.0)  # only (3,3) counts


def test_hypervolume_3d_monte_carlo_is_deterministic():
    pts = [(80, 80, 80), (90, 70, 60), (60, 90, 75)]
    d = ["max", "max", "max"]
    hv1, m1 = rp.hypervolume(pts, d)
    hv2, _ = rp.hypervolume(pts, d)
    assert m1 == "monte_carlo"
    assert hv1 > 0 and hv1 == hv2


def test_knee_picks_balanced_point():
    assert rp.knee_index([(90, 10), (50, 50), (10, 90)], ["max", "max"]) == 1


def test_pareto_summary_shape():
    s = rp.pareto_summary([(80, 5), (70, 10), (75, 3)], ["max", "min"], labels=["yield", "impurity"])
    assert s["pareto_size"] == 2
    assert s["non_dominated_indices"] == [0, 2]
    assert s["objectives"] == ["yield", "impurity"]
    assert s["guaranteed_optimum"] is False


# --------------------------------------------------------------------------- #
# BO integration helper
# --------------------------------------------------------------------------- #
def _training(rows: list[tuple[int, str, dict]]) -> list[_TrainingExample]:
    return [
        _TrainingExample(
            experiment_id=eid,
            experiment_code=code,
            conditions={},
            outcome=outcome,
            score=0.0,
            status="completed",
        )
        for eid, code, outcome in rows
    ]


def test_compute_pareto_front_multi_objective():
    training = _training(
        [
            (1, "E1", {"yield_percent": 80, "selectivity_percent": 60, "impurity_percent": 10, "conversion_percent": 90}),
            (2, "E2", {"yield_percent": 60, "selectivity_percent": 90, "impurity_percent": 5, "conversion_percent": 70}),
            (3, "E3", {"yield_percent": 50, "selectivity_percent": 50, "impurity_percent": 20, "conversion_percent": 60}),
            (4, "E4", {"yield_percent": 85, "selectivity_percent": 85, "impurity_percent": 3, "conversion_percent": 95}),
        ]
    )
    front = _compute_pareto_front(training, "multi_objective", {})
    assert front is not None
    assert front["objectives"] == ["yield", "selectivity", "impurity", "conversion"]
    assert len(front["members"]) == 4
    by_code = {m["experiment_code"]: m for m in front["members"]}
    # E4 dominates E1, E3, E5; E2 trades selectivity -> both E2 and E4 are non-dominated.
    assert by_code["E4"]["non_dominated"] is True
    assert by_code["E2"]["non_dominated"] is True
    assert by_code["E3"]["non_dominated"] is False
    assert by_code["E1"]["non_dominated"] is False
    assert front["pareto_size"] == 2
    assert front["hypervolume"] > 0
    assert front["knee_experiment_id"] in {2, 4}
    # members carry RAW values (impurity shown as-is, not inverted)
    assert by_code["E4"]["objectives"]["impurity"] == 3


def test_compute_pareto_front_none_for_single_objective():
    training = _training([(1, "E1", {"yield_percent": 80})])
    assert _compute_pareto_front(training, "maximize_yield", {}) is None


def test_compute_pareto_front_none_when_fewer_than_two_objectives_weighted():
    # only yield weighted -> single active dimension -> no front
    training = _training(
        [
            (1, "E1", {"yield_percent": 80}),
            (2, "E2", {"yield_percent": 60}),
        ]
    )
    weights = {"yield_weight": 1.0, "selectivity_weight": 0.0, "impurity_penalty": 0.0, "conversion_weight": 0.0}
    assert _compute_pareto_front(training, "multi_objective", weights) is None


def test_compute_pareto_front_skips_incomplete_vectors():
    # only one experiment has all 4 default objectives -> fewer than two complete -> None
    training = _training(
        [
            (1, "E1", {"yield_percent": 80, "selectivity_percent": 60, "impurity_percent": 10, "conversion_percent": 90}),
            (2, "E2", {"yield_percent": 60}),  # missing selectivity/impurity/conversion
        ]
    )
    assert _compute_pareto_front(training, "multi_objective", {}) is None


# --------------------------------------------------------------------------- #
# End-to-end BO run surfaces the front in diagnostics
# --------------------------------------------------------------------------- #
def _sign_up(client: TestClient, email: str = "pareto@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _experiment(client, headers, pid, code, y, s, imp, conv):
    res = client.post(
        f"/reaction-projects/{pid}/experiments",
        headers=headers,
        json={
            "experiment_code": code,
            "status": "completed",
            "conditions_json": {"temperature_c": 60, "solvent": "MeCN", "catalyst": "Cat-A"},
            "outcome_json": {
                "yield_percent": y,
                "selectivity_percent": s,
                "impurity_percent": imp,
                "conversion_percent": conv,
            },
        },
    )
    assert res.status_code == 201, res.text


def test_bo_run_surfaces_pareto_front_in_diagnostics(client):
    with client:
        headers = _sign_up(client)
        project = client.post(
            "/reaction-projects",
            headers=headers,
            json={"name": "Pareto screen", "objective": "multi_objective", "status": "active"},
        ).json()
        pid = project["id"]
        client.post(
            f"/reaction-projects/{pid}/design-space",
            headers=headers,
            json={
                "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
                "categorical_variables_json": {"solvent": ["MeCN", "THF"], "catalyst": ["Cat-A", "Cat-B"]},
            },
        )
        client.post(
            f"/reaction-projects/{pid}/objective-profile",
            headers=headers,
            json={"objective_type": "multi_objective"},
        )
        rows = [
            ("BO-1", 80, 60, 10, 90),
            ("BO-2", 60, 90, 5, 70),
            ("BO-3", 50, 50, 20, 60),
            ("BO-4", 85, 85, 3, 95),
            ("BO-5", 70, 70, 8, 80),
        ]
        for code, y, s, imp, conv in rows:
            _experiment(client, headers, pid, code, y, s, imp, conv)

        run = client.post(
            f"/reaction-projects/{pid}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "gaussian_process_ei", "batch_size": 3},
        )
        assert run.status_code == 201, run.text
        front = run.json()["diagnostics_json"]["pareto_front"]
        assert front is not None
        assert front["objectives"] == ["yield", "selectivity", "impurity", "conversion"]
        assert len(front["members"]) == 5
        assert front["pareto_size"] >= 1
        assert front["hypervolume"] > 0
        assert any(m["non_dominated"] for m in front["members"])
        by_code = {m["experiment_code"]: m for m in front["members"]}
        assert by_code["BO-4"]["non_dominated"] is True  # dominates BO-1/3/5
        assert by_code["BO-3"]["non_dominated"] is False  # dominated by BO-4
