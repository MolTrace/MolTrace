from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'reaction.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app)


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
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


def _create_spectracheck_session(client: TestClient, headers: dict[str, str]) -> int:
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": "Reaction Evidence Project"},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()

    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={"sample_id": "RXN-EVID-001", "solvent": "CDCl3"},
    )
    assert sample_res.status_code == 201, sample_res.text
    sample = sample_res.json()

    session_res = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project["id"],
            "sample_pk": sample["id"],
            "sample_id": sample["sample_id"],
            "title": "Reaction linked evidence",
        },
    )
    assert session_res.status_code == 201, session_res.text
    session = session_res.json()

    evidence_res = client.post(
        f"/spectracheck/sessions/{session['id']}/evidence",
        headers=headers,
        json={
            "layer": "lcms",
            "title": "LCMS reaction outcome evidence",
            "source_tab": "reaction-studio",
            "status": "ready",
            "score": 0.82,
            "label": "supportive",
            "summary": "Processed evidence summary; not an identity guarantee.",
            "response_json": {"artifact_id": "safe-reference"},
        },
    )
    assert evidence_res.status_code == 201, evidence_res.text
    return session["id"]


def _add_variable(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    payload: dict,
) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/variables",
        headers=headers,
        json=payload,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_experiment(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    payload: dict,
) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/experiments",
        headers=headers,
        json=payload,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_reaction_optimization_mvp_workflow(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "chemist@example.com")

        project_res = client.post(
            "/reaction-projects",
            headers=headers,
            json={
                "name": "Amide coupling screen",
                "description": "Initial condition exploration for a coupling reaction.",
                "objective": "maximize_yield",
                "status": "active",
                "target_product_name": "Target amide",
                "target_product_smiles": "CC(=O)NC1=CC=CC=C1",
            },
        )
        assert project_res.status_code == 201, project_res.text
        project = project_res.json()
        assert project["objective"] == "maximize_yield"
        assert project["human_review_required"] is True

        temperature = _add_variable(
            client,
            headers,
            project["id"],
            {
                "name": "temperature_c",
                "variable_type": "numeric",
                "unit": "C",
                "min_value": 20,
                "max_value": 100,
                "default_value": 60,
            },
        )
        assert temperature["min_value"] == 20
        _add_variable(
            client,
            headers,
            project["id"],
            {
                "name": "solvent",
                "variable_type": "categorical",
                "allowed_values_json": ["MeCN", "THF", "EtOH"],
                "default_value": "MeCN",
            },
        )
        _add_variable(
            client,
            headers,
            project["id"],
            {
                "name": "catalyst",
                "variable_type": "categorical",
                "allowed_values_json": ["Cat-A", "Cat-B"],
                "default_value": "Cat-A",
            },
        )

        planned = _add_experiment(
            client,
            headers,
            project["id"],
            {
                "experiment_code": "RXN-000",
                "status": "planned",
                "conditions_json": {
                    "temperature_c": 60,
                    "solvent": "MeCN",
                    "catalyst": "Cat-A",
                },
            },
        )
        assert planned["status"] == "planned"

        completed = _add_experiment(
            client,
            headers,
            project["id"],
            {
                "experiment_code": "RXN-001",
                "status": "completed",
                "conditions_json": {
                    "temperature_c": 50,
                    "solvent": "MeCN",
                    "catalyst": "Cat-A",
                },
                "outcome_json": {
                    "yield_percent": 45,
                    "selectivity_percent": 70,
                    "impurity_percent": 12,
                    "conversion_percent": 58,
                    "notes": "Reviewed result.",
                },
            },
        )
        assert completed["outcome"]["yield_percent"] == 45

        low_data_run = client.post(
            f"/reaction-projects/{project['id']}/optimization/run",
            headers=headers,
            json={"model_type": "bayesian_placeholder", "max_recommendations": 4},
        )
        assert low_data_run.status_code == 201, low_data_run.text
        low_data = low_data_run.json()
        assert low_data["status"] == "requires_review"
        assert low_data["recommendations_json"]
        assert low_data["recommendations_json"][0]["label"] == "exploratory_condition"
        assert low_data["recommendations_json"][0]["uncertainty_json"]["label"] == "low_data"
        assert "placeholder" in " ".join(low_data["warnings_json"])

        _add_experiment(
            client,
            headers,
            project["id"],
            {
                "experiment_code": "RXN-002",
                "status": "completed",
                "conditions_json": {
                    "temperature_c": 70,
                    "solvent": "THF",
                    "catalyst": "Cat-A",
                },
                "outcome_json": {
                    "yield_percent": 62,
                    "selectivity_percent": 76,
                    "impurity_percent": 8,
                    "conversion_percent": 75,
                },
            },
        )
        _add_experiment(
            client,
            headers,
            project["id"],
            {
                "experiment_code": "RXN-003",
                "status": "completed",
                "conditions_json": {
                    "temperature_c": 90,
                    "solvent": "EtOH",
                    "catalyst": "Cat-B",
                },
                "outcome_json": {
                    "yield_percent": 38,
                    "selectivity_percent": 61,
                    "impurity_percent": 18,
                    "conversion_percent": 64,
                },
            },
        )

        ranked_run_res = client.post(
            f"/reaction-projects/{project['id']}/optimization/run",
            headers=headers,
            json={"model_type": "rule_based", "max_recommendations": 3},
        )
        assert ranked_run_res.status_code == 201, ranked_run_res.text
        ranked_run = ranked_run_res.json()
        assert ranked_run["status"] == "succeeded"
        assert ranked_run["metrics_json"]["best_score"] == 62
        top_recommendation = ranked_run["recommendations_json"][0]
        assert top_recommendation["label"] == "recommended_next_experiment"
        assert top_recommendation["predicted_outcome_json"]["source_experiment_code"] == "RXN-002"
        assert "not guaranteed" in top_recommendation["rationale"]

        recommendations_res = client.get(
            f"/reaction-projects/{project['id']}/recommendations",
            headers=headers,
        )
        assert recommendations_res.status_code == 200, recommendations_res.text
        recommendations = recommendations_res.json()
        assert recommendations

        approve_missing = client.post(
            f"/reaction-recommendations/{recommendations[0]['id']}/approve",
            headers=headers,
            json={},
        )
        assert approve_missing.status_code == 400, approve_missing.text

        approve_res = client.post(
            f"/reaction-recommendations/{recommendations[0]['id']}/approve",
            headers=headers,
            json={
                "reviewer_name": "Chemist Reviewer",
                "rationale": "Reviewed as a reasonable next experiment; not guaranteed.",
            },
        )
        assert approve_res.status_code == 200, approve_res.text
        assert approve_res.json()["status"] == "approved"
        assert approve_res.json()["human_review_required"] is False

        session_id = _create_spectracheck_session(client, headers)
        link_res = client.post(
            f"/reaction-experiments/{completed['id']}/link-spectracheck-session",
            headers=headers,
            json={"session_id": session_id},
        )
        assert link_res.status_code == 200, link_res.text
        assert link_res.json()["linked_spectracheck_session_id"] == session_id

        evidence_res = client.get(
            f"/reaction-experiments/{completed['id']}/evidence",
            headers=headers,
        )
        assert evidence_res.status_code == 200, evidence_res.text
        evidence = evidence_res.json()
        assert evidence["linked_spectracheck_session_id"] == session_id
        assert evidence["metadata"]["evidence_count"] == 1


def test_reaction_endpoints_appear_in_openapi(tmp_path):
    client = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/reaction-projects",
        "/reaction-projects/{reaction_project_id}",
        "/reaction-projects/{reaction_project_id}/variables",
        "/reaction-variables/{variable_id}",
        "/reaction-projects/{reaction_project_id}/experiments",
        "/reaction-experiments/{experiment_id}",
        "/reaction-projects/{reaction_project_id}/optimization/run",
        "/reaction-projects/{reaction_project_id}/optimization/runs",
        "/reaction-optimization-runs/{run_id}",
        "/reaction-projects/{reaction_project_id}/recommendations",
        "/reaction-recommendations/{recommendation_id}/approve",
        "/reaction-recommendations/{recommendation_id}/reject",
        "/reaction-experiments/{experiment_id}/link-spectracheck-session",
        "/reaction-experiments/{experiment_id}/evidence",
    ]:
        assert path in paths
    assert "post" in paths["/reaction-projects"]
    assert "post" in paths["/reaction-projects/{reaction_project_id}/optimization/run"]
