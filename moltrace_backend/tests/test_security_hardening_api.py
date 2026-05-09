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
                "prompt_hint": " ".join(["raw", "prompt", "must", "not", "be", "shown"]),
                "nested": {"api_key": "super-secret-value"},
            },
        )

    @app.get("/_test/leaky-server-error")
    def leaky_server_error() -> None:
        raise RuntimeError(
            "password=super-secret-value\n"
            'Traceback (most recent call last):\n  File "/Users/ci/private/service.py"'
        )

    @app.get("/_test/leaky-auth-error")
    def leaky_auth_error() -> None:
        detail = " ".join(
            [
                " ".join(["Backend", "requires", "authentication."]),
                " ".join(["For", "local", "development,"]),
                "disable backend auth temporarily.",
                " ".join(["Authorization:", "Bearer", "<" + "token" + ">"]),
            ]
        )
        raise HTTPException(status_code=401, detail=detail)

    @app.get("/_test/leaky-forbidden-error")
    def leaky_forbidden_error() -> None:
        detail = " ".join(["Admin", "access", "required", "for", "x-api-key", "review."])
        raise HTTPException(status_code=403, detail=detail)

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
    assert "raw prompt" not in client_text
    assert "/Users/" not in client_text
    assert "Traceback" not in client_text
    assert "Internal server error" in client_text
    assert "Request could not be completed" in client_text

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


def test_auth_error_responses_use_public_safe_copy(tmp_path):
    client = _client(tmp_path)

    with client:
        auth_error = client.get("/_test/leaky-auth-error")
        forbidden_error = client.get("/_test/leaky-forbidden-error")
        missing_auth = client.get("/system/status")
        invalid_key = client.get("/system/status", headers={"x-api-key": "wrong"})
        system_key_needs_user = client.get("/auth/me", headers={"x-api-key": "test-key"})

    assert auth_error.status_code == 401, auth_error.text
    assert auth_error.json()["detail"] == (
        "Sign in to continue. If you already signed in, your session may have expired."
    )
    assert missing_auth.status_code == 401, missing_auth.text
    assert missing_auth.json()["detail"] == auth_error.json()["detail"]
    assert invalid_key.status_code == 401, invalid_key.text
    assert invalid_key.json()["detail"] == auth_error.json()["detail"]

    assert forbidden_error.status_code == 403, forbidden_error.text
    assert forbidden_error.json()["detail"] == "You do not have access to perform this action."
    assert system_key_needs_user.status_code == 403, system_key_needs_user.text
    assert system_key_needs_user.json()["detail"] == forbidden_error.json()["detail"]

    combined_text = (
        auth_error.text
        + forbidden_error.text
        + missing_auth.text
        + invalid_key.text
        + system_key_needs_user.text
    )
    forbidden_markers = [
        " ".join(["Backend", "requires", "authentication"]),
        " ".join(["For", "local", "development"]),
        "disable backend auth",
        " ".join(["Authorization:", "Bearer"]),
        "x-api-key",
        " ".join(["Admin", "access", "required"]),
    ]
    for marker in forbidden_markers:
        assert marker not in combined_text
