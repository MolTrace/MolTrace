"""Security detections + SIEM alert sink (Security Prompt 19).

Turns the immutable ``SecurityEvent`` stream + the tamper-evident audit chain into
near-real-time detections, and ships high-severity alerts to a pluggable SIEM sink.

Four detections (the prompt's required scenarios):

- **impossible_travel** — the same actor produces two ``login_success`` events from
  *different* source IPs within a window too short to plausibly relocate (an
  IP-velocity heuristic; geo/ASN enrichment is a documented seam, not yet wired).
- **privilege_escalation** — a user's ``is_admin`` flips on (a ``privilege_escalation``
  event emitted at the grant sites).
- **cross_tenant_access** — an actor accrues >= threshold cross-tenant denials
  (``cross_tenant_denied`` events) within a window — an enumeration/probing pattern.
- **audit_chain_break** — the tamper-evident audit ledger fails verification.

The emission helpers (:func:`emit_login_success`, :func:`emit_privilege_escalation`,
:func:`emit_cross_tenant_denied`) are best-effort wrappers around
``operations_store.create_security_event`` — modelled on
``rate_limit._emit_throttle_event``: never raise, lazy imports, settings-gated. The
API layer calls them at the auth / ownership-deny seams.

The **SIEM sink** is the export boundary: a JSON-to-stdout sink by default (Render /
Vercel forward stdout to their log drains -> any SIEM), plus an optional webhook sink
(``SECURITY_ALERT_WEBHOOK_URL``) for high-severity push alerting. Shipping logs to a
*hosted* SIEM (Datadog/Splunk/Elastic) and the *24/7 on-call rotation* (PagerDuty/
Opsgenie) are operational; this module is the in-repo detection logic + alert seam +
the scenario coverage. See docs/security/siem_detections.md.
"""

from __future__ import annotations

import ipaddress
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from .models import DetectionScanResult, SecurityAlert, SecurityEventCreate

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session, sessionmaker

    from .models import AuditChainVerification, SecurityEvent
    from .settings import Settings

# SecurityEvent.event_type values this module emits/consumes (all in SecurityEventType).
EVENT_LOGIN_SUCCESS = "login_success"
EVENT_LOGIN_FAILURE = "login_failure"
EVENT_PRIVILEGE_ESCALATION = "privilege_escalation"
EVENT_CROSS_TENANT_DENIED = "cross_tenant_denied"

# Detection ids (DetectionId literal in models).
DETECTION_IMPOSSIBLE_TRAVEL = "impossible_travel"
DETECTION_PRIVILEGE_ESCALATION = "privilege_escalation"
DETECTION_CROSS_TENANT_ACCESS = "cross_tenant_access"
DETECTION_AUDIT_CHAIN_BREAK = "audit_chain_break"

# Severities that are pushed to the SIEM sink (info/warning stay in the queryable stream).
_SHIPPED_SEVERITIES = frozenset({"error", "critical"})


def _actor_key(email: str | None) -> str | None:
    return email.lower() if email else None


def _norm_ip(value: str) -> object:
    """Parse an IP, unwrapping an IPv4-mapped IPv6 (``::ffff:1.2.3.4``) to its IPv4 so
    the two renderings compare equal."""
    addr = ipaddress.ip_address(value)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def _same_ip(a: str | None, b: str | None) -> bool:
    """IP equality that treats equivalent renderings (an IPv4-mapped IPv6 vs the plain
    IPv4, or non-canonical IPv6) as the same address, so a dual-stack proxy can't
    trigger a false impossible-travel alert."""
    if a == b:
        return True
    if not a or not b:
        return False
    try:
        return _norm_ip(a) == _norm_ip(b)
    except ValueError:
        return False


# --------------------------------------------------------------------------- detections


def detect_impossible_travel(
    events: Sequence[SecurityEvent], *, window_seconds: float
) -> list[SecurityAlert]:
    """Same actor, two login_success from different IPs within window_seconds.

    Heuristic stand-in for true geo-distance impossible travel: without geo
    enrichment we cannot compute km/h, so we flag *any* source-IP change inside a
    window too short to plausibly relocate. One alert per actor (the tightest pair).
    """
    by_actor: dict[str, list[SecurityEvent]] = defaultdict(list)
    for event in events:
        if event.event_type == EVENT_LOGIN_SUCCESS and event.actor_email and event.ip_address:
            key = _actor_key(event.actor_email)
            if key is not None:
                by_actor[key].append(event)

    alerts: list[SecurityAlert] = []
    for actor, evs in by_actor.items():
        evs.sort(key=lambda e: e.created_at)
        # Keep the TIGHTEST in-window IP-change pair (smallest gap = most egregious
        # teleport), scanning all adjacent pairs — not just the earliest.
        best: tuple[float, SecurityEvent, SecurityEvent] | None = None
        for prev, cur in zip(evs, evs[1:], strict=False):
            if _same_ip(prev.ip_address, cur.ip_address):
                continue
            gap = (cur.created_at - prev.created_at).total_seconds()
            if 0 <= gap <= window_seconds and (best is None or gap < best[0]):
                best = (gap, prev, cur)
        if best is not None:
            gap, prev, cur = best
            alerts.append(
                SecurityAlert(
                    detection=DETECTION_IMPOSSIBLE_TRAVEL,
                    severity="warning",
                    actor_email=actor,
                    message=(
                        f"Impossible travel: {actor} logged in from {prev.ip_address} "
                        f"then {cur.ip_address} {int(gap)}s apart."
                    ),
                    first_seen=prev.created_at,
                    last_seen=cur.created_at,
                    event_count=2,
                    evidence={
                        "ip_a": prev.ip_address,
                        "ip_b": cur.ip_address,
                        "seconds_between": gap,
                        "window_seconds": window_seconds,
                    },
                )
            )
    return alerts


def detect_privilege_escalation(events: Sequence[SecurityEvent]) -> list[SecurityAlert]:
    """Each actor that gained admin (a privilege_escalation event) → one error alert."""
    alerts: list[SecurityAlert] = []
    seen: set[str] = set()
    for event in sorted(events, key=lambda e: e.created_at):
        if event.event_type != EVENT_PRIVILEGE_ESCALATION:
            continue
        key = _actor_key(event.actor_email)
        if key is None or key in seen:
            continue
        seen.add(key)
        alerts.append(
            SecurityAlert(
                detection=DETECTION_PRIVILEGE_ESCALATION,
                severity="error",
                actor_email=key,
                message=f"Privilege escalation: {key} was granted admin.",
                first_seen=event.created_at,
                last_seen=event.created_at,
                event_count=1,
                evidence=dict(event.metadata_json or {}),
            )
        )
    return alerts


def _max_in_window(times: Sequence[datetime], window_seconds: float) -> int:
    """Max number of timestamps falling inside any window_seconds-wide span."""
    if not times:
        return 0
    ordered = sorted(times)
    best = 1
    start = 0
    for end in range(len(ordered)):
        while (ordered[end] - ordered[start]).total_seconds() > window_seconds:
            start += 1
        best = max(best, end - start + 1)
    return best


def detect_cross_tenant_access(
    events: Sequence[SecurityEvent], *, threshold: int, window_seconds: float
) -> list[SecurityAlert]:
    """An actor with >= threshold cross_tenant_denied events inside a window."""
    by_actor: dict[str, list[SecurityEvent]] = defaultdict(list)
    for event in events:
        if event.event_type == EVENT_CROSS_TENANT_DENIED and event.actor_email:
            key = _actor_key(event.actor_email)
            if key is not None:
                by_actor[key].append(event)

    alerts: list[SecurityAlert] = []
    for actor, evs in by_actor.items():
        peak = _max_in_window([e.created_at for e in evs], window_seconds)
        if peak >= threshold:
            evs.sort(key=lambda e: e.created_at)
            resources = sorted({e.resource_id for e in evs if e.resource_id})[:20]
            alerts.append(
                SecurityAlert(
                    detection=DETECTION_CROSS_TENANT_ACCESS,
                    severity="warning",
                    actor_email=actor,
                    message=(
                        f"Cross-tenant probing: {actor} hit {peak} owner-denied resources "
                        f"within {int(window_seconds)}s (threshold {threshold})."
                    ),
                    first_seen=evs[0].created_at,
                    last_seen=evs[-1].created_at,
                    event_count=len(evs),
                    evidence={
                        "peak_in_window": peak,
                        "threshold": threshold,
                        "window_seconds": window_seconds,
                        "resources": resources,
                    },
                )
            )
    return alerts


def detect_audit_chain_break(
    verification: AuditChainVerification | None,
) -> list[SecurityAlert]:
    """A failed audit-chain verification → one critical alert."""
    if verification is None or verification.ok:
        return []
    return [
        SecurityAlert(
            detection=DETECTION_AUDIT_CHAIN_BREAK,
            severity="critical",
            message=f"Audit chain integrity check failed: {verification.detail}.",
            event_count=1,
            evidence={
                "detail": verification.detail,
                "first_break_seq": verification.first_break_seq,
                "anchors_ok": verification.anchors_ok,
                "key_id": verification.key_id,
            },
        )
    ]


# --------------------------------------------------------------------------- SIEM sink


class SiemSink(Protocol):
    def emit(self, payload: dict[str, Any]) -> bool: ...


class JsonStdoutSink:
    """Write a structured JSON alert line to stdout (Render/Vercel log drains → SIEM)."""

    def emit(self, payload: dict[str, Any]) -> bool:
        try:
            sys.stdout.write(json.dumps({"siem_alert": payload}, default=str) + "\n")
            sys.stdout.flush()
            return True
        except Exception:
            return False


class WebhookSink:
    """POST the alert JSON to a configured webhook (best-effort, never raises)."""

    def __init__(self, url: str, *, timeout: float = 5.0) -> None:
        self.url = url
        self.timeout = timeout

    def emit(self, payload: dict[str, Any]) -> bool:
        try:
            data = json.dumps(payload, default=str).encode("utf-8")
            req = urllib.request.Request(  # noqa: S310 - operator-configured https webhook
                self.url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout):  # noqa: S310
                return True
        except (urllib.error.URLError, OSError, ValueError):
            return False


class CompositeSink:
    def __init__(self, sinks: Sequence[SiemSink]) -> None:
        self._sinks = list(sinks)

    def emit(self, payload: dict[str, Any]) -> bool:
        # Evaluate EVERY sink (eager list, not a short-circuiting any()-generator —
        # otherwise the stdout sink returning True would skip the webhook push).
        results = [sink.emit(payload) for sink in self._sinks]
        return any(results)


def get_sink(settings: Settings) -> SiemSink:
    """Always log to stdout; additionally POST to the webhook when configured."""
    sinks: list[SiemSink] = [JsonStdoutSink()]
    url = (getattr(settings, "security_alert_webhook_url", "") or "").strip()
    if url:
        sinks.append(WebhookSink(url))
    return CompositeSink(sinks)


def _alert_payload(alert: SecurityAlert, now: datetime) -> dict[str, Any]:
    return {
        "kind": "moltrace.security.alert",
        "detection": alert.detection,
        "severity": alert.severity,
        "actor_email": alert.actor_email,
        "message": alert.message,
        "event_count": alert.event_count,
        "first_seen": alert.first_seen,
        "last_seen": alert.last_seen,
        "evidence": alert.evidence,
        "generated_at": now,
    }


# --------------------------------------------------------------------------- orchestrator


def run_detections(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    now: datetime | None = None,
    ship: bool = False,
    sink: SiemSink | None = None,
) -> DetectionScanResult:
    """Scan the recent SecurityEvent window + verify the audit chain → alerts.

    With ``ship=True`` the high-severity (error/critical) alerts are pushed to the
    SIEM sink. Returns a :class:`DetectionScanResult` (also the admin-endpoint shape).
    """
    if now is None:
        now = datetime.now(UTC)
    window_minutes = int(getattr(settings, "security_detection_window_minutes", 1440))
    since = now - timedelta(minutes=window_minutes)

    from . import operations_store

    scan_limit = int(getattr(settings, "security_detection_scan_limit", 5000))
    events = operations_store.recent_security_events(
        session_factory, since=since, limit=scan_limit
    )
    # If the window held more than the cap, the scan saw only the newest `scan_limit`
    # — surface that so a truncated scan doesn't read as a clean window.
    truncated = len(events) >= scan_limit

    alerts: list[SecurityAlert] = []
    alerts += detect_impossible_travel(
        events,
        window_seconds=float(getattr(settings, "impossible_travel_window_seconds", 300)),
    )
    alerts += detect_privilege_escalation(events)
    alerts += detect_cross_tenant_access(
        events,
        threshold=int(getattr(settings, "cross_tenant_denied_threshold", 5)),
        window_seconds=float(getattr(settings, "cross_tenant_window_seconds", 600)),
    )

    verification = operations_store.verify_audit_chain(session_factory, settings=settings)
    alerts += detect_audit_chain_break(verification)

    shipped = 0
    if ship:
        active_sink = sink or get_sink(settings)
        for alert in alerts:
            if alert.severity in _SHIPPED_SEVERITIES and active_sink.emit(
                _alert_payload(alert, now)
            ):
                shipped += 1

    return DetectionScanResult(
        generated_at=now,
        window_minutes=window_minutes,
        events_scanned=len(events),
        alerts=alerts,
        shipped=shipped,
        audit_chain_ok=bool(getattr(verification, "ok", True)),
        truncated=truncated,
    )


# --------------------------------------------------------------------------- emission seam


def _emit(
    request: Any, payload: SecurityEventCreate, *, user: Any = None, context: Any = None
) -> None:
    """Best-effort SecurityEvent emission (never raises; settings-gated).

    Mirrors rate_limit._emit_throttle_event: lazy imports, swallow everything, so a
    telemetry failure can never break the request being instrumented.
    """
    try:
        settings = request.app.state.settings
        if not getattr(settings, "security_siem_enabled", True):
            return
        from . import operations_store, rate_limit

        principal = user if user is not None else getattr(context, "user", None)
        actor = operations_store.OperationsActor(
            user_id=getattr(principal, "id", None),
            email=getattr(principal, "email", None),
            system_api_key=bool(getattr(context, "system_api_key", False)),
        )
        operations_store.create_security_event(
            request.app.state.session_factory,
            payload,
            actor=actor,
            request_ip=rate_limit._client_ip(request, settings),
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:
        return


def emit_login_success(request: Any, *, user: Any) -> None:
    """Record a successful login (with the client IP) so impossible-travel can run."""
    email = getattr(user, "email", None)
    if not email:
        return
    _emit(
        request,
        SecurityEventCreate(
            event_type=EVENT_LOGIN_SUCCESS,
            severity="info",
            actor_email=email,
            message=f"Successful login for {email}.",
        ),
        user=user,
    )


def emit_privilege_escalation(request: Any, *, email: str | None, granted_via: str) -> None:
    """Record an is_admin False→True transition (a privilege escalation)."""
    if not email:
        return
    _emit(
        request,
        SecurityEventCreate(
            event_type=EVENT_PRIVILEGE_ESCALATION,
            severity="error",
            actor_email=email,
            message=f"User {email} was granted admin ({granted_via}).",
            metadata_json={"granted_via": granted_via},
        ),
        context=None,
    )


def emit_cross_tenant_denied(
    request: Any,
    context: Any,
    *,
    resource_type: str | None,
    resource_id: str | None,
) -> None:
    """Record a cross-tenant / owner-scoped access denial (a non-leaking 404)."""
    actor_email = getattr(getattr(context, "user", None), "email", None)
    if not actor_email:
        # Anonymous / system-key denials can't trip the actor-keyed detector, so skip
        # the write (also bounds write-amplification under probing).
        return
    _emit(
        request,
        SecurityEventCreate(
            event_type=EVENT_CROSS_TENANT_DENIED,
            severity="warning",
            actor_email=actor_email,
            message=(
                f"Cross-tenant access denied to {resource_type or 'resource'} "
                f"{resource_id or '?'}."
            ),
            resource_type=(resource_type or None),
            resource_id=(str(resource_id)[:100] if resource_id is not None else None),
        ),
        context=context,
    )
