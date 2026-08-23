"""`fid.process` served locally — the first operation that does science.

Everything before this was admission control around an empty room: the guards
worked, the journal recorded, and the one route returned {"status": "ok"}. This
is the operation the desktop exists for, and the point of the test is that it
runs with NO database, NO network and NO authorization — which is what makes it
servable offline at all.
"""

from __future__ import annotations

import numpy as np
import pytest
from starlette.testclient import TestClient

from nmrcheck.local_science import PeakSummary, process_spectrum
from nmrcheck.local_service_app import HANDLER_CALLS, JOURNAL, create_local_app

CRED = "c" * 43


def auth() -> dict[str, str]:
    return {"x-moltrace-local-service": CRED}


@pytest.fixture
def client() -> TestClient:
    HANDLER_CALLS.clear()
    JOURNAL.clear()
    return TestClient(create_local_app(credential=CRED), raise_server_exceptions=False)


def two_peaks() -> dict:
    ppm = np.linspace(10.0, 0.0, 8192)
    data = np.exp(-((ppm - 7.26) ** 2) / 1e-4) + 0.5 * np.exp(-((ppm - 2.10) ** 2) / 1e-4)
    return {"ppm_axis": ppm.tolist(), "intensity": data.tolist(), "nucleus": "1H", "field_mhz": 400.0}


# --- the science itself, no HTTP ------------------------------------------


def test_it_runs_with_no_database_no_network_and_no_authorization() -> None:
    """The property that makes this servable offline at all."""
    result = process_spectrum(**two_peaks())
    assert len(result) == 2
    assert all(isinstance(p, PeakSummary) for p in result)
    assert result[0].position_ppm == pytest.approx(7.26, abs=0.05)


def test_an_empty_spectrum_is_refused_rather_than_returning_nothing() -> None:
    """Zero peaks from an empty input is a true answer to a question nobody asked.
    A caller cannot tell it from 'the analysis found nothing', which is different."""
    with pytest.raises(ValueError):
        process_spectrum(ppm_axis=[], intensity=[], nucleus="1H", field_mhz=400.0)


def test_mismatched_axes_are_refused() -> None:
    with pytest.raises(ValueError):
        process_spectrum(ppm_axis=[1.0, 2.0], intensity=[1.0], nucleus="1H", field_mhz=400.0)


# --- served over the local transport --------------------------------------


def test_the_operation_is_served_and_journalled(client: TestClient) -> None:
    r = client.post("/fid/process", headers=auth(), json=two_peaks())
    assert r.status_code == 200, r.text
    assert len(r.json()["peaks"]) == 2
    assert any(e.payload["operation"] == "fid.process" for e in JOURNAL)


def test_it_is_NOT_served_without_the_credential(client: TestClient) -> None:
    r = client.post("/fid/process", json=two_peaks())
    assert r.status_code == 401
    assert HANDLER_CALLS == [], "the science handler ran on an unauthenticated request"


def test_a_bad_spectrum_returns_a_refusal_not_a_crash(client: TestClient) -> None:
    r = client.post("/fid/process", headers=auth(), json={"ppm_axis": [], "intensity": [],
                                                          "nucleus": "1H", "field_mhz": 400.0})
    assert r.status_code == 400, r.text
    assert "detail" in r.json()


def test_the_response_carries_no_device_timestamp_as_a_record_time(client: TestClient) -> None:
    """§8.4. The result is science, not a record — and it must not look like one."""
    body = client.post("/fid/process", headers=auth(), json=two_peaks()).json()
    assert "record_time" not in body
    assert "timestamp" not in body
