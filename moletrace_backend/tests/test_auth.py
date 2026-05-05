from tempfile import mkdtemp

from fastapi import HTTPException
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    admin_demote_user,
    create_app,
    login_json,
    register,
    request_email_verification,
    request_password_reset,
    reset_password,
    verify_email,
)
from nmrcheck.database import init_db
from nmrcheck.models import EmailActionRequest, PasswordResetConfirm, UserCreate, UserLogin
from nmrcheck.settings import Settings


def _build_request(
    *,
    require_verified_email: bool,
    admin_emails: tuple[str, ...] = ("admin@example.com",),
) -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-auth-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/auth.sqlite3",
            require_verified_email=require_verified_email,
            api_key="test-key",
            admin_emails=admin_emails,
        )
    )
    init_db(app.state.session_factory)
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/auth/test",
        "query_string": b"",
    }
    return Request(scope)


def test_register_login_and_verification_reset_flow() -> None:
    request = _build_request(require_verified_email=True)
    email = "chemist@example.com"
    password = "StrongPass123!"
    new_password = "EvenStrongerPass456!"

    user = register(UserCreate(email=email, password=password), request)
    assert user.email == email
    assert user.is_verified is False

    try:
        login_json(UserLogin(email=email, password=password), request)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected login to fail before email verification.")

    verification = request_email_verification(EmailActionRequest(email=email), request)
    assert verification.token
    verified = verify_email(verification.token, request)
    assert "verified" in verified.detail.lower()

    login = login_json(UserLogin(email=email, password=password), request)
    assert login.user.is_verified is True
    assert login.access_token

    reset_preview = request_password_reset(EmailActionRequest(email=email), request)
    assert reset_preview.token
    reset_result = reset_password(
        PasswordResetConfirm(token=reset_preview.token, new_password=new_password),
        request,
    )
    assert "successful" in reset_result.detail.lower()

    relogin = login_json(UserLogin(email=email, password=new_password), request)
    assert relogin.user.email == email


def test_admin_email_stays_admin_after_demote_and_relogin() -> None:
    request = _build_request(require_verified_email=False)
    email = "admin@example.com"
    password = "AdminPass123!"

    admin_user = register(UserCreate(email=email, password=password), request)
    assert admin_user.is_admin is True

    demoted = admin_demote_user(
        admin_user.id,
        request,
        AccessContext(user=admin_user),
    )
    assert demoted.is_admin is False

    relogin = login_json(UserLogin(email=email, password=password), request)
    assert relogin.user.is_admin is True
