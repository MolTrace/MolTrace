from fastapi import HTTPException
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'security-hardening.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )

    @app.get("/_test/leaky-client-error")
    def leaky_client_error() -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    'Traceback (most recent call last):\n'
                    '  File "/Users/ci/private/service.py", line 1'
                ),
                "database_url": "postgresql://user:password@example.test/moltrace",
                "signed_url": "https://storage.example.test/object?X-Amz-Signature=abc123",
                "nested": {"api_key": "super-secret-value"},
            },
        )

    @app.get("/_test/leaky-server-error")
    def leaky_server_error() -> None:
        raise RuntimeError(
            "password=super-secret-value\n"
            'Traceback (most recent call last):\n  File "/Users/ci/private/service.py"'
        )

    return TestClient(app, raise_server_exceptions=False)


def test_error_responses_redact_sensitive_details(tmp_path):
    client = _client(tmp_path)

    with client:
        client_error = client.get(
            "/_test/leaky-client-error",
            headers={"X-Correlation-ID": "security-hardening-test-1"},
        )
        server_error = client.get(
            "/_test/leaky-server-error",
            headers={"X-Correlation-ID": "security-hardening-test-2"},
        )

    assert client_error.status_code == 400, client_error.text
    assert client_error.headers["x-correlation-id"] == "security-hardening-test-1"
    client_text = client_error.text
    assert "super-secret-value" not in client_text
    assert "postgresql://" not in client_text
    assert "X-Amz-Signature" not in client_text
    assert "/Users/" not in client_text
    assert "Traceback" not in client_text
    assert "Internal server error" in client_text

    assert server_error.status_code == 503, server_error.text
    assert server_error.headers["x-correlation-id"] == "security-hardening-test-2"
    payload = server_error.json()
    assert payload["detail"] == "Service temporarily unavailable"
    assert payload["data_mode"] == "unavailable"
    assert payload["warnings"] == ["Service temporarily unavailable"]
    assert payload["correlation_id"] == "security-hardening-test-2"
    assert "generated_at" in payload
    assert "super-secret-value" not in server_error.text
    assert "Traceback" not in server_error.text
