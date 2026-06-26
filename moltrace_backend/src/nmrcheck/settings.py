from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from .secrets_provider import resolve_secret, resolve_secret_strict


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    items = tuple(part.strip() for part in value.split(",") if part.strip())
    return items or default


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def normalize_database_url(database_url: str) -> str:
    url = database_url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


ETHANOL_SMILES = "CCO"


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    debug: bool = True
    log_level: str = "info"

    database_url: str = "sqlite:///./nmrcheck.sqlite3"
    redis_url: str | None = None
    queue_name: str = "nmrcheck"

    max_batch_size: int = 100
    allowed_upload_types: tuple[str, ...] = ("csv", "json")
    allowed_origins: tuple[str, ...] = ("*",)

    default_solvent: str | None = "CDCl3"
    default_smiles: str = ETHANOL_SMILES

    api_key: str | None = None
    disable_auth: bool = False
    # No admin is granted by default. Set ADMIN_EMAILS (comma-separated) in the
    # environment to designate admin accounts; see get_settings() below.
    admin_emails: tuple[str, ...] = ()

    host: str = "127.0.0.1"
    port: int = 8000
    healthcheck_path: str = "/health"

    access_token_ttl_minutes: int = 60 * 24 * 7
    require_verified_email: bool = False
    email_verification_ttl_minutes: int = 60 * 24 * 3
    password_reset_ttl_minutes: int = 60

    base_url: str = "http://127.0.0.1:8000"
    frontend_base_url: str = "http://localhost:3000"
    sso_encryption_key: str | None = None
    # MFA (Prompt 3). Separate key from SSO for blast-radius isolation; WebAuthn RP/origin are
    # pinned server-side (phishing resistance) and must match what the SPA serves from.
    mfa_encryption_key: str | None = None
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "MolTrace"
    webauthn_origin: str = "http://localhost:3000"
    mfa_pending_ttl_minutes: int = 5
    step_up_ttl_minutes: int = 5
    # Session/token hardening (Prompt 4). Defaults are generous (access TTL unchanged for
    # back-compat); shorten access in prod via ACCESS_TOKEN_TTL_MINUTES.
    refresh_token_idle_minutes: int = 60 * 24 * 7  # 7-day sliding idle window
    refresh_token_absolute_minutes: int = 60 * 24 * 30  # 30-day hard cap, never extended
    refresh_rotation_enabled: bool = True
    refresh_reuse_revokes_family: bool = True
    session_device_binding_enabled: bool = False
    # Credential hashing (Prompt 6). Passwords are Argon2id; this OPTIONAL application-wide
    # pepper (a KMS-held secret, §7) is HMAC-mixed into the password before hashing so a stolen
    # DB without the pepper can't be cracked offline. Default None = no pepper (back-compat).
    # NOTE: set it once and keep it stable — rotating/removing a configured pepper invalidates
    # all Argon2id hashes made with it (those users would need a password reset).
    password_pepper: str | None = None
    # Transport security (Prompt 9). HSTS is emitted ONLY on HTTPS requests (honours
    # X-Forwarded-Proto behind the TLS-terminating edge), so plain-HTTP local dev is untouched.
    # 2-year max-age + includeSubDomains + preload meets the hstspreload.org submission bar.
    hsts_enabled: bool = True
    hsts_max_age_seconds: int = 63072000  # 2 years
    hsts_include_subdomains: bool = True
    hsts_preload: bool = True
    # Tamper-evident audit chain (Prompt 10). The HMAC seal over periodic chain anchors uses
    # this key; default None falls back to a dev key (NOT for prod — set AUDIT_SIGNING_KEY).
    # audit_anchor_interval is the row count past which an anchor is suggested.
    audit_signing_key: str | None = None
    audit_anchor_interval: int = 1000
    email_from: str = "noreply@nmrcheck.local"
    email_backend: str = "database"

    default_analysis_minutes_saved: float = 7.0
    default_validation_minutes_saved: float = 2.0
    review_queue_limit: int = 100
    audit_log_limit: int = 200
    raw_fid_storage_dir: str = ".nmrcheck/raw_fid_store"
    raw_vault_dir: str = "raw_data_vault"
    raw_data_vault_dir: str = "raw_data_vault"
    raw_archive_max_bytes: int = 2 * 1024 * 1024 * 1024
    raw_archive_max_files: int = 5000
    raw_archive_allowed_extensions: tuple[str, ...] = (".zip", ".tar.gz", ".tgz")
    raw_archive_immutable: bool = True
    raw_archive_require_hash_verification: bool = True
    # ALCOA+ (Prompt 12): when True, a failure to set the raw-archive file read-only (chmod 0o444)
    # raises instead of warning, so write-once cannot silently degrade to warn-only. Default off to
    # preserve dev/test filesystems where chmod is a no-op; ops enables it on production.
    alcoa_raw_vault_strict_immutable: bool = False
    # API abuse protection (Prompt 16). Default OFF so existing tests + local dev are unaffected;
    # production turns it on via RATE_LIMIT_ENABLED. The limiter is an in-process token bucket keyed
    # by (principal|client-ip):route — see rate_limit.py + docs/security/waf_edge_runbook.md.
    rate_limit_enabled: bool = False
    rate_limit_default_per_minute: int = 300
    rate_limit_burst_multiplier: float = 2.0
    # Trust the first X-Forwarded-For hop for the client-IP key (only behind a trusted proxy such as
    # Render's edge — otherwise the header is spoofable). Default off.
    rate_limit_trust_forwarded_for: bool = False
    # Global request-body-size guard (Prompt 16), bytes. 0 = disabled (default, so existing flows are
    # unaffected); production sets a generous cap. Multipart uploads are exempt (own caps apply).
    max_request_body_bytes: int = 0
    enable_2d_nmr: bool = True
    enable_2d_contour_preview: bool = True
    enable_raw_2d_fid_beta: bool = False
    release_stage: str = "week21-release-candidate"
    release_version: str = "0.21.0"

    def is_admin_email(self, email: str | None) -> bool:
        if not email:
            return False
        return email.strip().lower() in self.admin_emails

    @property
    def local_auth_disabled(self) -> bool:
        """Allow unauthenticated local demos while keeping production protected."""
        return self.app_env.strip().lower() != "production" and (
            self.disable_auth or self.api_key is None
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env_admins = tuple(
        email.strip().lower()
        for email in _parse_csv(os.getenv("ADMIN_EMAILS"), ())
        if email.strip()
    )
    raw_vault_dir = os.getenv("RAW_VAULT_DIR", os.getenv("RAW_DATA_VAULT_DIR", "raw_data_vault"))
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        debug=_parse_bool(os.getenv("DEBUG"), True),
        log_level=os.getenv("LOG_LEVEL", "info"),
        database_url=normalize_database_url(
            resolve_secret_strict("DATABASE_URL", "sqlite:///./nmrcheck.sqlite3")
        ),
        redis_url=resolve_secret("REDIS_URL"),
        queue_name=os.getenv("QUEUE_NAME", "nmrcheck"),
        max_batch_size=_parse_int(os.getenv("MAX_BATCH_SIZE"), 100),
        allowed_upload_types=tuple(
            ext.lower().lstrip(".")
            for ext in _parse_csv(os.getenv("ALLOWED_UPLOAD_TYPES"), ("csv", "json"))
        ),
        allowed_origins=_parse_csv(os.getenv("ALLOWED_ORIGINS"), ("*",)),
        default_solvent=(os.getenv("DEFAULT_SOLVENT") or "CDCl3"),
        default_smiles=os.getenv("DEFAULT_SMILES", ETHANOL_SMILES),
        api_key=resolve_secret("API_KEY"),
        disable_auth=_parse_bool(
            os.getenv("DISABLE_BACKEND_AUTH") or os.getenv("DISABLE_AUTH"),
            False,
        ),
        admin_emails=env_admins,
        host=os.getenv("HOST", "127.0.0.1"),
        port=_parse_int(os.getenv("PORT"), 8000),
        healthcheck_path=os.getenv("HEALTHCHECK_PATH", "/health"),
        access_token_ttl_minutes=_parse_int(
            os.getenv("ACCESS_TOKEN_TTL_MINUTES"), 60 * 24 * 7
        ),
        require_verified_email=_parse_bool(
            os.getenv("REQUIRE_VERIFIED_EMAIL"), False
        ),
        email_verification_ttl_minutes=_parse_int(
            os.getenv("EMAIL_VERIFICATION_TTL_MINUTES"), 60 * 24 * 3
        ),
        password_reset_ttl_minutes=_parse_int(
            os.getenv("PASSWORD_RESET_TTL_MINUTES"), 60
        ),
        base_url=os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        frontend_base_url=os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/"),
        sso_encryption_key=resolve_secret("SSO_ENCRYPTION_KEY"),
        mfa_encryption_key=resolve_secret("MFA_ENCRYPTION_KEY"),
        webauthn_rp_id=os.getenv("WEBAUTHN_RP_ID", "localhost"),
        webauthn_rp_name=os.getenv("WEBAUTHN_RP_NAME", "MolTrace"),
        webauthn_origin=os.getenv(
            "WEBAUTHN_ORIGIN",
            os.getenv("FRONTEND_BASE_URL", "http://localhost:3000"),
        ).rstrip("/"),
        mfa_pending_ttl_minutes=_parse_int(os.getenv("MFA_PENDING_TTL_MINUTES"), 5),
        step_up_ttl_minutes=_parse_int(os.getenv("STEP_UP_TTL_MINUTES"), 5),
        refresh_token_idle_minutes=_parse_int(
            os.getenv("REFRESH_TOKEN_IDLE_MINUTES"), 60 * 24 * 7
        ),
        refresh_token_absolute_minutes=_parse_int(
            os.getenv("REFRESH_TOKEN_ABSOLUTE_MINUTES"), 60 * 24 * 30
        ),
        refresh_rotation_enabled=_parse_bool(os.getenv("REFRESH_ROTATION_ENABLED"), True),
        refresh_reuse_revokes_family=_parse_bool(
            os.getenv("REFRESH_REUSE_REVOKES_FAMILY"), True
        ),
        session_device_binding_enabled=_parse_bool(
            os.getenv("SESSION_DEVICE_BINDING_ENABLED"), False
        ),
        password_pepper=resolve_secret("PASSWORD_PEPPER"),
        hsts_enabled=_parse_bool(os.getenv("HSTS_ENABLED"), True),
        hsts_max_age_seconds=_parse_int(os.getenv("HSTS_MAX_AGE_SECONDS"), 63072000),
        hsts_include_subdomains=_parse_bool(os.getenv("HSTS_INCLUDE_SUBDOMAINS"), True),
        hsts_preload=_parse_bool(os.getenv("HSTS_PRELOAD"), True),
        audit_signing_key=resolve_secret("AUDIT_SIGNING_KEY"),
        audit_anchor_interval=_parse_int(os.getenv("AUDIT_ANCHOR_INTERVAL"), 1000),
        email_from=os.getenv("EMAIL_FROM", "noreply@nmrcheck.local"),
        email_backend=(
            os.getenv("EMAIL_BACKEND", "database").strip().lower() or "database"
        ),
        default_analysis_minutes_saved=_parse_float(
            os.getenv("DEFAULT_ANALYSIS_MINUTES_SAVED"), 7.0
        ),
        default_validation_minutes_saved=_parse_float(
            os.getenv("DEFAULT_VALIDATION_MINUTES_SAVED"), 2.0
        ),
        review_queue_limit=_parse_int(os.getenv("REVIEW_QUEUE_LIMIT"), 100),
        audit_log_limit=_parse_int(os.getenv("AUDIT_LOG_LIMIT"), 200),
        raw_fid_storage_dir=os.getenv("RAW_FID_STORAGE_DIR", ".nmrcheck/raw_fid_store"),
        raw_vault_dir=raw_vault_dir,
        raw_data_vault_dir=raw_vault_dir,
        raw_archive_max_bytes=_parse_int(
            os.getenv("RAW_ARCHIVE_MAX_BYTES"), 2 * 1024 * 1024 * 1024
        ),
        raw_archive_max_files=_parse_int(os.getenv("RAW_ARCHIVE_MAX_FILES"), 5000),
        raw_archive_allowed_extensions=tuple(
            ext if ext.startswith(".") else f".{ext}"
            for ext in _parse_csv(
                os.getenv("RAW_ARCHIVE_ALLOWED_EXTENSIONS"),
                (".zip", ".tar.gz", ".tgz"),
            )
        ),
        raw_archive_immutable=_parse_bool(os.getenv("RAW_ARCHIVE_IMMUTABLE"), True),
        raw_archive_require_hash_verification=_parse_bool(
            os.getenv("RAW_ARCHIVE_REQUIRE_HASH_VERIFICATION"), True
        ),
        alcoa_raw_vault_strict_immutable=_parse_bool(
            os.getenv("ALCOA_RAW_VAULT_STRICT_IMMUTABLE"), False
        ),
        rate_limit_enabled=_parse_bool(os.getenv("RATE_LIMIT_ENABLED"), False),
        rate_limit_default_per_minute=_parse_int(
            os.getenv("RATE_LIMIT_DEFAULT_PER_MINUTE"), 300
        ),
        rate_limit_burst_multiplier=_parse_float(
            os.getenv("RATE_LIMIT_BURST_MULTIPLIER"), 2.0
        ),
        rate_limit_trust_forwarded_for=_parse_bool(
            os.getenv("RATE_LIMIT_TRUST_FORWARDED_FOR"), False
        ),
        max_request_body_bytes=_parse_int(os.getenv("MAX_REQUEST_BODY_BYTES"), 0),
        enable_2d_nmr=_parse_bool(os.getenv("ENABLE_2D_NMR"), True),
        enable_2d_contour_preview=_parse_bool(os.getenv("ENABLE_2D_CONTOUR_PREVIEW"), True),
        enable_raw_2d_fid_beta=_parse_bool(os.getenv("ENABLE_RAW_2D_FID_BETA"), False),
        release_stage=os.getenv("RELEASE_STAGE", "week21-release-candidate"),
        release_version=os.getenv("RELEASE_VERSION", "0.21.0"),
    )


def validate_startup_settings(settings: Settings) -> list[str]:
    issues: list[str] = []
    if settings.app_env == "production" and not settings.api_key:
        issues.append("API_KEY is not set for production.")
    if settings.app_env == "production" and not settings.sso_encryption_key:
        issues.append("SSO_ENCRYPTION_KEY must be set in production.")
    if settings.app_env == "production" and not settings.mfa_encryption_key:
        issues.append("MFA_ENCRYPTION_KEY must be set in production.")
    if settings.app_env == "production" and settings.disable_auth:
        issues.append("DISABLE_BACKEND_AUTH must not be enabled in production.")
    if settings.app_env == "production" and settings.debug:
        issues.append("DEBUG should be false in production.")
    if settings.app_env == "production" and settings.allowed_origins == ("*",):
        issues.append("ALLOWED_ORIGINS should be restricted in production.")
    if settings.max_batch_size < 1:
        issues.append("MAX_BATCH_SIZE must be at least 1.")
    if settings.raw_archive_max_bytes < 1:
        issues.append("RAW_ARCHIVE_MAX_BYTES must be at least 1.")
    if settings.raw_archive_max_files < 1:
        issues.append("RAW_ARCHIVE_MAX_FILES must be at least 1.")
    if not settings.raw_archive_allowed_extensions:
        issues.append("RAW_ARCHIVE_ALLOWED_EXTENSIONS must include at least one extension.")
    unsupported = set(settings.raw_archive_allowed_extensions) - {".zip", ".tar.gz", ".tgz"}
    if unsupported:
        issues.append("RAW_ARCHIVE_ALLOWED_EXTENSIONS may only include .zip, .tar.gz, and .tgz.")
    if not settings.healthcheck_path.startswith("/"):
        issues.append("HEALTHCHECK_PATH must begin with '/'.")
    if settings.access_token_ttl_minutes < 15:
        issues.append("ACCESS_TOKEN_TTL_MINUTES is unusually short.")
    return issues
