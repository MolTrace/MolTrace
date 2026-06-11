from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path, *, require_verified_email: bool = False) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'frontend_auth.sqlite3'}",
            require_verified_email=require_verified_email,
            api_key="test-key",
        )
    )
    return TestClient(app)


def test_frontend_sign_up_and_sign_in_issue_sessions(client) -> None:
    with client:
        sign_up = client.post(
            "/auth/sign-up",
            json={
                "name": "Ada Chemist",
                "email": "ada@example.com",
                "password": "StrongPassword123!",
                "password-confirm": "StrongPassword123!",
            },
        )
        assert sign_up.status_code == 201, sign_up.text
        sign_up_json = sign_up.json()
        assert sign_up_json["access_token"]
        assert sign_up_json["user"]["email"] == "ada@example.com"
        assert sign_up_json["requires_email_verification"] is False

        me = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {sign_up_json['access_token']}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["email"] == "ada@example.com"

        sign_in = client.post(
            "/auth/sign-in",
            json={
                "email": "ada@example.com",
                "password": "StrongPassword123!",
                "rememberMe": True,
            },
        )
        assert sign_in.status_code == 200, sign_in.text
        assert sign_in.json()["access_token"]
        assert sign_in.json()["detail"] == "Signed in."


def test_frontend_sign_up_rejects_password_confirmation_mismatch(client) -> None:
    with client:
        response = client.post(
            "/auth/sign-up",
            json={
                "email": "mismatch@example.com",
                "password": "StrongPassword123!",
                "password_confirm": "DifferentPassword123!",
            },
        )

    assert response.status_code == 422
    assert "Password confirmation does not match password" in response.text


def test_frontend_sign_up_respects_email_verification_requirement(tmp_path) -> None:
    with _client(tmp_path, require_verified_email=True) as client:
        sign_up = client.post(
            "/auth/sign-up",
            json={
                "name": "Verify Me",
                "email": "verify@example.com",
                "password": "StrongPassword123!",
                "passwordConfirm": "StrongPassword123!",
            },
        )
        assert sign_up.status_code == 201, sign_up.text
        sign_up_json = sign_up.json()
        assert sign_up_json["access_token"] is None
        assert sign_up_json["requires_email_verification"] is True
        assert sign_up_json["user"]["is_verified"] is False

        sign_in = client.post(
            "/auth/sign-in",
            json={"email": "verify@example.com", "password": "StrongPassword123!"},
        )
        assert sign_in.status_code == 401


def test_frontend_auth_routes_appear_in_openapi(client) -> None:
    with client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/auth/sign-up" in paths
    assert "/auth/sign-in" in paths
