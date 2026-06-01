"""Tests for the remote NMRNet backend client (HTTP microservice topology).

The GPU service isn't running in CI, so we mock ``urllib.request.urlopen`` and
verify (a) the client serialises atoms+coords and parses the shift map, (b) the
wrapper routes through it to backend ``"nmrnet"`` end-to-end, (c) a missing
service URL is a clean ``NMRNetUnavailable``, and (d) an unreachable service
falls back to the HOSE predictor instead of erroring.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from moltrace.spectroscopy.predict import predict_shifts
from moltrace.spectroscopy.predict.nmrnet_client import (
    NMRNetUnavailable,
    load_pretrained,
)

_CLIENT_MODULE = "moltrace.spectroscopy.predict.nmrnet_client"


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _fake_service(monkeypatch, *, c_ppm=50.0, h_ppm=5.0) -> None:
    """Patch urlopen to behave like a conformant NMRNet service."""

    def fake_urlopen(request, timeout=None):
        payload = json.loads(request.data)
        shifts = {}
        for index, symbol in enumerate(payload["symbols"]):
            if symbol == "C":
                shifts[str(index)] = [c_ppm, 0.4]
            elif symbol == "H":
                shifts[str(index)] = [h_ppm, 0.1]
        return _FakeResponse(json.dumps({"shifts": shifts}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_load_pretrained_requires_service_url(monkeypatch) -> None:
    monkeypatch.delenv("MOLTRACE_NMRNET_SERVICE_URL", raising=False)
    with pytest.raises(NMRNetUnavailable):
        load_pretrained()


def test_wrapper_routes_through_remote_service(monkeypatch) -> None:
    _fake_service(monkeypatch, c_ppm=50.0, h_ppm=5.0)
    monkeypatch.setenv("MOLTRACE_NMRNET_MODULE", _CLIENT_MODULE)
    monkeypatch.setenv("MOLTRACE_NMRNET_SERVICE_URL", "http://fake-nmrnet:8000")

    result = predict_shifts("CC", nuclei=["1H", "13C"])  # ethane

    assert result.backend == "nmrnet"
    assert result.notes == ()
    carbons = [s.predicted_ppm for s in result.shifts.values() if s.element == "C"]
    hydrogens = [s.predicted_ppm for s in result.shifts.values() if s.element == "H"]
    assert carbons and all(abs(v - 50.0) < 1e-9 for v in carbons)
    assert hydrogens and all(abs(v - 5.0) < 1e-9 for v in hydrogens)
    assert all(s.method == "nmrnet" for s in result.shifts.values())


def test_unreachable_service_falls_back_to_hose(monkeypatch) -> None:
    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setenv("MOLTRACE_NMRNET_MODULE", _CLIENT_MODULE)
    monkeypatch.setenv("MOLTRACE_NMRNET_SERVICE_URL", "http://down:8000")

    result = predict_shifts("c1ccccc1")  # benzene
    assert result.backend == "hose_nmrshiftdb2"
    assert any("inference failed" in note.lower() for note in result.notes)
    # And the fallback still produced sensible benzene shifts.
    assert any(abs(s.predicted_ppm - 128.4) < 0.5 for s in result.shifts.values() if s.nucleus == "13C")
