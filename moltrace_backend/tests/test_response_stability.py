from fastapi.testclient import TestClient

from nmrcheck import analytics_store
from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'response-stability.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def test_unavailable_service_response_is_stable_json(tmp_path, monkeypatch):
    client, headers = _client(tmp_path)
    secret_url = "postgresql://moltrace:secret-password@db.example/moltrace"

    def failing_summary(*args, **kwargs):
        raise RuntimeError(f"could not connect to {secret_url}\nTraceback: unsafe")

    monkeypatch.setattr(analytics_store, "analytics_summary", failing_summary)
    headers = {**headers, "X-Correlation-ID": "test-correlation-1"}

    with client:
        res = client.get("/analytics/summary", headers=headers)

    assert res.status_code == 503, res.text
    assert res.headers["x-correlation-id"] == "test-correlation-1"
    assert res.headers["x-request-id"] == "test-correlation-1"
    assert res.headers["x-moltrace-data-mode"] == "unavailable"

    payload = res.json()
    assert payload["detail"] == "Service temporarily unavailable"
    assert payload["data_mode"] == "unavailable"
    assert payload["warnings"] == ["Service temporarily unavailable"]
    assert payload["correlation_id"] == "test-correlation-1"
    assert "generated_at" in payload
    assert secret_url not in res.text
    assert "Traceback" not in res.text


def test_system_health_includes_non_breaking_data_mode_metadata(tmp_path):
    client, _headers = _client(tmp_path)

    with client:
        res = client.get("/system/health")

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["status"] in {"healthy", "degraded", "unhealthy"}
    assert payload["data_mode"] in {
        "live",
        "partially_synced",
        "unavailable",
    }
    assert "generated_at" in payload
