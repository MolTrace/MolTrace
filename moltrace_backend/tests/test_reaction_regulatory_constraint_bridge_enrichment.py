"""Integration test for Repho R4 bridge enrichment: the dossier->bridge->constraint->compliance
auto-flow now carries a numeric ICH limit end to end.

Uses the system api key (api_headers) so the cross-module owner-scoping is unrestricted for setup.
"""

from fastapi.testclient import TestClient


def _dossier(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "R4 enrichment dossier",
            "product_name": "R4 fixture product",
            "compound_name": "R4 fixture compound",
            "intended_use": "Internal compliance planning fixture.",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _reaction_project(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "R4 enrichment project", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _impurity_action(client, headers, dossier_id, *, threshold=0.15, observed=0.42):
    res = client.post(
        "/regulatory/action-items",
        headers=headers,
        json={
            "dossier_id": dossier_id,
            "action_type": "impurity_identification",
            "severity": "high",
            "status": "open",
            "title": "Impurity above identification threshold",
            "description": "Observed impurity exceeded the ICH identification threshold.",
            "metadata_json": {
                "threshold_percent": threshold,
                "observed_level_percent": observed,
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_bridge_enriches_constraint_with_numeric_limit_and_compliance_enforces(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        project = _reaction_project(client, headers)
        pid = project["id"]
        action = _impurity_action(client, headers, dossier["id"], threshold=0.15, observed=0.42)

        bridge = client.post(
            "/bridges/regulatory-to-reaction",
            headers=headers,
            json={
                "dossier_id": dossier["id"],
                "regulatory_action_item_id": action["id"],
                "reaction_project_id": pid,
            },
        )
        assert bridge.status_code == 201, bridge.text
        assert bridge.json()["created_constraint_ids_json"]

        # --- enrichment: the auto-created constraint now carries the ICH numeric limit ---
        constraints = client.get(
            f"/reaction-projects/{pid}/regulatory-constraints", headers=headers
        ).json()
        impurity = next(c for c in constraints if c["constraint_type"] == "impurity_limit")
        cj = impurity["constraint_json"]
        assert cj["limit_value"] == 0.15
        assert cj["objective_field"] == "impurity_percent"
        assert cj["comparator"] == "max"
        assert "identification" in cj["limit_basis"]
        assert impurity["status"] == "draft"  # review-gated until activated

        # --- activate (the existing review/edit path) then enforce end to end ---
        activated = client.patch(
            f"/reaction-regulatory-constraints/{impurity['id']}",
            headers=headers,
            json={"status": "active"},
        )
        assert activated.status_code == 200, activated.text

        client.post(
            f"/reaction-projects/{pid}/experiments",
            headers=headers,
            json={
                "experiment_code": "R4-bad",
                "status": "completed",
                "conditions_json": {"temperature_c": 60},
                "outcome_json": {"yield_percent": 70.0, "impurity_percent": 0.42},
            },
        )

        report = client.get(
            f"/reaction-projects/{pid}/regulatory-compliance", headers=headers
        ).json()
        assert report["enforced_constraint_count"] == 1
        assert report["non_compliant_experiment_count"] == 1
        item = next(i for i in report["items"] if i["experiment_code"] == "R4-bad")
        assert item["hard_block"] is True
        viol = item["violations"][0]
        assert viol["limit_value"] == 0.15
        assert viol["predicted_value"] == 0.42
        assert action["id"] in viol["source_action_item_ids"]
