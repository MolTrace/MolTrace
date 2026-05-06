from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _preview_payload() -> dict[str, str]:
    return {"name": "ethanol", "smiles": "CCO"}


def test_development_without_api_key_allows_local_unauthenticated_demo(tmp_path) -> None:
    app = create_app(
        Settings(
            app_env="development",
            database_url=f"sqlite:///{tmp_path / 'local-open.sqlite3'}",
            api_key=None,
        )
    )

    with TestClient(app) as client:
        res = client.post("/prediction/nmr/preview", json=_preview_payload())

    assert res.status_code == 200
    assert res.json()["formula"] == "C2H6O"


def test_development_with_api_key_still_requires_auth_by_default(tmp_path) -> None:
    app = create_app(
        Settings(
            app_env="development",
            database_url=f"sqlite:///{tmp_path / 'local-keyed.sqlite3'}",
            api_key="test-key",
        )
    )

    with TestClient(app) as client:
        blocked = client.post("/prediction/nmr/preview", json=_preview_payload())
        allowed = client.post(
            "/prediction/nmr/preview",
            headers={"x-api-key": "test-key"},
            json=_preview_payload(),
        )

    assert blocked.status_code == 401
    assert allowed.status_code == 200


def test_development_disable_auth_overrides_local_api_key_for_demos(tmp_path) -> None:
    app = create_app(
        Settings(
            app_env="development",
            database_url=f"sqlite:///{tmp_path / 'local-disabled.sqlite3'}",
            api_key="test-key",
            disable_auth=True,
        )
    )

    with TestClient(app) as client:
        res = client.post("/prediction/nmr/preview", json=_preview_payload())

    assert res.status_code == 200


def test_production_never_disables_auth_even_if_flag_is_set(tmp_path) -> None:
    app = create_app(
        Settings(
            app_env="production",
            debug=False,
            allowed_origins=("http://example.test",),
            database_url=f"sqlite:///{tmp_path / 'prod.sqlite3'}",
            api_key="test-key",
            disable_auth=True,
        )
    )

    with TestClient(app) as client:
        blocked = client.post("/prediction/nmr/preview", json=_preview_payload())
        allowed = client.post(
            "/prediction/nmr/preview",
            headers={"x-api-key": "test-key"},
            json=_preview_payload(),
        )

    assert blocked.status_code == 401
    assert allowed.status_code == 200
