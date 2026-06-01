"""Remote NMRNet backend — an HTTP client to the NMRNet GPU microservice.

This is the **microservice topology** for the NMRNet wrapper (the recommended
one): NMRNet runs in its own Python-3.8 / CUDA container (see
``nmrnet_service/``), and the main MolTrace backend talks to it over HTTP. That
keeps the main process **torch-free** and lets the GPU scale independently.

Wire it up with two environment variables::

    MOLTRACE_NMRNET_MODULE=moltrace.spectroscopy.predict.nmrnet_client
    MOLTRACE_NMRNET_SERVICE_URL=http://<gpu-host>:8000

``predict_shifts(...)`` then routes through this client. If the URL is unset the
loader raises :class:`NMRNetUnavailable` (→ HOSE fallback); if the service is
unreachable at call time the request error propagates and the wrapper falls back
too. No local torch or weights are required here — hence
``REQUIRES_LOCAL_TORCH = False``.

The service contract (kept deliberately tiny)::

    POST {url}/predict
    request : {"symbols": ["C","C","H",...],
               "coordinates": [[x,y,z], ...],   # Å, one per atom, same order
               "nuclei": ["1H","13C"]}
    response: {"shifts": {"<atom_index>": [predicted_ppm, uncertainty_ppm], ...}}
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Sequence

from .nmrnet_wrapper import NMRNetUnavailable

# Tells _NMRNetBackend.load() not to require a local torch / checkpoint.
REQUIRES_LOCAL_TORCH = False

_DEFAULT_TIMEOUT_S = float(os.environ.get("MOLTRACE_NMRNET_TIMEOUT", "30"))


class _RemoteNMRNet:
    """Callable model proxy that delegates inference to the remote service."""

    def __init__(self, url: str, timeout_s: float) -> None:
        self._predict_url = url.rstrip("/") + "/predict"
        self._timeout_s = timeout_s

    def __call__(
        self,
        symbols: Sequence[str],
        coordinates: Sequence[Sequence[float]],
        nuclei: Sequence[str],
    ) -> dict[int, tuple[float, float]]:
        payload = json.dumps(
            {
                "symbols": list(symbols),
                "coordinates": [[float(c) for c in xyz] for xyz in coordinates],
                "nuclei": list(nuclei),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._predict_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Propagate as a generic error; predict_shifts() catches it and falls
            # back to the HOSE predictor rather than failing the whole request.
            raise RuntimeError(f"NMRNet service call failed: {exc}") from exc

        shifts = body.get("shifts", {})
        return {
            int(atom_index): (float(value[0]), float(value[1]))
            for atom_index, value in shifts.items()
        }


def load_pretrained(weights_path: str | None = None) -> _RemoteNMRNet:
    """Return a remote-model proxy, or raise if the service URL is unconfigured.

    ``weights_path`` is ignored here — the checkpoint lives on the GPU service.
    """

    url = os.environ.get("MOLTRACE_NMRNET_SERVICE_URL")
    if not url:
        raise NMRNetUnavailable(
            "remote NMRNet backend selected but MOLTRACE_NMRNET_SERVICE_URL is unset"
        )
    return _RemoteNMRNet(url, _DEFAULT_TIMEOUT_S)
