"""Compliance control->evidence register validator (Security Prompt 22).

Asserts the SHIPPED register validates (every in-repo control's evidence path resolves
— the fail-on-drift gate: a deleted control file breaks this test) and unit-tests the
validator's problem detection.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# Repo-root infra tooling, loaded by path. tests/ -> moltrace_backend/ -> <repo root>.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "compliance" / "validate_controls.py"
_REGISTER = _REPO_ROOT / "compliance" / "controls.json"


def _load():
    spec = importlib.util.spec_from_file_location("validate_controls", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _load()


def test_files_exist():
    assert _SCRIPT.exists() and _REGISTER.exists()


def test_shipped_register_validates():
    # Fail-on-drift: every in-repo control's evidence path must resolve in the repo.
    register = json.loads(_REGISTER.read_text())
    problems = cc.validate(register, repo_root=_REPO_ROOT)
    assert problems == [], problems


def test_shipped_register_does_not_claim_certification():
    # Honesty guard: the register must not assert held SOC 2 / ISO certification.
    text = _REGISTER.read_text().lower()
    assert "not held" in text
    for forbidden in ("soc 2 compliant", "soc 2 certified", "iso 27001 certified", "is certified"):
        assert forbidden not in text, forbidden


def test_validator_flags_missing_evidence_path():
    register = {
        "controls": [
            {
                "id": "x",
                "control": "X",
                "summary": "s",
                "soc2_tsc": ["CC6"],
                "iso27001_annex_a": ["A.8"],
                "type": "in-repo",
                "evidence": ["does/not/exist.py"],
            }
        ]
    }
    problems = cc.validate(register, repo_root=_REPO_ROOT)
    assert any("does not resolve" in p for p in problems)


def test_validator_flags_unmapped_control():
    register = {
        "controls": [
            {
                "id": "x",
                "control": "X",
                "summary": "s",
                "soc2_tsc": [],
                "iso27001_annex_a": [],
                "type": "in-repo",
                "evidence": ["compliance/controls.json"],
            }
        ]
    }
    problems = cc.validate(register, repo_root=_REPO_ROOT)
    assert any("SOC 2" in p for p in problems)
    assert any("Annex A" in p for p in problems)


def test_validator_flags_duplicate_id_and_empty():
    assert any("no 'controls'" in p for p in cc.validate({}, repo_root=_REPO_ROOT))
    dup = {
        "controls": [
            {"id": "d", "control": "A", "summary": "s", "soc2_tsc": ["CC6"],
             "iso27001_annex_a": ["A.8"], "type": "in-repo", "evidence": ["compliance/controls.json"]},
            {"id": "d", "control": "B", "summary": "s", "soc2_tsc": ["CC6"],
             "iso27001_annex_a": ["A.8"], "type": "in-repo", "evidence": ["compliance/controls.json"]},
        ]
    }
    assert any("duplicate id" in p for p in cc.validate(dup, repo_root=_REPO_ROOT))


def test_validator_rejects_absolute_and_directory_evidence():
    register = {
        "controls": [
            {"id": "abs", "control": "A", "summary": "s", "soc2_tsc": ["CC6"],
             "iso27001_annex_a": ["A.8"], "type": "in-repo", "evidence": ["/etc/hosts"]},
            {"id": "dir", "control": "D", "summary": "s", "soc2_tsc": ["CC6"],
             "iso27001_annex_a": ["A.8"], "type": "in-repo", "evidence": ["compliance"]},
        ]
    }
    problems = cc.validate(register, repo_root=_REPO_ROOT)
    assert any("invalid evidence path" in p for p in problems)  # absolute path rejected
    assert any("does not resolve to a file" in p for p in problems)  # a directory is not evidence


def test_validator_handles_non_dict_control():
    problems = cc.validate({"controls": ["oops"]}, repo_root=_REPO_ROOT)
    assert any("not an object" in p for p in problems)


def test_validator_checks_inherited_entries():
    register = {
        "controls": [],
        "inherited_or_operational": [{"control": "physical", "type": "inherited"}],  # missing 'via'
    }
    problems = cc.validate(register, repo_root=_REPO_ROOT)
    assert any("missing 'via'" in p for p in problems)
