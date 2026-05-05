from nmrcheck.settings import Settings, validate_startup_settings


def test_production_settings_warn_on_debug_and_open_origins() -> None:
    settings = Settings(
        app_env="production",
        debug=True,
        api_key=None,
        disable_auth=True,
        allowed_origins=("*",),
        healthcheck_path="health",
    )

    issues = validate_startup_settings(settings)

    assert any("API_KEY" in issue for issue in issues)
    assert any("DISABLE_BACKEND_AUTH" in issue for issue in issues)
    assert any("DEBUG" in issue for issue in issues)
    assert any("ALLOWED_ORIGINS" in issue for issue in issues)
    assert any("HEALTHCHECK_PATH" in issue for issue in issues)
