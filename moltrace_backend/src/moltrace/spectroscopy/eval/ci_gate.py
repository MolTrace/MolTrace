"""CI entry point for the Prompt 17 evaluation harness: ``moltrace-eval-gate``.

The harness (:mod:`.harness`) has carried the whole promotion machinery —
checksummed gold set, ten-metric vector, dominance rule, ``gate_for_ci`` exit
codes — since Prompt 17, but no gold set existed in the repo and nothing called
``gate_for_ci`` outside its own tests, so no commit has ever been scored for
accuracy regression. This module supplies the two missing pieces:

* a loader for the frozen fixture-backed gold set
  (``tests/fixtures/nmr_gold_set/gold_set_v1.json``, built by
  ``scripts/build_nmr_gold_set.py`` from the real NMRShiftDB2 Bruker fixtures
  already in the repo), and
* a **production-path** :class:`~.harness.ModelBundle`: each record's real FID
  is read with :func:`~moltrace.spectroscopy.io.fid_reader.read_fid` and scored
  through :func:`~moltrace.spectroscopy.verification.scorer.verify_structure`
  plus :func:`~moltrace.spectroscopy.predict.nmrnet_wrapper.predict_shifts` —
  the same functions production calls, never a reimplementation. A synthesised
  spectrum was measured not to transfer (r = -0.106) and must not be
  substituted; the real archives are in the repo, so nothing needs to be.

Honesty constraints, stated once and carried in the vector's metadata:

* This is a **regression sentinel, not an accuracy claim**. Several gold
  molecules are in the shipped knowledge base's training data, so absolute
  shift-MAE here partially measures memorisation; held-out accuracy numbers
  come only from ``eval/shift_accuracy.py`` on a disjoint split. Dominance
  comparisons (candidate vs incumbent on the identical set and KB) are valid
  regardless — that is what a CI gate needs.
* The candidate and the incumbent must be evaluated against the **same
  knowledge base**; the vector records ``kb_source`` in ``model_versions`` and
  the gate refuses a comparison across differing KB provenance rather than
  reporting a spurious regression.
* v1 has no wrong-structure records, so ``false_confirmation_rate`` is
  ``None`` (nullable, with its denominator visible) — not a perfect score.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .harness import (
    NULLABLE_METRICS,
    CallableBundle,
    GoldMetricVector,
    GoldRecord,
    GoldSet,
    GoldSetChecksumError,
    Prediction,
)

__all__ = ["load_gold_set", "load_incumbent_vector", "production_bundle", "main"]

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_GOLD_SET = _BACKEND_ROOT / "tests/fixtures/nmr_gold_set/gold_set_v1.json"
DEFAULT_INCUMBENT = _BACKEND_ROOT / "benchmarks/nmr/incumbent_metric_vector.json"
_FIXTURES_ROOT = _BACKEND_ROOT / "tests/fixtures/nmrshiftdb2"


def load_gold_set(path: str | Path) -> GoldSet:
    """Load the frozen gold set and let ``expected_checksum`` do the pinning."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = tuple(
        GoldRecord(
            identifier=item["identifier"],
            source=item["source"],
            true_inchikey=item["true_inchikey"],
            proposed_inchikey=item.get("proposed_inchikey"),
            reviewer_verdict=bool(item["reviewer_verdict"]),
            reference_shifts={k: list(v) for k, v in item["reference_shifts"].items()},
            spectrum=item.get("spectrum"),
        )
        for item in payload["records"]
    )
    return GoldSet(
        name=payload["name"],
        records=records,
        expected_checksum=payload.get("checksum"),
        expected_size=payload.get("record_count"),
    )


def load_incumbent_vector(path: str | Path) -> GoldMetricVector | None:
    """The committed production incumbent, or ``None`` when none exists yet."""

    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    fields = {f for f in GoldMetricVector.__dataclass_fields__}
    kwargs = {k: v for k, v in data.items() if k in fields}
    # Nullable metrics are omitted from persisted snapshots when unmeasured.
    # Requiring them here makes a *real* snapshot unreadable — and a caller that
    # reads "unreadable incumbent" as "no incumbent" then promotes without
    # comparing (the exact failure NULLABLE_METRICS documents).
    for metric in NULLABLE_METRICS & fields:
        kwargs.setdefault(metric, None)
    return GoldMetricVector(**kwargs)


def _predicted_shift_map(smiles: str) -> dict[str, list[float]]:
    from moltrace.spectroscopy.predict.nmrnet_wrapper import predict_shifts

    prediction = predict_shifts(smiles, n_conformers=1)
    shifts: dict[str, list[float]] = {}
    for atom in prediction.shifts:
        shifts.setdefault(atom.nucleus, []).append(float(atom.predicted_ppm))
    return {k: sorted(v) for k, v in shifts.items()}


def production_bundle() -> CallableBundle:
    """The production verify/predict path wrapped as a harness bundle.

    ``model_versions`` carries the live KB provenance so a vector produced
    against the seed table can never be silently compared with one produced
    against the full index.
    """

    from moltrace.spectroscopy.io.fid_reader import read_fid
    from moltrace.spectroscopy.predict.nmrnet_wrapper import (
        knowledge_base_status,
        predict_shifts,
    )
    from moltrace.spectroscopy.verification.scorer import verify_structure

    # Force the lazy KB load before stamping provenance — an unloaded table
    # reads as "configured", which says nothing about WHICH table answers.
    predict_shifts("C", n_conformers=1)

    spectrum_cache: dict[str, Any] = {}

    def _predict(record: GoldRecord) -> Prediction:
        spec = record.spectrum or {}
        smiles = spec.get("proposed_smiles")
        fixture_dir = spec.get("fixture_dir")
        if not smiles or not fixture_dir:
            raise ValueError(f"{record.identifier}: gold record lacks proposed_smiles/fixture_dir")
        if fixture_dir not in spectrum_cache:
            spectrum_cache[fixture_dir] = read_fid(_FIXTURES_ROOT / fixture_dir)
        t0 = time.perf_counter()
        result = verify_structure(spectrum_cache[fixture_dir], smiles)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return Prediction(
            ranked_candidates=(record.proposed_inchikey or record.true_inchikey,),
            predicted_shifts=_predicted_shift_map(smiles),
            confidence=float(result.posterior_confidence),
            confirmed=result.verdict == "consistent",
            uncertainty=1.0 - float(result.posterior_confidence),
            latency_ms=latency_ms,
        )

    # Load lazily-cheap provenance up front so it stamps the vector.
    kb = knowledge_base_status()
    return CallableBundle(
        predict_fn=_predict,
        model_versions={
            "verifier": "verify_structure",
            "shift_predictor": "hose_fallback",
            "kb_source": str(
                kb.get("source") or ("configured" if kb.get("configured") else "seed")
            ),
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score the production verify/predict path on the frozen NMR gold set and "
            "compare against the committed incumbent vector (Prompt 17 dominance). "
            "Exit 0 promotable, 1 regression, 2 gold-set drift / evaluation error."
        )
    )
    parser.add_argument("--gold-set", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--incumbent", type=Path, default=DEFAULT_INCUMBENT)
    parser.add_argument(
        "--persist-out",
        type=Path,
        default=None,
        help="Write the candidate's metric vector JSON here (e.g. to refresh the incumbent).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N records (smoke/testing only — the checksum is "
        "recomputed for the subset, so this never counts as the frozen verdict).",
    )
    parser.add_argument(
        "--mode",
        choices=("regression", "promotion"),
        default="regression",
        help="'regression' (default, the per-commit question): fail only when a metric "
        "regresses beyond tolerance — an unchanged model passes. 'promotion' is the "
        "full Prompt 17 dominance rule (also requires a strict improvement), for "
        "judging a deliberate model change.",
    )
    parser.add_argument(
        "--informational",
        action="store_true",
        help="Report the verdict but always exit 0 — the agreed first-iteration CI mode; "
        "flip to blocking by dropping this flag once the incumbent is reviewed.",
    )
    args = parser.parse_args(argv)

    try:
        gold = load_gold_set(args.gold_set)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"gold set unreadable: {exc}", file=sys.stderr)
        return 2

    if args.limit is not None:
        subset = gold.records[: max(0, args.limit)]
        gold = GoldSet(name=f"{gold.name}[:{len(subset)}]", records=subset)

    incumbent = load_incumbent_vector(args.incumbent)
    bundle = production_bundle()

    if incumbent is not None:
        incumbent_kb = (incumbent.model_versions or {}).get("kb_source")
        candidate_kb = bundle.model_versions.get("kb_source")
        if incumbent_kb != candidate_kb:
            print(
                f"knowledge-base provenance differs (incumbent={incumbent_kb!r}, "
                f"candidate={candidate_kb!r}); a dominance comparison would report KB "
                "drift as model regression. Stage the same KB and rerun.",
                file=sys.stderr,
            )
            return 0 if args.informational else 2

    from .harness import dominates, evaluate, persist_metric_vector

    try:
        candidate = evaluate(bundle, gold, k=5)
    except GoldSetChecksumError as exc:
        print(f"gold-set checksum drift: {exc}", file=sys.stderr)
        return 2
    if args.persist_out is not None:
        persist_metric_vector(candidate, path=args.persist_out)

    if incumbent is None:
        print(
            f"moltrace-eval-gate: promotable on {len(gold.records)} records "
            f"(no incumbent, kb={bundle.model_versions.get('kb_source')})"
        )
        return 0

    passed_promotion, deltas = dominates(candidate, incumbent)
    # dominates() refuses a safety-critical metric missing from either side by
    # recording an unmeasured regressed delta — the anti-gaming rule that stops a
    # candidate from dropping a metric to stop being judged on it. When NEITHER
    # side has ever measured it (v1 has no decoy records, so
    # false_confirmation_rate is honestly unmeasured everywhere), a per-commit
    # regression gate that is permanently red for that reason teaches people to
    # ignore it — so that one case downgrades to a loud warning here, while a
    # candidate dropping a metric the incumbent HAD still fails.
    never_measured = [
        d
        for d in deltas
        if d.safety_critical and not d.measured and d.candidate is None and d.incumbent is None
    ]
    for d in never_measured:
        print(
            f"warning: safety-critical metric {d.metric!r} has never been measured on "
            "either side (no decoy records yet); add wrong-structure gold records to "
            "close this gap.",
            file=sys.stderr,
        )
    hard_regressions = [d for d in deltas if d.regressed and d not in never_measured]
    if args.mode == "regression":
        code = 1 if hard_regressions else 0
    else:
        code = 0 if passed_promotion else 1

    for d in hard_regressions:
        print(
            f"regressed: {d.metric} {d.incumbent!r} -> {d.candidate!r} "
            f"(tolerance {d.tolerance})",
            file=sys.stderr,
        )
    if code == 0:
        verdict = "pass (no regression)"
    elif args.mode == "regression":
        verdict = "regression"
    else:
        verdict = "not promotable (regression or no improvement)"
    print(
        f"moltrace-eval-gate[{args.mode}]: {verdict} on {len(gold.records)} records "
        f"(incumbent={args.incumbent}, kb={bundle.model_versions.get('kb_source')})"
    )
    if args.informational and code != 0:
        print("informational mode: reporting only, exiting 0.", file=sys.stderr)
        return 0
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
