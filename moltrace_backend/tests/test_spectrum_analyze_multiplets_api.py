"""Wire-level contract for ``POST /spectrum/analyze/multiplets``.

Pins the request/response shape + happy-path + telemetry-emission +
synthetic-overlay generation for the Prompt 4 endpoint.  Acceptance-
level coverage (quinine + Mnova hidden coupling) lives in
``test_multiplet_quinine_reference`` and
``test_multiplet_mnova_hidden_coupling``; this file covers the
HTTP/Pydantic surface.
"""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'multiplets.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )
    return app, TestClient(app)


def _peak(
    ppm: float, hz: float, intensity: float = 100.0, width_hz: float = 1.0
) -> dict[str, object]:
    """Build a peak dict matching ``GSDPromptPeak`` for the request body."""
    return {
        "position_ppm": ppm,
        "position_hz": hz,
        "intensity": intensity,
        "area": intensity * 10.0,
        "width_hz": width_hz,
        "shape": "lorentzian",
        "category": "compound",
        "confidence": 0.95,
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_singlet_returns_one_s_multiplet(tmp_path) -> None:
    """One peak in → one ``s`` multiplet out with no J couplings."""
    _, client = _client(tmp_path)
    with client:
        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={"peaks": [_peak(7.26, 7.26 * 500)]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
    assert body["multiplet_count"] == 1
    assert body["multiplicity_counts"] == {"s": 1}
    multiplet = body["multiplets"][0]
    assert multiplet["name"] == "A"
    assert multiplet["multiplicity_label"] == "s"
    assert multiplet["j_couplings_hz"] == []
    assert multiplet["num_nuclides"] == 0
    assert multiplet["constituent_peak_indices"] == [0]


def test_doublet_recovers_J_value(tmp_path) -> None:
    """Two peaks 8 Hz apart at 500 MHz → ``d`` with J=8.0 Hz."""
    _, client = _client(tmp_path)
    centre_hz = 7.26 * 500
    with client:
        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={
                "peaks": [
                    _peak(7.252, centre_hz - 4.0),
                    _peak(7.268, centre_hz + 4.0),
                ]
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
    assert body["multiplet_count"] == 1
    m = body["multiplets"][0]
    assert m["multiplicity_label"] == "d"
    assert len(m["j_couplings_hz"]) == 1
    assert abs(m["j_couplings_hz"][0] - 8.0) < 0.1
    assert m["num_nuclides"] == 1


def test_two_separate_doublets_named_A_then_B(tmp_path) -> None:
    """Two well-separated doublets get A then B in ppm-ascending order."""
    _, client = _client(tmp_path)
    with client:
        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={
                "peaks": [
                    _peak(3.40, 3.40 * 500),  # lower-field, will be A
                    _peak(3.408, 3.408 * 500),
                    _peak(7.26, 7.26 * 500),  # higher-field, will be B
                    _peak(7.268, 7.268 * 500),
                ]
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
    assert body["multiplet_count"] == 2
    assert body["multiplicity_counts"] == {"d": 2}
    assert body["multiplets"][0]["name"] == "A"
    assert body["multiplets"][0]["center_ppm"] < body["multiplets"][1]["center_ppm"]
    assert body["multiplets"][1]["name"] == "B"


def test_synthetic_overlay_matches_recovered_multiplet(tmp_path) -> None:
    """The overlay ppm positions are the forward-modelled J set."""
    _, client = _client(tmp_path)
    centre_hz = 7.26 * 500
    with client:
        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={
                "peaks": [
                    _peak(7.252, centre_hz - 4.0),
                    _peak(7.268, centre_hz + 4.0),
                ]
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
    # One multiplet → one overlay; the overlay carries the predicted
    # ppm positions for the recovered J=8.0 doublet (±4 Hz from centre).
    overlay = body["synthetic_overlays_ppm"][0]
    assert len(overlay) == 2
    assert abs(overlay[0] - 7.252) < 0.001
    assert abs(overlay[1] - 7.268) < 0.001


def test_endpoint_emits_audit_event(tmp_path) -> None:
    """Each invocation writes one ``spectrum.analyze_multiplets`` event."""
    _, client = _client(tmp_path)
    with client:
        # Sign up an admin (inside the startup context, where the
        # users table exists) so we can read the audit log.
        admin = client.post(
            "/auth/sign-up",
            json={
                "email": "admin@example.com",
                "password": "password123",
                "password_confirm": "password123",
            },
        )
        admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}

        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={"peaks": [_peak(7.26, 7.26 * 500)]},
        )
        assert res.status_code == 200, res.text

        audit = client.get(
            "/audit/events",
            headers=admin_headers,
            params={"event_type": "spectrum.analyze_multiplets"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
    assert len(events) == 1
    meta = events[0]["metadata"]
    assert meta["input_peak_count"] == 1
    assert meta["multiplet_count"] == 1
    assert meta["multiplicity_counts"] == {"s": 1}
    assert meta["backend"] == "multiplet_prompt4"


def test_empty_peak_list_is_rejected(tmp_path) -> None:
    """Pydantic ``min_length=1`` floors out a request with no peaks."""
    _, client = _client(tmp_path)
    with client:
        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={"peaks": []},
        )
        assert res.status_code == 422, res.text


def test_response_payload_is_well_formed(tmp_path) -> None:
    """Smoke: no NaN/Inf in the response."""
    _, client = _client(tmp_path)
    with client:
        res = client.post(
            "/spectrum/analyze/multiplets",
            headers={"x-api-key": "test-key"},
            json={"peaks": [_peak(7.26, 7.26 * 500)]},
        )
        body = res.json()
    multiplet = body["multiplets"][0]
    assert math.isfinite(multiplet["center_ppm"])
    assert math.isfinite(multiplet["range_ppm"][0])
    assert math.isfinite(multiplet["range_ppm"][1])
