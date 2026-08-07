"""Shift-prediction provenance and coverage invariants (B0).

Why this file exists
--------------------
Production shift prediction silently degraded to a 16-molecule seed knowledge
base: ``MOLTRACE_HOSE_KB`` is unset, so ``_fallback_kb()`` returns
``build_seed_knowledge_base()``, and every atom without a HOSE match falls to a
bare element-level prior (¹³C σ = 35 ppm — roughly fifteen times DP4's own ¹³C
error scale of 2.306 ppm).

Nothing was hidden: each fallback appends a per-atom warning string. But no
caller *aggregated* those warnings, so the degradation was invisible in every
consumer — including ``verification.scorer``, which derives each test's
significance from the prediction uncertainty and therefore quietly discounted
its own ¹³C evidence to ~16 % of design weight.

So these tests encode two things:

1. **Provenance invariants** — every predicted shift must say where it came
   from, and every prediction must report its aggregate coverage. These are
   permanent.
2. **A measured baseline** — today's coverage on a fixed panel of drug-like
   molecules. This is *not* an assertion that the current numbers are good;
   they are bad. It is a guard so the degradation cannot get worse silently,
   and — via the strict-xfail target below — so that fixing it is impossible to
   do *quietly*.

Re-baselining
-------------
``test_target_median_13c_sigma_below_dp4_scale`` is ``xfail(strict=True)``. The
moment a real NMRShiftDB2 knowledge base is wired up it will XPASS, which
**fails the suite** and forces whoever landed it to update the baselines here in
the same change. That is the "re-baseline visibly" rule expressed as a test
rather than as a docstring nobody reads.
"""

from __future__ import annotations

import math
import statistics

import pytest

from moltrace.spectroscopy.predict.nmrnet_wrapper import predict_shifts

# DP4's published ¹³C error-model scale (Smith & Goodman 2010) — the width of
# the distribution that *consumes* these predictions. A prediction whose own
# uncertainty exceeds this is not usable evidence for candidate ranking.
DP4_SIGMA_13C_PPM = 2.306

# A fixed panel of drug-like molecules. Deliberately small, deliberately not
# solvents: the seed knowledge base covers common solvents and simple functional
# groups, so a solvent panel would flatter the coverage number.
DRUG_PANEL: dict[str, str] = {
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "atorvastatin_fragment": (
        "CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1"
        "CC[C@@H](O)C[C@@H](O)CC(=O)O"
    ),
}


@pytest.fixture(scope="module")
def panel_predictions():
    """Predict once per molecule; every test below reads these."""

    return {name: predict_shifts(smi) for name, smi in DRUG_PANEL.items()}


# --------------------------------------------------------------------------- #
# Provenance invariants — permanent
# --------------------------------------------------------------------------- #
def test_every_atom_shift_names_its_source(panel_predictions):
    """No predicted shift may be anonymous about where its value came from.

    A consumer weighting evidence needs to distinguish a model prediction from a
    knowledge-base lookup from a bare element average. Parsing warning strings is
    not an interface.
    """

    valid = {"nmrnet", "hose", "element_prior"}
    for name, pred in panel_predictions.items():
        assert pred.shifts, f"{name}: no shifts predicted at all"
        for s in pred.shifts:
            assert s.source in valid, (
                f"{name}: atom {s.atom_index} {s.nucleus} has source {s.source!r}, "
                f"expected one of {sorted(valid)}"
            )


def test_prediction_reports_aggregate_coverage(panel_predictions):
    """The aggregate must be computed by the producer, not by each caller.

    This is the specific gap that let a 35 ppm median σ reach production: the
    per-atom warnings existed, but nothing summed them.
    """

    for name, pred in panel_predictions.items():
        frac = pred.prior_fallback_fraction
        assert 0.0 <= frac <= 1.0, f"{name}: prior_fallback_fraction out of range: {frac}"

        counted = sum(1 for s in pred.shifts if s.source == "element_prior")
        assert frac == pytest.approx(counted / len(pred.shifts)), (
            f"{name}: prior_fallback_fraction disagrees with the per-atom sources"
        )


def test_prediction_reports_knowledge_base_provenance(panel_predictions):
    """A number is not reproducible unless you can say which table produced it."""

    for name, pred in panel_predictions.items():
        assert pred.kb_source in {"seed", "nmrshiftdb2", "none"}, (
            f"{name}: unexpected kb_source {pred.kb_source!r}"
        )
        if pred.method == "hose_fallback":
            assert pred.kb_source != "none", f"{name}: fallback used but no KB named"
            assert pred.kb_records > 0, f"{name}: KB named but reports 0 records"


def test_median_uncertainty_is_reported_per_nucleus(panel_predictions):
    """Callers gate on σ, so σ must be summarised at the prediction level."""

    for name, pred in panel_predictions.items():
        summary = pred.median_uncertainty_ppm
        for nucleus in ("1H", "13C"):
            if any(s.nucleus == nucleus for s in pred.shifts):
                assert nucleus in summary, f"{name}: no median σ reported for {nucleus}"
                assert math.isfinite(summary[nucleus]), (
                    f"{name}: median σ for {nucleus} is not finite"
                )


def test_fallback_method_is_recorded_never_silent(panel_predictions):
    """Degrading to the fallback is allowed. Degrading *silently* is not."""

    for name, pred in panel_predictions.items():
        assert pred.method in {"nmrnet", "hose_fallback"}
        if pred.method == "hose_fallback":
            assert any("fallback" in w.lower() or "prior" in w.lower() for w in pred.warnings), (
                f"{name}: fell back to HOSE but no warning explains why"
            )


def test_identical_input_and_seed_gives_identical_shifts():
    """GxP reproducibility: conformer embedding is stochastic, so pin the seed.

    The same input must give a byte-identical number on a re-run, or the same
    dossier re-opened tomorrow disagrees with itself.
    """

    a = predict_shifts("CC(=O)Nc1ccc(O)cc1")
    b = predict_shifts("CC(=O)Nc1ccc(O)cc1")

    assert [(s.atom_index, s.nucleus) for s in a.shifts] == [
        (s.atom_index, s.nucleus) for s in b.shifts
    ]
    for x, y in zip(a.shifts, b.shifts, strict=True):
        assert x.predicted_ppm == y.predicted_ppm, (
            f"atom {x.atom_index} {x.nucleus} drifted between identical runs: "
            f"{x.predicted_ppm} != {y.predicted_ppm}"
        )
        assert x.source == y.source


# --------------------------------------------------------------------------- #
# Measured baselines, re-measured 2026-08-07 after the knowledge base landed
# --------------------------------------------------------------------------- #
# Behaviour depends on which table is configured, so the thresholds do too. The
# earlier strict-xfail target XPASSed the moment a real KB was built, failed the
# suite, and forced this re-measurement — which is what it was for.
#
#                             seed (16 mol / 146 refs)   nmrshiftdb2 (49 618 mol / 495 215 refs)
#   prior-fallback share           22.6 - 44.4 %                    0.0 %
#   pooled median 13C sigma           35.00 ppm                    1.88 ppm
#   pooled median  1H sigma            0.52 ppm                    0.26 ppm
#
# Build the full table with:
#   python scripts/build_hose_kb.py <nmrshiftdb2.nmredata.sd> -o <path>
#   export MOLTRACE_HOSE_KB=<path>
SEED_MAX_PRIOR_FRACTION = 0.50  # seed path: observed 0.226-0.444
FULL_MAX_PRIOR_FRACTION = 0.05  # nmrshiftdb2 path: observed 0.000 on all four


def _kb_source(panel_predictions) -> str:
    sources = {p.kb_source for p in panel_predictions.values()}
    assert len(sources) == 1, f"panel mixed knowledge bases: {sources}"
    return sources.pop()


def test_prior_fallback_does_not_degrade(panel_predictions):
    """Coverage must not regress below the measurement for whichever table is in use.

    Two baselines rather than one, because a single threshold would either be
    vacuous on the full table or unmeetable on the seed. If this fails *low* —
    coverage improved materially — re-measure the constants in the same change
    that improved them and record it in the changelog.
    """

    source = _kb_source(panel_predictions)
    limit = FULL_MAX_PRIOR_FRACTION if source == "nmrshiftdb2" else SEED_MAX_PRIOR_FRACTION

    for name, pred in panel_predictions.items():
        assert pred.prior_fallback_fraction <= limit, (
            f"{name}: {pred.prior_fallback_fraction:.1%} of atoms fell to the element "
            f"prior against a {limit:.0%} ceiling for the '{source}' knowledge base "
            f"({pred.kb_records} reference atoms). Coverage regressed."
        )


def test_median_13c_sigma_below_dp4_scale(panel_predictions):
    """The prediction must be sharper than the error model that consumes it.

    Was a strict-xfail while only the 16-molecule seed table existed (median ¹³C σ
    of 35 ppm, ~15× DP4's scale, which discounted the verifier's ¹³C evidence to
    ~16 % of design weight). With a real knowledge base configured this is a live
    requirement: a prediction wider than DP4's own error distribution cannot
    discriminate between candidates, so DP4 over it is arithmetic without
    evidence.

    Skipped — not silently passed — when no real table is configured, so the gap
    stays visible on a bare checkout instead of looking like a success.
    """

    source = _kb_source(panel_predictions)
    if source != "nmrshiftdb2":
        pytest.skip(
            f"no NMRShiftDB2 knowledge base configured (using '{source}'). "
            "Build one with scripts/build_hose_kb.py and set MOLTRACE_HOSE_KB; "
            "until then the median 13C sigma is the ~35 ppm element prior."
        )

    medians = [
        pred.median_uncertainty_ppm["13C"]
        for pred in panel_predictions.values()
        if "13C" in pred.median_uncertainty_ppm
    ]
    assert medians, "panel produced no 13C predictions at all"
    observed = statistics.median(medians)
    assert observed < DP4_SIGMA_13C_PPM, (
        f"median 13C prediction uncertainty is {observed:.2f} ppm, at or above DP4's "
        f"{DP4_SIGMA_13C_PPM} ppm error scale — the prediction cannot discriminate "
        f"candidates the ranking is asked to separate"
    )
