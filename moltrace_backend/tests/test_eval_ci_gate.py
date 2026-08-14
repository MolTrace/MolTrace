"""moltrace-eval-gate: the first caller gate_for_ci's machinery has ever had.

Pins the pieces that make the CI accuracy gate trustworthy: the committed gold
set loads and its checksum binds content; a tampered set is refused; a persisted
incumbent with honestly-unmeasured nullable metrics is readable (the exact
reconstruction trap NULLABLE_METRICS documents); and the regression-mode
semantics — never-measured-anywhere safety metrics warn instead of permanently
failing, while a candidate that *drops* a measured safety metric still fails.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from moltrace.spectroscopy.eval.ci_gate import (
    DEFAULT_GOLD_SET,
    DEFAULT_INCUMBENT,
    load_gold_set,
    load_incumbent_vector,
)
from moltrace.spectroscopy.eval.harness import GoldSet, dominates


def test_committed_gold_set_loads_and_checksum_binds() -> None:
    gold = load_gold_set(DEFAULT_GOLD_SET)
    assert len(gold.records) >= 20
    assert gold.expected_checksum == gold.checksum()
    nuclei = {n for r in gold.records for n in r.reference_shifts}
    assert {"1H", "13C"} <= nuclei
    for record in gold.records:
        assert record.spectrum is not None
        assert record.spectrum.get("proposed_smiles")
        assert record.spectrum.get("fixture_dir")


def test_tampered_gold_set_is_refused(tmp_path) -> None:
    payload = json.loads(DEFAULT_GOLD_SET.read_text(encoding="utf-8"))
    payload["records"][0]["reference_shifts"]["13C" if "13C" in payload["records"][0]["reference_shifts"] else "1H"][0] += 0.5
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    gold = load_gold_set(tampered)
    assert gold.expected_checksum != gold.checksum()


def test_incumbent_with_unmeasured_nullable_metrics_is_readable() -> None:
    # The persisted snapshot omits nullable metrics that were never measured;
    # requiring them made a real snapshot unreadable, and "unreadable incumbent"
    # reads as "no incumbent" — which silently promotes without comparing.
    vector = load_incumbent_vector(DEFAULT_INCUMBENT)
    assert vector is not None
    assert vector.false_confirmation_rate is None
    assert vector.gold_checksum == load_gold_set(DEFAULT_GOLD_SET).checksum()


def test_never_measured_safety_metric_warns_but_dropping_one_fails() -> None:
    incumbent = load_incumbent_vector(DEFAULT_INCUMBENT)
    assert incumbent is not None

    # Identical vectors: the only regressed deltas are the never-measured-anywhere
    # safety refusals (false_confirmation_rate has no decoy records yet) — the
    # case the CLI downgrades to a warning so the per-commit gate is not
    # permanently red.
    _passed, deltas = dominates(incumbent, incumbent)
    never_measured = [
        d
        for d in deltas
        if d.safety_critical and not d.measured and d.candidate is None and d.incumbent is None
    ]
    hard = [d for d in deltas if d.regressed and d not in never_measured]
    assert not hard
    assert {d.metric for d in never_measured} == {"false_confirmation_rate"}

    # A candidate that DROPS a measured safety metric must still hard-fail —
    # otherwise deleting a metric is a way to stop being judged on it.
    dropped = replace(incumbent, ece=None)
    _passed, deltas = dominates(dropped, incumbent)
    still_hard = [
        d
        for d in deltas
        if d.regressed
        and not (d.safety_critical and not d.measured and d.candidate is None and d.incumbent is None)
    ]
    assert any(d.metric == "ece" for d in still_hard)


def test_gold_set_subset_never_masquerades_as_frozen() -> None:
    gold = load_gold_set(DEFAULT_GOLD_SET)
    subset = GoldSet(name=f"{gold.name}[:2]", records=gold.records[:2])
    # A subset has no expected checksum, so nothing can mistake it for the
    # frozen verdict set.
    assert subset.expected_checksum is None


@pytest.mark.slow
def test_cli_end_to_end_single_record() -> None:
    from moltrace.spectroscopy.eval.ci_gate import main

    # One real fixture through read_fid + verify_structure + predict_shifts.
    # No incumbent supplied (a subset must never be compared to the frozen
    # incumbent), so the verdict is "promotable" and the exit code 0.
    assert main(["--limit", "1", "--incumbent", "/nonexistent/incumbent.json"]) == 0
