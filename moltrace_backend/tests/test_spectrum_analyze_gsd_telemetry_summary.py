"""Aggregate soak-telemetry rollup for the opt-in GSD endpoint.

Backs ``GET /spectrum/analyze/gsd/telemetry-summary?window_days=N``,
which the FE readiness panel calls to render the
"quarter-of-clean-tenant-runs" countdown without fetching every audit
event individually.

These tests exercise three slices of the aggregation surface:

1. ``test_telemetry_summary_empty_window_returns_zeros`` — no GSD calls
   inside the window: invocations/errors zero, rates None, slice dicts
   empty.
2. ``test_telemetry_summary_aggregates_mixed_invocations`` — fire 4
   happy-path calls (2 × ¹H + 2 × ¹³C at mixed levels, two with a
   declared solvent + a CDCl3 residual peak so solvent-detect is
   measurable) and assert the rollup numbers match.
3. ``test_telemetry_summary_counts_errors_and_error_kinds`` — fire a
   validation-error call + happy-path call and assert ``errors`` and
   ``error_kind_counts`` reflect the failure event without bleeding
   into the happy-path solvent-detect numerator.

The endpoint is admin-only; the test harness signs up an admin user via
the same path as the other admin endpoint tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-telemetry-summary.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )
    return app, TestClient(app)


def _sign_up_admin(client: TestClient) -> dict[str, str]:
    """Sign up as ``admin@example.com``; the Settings fixture flags
    that address as an admin so the resulting bearer token satisfies
    ``require_admin``."""
    res = client.post(
        "/auth/sign-up",
        json={
            "email": "admin@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _api_headers() -> dict[str, str]:
    """``x-api-key`` headers — enough auth to call the GSD endpoint
    (only the summary endpoint needs admin)."""
    return {"x-api-key": "test-key"}


def _synthetic_cdcl3_1h_spectrum() -> tuple[list[float], list[float]]:
    """Two Lorentzians: CDCl3 residual at ~7.26 ppm + a compound peak."""
    n = 4096
    ppm_lo, ppm_hi = 0.0, 10.0
    ppm = [ppm_lo + (ppm_hi - ppm_lo) * i / (n - 1) for i in range(n)]
    intensity = [0.0] * n

    def _lorentzian(centre: float, fwhm_ppm: float, height: float) -> None:
        gamma = 0.5 * fwhm_ppm
        for i, x in enumerate(ppm):
            intensity[i] += height * (gamma * gamma) / (
                (x - centre) ** 2 + gamma * gamma
            )

    _lorentzian(centre=7.26, fwhm_ppm=0.005, height=100.0)
    _lorentzian(centre=3.50, fwhm_ppm=0.005, height=60.0)
    return ppm, intensity


def _synthetic_13c_spectrum() -> tuple[list[float], list[float]]:
    """One ¹³C compound Lorentzian — no solvent reference required."""
    n = 4096
    ppm_lo, ppm_hi = -10.0, 220.0
    ppm = [ppm_lo + (ppm_hi - ppm_lo) * i / (n - 1) for i in range(n)]
    intensity = [0.0] * n
    centre = 28.0
    fwhm_ppm = 0.05
    gamma = 0.5 * fwhm_ppm
    for i, x in enumerate(ppm):
        intensity[i] += 100.0 * (gamma * gamma) / (
            (x - centre) ** 2 + gamma * gamma
        )
    return ppm, intensity


def test_telemetry_summary_empty_window_returns_zeros(tmp_path) -> None:
    """No GSD invocations → zero invocations, None rates, empty slices."""
    _, client = _client(tmp_path)

    with client:
        headers = _sign_up_admin(client)
        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=headers,
            params={"window_days": 30},
        )
        assert res.status_code == 200, res.text
        body = res.json()

    assert body["window_days"] == 30
    assert body["invocations"] == 0
    assert body["errors"] == 0
    assert body["error_rate"] is None
    assert body["median_wall_ms"] is None
    assert body["p95_wall_ms"] is None
    assert body["fixtures_with_solvent_declared"] == 0
    assert body["solvent_detected_count"] == 0
    assert body["solvent_detect_rate"] is None
    assert body["by_nucleus"] == {}
    assert body["by_level"] == {}
    assert body["error_kind_counts"] == {}


def test_telemetry_summary_aggregates_mixed_invocations(tmp_path) -> None:
    """Happy-path mix: ¹H + ¹³C at two levels → correct slice counts."""
    _, client = _client(tmp_path)
    api = _api_headers()
    proton_ppm, proton_int = _synthetic_cdcl3_1h_spectrum()
    carbon_ppm, carbon_int = _synthetic_13c_spectrum()

    with client:
        admin = _sign_up_admin(client)

        # 2 × ¹H with CDCl3 solvent, levels 2 + 3
        for level in (2, 3):
            res = client.post(
                "/spectrum/analyze/gsd",
                headers=api,
                json={
                    "ppm_axis": proton_ppm,
                    "intensity": proton_int,
                    "nucleus": "1H",
                    "solvent": "CDCl3",
                    "field_mhz": 500.0,
                    "level": level,
                },
            )
            assert res.status_code == 200, res.text

        # 2 × ¹³C at level 2 with NO solvent declared (so they do not
        # contribute to the solvent-detect denominator, but still count
        # toward invocations + by_nucleus + by_level).
        for _ in range(2):
            res = client.post(
                "/spectrum/analyze/gsd",
                headers=api,
                json={
                    "ppm_axis": carbon_ppm,
                    "intensity": carbon_int,
                    "nucleus": "13C",
                    "solvent": "",
                    "field_mhz": 125.0,
                    "level": 2,
                },
            )
            assert res.status_code == 200, res.text

        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin,
            params={"window_days": 30},
        )
        assert res.status_code == 200, res.text
        body = res.json()

    assert body["invocations"] == 4
    assert body["errors"] == 0
    assert body["error_rate"] == 0.0
    assert body["by_nucleus"] == {"1H": 2, "13C": 2}
    assert body["by_level"] == {"2": 3, "3": 1}

    # Solvent-detect: 2 ¹H calls declared CDCl3; both should auto-detect
    # the residual at 7.26 ppm (the synthetic spectrum is built around it).
    # ¹³C calls declared no solvent so they are excluded from both sides.
    assert body["fixtures_with_solvent_declared"] == 2
    assert body["solvent_detected_count"] == 2
    assert body["solvent_detect_rate"] == 1.0

    # Performance: wall_ms percentiles populated on a non-empty sample.
    assert body["median_wall_ms"] is not None and body["median_wall_ms"] >= 0
    assert body["p95_wall_ms"] is not None and body["p95_wall_ms"] >= 0
    # No errors emitted, so the error_kind_counts dict is empty.
    assert body["error_kind_counts"] == {}


def test_telemetry_summary_counts_errors_and_error_kinds(tmp_path) -> None:
    """Validation failures land in ``errors`` and ``error_kind_counts``."""
    _, client = _client(tmp_path)
    api = _api_headers()
    proton_ppm, proton_int = _synthetic_cdcl3_1h_spectrum()

    with client:
        admin = _sign_up_admin(client)

        # 1 × happy path
        ok = client.post(
            "/spectrum/analyze/gsd",
            headers=api,
            json={
                "ppm_axis": proton_ppm,
                "intensity": proton_int,
                "nucleus": "1H",
                "solvent": "CDCl3",
                "field_mhz": 500.0,
                "level": 2,
            },
        )
        assert ok.status_code == 200, ok.text

        # 1 × validation failure (mismatched array lengths, both above
        # the ≥16-point floor so the handler's own check raises 400 and
        # _emit_gsd_telemetry records the failure event).
        bad = client.post(
            "/spectrum/analyze/gsd",
            headers=api,
            json={
                "ppm_axis": [float(i) for i in range(20)],
                "intensity": [float(i) for i in range(18)],
                "nucleus": "1H",
                "solvent": "CDCl3",
                "field_mhz": 500.0,
                "level": 2,
            },
        )
        assert bad.status_code == 400, bad.text

        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin,
            params={"window_days": 30},
        )
        assert res.status_code == 200, res.text
        body = res.json()

    assert body["invocations"] == 2
    assert body["errors"] == 1
    assert body["error_rate"] == 0.5
    assert body["error_kind_counts"] == {"ppm_axis_length_mismatch": 1}

    # The failure event recorded the declared solvent but had zero
    # detected labels, so it counts toward the solvent denominator but
    # not the numerator — solvent_detect_rate = 1/2 = 0.5.
    assert body["fixtures_with_solvent_declared"] == 2
    assert body["solvent_detected_count"] == 1
    assert body["solvent_detect_rate"] == 0.5

    # Both calls were ¹H @ level 2.
    assert body["by_nucleus"] == {"1H": 2}
    assert body["by_level"] == {"2": 2}


def test_telemetry_summary_rejects_unauthenticated(tmp_path) -> None:
    """No auth at all → 401/403; ``x-api-key`` is admin-equivalent and works."""
    _, client = _client(tmp_path)
    with client:
        # Unauthenticated: must be rejected.
        no_auth = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            params={"window_days": 30},
        )
        assert no_auth.status_code in (401, 403), no_auth.text

        # ``x-api-key`` IS admin-equivalent under the current auth
        # contract (``require_admin`` accepts ``system_api_key``) so the
        # same caller that fires the GSD endpoint can also read the
        # rollup — pinning that contract here so a future tightening
        # would have to update this test deliberately.
        with_api = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=_api_headers(),
            params={"window_days": 30},
        )
        assert with_api.status_code == 200, with_api.text


def test_telemetry_summary_window_days_is_clamped(tmp_path) -> None:
    """``window_days`` below 1 or above 365 fails Pydantic validation."""
    _, client = _client(tmp_path)
    with client:
        headers = _sign_up_admin(client)
        too_small = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=headers,
            params={"window_days": 0},
        )
        too_big = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=headers,
            params={"window_days": 366},
        )
    assert too_small.status_code == 422, too_small.text
    assert too_big.status_code == 422, too_big.text
