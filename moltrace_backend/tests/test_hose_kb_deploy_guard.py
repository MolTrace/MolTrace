"""Deploy guard for the HOSE knowledge base — a degraded predictor must be loud.

A CI checkout is clean and ``data/hose`` is gitignored, so an image can be built
whose predictor silently answers from the 16-molecule seed table (~35 ppm median
13C uncertainty vs ~1.88 ppm with the full NMRShiftDB2 index). These tests pin
the runtime half of the guard: status introspection, startup issues, and the
health surface. The build-time half is the Dockerfile ``REQUIRE_HOSE_KB``
assertion plus the CI staging step in ``ci-cd.yml``; the lazy set-and-missing
ERROR log is pinned separately in ``test_hose_kb_index_format.py``.
"""

from __future__ import annotations

from moltrace.spectroscopy.predict import nmrnet_wrapper
from nmrcheck.api import _health_response
from nmrcheck.settings import Settings, validate_startup_settings


def test_status_unset_env_reports_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("MOLTRACE_HOSE_KB", raising=False)
    monkeypatch.setattr(nmrnet_wrapper, "_FALLBACK_KB", None)
    assert nmrnet_wrapper.knowledge_base_status() == {
        "configured": False,
        "path_present": False,
        "loaded": False,
        "source": None,
        "reference_count": None,
    }


def test_status_set_and_missing_is_visible(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MOLTRACE_HOSE_KB", str(tmp_path / "not-staged.json.gz"))
    monkeypatch.setattr(nmrnet_wrapper, "_FALLBACK_KB", None)
    status = nmrnet_wrapper.knowledge_base_status()
    assert status["configured"] is True
    assert status["path_present"] is False


def test_status_reports_loaded_table_provenance(monkeypatch) -> None:
    seed = nmrnet_wrapper.build_seed_knowledge_base()
    monkeypatch.setattr(nmrnet_wrapper, "_FALLBACK_KB", seed)
    status = nmrnet_wrapper.knowledge_base_status()
    assert status["loaded"] is True
    assert status["source"] == seed.source
    assert status["reference_count"] == seed.reference_count


def test_startup_issue_when_production_is_unconfigured() -> None:
    issues = validate_startup_settings(Settings(app_env="production"))
    assert any("MOLTRACE_HOSE_KB" in issue for issue in issues)


def test_startup_issue_when_set_and_missing_in_any_env(tmp_path) -> None:
    issues = validate_startup_settings(
        Settings(app_env="development", hose_kb_path=str(tmp_path / "gone.json.gz"))
    )
    assert any("MOLTRACE_HOSE_KB" in issue for issue in issues)


def test_no_startup_issue_for_dev_seed_fallback() -> None:
    issues = validate_startup_settings(Settings(app_env="development"))
    assert not any("MOLTRACE_HOSE_KB" in issue for issue in issues)


def test_health_flags_set_and_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MOLTRACE_HOSE_KB", str(tmp_path / "gone.json.gz"))
    monkeypatch.setattr(nmrnet_wrapper, "_FALLBACK_KB", None)
    report = _health_response()
    assert report["checks"]["hose_kb"] == "error"
    assert report["status"] == "degraded"
    assert report["hose_kb"]["configured"] is True
    assert report["hose_kb"]["path_present"] is False


def test_health_ok_on_dev_seed(monkeypatch) -> None:
    monkeypatch.delenv("MOLTRACE_HOSE_KB", raising=False)
    monkeypatch.setattr(nmrnet_wrapper, "_FALLBACK_KB", None)
    report = _health_response()
    assert report["checks"]["hose_kb"] == "ok"
    assert report["status"] == "ok"
    assert report["hose_kb"]["configured"] is False
