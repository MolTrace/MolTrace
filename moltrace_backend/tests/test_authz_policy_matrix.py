"""Deny-by-default policy matrix for the embedded PDP (Security Prompt 5), tier 1.

Pure-logic tests over ``nmrcheck.authz.authorize`` — no app, no DB. They pin the principal ×
action × resource truth table that reproduces the legacy scattered gates exactly:
system/admin unrestricted; a user owns only their own resources; everyone else default-denies;
forbid overrides permit; and ``principal_from_access_context`` reduces an AccessContext the same
way the old ``_user_scope_for_context`` did.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nmrcheck import authz
from nmrcheck.authz import Action, Effect, Policy, Principal, PrincipalKind, Resource

SYSTEM = Principal(PrincipalKind.SYSTEM)
ADMIN = Principal(PrincipalKind.ADMIN, user_id=9, is_admin=True)
OWNER = Principal(PrincipalKind.USER, user_id=1)
OTHER = Principal(PrincipalKind.USER, user_id=2)
ANON = Principal(PrincipalKind.ANONYMOUS)

DOSSIER = Resource("dossier", resource_id=10, owner_id=1)  # owned by user 1
OWNED = Resource("project", resource_id=5, owner_id=1)  # generic owned resource


def _allowed(prin: Principal, action: str, res: Resource) -> bool:
    return authz.authorize(prin, Action(action), res).allowed


# --------------------------------------------------------------------------- #
# Dossier read/write (owner_id == 1): owner + privileged allow, others deny
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "prin,allowed",
    [(SYSTEM, True), (ADMIN, True), (OWNER, True), (OTHER, False), (ANON, False)],
)
@pytest.mark.parametrize("action", ["dossier:read", "dossier:write"])
def test_dossier_rw(prin: Principal, allowed: bool, action: str) -> None:
    assert _allowed(prin, action, DOSSIER) is allowed


@pytest.mark.parametrize(
    "prin,allowed",
    [(SYSTEM, True), (ADMIN, True), (OWNER, True), (OTHER, False), (ANON, False)],
)
@pytest.mark.parametrize("action", ["ai_decision:read", "ai_decision:write", "ai_decision:review"])
def test_ai_decision_inherits_dossier_ownership(
    prin: Principal, allowed: bool, action: str
) -> None:
    assert _allowed(prin, action, DOSSIER) is allowed


# --------------------------------------------------------------------------- #
# Admin/privilege actions: only system + admin
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "prin,allowed",
    [(SYSTEM, True), (ADMIN, True), (OWNER, False), (OTHER, False), (ANON, False)],
)
@pytest.mark.parametrize("action", ["admin:read", "admin:write", "surveillance:write"])
def test_privilege_actions_admin_only(prin: Principal, allowed: bool, action: str) -> None:
    res = Resource("admin") if action.startswith("admin") else Resource("surveillance")
    assert _allowed(prin, action, res) is allowed


# --------------------------------------------------------------------------- #
# Surveillance read: any authenticated principal; anonymous denied
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "prin,allowed",
    [(SYSTEM, True), (ADMIN, True), (OWNER, True), (OTHER, True), (ANON, False)],
)
def test_surveillance_read_open_to_authenticated(prin: Principal, allowed: bool) -> None:
    assert _allowed(prin, "surveillance:read", Resource("surveillance")) is allowed


# --------------------------------------------------------------------------- #
# Generic owned resources: owner + privileged allow; non-owner + anon deny
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "prin,allowed",
    [(SYSTEM, True), (ADMIN, True), (OWNER, True), (OTHER, False), (ANON, False)],
)
@pytest.mark.parametrize("action", ["owned:read", "owned:write"])
def test_owned_resource(prin: Principal, allowed: bool, action: str) -> None:
    assert _allowed(prin, action, OWNED) is allowed


# --------------------------------------------------------------------------- #
# Authenticated floor: any logged-in principal; anonymous denied (-> 401)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "prin,allowed",
    [(SYSTEM, True), (ADMIN, True), (OWNER, True), (OTHER, True), (ANON, False)],
)
def test_authenticated_access_floor(prin: Principal, allowed: bool) -> None:
    assert _allowed(prin, "authenticated:access", Resource("any")) is allowed


# --------------------------------------------------------------------------- #
# Non-leaking branch at the PDP: missing/NULL-owner dossier (owner_id None)
# --------------------------------------------------------------------------- #
def test_missing_or_null_owner_dossier_is_non_leaking() -> None:
    ghost = Resource("dossier", resource_id=999, owner_id=None)
    assert _allowed(OWNER, "dossier:read", ghost) is False  # owner sees nothing -> 404
    assert _allowed(OTHER, "dossier:read", ghost) is False  # non-owner -> identical 404
    assert _allowed(SYSTEM, "dossier:read", ghost) is True  # privileged still sees it
    assert _allowed(ADMIN, "dossier:read", ghost) is True


# --------------------------------------------------------------------------- #
# Deny-by-default: an unknown action is denied for everyone but the '*' holders
# --------------------------------------------------------------------------- #
def test_default_deny_unknown_action() -> None:
    assert _allowed(OWNER, "frobnicate:read", DOSSIER) is False
    assert _allowed(OTHER, "frobnicate:read", DOSSIER) is False
    assert _allowed(ANON, "frobnicate:read", DOSSIER) is False
    assert _allowed(SYSTEM, "frobnicate:read", DOSSIER) is True  # system '*' still applies
    assert _allowed(ADMIN, "frobnicate:read", DOSSIER) is True


def test_default_deny_unknown_resource_type_for_user() -> None:
    # A user has no permit for an unmodeled resource type -> default deny.
    assert _allowed(OWNER, "owned:read", Resource("mystery", owner_id=1)) is True  # owned:* any type
    assert _allowed(OWNER, "mystery:read", Resource("mystery", owner_id=1)) is False


# --------------------------------------------------------------------------- #
# Forbid overrides permit (machinery present for future rules)
# --------------------------------------------------------------------------- #
def test_forbid_overrides_permit() -> None:
    forbid = Policy(
        id="forbid-test",
        effect=Effect.FORBID,
        principal_kinds=frozenset({PrincipalKind.SYSTEM}),
        actions=frozenset({"*"}),
        resource_types=None,
    )
    decision = authz.authorize(
        SYSTEM, Action("dossier:read"), DOSSIER, policies=(forbid, *authz.POLICY_SET)
    )
    assert decision.allowed is False
    assert decision.effect is Effect.FORBID


def test_forbid_wins_regardless_of_order() -> None:
    forbid = Policy(
        "f", Effect.FORBID, frozenset({PrincipalKind.USER}), frozenset({"dossier:read"}), None
    )
    # forbid AFTER the permits still wins (set-based, order-independent)
    decision = authz.authorize(
        OWNER, Action("dossier:read"), DOSSIER, policies=(*authz.POLICY_SET, forbid)
    )
    assert decision.allowed is False and decision.effect is Effect.FORBID


def test_empty_policy_set_is_total_deny() -> None:
    decision = authz.authorize(SYSTEM, Action("admin:read"), Resource("admin"), policies=(_NOOP,))
    assert decision.allowed is False and decision.effect is None  # default deny


_NOOP = Policy(
    "noop", Effect.PERMIT, frozenset({PrincipalKind.ANONYMOUS}), frozenset({"nothing"}), None
)


# --------------------------------------------------------------------------- #
# AccessContext -> Principal adapter mirrors the legacy reduction exactly
# --------------------------------------------------------------------------- #
def test_principal_from_access_context_system() -> None:
    ctx = SimpleNamespace(system_api_key=True, user=None)
    prin = authz.principal_from_access_context(ctx)
    assert prin.kind is PrincipalKind.SYSTEM and prin.is_unrestricted is True


def test_principal_from_access_context_admin() -> None:
    user = SimpleNamespace(id=3, email="a@x.com", is_admin=True)
    ctx = SimpleNamespace(system_api_key=False, user=user)
    prin = authz.principal_from_access_context(ctx)
    assert prin.kind is PrincipalKind.ADMIN and prin.is_unrestricted is True
    assert prin.user_id == 3


def test_principal_from_access_context_user() -> None:
    user = SimpleNamespace(id=7, email="u@x.com", is_admin=False)
    ctx = SimpleNamespace(system_api_key=False, user=user)
    prin = authz.principal_from_access_context(ctx)
    assert prin.kind is PrincipalKind.USER and prin.is_unrestricted is False
    assert prin.user_id == 7


def test_principal_from_access_context_anonymous() -> None:
    ctx = SimpleNamespace(system_api_key=False, user=None)
    prin = authz.principal_from_access_context(ctx)
    assert prin.kind is PrincipalKind.ANONYMOUS and prin.is_unrestricted is False
    assert prin.user_id is None
