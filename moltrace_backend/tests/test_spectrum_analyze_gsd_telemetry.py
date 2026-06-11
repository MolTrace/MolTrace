"""Soak telemetry coverage for ``POST /spectrum/analyze/gsd``.

The default GSD endpoint tests live in
``tests/test_spectrum_analyze_gsd_api.py`` and call the handler directly
(passing ``request=None``) so they exercise the algorithm, not the
audit-event surface.  These tests fire the endpoint via ``TestClient``
with a real app + Postgres-backed audit table so we can prove the v0.6.3
soak-telemetry event (``spectrum.analyze_gsd``) reaches the audit log
with the expected payload shape — happy path and validation-error path.

The goal is to lock the wire-level contract for the soak telemetry so a
later refactor doesn't silently drop the event, and so dashboards built
against the payload keep working.
"""

from __future__ import annotations

import math


def _synthetic_cdcl3_spectrum() -> tuple[list[float], list[float]]:
    """A minimal 1H spectrum with a CDCl3 residual at ~7.26 ppm.

    Two Lorentzian peaks: one CDCl3 residual + one compound peak.  Wide
    enough ppm window and dense enough sampling to pass the GSD
    detection floor at default level 2.
    """
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

    _lorentzian(centre=7.26, fwhm_ppm=0.005, height=100.0)  # CDCl3 residual
    _lorentzian(centre=3.50, fwhm_ppm=0.005, height=60.0)  # compound peak
    return ppm, intensity


def test_spectrum_analyze_gsd_emits_telemetry_audit_event(client, api_headers) -> None:
    """Happy-path GSD invocation writes one ``spectrum.analyze_gsd`` event."""
    headers = api_headers

    ppm, intensity = _synthetic_cdcl3_spectrum()
    with client:
        res = client.post(
            "/spectrum/analyze/gsd",
            headers=headers,
            json={
                "ppm_axis": ppm,
                "intensity": intensity,
                "nucleus": "1H",
                "solvent": "CDCl3",
                "field_mhz": 500.0,
                "level": 2,
            },
        )
        assert res.status_code == 200, res.text

        audit = client.get(
            "/audit/events",
            headers=headers,
            params={"event_type": "spectrum.analyze_gsd"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
        assert len(events) == 1, (
            f"Expected exactly one spectrum.analyze_gsd event, got "
            f"{len(events)}"
        )

        event = events[0]
        assert event["event_type"] == "spectrum.analyze_gsd"
        assert event["message"] == "Opt-in GSD spectrum analysis completed."

        # Request shape — every soak dashboard slices on these.
        meta = event["metadata"]
        assert meta["level"] == 2
        assert meta["nucleus"] == "1H"
        assert meta["solvent_declared"] == "CDCl3"
        assert meta["field_mhz"] == 500.0
        assert meta["input_point_count"] == len(ppm)
        assert meta["backend"] == "gsd_prompt3"
        assert meta["experimental"] is True

        # Outcome shape — peak / environment counts must be non-negative
        # ints and the category_counts dict must sum to peak_count.
        assert isinstance(meta["peak_count"], int) and meta["peak_count"] >= 0
        assert (
            isinstance(meta["compound_peak_count"], int)
            and meta["compound_peak_count"] >= 0
        )
        assert (
            isinstance(meta["environment_count"], int)
            and meta["environment_count"] >= 0
        )
        assert (
            isinstance(meta["compound_environment_count"], int)
            and meta["compound_environment_count"] >= 0
        )
        assert isinstance(meta["category_counts"], dict)
        assert sum(meta["category_counts"].values()) == meta["peak_count"]
        assert isinstance(meta["solvent_labels_detected"], list)

        # Performance shape — wall_ms must be a non-negative int.
        assert isinstance(meta["wall_ms"], int) and meta["wall_ms"] >= 0

        # Happy path must NOT set error_kind.
        assert "error_kind" not in meta


def test_spectrum_analyze_gsd_emits_telemetry_on_validation_error(client, api_headers) -> None:
    """Validation failure (mismatched array lengths) still writes one event."""
    headers = api_headers

    with client:
        res = client.post(
            "/spectrum/analyze/gsd",
            headers=headers,
            json={
                # Both arrays pass the Pydantic min_length=16 floor but
                # have *different* lengths, so the handler's own check
                # raises HTTPException(400) and emits the failure event.
                "ppm_axis": [float(i) for i in range(20)],
                "intensity": [float(i) for i in range(18)],
                "nucleus": "1H",
                "solvent": "CDCl3",
                "field_mhz": 500.0,
                "level": 2,
            },
        )
        assert res.status_code == 400, res.text

        audit = client.get(
            "/audit/events",
            headers=headers,
            params={"event_type": "spectrum.analyze_gsd"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
        assert len(events) == 1, (
            f"Expected one spectrum.analyze_gsd event on validation failure, "
            f"got {len(events)}"
        )

        event = events[0]
        assert event["message"] == "Opt-in GSD spectrum analysis failed."
        meta = event["metadata"]
        assert meta["error_kind"] == "ppm_axis_length_mismatch"
        # Failure path must zero outcome counts so dashboards do not
        # double-count partial work.
        assert meta["peak_count"] == 0
        assert meta["environment_count"] == 0
        assert meta["category_counts"] == {}
        assert meta["solvent_labels_detected"] == []
        # Wall time still recorded so we can see how fast we fail.
        assert isinstance(meta["wall_ms"], int) and meta["wall_ms"] >= 0


def test_spectrum_analyze_gsd_telemetry_does_not_break_handler(client, api_headers) -> None:
    """Even if telemetry would somehow fail, the analysis response is intact.

    Smoke check that the response payload is well-formed after the
    telemetry call returns — i.e. the telemetry emission is non-blocking
    and does not mutate the response.
    """
    headers = api_headers

    ppm, intensity = _synthetic_cdcl3_spectrum()
    with client:
        res = client.post(
            "/spectrum/analyze/gsd",
            headers=headers,
            json={
                "ppm_axis": ppm,
                "intensity": intensity,
                "nucleus": "1H",
                "solvent": "CDCl3",
                "field_mhz": 500.0,
                "level": 2,
            },
        )
        assert res.status_code == 200
        body = res.json()
        # Response payload contract — checked here so a regression that
        # accidentally returns the telemetry dict instead of the result
        # would fail loudly.
        assert body["backend"] == "gsd_prompt3"
        assert body["experimental"] is True
        assert isinstance(body["peaks"], list)
        assert isinstance(body["environments"], list)
        assert isinstance(body["environment_count"], int)
        # No NaN/Inf leaking into the response.
        for peak in body["peaks"]:
            assert math.isfinite(peak["position_ppm"])
            assert math.isfinite(peak["intensity"])
