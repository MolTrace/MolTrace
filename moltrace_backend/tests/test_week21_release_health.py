from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def test_release_health_requires_admin_and_returns_release_data(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path / 'release_health.sqlite3'}"
    settings = Settings(
        database_url=db_url,
        require_verified_email=False,
        api_key="test-key",
        admin_emails=("admin@example.com",),
    )
    with TestClient(create_app(settings)) as client:
        reg = client.post(
            "/auth/register",
            json={"email": "admin@example.com", "password": "StrongPassword123!"},
        )
        assert reg.status_code in {200, 201, 409}

        login = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "StrongPassword123!"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        res = client.get(
            "/admin/release-health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["release_stage"] == "week21-release-candidate"
        assert data["release_version"] == "0.21.0"
        assert data["supported_raw_fid_vendors_beta"] == ["Bruker", "Varian/Agilent"]
        assert "value_dashboard" in data
