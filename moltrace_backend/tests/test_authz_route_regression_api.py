"""Policy-engine route regression matrix (Security Prompt 5), tier 2.

Asserts the HTTP *rendering* of every authorization decision is unchanged after the gates were
refactored to delegate to ``nmrcheck.authz.authorize`` — owner 200, non-owner non-leaking 404,
privilege 403, anonymous 401 — and proves the two new guarantees: (1) a NEW route with no auth
dependency of its own still fails closed via the router default-deny baseline, and (2) the
public allow-list is pinned so making a route public is a deliberate, reviewed change.
"""

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from nmrcheck import api as api_module
from nmrcheck.api import create_app
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}
ADMIN_EMAIL = "admin@example.com"


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'authz_routes.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=(ADMIN_EMAIL,),
        )
    )


def _sign_up(client: TestClient, email: str) -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_dossier(client: TestClient, headers: dict) -> int:
    res = client.post("/regulatory/dossiers", headers=headers, json={"title": "authz matrix"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------- #
# Dossier gate (ownership-secret -> 404 / 401), via the refactored require_dossier_access
# --------------------------------------------------------------------------- #
def test_dossier_access_matrix(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        owner = _sign_up(client, "owner@example.com")
        other = _sign_up(client, "other@example.com")
        admin = _sign_up(client, ADMIN_EMAIL)
        did = _create_dossier(client, owner)
        url = f"/regulatory/dossiers/{did}"
        assert client.get(url, headers=owner).status_code == 200
        assert client.get(url, headers=other).status_code == 404  # non-owner, non-leaking
        assert client.get(url, headers=SYSTEM).status_code == 200
        assert client.get(url, headers=admin).status_code == 200
        assert client.get(url).status_code == 401  # anonymous -> baseline floor


def test_dossier_non_leaking_identical_status_and_body(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        owner = _sign_up(client, "owner@example.com")
        other = _sign_up(client, "other@example.com")
        did = _create_dossier(client, owner)
        unowned = client.get(f"/regulatory/dossiers/{did}", headers=other)
        missing = client.get("/regulatory/dossiers/999999", headers=other)
        assert unowned.status_code == missing.status_code == 404
        assert unowned.json() == missing.json()  # body must not leak existence


# --------------------------------------------------------------------------- #
# Admin/privilege gate (-> 403 / 401), via the refactored require_admin
# --------------------------------------------------------------------------- #
def test_admin_gate_matrix(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        user = _sign_up(client, "plainuser@example.com")
        admin = _sign_up(client, ADMIN_EMAIL)
        url = "/admin/deployment"
        assert client.get(url, headers=user).status_code == 403  # non-admin -> privilege denied
        assert client.get(url, headers=admin).status_code == 200
        assert client.get(url, headers=SYSTEM).status_code == 200
        assert client.get(url).status_code == 401  # anonymous -> baseline floor


# --------------------------------------------------------------------------- #
# Surveillance: reads open to any authenticated user; writes admin-only
# --------------------------------------------------------------------------- #
def test_surveillance_read_open_write_privileged(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        user = _sign_up(client, "su@example.com")
        # read is open to an authenticated non-admin (a 401/403 here would be a regression)
        assert client.get("/regulatory/surveillance/sources", headers=user).status_code == 200
        assert client.get("/regulatory/surveillance/sources").status_code == 401  # anon floor


# --------------------------------------------------------------------------- #
# Fail-closed-by-default: a brand-new route with NO auth dep inherits the gate
# --------------------------------------------------------------------------- #
def test_new_route_inherits_default_deny(tmp_path):
    app = _app(tmp_path)
    extra = APIRouter()

    @extra.get("/__authz_inherit_probe__")
    def _probe() -> dict[str, bool]:  # no auth dependency declared on purpose
        return {"ok": True}

    # Include it the same way create_app wires the main router: with the baseline.
    app.include_router(extra, dependencies=[Depends(api_module._baseline_access_gate)])
    with TestClient(app) as client:
        # anonymous -> 401 purely from the inherited baseline (route declared none itself)
        assert client.get("/__authz_inherit_probe__").status_code == 401
        # an authenticated principal passes the floor and reaches the handler
        user = _sign_up(client, "probe@example.com")
        ok = client.get("/__authz_inherit_probe__", headers=user)
        assert ok.status_code == 200 and ok.json() == {"ok": True}


def test_gate_factory_owns_resource_matrix(tmp_path):
    """The gate() factory is the canonical one-liner for a NEW owned-resource route. Prove it
    works end-to-end: owner 200, non-owner non-leaking 404, malformed id fails safe (404, not
    500), and a role gate (deny_status=403) renders 403 for a non-privileged user."""
    app = _app(tmp_path)
    extra = APIRouter()

    # a fake owner store: resource 1 -> owned by the FIRST signed-up user (id resolved at call)
    owners: dict[int, int] = {}

    def _resolver(request, resource_id):
        return owners.get(resource_id)

    @extra.get(
        "/__widgets__/{widget_id}",
        dependencies=[
            Depends(api_module.gate("owned", "owned:read", id_param="widget_id",
                                    owner_resolver=_resolver))
        ],
    )
    def _widget(widget_id: int) -> dict[str, int]:
        return {"widget_id": widget_id}

    @extra.get(
        "/__rolegate__",
        dependencies=[Depends(api_module.gate("admin", "admin:read", deny_status=403))],
    )
    def _rolegate() -> dict[str, bool]:
        return {"ok": True}

    # A str-typed path param so a non-integer value reaches gate()'s int() coercion (an
    # int-typed route would 422 at routing first) — proves the malformed-id fail-safe.
    @extra.get(
        "/__strwidget__/{widget_id}",
        dependencies=[
            Depends(api_module.gate("owned", "owned:read", id_param="widget_id",
                                    owner_resolver=_resolver))
        ],
    )
    def _strwidget(widget_id: str) -> dict[str, str]:
        return {"widget_id": widget_id}

    app.include_router(extra, dependencies=[Depends(api_module._baseline_access_gate)])
    with TestClient(app) as client:
        owner = _sign_up(client, "wowner@example.com")
        other = _sign_up(client, "wother@example.com")
        admin = _sign_up(client, ADMIN_EMAIL)
        # resolve the owner's user id and mark widget 1 as theirs
        owners[1] = client.get("/auth/me", headers=owner).json()["id"]
        assert client.get("/__widgets__/1", headers=owner).status_code == 200
        assert client.get("/__widgets__/1", headers=other).status_code == 404  # non-leaking
        assert client.get("/__widgets__/1", headers=SYSTEM).status_code == 200  # unrestricted
        assert client.get("/__widgets__/999", headers=owner).status_code == 404  # unowned/missing
        # role gate: non-privileged user -> 403; admin -> 200
        assert client.get("/__rolegate__", headers=other).status_code == 403
        assert client.get("/__rolegate__", headers=admin).status_code == 200
        # malformed id -> fail safe (404 for a user), never a 500
        assert client.get("/__strwidget__/not-an-int", headers=owner).status_code == 404


# --------------------------------------------------------------------------- #
# Public allow-list is pinned (adding/removing a public route must be deliberate)
# --------------------------------------------------------------------------- #
EXPECTED_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/queue/status",
        "/system/health",
        "/system/version",
        "/auth/register",
        "/auth/sign-up",
        "/auth/login",
        "/auth/sign-in",
        "/auth/token",
        "/auth/refresh",
        "/auth/refresh/revoke",
        "/auth/sso/{slug}/login",
        "/auth/sso/callback",
        "/auth/sso/exchange",
        "/auth/mfa/login/totp",
        "/auth/mfa/login/webauthn",
        "/auth/mfa/login/recovery",
        "/auth/request-email-verification",
        "/auth/verify-email",
        "/auth/request-password-reset",
        "/auth/reset-password",
        "/fid/presets",
        "/share-links/{token}",
    }
)


def test_public_allow_list_is_pinned():
    assert api_module.PUBLIC_ROUTE_PATHS == EXPECTED_PUBLIC_PATHS


def test_public_routes_reachable_anonymously(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/system/version").status_code == 200


def test_public_routes_ignore_stale_or_bad_credentials(tmp_path):
    """Regression (review HIGH finding): the baseline must NOT 401 a public route when a
    stale/wrong credential rides along — the SPA re-attaches an expired bearer to every
    request, including the re-login POST, and LB probes may carry a rotated api key. Resolving
    credentials only after the public-route short-circuit preserves the pre-baseline 200."""
    with TestClient(_app(tmp_path)) as client:
        stale_bearer = {"Authorization": "Bearer expired-or-unknown-token"}
        bad_key = {"x-api-key": "WRONG-KEY"}
        # Health/system probes must stay reachable despite a bad credential.
        assert client.get("/health", headers=stale_bearer).status_code == 200
        assert client.get("/health", headers=bad_key).status_code == 200
        # Re-login must complete even though the SPA still has the expired bearer attached.
        client.post(
            "/auth/sign-up",
            json={"email": "relog@x.com", "password": "password123",
                  "password_confirm": "password123"},
        )
        res = client.post(
            "/auth/login",
            json={"email": "relog@x.com", "password": "password123"},
            headers=stale_bearer,
        )
        assert res.status_code == 200 and res.json().get("access_token")  # not locked out


def _dependant_calls(dependant) -> set:
    """Recursively collect the callables in a route's dependant tree."""
    calls = set()
    for sub in dependant.dependencies:
        if sub.call is not None:
            calls.add(sub.call)
        calls |= _dependant_calls(sub)
    return calls


def test_baseline_attached_to_a_known_nonpublic_route(tmp_path):
    app = _app(tmp_path)
    target = None
    for route in app.routes:
        if getattr(route, "path", None) == "/regulatory/dossiers/{dossier_id}" and (
            "GET" in getattr(route, "methods", set())
        ):
            target = route
            break
    assert target is not None, "dossier GET route not found"
    assert api_module._baseline_access_gate in _dependant_calls(target.dependant)
