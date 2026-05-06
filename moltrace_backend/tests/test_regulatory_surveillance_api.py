from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'regulatory_surveillance.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _jurisdiction(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/regulatory/jurisdictions",
        headers=headers,
        json={
            "name": "Phase 56 US FDA",
            "region": "North America",
            "country_code": "US",
            "authority_name": "Food and Drug Administration",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _dossier(client: TestClient, headers: dict[str, str], jurisdiction_id: int) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Phase 56 change impact dossier",
            "product_name": "Phase 56 product",
            "compound_name": "Phase 56 compound",
            "jurisdiction_id": jurisdiction_id,
            "intended_use": "Research decision support",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _rule_set(client: TestClient, headers: dict[str, str], jurisdiction_id: int, source_id: int) -> dict:
    res = client.post(
        "/regulatory/rule-sets",
        headers=headers,
        json={
            "name": "Phase 56 impurity source-linked rules",
            "jurisdiction_id": jurisdiction_id,
            "version": "draft-2026-a",
            "source_type": "fda",
            "source_ids_json": [source_id],
            "status": "active",
            "impurity_threshold_rules_json": [
                {
                    "rule_type": "reporting",
                    "threshold_percent": 0.05,
                    "applies_to": "drug_substance",
                    "citation_ids_json": [],
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_regulatory_source_surveillance_change_impact_workflow(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        jurisdiction = _jurisdiction(client, headers)

        watcher = client.post(
            "/regulatory/surveillance/sources",
            headers=headers,
            json={
                "title": "Phase 56 impurity threshold guidance",
                "source_type": "fda_guidance",
                "jurisdiction_id": jurisdiction["id"],
                "source_url": "https://example.invalid/fda-guidance.pdf",
                "check_frequency": "manual",
            },
        )
        assert watcher.status_code == 201, watcher.text
        watcher_body = watcher.json()
        assert watcher_body["status"] == "active"
        assert watcher_body["human_review_required"] is True

        first_run = client.post(
            "/regulatory/surveillance/runs",
            headers=headers,
            json={
                "watcher_id": watcher_body["id"],
                "version_label": "2026-draft-a",
                "uploaded_text": (
                    "Impurity reporting threshold is 0.05 percent. "
                    "Identification threshold is 0.10 percent. "
                    "Nitrosamine and qNMR validation topics require review."
                ),
            },
        )
        assert first_run.status_code == 201, first_run.text
        first_run_body = first_run.json()
        assert first_run_body["created_version_id"]
        assert first_run_body["change_event_id"]

        source_id = first_run_body["source_id"]
        versions = client.get(f"/regulatory/sources/{source_id}/versions", headers=headers)
        assert versions.status_code == 200, versions.text
        assert len(versions.json()) == 1
        first_version_id = versions.json()[0]["id"]
        assert versions.json()[0]["sha256"]
        assert versions.json()[0]["content_hash"]

        dossier = _dossier(client, headers, jurisdiction["id"])
        rule_set = _rule_set(client, headers, jurisdiction["id"], source_id)

        changed_run = client.post(
            "/regulatory/surveillance/runs",
            headers=headers,
            json={
                "watcher_id": watcher_body["id"],
                "version_label": "2026-draft-b",
                "uploaded_text": (
                    "Impurity reporting threshold is 0.03 percent. "
                    "Identification threshold is 0.08 percent. "
                    "Residual solvent PDE, nitrosamine watch, qNMR validation, "
                    "AI governance, and jurisdictional map topics require review."
                ),
            },
        )
        assert changed_run.status_code == 201, changed_run.text
        changed_body = changed_run.json()
        assert changed_body["status"] == "completed"
        assert changed_body["change_event_id"]
        second_version_id = changed_body["created_version_id"]

        compare = client.post(
            f"/regulatory/sources/{source_id}/versions/compare",
            headers=headers,
            json={"old_version_id": first_version_id, "new_version_id": second_version_id},
        )
        assert compare.status_code == 200, compare.text
        compare_body = compare.json()
        assert compare_body["changed"] is True
        assert compare_body["change_type"] == "threshold_changed"
        assert "impurity_threshold" in compare_body["affected_topics_json"]
        assert compare_body["human_review_required"] is True

        changes = client.get("/regulatory/changes", headers=headers, params={"source_id": source_id})
        assert changes.status_code == 200, changes.text
        changed_events = [item for item in changes.json() if item["id"] == changed_body["change_event_id"]]
        assert changed_events
        change_event = changed_events[0]
        assert change_event["change_type"] == "threshold_changed"
        assert change_event["affected_rule_set_ids_json"] == [rule_set["id"]]
        assert dossier["id"] in change_event["affected_dossier_ids_json"]
        assert change_event["human_review_required"] is True

        fetched_change = client.get(f"/regulatory/changes/{change_event['id']}", headers=headers)
        assert fetched_change.status_code == 200, fetched_change.text
        assert fetched_change.json()["diffs"]

        reviewed = client.post(
            f"/regulatory/changes/{change_event['id']}/review",
            headers=headers,
            json={
                "review_status": "in_review",
                "reviewer_name": "Regulatory reviewer",
                "reviewer_comment": "Initial triage opened for source-supported review.",
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["review_status"] == "in_review"

        impact = client.post(
            f"/regulatory/changes/{change_event['id']}/impact-assessment",
            headers=headers,
            json={},
        )
        assert impact.status_code == 201, impact.text
        impact_body = impact.json()
        assert impact_body["status"] == "draft"
        assert impact_body["impacted_dossiers_json"] == [dossier["id"]]
        assert impact_body["impacted_rule_sets_json"] == [rule_set["id"]]
        assert impact_body["impacted_action_items_json"]
        assert impact_body["human_review_required"] is True

        proposal = client.post(
            f"/regulatory/changes/{change_event['id']}/rule-update-proposal",
            headers=headers,
            json={
                "rule_set_id": rule_set["id"],
                "proposal_type": "update_threshold",
                "title": "Review impurity reporting threshold",
                "rationale": "Source change detected in uploaded version; requires qualified review.",
                "proposed_changes_json": {"impurity_threshold_rules_json": [{"rule_type": "reporting", "threshold_percent": 0.03}]},
            },
        )
        assert proposal.status_code == 201, proposal.text
        proposal_body = proposal.json()
        assert proposal_body["status"] == "proposed"
        assert proposal_body["metadata_json"]["warnings"]

        missing_rationale = client.post(
            f"/regulatory/rule-update-proposals/{proposal_body['id']}/approve",
            headers=headers,
            json={"reviewer_name": "Qualified reviewer"},
        )
        assert missing_rationale.status_code == 422, missing_rationale.text

        approved = client.post(
            f"/regulatory/rule-update-proposals/{proposal_body['id']}/approve",
            headers=headers,
            json={
                "reviewer_name": "Qualified reviewer",
                "reviewer_comment": "Approved as a proposal only; separate implementation review required.",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["reviewer_name"] == "Qualified reviewer"

        dossier_impact = client.get(f"/regulatory/dossiers/{dossier['id']}/change-impact", headers=headers)
        assert dossier_impact.status_code == 200, dossier_impact.text
        dossier_impact_body = dossier_impact.json()
        assert dossier_impact_body["change_events"]
        assert dossier_impact_body["impact_assessments"]
        assert dossier_impact_body["rule_update_proposals"]

        notifications = client.get("/regulatory/notifications", headers=headers, params={"dossier_id": dossier["id"]})
        assert notifications.status_code == 200, notifications.text
        assert notifications.json()
        notification_id = notifications.json()[0]["id"]
        read = client.patch(
            f"/regulatory/notifications/{notification_id}",
            headers=headers,
            json={"status": "read"},
        )
        assert read.status_code == 200, read.text
        assert read.json()["status"] == "read"
        dismissed = client.patch(
            f"/regulatory/notifications/{notification_id}",
            headers=headers,
            json={"status": "dismissed"},
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["status"] == "dismissed"


def test_regulatory_surveillance_endpoints_appear_in_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/regulatory/surveillance/sources",
        "/regulatory/surveillance/sources/{watcher_id}",
        "/regulatory/surveillance/runs",
        "/regulatory/surveillance/runs/{run_id}",
        "/regulatory/sources/{source_id}/versions",
        "/regulatory/sources/{source_id}/versions/{version_id}",
        "/regulatory/sources/{source_id}/versions/compare",
        "/regulatory/changes",
        "/regulatory/changes/{change_id}",
        "/regulatory/changes/{change_id}/review",
        "/regulatory/changes/{change_id}/impact-assessment",
        "/regulatory/changes/{change_id}/rule-update-proposal",
        "/regulatory/rule-update-proposals",
        "/regulatory/rule-update-proposals/{proposal_id}",
        "/regulatory/rule-update-proposals/{proposal_id}/approve",
        "/regulatory/rule-update-proposals/{proposal_id}/reject",
        "/regulatory/dossiers/{dossier_id}/change-impact",
        "/regulatory/notifications",
        "/regulatory/notifications/{notification_id}",
    ]
    for path in required_paths:
        assert path in paths

    schemas = res.json()["components"]["schemas"]
    for schema in [
        "RegulatorySourceWatcher",
        "RegulatorySourceVersion",
        "RegulatoryChangeEvent",
        "RegulatoryImpactAssessment",
        "RegulatoryRuleUpdateProposal",
        "RegulatoryImpactNotification",
    ]:
        assert schema in schemas
