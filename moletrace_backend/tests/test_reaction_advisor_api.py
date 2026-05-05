from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'reaction_advisor.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app)


def _sign_up(client: TestClient, email: str = "advisor@example.com") -> dict[str, str]:
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


def _project(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Advisor reaction screen", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _design_space(client: TestClient, headers: dict[str, str], project_id: int) -> None:
    res = client.post(
        f"/reaction-projects/{project_id}/design-space",
        headers=headers,
        json={
            "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
            "categorical_variables_json": {"solvent": ["MeCN", "THF"], "catalyst": ["Cat-A", "Cat-B"]},
        },
    )
    assert res.status_code == 201, res.text


def _completed(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    index: int,
    *,
    temperature: int,
    solvent: str,
    catalyst: str,
    yield_percent: float,
) -> None:
    res = client.post(
        f"/reaction-projects/{project_id}/experiments",
        headers=headers,
        json={
            "experiment_code": f"ADV-{index:03d}",
            "status": "completed",
            "conditions_json": {
                "temperature_c": temperature,
                "solvent": solvent,
                "catalyst": catalyst,
            },
            "outcome_json": {
                "yield_percent": yield_percent,
                "selectivity_percent": min(99, yield_percent + 10),
                "impurity_percent": 9,
                "conversion_percent": min(99, yield_percent + 15),
            },
        },
    )
    assert res.status_code == 201, res.text


def _seed_completed(client: TestClient, headers: dict[str, str], project_id: int) -> None:
    rows = [
        (40, "MeCN", "Cat-A", 42),
        (60, "MeCN", "Cat-A", 58),
        (80, "THF", "Cat-A", 64),
        (60, "THF", "Cat-B", 71),
        (80, "MeCN", "Cat-B", 67),
    ]
    for index, (temperature, solvent, catalyst, yield_percent) in enumerate(rows, start=1):
        _completed(
            client,
            headers,
            project_id,
            index,
            temperature=temperature,
            solvent=solvent,
            catalyst=catalyst,
            yield_percent=yield_percent,
        )


def _manual_recommendation(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    *,
    label: str = "high_expected_improvement",
    estimated_cost: float | None = None,
    temperature: int = 60,
) -> dict:
    predicted = {"predicted_score": 70, "expected_improvement": 2.5}
    if estimated_cost is not None:
        predicted["estimated_cost"] = estimated_cost
    res = client.post(
        f"/reaction-projects/{project_id}/recommendations",
        headers=headers,
        json={
            "rank": 1,
            "conditions_json": {
                "temperature_c": temperature,
                "solvent": "MeCN",
                "catalyst": "Cat-A",
            },
            "predicted_outcome_json": predicted,
            "uncertainty_json": {"uncertainty": 0.25},
            "rationale": "Suggested for review as a plausible reaction condition.",
            "label": label,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_advisor_run_uses_rule_based_mode_without_llm_provider(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-run@example.com")
        project = _project(client, headers)
        _design_space(client, headers, project["id"])
        _seed_completed(client, headers, project["id"])
        bo = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "tpe_like", "batch_size": 2},
        )
        assert bo.status_code == 201, bo.text

        res = client.post(
            f"/reaction-projects/{project['id']}/advisor/run",
            headers=headers,
            json={"bo_run_id": bo.json()["bo_run_id"], "advisor_mode": "llm_guided_placeholder"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["advisor_mode"] == "rule_based_mechanistic"
        assert body["human_review_required"] is True
        assert body["advisor_run_id"] == body["id"]
        assert body["recommendation_count"] == 2
        assert body["critiques"]
        assert "External LLM guidance is not configured. Rule-based mechanistic advisor was used." in body["notes"]


def test_safety_blocked_recommendation_is_not_accepted(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-safety@example.com")
        project = _project(client, headers)
        rec = _manual_recommendation(
            client,
            headers,
            project["id"],
            label="safety_blocked",
            temperature=120,
        )

        critique = client.post(
            f"/reaction-recommendations/{rec['id']}/advisor/critique",
            headers=headers,
            json={},
        )
        assert critique.status_code == 201, critique.text
        body = critique.json()
        assert body["recommendation"] in {"reject_or_deprioritize", "insufficient_information"}
        assert body["human_review_required"] is True
        assert body["recommendation"] != "accept_for_review"


def test_high_cost_recommendation_produces_cost_warning(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-cost@example.com")
        project = _project(client, headers)
        _seed_completed(client, headers, project["id"])
        cost = client.post(
            f"/reaction-projects/{project['id']}/cost-profile",
            headers=headers,
            json={"max_cost_per_experiment": 100, "cost_penalty_weight": 1},
        )
        assert cost.status_code == 201, cost.text
        rec = _manual_recommendation(
            client,
            headers,
            project["id"],
            estimated_cost=250,
        )

        critique = client.post(
            f"/reaction-recommendations/{rec['id']}/advisor/critique",
            headers=headers,
            json={},
        )
        assert critique.status_code == 201, critique.text
        body = critique.json()
        assert "potential concern" in body["cost_assessment"]
        assert any(flag["type"] == "high_cost" for flag in body["risk_flags"])


def test_low_data_project_labels_insufficient_information(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-low-data@example.com")
        project = _project(client, headers)
        _manual_recommendation(client, headers, project["id"])

        res = client.post(
            f"/reaction-projects/{project['id']}/advisor/run",
            headers=headers,
            json={},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["human_review_required"] is True
        assert body["critiques"][0]["recommendation"] == "insufficient_information"
        assert "Insufficient information" in " ".join(body["warnings"])


def test_mechanistic_hypothesis_can_be_created_and_updated(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-hypothesis@example.com")
        project = _project(client, headers)
        created = client.post(
            f"/reaction-projects/{project['id']}/mechanistic-hypotheses",
            headers=headers,
            json={
                "title": "Base loading may affect conversion",
                "hypothesis": "Higher base loading is a plausible driver for improved conversion.",
                "confidence_label": "speculative",
            },
        )
        assert created.status_code == 201, created.text
        updated = client.patch(
            f"/reaction-mechanistic-hypotheses/{created.json()['id']}",
            headers=headers,
            json={"status": "revised", "confidence_label": "medium"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "revised"
        assert updated.json()["confidence_label"] == "medium"


def test_literature_prior_can_be_created_and_listed(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-literature@example.com")
        project = _project(client, headers)
        created = client.post(
            f"/reaction-projects/{project['id']}/literature-priors",
            headers=headers,
            json={
                "source_type": "user_note",
                "title": "Internal amidation note",
                "summary": "Polar aprotic solvents were suggested as chemically reasonable starting points.",
                "relevance_tags_json": ["solvent", "amidation"],
            },
        )
        assert created.status_code == 201, created.text
        listed = client.get(
            f"/reaction-projects/{project['id']}/literature-priors",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["title"] == "Internal amidation note"


def test_bo_vs_advisor_comparison_and_review_endpoint(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "advisor-compare@example.com")
        project = _project(client, headers)
        _design_space(client, headers, project["id"])
        _seed_completed(client, headers, project["id"])
        bo = client.post(
            f"/reaction-projects/{project['id']}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "tpe_like", "batch_size": 2},
        )
        assert bo.status_code == 201, bo.text
        advisor = client.post(
            f"/reaction-projects/{project['id']}/advisor/run",
            headers=headers,
            json={"bo_run_id": bo.json()["bo_run_id"]},
        )
        assert advisor.status_code == 201, advisor.text

        comparison = client.post(
            f"/reaction-projects/{project['id']}/advisor/compare-bo-llm",
            headers=headers,
            json={
                "bo_run_id": bo.json()["bo_run_id"],
                "advisor_run_id": advisor.json()["advisor_run_id"],
            },
        )
        assert comparison.status_code == 201, comparison.text
        debate = comparison.json()
        assert debate["human_review_required"] is True
        assert debate["agreements"] or debate["disagreements"]

        review = client.post(
            f"/reaction-advisor-runs/{advisor.json()['advisor_run_id']}/review",
            headers=headers,
            json={
                "reviewer_name": "Reviewer",
                "decision": "reviewed",
                "rationale": "Advisor output reviewed before any scheduling discussion.",
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["metadata"]["review"]["decision"] == "reviewed"


def test_phase51_openapi_includes_advisor_endpoints(tmp_path):
    client = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/reaction-projects/{reaction_project_id}/advisor/run",
        "/reaction-projects/{reaction_project_id}/advisor/runs",
        "/reaction-advisor-runs/{advisor_run_id}",
        "/reaction-recommendations/{recommendation_id}/advisor/critique",
        "/reaction-projects/{reaction_project_id}/mechanistic-hypotheses",
        "/reaction-mechanistic-hypotheses/{hypothesis_id}",
        "/reaction-projects/{reaction_project_id}/literature-priors",
        "/reaction-projects/{reaction_project_id}/advisor/compare-bo-llm",
        "/reaction-projects/{reaction_project_id}/advisor/comparisons",
        "/reaction-advisor-runs/{advisor_run_id}/review",
    ]:
        assert path in paths
    assert "post" in paths["/reaction-projects/{reaction_project_id}/advisor/run"]
    assert "patch" in paths["/reaction-mechanistic-hypotheses/{hypothesis_id}"]
