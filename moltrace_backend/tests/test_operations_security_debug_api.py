from fastapi.testclient import TestClient


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


def test_operations_security_and_debug_workflow(client, api_headers, monkeypatch):
    monkeypatch.setenv("API_KEY", "super-secret-test-value")
    admin_headers = api_headers

    with client:
        viewer_headers = _sign_up(client, "viewer@example.com")

        health = client.get("/system/health")
        assert health.status_code == 200, health.text
        assert health.json()["status"] in {"healthy", "degraded", "unhealthy"}

        status = client.get("/system/status", headers=admin_headers)
        assert status.status_code == 200, status.text
        assert status.json()["database_status"] in {"ok", "warning", "error", "unknown"}
        assert status.json()["openapi_available"] is True

        deps = client.get("/system/dependencies", headers=admin_headers)
        assert deps.status_code == 200, deps.text
        assert {check["name"] for check in deps.json()} >= {"database", "storage", "openapi"}

        env = client.get("/system/environment-check", headers=admin_headers)
        assert env.status_code == 200, env.text
        env_text = env.text
        assert "super-secret-test-value" not in env_text
        assert "test-key" not in env_text

        viewer_env = client.get("/system/environment-check", headers=viewer_headers)
        assert viewer_env.status_code == 403, viewer_env.text

        metrics = client.get("/system/metrics", headers=admin_headers)
        assert metrics.status_code == 200, metrics.text
        assert any(metric["name"] == "security_events_total" for metric in metrics.json())

        security_event = client.post(
            "/security/events",
            headers=admin_headers,
            json={
                "event_type": "permission_denied",
                "severity": "warning",
                "actor_email": "viewer@example.com",
                "resource_type": "admin_debug",
                "resource_id": "debug",
                "message": "Viewer attempted admin debug access.",
                "metadata_json": {"token": "never-show-this"},
            },
        )
        assert security_event.status_code == 201, security_event.text
        assert security_event.json()["event_type"] == "permission_denied"
        assert "never-show-this" not in security_event.text

        listed_events = client.get("/security/events", headers=admin_headers)
        assert listed_events.status_code == 200, listed_events.text
        assert any(event["event_type"] == "permission_denied" for event in listed_events.json())

        summary = client.get("/security/summary", headers=admin_headers)
        assert summary.status_code == 200, summary.text
        assert summary.json()["counts_by_type"]["permission_denied"] == 1

        audit = client.get(
            "/admin/audit/search",
            headers=admin_headers,
            params={"event_type": "security.event.create"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()

        debug_bundle = client.post(
            "/admin/debug-bundles",
            headers=admin_headers,
            json={
                "title": "Safe system diagnostics",
                "scope": "system",
                "metadata_json": {
                    "requested_by": "test",
                    "password": "do-not-include",
                    "access_token": "do-not-include-token",
                },
            },
        )
        assert debug_bundle.status_code == 201, debug_bundle.text
        bundle = debug_bundle.json()
        assert bundle["status"] == "created"
        assert bundle["metadata_json"]["password"] == "[redacted]"
        assert bundle["metadata_json"]["access_token"] == "[redacted]"

        downloaded = client.get(
            f"/admin/debug-bundles/{bundle['id']}/download",
            headers=admin_headers,
        )
        assert downloaded.status_code == 200, downloaded.text
        assert "do-not-include" not in downloaded.text
        assert "super-secret-test-value" not in downloaded.text
        assert "raw uploaded files" in downloaded.text

        viewer_admin = client.get("/admin/audit/search", headers=viewer_headers)
        assert viewer_admin.status_code == 403, viewer_admin.text


def test_operations_endpoints_appear_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/system/health",
        "/system/status",
        "/system/version",
        "/system/dependencies",
        "/system/environment-check",
        "/system/metrics",
        "/system/jobs/summary",
        "/system/storage/summary",
        "/security/events",
        "/security/summary",
        "/admin/audit/search",
        "/admin/debug-bundles",
        "/admin/debug-bundles/{bundle_id}",
        "/admin/debug-bundles/{bundle_id}/download",
    ]:
        assert path in paths
    assert "post" in paths["/security/events"]
    assert "post" in paths["/admin/debug-bundles"]
