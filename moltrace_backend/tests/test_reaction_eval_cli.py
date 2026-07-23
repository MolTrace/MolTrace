"""R11 CI entrypoint tests — the promotion gate's process-exit contract (fail-closed)."""

from __future__ import annotations

import json
from pathlib import Path

from nmrcheck.reaction_eval import EXIT_BLOCKED, EXIT_DRIFT, EXIT_OK
from nmrcheck.reaction_eval_cli import main

_GOLD = Path(__file__).parent / "fixtures" / "reaction_eval" / "gold_set_v1.json"


def _checksum() -> str:
    return json.loads(_GOLD.read_text())["checksum"]


def _write(tmp_path: Path, name: str, payload: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _results(version: str, *, to_target: float, recall: float, regret: float, stamped=True) -> dict:
    return {
        "model_version": version,
        "metrics": {
            "experiments_to_target_median": to_target,
            "best_objective": 91.0,
            "cumulative_regret": regret,
            "reproduction_accuracy": 1.0,
        },
        "safety_flag_recall": recall,
        "gold_checksum": _checksum() if stamped else "sha256:not-this-gold-set",
    }


def _run(tmp_path, candidate: dict, incumbent: dict, gold: str | None = None) -> int:
    return main(
        [
            "--gold", gold or str(_GOLD),
            "--candidate", _write(tmp_path, "candidate.json", candidate),
            "--incumbent", _write(tmp_path, "incumbent.json", incumbent),
        ]
    )


def test_exit_ok_when_candidate_dominates_without_safety_regression(tmp_path, capsys):
    code = _run(
        tmp_path,
        _results("candidate.v2", to_target=4.0, recall=0.97, regret=85.0),
        _results("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "PROMOTABLE" in out
    assert "human sign-off" in out  # never presented as auto-deploy


def test_exit_blocked_on_safety_recall_regression(tmp_path):
    code = _run(
        tmp_path,
        _results("candidate.v2", to_target=3.0, recall=0.90, regret=60.0),  # better, less safe
        _results("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert code == EXIT_BLOCKED


def test_exit_blocked_when_not_dominant(tmp_path):
    code = _run(
        tmp_path,
        _results("candidate.v2", to_target=7.0, recall=0.95, regret=130.0),
        _results("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert code == EXIT_BLOCKED


def test_exit_drift_on_tampered_gold_set(tmp_path):
    payload = json.loads(_GOLD.read_text())
    payload["tasks"][0]["objective_target"] = 1.0  # checksum not re-frozen
    gold = _write(tmp_path, "gold.json", payload)
    code = _run(
        tmp_path,
        _results("candidate.v2", to_target=4.0, recall=0.97, regret=85.0),
        _results("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
        gold=gold,
    )
    assert code == EXIT_DRIFT


def test_exit_drift_when_results_not_bound_to_this_gold_set(tmp_path):
    code = _run(
        tmp_path,
        _results("candidate.v2", to_target=4.0, recall=0.97, regret=85.0, stamped=False),
        _results("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert code == EXIT_DRIFT


def test_exit_drift_on_missing_file(tmp_path):
    code = main(
        [
            "--gold", str(_GOLD),
            "--candidate", str(tmp_path / "nope.json"),
            "--incumbent", str(tmp_path / "also-nope.json"),
        ]
    )
    assert code == EXIT_DRIFT


def test_exit_drift_on_malformed_results(tmp_path):
    # Missing safety_flag_recall — the blocking dimension — must be drift, never a pass.
    bad = {"model_version": "x", "metrics": {"best_objective": 91.0}}
    code = _run(tmp_path, bad, _results("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0))
    assert code == EXIT_DRIFT
