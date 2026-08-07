"""HTTP client for the NMRNet GPU inference sidecar.

Why this module exists
----------------------
NMRNet needs torch + CUDA + Uni-Core (Python 3.8 / CUDA 11.6 on Linux x86_64).
The main MolTrace backend runs on Cloud Run without a GPU and deliberately stays
torch-free. So NMRNet runs as a separate service (``nmrnet_service/``) and this
module is the only thing that talks to it.

``nmrnet_service/README.md`` has documented this module as the integration route
since the service was written, but it did not exist, and ``nmrnet_wrapper`` had
no hook to call it — only a local-torch path that is unusable on the production
host. Every production prediction therefore fell through to the HOSE fallback.
This module plus the ``_remote_backend`` hook in the wrapper closes that.

Contract (mirrors ``nmrnet_service/app.py``)::

    GET  /health  -> {"ok": true}
    POST /predict    {"symbols": ["C","H",...],
                      "coordinates": [[x,y,z], ...],   # Angstrom, 1:1 with symbols
                      "nuclei": ["1H","13C"]}
                  -> {"shifts": {"<atom_index>": [predicted_ppm, uncertainty_ppm]}}

Design rules
------------
* **Never fabricate.** Any failure — unreachable, timeout, malformed body, model
  not loaded — raises :class:`NMRNetServiceError`. The caller converts that to
  ``NMRNetUnavailable`` and falls back *with the method recorded*. This module
  never invents a shift and never silently returns a partial result.
* **No new dependencies.** ``urllib.request`` from the standard library, matching
  the weight-download path in ``nmrnet_wrapper``.
* **Torch-free.** Nothing here imports torch, so it is safe on the API host.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from urllib.parse import urlparse

__all__ = [
    "NMRNetServiceError",
    "service_url",
    "health",
    "predict",
]

_DEFAULT_TIMEOUT_S = 30.0
_ALLOWED_SCHEMES = {"http", "https"}


class NMRNetServiceError(RuntimeError):
    """The sidecar could not produce a usable prediction. Always fall back."""


def service_url() -> str | None:
    """The configured sidecar base URL, or ``None`` when unconfigured.

    Unconfigured is a normal state, not an error: it means this deployment has no
    GPU sidecar and predictions use the HOSE fallback.
    """

    raw = os.environ.get("MOLTRACE_NMRNET_SERVICE_URL", "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        raise NMRNetServiceError(
            f"MOLTRACE_NMRNET_SERVICE_URL must be an http(s) URL; got {raw!r}"
        )
    return raw.rstrip("/")


def _timeout() -> float:
    try:
        return float(os.environ.get("MOLTRACE_NMRNET_TIMEOUT_S", _DEFAULT_TIMEOUT_S))
    except ValueError:
        return _DEFAULT_TIMEOUT_S


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise NMRNetServiceError(f"NMRNet service returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise NMRNetServiceError(f"NMRNet service unreachable: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise NMRNetServiceError(f"NMRNet service transport failure: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NMRNetServiceError("NMRNet service returned a non-JSON body") from exc


def health(base_url: str | None = None, timeout: float | None = None) -> bool:
    """``True`` only when the sidecar reports a loaded model.

    A reachable service whose model failed to load returns ``{"ok": false}`` and
    must be treated as unavailable — a loaded-looking service that cannot infer
    is exactly the case that would otherwise produce a confusing partial failure
    mid-request.
    """

    url = base_url or service_url()
    if not url:
        return False
    try:
        request = urllib.request.Request(f"{url.rstrip('/')}/health", method="GET")
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=timeout or _timeout()
        ) as response:
            return bool(json.loads(response.read().decode("utf-8")).get("ok"))
    except Exception:
        return False


def predict(
    symbols: Sequence[str],
    coordinates: Sequence[Sequence[float]],
    nuclei: Sequence[str],
    *,
    base_url: str | None = None,
    timeout: float | None = None,
) -> dict[int, tuple[float, float]]:
    """One conformer → ``{atom_index: (predicted_ppm, uncertainty_ppm)}``.

    ``symbols`` and ``coordinates`` are 1:1 per atom in RDKit ``AddHs`` order, so
    the returned atom indices align with the caller's molecule without a remap.

    Raises :class:`NMRNetServiceError` on any failure. Never returns a partial or
    invented result.
    """

    if len(symbols) != len(coordinates):
        raise NMRNetServiceError(
            f"symbols ({len(symbols)}) and coordinates ({len(coordinates)}) must be 1:1"
        )
    if not symbols:
        raise NMRNetServiceError("no atoms supplied")

    url = base_url or service_url()
    if not url:
        raise NMRNetServiceError("MOLTRACE_NMRNET_SERVICE_URL is not configured")

    payload = {
        "symbols": list(symbols),
        "coordinates": [[float(v) for v in xyz] for xyz in coordinates],
        "nuclei": list(nuclei),
    }
    body = _post_json(f"{url}/predict", payload, timeout or _timeout())

    raw = body.get("shifts")
    if not isinstance(raw, dict):
        raise NMRNetServiceError("NMRNet service response had no 'shifts' mapping")

    out: dict[int, tuple[float, float]] = {}
    for key, value in raw.items():
        try:
            atom_index = int(key)
            ppm, uncertainty = float(value[0]), float(value[1])
        except (TypeError, ValueError, IndexError) as exc:
            raise NMRNetServiceError(
                f"malformed shift entry for atom {key!r}: {value!r}"
            ) from exc
        if not 0 <= atom_index < len(symbols):
            raise NMRNetServiceError(
                f"atom index {atom_index} outside the {len(symbols)}-atom molecule sent"
            )
        out[atom_index] = (ppm, uncertainty)

    if not out:
        raise NMRNetServiceError("NMRNet service returned an empty shift set")
    return out
