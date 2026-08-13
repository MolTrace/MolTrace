"""Resolve real-spectra fixtures without naming them in tracked code.

The repository is public. The maintainer's compounds, sample codes and the
spectra derived from them are not publishable, and a hard-coded fixture path
publishes a sample code just as effectively as committing the data would — the
directory name *is* the compound's identity.

So tracked code refers to a fixture by a **role** ("the quantitative half of the
matched pair"), and the mapping from role to directory lives in

    validation_fixtures/fixture_map.json      (gitignored)

which looks like::

    {
      "quantitative_pair_relaxed": "bruker/<dir>/10/pdata/1",
      "quantitative_pair_routine": "bruker/<dir>/11/pdata/1",
      "hsqc_edited":               "nmr2d/<dir>/25"
    }

An environment variable of the same name (upper-cased, ``MOLTRACE_FIXTURE_``
prefixed) overrides an entry, so a machine can point at spectra held outside the
repository entirely.

Every consumer must skip cleanly when a role is unresolved. A fixture that is
absent is the normal state for anyone who is not the maintainer, and a test that
errors instead of skipping would make the public suite unrunnable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = ["fixture_root", "resolve_fixture", "fixture_reason"]

_MAP_NAME = "fixture_map.json"
_ENV_PREFIX = "MOLTRACE_FIXTURE_"


def fixture_root() -> Path:
    return Path(__file__).resolve().parent.parent / "validation_fixtures"


def _load_map() -> dict[str, str]:
    path = fixture_root() / _MAP_NAME
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def resolve_fixture(role: str) -> Path | None:
    """Directory for ``role``, or None when it is not available here.

    None is the expected answer on any machine without the maintainer's spectra.
    Callers skip; they must not raise, and must not fall back to a guessed path.
    """
    override = os.environ.get(_ENV_PREFIX + role.upper())
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.exists() else None

    relative = _load_map().get(role)
    if not relative:
        return None
    candidate = fixture_root() / relative
    return candidate if candidate.exists() else None


def fixture_reason(role: str) -> str:
    """Skip message that explains the absence without naming the sample."""
    return (
        f"fixture role {role!r} is not available on this machine. Real spectra are "
        f"gitignored and their identities are not published; map the role in "
        f"validation_fixtures/{_MAP_NAME} or set {_ENV_PREFIX}{role.upper()}."
    )
