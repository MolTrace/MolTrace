"""CSPM IaC posture drift gate (Security Prompt 18).

Unit-tests the pure scorer at infra/cspm/score_iac_posture.py — no Trivy needed; we
feed synthetic `trivy config --format json` reports. Covers finding extraction
(severity + FAIL filtering), drift computation, the CLI exit codes (no-drift→0,
drift→1, parse-error→2), and --update re-baselining.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# The scorer is repo-root infra tooling, not part of the nmrcheck package — load it by
# path. tests/ -> moltrace_backend/ -> <repo root> -> infra/cspm/score_iac_posture.py
_SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "cspm" / "score_iac_posture.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("score_iac_posture", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cspm = _load_module()


def _report(*misconfigs) -> dict:
    # Real Trivy reports carry SchemaVersion; the scorer's integrity guard requires it.
    return {
        "SchemaVersion": 2,
        "Results": [{"Target": "render.yaml", "Misconfigurations": list(misconfigs)}],
    }


def _m(mid: str, severity: str, status: str = "FAIL") -> dict:
    return {"ID": mid, "Severity": severity, "Status": status, "Title": mid}


def test_script_exists():
    assert _SCRIPT.exists(), _SCRIPT


# --------------------------------------------------------------------------- extract


def test_extract_only_failing_high_critical():
    report = _report(
        _m("AVD-1", "CRITICAL"),
        _m("AVD-2", "HIGH"),
        _m("AVD-3", "MEDIUM"),  # below threshold
        _m("AVD-4", "HIGH", status="PASS"),  # compliant, not a finding
    )
    found = cspm.extract_findings(report)
    assert found == {"AVD-1::render.yaml::CRITICAL", "AVD-2::render.yaml::HIGH"}


def test_extract_empty_report():
    assert cspm.extract_findings({}) == set()
    assert cspm.extract_findings({"Results": []}) == set()


def test_extract_target_distinguishes_same_check():
    report = {
        "Results": [
            {"Target": "a.yaml", "Misconfigurations": [_m("AVD-1", "HIGH")]},
            {"Target": "b.yaml", "Misconfigurations": [_m("AVD-1", "HIGH")]},
        ]
    }
    assert cspm.extract_findings(report) == {"AVD-1::a.yaml::HIGH", "AVD-1::b.yaml::HIGH"}


# --------------------------------------------------------------------------- drift


def test_compute_drift_is_new_minus_accepted():
    current = {"A::x", "B::y"}
    accepted = {"A::x"}
    assert cspm.compute_drift(current, accepted) == {"B::y"}
    assert cspm.compute_drift(accepted, current) == set()  # current subset of accepted


# --------------------------------------------------------------------------- CLI


def _write(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj))
    return path


def test_main_no_drift_when_current_subset_of_baseline(tmp_path):
    trivy = _write(tmp_path / "t.json", _report(_m("AVD-1", "HIGH")))
    baseline = _write(tmp_path / "b.json", {"accepted": ["AVD-1::render.yaml::HIGH"]})
    assert cspm.main(["--trivy-json", str(trivy), "--baseline", str(baseline)]) == 0


def test_main_clean_posture_passes(tmp_path):
    trivy = _write(tmp_path / "t.json", _report())  # no misconfigs
    baseline = _write(tmp_path / "b.json", {"accepted": []})
    assert cspm.main(["--trivy-json", str(trivy), "--baseline", str(baseline)]) == 0


def test_main_drift_fails(tmp_path):
    trivy = _write(tmp_path / "t.json", _report(_m("AVD-9", "HIGH")))
    baseline = _write(tmp_path / "b.json", {"accepted": []})  # empty baseline
    assert cspm.main(["--trivy-json", str(trivy), "--baseline", str(baseline)]) == 1


def test_main_parse_error_returns_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    baseline = _write(tmp_path / "b.json", {"accepted": []})
    assert cspm.main(["--trivy-json", str(bad), "--baseline", str(baseline)]) == 2


def test_main_rejects_non_trivy_report(tmp_path):
    # A silently-failed scan emitting {} / null (valid JSON, no SchemaVersion) must NOT
    # be scored as a clean posture — that would be a false negative. Exit 2 (error).
    baseline = _write(tmp_path / "b.json", {"accepted": []})
    for garbage in ("{}", "null", '{"Results": []}'):  # last one: valid-ish but no SchemaVersion
        bad = tmp_path / "g.json"
        bad.write_text(garbage)
        assert cspm.main(["--trivy-json", str(bad), "--baseline", str(baseline)]) == 2, garbage


def test_severity_change_is_detected(tmp_path):
    # An accepted HIGH that later fires at CRITICAL (or any severity change) is drift:
    # the severity is part of the key, so it cannot be silently absorbed.
    baseline = _write(tmp_path / "b.json", {"accepted": ["AVD-X::render.yaml::HIGH"]})
    escalated = _write(tmp_path / "t.json", _report(_m("AVD-X", "CRITICAL")))
    assert cspm.main(["--trivy-json", str(escalated), "--baseline", str(baseline)]) == 1


def test_main_update_rebaselines(tmp_path):
    trivy = _write(tmp_path / "t.json", _report(_m("AVD-7", "CRITICAL")))
    baseline = tmp_path / "b.json"
    baseline.write_text(json.dumps({"accepted": []}))
    # --update accepts the current findings; a subsequent gate run is then clean.
    assert (
        cspm.main(["--trivy-json", str(trivy), "--baseline", str(baseline), "--update"])
        == 0
    )
    assert json.loads(baseline.read_text())["accepted"] == ["AVD-7::render.yaml::CRITICAL"]
    assert cspm.main(["--trivy-json", str(trivy), "--baseline", str(baseline)]) == 0


def test_committed_baseline_is_valid_and_clean():
    # The shipped baseline must be parseable and reflect the current clean posture.
    baseline = _SCRIPT.parent / "iac_posture_baseline.json"
    data = json.loads(baseline.read_text())
    assert data["accepted"] == [], "committed IaC posture baseline should be clean (empty)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
