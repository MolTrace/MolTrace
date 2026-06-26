"""Per-tenant + per-route API rate limiting (Security Prompt 16).

The enforceable core of P16's abuse protection: an in-process **token-bucket** limiter keyed by
``(principal | client-ip) : route-template``, with tighter limits on the abuse-prone unauthenticated
auth endpoints. It is invoked from the single router choke point (``_baseline_access_gate`` in
api.py), so it reuses the already-resolved ``AccessContext`` (no duplicate token decode) and covers
both public and authenticated routes.

Design choices (grounded in the deployment):
* **In-process store.** Render runs a single uvicorn worker (no ``--workers`` in render.yaml), so a
  per-process dict of buckets is consistent for all traffic today. The store sits behind a small
  ``RateLimitStore`` protocol so a Redis-backed store can drop in unchanged IF the deploy ever goes
  multi-worker — see ``docs/security/waf_edge_runbook.md``. No new dependency is added.
* **Tenant == user today.** ``AccessContext`` carries no org/tenant id (the product runs
  single-tenant-per-user), so the per-user key *is* the per-tenant key; the key builder is the one
  place to widen to ``org:{id}`` when an org id lands on the request.
* **Fail-open.** Any internal error in the limiter must never 500 a legitimate request — only an
  exceeded bucket raises (429). Settings-gated and **default-off** so existing tests / local dev are
  unaffected; production turns it on via ``RATE_LIMIT_ENABLED``.
* **Auditable.** A throttle emits a ``SecurityEvent(event_type="rate_limit")`` — best-effort and
  de-duplicated to ~once per key per window to avoid a DB-write amplification vector.

These controls *support* OWASP API4:2023 (Unrestricted Resource Consumption); the network-edge WAF
is a separate, documented control (Render has none) — see the runbook.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from fastapi import HTTPException

if TYPE_CHECKING:
    from fastapi import Request

    from .api import AccessContext
    from .settings import Settings


# --------------------------------------------------------------------------- route policy


@dataclass(frozen=True)
class RoutePolicy:
    limit: int  # sustained requests per window
    window_s: float
    scope: str  # "auth" | "default" — informational, surfaced in the abuse signal


# First matching prefix wins. Unauthenticated auth endpoints get tight limits (credential-stuffing /
# enumeration / reset-spam defense); everything else uses the generous default-per-minute setting.
_SENSITIVE_PREFIXES: tuple[tuple[str, RoutePolicy], ...] = (
    # Keep in sync with the real public /auth/* routes (PUBLIC_ROUTE_PATHS) — a drift-guard test
    # asserts every public auth route resolves to scope="auth" rather than the generous default.
    ("/auth/login", RoutePolicy(10, 60.0, "auth")),
    ("/auth/sign-in", RoutePolicy(10, 60.0, "auth")),
    ("/auth/register", RoutePolicy(5, 60.0, "auth")),
    ("/auth/sign-up", RoutePolicy(5, 60.0, "auth")),
    ("/auth/request-password-reset", RoutePolicy(5, 60.0, "auth")),
    ("/auth/request-email-verification", RoutePolicy(5, 60.0, "auth")),
    ("/auth/reset-password", RoutePolicy(5, 60.0, "auth")),
    ("/auth/verify", RoutePolicy(10, 60.0, "auth")),  # covers /auth/verify-email
    ("/auth/step-up", RoutePolicy(20, 60.0, "auth")),
    ("/auth/mfa", RoutePolicy(20, 60.0, "auth")),
)


def _route_template(request: Request) -> str:
    """The route's path TEMPLATE (e.g. ``/reviews/{analysis_id}/approve``) so every id shares one
    bucket; falls back to the concrete path for unmatched routes."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


def _policy_for(path: str, settings: Settings) -> RoutePolicy:
    for prefix, policy in _SENSITIVE_PREFIXES:
        if path.startswith(prefix):
            return policy
    default = int(getattr(settings, "rate_limit_default_per_minute", 300))
    return RoutePolicy(default, 60.0, "default")


# --------------------------------------------------------------------------- token-bucket store


@dataclass
class _Bucket:
    tokens: float
    last: float
    last_event: float = 0.0


class RateLimitStore(Protocol):
    def consume(
        self, key: str, *, limit: int, window_s: float, burst: float, now: float
    ) -> tuple[bool, float, int]: ...

    def should_emit(self, key: str, *, now: float, window_s: float) -> bool: ...


# Bound the bucket map so an attacker rotating the IP/key can't grow it without limit (a
# memory-exhaustion vector). Eviction drops idle (fully-refilled) buckets first — harmless, since a
# missing key just starts fresh-full — then the oldest-touched to hold the ceiling.
_MAX_BUCKETS = 100_000
_IDLE_EVICT_SECONDS = 300.0


class InProcessTokenBucketStore:
    """Thread-safe per-process token buckets. capacity = ``limit*burst``; refill = ``limit/window``.
    O(1) memory per key (tokens + last-refill timestamp); the key map is bounded
    (see ``_MAX_BUCKETS``)."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _evict_locked(self, now: float) -> None:
        if len(self._buckets) <= _MAX_BUCKETS:
            return
        cutoff = now - _IDLE_EVICT_SECONDS
        for key in [k for k, b in self._buckets.items() if b.last < cutoff]:
            del self._buckets[key]
        if len(self._buckets) > _MAX_BUCKETS:
            # Still over (active flood from many distinct keys — the edge WAF's job): drop the
            # oldest-touched to hold the ceiling. Bounds memory; may reset a few keys' limits.
            overflow = len(self._buckets) - _MAX_BUCKETS
            for key in sorted(self._buckets, key=lambda k: self._buckets[k].last)[:overflow]:
                del self._buckets[key]

    def consume(
        self, key: str, *, limit: int, window_s: float, burst: float, now: float
    ) -> tuple[bool, float, int]:
        capacity = max(1.0, limit * burst)
        refill_rate = limit / window_s if window_s > 0 else float(limit)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._evict_locked(now)
                bucket = _Bucket(tokens=capacity, last=now)
                self._buckets[key] = bucket
            bucket.tokens = min(capacity, bucket.tokens + (now - bucket.last) * refill_rate)
            bucket.last = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0, int(bucket.tokens)
            retry_after = (1.0 - bucket.tokens) / refill_rate if refill_rate > 0 else window_s
            return False, retry_after, 0

    def should_emit(self, key: str, *, now: float, window_s: float) -> bool:
        """De-dup the abuse signal to ~once per key per window (caps DB writes under a flood)."""
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return True
            if now - bucket.last_event >= window_s:
                bucket.last_event = now
                return True
            return False


def _get_store(request: Request) -> InProcessTokenBucketStore:
    store = getattr(request.app.state, "_rate_limit_store", None)
    if store is None:
        store = InProcessTokenBucketStore()
        request.app.state._rate_limit_store = store
    return store


# --------------------------------------------------------------------------- key resolution


def _client_ip(request: Request, settings: Settings) -> str:
    # Behind Render's proxy, request.client.host is the proxy; trust the first X-Forwarded-For hop
    # only when explicitly configured (TRUST_FORWARDED_FOR) so the header can't be spoofed off-prod.
    if getattr(settings, "rate_limit_trust_forwarded_for", False):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
    client = request.client
    return client.host if client is not None else "unknown"


_SENTINEL_UNLIMITED = None


def _resolve_key(request: Request, context: AccessContext | None, path: str, settings: Settings):
    """Return the bucket key, or None for an unlimited principal (system api key / admin)."""
    if context is not None:
        if context.system_api_key:
            return _SENTINEL_UNLIMITED
        user = context.user
        if user is not None:
            if getattr(user, "is_admin", False):
                return _SENTINEL_UNLIMITED
            return f"user:{user.id}:{path}"
    return f"ip:{_client_ip(request, settings)}:{path}"


# --------------------------------------------------------------------------- enforcement


def _enforce_body_size(request: Request, settings: Settings) -> None:
    """Reject an oversized request body (413) for non-multipart requests — a centralized guard
    against huge JSON payloads (OWASP API4). Gated on ``max_request_body_bytes`` (0 = off).
    Multipart uploads are EXEMPT — they have their own caps and are large by design."""
    cap = int(getattr(settings, "max_request_body_bytes", 0) or 0)
    if cap <= 0:
        return
    if request.headers.get("content-type", "").startswith("multipart/"):
        return
    content_length = request.headers.get("content-length")
    if content_length is None:
        # No declared length. A chunked (Transfer-Encoding) non-multipart body can't be size-checked
        # up-front, so fail closed for the guard when a cap is set rather than let it stream past.
        if "chunked" in request.headers.get("transfer-encoding", "").lower():
            raise HTTPException(
                status_code=413,
                detail="Chunked request body not permitted — its size cannot be verified.",
            )
        return
    try:
        declared = int(content_length)
    except ValueError:
        return
    if declared > cap:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (limit {cap} bytes).",
        )


def enforce(request: Request, context: AccessContext | None) -> None:
    """Apply request limits. The body-size guard runs whenever ``max_request_body_bytes`` is set;
    the rate limiter is also gated on ``rate_limit_enabled``. Raises 413 on an oversized body and
    429 (with ``Retry-After`` + ``X-RateLimit-*`` headers) when the bucket is empty. Fail-open: an
    internal error is swallowed so the limiter can never 500 a request."""
    settings = request.app.state.settings
    _enforce_body_size(request, settings)
    if not getattr(settings, "rate_limit_enabled", False):
        return
    try:
        path = _route_template(request)
        key = _resolve_key(request, context, path, settings)
        if key is None:
            return  # unlimited principal
        policy = _policy_for(path, settings)
        burst = float(getattr(settings, "rate_limit_burst_multiplier", 2.0))
        store = _get_store(request)
        now = time.monotonic()
        allowed, retry_after, remaining = store.consume(
            key, limit=policy.limit, window_s=policy.window_s, burst=burst, now=now
        )
    except HTTPException:
        raise
    except Exception:
        # Fail-open: a limiter bug must never break a legitimate request.
        return
    if allowed:
        return
    retry_seconds = max(1, int(retry_after + 0.999))
    _emit_throttle_event(request, context, path, policy, store, now)
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded — slow down and retry after the indicated interval.",
        headers={
            "Retry-After": str(retry_seconds),
            "X-RateLimit-Limit": str(policy.limit),
            "X-RateLimit-Remaining": str(max(remaining, 0)),
            "X-RateLimit-Window": str(int(policy.window_s)),
        },
    )


def _emit_throttle_event(
    request: Request,
    context: AccessContext | None,
    path: str,
    policy: RoutePolicy,
    store: InProcessTokenBucketStore,
    now: float,
) -> None:
    """Best-effort, de-duplicated abuse signal into the SecurityEvent stream. Never raises."""
    try:
        key = _resolve_key(request, context, path, request.app.state.settings)
        if key is None or not store.should_emit(key, now=now, window_s=policy.window_s):
            return
        from . import operations_store
        from .models import SecurityEventCreate

        settings = request.app.state.settings
        user = context.user if context is not None else None
        actor = operations_store.OperationsActor(
            user_id=getattr(user, "id", None),
            email=getattr(user, "email", None),
            system_api_key=bool(context.system_api_key) if context is not None else False,
        )
        operations_store.create_security_event(
            request.app.state.session_factory,
            SecurityEventCreate(
                event_type="rate_limit",
                severity="warning",
                message=f"Rate limit exceeded on {path} ({policy.scope} policy: {policy.limit}/"
                f"{int(policy.window_s)}s).",
                resource_type="route",
                resource_id=path[:100],
                metadata_json={"scope": policy.scope, "limit": policy.limit},
            ),
            actor=actor,
            request_ip=_client_ip(request, settings),
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:
        return
