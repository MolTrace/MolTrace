from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'reaction_bo.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app)


def _sign_up(client: TestClient, email: str = "phase50@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str], *, objective: str = "maximize_yield") -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={
            "name": "Phase 50 coupling screen",
            "objective": objective,
            "status": "active",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _design_space(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    *,
    temperatures: list[int] | None = None,
    catalysts: list[str] | None = None,
) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/design-space",
        headers=headers,
        json={
            "numeric_variables_json": {
                "temperature_c": {"values": temperatures or [40, 60, 80]},
            },
            "categorical_variables_json": {
                "solvent": ["MeCN", "THF"],
                "catalyst": catalysts or ["Cat-A", "Cat-B"],
            },
            "fixed_conditions_json": {"base": "K2CO3"},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _objective_profile(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    *,
    objective_type: str = "maximize_yield",
) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/objective-profile",
        headers=headers,
        json={
            "objective_type": objective_type,
            "weights_json": {
                "yield_weight": 0.55,
                "selectivity_weight": 0.25,
                "impurity_penalty": 0.15,
                "conversion_weight": 0.05,
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _completed_experiment(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    index: int,
    *,
    temperature: int,
    solvent: str,
    catalyst: str,
    yield_percent: float,
    impurity_percent: float = 8,
) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/experiments",
        headers=headers,
        json={
            "experiment_code": f"BO-{index:03d}",
            "status": "completed",
            "conditions_json": {
                "temperature_c": temperature,
                "solvent": solvent,
                "catalyst": catalyst,
                "base": "K2CO3",
            },
            "outcome_json": {
                "yield_percent": yield_percent,
                "selectivity_percent": min(99, yield_percent + 12),
                "impurity_percent": impurity_percent,
                "conversion_percent": min(99, yield_percent + 18),
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _seed_five_completed(client: TestClient, headers: dict[str, str], project_id: int) -> None:
    rows = [
        (40, "MeCN", "Cat-A", 42),
        (60, "MeCN", "Cat-A", 58),
        (80, "THF", "Cat-A", 64),
        (60, "THF", "Cat-B", 71),
        (80, "MeCN", "Cat-B", 67),
    ]
    for index, (temperature, solvent, catalyst, yield_percent) in enumerate(rows, start=1):
        _completed_experiment(
            client,
            headers,
            project_id,
            index,
            temperature=temperature,
            solvent=solvent,
            catalyst=catalyst,
            yield_percent=yield_percent,
        )


def test_phase50_profiles_can_be_created(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client)
        project = _project(client, headers)

        design = _design_space(client, headers, project["id"])
        assert design["reaction_project_id"] == project["id"]
        assert "temperature_c" in design["numeric_variables_json"]

        objective = _objective_profile(client, headers, project["id"], objective_type="multi_objective")
        assert objective["objective_type"] == "multi_objective"
        assert objective["weights_json"]["yield_weight"] == 0.55

        cost = client.post(
            f"/reaction-projects/{project['id']}/cost-profile",
            headers=headers,
            json={
                "reagent_costs_json": {"base": {"K2CO3": 2}},
                "solvent_costs_json": {"solvent": {"MeCN": 4, "THF": 7}},
                "catalyst_costs_json": {"catalyst": {"Cat-A": 15, "Cat-B": 45}},
                "availability_json": {"Cat-B": True},
                "max_cost_per_experiment": 100,
                "cost_penalty_weight": 0.1,
            },
        )
        assert cost.status_code == 201, cost.text
        assert cost.json()["cost_penalty_weight"] == 0.1

        safety = client.post(
            f"/reaction-projects/{project['id']}/safety-profile",
            headers=headers,
            json={
                "blocked_reagents_json": ["diazomethane"],
                "blocked_solvents_json": ["benzene"],
                "max_temperature_c": 90,
                "max_pressure_bar": 5,
                "required_controls_json": ["reviewed_sop"],
            },
        )
        assert safety.status_code == 201, safety.text
        assert safety.json()["max_temperature_c"] == 90


def test_bo_run_with_insufficient_data_returns_exploratory_recommendations(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "low-data@example.com")
        project = _project(client, headers)
        _design_space(client, headers, project["id"])
        _objective_profile(client, headers, project["id"])
        _completed_experiment(
            client,
            headers,
            project["id"],
            1,
            temperature=40,
            solvent="MeCN",
            catalyst="Cat-A",
            yield_percent=35,
        )

        res = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "gaussian_process_ei", "batch_size": 3},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["bo_run_id"] == body["id"]
        assert body["model_type"] == "rule_based_fallback"
        assert body["input_experiment_count"] == 1
        assert body["human_review_required"] is True
        assert body["recommendations"]
        assert body["recommendations"][0]["label"] == "insufficient_data"
        assert body["recommendations"][0]["metadata_json"]["confidence_label"] == "low_data"
        assert "Fewer than 5 completed experiments" in " ".join(body["warnings"])


def test_bo_run_with_completed_experiments_returns_ranked_recommendations(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "ranked@example.com")
        project = _project(client, headers)
        _design_space(client, headers, project["id"])
        _objective_profile(client, headers, project["id"])
        _seed_five_completed(client, headers, project["id"])

        res = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "tpe_like", "batch_size": 4, "candidate_count": 40},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["status"] == "succeeded"
        assert body["model_type"] == "tpe_like"
        assert body["input_experiment_count"] == 5
        assert body["diagnostics"]["best_observed_objective"] == 71
        ranks = [item["rank"] for item in body["recommendations"]]
        assert ranks == sorted(ranks)
        scores = [item["acquisition_score"] for item in body["recommendations"]]
        assert scores == sorted(scores, reverse=True)
        assert all(item["rationale"] for item in body["recommendations"])
        assert all(item["uncertainty"] is not None for item in body["recommendations"])

        fetched = client.get(
            f"/reaction-optimization/bo-runs/{body['bo_run_id']}",
            headers=headers,
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["recommendations"][0]["bo_run_id"] == body["bo_run_id"]


def test_safety_blocked_conditions_are_not_recommended_as_allowed(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "safety@example.com")
        project = _project(client, headers)
        _design_space(client, headers, project["id"], temperatures=[40, 120])
        _objective_profile(client, headers, project["id"])
        _seed_five_completed(client, headers, project["id"])
        safety = client.post(
            f"/reaction-projects/{project['id']}/safety-profile",
            headers=headers,
            json={"max_temperature_c": 80},
        )
        assert safety.status_code == 201, safety.text

        res = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "rule_based_fallback", "batch_size": 6, "safety_aware": True},
        )
        assert res.status_code == 201, res.text
        for item in res.json()["recommendations"]:
            if item["conditions_json"].get("temperature_c", 0) > 80:
                assert item["safety_status"] != "allowed"


def test_cost_aware_mode_penalizes_expensive_conditions(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "cost@example.com")
        project = _project(client, headers)
        _design_space(
            client,
            headers,
            project["id"],
            temperatures=[60],
            catalysts=["cheap-catalyst", "expensive-catalyst"],
        )
        _objective_profile(client, headers, project["id"])
        _seed_five_completed(client, headers, project["id"])
        cost = client.post(
            f"/reaction-projects/{project['id']}/cost-profile",
            headers=headers,
            json={
                "catalyst_costs_json": {
                    "catalyst": {"cheap-catalyst": 1, "expensive-catalyst": 1000}
                },
                "cost_penalty_weight": 1,
            },
        )
        assert cost.status_code == 201, cost.text

        res = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={
                "algorithm": "rule_based_fallback",
                "batch_size": 2,
                "cost_aware": True,
                "safety_aware": False,
            },
        )
        assert res.status_code == 201, res.text
        recommendations = res.json()["recommendations"]
        assert recommendations[0]["conditions_json"]["catalyst"] == "cheap-catalyst"
        assert recommendations[0]["acquisition_score"] > recommendations[-1]["acquisition_score"]


def test_recommendation_approval_requires_reviewer_rationale(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "approval@example.com")
        project = _project(client, headers)
        _design_space(client, headers, project["id"])
        _objective_profile(client, headers, project["id"])
        _seed_five_completed(client, headers, project["id"])

        run = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "tpe_like", "batch_size": 2},
        )
        assert run.status_code == 201, run.text
        recommendation_id = run.json()["recommendations_json"][0]["recommendation_id"]

        missing = client.post(
            f"/reaction-recommendations/{recommendation_id}/approve",
            headers=headers,
            json={},
        )
        assert missing.status_code == 400, missing.text

        approved = client.post(
            f"/reaction-recommendations/{recommendation_id}/approve",
            headers=headers,
            json={"rationale": "Reviewed by a chemist before any scheduling action."},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        batch = client.post(
            f"/reaction-projects/{project['id']}/recommendation-batches",
            headers=headers,
            json={"bo_run_id": run.json()["bo_run_id"]},
        )
        assert batch.status_code == 201, batch.text
        assert batch.json()["recommendations_json"]


def test_phase50_openapi_includes_all_endpoints(tmp_path):
    client = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/reaction-projects/{reaction_project_id}/design-space",
        "/reaction-projects/{reaction_project_id}/objective-profile",
        "/reaction-projects/{reaction_project_id}/cost-profile",
        "/reaction-projects/{reaction_project_id}/safety-profile",
        "/reaction-projects/{reaction_project_id}/optimization/bo/run",
        "/reaction-projects/{reaction_project_id}/optimization/bo/runs",
        "/reaction-optimization/bo-runs/{bo_run_id}",
        "/reaction-projects/{reaction_project_id}/recommendation-batches",
        "/reaction-recommendation-batches/{batch_id}",
        "/reaction-recommendations/{recommendation_id}/approve",
        "/reaction-recommendations/{recommendation_id}/reject",
        "/reaction-projects/{reaction_project_id}/optimization/benchmark",
        "/reaction-projects/{reaction_project_id}/optimization/benchmark-runs",
    ]:
        assert path in paths
    assert "post" in paths["/reaction-projects/{reaction_project_id}/optimization/bo/run"]
    assert "patch" in paths["/reaction-projects/{reaction_project_id}/design-space"]
