import hashlib

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


DEFAULT_PROGRAM_ORDER = ["spectracheck", "regulatory_hub", "reaction_optimization"]
REQUIRED_MOBILE_PATHS = [
    "/mobile/config",
    "/mobile/device-sessions",
    "/mobile/device-sessions/{device_session_id}",
    "/mobile/dashboard",
    "/mobile/command-center",
    "/mobile/spectracheck/sessions/{session_id}/summary",
    "/mobile/regulatory/dossiers/{dossier_id}/summary",
    "/mobile/reactions/{reaction_project_id}/summary",
    "/mobile/action-queue",
    "/mobile/action-drafts",
    "/mobile/action-drafts/{draft_id}",
    "/mobile/sync",
    "/mobile/push-subscriptions",
    "/mobile/notifications",
    "/mobile/notifications/{notification_id}",
    "/mobile/reports/{report_id}/preview",
    "/mobile/jobs/summary",
    "/mobile/offline-safe-summary",
]


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'phase61_mobile_pwa.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _analysis_payload() -> dict:
    return {
        "sample_id": "phase61-mobile-sample",
        "smiles": "CCO",
        "nmr_text": "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)",
        "solvent": "CDCl3",
    }


def _analysis_id(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post("/analyze", headers=headers, json=_analysis_payload())
    assert response.status_code == 200, response.text
    history = client.get("/history", headers=headers)
    assert history.status_code == 200, history.text
    return history.json()[0]["id"]


def _draft(
    client: TestClient,
    headers: dict[str, str],
    *,
    action_type: str,
    target_type: str,
    target_id: str,
    payload: dict,
    status: str = "queued_for_sync",
) -> dict:
    response = client.post(
        "/mobile/action-drafts",
        headers=headers,
        json={
            "action_type": action_type,
            "target_type": target_type,
            "target_id": target_id,
            "draft_payload_json": payload,
            "status": status,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_mobile_config_returns_integrated_program_order(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.get("/mobile/config", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert [item["program_key"] for item in body["navigation_order"]] == DEFAULT_PROGRAM_ORDER
        assert [item["display_order"] for item in body["navigation_order"]] == [1, 2, 3]
        assert body["draft_sync_required"] is True


def test_pwa_api_responses_disable_http_cache_and_expose_backend_version(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.get("/mobile/config", headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"
        assert response.headers["x-moltrace-backend-version"] == "0.21.0"


def test_mobile_dashboard_returns_compact_summaries(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.get("/mobile/dashboard", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["module_order"] == DEFAULT_PROGRAM_ORDER
        assert body["compact_payload"] is True
        assert set(body["summary"]) >= {
            "spectracheck_summary_json",
            "regulatory_summary_json",
            "reaction_summary_json",
            "action_summary_json",
        }
        serialized = str(body).lower()
        assert "raw_fid" not in serialized
        assert "raw_spectra" not in serialized
        assert "full_source_text" not in serialized
        assert "latest_report_json" not in serialized


def test_mobile_action_draft_rejects_raw_spectrum_like_payload(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/mobile/action-drafts",
            headers=headers,
            json={
                "action_type": "evidence_comment",
                "target_type": "analysis",
                "target_id": "1",
                "draft_payload_json": {
                    "raw_spectrum": [{"ppm": 1.0, "intensity": 12.5}],
                    "comment": "unsafe raw payload",
                },
            },
        )
        assert response.status_code == 400
        assert "forbidden_mobile_payload_field" in response.text


def test_mobile_action_draft_rejects_token_password_like_payload(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/mobile/action-drafts",
            headers=headers,
            json={
                "action_type": "review_decision",
                "target_type": "analysis",
                "target_id": "1",
                "draft_payload_json": {
                    "decision": "approve",
                    "access_token": "do-not-store-this",
                },
            },
        )
        assert response.status_code == 400
        assert "forbidden_mobile_payload_field" in response.text


def test_mobile_sync_applies_valid_review_draft_and_audits(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        analysis_id = _analysis_id(client, headers)
        draft = _draft(
            client,
            headers,
            action_type="review_decision",
            target_type="analysis",
            target_id=str(analysis_id),
            payload={"decision": "approve", "comment": "Mobile field review accepted."},
        )

        sync = client.post(
            "/mobile/sync",
            headers=headers,
            json={"draft_ids": [draft["id"]]},
        )
        assert sync.status_code == 200, sync.text
        body = sync.json()
        assert body["result"]["synced_count"] == 1
        assert body["result"]["rejected_count"] == 0
        assert body["items"][0]["status"] == "synced"

        history = client.get("/history", headers=headers)
        assert history.status_code == 200, history.text
        updated = next(item for item in history.json() if item["id"] == analysis_id)
        assert updated["review_status"] == "approved"

        audit = client.get(
            "/audit",
            headers=headers,
            params={"entity_type": "analysis", "entity_id": analysis_id},
        )
        assert audit.status_code == 200, audit.text
        assert any(event["event_type"] == "mobile.review_decision.sync" for event in audit.json())


def test_mobile_sync_rejects_invalid_draft_with_warning(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        draft = _draft(
            client,
            headers,
            action_type="review_decision",
            target_type="analysis",
            target_id="999999",
            payload={"decision": "approve", "comment": "Missing target should fail."},
        )

        sync = client.post("/mobile/sync", headers=headers, json={"draft_ids": [draft["id"]]})
        assert sync.status_code == 200, sync.text
        body = sync.json()
        assert body["result"]["synced_count"] == 0
        assert body["result"]["rejected_count"] == 1
        assert body["items"][0]["status"] == "rejected"
        assert any("target_not_found" in message for message in body["items"][0]["validation_messages"])

        drafts = client.get("/mobile/action-drafts", headers=headers, params={"status": "rejected"})
        assert drafts.status_code == 200, drafts.text
        assert drafts.json()[0]["validation_warnings_json"]


def test_mobile_push_subscription_stores_endpoint_hash_without_raw_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    endpoint = "https://push.example.test/subscriptions/raw-endpoint-123"
    with client:
        response = client.post(
            "/mobile/push-subscriptions",
            headers=headers,
            json={
                "endpoint": endpoint,
                "subscription_json": {
                    "endpoint": endpoint,
                    "keys": {"p256dh": "public-key-material", "auth": "auth-secret"},
                },
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["endpoint_hash"] == hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        assert endpoint not in str(body)
        assert "auth-secret" not in str(body)
        assert "public-key-material" not in str(body)


def test_mobile_notifications_can_be_listed_read_and_dismissed(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        analysis_id = _analysis_id(client, headers)
        created = client.post(
            "/mobile/notifications",
            headers=headers,
            json={
                "notification_type": "review_required",
                "title": "Review required",
                "message": "A mobile field review is waiting.",
                "target_type": "analysis",
                "target_id": str(analysis_id),
                "severity": "warning",
            },
        )
        assert created.status_code == 201, created.text

        listed = client.get("/mobile/notifications", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["status"] == "unread"
        assert listed.json()[0]["target_type"] == "analysis"

        read = client.patch(
            f"/mobile/notifications/{created.json()['id']}",
            headers=headers,
            json={"status": "read"},
        )
        assert read.status_code == 200, read.text
        assert read.json()["status"] == "read"

        dismissed = client.patch(
            f"/mobile/notifications/{created.json()['id']}",
            headers=headers,
            json={"status": "dismissed"},
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["status"] == "dismissed"


def test_mobile_report_preview_avoids_raw_appendices(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        analysis_id = _analysis_id(client, headers)
        report = client.post(f"/reports/from-analysis/{analysis_id}", headers=headers)
        assert report.status_code == 201, report.text

        preview = client.get(f"/mobile/reports/{report.json()['id']}/preview", headers=headers)
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["raw_appendices_included"] is False
        assert body["compact_payload"] is True
        assert "raw_appendices" in body["omitted_sections"]
        preview_text = str(body["preview_sections"])
        assert _analysis_payload()["nmr_text"] not in preview_text
        assert "parsed_peaks" not in preview_text


def test_openapi_includes_mobile_endpoints(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.get("/openapi.json")
        assert response.status_code == 200, response.text
        paths = response.json()["paths"]
        for path in REQUIRED_MOBILE_PATHS:
            assert path in paths
