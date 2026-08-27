"""The fitted conformal calibration must actually reach the verifier in production.

``VerificationOptions.shift_calibration`` existed and was consumed, but no production caller
ever set it, so every real verdict was scored on the predictor's claimed sigma -- the basis
held-out measurement showed is differentially mis-scaled (half-width/sigma running 8.66x down
to 1.77x, where a correct sigma gives a constant, and worst in the tight bins the arbiter leans
on hardest). A capability that nothing reaches is indistinguishable from one that does not
exist, so these tests pin the path rather than the arithmetic: the shipped artifact loads, the
image points at it, and an operator can see which basis is live.

The scoring behaviour itself is covered by tests/spectroscopy/test_verifier_significance_basis.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moltrace.spectroscopy.eval import conformal as conformal_mod
from moltrace.spectroscopy.eval.conformal import (
    CALIBRATION_PATH_ENV,
    CALIBRATION_VERSION,
    ConformalCalibration,
    conformal_calibration_status,
    load_deployed_calibration,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARTIFACT = _REPO_ROOT / "data" / "conformal" / "shift_calibration.json"


@pytest.fixture(autouse=True)
def _reset_calibration_cache(monkeypatch: pytest.MonkeyPatch):
    """The loader caches for the life of the process; each test needs a cold one."""

    monkeypatch.setattr(conformal_mod, "_DEPLOYED", None, raising=False)
    monkeypatch.setattr(conformal_mod, "_DEPLOYED_LOADED", False, raising=False)
    yield
    monkeypatch.setattr(conformal_mod, "_DEPLOYED", None, raising=False)
    monkeypatch.setattr(conformal_mod, "_DEPLOYED_LOADED", False, raising=False)


def test_the_shipped_artifact_exists_and_survives_its_own_guards() -> None:
    """Version and fingerprint are both checked on load; the shipped file must pass both."""

    assert _ARTIFACT.exists(), f"{_ARTIFACT} is missing; the image's env var would dangle"
    calibration = ConformalCalibration.from_json(_ARTIFACT.read_text(encoding="utf-8"))

    assert calibration.version == CALIBRATION_VERSION
    # Deployed at the target that met its guarantee on both nuclei (0.90: worst_deficit 0.0).
    # The 0.95 fit undershot on 13C and was deliberately not shipped -- see the README.
    assert calibration.target_coverage == pytest.approx(0.90)
    assert calibration.bins, "a calibration with no bins would silently score nothing"

    # The fingerprint recorded in the file is the fingerprint of its contents.
    stored = json.loads(_ARTIFACT.read_text(encoding="utf-8"))
    assert stored["fingerprint"] == calibration.fingerprint()


def test_an_edited_artifact_is_refused_rather_than_used() -> None:
    """A calibration whose numbers were changed after fitting is not a calibration."""

    stored = json.loads(_ARTIFACT.read_text(encoding="utf-8"))
    stored["bins"][0]["half_width_ppm"] = float(stored["bins"][0]["half_width_ppm"]) * 2.0
    with pytest.raises(ValueError):
        ConformalCalibration.from_json(json.dumps(stored))


def test_the_loader_reads_the_shipped_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CALIBRATION_PATH_ENV, str(_ARTIFACT))
    calibration = load_deployed_calibration()
    assert calibration is not None
    assert calibration.target_coverage == pytest.approx(0.90)

    status = conformal_calibration_status()
    assert status["configured"] is True
    assert status["path_present"] is True
    assert status["loaded"] is True
    assert status["basis"] == "conformal"
    assert status["fingerprint"] == calibration.fingerprint()


def test_unset_falls_back_to_sigma_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dev checkout with no artifact is a legitimate configuration, not a failure."""

    monkeypatch.delenv(CALIBRATION_PATH_ENV, raising=False)
    assert load_deployed_calibration() is None
    assert conformal_calibration_status()["basis"] == "predicted_sigma"


def test_set_and_missing_is_logged_at_error_not_absorbed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """What a deploy that forgot to stage the artifact looks like. It must be loud."""

    monkeypatch.setenv(CALIBRATION_PATH_ENV, str(tmp_path / "absent.json"))
    with caplog.at_level("ERROR"):
        assert load_deployed_calibration() is None
    assert any(CALIBRATION_PATH_ENV in record.getMessage() for record in caplog.records)


def test_a_corrupt_artifact_degrades_to_sigma_rather_than_refusing_service(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """A bad file must not take the service down -- the sigma basis is weaker, not absent."""

    bad = tmp_path / "corrupt.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(CALIBRATION_PATH_ENV, str(bad))
    with caplog.at_level("ERROR"):
        assert load_deployed_calibration() is None
    assert conformal_calibration_status()["basis"] == "predicted_sigma"


def test_the_image_points_at_a_path_that_exists_in_the_build_context() -> None:
    """The Dockerfile's env var and the artifact's location must move together.

    The HOSE table taught this: an env var pointing at a file nobody stages produces a service
    that runs on the degraded basis and says nothing. Here the artifact is in the repository, so
    the only way to break it is to move or rename one side without the other.
    """

    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    line = next(
        (ln for ln in dockerfile.splitlines() if CALIBRATION_PATH_ENV in ln),
        None,
    )
    assert line is not None, f"the image does not set {CALIBRATION_PATH_ENV}"

    container_path = line.split("=", 1)[1].strip().rstrip("\\").strip()
    assert container_path.startswith("/app/"), container_path
    assert (_REPO_ROOT / container_path[len("/app/") :]).exists(), (
        f"{container_path} is set in the image but no such file exists in the build context"
    )
