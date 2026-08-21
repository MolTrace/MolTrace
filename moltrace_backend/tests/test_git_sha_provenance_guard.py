"""Deploy guard for build provenance — a result with no code revision must be loud.

``RegistryEntry.code_sha`` records which code revision produced a regulated result.
It resolves ``$MOLTRACE_GIT_SHA`` -> ``git rev-parse`` -> the literal ``"unknown"``
(``spectroscopy/infra/versioning.py:109``) and never raises, so a failure to resolve
is invisible at the point of use.

In the deployed image the middle step cannot succeed: ``.dockerignore`` excludes
``.git/`` and the runtime stage is a bare ``python`` base with no git installed.
Until the ``MOLTRACE_GIT_SHA`` build argument was wired through ``cloudbuild.yaml``,
nothing set the variable, so every ``code_sha`` in production was ``"unknown"`` —
provenance was not degraded, it was absent.

These tests pin the runtime half, matching ``test_hose_kb_deploy_guard.py``: the
startup surface must say so. The build-time half is the Dockerfile's
``ARG MOLTRACE_GIT_SHA`` plus the ``--build-arg`` in ``cloudbuild.yaml``.
"""

from __future__ import annotations

from moltrace.spectroscopy.infra import versioning
from nmrcheck.settings import Settings, validate_startup_settings

_ISSUE_KEY = "MOLTRACE_GIT_SHA"


def _issues(env: str, monkeypatch, *, sha: str) -> list[str]:
    monkeypatch.setattr(versioning, "current_git_sha", lambda **_: sha)
    return validate_startup_settings(Settings(app_env=env))


def test_production_without_a_resolvable_revision_is_a_startup_issue(monkeypatch) -> None:
    issues = _issues("production", monkeypatch, sha="unknown")
    assert any(_ISSUE_KEY in issue for issue in issues)


def test_production_with_a_resolvable_revision_is_silent(monkeypatch) -> None:
    issues = _issues("production", monkeypatch, sha="f8ec66a62b7a")
    assert not any(_ISSUE_KEY in issue for issue in issues)


def test_development_is_not_nagged(monkeypatch) -> None:
    """A developer checkout without git provenance is normal, not a defect."""
    issues = _issues("development", monkeypatch, sha="unknown")
    assert not any(_ISSUE_KEY in issue for issue in issues)


def test_empty_env_var_falls_through_and_is_never_treated_as_a_revision(monkeypatch) -> None:
    """The Dockerfile defaults the build argument to EMPTY on purpose.

    ``_TAG`` falls back to ``"latest"`` for a manual build, and stamping that into
    provenance would be a plausible-looking lie. Empty must be falsy here so it
    falls through to the honest ``"unknown"``. If this ever returns ``""`` as a
    revision, the Dockerfile's default becomes unsafe.
    """
    monkeypatch.setenv("MOLTRACE_GIT_SHA", "")
    monkeypatch.setattr(versioning.subprocess, "run", _raise_oserror)
    assert versioning.current_git_sha() == "unknown"


def test_a_set_revision_wins_over_git(monkeypatch) -> None:
    monkeypatch.setenv("MOLTRACE_GIT_SHA", "abc123def4567890")
    monkeypatch.setattr(versioning.subprocess, "run", _raise_oserror)
    assert versioning.current_git_sha() == "abc123def4567890"
    assert versioning.current_git_sha(short=True) == "abc123d"


def _raise_oserror(*_args, **_kwargs):
    """Stand in for the deployed image, where the git binary is absent."""
    raise OSError("git not found")
