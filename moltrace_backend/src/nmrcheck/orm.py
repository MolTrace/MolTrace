from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email_verified", "email", "is_verified"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # v0.6.7 per-tenant graduation knob for the opt-in GSD analysis
    # backend.  ``None`` means the tenant still sees ``experimental:
    # true`` on /spectrum/analyze/gsd; a timestamp means the admin
    # graduated this tenant out of experimental at that moment.
    # Self-documenting: the timestamp tells dashboards "when did each
    # tenant graduate" without a separate audit query.
    gsd_graduated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tokens: Mapped[list[SessionTokenORM]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    action_tokens: Mapped[list[UserActionTokenORM]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    analyses: Mapped[list[AnalysisORM]] = relationship(
        back_populates="user", foreign_keys="AnalysisORM.user_id"
    )
    review_assignments: Mapped[list[AnalysisORM]] = relationship(
        back_populates="reviewer", foreign_keys="AnalysisORM.reviewer_user_id"
    )
    jobs: Mapped[list[JobORM]] = relationship(back_populates="user")
    projects: Mapped[list[ProjectORM]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    review_decisions: Mapped[list[ReviewDecisionORM]] = relationship(back_populates="reviewer")
    raw_archives: Mapped[list[RawArchiveORM]] = relationship(back_populates="user")
    nmr2d_runs: Mapped[list[NMR2DRunORM]] = relationship(back_populates="user")
    audit_events: Mapped[list[AuditEventORM]] = relationship(back_populates="actor_user")


class SessionTokenORM(Base):
    __tablename__ = "session_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # MFA state (Prompt 3): authentication methods carried + the rolling step-up proof.
    # authentication methods reference (pwd / totp / webauthn / sso / backup)
    amr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stepped_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step_up_factor: Mapped[str | None] = mapped_column(String(16), nullable=True)
    step_up_aal: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Session/token hardening (Prompt 4): the family this access row belongs to (NULL = legacy
    # pre-0020 row, so the family-revocation predicate no-ops) + the refresh that minted it.
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_families.id", ondelete="CASCADE"), nullable=True, index=True
    )
    refresh_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[UserORM] = relationship(back_populates="tokens")


class SessionFamilyORM(Base):
    """A login lineage (Prompt 4): one row per login, constant across refresh rotations. Carries the
    hard absolute-expiry cap, the MFA provenance, an optional device-binding fingerprint, and the
    single revoked_at flag that the access read-path checks for IMMEDIATE family-wide revocation."""

    __tablename__ = "session_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    idle_ttl_seconds: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    device_fingerprint_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshTokenORM(Base):
    """A rotating, single-use refresh token (Prompt 4). Stored sha256-at-rest. Spent on rotation
    (``rotated_at`` set, ``next_id`` chained); presenting a spent/revoked refresh is reuse and
    revokes the whole family. Authorizes ONLY /auth/refresh — never a product API request."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family_rotated", "family_id", "rotated_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("session_families.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prev_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserActionTokenORM(Base):
    __tablename__ = "user_action_tokens"
    __table_args__ = (
        Index("ix_user_action_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_user_action_tokens_expires", "expires_at"),
        UniqueConstraint("token_hash", name="uq_user_action_tokens_token_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserORM] = relationship(back_populates="action_tokens")


class SSOConnectionORM(Base):
    """A per-organization OIDC identity-provider configuration (Prompt 1, SSO)."""

    __tablename__ = "sso_connections"
    __table_args__ = (Index("ix_sso_connections_org", "organization_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    protocol: Mapped[str] = mapped_column(String(16), default="oidc")
    issuer: Mapped[str] = mapped_column(String(500))
    client_id: Mapped[str] = mapped_column(String(500))
    client_secret_encrypted: Mapped[str] = mapped_column(Text)  # AES-256-GCM at rest
    email_domains_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enforce_sso: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SSOLoginFlowORM(Base):
    """Ephemeral state for one OIDC login (PKCE + nonce), then a one-time exchange code.

    No session token is stored: the callback records the resolved ``user_id`` and a one-time
    ``exchange_code``; the bearer session is minted only when the SPA calls the exchange route.
    """

    __tablename__ = "sso_login_flows"
    __table_args__ = (
        Index("ix_sso_login_flows_exchange", "exchange_code"),
        Index("ix_sso_login_flows_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("sso_connections.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    nonce: Mapped[str] = mapped_column(String(128))
    code_verifier: Mapped[str] = mapped_column(String(128))
    redirect_uri: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|completed|consumed
    exchange_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SCIMTokenORM(Base):
    """A long-lived SCIM bearer token for one SSO connection (SCIM 2.0 provisioning).

    The token is stored as a SHA-256 digest only (``token_hash``) — the server compares a
    presented token, never recovers it — exactly like ``session_tokens``/``user_action_tokens``.
    At most one *live* token per connection (enforced in code on issue, plus a Postgres
    partial-unique index); rotation is issue-then-revoke.
    """

    __tablename__ = "scim_tokens"
    __table_args__ = (
        Index(
            "ix_scim_tokens_live",
            "connection_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("sso_connections.id", ondelete="CASCADE"), index=True
    )
    token_prefix: Mapped[str] = mapped_column(String(16), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SCIMUserORM(Base):
    """The per-connection SCIM resource for one provisioned user (SCIM 2.0 provisioning).

    This is the tenant-isolation boundary: the SCIM resource ``id`` returned to the IdP is this
    row's ``id`` (never the global ``users.id``), so an id minted under one connection resolves
    to no row under another connection's token — closing IDOR/enumeration. ``external_id`` /
    ``scim_user_name`` are per-connection identifiers (``users.email`` is cross-org by design).
    Deprovisioning is soft: ``active``/``deprovisioned_at`` flip, the underlying user row is kept.
    """

    __tablename__ = "scim_users"
    __table_args__ = (
        Index("ix_scim_users_user", "user_id"),
        UniqueConstraint("connection_id", "external_id", name="uq_scim_users_conn_external"),
        UniqueConstraint("connection_id", "scim_user_name", name="uq_scim_users_conn_username"),
        UniqueConstraint("connection_id", "user_id", name="uq_scim_users_conn_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("sso_connections.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scim_user_name: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    raw_attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deprovisioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MFATotpCredentialORM(Base):
    """A user's RFC 6238 TOTP authenticator. The base32 secret is AES-256-GCM encrypted at rest;
    a secret is only usable once ``confirmed_at`` is set (a code was verified). At most one
    confirmed TOTP per user (partial-unique, Postgres + SQLite)."""

    __tablename__ = "mfa_totp_credentials"
    __table_args__ = (
        Index(
            "ix_mfa_totp_confirmed",
            "user_id",
            unique=True,
            postgresql_where=text("confirmed_at IS NOT NULL"),
            sqlite_where=text("confirmed_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    secret_encrypted: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # replay guard
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MFAWebAuthnCredentialORM(Base):
    """A registered WebAuthn/FIDO2 passkey. Stores only public material (no secret): the raw
    ``credential_id``, the COSE ``public_key``, and the ``sign_count`` for clone detection."""

    __tablename__ = "mfa_webauthn_credentials"
    __table_args__ = (Index("ix_mfa_webauthn_cred_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    transports_json: Mapped[str] = mapped_column(Text, default="[]")
    aaguid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # single/multi
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)
    nickname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MFAWebAuthnChallengeORM(Base):
    """Ephemeral, single-use WebAuthn challenge persisted server-side between the options and verify
    legs (register / authenticate / step-up). The server-stored ``challenge`` + ``rp_id`` are the
    only values trusted at verify — the client-returned challenge is ignored."""

    __tablename__ = "mfa_webauthn_challenges"
    __table_args__ = (Index("ix_mfa_webauthn_chal_expires", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(24))  # webauthn_register|webauthn_auth|step_up
    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    rp_id: Mapped[str] = mapped_column(String(255))
    webauthn_user_handle: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MFARecoveryCodeORM(Base):
    """A one-time recovery/backup code, stored only as a SHA-256 digest. Valid as a login second
    factor (never as a signing/admin step-up)."""

    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (Index("ix_mfa_recovery_user_used", "user_id", "used_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MFALoginChallengeORM(Base):
    """The short-lived MFA-pending token issued mid-login. It is stored ONLY as a digest in this
    separate table — invisible to ``get_user_by_token`` — so a pending token can never authorize an
    API call ("no MFA -> no bearer" is structural). Traded for a real session at the verify routes."""

    __tablename__ = "mfa_login_challenges"
    __table_args__ = (Index("ix_mfa_login_chal_expires", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(String(24), default="login")
    factors_offered_json: Mapped[str] = mapped_column(Text, default="[]")
    webauthn_challenge: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sso_flow_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amr_from_sso: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MFAPolicyORM(Base):
    """Per-organization MFA enforcement policy (one row per org). The source of truth for the
    fail-closed ``require_mfa_satisfied`` check."""

    __tablename__ = "mfa_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_mfa_policies_org"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allowed_factors_json: Mapped[str] = mapped_column(Text, default='["webauthn", "totp"]')
    grace_period_days: Mapped[int] = mapped_column(Integer, default=7)
    enforce_for_sso: Mapped[bool] = mapped_column(Boolean, default=False)
    require_step_up_for_signing: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmailOutboxORM(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    to_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(String(32), nullable=True)


class JobORM(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_user_status_created", "user_id", "status", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    completed_items: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    queue_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user: Mapped[UserORM | None] = relationship(back_populates="jobs")
    analyses: Mapped[list[AnalysisORM]] = relationship(back_populates="job")


class AnalysisORM(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        Index("ix_analyses_user_created", "user_id", "created_at"),
        Index("ix_analyses_job_created", "job_id", "created_at"),
        Index("ix_analyses_label_created", "label", "created_at"),
        Index("ix_analyses_review_status", "review_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    solvent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    smiles: Mapped[str] = mapped_column(Text)
    nmr_text: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(64), index=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review")
    final_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_total_h: Mapped[int] = mapped_column(Integer)
    observed_total_h: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    notes_json: Mapped[str] = mapped_column(Text)
    parsed_peak_count: Mapped[int] = mapped_column(Integer, default=0)
    delta_total_h: Mapped[int] = mapped_column(Integer, default=0)
    hours_saved_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    full_report_json: Mapped[str] = mapped_column(Text)

    user: Mapped[UserORM | None] = relationship(back_populates="analyses", foreign_keys=[user_id])
    reviewer: Mapped[UserORM | None] = relationship(
        back_populates="review_assignments", foreign_keys=[reviewer_user_id]
    )
    job: Mapped[JobORM | None] = relationship(back_populates="analyses")
    project_samples: Mapped[list[ProjectSampleORM]] = relationship(back_populates="analysis")
    review_decisions: Mapped[list[ReviewDecisionORM]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    reports: Mapped[list[ReportORM]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    fid_runs: Mapped[list[FIDRunORM]] = relationship(back_populates="analysis")
    nmr2d_runs: Mapped[list[NMR2DRunORM]] = relationship(back_populates="analysis")


class ProjectORM(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "name", name="uq_projects_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[UserORM] = relationship(back_populates="projects")
    samples: Mapped[list[ProjectSampleORM]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectSampleORM(Base):
    __tablename__ = "project_samples"
    __table_args__ = (
        Index("ix_project_samples_project_created", "project_id", "created_at"),
        Index("ix_project_samples_analysis_created", "analysis_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    smiles: Mapped[str] = mapped_column(Text)
    nmr_text: Mapped[str] = mapped_column(Text)
    solvent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    project: Mapped[ProjectORM] = relationship(back_populates="samples")
    analysis: Mapped[AnalysisORM | None] = relationship(back_populates="project_samples")


class SpectraCheckProjectORM(Base):
    __tablename__ = "spectracheck_projects"
    __table_args__ = (
        Index("ix_spectracheck_projects_owner_updated", "owner_id", "updated_at"),
        Index("ix_spectracheck_projects_status_updated", "status", "updated_at"),
        UniqueConstraint("owner_id", "name", name="uq_spectracheck_projects_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    samples: Mapped[list[SpectraCheckSampleORM]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[SpectraCheckSessionORM]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class SpectraCheckSampleORM(Base):
    __tablename__ = "spectracheck_samples"
    __table_args__ = (
        Index("ix_spectracheck_samples_project_updated", "project_id", "updated_at"),
        UniqueConstraint(
            "project_id", "sample_id", name="uq_spectracheck_samples_project_sample_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_projects.id", ondelete="CASCADE"), index=True
    )
    sample_id: Mapped[str] = mapped_column(String(100), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    molecule_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    solvent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    project: Mapped[SpectraCheckProjectORM] = relationship(back_populates="samples")
    sessions: Mapped[list[SpectraCheckSessionORM]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class SpectraCheckSessionORM(Base):
    __tablename__ = "spectracheck_sessions"
    __table_args__ = (
        Index("ix_spectracheck_sessions_project_updated", "project_id", "updated_at"),
        Index("ix_spectracheck_sessions_sample_updated", "sample_pk", "updated_at"),
        Index("ix_spectracheck_sessions_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_projects.id", ondelete="CASCADE"), index=True
    )
    sample_pk: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_samples.id", ondelete="CASCADE"), index=True
    )
    sample_id: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    shared_inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    latest_unified_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    project: Mapped[SpectraCheckProjectORM] = relationship(back_populates="sessions")
    sample: Mapped[SpectraCheckSampleORM] = relationship(back_populates="sessions")
    evidence_records: Mapped[list[SpectraCheckEvidenceRecordORM]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    review_decisions: Mapped[list[SpectraCheckReviewDecisionORM]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list[SpectraCheckAuditEventORM]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    reports: Mapped[list[SpectraCheckReportRecordORM]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SpectraCheckEvidenceRecordORM(Base):
    __tablename__ = "spectracheck_evidence_records"
    __table_args__ = (
        Index("ix_spectracheck_evidence_session_created", "session_id", "created_at"),
        Index("ix_spectracheck_evidence_layer_created", "layer", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    layer: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    source_tab: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(100), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary_json: Mapped[str] = mapped_column(Text, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    endpoint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_preview_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    selected_for_unified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    session: Mapped[SpectraCheckSessionORM] = relationship(back_populates="evidence_records")


class SpectraCheckReviewDecisionORM(Base):
    __tablename__ = "spectracheck_review_decisions"
    __table_args__ = (
        Index("ix_spectracheck_reviews_session_created", "session_id", "created_at"),
        Index("ix_spectracheck_reviews_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    session: Mapped[SpectraCheckSessionORM] = relationship(back_populates="review_decisions")


class SpectraCheckAuditEventORM(Base):
    __tablename__ = "spectracheck_audit_events"
    __table_args__ = (
        Index("ix_spectracheck_audit_session_created", "session_id", "created_at"),
        Index("ix_spectracheck_audit_type_created", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    session: Mapped[SpectraCheckSessionORM] = relationship(back_populates="audit_events")


class SpectraCheckReportRecordORM(Base):
    __tablename__ = "spectracheck_report_records"
    __table_args__ = (
        Index("ix_spectracheck_reports_session_created", "session_id", "created_at"),
        Index("ix_spectracheck_reports_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    report_title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(64), index=True)
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    report_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    session: Mapped[SpectraCheckSessionORM] = relationship(back_populates="reports")


class MethodRegistryEntryORM(Base):
    __tablename__ = "method_registry_entries"
    __table_args__ = (
        Index("ix_method_registry_category_status", "category", "status"),
        UniqueConstraint("slug", "version", name="uq_method_registry_slug_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    implementation_module: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    default_scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    default_threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelVersionORM(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        Index("ix_model_versions_method_status", "method_id", "status"),
        Index("ix_model_versions_name_version", "model_name", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_name: Mapped[str] = mapped_column(String(200), index=True)
    model_family: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    training_data_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ScoringProfileORM(Base):
    __tablename__ = "scoring_profiles"
    __table_args__ = (
        Index("ix_scoring_profiles_method_status", "method_id", "status"),
        UniqueConstraint("slug", "version", name="uq_scoring_profiles_slug_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    weights_json: Mapped[str] = mapped_column(Text, default="{}")
    scoring_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    label_thresholds_json: Mapped[str] = mapped_column(Text, default="{}")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ThresholdProfileORM(Base):
    __tablename__ = "threshold_profiles"
    __table_args__ = (
        Index("ix_threshold_profiles_category_status", "category", "status"),
        UniqueConstraint("slug", "version", name="uq_threshold_profiles_slug_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    thresholds_json: Mapped[str] = mapped_column(Text, default="{}")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class BenchmarkDatasetORM(Base):
    __tablename__ = "benchmark_datasets"
    __table_args__ = (
        Index("ix_benchmark_datasets_category_created", "category", "created_at"),
        UniqueConstraint("slug", "version", name="uq_benchmark_datasets_slug_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    dataset_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ground_truth_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationRunORM(Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        Index("ix_validation_runs_method_created", "method_id", "created_at"),
        Index("ix_validation_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    benchmark_dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("benchmark_datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationMetricORM(Base):
    __tablename__ = "validation_metrics"
    __table_args__ = (Index("ix_validation_metrics_run_name", "validation_run_id", "metric_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(160), index=True)
    metric_value: Mapped[float] = mapped_column(Float)
    metric_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DriftAlertORM(Base):
    __tablename__ = "drift_alerts"
    __table_args__ = (
        Index("ix_drift_alerts_method_status", "method_id", "status"),
        Index("ix_drift_alerts_severity_created", "severity", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    severity: Mapped[str] = mapped_column(String(32), default="warning", index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    metric_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MethodComparisonRunORM(Base):
    __tablename__ = "method_comparison_runs"
    __table_args__ = (
        Index(
            "ix_method_comparisons_baseline_candidate", "baseline_method_id", "candidate_method_id"
        ),
        Index("ix_method_comparisons_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    baseline_method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    benchmark_dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("benchmark_datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    winner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class OrganizationORM(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("ix_organizations_name_created", "name", "created_at"),
        UniqueConstraint("name", name="uq_organizations_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TeamMemberORM(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        Index("ix_team_members_org_email", "organization_id", "user_email"),
        Index("ix_team_members_email_status", "user_email", "status"),
        UniqueConstraint("organization_id", "user_email", name="uq_team_members_org_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ProjectPermissionORM(Base):
    __tablename__ = "project_permissions"
    __table_args__ = (
        Index("ix_project_permissions_project_email", "project_id", "user_email"),
        UniqueConstraint("project_id", "user_email", name="uq_project_permissions_project_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_projects.id", ondelete="CASCADE"), index=True
    )
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SessionReviewerORM(Base):
    __tablename__ = "session_reviewers"
    __table_args__ = (
        Index("ix_session_reviewers_session_status", "session_id", "status"),
        UniqueConstraint("session_id", "reviewer_email", name="uq_session_reviewers_session_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    reviewer_email: Mapped[str] = mapped_column(String(255), index=True)
    assigned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="assigned", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class EvidenceCommentORM(Base):
    __tablename__ = "evidence_comments"
    __table_args__ = (
        Index("ix_evidence_comments_session_created", "session_id", "created_at"),
        Index("ix_evidence_comments_evidence_created", "evidence_id", "created_at"),
        Index("ix_evidence_comments_artifact_created", "artifact_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_evidence_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifact_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    comment: Mapped[str] = mapped_column(Text)
    comment_type: Mapped[str] = mapped_column(String(32), default="note", index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReviewTaskORM(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        Index("ix_review_tasks_session_status", "session_id", "status"),
        Index("ix_review_tasks_assignee_status", "assigned_to", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ApprovalRecordORM(Base):
    __tablename__ = "approval_records"
    __table_args__ = (
        Index("ix_approval_records_session_created", "session_id", "created_at"),
        Index("ix_approval_records_report_decision", "report_id", "decision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_evidence_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_report_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    approver_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReportLockORM(Base):
    __tablename__ = "report_locks"
    __table_args__ = (
        Index("ix_report_locks_report_status", "report_id", "status"),
        Index("ix_report_locks_session_status", "session_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_report_records.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="locked", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SecureShareLinkORM(Base):
    __tablename__ = "secure_share_links"
    __table_args__ = (
        Index("ix_secure_share_links_project_created", "project_id", "created_at"),
        Index("ix_secure_share_links_session_created", "session_id", "created_at"),
        UniqueConstraint("token_hash", name="uq_secure_share_links_token_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_report_records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    permission: Mapped[str] = mapped_column(String(32), default="view", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ManagedFileRecordORM(Base):
    __tablename__ = "managed_file_records"
    __table_args__ = (
        Index("ix_managed_files_sha256", "sha256"),
        Index("ix_managed_files_kind_created", "file_kind", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", index=True)
    storage_key: Mapped[str] = mapped_column(Text)
    file_kind: Mapped[str] = mapped_column(String(64), default="other", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SpectraCheckSessionFileLinkORM(Base):
    __tablename__ = "spectracheck_session_file_links"
    __table_args__ = (
        Index("ix_session_file_links_session_created", "session_id", "created_at"),
        Index("ix_session_file_links_file_created", "file_id", "created_at"),
        UniqueConstraint("session_id", "file_id", "role", name="uq_session_file_link_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("managed_file_records.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AnalysisJobORM(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_session_created", "session_id", "created_at"),
        Index("ix_analysis_jobs_status_created", "status", "created_at"),
        Index("ix_analysis_jobs_type_created", "job_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    current_step: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_file_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class JobEventORM(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        Index("ix_job_events_job_created", "job_id", "created_at"),
        Index("ix_job_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ArtifactRecordORM(Base):
    __tablename__ = "artifact_records"
    __table_args__ = (
        Index("ix_artifacts_job_created", "job_id", "created_at"),
        Index("ix_artifacts_session_created", "session_id", "created_at"),
        Index("ix_artifacts_type_created", "artifact_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ConnectorRegistryORM(Base):
    __tablename__ = "connector_registry"
    __table_args__ = (
        UniqueConstraint("connector_key", name="uq_connector_registry_key"),
        Index("ix_connector_registry_type_status", "connector_type", "status"),
        Index("ix_connector_registry_target_status", "target_program", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_key: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    connector_type: Mapped[str] = mapped_column(String(64), index=True)
    target_program: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    config_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ConnectorCredentialReferenceORM(Base):
    __tablename__ = "connector_credential_references"
    __table_args__ = (
        Index("ix_connector_credentials_connector_status", "connector_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="CASCADE"),
        index=True,
    )
    credential_type: Mapped[str] = mapped_column(String(32), index=True)
    secret_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ConnectorHealthCheckORM(Base):
    __tablename__ = "connector_health_checks"
    __table_args__ = (
        Index("ix_connector_health_connector_checked", "connector_id", "checked_at"),
        Index("ix_connector_health_status_checked", "status", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class InstrumentWatchFolderORM(Base):
    __tablename__ = "instrument_watch_folders"
    __table_args__ = (
        Index("ix_watch_folders_connector_status", "connector_id", "status"),
        Index("ix_watch_folders_target_status", "target_program", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int | None] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    folder_path: Mapped[str] = mapped_column(Text)
    file_patterns_json: Mapped[str] = mapped_column(Text, default="[]")
    recursive: Mapped[bool] = mapped_column(Boolean, default=False)
    target_program: Mapped[str] = mapped_column(String(64), index=True)
    target_route: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class IngestionRunORM(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_connector_created", "connector_id", "created_at"),
        Index("ix_ingestion_runs_watch_folder_created", "watch_folder_id", "created_at"),
        Index("ix_ingestion_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int | None] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    watch_folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("instrument_watch_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class FileNormalizationRunORM(Base):
    __tablename__ = "file_normalization_runs"
    __table_args__ = (
        Index("ix_file_normalization_file_created", "file_id", "created_at"),
        Index("ix_file_normalization_status_created", "status", "created_at"),
        Index("ix_file_normalization_format_status", "source_format", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("managed_file_records.id", ondelete="CASCADE"),
        index=True,
    )
    source_format: Mapped[str] = mapped_column(String(48), index=True)
    target_format: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    output_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifact_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExternalSystemRecordORM(Base):
    __tablename__ = "external_system_records"
    __table_args__ = (
        Index("ix_external_records_connector_created", "connector_id", "created_at"),
        Index("ix_external_records_system_object", "external_system", "external_object_type"),
        UniqueConstraint(
            "connector_id",
            "external_system",
            "external_object_type",
            "external_object_id",
            name="uq_external_records_connector_object",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="CASCADE"),
        index=True,
    )
    external_system: Mapped[str] = mapped_column(String(160), index=True)
    external_object_type: Mapped[str] = mapped_column(String(48), index=True)
    external_object_id: Mapped[str] = mapped_column(String(240), index=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExternalObjectLinkORM(Base):
    __tablename__ = "external_object_links"
    __table_args__ = (
        Index("ix_external_links_external_created", "external_record_id", "created_at"),
        Index(
            "ix_external_links_moltrace_resource",
            "moltrace_resource_type",
            "moltrace_resource_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_record_id: Mapped[int] = mapped_column(
        ForeignKey("external_system_records.id", ondelete="CASCADE"),
        index=True,
    )
    moltrace_resource_type: Mapped[str] = mapped_column(String(64), index=True)
    moltrace_resource_id: Mapped[int] = mapped_column(Integer, index=True)
    relation_type: Mapped[str] = mapped_column(String(48), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MappingTemplateORM(Base):
    __tablename__ = "mapping_templates"
    __table_args__ = (
        Index("ix_mapping_templates_connector_status", "connector_id", "status"),
        Index("ix_mapping_templates_source_target", "source_type", "target_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int | None] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(240))
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    field_map_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class OutboundSyncJobORM(Base):
    __tablename__ = "outbound_sync_jobs"
    __table_args__ = (
        Index("ix_outbound_sync_connector_created", "connector_id", "created_at"),
        Index("ix_outbound_sync_status_created", "status", "created_at"),
        Index("ix_outbound_sync_resource", "source_resource_type", "source_resource_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="CASCADE"),
        index=True,
    )
    target_system: Mapped[str] = mapped_column(String(160), index=True)
    source_resource_type: Mapped[str] = mapped_column(String(64), index=True)
    source_resource_id: Mapped[int] = mapped_column(Integer, index=True)
    payload_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WebhookSubscriptionORM(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        Index("ix_webhook_subscriptions_connector_status", "connector_id", "status"),
        Index("ix_webhook_subscriptions_target_hash", "target_url_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int | None] = mapped_column(
        ForeignKey("connector_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(240))
    event_types_json: Mapped[str] = mapped_column(Text, default="[]")
    target_url_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatorySubmissionPackageORM(Base):
    __tablename__ = "regulatory_submission_packages"
    __table_args__ = (
        Index("ix_submission_packages_dossier_created", "dossier_id", "created_at"),
        Index("ix_submission_packages_status_created", "status", "created_at"),
        Index("ix_submission_packages_type_status", "package_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    package_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    file_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    package_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationProjectORM(Base):
    __tablename__ = "validation_projects"
    __table_args__ = (
        Index("ix_validation_projects_scope_status", "scope", "status"),
        Index("ix_validation_projects_type_status", "validation_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    scope: Mapped[str] = mapped_column(String(64), index=True)
    validation_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    intended_use: Mapped[str] = mapped_column(Text)
    regulated_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    qa_reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class UserRequirementSpecificationORM(Base):
    __tablename__ = "user_requirement_specifications"
    __table_args__ = (
        Index("ix_urs_project_status", "validation_project_id", "status"),
        Index("ix_urs_module_criticality", "module", "criticality"),
        UniqueConstraint(
            "validation_project_id",
            "requirement_code",
            name="uq_urs_project_requirement_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_project_id: Mapped[int] = mapped_column(
        ForeignKey("validation_projects.id", ondelete="CASCADE"),
        index=True,
    )
    requirement_code: Mapped[str] = mapped_column(String(100), index=True)
    module: Mapped[str] = mapped_column(String(64), index=True)
    requirement_text: Mapped[str] = mapped_column(Text)
    criticality: Mapped[str] = mapped_column(String(32), index=True)
    gxp_impact: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class FunctionalSpecificationORM(Base):
    __tablename__ = "functional_specifications"
    __table_args__ = (
        Index("ix_functional_specs_project_status", "validation_project_id", "status"),
        Index("ix_functional_specs_requirement", "requirement_id"),
        UniqueConstraint(
            "validation_project_id",
            "function_code",
            name="uq_functional_specs_project_function_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_project_id: Mapped[int] = mapped_column(
        ForeignKey("validation_projects.id", ondelete="CASCADE"),
        index=True,
    )
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_requirement_specifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    function_code: Mapped[str] = mapped_column(String(100), index=True)
    function_name: Mapped[str] = mapped_column(String(240))
    function_description: Mapped[str] = mapped_column(Text)
    expected_behavior: Mapped[str] = mapped_column(Text)
    module: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationRiskAssessmentORM(Base):
    __tablename__ = "validation_risk_assessments"
    __table_args__ = (
        Index("ix_validation_risks_project_status", "validation_project_id", "status"),
        Index("ix_validation_risks_target", "target_type", "target_id"),
        Index("ix_validation_risks_severity", "severity", "probability", "detectability"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_project_id: Mapped[int] = mapped_column(
        ForeignKey("validation_projects.id", ondelete="CASCADE"),
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    risk_description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    probability: Mapped[str] = mapped_column(String(32), index=True)
    detectability: Mapped[str] = mapped_column(String(32), index=True)
    risk_priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mitigation: Mapped[str] = mapped_column(Text)
    testing_rigor: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationTestProtocolORM(Base):
    __tablename__ = "validation_test_protocols"
    __table_args__ = (
        Index("ix_validation_protocols_project_status", "validation_project_id", "status"),
        Index("ix_validation_protocols_module_type", "module", "protocol_type"),
        UniqueConstraint(
            "validation_project_id",
            "protocol_code",
            name="uq_validation_protocol_project_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_project_id: Mapped[int] = mapped_column(
        ForeignKey("validation_projects.id", ondelete="CASCADE"),
        index=True,
    )
    protocol_code: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    module: Mapped[str] = mapped_column(String(64), index=True)
    protocol_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationTestCaseORM(Base):
    __tablename__ = "validation_test_cases"
    __table_args__ = (
        Index("ix_validation_test_cases_protocol_status", "protocol_id", "status"),
        UniqueConstraint("protocol_id", "test_case_code", name="uq_validation_test_case_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("validation_test_protocols.id", ondelete="CASCADE"),
        index=True,
    )
    test_case_code: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    preconditions: Mapped[str] = mapped_column(Text)
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    expected_results: Mapped[str] = mapped_column(Text)
    linked_requirement_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    linked_risk_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ValidationTestExecutionORM(Base):
    __tablename__ = "validation_test_executions"
    __table_args__ = (
        Index("ix_validation_executions_test_case_status", "test_case_id", "execution_status"),
        Index("ix_validation_executions_executed", "executed_at"),
        Index("ix_validation_executions_deviation", "deviation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("validation_test_cases.id", ondelete="CASCADE"),
        index=True,
    )
    executed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    execution_status: Mapped[str] = mapped_column(String(32), index=True)
    actual_results: Mapped[str] = mapped_column(Text)
    evidence_file_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_artifact_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    deviation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TraceabilityMatrixORM(Base):
    __tablename__ = "traceability_matrices"
    __table_args__ = (
        Index("ix_traceability_project_status", "validation_project_id", "status"),
        Index("ix_traceability_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_project_id: Mapped[int] = mapped_column(
        ForeignKey("validation_projects.id", ondelete="CASCADE"),
        index=True,
    )
    matrix_json: Mapped[str] = mapped_column(Text, default="{}")
    coverage_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    missing_coverage_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ElectronicSignatureRecordORM(Base):
    __tablename__ = "electronic_signature_records"
    __table_args__ = (
        Index("ix_esignatures_target", "target_type", "target_id"),
        Index("ix_esignatures_signer_signed", "signer_email", "signed_at"),
        Index("ix_esignatures_meaning_signed", "signature_meaning", "signed_at"),
        Index("ix_esignatures_signer_user", "signer_user_id"),
        Index("ix_esignatures_record_content", "target_type", "target_id", "record_content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signer_name: Mapped[str] = mapped_column(String(200))
    signer_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    signature_meaning: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(100), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    reason: Mapped[str] = mapped_column(Text)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    authentication_method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    signature_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    # --- 21 CFR Part 11 binding (Security Prompt 11). All nullable/additive: legacy rows predate
    #     content binding and verify as "unbound" (honest), never as tampered. ---
    # §11.100 attribution — the authenticated server principal, never the client-supplied name.
    signer_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # §11.70 record linking — SHA-256 ("sha256:"+64) of the exact signed record snapshot; binding
    # this into the digest makes the signature non-transferable to a different record/version.
    record_content_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    # Content-bound signature digest ("sha256:"+64). The legacy String(64) signature_hash is kept
    # unchanged for back-compat with existing rows and the exactly-64 response-model contract.
    signature_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)


class ControlledRecordORM(Base):
    __tablename__ = "controlled_records"
    __table_args__ = (
        Index("ix_controlled_records_type_status", "record_type", "status"),
        Index("ix_controlled_records_resource", "record_type", "resource_id"),
        Index("ix_controlled_records_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    version: Mapped[str] = mapped_column(String(64), default="1")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    retention_policy_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RecordRetentionPolicyORM(Base):
    __tablename__ = "record_retention_policies"
    __table_args__ = (
        Index("ix_retention_policies_type_status", "record_type", "status"),
        UniqueConstraint("name", "record_type", name="uq_retention_policy_name_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(240))
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    retention_period_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archive_strategy: Mapped[str] = mapped_column(Text)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DataIntegrityAssessmentORM(Base):
    __tablename__ = "data_integrity_assessments"
    __table_args__ = (
        Index("ix_data_integrity_scope_status", "scope", "assessment_status"),
        Index("ix_data_integrity_scope_id", "scope", "scope_id"),
        Index("ix_data_integrity_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    assessment_status: Mapped[str] = mapped_column(String(32), index=True)
    attributable_status: Mapped[str] = mapped_column(String(32))
    legible_status: Mapped[str] = mapped_column(String(32))
    contemporaneous_status: Mapped[str] = mapped_column(String(32))
    original_status: Mapped[str] = mapped_column(String(32))
    accurate_status: Mapped[str] = mapped_column(String(32))
    complete_status: Mapped[str] = mapped_column(String(32))
    consistent_status: Mapped[str] = mapped_column(String(32))
    enduring_status: Mapped[str] = mapped_column(String(32))
    available_status: Mapped[str] = mapped_column(String(32))
    findings_json: Mapped[str] = mapped_column(Text, default="[]")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class InspectionReadinessPackageORM(Base):
    __tablename__ = "inspection_readiness_packages"
    __table_args__ = (
        Index("ix_inspection_packages_scope_status", "scope", "package_status"),
        Index("ix_inspection_packages_created", "created_at"),
        Index("ix_inspection_packages_sha", "package_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    scope: Mapped[str] = mapped_column(String(64), index=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    package_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    included_record_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    included_signature_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    included_audit_event_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    included_validation_project_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    package_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SystemReleaseRecordORM(Base):
    __tablename__ = "system_release_records"
    __table_args__ = (
        Index("ix_system_releases_version", "release_version"),
        Index("ix_system_releases_type_status", "release_type", "approval_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_version: Mapped[str] = mapped_column(String(120), index=True)
    release_type: Mapped[str] = mapped_column(String(64), index=True)
    change_summary: Mapped[str] = mapped_column(Text)
    validation_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    risk_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    approval_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DeviationRecordORM(Base):
    __tablename__ = "deviation_records"
    __table_args__ = (
        UniqueConstraint("deviation_code", name="uq_deviation_code"),
        Index("ix_deviations_status_severity", "status", "severity"),
        Index("ix_deviations_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deviation_code: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CAPARecordORM(Base):
    __tablename__ = "capa_records"
    __table_args__ = (
        UniqueConstraint("capa_code", name="uq_capa_code"),
        Index("ix_capa_status_due", "status", "due_date"),
        Index("ix_capa_deviation", "source_deviation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capa_code: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    source_deviation_id: Mapped[int | None] = mapped_column(
        ForeignKey("deviation_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    corrective_action: Mapped[str] = mapped_column(Text)
    preventive_action: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantORM(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("tenant_key", name="uq_tenants_key"),
        Index("ix_tenants_type_status", "tenant_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_key: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    tenant_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(32), default="onboarding", index=True)
    primary_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantEnvironmentORM(Base):
    __tablename__ = "tenant_environments"
    __table_args__ = (
        Index("ix_tenant_environments_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_environments_type_status", "environment_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    environment_type: Mapped[str] = mapped_column(String(32), index=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    data_retention_policy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SubscriptionPlanORM(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (
        UniqueConstraint("plan_key", name="uq_subscription_plans_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_key: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    default_entitlements_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantEntitlementORM(Base):
    __tablename__ = "tenant_entitlements"
    __table_args__ = (
        Index("ix_tenant_entitlements_tenant_program", "tenant_id", "program"),
        Index("ix_tenant_entitlements_feature", "feature_key", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    feature_key: Mapped[str] = mapped_column(String(160), index=True)
    program: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    limit_json: Mapped[str] = mapped_column(Text, default="{}")
    effective_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class FeatureFlagORM(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("flag_key", name="uq_feature_flags_key"),
        Index("ix_feature_flags_program_status", "program", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flag_key: Mapped[str] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    program: Mapped[str] = mapped_column(String(64), index=True)
    default_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    rollout_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotProgramORM(Base):
    __tablename__ = "pilot_programs"
    __table_args__ = (
        Index("ix_pilot_programs_tenant_status", "tenant_id", "status"),
        Index("ix_pilot_programs_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_programs_json: Mapped[str] = mapped_column(Text, default="[]")
    success_criteria_json: Mapped[str] = mapped_column(Text, default="[]")
    risks_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CustomerOnboardingProjectORM(Base):
    __tablename__ = "customer_onboarding_projects"
    __table_args__ = (
        Index("ix_onboarding_projects_tenant_status", "tenant_id", "status"),
        Index("ix_onboarding_projects_stage", "implementation_stage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    pilot_program_id: Mapped[int | None] = mapped_column(
        ForeignKey("pilot_programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    implementation_stage: Mapped[str] = mapped_column(String(64), default="discovery", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ImplementationTaskORM(Base):
    __tablename__ = "implementation_tasks"
    __table_args__ = (
        Index("ix_implementation_tasks_project_status", "onboarding_project_id", "status"),
        Index("ix_implementation_tasks_program_status", "program", "status"),
        Index("ix_implementation_tasks_due", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    onboarding_project_id: Mapped[int] = mapped_column(
        ForeignKey("customer_onboarding_projects.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    program: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantDataBoundaryORM(Base):
    __tablename__ = "tenant_data_boundaries"
    __table_args__ = (
        Index("ix_tenant_data_boundaries_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_data_boundaries_isolation", "isolation_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    isolation_mode: Mapped[str] = mapped_column(String(64), index=True)
    encryption_profile: Mapped[str | None] = mapped_column(String(160), nullable=True)
    storage_prefix: Mapped[str | None] = mapped_column(String(300), nullable=True)
    allowed_regions_json: Mapped[str] = mapped_column(Text, default="[]")
    data_residency_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantSecurityProfileORM(Base):
    __tablename__ = "tenant_security_profiles"
    __table_args__ = (
        Index("ix_tenant_security_profiles_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    sso_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_domains_json: Mapped[str] = mapped_column(Text, default="[]")
    session_timeout_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_allowlist_json: Mapped[str] = mapped_column(Text, default="[]")
    security_frameworks_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantValidationProfileORM(Base):
    __tablename__ = "tenant_validation_profiles"
    __table_args__ = (
        Index("ix_tenant_validation_profiles_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    validation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_project_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    controlled_record_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    esignature_required: Mapped[bool] = mapped_column(Boolean, default=False)
    data_integrity_assessment_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    inspection_package_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CustomerSuccessHealthScoreORM(Base):
    __tablename__ = "customer_success_health_scores"
    __table_args__ = (
        Index("ix_customer_health_tenant_created", "tenant_id", "created_at"),
        Index("ix_customer_health_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    usage_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    onboarding_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    support_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    roi_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    blockers_json: Mapped[str] = mapped_column(Text, default="[]")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantUsageSummaryORM(Base):
    __tablename__ = "tenant_usage_summaries"
    __table_args__ = (
        Index("ix_tenant_usage_tenant_period", "tenant_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    spectracheck_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    regulatory_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    reaction_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    reports_generated: Mapped[int] = mapped_column(Integer, default=0)
    actions_completed: Mapped[int] = mapped_column(Integer, default=0)
    hours_saved: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantRoiSnapshotORM(Base):
    __tablename__ = "tenant_roi_snapshots"
    __table_args__ = (
        Index("ix_tenant_roi_tenant_period", "tenant_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total_hours_saved: Mapped[float] = mapped_column(Float, default=0.0)
    tasks_automated: Mapped[int] = mapped_column(Integer, default=0)
    reports_generated: Mapped[int] = mapped_column(Integer, default=0)
    regulatory_actions_created: Mapped[int] = mapped_column(Integer, default=0)
    reaction_recommendations_approved: Mapped[int] = mapped_column(Integer, default=0)
    renewal_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ProcurementEvidencePackageORM(Base):
    __tablename__ = "procurement_evidence_packages"
    __table_args__ = (
        Index("ix_procurement_packages_tenant_status", "tenant_id", "status"),
        Index("ix_procurement_packages_type", "package_type"),
        Index("ix_procurement_packages_sha", "package_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    package_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    package_json: Mapped[str] = mapped_column(Text, default="{}")
    package_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TenantAuditExportORM(Base):
    __tablename__ = "tenant_audit_exports"
    __table_args__ = (
        Index("ix_tenant_audit_exports_tenant_scope", "tenant_id", "export_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    export_scope: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    export_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class GoldenDatasetORM(Base):
    __tablename__ = "golden_datasets"
    __table_args__ = (
        UniqueConstraint("dataset_key", name="uq_golden_datasets_key"),
        Index("ix_golden_datasets_type_status", "dataset_type", "status"),
        Index("ix_golden_datasets_source", "source_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_key: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    dataset_type: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    source_references_json: Mapped[str] = mapped_column(Text, default="[]")
    file_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class GoldenPilotScenarioORM(Base):
    __tablename__ = "golden_pilot_scenarios"
    __table_args__ = (
        UniqueConstraint("scenario_key", name="uq_golden_pilot_scenarios_key"),
        Index("ix_golden_scenarios_type_status", "scenario_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_key: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    scenario_type: Mapped[str] = mapped_column(String(80), index=True)
    program_sequence_json: Mapped[str] = mapped_column(Text, default="[]")
    dataset_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    required_inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    expected_outputs_json: Mapped[str] = mapped_column(Text, default="{}")
    acceptance_criteria_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class GoldenWorkflowCaseORM(Base):
    __tablename__ = "golden_workflow_cases"
    __table_args__ = (
        Index("ix_golden_workflow_cases_scenario_status", "scenario_id", "status"),
        Index("ix_golden_workflow_cases_key", "case_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("golden_pilot_scenarios.id", ondelete="CASCADE"),
        index=True,
    )
    case_key: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(300))
    input_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    expected_step_order_json: Mapped[str] = mapped_column(Text, default="[]")
    expected_resource_links_json: Mapped[str] = mapped_column(Text, default="[]")
    expected_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExpectedOutputContractORM(Base):
    __tablename__ = "expected_output_contracts"
    __table_args__ = (
        Index("ix_expected_contracts_scenario_module", "scenario_id", "target_module"),
        Index("ix_expected_contracts_step", "step_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("golden_pilot_scenarios.id", ondelete="CASCADE"),
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(160), index=True)
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    expected_output_type: Mapped[str] = mapped_column(String(80), index=True)
    required_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    forbidden_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    expected_statuses_json: Mapped[str] = mapped_column(Text, default="[]")
    tolerance_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotRunORM(Base):
    __tablename__ = "pilot_runs"
    __table_args__ = (
        Index("ix_pilot_runs_scenario_status", "scenario_id", "status"),
        Index("ix_pilot_runs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("golden_pilot_scenarios.id", ondelete="CASCADE"),
        index=True,
    )
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sample_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_label: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotRunStepORM(Base):
    __tablename__ = "pilot_run_steps"
    __table_args__ = (
        Index("ix_pilot_run_steps_run_module", "pilot_run_id", "module"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pilot_run_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_runs.id", ondelete="CASCADE"),
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(160), index=True)
    module: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    input_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    output_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    linked_resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    linked_resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ScenarioValidationResultORM(Base):
    __tablename__ = "scenario_validation_results"
    __table_args__ = (
        Index("ix_scenario_validation_run_status", "pilot_run_id", "validation_status"),
        Index("ix_scenario_validation_contract", "contract_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pilot_run_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_runs.id", ondelete="CASCADE"),
        index=True,
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("golden_pilot_scenarios.id", ondelete="CASCADE"),
        index=True,
    )
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("expected_output_contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    validation_status: Mapped[str] = mapped_column(String(32), default="not_assessed", index=True)
    expected_json: Mapped[str] = mapped_column(Text, default="{}")
    actual_json: Mapped[str] = mapped_column(Text, default="{}")
    differences_json: Mapped[str] = mapped_column(Text, default="{}")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CustomerAcceptanceProtocolORM(Base):
    __tablename__ = "customer_acceptance_protocols"
    __table_args__ = (
        Index("ix_customer_acceptance_tenant_status", "tenant_id", "status"),
        Index("ix_customer_acceptance_scope", "scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pilot_program_id: Mapped[int | None] = mapped_column(
        ForeignKey("pilot_programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    scope: Mapped[str] = mapped_column(String(64), index=True)
    scenario_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    acceptance_tests_json: Mapped[str] = mapped_column(Text, default="[]")
    success_criteria_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CustomerAcceptanceTestORM(Base):
    __tablename__ = "customer_acceptance_tests"
    __table_args__ = (
        Index("ix_customer_acceptance_tests_protocol_status", "protocol_id", "status"),
        Index("ix_customer_acceptance_tests_scenario", "scenario_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("customer_acceptance_protocols.id", ondelete="CASCADE"),
        index=True,
    )
    test_key: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("golden_pilot_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expected_result: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="not_run", index=True)
    executed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotSuccessMetricORM(Base):
    __tablename__ = "pilot_success_metrics"
    __table_args__ = (
        Index("ix_pilot_success_metrics_run", "pilot_run_id"),
        Index("ix_pilot_success_metrics_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pilot_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("pilot_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metric_key: Mapped[str] = mapped_column(String(160), index=True)
    metric_name: Mapped[str] = mapped_column(String(240))
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="not_assessed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotReadinessAssessmentORM(Base):
    __tablename__ = "pilot_readiness_assessments"
    __table_args__ = (
        Index("ix_pilot_readiness_tenant_created", "tenant_id", "created_at"),
        Index("ix_pilot_readiness_status", "readiness_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pilot_program_id: Mapped[int | None] = mapped_column(
        ForeignKey("pilot_programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    onboarding_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_onboarding_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    readiness_status: Mapped[str] = mapped_column(String(40), default="partially_ready", index=True)
    spectracheck_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    regulatory_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    reaction_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    connector_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    mobile_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    security_readiness_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotSignoffRecordORM(Base):
    __tablename__ = "pilot_signoff_records"
    __table_args__ = (
        Index("ix_pilot_signoffs_tenant", "tenant_id"),
        Index("ix_pilot_signoffs_run", "pilot_run_id"),
        Index("ix_pilot_signoffs_protocol", "protocol_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pilot_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("pilot_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    protocol_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_acceptance_protocols.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signer_name: Mapped[str] = mapped_column(String(200))
    signer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision: Mapped[str] = mapped_column(String(40), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    signature_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DemoTenantSeedORM(Base):
    __tablename__ = "demo_tenant_seeds"
    __table_args__ = (
        Index("ix_demo_tenant_seeds_tenant_status", "tenant_id", "status"),
        Index("ix_demo_tenant_seeds_scenario", "scenario_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("golden_pilot_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    seed_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    created_resource_ids_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PilotEvidenceBundleORM(Base):
    __tablename__ = "pilot_evidence_bundles"
    __table_args__ = (
        Index("ix_pilot_evidence_bundles_run_status", "pilot_run_id", "status"),
        Index("ix_pilot_evidence_bundles_sha", "package_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pilot_run_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_runs.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    included_resource_ids_json: Mapped[str] = mapped_column(Text, default="{}")
    package_json: Mapped[str] = mapped_column(Text, default="{}")
    package_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class QualityFindingORM(Base):
    __tablename__ = "quality_findings"
    __table_args__ = (
        Index("ix_quality_findings_target_created", "target_type", "target_id", "created_at"),
        Index("ix_quality_findings_severity_created", "severity", "created_at"),
        Index("ix_quality_findings_code_created", "code", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class QualityAssessmentORM(Base):
    __tablename__ = "quality_assessments"
    __table_args__ = (
        Index("ix_quality_assessments_target_created", "target_type", "target_id", "created_at"),
        Index("ix_quality_assessments_status_created", "qc_status", "created_at"),
        Index("ix_quality_assessments_readiness_created", "readiness_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    modality: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qc_status: Mapped[str] = mapped_column(String(32), default="not_assessed", index=True)
    readiness_status: Mapped[str] = mapped_column(String(64), default="not_ready", index=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    findings_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    override_status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class QualityOverrideORM(Base):
    __tablename__ = "quality_overrides"
    __table_args__ = (
        Index("ix_quality_overrides_assessment_created", "assessment_id", "created_at"),
        Index("ix_quality_overrides_decision_created", "decision", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("quality_assessments.id", ondelete="CASCADE"), index=True
    )
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WorkflowTemplateORM(Base):
    __tablename__ = "workflow_templates"
    __table_args__ = (
        Index("ix_workflow_templates_category_updated", "category", "updated_at"),
        UniqueConstraint("slug", name="uq_workflow_templates_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    required_inputs_json: Mapped[str] = mapped_column(Text, default="[]")
    optional_inputs_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WorkflowRunORM(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_session_created", "session_id", "created_at"),
        Index("ix_workflow_runs_status_created", "status", "created_at"),
        Index("ix_workflow_runs_template_created", "template_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    current_step_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    outputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WorkflowRunStepORM(Base):
    __tablename__ = "workflow_run_steps"
    __table_args__ = (
        Index("ix_workflow_steps_run_created", "workflow_run_id", "created_at"),
        Index("ix_workflow_steps_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(100), index=True)
    step_name: Mapped[str] = mapped_column(String(200))
    step_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WorkflowRunEventORM(Base):
    __tablename__ = "workflow_run_events"
    __table_args__ = (
        Index("ix_workflow_events_run_created", "workflow_run_id", "created_at"),
        Index("ix_workflow_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WorkflowRunArtifactORM(Base):
    __tablename__ = "workflow_run_artifacts"
    __table_args__ = (
        Index("ix_workflow_artifacts_run_created", "workflow_run_id", "created_at"),
        Index("ix_workflow_artifacts_type_created", "artifact_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifact_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_evidence_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    artifact_type: Mapped[str] = mapped_column(String(100), index=True)
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scoring_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("scoring_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    threshold_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReportORM(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_analysis_created", "analysis_id", "created_at"),
        Index("ix_reports_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255))
    report_json: Mapped[str] = mapped_column(Text)

    analysis: Mapped[AnalysisORM] = relationship(back_populates="reports")


class ReviewDecisionORM(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        Index("ix_review_decisions_analysis_created", "analysis_id", "created_at"),
        Index("ix_review_decisions_reviewer_created", "reviewer_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    reviewer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(32), index=True)
    previous_status: Mapped[str] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis: Mapped[AnalysisORM] = relationship(back_populates="review_decisions")
    reviewer: Mapped[UserORM] = relationship(back_populates="review_decisions")


class FIDRunORM(Base):
    __tablename__ = "fid_runs"
    __table_args__ = (
        Index("ix_fid_runs_user_created", "user_id", "created_at"),
        Index("ix_fid_runs_review_status_created", "review_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_archive_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_archives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    raw_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    selected_preset: Mapped[str] = mapped_column(String(100))
    quality_label: Mapped[str] = mapped_column(String(32))
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review")
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_json: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)
    processing_recipe_json: Mapped[str] = mapped_column(Text, default="{}")
    derived_spectrum_metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    analysis: Mapped[AnalysisORM | None] = relationship(back_populates="fid_runs")
    raw_archive: Mapped[RawArchiveORM | None] = relationship(back_populates="fid_runs")
    decisions: Mapped[list[FIDRunReviewDecisionORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class FIDRunReviewDecisionORM(Base):
    __tablename__ = "fid_run_review_decisions"
    __table_args__ = (
        Index("ix_fid_run_decisions_run_created", "run_id", "created_at"),
        Index("ix_fid_run_decisions_reviewer_created", "reviewer_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("fid_runs.id", ondelete="CASCADE"), index=True)
    reviewer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(32), index=True)
    previous_status: Mapped[str] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[FIDRunORM] = relationship(back_populates="decisions")


class RawArchiveORM(Base):
    __tablename__ = "raw_archives"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_raw_archives_sha256"),
        Index("ix_raw_archives_user_created", "user_id", "created_at"),
        Index("ix_raw_archives_vendor_created", "vendor_detected", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(Text)
    vendor_detected: Mapped[str] = mapped_column(String(100), index=True)
    dataset_root: Mapped[str | None] = mapped_column(String(500), nullable=True)
    required_files_present: Mapped[bool] = mapped_column(Boolean, default=False)
    files_found_json: Mapped[str] = mapped_column(Text, default="[]")
    acquisition_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[UserORM | None] = relationship(back_populates="raw_archives")
    fid_runs: Mapped[list[FIDRunORM]] = relationship(back_populates="raw_archive")


class NMR2DRunORM(Base):
    __tablename__ = "nmr2d_runs"
    __table_args__ = (
        Index("ix_nmr2d_runs_user_created", "user_id", "created_at"),
        Index("ix_nmr2d_runs_analysis_created", "analysis_id", "created_at"),
        Index("ix_nmr2d_runs_review_status_created", "review_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sample_pk: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    experiment_detected: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    source_filename: Mapped[str] = mapped_column(String(255))
    experiment_types_json: Mapped[str] = mapped_column(Text, default="[]")
    peak_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    suspicious_peak_count: Mapped[int] = mapped_column(Integer, default=0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review")
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    peaks_json: Mapped[str] = mapped_column(Text, default="[]")
    report_json: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    user: Mapped[UserORM | None] = relationship(back_populates="nmr2d_runs")
    analysis: Mapped[AnalysisORM | None] = relationship(back_populates="nmr2d_runs")


class SecurityEventORM(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_type_created", "event_type", "created_at"),
        Index("ix_security_events_severity_created", "severity", "created_at"),
        Index("ix_security_events_actor_created", "actor_email", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DebugBundleORM(Base):
    __tablename__ = "debug_bundles"
    __table_args__ = (
        Index("ix_debug_bundles_scope_created", "scope", "created_at"),
        Index("ix_debug_bundles_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    scope: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    bundle_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    bundle_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class UsageEventORM(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_type_created", "event_type", "created_at"),
        Index("ix_usage_events_project_created", "project_id", "created_at"),
        Index("ix_usage_events_session_created", "session_id", "created_at"),
        Index("ix_usage_events_user_created", "user_email", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sample_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    artifact_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    report_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_minutes_saved: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_source: Mapped[str] = mapped_column(String(32), default="backend", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AutomationTaskDefinitionORM(Base):
    __tablename__ = "automation_task_definitions"
    __table_args__ = (
        UniqueConstraint("task_key", name="uq_automation_task_definitions_task_key"),
        Index("ix_automation_task_definitions_category_enabled", "category", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(32), index=True)
    default_minutes_saved: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AutomationRunMetricORM(Base):
    __tablename__ = "automation_run_metrics"
    __table_args__ = (
        Index("ix_automation_run_metrics_task_created", "task_key", "created_at"),
        Index("ix_automation_run_metrics_project_created", "project_id", "created_at"),
        Index("ix_automation_run_metrics_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="succeeded", index=True)
    minutes_saved: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RoiSnapshotORM(Base):
    __tablename__ = "roi_snapshots"
    __table_args__ = (
        Index("ix_roi_snapshots_scope_period", "scope", "scope_id", "period_start", "period_end"),
        Index("ix_roi_snapshots_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tasks_automated: Mapped[int] = mapped_column(Integer, default=0)
    total_minutes_saved: Mapped[float] = mapped_column(Float, default=0.0)
    total_hours_saved: Mapped[float] = mapped_column(Float, default=0.0)
    reports_generated: Mapped[int] = mapped_column(Integer, default=0)
    workflows_completed: Mapped[int] = mapped_column(Integer, default=0)
    analyses_completed: Mapped[int] = mapped_column(Integer, default=0)
    review_tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    qc_warnings: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserFeedbackEventORM(Base):
    __tablename__ = "user_feedback_events"
    __table_args__ = (
        Index("ix_user_feedback_events_type_created", "feedback_type", "created_at"),
        Index("ix_user_feedback_events_project_created", "project_id", "created_at"),
        Index("ix_user_feedback_events_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(32), index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RenewalValueReportORM(Base):
    __tablename__ = "renewal_value_reports"
    __table_args__ = (
        Index("ix_renewal_value_reports_scope_created", "scope", "scope_id", "created_at"),
        Index("ix_renewal_value_reports_sha", "report_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    report_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionProjectORM(Base):
    __tablename__ = "reaction_projects"
    __table_args__ = (
        Index("ix_reaction_projects_status_updated", "status", "updated_at"),
        Index("ix_reaction_projects_owner_updated", "owner_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    target_product_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    target_product_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionVariableORM(Base):
    __tablename__ = "reaction_variables"
    __table_args__ = (
        Index("ix_reaction_variables_project_created", "reaction_project_id", "created_at"),
        UniqueConstraint(
            "reaction_project_id",
            "name",
            name="uq_reaction_variables_project_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160))
    variable_type: Mapped[str] = mapped_column(String(32), index=True)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    allowed_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionExperimentORM(Base):
    __tablename__ = "reaction_experiments"
    __table_args__ = (
        UniqueConstraint(
            "reaction_project_id",
            "experiment_code",
            name="uq_reaction_experiments_project_code",
        ),
        Index("ix_reaction_experiments_project_status", "reaction_project_id", "status"),
        Index("ix_reaction_experiments_spectracheck", "linked_spectracheck_session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_code: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome_json: Mapped[str] = mapped_column(Text, default="{}")
    linked_spectracheck_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionOptimizationRunORM(Base):
    __tablename__ = "reaction_optimization_runs"
    __table_args__ = (
        Index("ix_reaction_optimization_runs_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_optimization_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    model_type: Mapped[str] = mapped_column(String(64), default="rule_based", index=True)
    objective: Mapped[str] = mapped_column(String(40), index=True)
    input_experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    recommendations_json: Mapped[str] = mapped_column(Text, default="[]")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionRecommendationORM(Base):
    __tablename__ = "reaction_recommendations"
    __table_args__ = (
        Index("ix_reaction_recommendations_project_rank", "reaction_project_id", "rank"),
        Index("ix_reaction_recommendations_run_rank", "optimization_run_id", "rank"),
        Index("ix_reaction_recommendations_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    optimization_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, default=1)
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    predicted_outcome_json: Mapped[str] = mapped_column(Text, default="{}")
    uncertainty_json: Mapped[str] = mapped_column(Text, default="{}")
    rationale: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionDesignSpaceORM(Base):
    __tablename__ = "reaction_design_spaces"
    __table_args__ = (
        Index("ix_reaction_design_spaces_project_updated", "reaction_project_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    variables_json: Mapped[str] = mapped_column(Text, default="{}")
    categorical_variables_json: Mapped[str] = mapped_column(Text, default="{}")
    numeric_variables_json: Mapped[str] = mapped_column(Text, default="{}")
    boolean_variables_json: Mapped[str] = mapped_column(Text, default="{}")
    fixed_conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    excluded_conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionObjectiveProfileORM(Base):
    __tablename__ = "reaction_objective_profiles"
    __table_args__ = (
        Index(
            "ix_reaction_objective_profiles_project_updated", "reaction_project_id", "updated_at"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    objective_type: Mapped[str] = mapped_column(String(40), index=True)
    weights_json: Mapped[str] = mapped_column(Text, default="{}")
    target_thresholds_json: Mapped[str] = mapped_column(Text, default="{}")
    hard_constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    soft_constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionCostProfileORM(Base):
    __tablename__ = "reaction_cost_profiles"
    __table_args__ = (
        Index("ix_reaction_cost_profiles_project_updated", "reaction_project_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    reagent_costs_json: Mapped[str] = mapped_column(Text, default="{}")
    solvent_costs_json: Mapped[str] = mapped_column(Text, default="{}")
    catalyst_costs_json: Mapped[str] = mapped_column(Text, default="{}")
    ligand_costs_json: Mapped[str] = mapped_column(Text, default="{}")
    availability_json: Mapped[str] = mapped_column(Text, default="{}")
    max_cost_per_experiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_penalty_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionSafetyConstraintProfileORM(Base):
    __tablename__ = "reaction_safety_constraint_profiles"
    __table_args__ = (
        Index("ix_reaction_safety_profiles_project_updated", "reaction_project_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    blocked_reagents_json: Mapped[str] = mapped_column(Text, default="[]")
    blocked_solvents_json: Mapped[str] = mapped_column(Text, default="[]")
    max_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_pressure_bar: Mapped[float | None] = mapped_column(Float, nullable=True)
    incompatible_pairs_json: Mapped[str] = mapped_column(Text, default="[]")
    required_controls_json: Mapped[str] = mapped_column(Text, default="[]")
    safety_notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionGreenProfileORM(Base):
    __tablename__ = "reaction_green_profiles"
    __table_args__ = (
        Index("ix_reaction_green_profiles_project_updated", "reaction_project_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    solvent_greenness_json: Mapped[str] = mapped_column(Text, default="{}")
    default_assumptions_json: Mapped[str] = mapped_column(Text, default="{}")
    solvent_table_version: Mapped[str] = mapped_column(String(64), default="chem21-2016")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionGreenAssessmentORM(Base):
    __tablename__ = "reaction_green_assessments"
    __table_args__ = (
        Index(
            "ix_reaction_green_assessments_experiment_created",
            "reaction_experiment_id",
            "created_at",
        ),
        Index(
            "ix_reaction_green_assessments_project_created",
            "reaction_project_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_experiment_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_experiments.id", ondelete="CASCADE"),
        index=True,
    )
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionPlateDesignORM(Base):
    __tablename__ = "reaction_plate_designs"
    __table_args__ = (
        Index("ix_reaction_plate_designs_project_created", "reaction_project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    plate_format: Mapped[str] = mapped_column(String(8), default="96")
    strategy: Mapped[str] = mapped_column(String(32), default="sobol")
    well_count: Mapped[int] = mapped_column(Integer, default=0)
    design_json: Mapped[str] = mapped_column(Text, default="{}")
    inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionSafetyScreeningORM(Base):
    """A persisted structural process-safety screening (R6) + its expert-review state.

    Distinct from ``ReactionSafetyConstraintProfileORM`` (manual operating constraints):
    this is the deterministic RDKit-SMARTS energetic-group screen, retained with a
    human-in-the-loop review verdict so a flagged structure can be gated before execution.
    """

    __tablename__ = "reaction_safety_screenings"
    __table_args__ = (
        Index(
            "ix_reaction_safety_screenings_project_created",
            "reaction_project_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    label: Mapped[str] = mapped_column(String(200), default="")
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    overall_risk: Mapped[str] = mapped_column(String(16), default="unknown")
    requires_expert_review: Mapped[bool] = mapped_column(Boolean, default=True)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionBayesianOptimizationRunORM(Base):
    __tablename__ = "reaction_bayesian_optimization_runs"
    __table_args__ = (
        Index("ix_reaction_bo_runs_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_bo_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    algorithm: Mapped[str] = mapped_column(String(64), index=True)
    batch_size: Mapped[int] = mapped_column(Integer, default=5)
    exploration_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_aware: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_aware: Mapped[bool] = mapped_column(Boolean, default=True)
    input_experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    recommendations_json: Mapped[str] = mapped_column(Text, default="[]")
    diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionSurrogateModelRecordORM(Base):
    __tablename__ = "reaction_surrogate_model_records"
    __table_args__ = (
        Index("ix_reaction_surrogate_models_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_surrogate_models_bo_run", "bo_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    bo_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_bayesian_optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_type: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    training_experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    feature_encoding_json: Mapped[str] = mapped_column(Text, default="{}")
    objective_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionAcquisitionCandidateORM(Base):
    __tablename__ = "reaction_acquisition_candidates"
    __table_args__ = (
        Index("ix_reaction_acquisition_candidates_run_rank", "bo_run_id", "rank"),
        Index("ix_reaction_acquisition_candidates_safety", "safety_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bo_run_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_bayesian_optimization_runs.id", ondelete="CASCADE"),
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, default=1)
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    predicted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_improvement: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    acquisition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionRecommendationBatchORM(Base):
    __tablename__ = "reaction_recommendation_batches"
    __table_args__ = (
        Index(
            "ix_reaction_recommendation_batches_project_created",
            "reaction_project_id",
            "created_at",
        ),
        Index("ix_reaction_recommendation_batches_bo_run", "bo_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    bo_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_bayesian_optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    recommendations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionOptimizationBenchmarkRunORM(Base):
    __tablename__ = "reaction_optimization_benchmark_runs"
    __table_args__ = (
        Index("ix_reaction_benchmark_runs_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_benchmark_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    benchmark_name: Mapped[str] = mapped_column(String(200))
    algorithm: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    trajectory_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionOptimizationAdvisorRunORM(Base):
    __tablename__ = "reaction_optimization_advisor_runs"
    __table_args__ = (
        Index("ix_reaction_advisor_runs_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_advisor_runs_bo_run", "bo_run_id"),
        Index("ix_reaction_advisor_runs_batch", "recommendation_batch_id"),
        Index("ix_reaction_advisor_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    bo_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_bayesian_optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommendation_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_recommendation_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    advisor_mode: Mapped[str] = mapped_column(
        String(64), default="rule_based_mechanistic", index=True
    )
    input_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    advisor_output_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionMechanisticHypothesisORM(Base):
    __tablename__ = "reaction_mechanistic_hypotheses"
    __table_args__ = (
        Index(
            "ix_reaction_mechanistic_hypotheses_project_created",
            "reaction_project_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240))
    hypothesis: Mapped[str] = mapped_column(Text)
    supporting_observations_json: Mapped[str] = mapped_column(Text, default="[]")
    contradicting_observations_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence_label: Mapped[str] = mapped_column(String(32), default="speculative", index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionConditionCritiqueORM(Base):
    __tablename__ = "reaction_condition_critiques"
    __table_args__ = (
        Index(
            "ix_reaction_condition_critiques_project_created", "reaction_project_id", "created_at"
        ),
        Index("ix_reaction_condition_critiques_recommendation", "recommendation_id"),
        Index("ix_reaction_condition_critiques_advisor_run", "advisor_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    advisor_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_optimization_advisor_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    condition_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    mechanistic_rationale: Mapped[str] = mapped_column(Text)
    practicality_assessment: Mapped[str] = mapped_column(Text)
    cost_assessment: Mapped[str] = mapped_column(Text)
    safety_assessment: Mapped[str] = mapped_column(Text)
    risk_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    suggested_controls_json: Mapped[str] = mapped_column(Text, default="[]")
    suggested_alternatives_json: Mapped[str] = mapped_column(Text, default="[]")
    recommendation: Mapped[str] = mapped_column(String(64), default="insufficient_information")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionLiteraturePriorORM(Base):
    __tablename__ = "reaction_literature_priors"
    __table_args__ = (
        Index("ix_reaction_literature_priors_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_literature_priors_source", "source_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionOptimizationDebateORM(Base):
    __tablename__ = "reaction_optimization_debates"
    __table_args__ = (
        Index(
            "ix_reaction_optimization_debates_project_created", "reaction_project_id", "created_at"
        ),
        Index("ix_reaction_optimization_debates_bo_run", "bo_run_id"),
        Index("ix_reaction_optimization_debates_advisor_run", "advisor_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
        index=True,
    )
    bo_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_bayesian_optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    advisor_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_optimization_advisor_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bo_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    advisor_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    agreements_json: Mapped[str] = mapped_column(Text, default="[]")
    disagreements_json: Mapped[str] = mapped_column(Text, default="[]")
    final_review_recommendation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionExecutionBatchORM(Base):
    __tablename__ = "reaction_execution_batches"
    __table_args__ = (
        UniqueConstraint(
            "reaction_project_id",
            "batch_code",
            name="uq_reaction_execution_batches_project_code",
        ),
        Index("ix_reaction_execution_batches_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_execution_batches_project_status", "reaction_project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
    )
    batch_code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionExecutionItemORM(Base):
    __tablename__ = "reaction_execution_items"
    __table_args__ = (
        UniqueConstraint(
            "execution_batch_id",
            "item_code",
            name="uq_reaction_execution_items_batch_code",
        ),
        Index("ix_reaction_execution_items_batch_status", "execution_batch_id", "status"),
        Index("ix_reaction_execution_items_project_created", "reaction_project_id", "created_at"),
        Index("ix_reaction_execution_items_recommendation", "recommendation_id"),
        Index("ix_reaction_execution_items_experiment", "experiment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_batch_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_execution_batches.id", ondelete="CASCADE"),
    )
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_experiments.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_code: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="planned")
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    checklist_json: Mapped[str] = mapped_column(Text, default="[]")
    operator_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionExecutionEventORM(Base):
    __tablename__ = "reaction_execution_events"
    __table_args__ = (
        Index("ix_reaction_execution_events_item_created", "execution_item_id", "created_at"),
        Index("ix_reaction_execution_events_batch_created", "execution_batch_id", "created_at"),
        Index("ix_reaction_execution_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_execution_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_execution_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionAnalyticalResultORM(Base):
    __tablename__ = "reaction_analytical_results"
    __table_args__ = (
        Index("ix_reaction_analytical_results_item_created", "execution_item_id", "created_at"),
        Index("ix_reaction_analytical_results_spectracheck", "spectracheck_session_id"),
        Index("ix_reaction_analytical_results_type_created", "result_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_item_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_execution_items.id", ondelete="CASCADE"),
    )
    spectracheck_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_type: Mapped[str] = mapped_column(String(32), default="other")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    qc_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionOutcomeExtractionRunORM(Base):
    __tablename__ = "reaction_outcome_extraction_runs"
    __table_args__ = (
        Index(
            "ix_reaction_outcome_extraction_runs_item_created", "execution_item_id", "created_at"
        ),
        Index("ix_reaction_outcome_extraction_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_item_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_execution_items.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(32), default="queued")
    extraction_method: Mapped[str] = mapped_column(String(64), default="rule_based")
    proposed_outcome_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence_label: Mapped[str] = mapped_column(String(32), default="requires_review")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionOptimizationCycleORM(Base):
    __tablename__ = "reaction_optimization_cycles"
    __table_args__ = (
        UniqueConstraint(
            "reaction_project_id",
            "cycle_number",
            name="uq_reaction_optimization_cycles_project_number",
        ),
        Index(
            "ix_reaction_optimization_cycles_project_created", "reaction_project_id", "created_at"
        ),
        Index("ix_reaction_optimization_cycles_project_status", "reaction_project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"),
    )
    cycle_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    input_experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    new_experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    bo_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_bayesian_optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    advisor_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_optimization_advisor_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommendation_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_recommendation_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_execution_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ReactionCycleDecisionRecordORM(Base):
    __tablename__ = "reaction_cycle_decision_records"
    __table_args__ = (
        Index("ix_reaction_cycle_decisions_cycle_created", "optimization_cycle_id", "created_at"),
        Index("ix_reaction_cycle_decisions_decision_created", "decision", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    optimization_cycle_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_optimization_cycles.id", ondelete="CASCADE"),
    )
    decision: Mapped[str] = mapped_column(String(64))
    rationale: Mapped[str] = mapped_column(Text)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryJurisdictionORM(Base):
    __tablename__ = "regulatory_jurisdictions"
    __table_args__ = (
        UniqueConstraint("name", name="uq_regulatory_jurisdictions_name"),
        Index("ix_regulatory_jurisdictions_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(240))
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    authority_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatorySourceDocumentORM(Base):
    __tablename__ = "regulatory_source_documents"
    __table_args__ = (
        Index("ix_regulatory_sources_jurisdiction_created", "jurisdiction_id", "created_at"),
        Index("ix_regulatory_sources_type_status", "source_type", "status"),
        Index("ix_regulatory_sources_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(40), default="other")
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryCitationORM(Base):
    __tablename__ = "regulatory_citations"
    __table_args__ = (
        Index("ix_regulatory_citations_source_created", "source_id", "created_at"),
        UniqueConstraint(
            "source_id", "citation_label", name="uq_regulatory_citations_source_label"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source_documents.id", ondelete="CASCADE"),
    )
    citation_label: Mapped[str] = mapped_column(String(120))
    section_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryDossierORM(Base):
    __tablename__ = "regulatory_dossiers"
    __table_args__ = (
        Index("ix_regulatory_dossiers_status_updated", "status", "updated_at"),
        Index("ix_regulatory_dossiers_jurisdiction_created", "jurisdiction_id", "created_at"),
        Index("ix_regulatory_dossiers_spectracheck", "spectracheck_session_id"),
        Index("ix_regulatory_dossiers_reaction_project", "reaction_project_id"),
        Index("ix_regulatory_dossiers_created_by_user", "created_by_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Owner = the user who created the dossier; reads are scoped to it (a system api key
    # sees all). NULL for system-key-created or legacy rows (legacy backfilled from the
    # regulatory.dossier.create audit event in migration 0015).
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    sample_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spectracheck_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    reaction_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    product_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    compound_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    intended_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Product context for dose-driven impurity limits (ICH Q3A/B thresholds,
    # dose-scaled Q3C/Q3D limits). One dose per dossier; all its assessments use it.
    max_daily_dose_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    substance_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryRequirementORM(Base):
    __tablename__ = "regulatory_requirements"
    __table_args__ = (
        Index("ix_regulatory_requirements_dossier_created", "dossier_id", "created_at"),
        Index("ix_regulatory_requirements_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(64), default="other")
    requirement_text: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_link_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryEvidenceLinkORM(Base):
    __tablename__ = "regulatory_evidence_links"
    __table_args__ = (
        Index("ix_regulatory_evidence_links_dossier_created", "dossier_id", "created_at"),
        Index("ix_regulatory_evidence_links_requirement", "requirement_id"),
        Index("ix_regulatory_evidence_links_type_status", "evidence_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
    )
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_requirements.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(64), default="other")
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="linked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryQueryORM(Base):
    __tablename__ = "regulatory_queries"
    __table_args__ = (
        Index("ix_regulatory_queries_dossier_created", "dossier_id", "created_at"),
        Index("ix_regulatory_queries_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    question: Mapped[str] = mapped_column(Text)
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="queued")
    answer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryAnswerORM(Base):
    __tablename__ = "regulatory_answers"
    __table_args__ = (
        Index("ix_regulatory_answers_query_created", "query_id", "created_at"),
        Index("ix_regulatory_answers_confidence_created", "confidence_label", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_queries.id", ondelete="CASCADE"),
    )
    answer_text: Mapped[str] = mapped_column(Text)
    confidence_label: Mapped[str] = mapped_column(String(32), default="insufficient_sources")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_sources_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryRiskAssessmentORM(Base):
    __tablename__ = "regulatory_risk_assessments"
    __table_args__ = (
        Index("ix_regulatory_risk_assessments_dossier_created", "dossier_id", "created_at"),
        Index("ix_regulatory_risk_assessments_risk_created", "overall_risk", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
    )
    overall_risk: Mapped[str] = mapped_column(String(32), default="unknown")
    risk_factors_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, default="[]")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryReviewDecisionORM(Base):
    __tablename__ = "regulatory_review_decisions"
    __table_args__ = (
        Index("ix_regulatory_review_decisions_dossier_created", "dossier_id", "created_at"),
        Index("ix_regulatory_review_decisions_decision_created", "decision", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
    )
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryChangeAlertORM(Base):
    __tablename__ = "regulatory_change_alerts"
    __table_args__ = (
        Index("ix_regulatory_change_alerts_jurisdiction_created", "jurisdiction_id", "created_at"),
        Index("ix_regulatory_change_alerts_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), default="info")
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryReadinessReportORM(Base):
    __tablename__ = "regulatory_readiness_reports"
    __table_args__ = (
        Index("ix_regulatory_readiness_reports_dossier_created", "dossier_id", "created_at"),
        Index("ix_regulatory_readiness_reports_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(32), default="requires_review")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    requirements_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    gaps_json: Mapped[str] = mapped_column(Text, default="[]")
    risks_json: Mapped[str] = mapped_column(Text, default="{}")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    review_status_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryRuleSetORM(Base):
    __tablename__ = "regulatory_rule_sets"
    __table_args__ = (
        Index("ix_regulatory_rule_sets_status_source", "status", "source_type"),
        Index("ix_regulatory_rule_sets_jurisdiction", "jurisdiction_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300))
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(32), default="custom")
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ImpurityThresholdRuleORM(Base):
    __tablename__ = "impurity_threshold_rules"
    __table_args__ = (
        Index("ix_impurity_threshold_rules_set_type", "rule_set_id", "rule_type"),
        Index("ix_impurity_threshold_rules_applies", "applies_to"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_set_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_rule_sets.id", ondelete="CASCADE"),
    )
    rule_type: Mapped[str] = mapped_column(String(32))
    threshold_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_amount_mg_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    applies_to: Mapped[str] = mapped_column(String(32), default="unspecified")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ResidualSolventRuleORM(Base):
    __tablename__ = "residual_solvent_rules"
    __table_args__ = (
        Index("ix_residual_solvent_rules_set_solvent", "rule_set_id", "solvent_name"),
        Index("ix_residual_solvent_rules_class", "solvent_class"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_set_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_rule_sets.id", ondelete="CASCADE"),
    )
    solvent_name: Mapped[str] = mapped_column(String(160))
    solvent_class: Mapped[str] = mapped_column(String(32), default="unknown")
    permitted_daily_exposure: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class NitrosamineRiskRuleORM(Base):
    __tablename__ = "nitrosamine_risk_rules"
    __table_args__ = (
        Index("ix_nitrosamine_risk_rules_set_category", "rule_set_id", "risk_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_set_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_rule_sets.id", ondelete="CASCADE"),
    )
    risk_category: Mapped[str] = mapped_column(String(64), default="unknown")
    structural_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptable_intake: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class QNMRComplianceProfileORM(Base):
    __tablename__ = "qnmr_compliance_profiles"
    __table_args__ = (
        Index("ix_qnmr_profiles_dossier_created", "dossier_id", "created_at"),
        Index("ix_qnmr_profiles_status", "q2_q14_readiness_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    analytical_target_profile_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    calibration_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    internal_standard: Mapped[str | None] = mapped_column(String(200), nullable=True)
    acquisition_parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    uncertainty_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    q2_q14_readiness_status: Mapped[str] = mapped_column(String(32), default="not_assessed")
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AnalyticalMethodValidationProfileORM(Base):
    __tablename__ = "analytical_method_validation_profiles"
    __table_args__ = (
        Index("ix_method_validation_profiles_dossier_created", "dossier_id", "created_at"),
        Index("ix_method_validation_profiles_type_status", "method_type", "validation_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    method_type: Mapped[str] = mapped_column(String(32), default="other")
    analytical_target_profile_json: Mapped[str] = mapped_column(Text, default="{}")
    accuracy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    precision_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    specificity_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    linearity_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    range_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    robustness_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    lod_loq_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="not_started")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryActionItemORM(Base):
    __tablename__ = "regulatory_action_items"
    __table_args__ = (
        Index("ix_regulatory_action_items_dossier_status", "dossier_id", "status"),
        Index("ix_regulatory_action_items_batch_status", "batch_id", "status"),
        Index("ix_regulatory_action_items_compound_status", "compound_id", "status"),
        Index("ix_regulatory_action_items_type_severity", "action_type", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"),
        nullable=True,
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_evidence_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_requirements.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(64), default="human_review")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    status: Mapped[str] = mapped_column(String(32), default="open")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class BatchRegulatoryAssessmentORM(Base):
    __tablename__ = "batch_regulatory_assessments"
    __table_args__ = (
        Index("ix_batch_reg_assessments_dossier_created", "dossier_id", "created_at"),
        Index("ix_batch_reg_assessments_batch_created", "batch_id", "created_at"),
        Index("ix_batch_reg_assessments_status", "overall_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_batches.id", ondelete="SET NULL"), nullable=True
    )
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="SET NULL"), nullable=True
    )
    overall_status: Mapped[str] = mapped_column(String(32), default="not_assessed")
    impurity_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    elemental_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    residual_solvent_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    nitrosamine_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    qnmr_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    ai_governance_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    action_item_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ImpurityRiskRegisterORM(Base):
    __tablename__ = "impurity_risk_register"
    __table_args__ = (
        Index("ix_impurity_risk_register_dossier_created", "dossier_id", "created_at"),
        Index("ix_impurity_risk_register_type_status", "impurity_type", "status"),
        Index("ix_impurity_risk_register_action", "action_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    impurity_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    impurity_type: Mapped[str] = mapped_column(String(32), default="unknown")
    source: Mapped[str] = mapped_column(String(32), default="unknown")
    observed_level_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_triggered: Mapped[str] = mapped_column(String(32), default="none")
    structural_assignment: Mapped[str | None] = mapped_column(Text, nullable=True)
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="SET NULL"), nullable=True
    )
    evidence_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_evidence_links.id", ondelete="SET NULL"), nullable=True
    )
    action_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_action_items.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="draft")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AIGovernanceRecordORM(Base):
    __tablename__ = "ai_governance_records"
    __table_args__ = (
        Index("ix_ai_governance_records_dossier_created", "dossier_id", "created_at"),
        Index("ix_ai_governance_records_status", "governance_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    ai_system_name: Mapped[str] = mapped_column(String(240))
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("method_registry_entries.id", ondelete="SET NULL"), nullable=True
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    evidence_item_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    explainability_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    human_override_available: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_record_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    governance_status: Mapped[str] = mapped_column(String(32), default="not_assessed")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryAIDecisionORM(Base):
    """One hash-chained EU GMP Draft Annex 22 AI-decision record for a dossier.

    Append-only: rows are immutable and chained per dossier via
    ``previous_entry_hash`` -> ``entry_hash``. A HITL review is itself a row (its
    ``reviews_entry_hash`` points at the reviewed decision). Backs
    ``moltrace.regulatory.compliance.AIDecisionRecord``.
    """

    __tablename__ = "regulatory_ai_decisions"
    __table_args__ = (
        Index("ix_regulatory_ai_decisions_dossier", "dossier_id", "id"),
        Index("ix_regulatory_ai_decisions_entry_hash", "entry_hash"),
        Index("ix_regulatory_ai_decisions_reviews", "reviews_entry_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    entry_hash: Mapped[str] = mapped_column(String(96))
    previous_entry_hash: Mapped[str] = mapped_column(String(96))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[str] = mapped_column(String(128))
    decision_type: Mapped[str] = mapped_column(String(128))
    model_name: Mapped[str] = mapped_column(String(240))
    model_version: Mapped[str] = mapped_column(String(512))
    input_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_data_hash: Mapped[str] = mapped_column(String(96))
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float] = mapped_column(Float)
    feature_attribution_json: Mapped[str] = mapped_column(Text, default="{}")
    regulatory_basis: Mapped[str] = mapped_column(String(512))
    risk_level: Mapped[str] = mapped_column(String(16))
    hitl_required: Mapped[bool] = mapped_column(Boolean, default=False)
    hitl_reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hitl_review_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hitl_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reviews_entry_hash: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JurisdictionalRequirementMapORM(Base):
    __tablename__ = "jurisdictional_requirement_maps"
    __table_args__ = (
        Index("ix_jurisdictional_maps_dossier_created", "dossier_id", "created_at"),
        Index("ix_jurisdictional_maps_jurisdiction", "jurisdiction_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE")
    )
    jurisdiction_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="CASCADE")
    )
    rule_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_rule_sets.id", ondelete="SET NULL"), nullable=True
    )
    requirement_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    threshold_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    differences_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatorySourceWatcherORM(Base):
    __tablename__ = "regulatory_source_watchers"
    __table_args__ = (
        Index("ix_regulatory_source_watchers_source_status", "source_id", "status"),
        Index("ix_regulatory_source_watchers_jurisdiction", "jurisdiction_id"),
        Index("ix_regulatory_source_watchers_frequency", "check_frequency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(64), default="other")
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_frequency: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_change_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatorySurveillanceRunORM(Base):
    __tablename__ = "regulatory_surveillance_runs"
    __table_args__ = (
        Index("ix_regulatory_surveillance_runs_watcher_created", "watcher_id", "created_at"),
        Index("ix_regulatory_surveillance_runs_source_created", "source_id", "created_at"),
        Index("ix_regulatory_surveillance_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watcher_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_watchers.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_type: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(32), default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    change_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_change_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatorySourceVersionORM(Base):
    __tablename__ = "regulatory_source_versions"
    __table_args__ = (
        Index("ix_regulatory_source_versions_source_status", "source_id", "status"),
        Index("ix_regulatory_source_versions_watcher_created", "watcher_id", "created_at"),
        Index("ix_regulatory_source_versions_hash", "normalized_text_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source_documents.id", ondelete="CASCADE"),
    )
    watcher_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_watchers.id", ondelete="SET NULL"),
        nullable=True,
    )
    version_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="current")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryChangeEventORM(Base):
    __tablename__ = "regulatory_change_events"
    __table_args__ = (
        Index("ix_regulatory_change_events_source_created", "source_id", "created_at"),
        Index("ix_regulatory_change_events_type_severity", "change_type", "severity"),
        Index("ix_regulatory_change_events_review", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source_documents.id", ondelete="CASCADE"),
    )
    old_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_source_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_version_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_source_versions.id", ondelete="CASCADE"),
    )
    change_type: Mapped[str] = mapped_column(String(40), default="text_changed")
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    affected_topics_json: Mapped[str] = mapped_column(Text, default="[]")
    affected_rule_set_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    affected_dossier_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    review_status: Mapped[str] = mapped_column(String(32), default="unreviewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryChangeDiffORM(Base):
    __tablename__ = "regulatory_change_diffs"
    __table_args__ = (
        Index("ix_regulatory_change_diffs_event_type", "change_event_id", "diff_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_event_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_change_events.id", ondelete="CASCADE"),
    )
    diff_type: Mapped[str] = mapped_column(String(32), default="text")
    before_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_summary: Mapped[str] = mapped_column(Text)
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryImpactAssessmentORM(Base):
    __tablename__ = "regulatory_impact_assessments"
    __table_args__ = (
        Index("ix_regulatory_impact_assessments_event_created", "change_event_id", "created_at"),
        Index("ix_regulatory_impact_assessments_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_event_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_change_events.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(32), default="draft")
    impacted_dossiers_json: Mapped[str] = mapped_column(Text, default="[]")
    impacted_requirements_json: Mapped[str] = mapped_column(Text, default="[]")
    impacted_action_items_json: Mapped[str] = mapped_column(Text, default="[]")
    impacted_rule_sets_json: Mapped[str] = mapped_column(Text, default="[]")
    impacted_ai_governance_records_json: Mapped[str] = mapped_column(Text, default="[]")
    recommended_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryRuleUpdateProposalORM(Base):
    __tablename__ = "regulatory_rule_update_proposals"
    __table_args__ = (
        Index("ix_regulatory_rule_update_proposals_event_status", "change_event_id", "status"),
        Index("ix_regulatory_rule_update_proposals_rule_set", "rule_set_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_event_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_change_events.id", ondelete="CASCADE"),
    )
    rule_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_rule_sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    proposal_type: Mapped[str] = mapped_column(String(64), default="other")
    title: Mapped[str] = mapped_column(String(300))
    rationale: Mapped[str] = mapped_column(Text)
    proposed_changes_json: Mapped[str] = mapped_column(Text, default="{}")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryImpactNotificationORM(Base):
    __tablename__ = "regulatory_impact_notifications"
    __table_args__ = (
        Index("ix_regulatory_impact_notifications_status_created", "status", "created_at"),
        Index("ix_regulatory_impact_notifications_dossier_status", "dossier_id", "status"),
        Index("ix_regulatory_impact_notifications_event", "change_event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_change_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_action_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="unread")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeSourceORM(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        Index("ix_knowledge_sources_type_status", "source_type", "status"),
        Index("ix_knowledge_sources_doi", "doi"),
        Index("ix_knowledge_sources_patent", "patent_number"),
        Index("ix_knowledge_sources_jurisdiction", "jurisdiction_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(64), default="other")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    patent_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    publisher: Mapped[str | None] = mapped_column(String(240), nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    reliability_label: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeSourceFileORM(Base):
    __tablename__ = "knowledge_source_files"
    __table_args__ = (
        Index("ix_knowledge_source_files_source_created", "source_id", "created_at"),
        Index("ix_knowledge_source_files_sha256", "sha256"),
        Index("ix_knowledge_source_files_parse_status", "parse_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("managed_file_records.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parsed_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="not_parsed")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeExtractionRunORM(Base):
    __tablename__ = "knowledge_extraction_runs"
    __table_args__ = (
        Index("ix_knowledge_extraction_runs_source_created", "source_id", "created_at"),
        Index("ix_knowledge_extraction_runs_file_created", "source_file_id", "created_at"),
        Index("ix_knowledge_extraction_runs_type_status", "extraction_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_source_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    extraction_type: Mapped[str] = mapped_column(String(64), default="mixed", index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    model_or_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    method_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extracted_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExtractedCitationORM(Base):
    __tablename__ = "extracted_citations"
    __table_args__ = (
        Index("ix_extracted_citations_source_created", "source_id", "created_at"),
        Index("ix_extracted_citations_file_created", "source_file_id", "created_at"),
        UniqueConstraint("source_id", "citation_label", name="uq_extracted_citations_source_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_source_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    citation_label: Mapped[str] = mapped_column(String(120))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    paragraph_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExtractedReactionRecordORM(Base):
    __tablename__ = "extracted_reaction_records"
    __table_args__ = (
        Index("ix_extracted_reactions_run_created", "extraction_run_id", "created_at"),
        Index("ix_extracted_reactions_source_created", "source_id", "created_at"),
        Index("ix_extracted_reactions_review", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_extraction_runs.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    reaction_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    reaction_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    substrate_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    reagent_json: Mapped[str] = mapped_column(Text, default="[]")
    solvent_json: Mapped[str] = mapped_column(Text, default="[]")
    catalyst_json: Mapped[str] = mapped_column(Text, default="[]")
    ligand_json: Mapped[str] = mapped_column(Text, default="[]")
    base_json: Mapped[str] = mapped_column(Text, default="[]")
    additive_json: Mapped[str] = mapped_column(Text, default="[]")
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scale: Mapped[str | None] = mapped_column(String(120), nullable=True)
    yield_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    selectivity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    ee_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    impurity_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="unreviewed", index=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExtractedAnalyticalRecordORM(Base):
    __tablename__ = "extracted_analytical_records"
    __table_args__ = (
        Index("ix_extracted_analytical_run_created", "extraction_run_id", "created_at"),
        Index("ix_extracted_analytical_source_created", "source_id", "created_at"),
        Index("ix_extracted_analytical_review", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_extraction_runs.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    compound_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    structure_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    formula: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exact_mass: Mapped[float | None] = mapped_column(Float, nullable=True)
    nmr_1h_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    nmr_13c_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    nmr_2d_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    hrms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    msms_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    solvent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    frequency_mhz: Mapped[float | None] = mapped_column(Float, nullable=True)
    analytical_method: Mapped[str | None] = mapped_column(String(160), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="unreviewed", index=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExtractedRegulatoryRecordORM(Base):
    __tablename__ = "extracted_regulatory_records"
    __table_args__ = (
        Index("ix_extracted_regulatory_run_created", "extraction_run_id", "created_at"),
        Index("ix_extracted_regulatory_source_created", "source_id", "created_at"),
        Index("ix_extracted_regulatory_topic_review", "topic", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_extraction_runs.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    jurisdiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_jurisdictions.id", ondelete="SET NULL"), nullable=True
    )
    topic: Mapped[str] = mapped_column(String(64), default="other", index=True)
    requirement_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_candidate_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_candidate_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="unreviewed", index=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeReviewTaskORM(Base):
    __tablename__ = "knowledge_review_tasks"
    __table_args__ = (
        Index("ix_knowledge_review_tasks_status_created", "status", "created_at"),
        Index("ix_knowledge_review_tasks_record", "record_type", "record_id"),
        Index("ix_knowledge_review_tasks_run", "extraction_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_extraction_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class KnowledgeGraphLinkORM(Base):
    __tablename__ = "knowledge_graph_links"
    __table_args__ = (
        Index("ix_knowledge_graph_links_record", "record_type", "record_id"),
        Index("ix_knowledge_graph_links_target", "target_type", "target_id"),
        Index("ix_knowledge_graph_links_relation", "relation_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(160), index=True)
    relation_type: Mapped[str] = mapped_column(String(64), index=True)
    confidence_label: Mapped[str] = mapped_column(String(32), default="requires_review", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class TrainingDatasetCandidateORM(Base):
    __tablename__ = "training_dataset_candidates"
    __table_args__ = (
        Index("ix_training_candidates_record", "record_type", "record_id"),
        Index("ix_training_candidates_type_status", "dataset_type", "status"),
        Index("ix_training_candidates_source", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True
    )
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    dataset_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    quality_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    citation_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class BenchmarkDatasetCandidateORM(Base):
    __tablename__ = "benchmark_dataset_candidates"
    __table_args__ = (
        Index("ix_benchmark_candidates_record", "record_type", "record_id"),
        Index("ix_benchmark_candidates_type_status", "benchmark_type", "status"),
        Index("ix_benchmark_candidates_leakage", "leakage_risk_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True
    )
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    benchmark_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    split_recommendation: Mapped[str] = mapped_column(String(32), default="unknown")
    leakage_risk_label: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    quality_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelImprovementQueueItemORM(Base):
    __tablename__ = "model_improvement_queue_items"
    __table_args__ = (
        Index("ix_model_improvement_queue_status_priority", "status", "priority"),
        Index("ix_model_improvement_queue_module", "target_module"),
        Index("ix_model_improvement_queue_linked_record", "linked_record_type", "linked_record_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    linked_record_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class FeatureRecordORM(Base):
    __tablename__ = "feature_records"
    __table_args__ = (
        Index("ix_feature_records_record", "record_type", "record_id"),
        Index("ix_feature_records_family_version", "feature_family", "feature_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_type: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    feature_family: Mapped[str] = mapped_column(String(64), index=True)
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    feature_version: Mapped[str] = mapped_column(String(64), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DatasetVersionORM(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        Index("ix_dataset_versions_type_status", "dataset_type", "status"),
        UniqueConstraint(
            "dataset_type", "name", "version", name="uq_dataset_versions_type_name_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(64))
    source_record_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    split_json: Mapped[str] = mapped_column(Text, default="{}")
    quality_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    leakage_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MLTaskDefinitionORM(Base):
    __tablename__ = "ml_task_definitions"
    __table_args__ = (
        UniqueConstraint("task_key", name="uq_ml_task_definitions_task_key"),
        Index("ix_ml_task_definitions_domain_status", "domain", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(32), index=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    default_metric: Mapped[str] = mapped_column(String(120), default="review_required")
    required_dataset_type: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class FeaturePipelineORM(Base):
    __tablename__ = "feature_pipelines"
    __table_args__ = (
        UniqueConstraint(
            "task_key", "name", "version", name="uq_feature_pipelines_task_name_version"
        ),
        Index("ix_feature_pipelines_task_status", "task_key", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(80))
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    input_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    output_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    feature_steps_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="experimental", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MLTrainingRunORM(Base):
    __tablename__ = "ml_training_runs"
    __table_args__ = (
        Index("ix_ml_training_runs_task_status", "task_key", "status"),
        Index("ix_ml_training_runs_dataset", "dataset_version_id"),
        Index("ix_ml_training_runs_family", "model_family"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), index=True
    )
    feature_pipeline_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_pipelines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_family: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    training_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelArtifactORM(Base):
    __tablename__ = "model_artifacts"
    __table_args__ = (
        Index("ix_model_artifacts_task_status", "task_key", "status"),
        Index("ix_model_artifacts_name_version", "model_name", "model_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_run_id: Mapped[int] = mapped_column(
        ForeignKey("ml_training_runs.id", ondelete="CASCADE"), index=True
    )
    model_name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(80))
    model_family: Mapped[str] = mapped_column(String(64), index=True)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), default="trained", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MLEvaluationRunORM(Base):
    __tablename__ = "ml_evaluation_runs"
    __table_args__ = (
        Index("ix_ml_evaluation_runs_status_created", "status", "created_at"),
        Index("ix_ml_evaluation_runs_artifact", "model_artifact_id"),
        Index("ix_ml_evaluation_runs_dataset", "dataset_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ml_training_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    benchmark_dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("benchmark_datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    slice_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    confusion_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calibration_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_examples_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelMetricORM(Base):
    __tablename__ = "model_metrics"
    __table_args__ = (
        Index("ix_ml_model_metrics_evaluation_metric", "evaluation_run_id", "metric_name"),
        Index("ix_ml_model_metrics_split", "split"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[int] = mapped_column(
        ForeignKey("ml_evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(120), index=True)
    metric_value: Mapped[float] = mapped_column(Float)
    metric_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    split: Mapped[str] = mapped_column(String(32), default="unknown")
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CalibrationAssessmentORM(Base):
    __tablename__ = "calibration_assessments"
    __table_args__ = (
        Index("ix_calibration_assessments_artifact_status", "model_artifact_id", "status"),
        Index("ix_calibration_assessments_evaluation", "evaluation_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="CASCADE"), index=True
    )
    evaluation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ml_evaluation_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    calibration_method: Mapped[str] = mapped_column(String(64), default="not_assessed", index=True)
    calibration_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="not_assessed", index=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ErrorAnalysisSliceORM(Base):
    __tablename__ = "error_analysis_slices"
    __table_args__ = (
        Index("ix_error_analysis_slices_evaluation_severity", "evaluation_run_id", "severity"),
        Index("ix_error_analysis_slices_type", "slice_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[int] = mapped_column(
        ForeignKey("ml_evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    slice_name: Mapped[str] = mapped_column(String(200))
    slice_type: Mapped[str] = mapped_column(String(64), default="other", index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    representative_errors_json: Mapped[str] = mapped_column(Text, default="[]")
    severity: Mapped[str] = mapped_column(String(32), default="info", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class OutOfDomainAssessmentORM(Base):
    __tablename__ = "out_of_domain_assessments"
    __table_args__ = (
        Index("ix_ood_assessments_artifact_status", "model_artifact_id", "status"),
        Index("ix_ood_assessments_dataset", "dataset_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="CASCADE"), index=True
    )
    dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    method: Mapped[str] = mapped_column(String(64), default="rule_based", index=True)
    ood_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    high_risk_regions_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="requires_review", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelCardORM(Base):
    __tablename__ = "model_cards"
    __table_args__ = (
        Index("ix_model_cards_artifact", "model_artifact_id"),
        Index("ix_model_cards_task_status", "task_key", "approval_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="CASCADE"), index=True
    )
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    intended_use: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)
    training_data_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    evaluation_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    bias_risk_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    out_of_domain_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    calibration_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    human_review_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    approval_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class DeploymentCandidateORM(Base):
    __tablename__ = "deployment_candidates"
    __table_args__ = (
        Index("ix_deployment_candidates_artifact_status", "model_artifact_id", "status"),
        Index("ix_deployment_candidates_target_status", "target_module", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="CASCADE"), index=True
    )
    model_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    target_endpoint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PredictionServiceConfigORM(Base):
    __tablename__ = "prediction_service_configs"
    __table_args__ = (
        Index("ix_prediction_service_configs_target_status", "target_module", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    active_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fallback_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    routing_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence_thresholds_json: Mapped[str] = mapped_column(Text, default="{}")
    ood_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    fallback_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    human_review_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    max_batch_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AIServiceRegistryORM(Base):
    __tablename__ = "ai_service_registry"
    __table_args__ = (
        UniqueConstraint("service_key", name="uq_ai_service_registry_service_key"),
        Index("ix_ai_service_registry_module_status", "target_module", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    active_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fallback_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prediction_service_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("prediction_service_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PredictionRunORM(Base):
    __tablename__ = "prediction_runs"
    __table_args__ = (
        Index("ix_prediction_runs_service_status", "service_key", "status"),
        Index("ix_prediction_runs_model_created", "model_artifact_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(120), index=True)
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deployment_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("deployment_candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    prediction_result_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_json: Mapped[str] = mapped_column(Text, default="{}")
    ood_status: Mapped[str] = mapped_column(String(32), default="not_assessed", index=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PredictionResultORM(Base):
    __tablename__ = "prediction_results"
    __table_args__ = (
        Index("ix_prediction_results_run", "prediction_run_id"),
        Index("ix_prediction_results_type_created", "result_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_run_id: Mapped[int] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE"), index=True
    )
    result_type: Mapped[str] = mapped_column(String(64), index=True)
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_json: Mapped[str] = mapped_column(Text, default="{}")
    explanation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelRoutingDecisionORM(Base):
    __tablename__ = "model_routing_decisions"
    __table_args__ = (
        Index("ix_model_routing_decisions_service_created", "service_key", "created_at"),
        Index("ix_model_routing_decisions_target", "target_module"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(120), index=True)
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    selected_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fallback_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    routing_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class InferenceExplanationORM(Base):
    __tablename__ = "inference_explanations"
    __table_args__ = (
        Index("ix_inference_explanations_run", "prediction_run_id"),
        Index("ix_inference_explanations_type", "explanation_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    explanation_type: Mapped[str] = mapped_column(String(64), default="unavailable", index=True)
    explanation_json: Mapped[str] = mapped_column(Text, default="{}")
    summary: Mapped[str] = mapped_column(Text, default="")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PredictionFeedbackORM(Base):
    __tablename__ = "prediction_feedback"
    __table_args__ = (
        Index("ix_prediction_feedback_run_type", "prediction_run_id", "feedback_type"),
        Index("ix_prediction_feedback_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_run_id: Mapped[int] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE"), index=True
    )
    feedback_type: Mapped[str] = mapped_column(String(32), index=True)
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ActiveLearningCandidateORM(Base):
    __tablename__ = "active_learning_candidates"
    __table_args__ = (
        Index("ix_active_learning_candidates_status_priority", "status", "priority"),
        Index("ix_active_learning_candidates_run", "prediction_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    linked_model_improvement_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_improvement_queue_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ShadowEvaluationRunORM(Base):
    __tablename__ = "shadow_evaluation_runs"
    __table_args__ = (
        Index("ix_shadow_evaluation_runs_service_status", "service_key", "status"),
        Index("ix_shadow_evaluation_runs_candidate", "candidate_model_artifact_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(120), index=True)
    production_model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_model_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="CASCADE"), index=True
    )
    dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    comparison_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    disagreement_examples_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CanaryDeploymentRecordORM(Base):
    __tablename__ = "canary_deployment_records"
    __table_args__ = (
        Index("ix_canary_deployments_service_status", "service_key", "status"),
        Index("ix_canary_deployments_candidate", "candidate_model_artifact_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(120), index=True)
    candidate_model_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="CASCADE"), index=True
    )
    target_module: Mapped[str] = mapped_column(String(64), index=True)
    traffic_percent: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    monitoring_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModelMonitoringEventORM(Base):
    __tablename__ = "model_monitoring_events"
    __table_args__ = (
        Index("ix_model_monitoring_events_service_created", "service_key", "created_at"),
        Index("ix_model_monitoring_events_type_severity", "event_type", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_key: Mapped[str] = mapped_column(String(120), index=True)
    model_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ProductProgramRegistryORM(Base):
    __tablename__ = "product_program_registry"
    __table_args__ = (
        UniqueConstraint("program_key", name="uq_product_program_registry_key"),
        Index("ix_product_program_registry_order", "display_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_key: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    display_order: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ModulePriorityMapORM(Base):
    __tablename__ = "module_priority_maps"
    __table_args__ = (UniqueConstraint("context", name="uq_module_priority_maps_context"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    context: Mapped[str] = mapped_column(String(32), index=True)
    program_order_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CrossModuleWorkflowTemplateORM(Base):
    __tablename__ = "cross_module_workflow_templates"
    __table_args__ = (
        UniqueConstraint("template_key", name="uq_cross_module_workflow_templates_key"),
        Index("ix_cross_module_workflow_templates_trigger", "trigger_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    program_sequence_json: Mapped[str] = mapped_column(Text, default="[]")
    trigger_type: Mapped[str] = mapped_column(String(64), default="manual", index=True)
    required_inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    optional_inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SpectroscopyToRegulatoryBridgeORM(Base):
    __tablename__ = "spectroscopy_to_regulatory_bridges"
    __table_args__ = (
        Index("ix_s2r_bridges_session", "spectracheck_session_id"),
        Index("ix_s2r_bridges_dossier_status", "dossier_id", "bridge_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spectracheck_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_evidence_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_report_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bridge_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    extracted_regulatory_signals_json: Mapped[str] = mapped_column(Text, default="{}")
    created_requirement_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_action_item_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryToReactionBridgeORM(Base):
    __tablename__ = "regulatory_to_reaction_bridges"
    __table_args__ = (
        Index("ix_r2r_bridges_dossier", "dossier_id"),
        Index("ix_r2r_bridges_project_status", "reaction_project_id", "bridge_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    regulatory_action_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_action_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reaction_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bridge_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    regulatory_constraints_json: Mapped[str] = mapped_column(Text, default="[]")
    optimization_objectives_json: Mapped[str] = mapped_column(Text, default="{}")
    created_constraint_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RegulatoryConstraintSetORM(Base):
    __tablename__ = "regulatory_constraint_sets"
    __table_args__ = (
        Index("ix_regulatory_constraints_project_status", "reaction_project_id", "status"),
        Index("ix_regulatory_constraints_type_severity", "constraint_type", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"), index=True
    )
    dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_action_item_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    constraint_type: Mapped[str] = mapped_column(String(64), default="other", index=True)
    constraint_json: Mapped[str] = mapped_column(Text, default="{}")
    severity: Mapped[str] = mapped_column(String(32), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ComplianceDrivenOptimizationObjectiveORM(Base):
    __tablename__ = "compliance_driven_optimization_objectives"
    __table_args__ = (
        Index("ix_compliance_objectives_project_status", "reaction_project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction_project_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_projects.id", ondelete="CASCADE"), index=True
    )
    regulatory_constraint_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_constraint_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    objective_json: Mapped[str] = mapped_column(Text, default="{}")
    scalarization_json: Mapped[str] = mapped_column(Text, default="{}")
    hard_constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    soft_constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CTDModule3ReportBundleORM(Base):
    __tablename__ = "ctd_module3_report_bundles"
    __table_args__ = (Index("ix_ctd_module3_bundles_dossier_created", "dossier_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="CASCADE"), index=True
    )
    spectracheck_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_report_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    regulatory_readiness_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_readiness_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    batch_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("batch_regulatory_assessments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    qnmr_compliance_id: Mapped[int | None] = mapped_column(
        ForeignKey("qnmr_compliance_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    impurity_register_id: Mapped[int | None] = mapped_column(
        ForeignKey("impurity_risk_register.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ai_governance_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_governance_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    report_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CrossModuleActionItemORM(Base):
    __tablename__ = "cross_module_action_items"
    __table_args__ = (
        Index("ix_cross_module_actions_source", "source_program", "source_resource_type"),
        Index("ix_cross_module_actions_target", "target_program", "target_resource_type"),
        Index("ix_cross_module_actions_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_program: Mapped[str] = mapped_column(String(64), index=True)
    target_program: Mapped[str] = mapped_column(String(64), index=True)
    source_resource_type: Mapped[str] = mapped_column(String(120), index=True)
    source_resource_id: Mapped[int] = mapped_column(Integer, index=True)
    target_resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    target_resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64), default="other", index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CrossModuleCommandCenterSummaryORM(Base):
    __tablename__ = "cross_module_command_center_summaries"
    __table_args__ = (
        Index("ix_command_center_summaries_scope", "scope", "scope_id"),
        Index("ix_command_center_summaries_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    spectracheck_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    regulatory_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    reaction_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    open_cross_module_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MobileDeviceSessionORM(Base):
    __tablename__ = "mobile_device_sessions"
    __table_args__ = (
        Index("ix_mobile_device_sessions_user_status", "user_email", "status"),
        Index("ix_mobile_device_sessions_last_seen", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    device_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    device_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MobileViewPreferenceORM(Base):
    __tablename__ = "mobile_view_preferences"
    __table_args__ = (
        Index("ix_mobile_view_preferences_user", "user_email"),
        Index("ix_mobile_view_preferences_device", "device_session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    device_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("mobile_device_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preferred_home: Mapped[str] = mapped_column(String(40), default="dashboard", index=True)
    compact_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    bottom_nav_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reduce_motion: Mapped[bool] = mapped_column(Boolean, default=False)
    high_contrast: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MobileActionDraftORM(Base):
    __tablename__ = "mobile_action_drafts"
    __table_args__ = (
        Index("ix_mobile_action_drafts_user_status", "user_email", "status"),
        Index("ix_mobile_action_drafts_device_status", "device_session_id", "status"),
        Index("ix_mobile_action_drafts_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    device_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("mobile_device_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), default="other", index=True)
    target_type: Mapped[str] = mapped_column(String(120), index=True)
    target_id: Mapped[str] = mapped_column(String(120), index=True)
    draft_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    validation_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MobileSyncResultORM(Base):
    __tablename__ = "mobile_sync_results"
    __table_args__ = (
        Index("ix_mobile_sync_results_device_created", "device_session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("mobile_device_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    synced_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MobilePushSubscriptionORM(Base):
    __tablename__ = "mobile_push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint_hash", name="uq_mobile_push_subscriptions_endpoint_hash"),
        Index("ix_mobile_push_subscriptions_user_status", "user_email", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64), index=True)
    subscription_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MobileNotificationORM(Base):
    __tablename__ = "mobile_notifications"
    __table_args__ = (
        Index("ix_mobile_notifications_user_status", "user_email", "status"),
        Index("ix_mobile_notifications_target", "target_type", "target_id"),
        Index("ix_mobile_notifications_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    notification_type: Mapped[str] = mapped_column(String(64), default="other", index=True)
    title: Mapped[str] = mapped_column(String(240))
    message: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", index=True)
    status: Mapped[str] = mapped_column(String(32), default="unread", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompactModuleSummaryORM(Base):
    __tablename__ = "compact_module_summaries"
    __table_args__ = (
        Index("ix_compact_module_summaries_scope", "scope", "scope_id"),
        Index("ix_compact_module_summaries_generated", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    spectracheck_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    regulatory_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    reaction_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    action_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompoundEntityORM(Base):
    __tablename__ = "compound_entities"
    __table_args__ = (
        Index("ix_compound_entities_registry", "registry_id"),
        Index("ix_compound_entities_type_status", "compound_type", "status"),
        Index("ix_compound_entities_inchikey", "inchikey"),
        Index("ix_compound_entities_formula", "molecular_formula"),
        Index("ix_compound_entities_updated", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    preferred_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    registry_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    compound_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    original_structure_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_structure_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    canonical_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    inchi: Mapped[str | None] = mapped_column(Text, nullable=True)
    inchikey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    molecular_formula: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    exact_mass: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    stereochemistry_status: Mapped[str] = mapped_column(String(32), default="unknown")
    salt_solvent_status: Mapped[str] = mapped_column(String(32), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompoundStructureRecordORM(Base):
    __tablename__ = "compound_structure_records"
    __table_args__ = (
        Index("ix_compound_structures_compound_created", "compound_id", "created_at"),
        Index("ix_compound_structures_inchikey", "inchikey"),
        Index("ix_compound_structures_formula", "formula"),
        Index("ix_compound_structures_source_status", "source", "validation_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compound_id: Mapped[int] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="CASCADE"),
        index=True,
    )
    structure_input: Mapped[str] = mapped_column(Text)
    structure_format: Mapped[str] = mapped_column(String(32))
    canonical_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    inchi: Mapped[str | None] = mapped_column(Text, nullable=True)
    inchikey: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    formula: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    exact_mass: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="user_entered", index=True)
    normalization_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    validation_status: Mapped[str] = mapped_column(String(32), default="not_checked", index=True)
    reviewer_status: Mapped[str] = mapped_column(String(32), default="unreviewed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompoundAliasORM(Base):
    __tablename__ = "compound_aliases"
    __table_args__ = (
        UniqueConstraint("compound_id", "alias", "alias_type", name="uq_compound_alias_identity"),
        Index("ix_compound_aliases_compound_created", "compound_id", "created_at"),
        Index("ix_compound_aliases_alias", "alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compound_id: Mapped[int] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="CASCADE"),
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(300))
    alias_type: Mapped[str] = mapped_column(String(32), default="other", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompoundBatchORM(Base):
    __tablename__ = "compound_batches"
    __table_args__ = (
        Index("ix_compound_batches_compound_status", "compound_id", "status"),
        Index("ix_compound_batches_batch_code", "batch_code"),
        Index("ix_compound_batches_reaction", "reaction_experiment_id"),
        Index("ix_compound_batches_spectracheck", "spectracheck_session_id"),
        Index("ix_compound_batches_dossier", "regulatory_dossier_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compound_id: Mapped[int] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="CASCADE"),
        index=True,
    )
    batch_code: Mapped[str] = mapped_column(String(160))
    lot_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    reaction_experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("reaction_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    spectracheck_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("spectracheck_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    regulatory_dossier_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulatory_dossiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    purity_method: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class SampleAliquotORM(Base):
    __tablename__ = "sample_aliquots"
    __table_args__ = (
        Index("ix_sample_aliquots_batch_status", "batch_id", "status"),
        Index("ix_sample_aliquots_sample_id", "sample_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("compound_batches.id", ondelete="CASCADE"),
        index=True,
    )
    sample_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    aliquot_code: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompoundRelationshipORM(Base):
    __tablename__ = "compound_relationships"
    __table_args__ = (
        Index("ix_compound_relationships_source", "source_compound_id", "relationship_type"),
        Index("ix_compound_relationships_target", "target_compound_id", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_compound_id: Mapped[int] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="CASCADE"),
        index=True,
    )
    target_compound_id: Mapped[int] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="CASCADE"),
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(64), index=True)
    confidence_label: Mapped[str] = mapped_column(String(32), default="requires_review", index=True)
    evidence_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class CompoundEvidenceLinkORM(Base):
    __tablename__ = "compound_evidence_links"
    __table_args__ = (
        Index("ix_compound_evidence_links_compound", "compound_id", "resource_type"),
        Index("ix_compound_evidence_links_batch", "batch_id", "resource_type"),
        Index("ix_compound_evidence_links_sample", "sample_id", "resource_type"),
        Index("ix_compound_evidence_links_resource", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_entities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_batches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sample_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="linked", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ScientificKnowledgeGraphEdgeORM(Base):
    __tablename__ = "scientific_knowledge_graph_edges"
    __table_args__ = (
        Index("ix_skg_edges_source", "source_type", "source_id"),
        Index("ix_skg_edges_target", "target_type", "target_id"),
        Index("ix_skg_edges_relation", "relation_type"),
        Index("ix_skg_edges_evidence_link", "evidence_link_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(160), index=True)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(160), index=True)
    relation_type: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confidence_label: Mapped[str] = mapped_column(String(32), default="requires_review", index=True)
    evidence_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound_evidence_links.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AIEvidenceItemORM(Base):
    __tablename__ = "ai_evidence_items"
    __table_args__ = (
        Index("ix_ai_evidence_items_module_status", "module", "status"),
        Index("ix_ai_evidence_items_entity", "entity_type", "entity_id"),
        Index("ix_ai_evidence_items_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="unknown")
    summary: Mapped[str] = mapped_column(Text, default="")
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AuditEventORM(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created", "created_at"),
        Index("ix_audit_events_type_created", "event_type", "created_at"),
        # Tamper-evident chain monotonicity guard (Prompt 10): UNIQUE forces a forked
        # chain to fail at INSERT on both Postgres and SQLite (the concurrency backstop).
        Index("ux_audit_events_chain_seq", "chain_seq", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    # --- Tamper-evident hash chain (Prompt 10) ---
    # All nullable: legacy rows pre-date the chain (chain_seq IS NULL => pre-chain, skipped
    # by the verifier). New rows are auto-populated by the before_flush listener in
    # audit_chain.py. chain_seq is a dedicated monotonic ordering key (not id, which is only
    # known post-flush); chain_ts is a server-trusted timestamp captured + hashed at seal
    # time (created_at stays the app clock for back-compat). String(71) = "sha256:" + 64 hex.
    chain_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    chain_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    actor_user: Mapped[UserORM | None] = relationship(back_populates="audit_events")


class AuditCheckpointORM(Base):
    """Periodic signed anchor over the audit hash chain (Prompt 10). Each row attests that
    rows ``from_seq..tip_seq`` had tip ``entry_hash == tip_hash`` at trusted ``anchored_at``,
    sealed with an HMAC over the canonical anchor payload. Forging history then requires forging
    every overlapping anchor's HMAC — which needs the audit signing key."""

    __tablename__ = "audit_checkpoints"
    __table_args__ = (
        Index("ix_audit_checkpoints_created", "created_at"),
        UniqueConstraint("tip_seq", name="uq_audit_checkpoints_tip_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    anchored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    from_seq: Mapped[int] = mapped_column(Integer)
    tip_seq: Mapped[int] = mapped_column(Integer)
    tip_hash: Mapped[str] = mapped_column(String(71))
    row_count: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(String(80))  # "hmac-sha256:" (12) + 64 hex = 76
    key_id: Mapped[str] = mapped_column(String(32))


class AuditChainHeadORM(Base):
    """Signed high-water mark of the audit chain (Prompt 10). A singleton (id=1) updated on every
    append with the current max chain_seq + tip entry_hash, HMAC-signed. Verification compares it
    to the live MAX(chain_seq): deleting the most-recent (as-yet-unanchored) rows lowers the live
    max below this signed mark, so tail-truncation is detected — and the mark cannot be lowered
    without the signing key."""

    __tablename__ = "audit_chain_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1 (singleton)
    max_seq: Mapped[int] = mapped_column(Integer)
    tip_hash: Mapped[str] = mapped_column(String(71))
    signature: Mapped[str] = mapped_column(String(80))  # HMAC over (max_seq, tip_hash)
    key_id: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppMetricDailyORM(Base):
    __tablename__ = "app_metrics_daily"
    __table_args__ = (UniqueConstraint("metric_date", name="uq_app_metrics_daily_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    analyses_count: Mapped[int] = mapped_column(Integer, default=0)
    jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    overrides_count: Mapped[int] = mapped_column(Integer, default=0)
    hours_saved_estimate: Mapped[float] = mapped_column(Float, default=0.0)
