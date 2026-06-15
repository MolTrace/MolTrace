"""Embedded, Cedar-style policy-decision point (PDP) for MolTrace (Security Prompt 5).

Pure Python — no external OPA/Cedar sidecar to deploy or operate. One entry point,
:func:`authorize`, evaluates a static, **deny-by-default** :data:`POLICY_SET` with
**forbid-overrides-permit** semantics. It reproduces the *exact* prior behavior of the
formerly-scattered route gates:

* a **system** api-key operator and an **admin** user are unrestricted;
* a **user** may read/write only resources they own (``created_by_user_id == user_id``);
* everyone else is denied — which the FastAPI layer renders as a **non-leaking 404** for
  ownership-secret resources (a missing resource and an unowned one are indistinguishable)
  or a **403** for privilege/role gates.

The PDP does **no I/O**: the route/store layer resolves the resource owner and passes it in
via :class:`Resource`, so the engine is trivially unit-testable, order-independent, and fast.
It imports nothing from ``api`` (``AccessContext`` is referenced only for typing), so there is
no import cycle — ``api`` imports *from* here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # typing only — never imported at runtime, so no api<->authz cycle
    from .api import AccessContext


# --------------------------------------------------------------------------- principals


class PrincipalKind(StrEnum):
    SYSTEM = "system"  # x-api-key operator / local-auth-disabled bypass
    ADMIN = "admin"  # authenticated user with is_admin
    USER = "user"  # authenticated non-admin user
    ANONYMOUS = "anonymous"  # no credentials


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, reduced from ``api.AccessContext``.

    ``user_id`` is ``None`` for SYSTEM and ANONYMOUS. ``stepped_up`` / ``org_roles`` are
    carried for forward-compatible policies (step-up, collaboration RBAC); the
    behavior-preserving v1 policy set ignores them, so adding such rules later needs no
    signature change.
    """

    kind: PrincipalKind
    user_id: int | None = None
    email: str | None = None
    is_admin: bool = False
    stepped_up: bool = False
    org_roles: Mapping[tuple[str, int], str] = field(default_factory=dict)

    @property
    def is_unrestricted(self) -> bool:
        """System key or admin — the legacy ``owner_scope_id is None`` class."""
        return self.kind is PrincipalKind.SYSTEM or self.is_admin


# --------------------------------------------------------------------------- resources


@dataclass(frozen=True)
class Resource:
    """The thing being acted upon.

    ``type`` is a stable string ("dossier", "admin", "surveillance", "owned", …).
    ``resource_id`` is the path id (or ``None`` for collection/type-level actions).
    ``owner_id`` is the resolved owner (``created_by_user_id``) when known — ``None`` means
    "missing / unowned / not-yet-loaded", which deny-by-default treats as not-owned for a
    user-scoped caller (this is what preserves the non-leaking 404). ``attrs`` carries any
    extra fields a condition may read.
    """

    type: str
    resource_id: int | None = None
    owner_id: int | None = None
    attrs: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- action / context


@dataclass(frozen=True)
class Action:
    """A namespaced verb, e.g. ``"dossier:read"``, ``"admin:*"``, ``"surveillance:write"``.

    A policy's action set may use a trailing ``*`` wildcard on the namespace (``"admin:*"``)
    or the bare ``"*"`` to mean "any action". ``name`` is the canonical key.
    """

    name: str

    @property
    def namespace(self) -> str:
        return self.name.split(":", 1)[0]


@dataclass(frozen=True)
class Context:
    """Request-time facts a condition may consult — **never** trusted for identity.

    Deliberately minimal in v1. Identity-bearing facts (owner, scope) live on
    Principal/Resource, never here, so a client cannot smuggle an owner/tenant id through
    request context. ``extra`` is open for future conditions (IP, time-of-day, MFA age).
    """

    path: str | None = None
    method: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- policy + decision


class Effect(StrEnum):
    PERMIT = "permit"
    FORBID = "forbid"


# A condition is a pure predicate over the four inputs; True means the policy applies.
Condition = Callable[["Principal", "Action", "Resource", "Context"], bool]


@dataclass(frozen=True)
class Policy:
    """A single Cedar-style statement.

    Applies when the principal kind, action, and resource type all match **and** the optional
    ``condition`` returns True. ``actions`` entries may be exact ("dossier:read"), a
    namespace wildcard ("admin:*"), or the bare "*". ``principal_kinds`` / ``resource_types``
    of ``None`` mean "any". A matching FORBID always beats any PERMIT (see :func:`authorize`).
    """

    id: str
    effect: Effect
    principal_kinds: frozenset[PrincipalKind] | None  # None = any
    actions: frozenset[str]  # exact, "ns:*", or "*"
    resource_types: frozenset[str] | None  # None = any
    condition: Condition | None = None
    description: str = ""


@dataclass(frozen=True)
class Decision:
    """Result of :func:`authorize`.

    ``allowed`` is the only bit the route layer needs; ``reason`` / ``matched_policy_id`` are
    for audit/debug. ``effect`` distinguishes an explicit FORBID from a default-deny (no
    matching permit) — both yield ``allowed=False``.
    """

    allowed: bool
    reason: str
    matched_policy_id: str | None = None
    effect: Effect | None = None  # None => default deny (no policy matched)


# --------------------------------------------------------------------------- evaluation


def _action_matches(policy_actions: frozenset[str], action: Action) -> bool:
    if "*" in policy_actions or action.name in policy_actions:
        return True
    return f"{action.namespace}:*" in policy_actions


def _policy_applies(
    policy: Policy, prin: Principal, act: Action, res: Resource, ctx: Context
) -> bool:
    if policy.principal_kinds is not None and prin.kind not in policy.principal_kinds:
        return False
    if not _action_matches(policy.actions, act):
        return False
    if policy.resource_types is not None and res.type not in policy.resource_types:
        return False
    if policy.condition is not None and not policy.condition(prin, act, res, ctx):
        return False
    return True


def authorize(
    principal: Principal,
    action: Action,
    resource: Resource,
    context: Context | None = None,
    *,
    policies: Sequence[Policy] = (),
) -> Decision:
    """The single decision point. Deny-by-default; forbid-overrides-permit; order-independent.

    Cedar semantics: gather matching policies; **any** FORBID → Deny; else **any** PERMIT →
    Allow; else (no permit) → default Deny. FORBID always wins regardless of position, so the
    policy set is composable and order-free. ``policies`` defaults to :data:`POLICY_SET` so
    callers pass only the four facts. This never raises on a normal deny — it returns a
    Decision; the *route* layer maps Deny to 404/403.
    """
    ctx = context or Context()
    pols = policies or POLICY_SET
    permit: Policy | None = None
    for policy in pols:
        if not _policy_applies(policy, principal, action, resource, ctx):
            continue
        if policy.effect is Effect.FORBID:
            return Decision(False, f"forbidden by {policy.id}", policy.id, Effect.FORBID)
        if permit is None:
            permit = policy
    if permit is not None:
        return Decision(True, f"permitted by {permit.id}", permit.id, Effect.PERMIT)
    return Decision(False, "default deny (no matching permit)", None, None)


# --------------------------------------------------------------------------- adapter


def principal_from_access_context(context: AccessContext) -> Principal:
    """Bridge ``api.AccessContext`` → :class:`Principal`, mirroring the legacy
    ``_user_scope_for_context`` reduction exactly: ``system_api_key`` → SYSTEM;
    ``user.is_admin`` → ADMIN; an authenticated user → USER; neither → ANONYMOUS.

    Reads only duck-typed attributes, so it needs no runtime import of ``api``.
    """
    if context.system_api_key:
        return Principal(kind=PrincipalKind.SYSTEM, stepped_up=True)
    user = context.user
    if user is None:
        return Principal(kind=PrincipalKind.ANONYMOUS)
    if user.is_admin:
        return Principal(
            kind=PrincipalKind.ADMIN, user_id=user.id, email=user.email, is_admin=True
        )
    return Principal(kind=PrincipalKind.USER, user_id=user.id, email=user.email)


# --------------------------------------------------------------------------- conditions


def _owns_resource(prin: Principal, act: Action, res: Resource, ctx: Context) -> bool:
    """The dossier-ownership predicate, lifted verbatim from ``dossier_owned_by``:
    a user-scoped caller owns the resource only if it exists **and**
    ``res.owner_id == prin.user_id``. ``owner_id is None`` (missing / unowned / NULL-owner /
    orphaned child) → False, which preserves the non-leaking 404. (Unrestricted callers never
    reach this — they match their own ``*`` permit first.)
    """
    if prin.user_id is None:
        return False
    return res.owner_id is not None and res.owner_id == prin.user_id


# --------------------------------------------------------------------------- policy set


POLICY_SET: tuple[Policy, ...] = (
    # 1. SYSTEM (x-api-key operator / local-auth-disabled) is unrestricted on everything.
    Policy(
        id="permit-system-all",
        effect=Effect.PERMIT,
        principal_kinds=frozenset({PrincipalKind.SYSTEM}),
        actions=frozenset({"*"}),
        resource_types=None,
        description="System api key / local-dev operator bypasses every gate.",
    ),
    # 2. ADMIN (global super-role is_admin) is unrestricted on everything.
    Policy(
        id="permit-admin-all",
        effect=Effect.PERMIT,
        principal_kinds=frozenset({PrincipalKind.ADMIN}),
        actions=frozenset({"*"}),
        resource_types=None,
        description="is_admin user has unrestricted scope.",
    ),
    # 3. A dossier owner may read+write their own dossier and its dossier-typed children
    #    (Annex 22 ai-decisions own the parent dossier).
    Policy(
        id="permit-owner-dossier-rw",
        effect=Effect.PERMIT,
        principal_kinds=frozenset({PrincipalKind.USER}),
        actions=frozenset(
            {
                "dossier:read",
                "dossier:write",
                "ai_decision:read",
                "ai_decision:write",
                "ai_decision:review",
            }
        ),
        resource_types=frozenset({"dossier"}),
        condition=_owns_resource,
        description="User reads/writes only dossiers they created (dossier_owned_by).",
    ),
    # 4. Generic owner pattern for the other inline-scoped resources (projects, FID runs,
    #    analyses, raw archives, …) — same created_by/owner_id == user_id rule.
    Policy(
        id="permit-owner-owned-rw",
        effect=Effect.PERMIT,
        principal_kinds=frozenset({PrincipalKind.USER}),
        actions=frozenset({"owned:read", "owned:write"}),
        resource_types=None,
        condition=_owns_resource,
        description="User reads/writes only resources they own (_user_scope_for_context).",
    ),
    # 5. Any authenticated user (or admin; system is covered by #1) may read surveillance.
    Policy(
        id="permit-authenticated-surveillance-read",
        effect=Effect.PERMIT,
        principal_kinds=frozenset({PrincipalKind.USER, PrincipalKind.ADMIN}),
        actions=frozenset({"surveillance:read"}),
        resource_types=frozenset({"surveillance"}),
        description="Surveillance reads are open to any authenticated caller.",
    ),
    # 6. Baseline authenticated floor: any logged-in principal passes 'authenticated:access'.
    #    ANONYMOUS is deliberately absent → default-deny → the route layer renders 401.
    Policy(
        id="permit-authenticated-access",
        effect=Effect.PERMIT,
        principal_kinds=frozenset({PrincipalKind.USER, PrincipalKind.ADMIN}),
        actions=frozenset({"authenticated:access"}),
        resource_types=None,
        description="Floor: authenticated principals pass the baseline gate.",
    ),
    # NOTE: there is intentionally NO permit for a USER on admin:* / surveillance:write /
    # sso:manage / scim_token:manage / tenant:admin. With only #1 and #2 granting those, a
    # USER hits default-deny → the route layer renders 403; ANONYMOUS hits default-deny
    # everywhere → 401. No explicit FORBID is needed: today's model denies by *absence* of a
    # permit, not by override. The forbid machinery exists (and is tested) for future rules
    # like "forbid disabled users" or "forbid writes to a frozen dossier".
)
