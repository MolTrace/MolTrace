"""Render the public error-code vocabulary into the TypeScript clients that mirror it.

``error_codes.py`` is the source of truth. The frontend proxy needs the same list at runtime
to decide which ``code`` survives 401/403 sanitization, and a desktop transport will need it
too. Hand-maintaining that list is what this module exists to stop: the registry's own
docstring names "three lists for one idea" as the problem, and a fourth would be the same
mistake with a different file extension.

This is deliberately **not** a fourth copy of the codes. It is a renderer plus a list of file
paths — the vocabulary is read from the registry at call time, so the only way to change what
is generated is to change the registry.

Why a generated *runtime* module rather than leaning on the generated OpenAPI types:
``schema.d.ts`` is declarations only and is erased at build time, so a ``Set`` cannot be built
from it; and nothing in CI verifies the checked-in ``schema.d.ts`` is current, so it cannot
serve as an arbiter of anything.

Regenerate with::

    cd moltrace_backend && uv run python -m nmrcheck.error_code_mirrors --write
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import error_codes

_HEADER = """// GENERATED FILE — do not edit.
// Source: moltrace_backend/src/nmrcheck/error_codes.py (PUBLIC_CODES).
// Regenerate: cd moltrace_backend && uv run python -m nmrcheck.error_code_mirrors --write
// Pinned by moltrace_backend/tests/test_error_code_mirrors.py.
"""


@dataclass(frozen=True)
class MirrorTarget:
    """One generated TypeScript module and the app directory that owns it."""

    #: Repo-root-relative path of the generated module.
    path: str
    #: The sibling application directory. If it is ABSENT the checkout is partial and the
    #: target is skipped; if it is PRESENT and the generated file is missing or stale, that
    #: is a failure. The asymmetry is deliberate — a backend-only checkout must still pass.
    app_dir: str


MIRROR_TARGETS: tuple[MirrorTarget, ...] = (
    MirrorTarget("moltrace_frontend/lib/api/public-error-codes.generated.ts", "moltrace_frontend"),
    # Phase 1, when the desktop package lands, registering it here is the whole change:
    # MirrorTarget(
    #     "moltrace_desktop/src/transport/public-error-codes.generated.ts", "moltrace_desktop"
    # ),
)


def repo_root() -> Path:
    """The monorepo root: ``src/nmrcheck/`` -> ``moltrace_backend/`` -> root."""

    return Path(__file__).resolve().parents[3]


def render_typescript() -> str:
    """The generated module. Deterministic — sorted codes, fixed header — so a test can
    byte-compare it against the checked-in file and fail on drift rather than on formatting."""

    codes = sorted(error_codes.PUBLIC_CODES)
    lines = [
        _HEADER,
        "/** Codes the backend marks safe to survive 401/403 sanitization. */",
        "export const PUBLIC_ERROR_CODES = [",
        *(f'  "{code}",' for code in codes),
        "] as const",
        "",
        "export type PublicErrorCode = (typeof PUBLIC_ERROR_CODES)[number]",
        "",
        "export const PUBLIC_ERROR_CODE_SET: ReadonlySet<PublicErrorCode> = new Set(",
        "  PUBLIC_ERROR_CODES,",
        ")",
        "",
    ]
    return "\n".join(lines)


def write_mirrors() -> list[Path]:
    """Write every target whose app directory exists. Returns the paths written."""

    root = repo_root()
    rendered = render_typescript()
    written: list[Path] = []
    for target in MIRROR_TARGETS:
        if not (root / target.app_dir).is_dir():
            continue
        destination = root / target.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        written.append(destination)
    return written


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--write" in args:
        for path in write_mirrors():
            print(f"wrote {path}")
        return 0
    sys.stdout.write(render_typescript())
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI seam
    raise SystemExit(main())
