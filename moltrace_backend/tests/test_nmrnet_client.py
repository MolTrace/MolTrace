"""NMRNet sidecar client + remote-route invariants (B0).

These run a real ``http.server`` on localhost rather than monkeypatching
``urllib``, so the transport, JSON handling, timeout and error paths are actually
exercised. No network egress, no new dependency.

The invariant that matters throughout: **a failing service must never become a
fabricated number.** Every failure mode below must end in the HOSE fallback with
``method == 'hose_fallback'`` recorded, not in a plausible-looking shift.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from moltrace.spectroscopy.predict import nmrnet_client
from moltrace.spectroscopy.predict.nmrnet_wrapper import predict_shifts

ETHANOL = "CCO"


def _make_server(handler_factory):
    """Start a one-off HTTP server on an ephemeral port; yield its base URL."""

    server = HTTPServer(("127.0.0.1", 0), handler_factory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


class _Handler(BaseHTTPRequestHandler):
    """Configurable stand-in for ``nmrnet_service/app.py``."""

    health_ok = True
    predict_status = 200
    predict_body: object = None
    seen_payloads: list[dict] = []

    def log_message(self, *args):  # silence test output
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": self.health_ok})
        else:
            self._send(404, {})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length).decode()) if length else {}
        type(self).seen_payloads.append(payload)
        if self.predict_status != 200:
            self._send(self.predict_status, {"detail": "boom"})
            return
        body = self.predict_body
        if body is None:
            # Echo a plausible response: every atom gets a shift.
            n = len(payload.get("symbols", []))
            body = {"shifts": {str(i): [100.0 + i, 0.5] for i in range(n)}}
        self._send(200, body)

    def _send(self, status: int, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def service(monkeypatch):
    """A running fake sidecar, wired into the env the wrapper reads."""

    handler = type("H", (_Handler,), {"seen_payloads": []})
    server, url = _make_server(handler)
    monkeypatch.setenv("MOLTRACE_NMRNET_SERVICE_URL", url)
    monkeypatch.setenv("MOLTRACE_NMRNET_TIMEOUT_S", "5")
    try:
        yield handler, url
    finally:
        server.shutdown()
        server.server_close()


# --------------------------------------------------------------------------- #
# Client contract
# --------------------------------------------------------------------------- #
def test_service_url_unset_is_not_an_error(monkeypatch):
    """No sidecar is a normal deployment, not a failure."""

    monkeypatch.delenv("MOLTRACE_NMRNET_SERVICE_URL", raising=False)
    assert nmrnet_client.service_url() is None


def test_service_url_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setenv("MOLTRACE_NMRNET_SERVICE_URL", "file:///etc/passwd")
    with pytest.raises(nmrnet_client.NMRNetServiceError, match="http"):
        nmrnet_client.service_url()


def test_health_reflects_model_loaded(service):
    handler, url = service
    assert nmrnet_client.health(url) is True

    handler.health_ok = False
    assert nmrnet_client.health(url) is False, (
        "a reachable service whose model failed to load must read as unavailable"
    )


def test_predict_returns_indexed_shifts(service):
    _handler, url = service
    out = nmrnet_client.predict(["C", "H"], [[0, 0, 0], [1, 0, 0]], ["1H", "13C"], base_url=url)
    assert out == {0: (100.0, 0.5), 1: (101.0, 0.5)}


def test_predict_sends_symbols_and_coordinates_one_to_one(service):
    handler, url = service
    nmrnet_client.predict(["C", "O"], [[0, 0, 0], [1.4, 0, 0]], ["13C"], base_url=url)
    sent = handler.seen_payloads[-1]
    assert sent["symbols"] == ["C", "O"]
    assert sent["coordinates"] == [[0.0, 0.0, 0.0], [1.4, 0.0, 0.0]]
    assert sent["nuclei"] == ["13C"]


def test_predict_rejects_mismatched_symbols_and_coordinates(service):
    _handler, url = service
    with pytest.raises(nmrnet_client.NMRNetServiceError, match="1:1"):
        nmrnet_client.predict(["C", "H"], [[0, 0, 0]], ["1H"], base_url=url)


@pytest.mark.parametrize(
    "body, match",
    [
        ({"nope": {}}, "shifts"),
        ({"shifts": {}}, "empty"),
        ({"shifts": {"0": ["not-a-number", 1.0]}}, "malformed"),
        ({"shifts": {"999": [1.0, 0.1]}}, "outside"),
    ],
)
def test_predict_rejects_malformed_responses(service, body, match):
    """A garbled body is a failure, never a partially-trusted result."""

    handler, url = service
    handler.predict_body = body
    with pytest.raises(nmrnet_client.NMRNetServiceError, match=match):
        nmrnet_client.predict(["C"], [[0, 0, 0]], ["13C"], base_url=url)


def test_predict_surfaces_http_error(service):
    handler, url = service
    handler.predict_status = 500
    with pytest.raises(nmrnet_client.NMRNetServiceError, match="500"):
        nmrnet_client.predict(["C"], [[0, 0, 0]], ["13C"], base_url=url)


def test_predict_unreachable_service_raises_not_fabricates(monkeypatch):
    # Port 1 is reserved and closed; this exercises the real connect-refused path.
    with pytest.raises(nmrnet_client.NMRNetServiceError):
        nmrnet_client.predict(
            ["C"], [[0, 0, 0]], ["13C"], base_url="http://127.0.0.1:1", timeout=2
        )


# --------------------------------------------------------------------------- #
# The wrapper's remote route
# --------------------------------------------------------------------------- #
def test_configured_service_routes_through_nmrnet_not_hose(service):
    """The gap B0 closes: a configured sidecar must actually be reached.

    Before this, MOLTRACE_NMRNET_SERVICE_URL was documented in the service README
    but read by nothing, so every prediction fell to HOSE regardless.
    """

    prediction = predict_shifts(ETHANOL, nuclei=("1H", "13C"))
    assert prediction.method == "nmrnet"
    assert prediction.device == "remote"
    assert all(s.source == "nmrnet" for s in prediction.shifts)
    assert prediction.prior_fallback_fraction == 0.0


def test_remote_route_needs_no_torch(service, monkeypatch):
    """The production API host is torch-free; requiring torch would rule it out."""

    import builtins

    real_import = builtins.__import__

    def _no_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise ImportError("torch is not installed on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_torch)
    prediction = predict_shifts(ETHANOL, nuclei=("13C",))
    assert prediction.method == "nmrnet"


def test_ensemble_spread_becomes_the_uncertainty(service):
    """Uncertainty must mean the same thing on the remote path as the local one."""

    prediction = predict_shifts(ETHANOL, nuclei=("13C",), n_conformers=4)
    assert prediction.n_conformers > 1
    # The fake service is deterministic per atom, so spread is exactly zero —
    # the point is that a real number was computed, not left NaN.
    assert all(s.uncertainty_ppm == pytest.approx(0.0) for s in prediction.shifts)


@pytest.mark.parametrize(
    "break_it",
    [
        {"predict_status": 500},
        {"predict_body": {"shifts": {}}},
        {"predict_body": {"garbage": True}},
    ],
)
def test_service_failure_falls_back_and_records_the_method(service, break_it):
    """The core safety property: a broken sidecar degrades, it does not invent."""

    handler, _url = service
    for key, value in break_it.items():
        setattr(handler, key, value)

    prediction = predict_shifts(ETHANOL, nuclei=("13C",))
    assert prediction.method == "hose_fallback"
    assert any("NMRNet" in w for w in prediction.warnings), (
        "the fallback must say why it fell back"
    )


def test_unreachable_service_falls_back(monkeypatch):
    monkeypatch.setenv("MOLTRACE_NMRNET_SERVICE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MOLTRACE_NMRNET_TIMEOUT_S", "2")
    prediction = predict_shifts(ETHANOL, nuclei=("13C",))
    assert prediction.method == "hose_fallback"


def test_allow_fallback_false_still_raises_on_service_failure(service):
    """A caller that opts out of the fallback must get an error, not a prior."""

    handler, _url = service
    handler.predict_status = 503
    with pytest.raises(Exception) as excinfo:
        predict_shifts(ETHANOL, nuclei=("13C",), allow_fallback=False)
    assert "NMRNet" in str(excinfo.value)
