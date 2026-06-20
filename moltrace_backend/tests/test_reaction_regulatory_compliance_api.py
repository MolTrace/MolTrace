"""API tests for Repho R4 enforcement (read side): regulatory-compliance over real outcomes.

A project's injected regulatory impurity limit is evaluated against the actual recorded outcomes
of its experiments; an experiment exceeding a high/critical limit is flagged non-compliant, with
provenance. Owner-scoped (non-owner -> non-leaking 404). Advisory when no numeric limit is active.
"""

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Compliance", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _impurity_constraint(client, headers, pid, *, limit=0.15, severity="high", status="active"):
    res = client.post(
        f"/reaction-projects/{pid}/regulatory-constraints",
        headers=headers,
        json={
            "constraint_type": "impurity_limit",
            "severity": severity,
            "status": status,
            "constraint_json": {
                "limit_value": limit,
                "limit_unit": "percent",
                "objective_field": "impurity_percent",
                "comparator": "max",
                "limit_basis": "ICH Q3B(R2) identification threshold",
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _experiment(client, headers, pid, code, impurity):
    res = client.post(
        f"/reaction-projects/{pid}/experiments",
        headers=headers,
        json={
            "experiment_code": code,
            "status": "completed",
            "conditions_json": {"temperature_c": 60, "solvent": "MeCN"},
            "outcome_json": {"yield_percent": 80.0, "impurity_percent": impurity},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_compliance_flags_outcomes_exceeding_an_active_limit(client):
    with client:
        headers = _sign_up(client, "compliance@example.com")
        pid = _project(client, headers)
        _impurity_constraint(client, headers, pid, limit=0.15, severity="high")
        _experiment(client, headers, pid, "E-ok", impurity=0.05)  # within limit
        _experiment(client, headers, pid, "E-bad", impurity=0.40)  # exceeds 0.15

        res = client.get(f"/reaction-projects/{pid}/regulatory-compliance", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["enforced_constraint_count"] == 1
        assert body["experiments_evaluated"] == 2
        assert body["non_compliant_experiment_count"] == 1

        by_code = {i["experiment_code"]: i for i in body["items"]}
        assert by_code["E-ok"]["feasible"] is True
        assert by_code["E-ok"]["violations"] == []
        bad = by_code["E-bad"]
        assert bad["hard_block"] is True
        assert bad["feasible"] is False
        assert len(bad["violations"]) == 1
        v = bad["violations"][0]
        assert v["predicted_value"] == 0.40
        assert v["limit_value"] == 0.15
        assert "Q3B" in v["basis"]


def test_low_severity_limit_penalises_but_is_not_non_compliant(client):
    with client:
        headers = _sign_up(client, "compliance-soft@example.com")
        pid = _project(client, headers)
        _impurity_constraint(client, headers, pid, limit=0.10, severity="warning")
        _experiment(client, headers, pid, "E-soft", impurity=0.30)

        body = client.get(
            f"/reaction-projects/{pid}/regulatory-compliance", headers=headers
        ).json()
        item = body["items"][0]
        assert item["hard_block"] is False  # warning tier -> not a hard block
        assert item["feasible"] is True
        assert item["penalty"] > 0.0
        assert len(item["violations"]) == 1
        assert body["non_compliant_experiment_count"] == 0


def test_draft_constraint_is_not_enforced_report_is_advisory(client):
    with client:
        headers = _sign_up(client, "compliance-draft@example.com")
        pid = _project(client, headers)
        _impurity_constraint(client, headers, pid, limit=0.15, status="draft")
        _experiment(client, headers, pid, "E-x", impurity=0.99)

        body = client.get(
            f"/reaction-projects/{pid}/regulatory-compliance", headers=headers
        ).json()
        assert body["enforced_constraint_count"] == 0  # draft is not enforceable
        assert body["non_compliant_experiment_count"] == 0
        assert any("advisory" in n for n in body["notes"])


def test_compliance_is_owner_scoped(client):
    with client:
        owner = _sign_up(client, "compliance-owner@example.com")
        intruder = _sign_up(client, "compliance-intruder@example.com")
        pid = _project(client, owner)
        _impurity_constraint(client, owner, pid)
        assert (
            client.get(
                f"/reaction-projects/{pid}/regulatory-compliance", headers=intruder
            ).status_code
            == 404
        )
