"""Security detections + SIEM sink (Security Prompt 19) — rule unit tests.

Exercises the four detection rules over synthetic SecurityEvent records, the
sliding-window helper, and the alert sinks. The end-to-end login→alert /
cross-tenant→alert / audit-chain-break→alert scenarios are covered against the live
app in test_security_detections_api.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nmrcheck import detections
from nmrcheck.models import AuditChainVerification, SecurityEvent

_T0 = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)


def _evt(event_type, *, actor="user@acme.com", ip=None, offset_s=0, sev="info", rid=None, meta=None):
    return SecurityEvent(
        id=offset_s + 1,
        event_type=event_type,
        severity=sev,
        actor_email=actor,
        ip_address=ip,
        resource_id=rid,
        message=f"{event_type} {actor}",
        created_at=_T0 + timedelta(seconds=offset_s),
        metadata_json=meta or {},
    )


# --------------------------------------------------------------------------- impossible travel


def test_impossible_travel_flags_ip_change_within_window():
    events = [
        _evt("login_success", ip="1.1.1.1", offset_s=0),
        _evt("login_success", ip="9.9.9.9", offset_s=60),  # 60s later, different IP
    ]
    alerts = detections.detect_impossible_travel(events, window_seconds=300)
    assert len(alerts) == 1
    assert alerts[0].detection == "impossible_travel"
    assert alerts[0].evidence["ip_a"] == "1.1.1.1"
    assert alerts[0].evidence["ip_b"] == "9.9.9.9"


def test_impossible_travel_ignores_same_ip_and_slow_moves():
    same_ip = [
        _evt("login_success", ip="1.1.1.1", offset_s=0),
        _evt("login_success", ip="1.1.1.1", offset_s=60),
    ]
    assert detections.detect_impossible_travel(same_ip, window_seconds=300) == []
    slow = [
        _evt("login_success", ip="1.1.1.1", offset_s=0),
        _evt("login_success", ip="9.9.9.9", offset_s=3600),  # 1h apart — plausible
    ]
    assert detections.detect_impossible_travel(slow, window_seconds=300) == []


def test_impossible_travel_one_alert_per_actor():
    events = [
        _evt("login_success", actor="a@x.com", ip="1.1.1.1", offset_s=0),
        _evt("login_success", actor="a@x.com", ip="2.2.2.2", offset_s=30),
        _evt("login_success", actor="a@x.com", ip="3.3.3.3", offset_s=60),
    ]
    assert len(detections.detect_impossible_travel(events, window_seconds=300)) == 1


def test_impossible_travel_actor_grouping_is_case_insensitive():
    events = [
        _evt("login_success", actor="A@X.com", ip="1.1.1.1", offset_s=0),
        _evt("login_success", actor="a@x.com", ip="2.2.2.2", offset_s=30),
    ]
    alerts = detections.detect_impossible_travel(events, window_seconds=300)
    assert len(alerts) == 1 and alerts[0].actor_email == "a@x.com"


def test_impossible_travel_picks_tightest_pair():
    # A wide in-window pair (250s) then a tight one (5s) → report the tighter.
    events = [
        _evt("login_success", ip="1.1.1.1", offset_s=0),
        _evt("login_success", ip="2.2.2.2", offset_s=250),
        _evt("login_success", ip="3.3.3.3", offset_s=255),
    ]
    alerts = detections.detect_impossible_travel(events, window_seconds=300)
    assert len(alerts) == 1
    assert alerts[0].evidence["seconds_between"] == 5  # the tightest teleport, not 250


def test_impossible_travel_normalizes_equivalent_ips():
    # IPv4-mapped IPv6 vs plain IPv4 are the same address → no false alert.
    events = [
        _evt("login_success", ip="1.2.3.4", offset_s=0),
        _evt("login_success", ip="::ffff:1.2.3.4", offset_s=30),
    ]
    assert detections.detect_impossible_travel(events, window_seconds=300) == []


# --------------------------------------------------------------------------- privilege escalation


def test_privilege_escalation_one_alert_per_actor():
    events = [
        _evt("privilege_escalation", actor="a@x.com", sev="error", offset_s=0),
        _evt("privilege_escalation", actor="a@x.com", sev="error", offset_s=5),
        _evt("login_success", actor="a@x.com", ip="1.1.1.1", offset_s=1),
    ]
    alerts = detections.detect_privilege_escalation(events)
    assert len(alerts) == 1
    assert alerts[0].severity == "error" and alerts[0].actor_email == "a@x.com"


# --------------------------------------------------------------------------- cross-tenant


def test_cross_tenant_fires_at_threshold():
    events = [
        _evt("cross_tenant_denied", actor="a@x.com", sev="warning", offset_s=i * 10, rid=f"d{i}")
        for i in range(5)
    ]
    alerts = detections.detect_cross_tenant_access(events, threshold=5, window_seconds=600)
    assert len(alerts) == 1
    assert alerts[0].evidence["peak_in_window"] >= 5


def test_cross_tenant_below_threshold_is_quiet():
    events = [
        _evt("cross_tenant_denied", actor="a@x.com", sev="warning", offset_s=i * 10)
        for i in range(4)
    ]
    assert detections.detect_cross_tenant_access(events, threshold=5, window_seconds=600) == []


def test_cross_tenant_respects_window():
    # 5 denials but spread across 2h — never 5 within a 600s window.
    events = [
        _evt("cross_tenant_denied", actor="a@x.com", sev="warning", offset_s=i * 1800)
        for i in range(5)
    ]
    assert detections.detect_cross_tenant_access(events, threshold=5, window_seconds=600) == []


def test_max_in_window():
    base = _T0
    times = [base + timedelta(seconds=s) for s in (0, 100, 200, 5000, 5100)]
    assert detections._max_in_window(times, 600) == 3  # the first cluster
    assert detections._max_in_window([], 600) == 0


# --------------------------------------------------------------------------- audit-chain break


def _verification(ok: bool, detail: str = "ok") -> AuditChainVerification:
    return AuditChainVerification(
        ok=ok,
        verified_count=10,
        total_chained=10,
        first_break_seq=None if ok else 7,
        anchors_ok=ok,
        anchor_count=1,
        detail=detail,
        key_id="prod-key",
    )


def test_audit_chain_break_alerts_on_failure():
    alerts = detections.detect_audit_chain_break(_verification(False, "entry_hash_mismatch"))
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].evidence["first_break_seq"] == 7


def test_audit_chain_break_silent_when_ok():
    assert detections.detect_audit_chain_break(_verification(True)) == []
    assert detections.detect_audit_chain_break(None) == []


# --------------------------------------------------------------------------- sinks


def test_json_stdout_sink_writes(capsys):
    assert detections.JsonStdoutSink().emit({"detection": "x", "severity": "critical"}) is True
    out = capsys.readouterr().out
    assert "siem_alert" in out and "critical" in out


def test_get_sink_adds_webhook_when_configured():
    class _S:
        security_alert_webhook_url = "https://siem.example/webhook"

    sink = detections.get_sink(_S())
    assert isinstance(sink, detections.CompositeSink)
    assert any(isinstance(s, detections.WebhookSink) for s in sink._sinks)


def test_get_sink_stdout_only_without_webhook():
    class _S:
        security_alert_webhook_url = ""

    sink = detections.get_sink(_S())
    assert not any(isinstance(s, detections.WebhookSink) for s in sink._sinks)


def test_composite_sink_true_if_any_accepts():
    class _Yes:
        def emit(self, payload):
            return True

    class _No:
        def emit(self, payload):
            return False

    assert detections.CompositeSink([_No(), _Yes()]).emit({}) is True
    assert detections.CompositeSink([_No(), _No()]).emit({}) is False


def test_composite_sink_invokes_every_sink():
    # Regression: a stdout sink returning True must NOT short-circuit the webhook.
    calls = []

    class _Spy:
        def __init__(self, name, ret):
            self.name, self.ret = name, ret

        def emit(self, payload):
            calls.append(self.name)
            return self.ret

    detections.CompositeSink([_Spy("stdout", True), _Spy("webhook", True)]).emit({})
    assert calls == ["stdout", "webhook"]  # both ran, not just the first truthy one
