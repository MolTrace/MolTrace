"""Flip-readiness verdict coverage for the GSD telemetry rollup.

The backend owns the "ready to flip ``experimental: false``?" decision
via ``_compute_flip_readiness_verdict`` (in ``nmrcheck.api``); these
tests pin the verdict policy + reason strings + policy snapshot that
the FE readiness panel renders as-is.

Two layers:

1. **Unit-level tests** of ``_compute_flip_readiness_verdict`` cover
   every verdict state and policy edge case directly — no DB / no
   TestClient needed, fast and exhaustive.
2. **End-to-end test** through ``GET /spectrum/analyze/gsd/
   telemetry-summary`` confirms the endpoint plumbs the helper output
   into the response correctly and that the policy snapshot is
   included verbatim.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import (
    _FLIP_READINESS_POLICY,
    _compute_flip_readiness_verdict,
    create_app,
)
from nmrcheck.settings import Settings

# ---------------------------------------------------------------------------
# Unit tests against the pure helper.
# ---------------------------------------------------------------------------


def test_verdict_insufficient_data_when_below_invocation_floor() -> None:
    """invocations < 500 → insufficient_data, regardless of rates."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=412,
        error_rate=0.001,  # near-perfect
        solvent_detect_rate=0.99,
        fixtures_with_solvent_declared=400,
    )
    assert verdict == "insufficient_data"
    assert reasons == [
        f"need >={_FLIP_READINESS_POLICY.min_invocations} invocations in window "
        f"(got 412)"
    ]


def test_verdict_clear_when_all_signals_pass() -> None:
    """Above floor + good error_rate + good solvent_detect_rate → clear."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=0.01,
        solvent_detect_rate=0.97,
        fixtures_with_solvent_declared=400,
    )
    assert verdict == "clear"
    assert reasons == []


def test_verdict_blocked_on_error_rate_alone() -> None:
    """Above floor + error_rate > 5 % → blocked with one reason."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=0.06,
        solvent_detect_rate=0.97,
        fixtures_with_solvent_declared=400,
    )
    assert verdict == "blocked"
    assert len(reasons) == 1
    assert "error_rate" in reasons[0]
    assert "6.00%" in reasons[0]


def test_verdict_blocked_on_solvent_detect_rate_alone() -> None:
    """Above floor + solvent_detect_rate < 95 % → blocked with one reason."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=0.01,
        solvent_detect_rate=0.85,
        fixtures_with_solvent_declared=400,
    )
    assert verdict == "blocked"
    assert len(reasons) == 1
    assert "solvent_detect_rate" in reasons[0]
    assert "85.00%" in reasons[0]


def test_verdict_blocked_lists_all_failing_signals() -> None:
    """Two blockers fire → blocked with two reasons (one per blocker)."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=0.10,
        solvent_detect_rate=0.85,
        fixtures_with_solvent_declared=400,
    )
    assert verdict == "blocked"
    assert len(reasons) == 2
    # The reasons describe distinct failures — they should not be
    # duplicates and should each name the failing metric.
    joined = " ".join(reasons)
    assert "error_rate" in joined
    assert "solvent_detect_rate" in joined


def test_verdict_clear_when_solvent_rate_is_unmeasurable() -> None:
    """Zero calls declared solvent → solvent check is skipped, not failed."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=0.01,
        solvent_detect_rate=None,  # rate is undefined
        fixtures_with_solvent_declared=0,
    )
    assert verdict == "clear"
    assert reasons == []


def test_verdict_clear_at_invocation_floor_boundary() -> None:
    """``invocations == min_invocations`` is exactly at the floor → clear.

    Pins the inequality choice (>= vs >) so a future policy adjustment
    has to update this test deliberately.
    """
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=_FLIP_READINESS_POLICY.min_invocations,
        error_rate=0.0,
        solvent_detect_rate=1.0,
        fixtures_with_solvent_declared=100,
    )
    assert verdict == "clear"
    assert reasons == []


def test_verdict_clear_at_error_rate_ceiling_boundary() -> None:
    """``error_rate == max_error_rate`` is exactly at the ceiling → clear.

    Pins the inequality choice (> vs >=).
    """
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=_FLIP_READINESS_POLICY.max_error_rate,
        solvent_detect_rate=1.0,
        fixtures_with_solvent_declared=100,
    )
    assert verdict == "clear"


def test_verdict_clear_at_solvent_rate_floor_boundary() -> None:
    """``solvent_detect_rate == min_solvent_detect_rate`` → clear."""
    verdict, reasons = _compute_flip_readiness_verdict(
        invocations=600,
        error_rate=0.0,
        solvent_detect_rate=_FLIP_READINESS_POLICY.min_solvent_detect_rate,
        fixtures_with_solvent_declared=100,
    )
    assert verdict == "clear"


# ---------------------------------------------------------------------------
# End-to-end test through the HTTP endpoint.
# ---------------------------------------------------------------------------


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-flip-readiness.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )
    return app, TestClient(app)


def test_endpoint_returns_insufficient_data_verdict_on_empty_window(
    tmp_path,
) -> None:
    """An empty window must yield ``insufficient_data`` (0 < 500)."""
    _, client = _client(tmp_path)
    with client:
        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers={"x-api-key": "test-key"},
            params={"window_days": 30},
        )
        assert res.status_code == 200, res.text
        body = res.json()

    # Verdict shape contract
    assert body["flip_readiness_verdict"] == "insufficient_data"
    assert len(body["flip_readiness_reasons"]) == 1
    assert "500 invocations" in body["flip_readiness_reasons"][0]
    assert "got 0" in body["flip_readiness_reasons"][0]

    # Policy snapshot must echo the live policy verbatim so the FE
    # renders progress widgets without hard-coding the thresholds.
    assert body["flip_readiness_policy"] == {
        "min_invocations": _FLIP_READINESS_POLICY.min_invocations,
        "max_error_rate": _FLIP_READINESS_POLICY.max_error_rate,
        "min_solvent_detect_rate": _FLIP_READINESS_POLICY.min_solvent_detect_rate,
    }
