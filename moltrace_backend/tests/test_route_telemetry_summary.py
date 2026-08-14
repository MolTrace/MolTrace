"""The generic route-latency rollup (P1 §3).

The FE-facing analysis routes now stamp ``wall_ms`` into the audit events they
already emit, and ``GET /admin/ops/route-telemetry-summary`` aggregates any
timed event type — so the paths hand-measured at 5–12 s in
``docs/raw_fid_latency_be_handoff.md`` have an automated latency readout
instead of a one-off number in a markdown file.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

HEADERS = {"x-api-key": "test-key"}
PEAK_CSV = b"""shift_ppm,integration_h,multiplicity
3.65,2,q
1.26,3,t
2.10,1,br s
"""


def _client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'route_telemetry.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app)


def test_processed_analyze_lands_in_the_rollup(tmp_path) -> None:
    with _client(tmp_path) as client:
        analyze = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "telemetry-probe",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": (
                    "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)"
                ),
                "candidates_text": "ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )
        assert analyze.status_code == 200

        summary = client.get(
            "/admin/ops/route-telemetry-summary",
            headers=HEADERS,
            params={"event_type": "nmr.processed.analyze", "window_days": 7},
        )
    assert summary.status_code == 200
    body = summary.json()
    assert body["event_type"] == "nmr.processed.analyze"
    assert body["invocations"] >= 1
    assert body["wall_ms_sample_count"] >= 1
    assert body["median_wall_ms"] is not None and body["median_wall_ms"] >= 0
    assert body["p95_wall_ms"] is not None and body["p95_wall_ms"] >= body["median_wall_ms"] * 0


def test_unknown_event_type_fails_loudly(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/admin/ops/route-telemetry-summary",
            headers=HEADERS,
            params={"event_type": "spectrum.analyze_gsd_typo"},
        )
    assert response.status_code == 422
    assert "not a timed event type" in response.json()["detail"]


def test_empty_window_reads_as_no_data_not_instant(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/admin/ops/route-telemetry-summary",
            headers=HEADERS,
            params={"event_type": "nmr.raw_fid.process"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["invocations"] == 0
    assert body["median_wall_ms"] is None
    assert body["p95_wall_ms"] is None
