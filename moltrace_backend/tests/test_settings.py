from nmrcheck.settings import get_settings, normalize_database_url


def test_normalize_postgres_scheme() -> None:
    assert normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"


def test_2d_feature_flags_default_for_local_development(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_2D_NMR", raising=False)
    monkeypatch.delenv("ENABLE_2D_CONTOUR_PREVIEW", raising=False)
    monkeypatch.delenv("ENABLE_RAW_2D_FID_BETA", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.enable_2d_nmr is True
    assert settings.enable_2d_contour_preview is True
    assert settings.enable_raw_2d_fid_beta is False


def test_2d_feature_flags_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_2D_NMR", "false")
    monkeypatch.setenv("ENABLE_2D_CONTOUR_PREVIEW", "false")
    monkeypatch.setenv("ENABLE_RAW_2D_FID_BETA", "true")
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.enable_2d_nmr is False
    assert settings.enable_2d_contour_preview is False
    assert settings.enable_raw_2d_fid_beta is True


def test_local_auth_bypass_can_be_enabled_with_env_flag(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("API_KEY", "local-key")
    monkeypatch.setenv("DISABLE_BACKEND_AUTH", "true")
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.disable_auth is True
    assert settings.local_auth_disabled is True


def test_production_ignores_local_auth_bypass(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "prod-key")
    monkeypatch.setenv("DISABLE_BACKEND_AUTH", "true")
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.disable_auth is True
    assert settings.local_auth_disabled is False
