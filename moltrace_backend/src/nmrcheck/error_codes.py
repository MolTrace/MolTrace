"""Stable machine-readable error codes.

Every error response carries a ``code`` a client may branch on. ``detail`` is prose for a
human and clients must **not** parse it — the same rule the audit chain adopted when
``break_kind`` was split out of ``detail``, and for the same reason: a string written for a
person changes when someone improves the wording, and anything switching on it breaks
silently.

This formalises behaviour that already shipped rather than inventing a vocabulary. Five
codes were already travelling *inside* ``detail`` and the codebase had grown three separate
mechanisms to keep them alive:

* ``PUBLIC_MACHINE_READABLE_403_DETAILS`` — a server-side allowlist so ``module_not_licensed``
  survives 403 sanitization.
* Dedicated exception handlers for ``MFAError`` / ``SessionError`` that bypass the sanitizer
  entirely, with a comment explaining they exist to "preserve the machine code … so the SPA
  can react".
* An allowlist in the frontend's ``/api/backend`` proxy, which sanitizes 401/403 bodies and
  passes exactly four ``detail`` values through verbatim.

Three lists for one idea. A code field replaces the need for any of them to grow.

**Adding a code**: register it here with the audience it is safe for. ``public=True`` means
the code may cross a sanitized 401/403 boundary — it must therefore name a *situation*, never
a reason a permission check failed, a resource, or a user. "This plan does not include that
product" is safe; "you are not the owner of dossier 7" is not.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    """One registered code. ``public`` gates whether it may survive 401/403 sanitization."""

    code: str
    meaning: str
    public: bool = False


# --------------------------------------------------------------------------- #
# Codes that already shipped inside `detail`. Values are unchanged on purpose:
# clients branch on these strings today and must keep working.
# --------------------------------------------------------------------------- #
MODULE_NOT_LICENSED = "module_not_licensed"
STEP_UP_REQUIRED = "step_up_required"
TOKEN_EXPIRED = "token_expired"
TOKEN_INVALID = "token_invalid"
TOKEN_REUSE_DETECTED = "token_reuse_detected"

# --------------------------------------------------------------------------- #
# Upgrade state. A locked capability has four distinguishable causes and four
# different next actions; collapsing them into one 403 forces the interface to
# guess, and a wrong guess sends a user to the wrong place (buy something they
# already own, or ask an admin for something no admin can grant).
# --------------------------------------------------------------------------- #
#: The deployment does not serve this product at all. Next action: commercial.
PRODUCT_NOT_IN_PLAN = "product_not_in_plan"
#: Served by the deployment but switched off for this workspace. Next action: an
#: administrator enables it — no purchase involved.
PRODUCT_NOT_ENABLED = "product_not_enabled"
#: Enabled but a prerequisite is missing (no index configured, no corpus loaded, a
#: worker not running). Next action: finish setup; nobody needs to buy or click a
#: permission toggle.
PRODUCT_NOT_PROVISIONED = "product_not_provisioned"
#: Present and provisioned; this *user* lacks the role. Next action: ask an admin for
#: access. Deliberately says nothing about what the resource is.
ROLE_REQUIRED = "role_required"

# --------------------------------------------------------------------------- #
# Authentication situations. Each names WHAT HAPPENED to the caller's own
# submission, never why an authorization check failed — the distinction the
# module docstring draws, and the reason these are safe to publish.
#
# Before these existed the sanitizer replaced every 401 with one sentence, so a
# desktop client could not tell "that authenticator code was wrong" from "your
# session ended". Both are things the caller already knows they attempted; the
# code lets the client say so without the server writing the copy.
# --------------------------------------------------------------------------- #
#: Sign-in was refused. Deliberately does NOT distinguish a wrong password from an
#: unknown address or an unverified email — that difference is an account-existence
#: oracle, and the three sign-in sites already collapse it in their prose.
CREDENTIALS_INVALID = "credentials_invalid"
#: The org requires a second factor, the user HAS one, and this session has not used
#: it. Next action: step up.
MFA_REQUIRED = "mfa_required"
#: The org requires a second factor and the user has NONE. Next action: enrol one.
#: Split from MFA_REQUIRED for the reason upgrade_state splits its four: the two need
#: different screens, and `detail` is fixed copy now, so `code` is the only carrier.
MFA_ENROLLMENT_REQUIRED = "mfa_enrollment_required"
#: A presented factor was not accepted — TOTP, recovery code, step-up password, or a
#: passkey assertion. One code for all four on purpose: the client always knows which
#: factor it just submitted, so a per-factor code would be the server restating the
#: client's own request.
#:
#: This deliberately also covers a passkey assertion refused for a sign-count regression.
#: Naming the clone/replay detector in the denial body tells the holder of a cloned
#: credential that the clone was caught and how; the person who owns the credential is
#: told through the audit chain and the account's notification path instead, which
#: reaches the owner rather than whoever is holding the copy.
MFA_FACTOR_INVALID = "mfa_factor_invalid"
#: A capability this build can serve is switched off in this deployment. The flag's
#: NAME is deployment configuration and never goes on the wire — not in `detail`, not
#: in a header; it goes to the operator log with the correlation id.
FEATURE_NOT_ENABLED = "feature_not_enabled"

# --------------------------------------------------------------------------- #
# Generic fallbacks, so every error carries a code even before a route is
# migrated. Never let absence of a specific code mean absence of the field —
# a client that must handle "sometimes there is a code" gains nothing.
# --------------------------------------------------------------------------- #
#: A processing preset id that maps to no real engine behaviour. Split out from the
#: generic 422 because the interface has a specific, useful reaction to it — re-open
#: the preset picker on the offending control — and because the alternative was
#: leaving the valid-id list in ``detail``, where it would reach a user as engine
#: jargon (``baseline_preserve``, ``phase_preserve``, …). Not public: a 422 never
#: crosses the 401/403 sanitizer.
UNKNOWN_PROCESSING_PRESET = "unknown_processing_preset"

BAD_REQUEST = "bad_request"
UNAUTHENTICATED = "unauthenticated"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
UNPROCESSABLE = "unprocessable"
RATE_LIMITED = "rate_limited"
UNAVAILABLE = "unavailable"

REGISTRY: dict[str, ErrorCode] = {
    entry.code: entry
    for entry in (
        ErrorCode(MODULE_NOT_LICENSED, "This deployment does not serve that product.", True),
        ErrorCode(STEP_UP_REQUIRED, "A fresh authentication step is required.", True),
        ErrorCode(TOKEN_EXPIRED, "The session token has expired.", True),
        ErrorCode(TOKEN_INVALID, "The session token is not valid.", True),
        ErrorCode(
            TOKEN_REUSE_DETECTED,
            "A refresh token was replayed; the token family was revoked.",
            True,
        ),
        ErrorCode(PRODUCT_NOT_IN_PLAN, "The product is not part of this plan.", True),
        ErrorCode(PRODUCT_NOT_ENABLED, "The product is not enabled for this workspace.", True),
        ErrorCode(
            PRODUCT_NOT_PROVISIONED, "The product is enabled but not yet set up.", True
        ),
        ErrorCode(ROLE_REQUIRED, "Your role does not include this action.", True),
        ErrorCode(CREDENTIALS_INVALID, "The sign-in details were not accepted.", True),
        ErrorCode(
            MFA_REQUIRED,
            "A second authentication factor is required for this session.",
            True,
        ),
        ErrorCode(
            MFA_ENROLLMENT_REQUIRED,
            "A second authentication factor must be enrolled before continuing.",
            True,
        ),
        ErrorCode(
            MFA_FACTOR_INVALID,
            "The authentication factor presented was not accepted.",
            True,
        ),
        ErrorCode(
            FEATURE_NOT_ENABLED,
            "A feature this deployment can serve is switched off.",
            True,
        ),
        ErrorCode(
            UNKNOWN_PROCESSING_PRESET,
            "The requested processing preset is not one the engine implements.",
        ),
        ErrorCode(BAD_REQUEST, "The request could not be understood."),
        ErrorCode(UNAUTHENTICATED, "Authentication is required."),
        ErrorCode(FORBIDDEN, "Access denied."),
        ErrorCode(NOT_FOUND, "Not found."),
        ErrorCode(CONFLICT, "The request conflicts with the current state."),
        ErrorCode(UNPROCESSABLE, "The request was well-formed but could not be processed."),
        ErrorCode(RATE_LIMITED, "Too many requests."),
        ErrorCode(UNAVAILABLE, "The service is temporarily unavailable."),
    )
}

#: Codes safe to expose across a sanitized 401/403 boundary.
PUBLIC_CODES: frozenset[str] = frozenset(
    entry.code for entry in REGISTRY.values() if entry.public
)

#: Every value ``code`` may take on a sanitized 401 or 403: the public codes plus the two
#: status fallbacks, because a denial that names no particular situation still carries a code
#: (never absent — see ``code_for``). This is the enumeration that reaches the OpenAPI contract
#: and therefore the generated frontend types.
#:
#: Derived, like ``PUBLIC_CODES``. A fourth hand-maintained list of the same idea is exactly
#: what this module was written to remove.
SANITIZED_AUTH_CODES: frozenset[str] = PUBLIC_CODES | {UNAUTHENTICATED, FORBIDDEN}

_STATUS_FALLBACK: dict[int, str] = {
    400: BAD_REQUEST,
    401: UNAUTHENTICATED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    409: CONFLICT,
    422: UNPROCESSABLE,
    429: RATE_LIMITED,
}


def code_for(status_code: int, detail: object, *, stated_code: str | None = None) -> str:
    """The code for a response, preferring one the raiser already stated.

    A ``detail`` that is exactly a registered code is treated as that code — which is how
    every pre-existing raise site is picked up without editing 800 routes. Anything else
    falls back to the status, so the field is always present and a client never has to
    handle its absence.

    ``stated_code`` is for the case those two mechanisms cannot express together: a raise
    site that wants a specific code *and* a ``detail`` written for a person. Putting the
    code in ``detail`` costs the prose; writing prose costs the code. The frontend renders
    ``String(data.detail)``, so a structured ``detail`` is not a third option — it would
    reach a user as "[object Object]". An unregistered value is ignored rather than
    trusted, so this cannot mint codes that are not in the registry above.
    """

    if stated_code is not None and stated_code in REGISTRY:
        return stated_code
    if isinstance(detail, str) and detail in REGISTRY:
        return detail
    if status_code >= 500:
        return UNAVAILABLE
    return _STATUS_FALLBACK.get(status_code, BAD_REQUEST)


# --------------------------------------------------------------------------- #
# Upgrade state resolution
# --------------------------------------------------------------------------- #
def upgrade_state(
    *,
    served_by_deployment: bool,
    enabled_for_workspace: bool,
    provisioned: bool,
    user_has_role: bool,
) -> str | None:
    """Which of the four locked states applies, or ``None`` when nothing is blocking.

    Order matters and is not arbitrary — it runs outermost-first, so a caller is told the
    thing they must fix *first* rather than the last check that happened to fail. A user
    whose plan lacks the product should not be told to ask an administrator for a role;
    the role would not help.

    Each state maps to a different next action, which is the whole reason for splitting
    them: buy it, have an admin switch it on, finish setup, or request access. A single
    403 forces the interface to guess between four, and three of those guesses send the
    user somewhere that cannot help.
    """

    if not served_by_deployment:
        return PRODUCT_NOT_IN_PLAN
    if not enabled_for_workspace:
        return PRODUCT_NOT_ENABLED
    if not provisioned:
        return PRODUCT_NOT_PROVISIONED
    if not user_has_role:
        return ROLE_REQUIRED
    return None
