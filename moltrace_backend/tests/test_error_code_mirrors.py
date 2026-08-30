"""The generated TypeScript mirror stays in step with the registry.

The vocabulary has to exist in more than one language: Python decides it, and the proxy needs
it at runtime to sanitize a 401/403. Every previous copy was hand-maintained and every one of
them drifted, which is what ``error_codes``'s docstring is complaining about. Generating the
copy only helps if something fails when the checked-in file is stale — otherwise it is a
hand-maintained list with a misleading header.
"""

from __future__ import annotations

import pytest

from nmrcheck import error_code_mirrors, error_codes


def test_the_render_is_deterministic() -> None:
    """A byte-comparison is only a fair test if the renderer is stable."""

    assert error_code_mirrors.render_typescript() == error_code_mirrors.render_typescript()


def test_the_render_carries_every_public_code_and_nothing_else() -> None:
    rendered = error_code_mirrors.render_typescript()
    for code in error_codes.PUBLIC_CODES:
        assert f'"{code}"' in rendered
    # A non-public code must never reach a client-side allowlist: that is the direction §3.3
    # calls impossible by construction, and this is the construction.
    for code in error_codes.REGISTRY:
        if code not in error_codes.PUBLIC_CODES:
            assert f'"{code}"' not in rendered


@pytest.mark.parametrize("target", error_code_mirrors.MIRROR_TARGETS, ids=lambda t: t.path)
def test_the_checked_in_mirror_is_current(target: error_code_mirrors.MirrorTarget) -> None:
    """Stale mirror -> failure, with the regeneration command in the message.

    Skipped when the sibling app is absent, because a backend-only checkout is legitimate;
    NOT skipped when the app is present and the file is missing, because that is the drift
    this exists to catch.
    """

    root = error_code_mirrors.repo_root()
    if not (root / target.app_dir).is_dir():
        pytest.skip(f"{target.app_dir} is not in this checkout")

    path = root / target.path
    assert path.exists(), (
        f"{target.path} is missing. Regenerate: "
        "cd moltrace_backend && uv run python -m nmrcheck.error_code_mirrors --write"
    )
    assert path.read_text(encoding="utf-8") == error_code_mirrors.render_typescript(), (
        f"{target.path} is stale. Regenerate: "
        "cd moltrace_backend && uv run python -m nmrcheck.error_code_mirrors --write"
    )
