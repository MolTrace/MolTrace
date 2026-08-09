"""How far the *arbiter* separates a right structure from a wrong one (B5.2, second layer).

:mod:`~moltrace.spectroscopy.eval.false_confirmation` measures one evidence layer — a
shift list, through DP4 — and says so in its own docstring. It deliberately does **not**
measure :func:`~moltrace.spectroscopy.verification.verify_structure`, which is the thing
that actually decides. That leaves the load-bearing question open: the published
false-confirmation rate describes a component, and the component is not the arbiter.

This closes it. Same decoys, same held-out split, same bucket discipline — but every
candidate is scored by the multi-test verifier, on a spectrum, exactly as a user's
proposal is scored.

Why a margin and not just a rate
--------------------------------
A rate answers "did the wrong one win?". It cannot answer "by how much?", and the second
question is the one that decides whether the verifier can be used as a *reward oracle*
for post-training. An oracle that ranks correctly but by a vanishing margin gives an
optimiser almost nothing to climb; an oracle that ties gives it exactly nothing and lets
the policy drift across the tie set at zero cost. So this reports the whole distribution,
and it reports ties as their own outcome rather than folding them into either side.

The margin is in **log-odds, not posterior confidence**
------------------------------------------------------
Measured on one thioester pair, the posterior-confidence margin is 0.435 at prior 0.2,
0.353 at 0.5 and 0.149 at 0.8 — the *same* evidence, three different numbers. The
log-odds margin is 1.906755 at all three, because the shared prior logit cancels in the
difference. A posterior-confidence margin is therefore not comparable across runs that
used different priors, and publishing one invites exactly that mistake.

Three reasons a margin is zero, and they are not the same finding
----------------------------------------------------------------
Aggregating them together is how a broken input reads as a scientific result:

``no_evidence``
    No test was applicable, or the spectrum yielded nothing to match. Measured: a
    peak-free ¹H spectrum gives aspirin, its regioisomer *and* ethanol the identical
    posterior — a perfect tie that says nothing about the structures. Note
    ``PredictionBoundsTest`` does **not** abstain on empty units (it scores -1), so
    "a test was applicable" is not sufficient to prove evidence existed.
``prediction_identical``
    The predictor returned a bit-identical shift multiset for both candidates, so the
    verifier was never given anything to separate. This is a *predictor coverage*
    finding, not a verifier finding, and it is dominated by :class:`KnowledgeBase`
    back-off: ``lookup`` walks sphere 6→1 to the first bucket holding
    ``_MIN_KB_MATCHES`` references, so codes that genuinely diverge at sphere 3 collapse
    to one shallow bucket whenever the table is thin. It is a property of the table in
    use, which is why every report records ``kb_source`` and ``kb_reference_count``.
``scored``
    Both candidates got distinct predictions and the verifier still tied or preferred
    one. The only bucket a margin distribution means anything over.

A tie is never credited to the truth
------------------------------------
``false_confirmation.py`` compares DP4 posteriors with ``>``, so an exact 0.5/0.5 tie
falls through to ``truth_wins``. On identical shift lists DP4 returns exactly 0.5/0.5,
so that is not a rare edge — it is precisely the population this module exists to look
at, scored in the flattering direction. Here ``truth_wins``, ``decoy_wins`` and
``exact_ties`` are three separate counters and the rate is reported over all three.

The spectrum is a **required caller input**, not something this module builds. A
synthesised one — real shift positions, synthetic lineshape — was measured against the
real Bruker fixtures and does not transfer (*r* = -0.106, 35 % of pairs ranked in the
opposite direction). :func:`simulate_spectrum` is kept only to reproduce that refutation.

Deterministic given its inputs: decoys are generated at fixed positions and the split is
content-hashed; nothing here samples.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from rdkit import Chem

from moltrace.spectroscopy.eval.decoys import generate_decoys
from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    ShiftPrediction,
    molecule_from_record,
    predict_shifts,
)
from moltrace.spectroscopy.verification.scorer import (
    VerificationOptions,
    VerificationResult,
    verify_structure,
)

__all__ = [
    "MarginOutcome",
    "PairMargin",
    "VerifierMarginReport",
    "measure_verifier_margin",
    "simulate_spectrum",
]

_MIN_OBSERVED_SHIFTS = 4
"""Below this there is too little experimental evidence for a margin to mean anything."""

_LOGIT_CLIP = 1.0e-12
"""Keeps a saturated posterior (exactly 0 or 1) from producing an infinite logit."""

# Spectrum-synthesis constants. Real peak *positions*, synthetic lineshape — see
# simulate_spectrum for why that trade is acceptable for 13C and weaker for 1H.
_SPECTRUM_POINTS = 16384
_WINDOWS_PPM: dict[str, tuple[float, float]] = {"13C": (-10.0, 230.0), "1H": (-1.0, 13.0)}
_LINEWIDTH_PPM: dict[str, float] = {"13C": 0.05, "1H": 0.006}
_NOISE_SNR = 250.0


class MarginOutcome:
    """Which bucket a truth/decoy pair landed in. Buckets sum to ``pairs_generated``."""

    SCORED = "scored"
    NO_EVIDENCE = "no_evidence"
    PREDICTION_IDENTICAL = "prediction_identical"
    REJECTED_ON_FORMULA = "rejected_on_formula"
    UNSCORABLE = "unscorable"


@dataclass(frozen=True)
class PairMargin:
    """One truth-vs-decoy comparison, with enough detail to re-derive the verdict."""

    truth_smiles: str
    decoy_smiles: str
    decoy_kind: str
    outcome: str
    truth_posterior: float | None = None
    decoy_posterior: float | None = None
    log_odds_margin: float | None = None
    truth_verdict: str | None = None
    decoy_verdict: str | None = None
    n_applicable_truth: int = 0

    @property
    def decoy_won(self) -> bool:
        return self.log_odds_margin is not None and self.log_odds_margin < 0.0

    @property
    def tied(self) -> bool:
        return self.log_odds_margin is not None and self.log_odds_margin == 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "truth_smiles": self.truth_smiles,
            "decoy_smiles": self.decoy_smiles,
            "decoy_kind": self.decoy_kind,
            "outcome": self.outcome,
            "truth_posterior": self.truth_posterior,
            "decoy_posterior": self.decoy_posterior,
            "log_odds_margin": self.log_odds_margin,
            "truth_verdict": self.truth_verdict,
            "decoy_verdict": self.decoy_verdict,
            "n_applicable_truth": self.n_applicable_truth,
        }


@dataclass(frozen=True)
class VerifierMarginReport:
    """The margin distribution, its denominators, and the table that produced it."""

    nucleus: str
    molecules_examined: int
    pairs_generated: int
    pairs_scored: int
    truth_wins: int
    decoy_wins: int
    exact_ties: int
    no_evidence: int
    prediction_identical: int
    rejected_on_formula: int
    unscorable: int
    kb_source: str
    kb_reference_count: int
    both_consistent: int = 0
    """Scored pairs where the verifier called the truth *and* the decoy 'consistent'."""
    margins: list[float] = field(default_factory=list)
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)
    pairs: list[PairMargin] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def false_confirmation_rate(self) -> float | None:
        """Share of scored pairs a wrong structure won. ``None`` if none were scored.

        A tie is not a win for either side, so it does not enter the numerator — but it
        *does* enter the denominator, because a verifier that cannot separate a pair has
        not discriminated it.
        """

        if not self.pairs_scored:
            return None
        return self.decoy_wins / self.pairs_scored

    @property
    def undiscriminated_rate(self) -> float | None:
        """Share of scored pairs the verifier failed to rank correctly (loss *or* tie).

        The quantity that bounds a reward oracle: a tie is as useless to an optimiser as
        a loss is harmful, so the two belong in one number as well as separately.
        """

        if not self.pairs_scored:
            return None
        return (self.decoy_wins + self.exact_ties) / self.pairs_scored

    def margin_quantiles(self) -> dict[str, float | None]:
        """Log-odds margin distribution over scored pairs. Empty ⇒ all ``None``."""

        if not self.margins:
            return {q: None for q in ("min", "p05", "p25", "median", "p75", "p95", "max")}
        arr = np.sort(np.asarray(self.margins, dtype=float))
        return {
            "min": float(arr[0]),
            "p05": float(np.percentile(arr, 5)),
            "p25": float(np.percentile(arr, 25)),
            "median": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)),
            "p95": float(np.percentile(arr, 95)),
            "max": float(arr[-1]),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "nucleus": self.nucleus,
            "molecules_examined": self.molecules_examined,
            "pairs_generated": self.pairs_generated,
            "pairs_scored": self.pairs_scored,
            "truth_wins": self.truth_wins,
            "decoy_wins": self.decoy_wins,
            "exact_ties": self.exact_ties,
            "no_evidence": self.no_evidence,
            "prediction_identical": self.prediction_identical,
            "rejected_on_formula": self.rejected_on_formula,
            "unscorable": self.unscorable,
            "both_consistent": self.both_consistent,
            "false_confirmation_rate": self.false_confirmation_rate,
            "undiscriminated_rate": self.undiscriminated_rate,
            "margin_quantiles": self.margin_quantiles(),
            "kb_source": self.kb_source,
            "kb_reference_count": self.kb_reference_count,
            "by_kind": {k: dict(v) for k, v in sorted(self.by_kind.items())},
            "notes": list(self.notes),
        }


def simulate_spectrum(
    shifts_ppm: Sequence[float], nucleus: str, *, seed: int = 0
) -> NMRSpectrum:
    """Build a 1-D spectrum whose peaks sit at *experimental* shifts.

    .. warning::

       **Measured invalid as a stand-in for a real spectrum.** Do not use this to produce
       a margin, a false-confirmation rate, or any bound on the verifier. It is retained
       only to reproduce the refutation below and as a fixture builder for unit tests.

       Paired against the 13 real Bruker ¹³C fixtures (same molecules, same decoys, one
       KB held fixed), margins measured here **do not transfer**: Pearson
       *r* = −0.106 over 31 pairs, 35 % of pairs ranked in the opposite direction, and a
       false-confirmation rate of 0.355 against 0.129 measured on the real spectra.

       The mechanism is the geometry, not the physics. The fixed −10..230 ppm window over
       ``_SPECTRUM_POINTS`` gives 0.0147 ppm/point, so a ``_LINEWIDTH_PPM`` line is only
       ~3.4 points wide and the trace is >99 % empty; ``gsd_peak_pick``'s dynamic-range
       estimate then tracks the noise rather than the signal and **saturates its 220-peak
       level-2 cap on 13 of 13** spectra, ~96 % of them spurious. ``_exp_units`` passes
       every one of those into the evidence set unfiltered, which turns the verifier into
       a near-universal acceptor: it calls a decoy "consistent" in 94 % of synthetic pairs
       versus 45 % of real ones. At SNR 10,000 the same construction recovers exactly the
       true peaks and the margins flip sign — so the noise floor is the proximate cause.

       The "set of singlets" premise is also false as an account of what the picker sees:
       75 % of peaks picked from the real ¹³C spectra sit at no assigned carbon, and the
       CDCl₃ 1:1:1 solvent triplet is resolved in 9 of 13 fixtures. Only the equal-heights
       sub-clause survived isolation (0.015 log-odds), and it survives vacuously — the
       saturated pick is insensitive to line height either way.

    The noise floor is not cosmetic: ``gsd_peak_pick`` computes a robust noise estimate
    and returns **no peaks at all** when it is zero, so a noiseless synthetic spectrum
    silently measures nothing. Choosing a level that avoids that *and* does not swamp the
    signal is the unsolved part; until it is solved, supply a real spectrum instead.
    """

    low, high = _WINDOWS_PPM.get(nucleus, _WINDOWS_PPM["13C"])
    half_width = _LINEWIDTH_PPM.get(nucleus, _LINEWIDTH_PPM["13C"]) / 2.0
    ppm = np.linspace(low, high, _SPECTRUM_POINTS)
    data = np.zeros(_SPECTRUM_POINTS, dtype=float)
    for centre in shifts_ppm:
        data += 1.0 / (1.0 + ((ppm - centre) / half_width) ** 2)  # Lorentzian
    rng = np.random.default_rng(seed)
    data += rng.normal(0.0, 1.0 / _NOISE_SNR, _SPECTRUM_POINTS)
    return NMRSpectrum(
        data=data,
        ppm_axis=ppm,
        metadata={"synthetic": True, "basis": "experimental_shift_positions"},
        nucleus=nucleus,
        solvent="unknown",
        field_mhz=100.0 if nucleus == "13C" else 400.0,
    )


def _log_odds(posterior: float) -> float:
    """Posterior confidence → log-odds, clipped so a saturated value stays finite."""

    p = min(max(float(posterior), _LOGIT_CLIP), 1.0 - _LOGIT_CLIP)
    return math.log(p / (1.0 - p))


def _shift_signature(prediction: ShiftPrediction | None, nucleus: str) -> tuple | None:
    """The predicted (shift, σ) multiset for one nucleus — the verifier's whole input.

    Two candidates with an identical signature cannot be separated by any test that reads
    the prediction, regardless of whether their HOSE codes differ. Comparing *codes*
    (what ``predictions_are_distinguishable`` and ``false_confirmation`` both do) misses
    exactly this case: measured, codes diverge at sphere 3 while the post-back-off
    lookups stay bit-identical.
    """

    if prediction is None:
        return None
    return tuple(
        sorted(
            (round(float(s.predicted_ppm), 6), round(float(s.uncertainty_ppm), 6))
            for s in prediction.shifts
            if s.nucleus == nucleus
        )
    )


def _n_applicable(result: VerificationResult) -> int:
    return sum(1 for t in result.test_results if t.applicable)


def _has_evidence(result: VerificationResult) -> bool:
    """Whether the verdict rested on experimental data at all.

    ``PredictionBoundsTest`` stays *applicable* on a spectrum with no usable peaks — it
    scores -1 rather than abstaining — so counting applicable tests is **not** enough, and
    a peak-free spectrum would otherwise be read as evidence. ``AssignmentsTest`` is the
    honest signal: it abstains precisely when ``not resonances or not units``, so its
    applicability is equivalent to "the spectrum yielded something to match".

    A pair whose truth had no experimental units is bucketed ``no_evidence``, because a
    tie there is a statement about the spectrum, not about the structures.
    """

    return any(t.applicable for t in result.test_results if t.name == "assignments")


def measure_verifier_margin(
    *,
    test: Sequence[Mapping[str, Any]],
    nucleus: str = "13C",
    spectrum_for: Callable[[Mapping[str, Any], Sequence[float], str], NMRSpectrum | None],
    max_molecules: int | None = None,
    options: VerificationOptions | None = None,
    keep_pairs: bool = False,
) -> VerifierMarginReport:
    """Score held-out molecules and their decoys through the multi-test verifier.

    ``test`` is a sequence of NMReDATA-shaped records (``molblock`` + ``assignments``).

    ``spectrum_for(record, observed_shifts, nucleus)`` must return the **real** spectrum
    for that record, or ``None`` to skip it. The spectrum is a required input rather than
    something this module synthesises, because a synthesised one was measured not to
    transfer — see the warning on :func:`simulate_spectrum`. Passing that function here
    reproduces the refuted measurement and is not a valid basis for any published number.

    The caller also owns the split **and** the knowledge base: build the table from a
    disjoint training split before calling, or the truth's prediction is memorised and
    every margin is inflated. The table actually in force is recorded on the report.
    """

    if not test:
        raise ValueError("measure_verifier_margin needs a non-empty test split")

    # Imported here so the module can be read without paying the KB load.
    from moltrace.spectroscopy.predict.nmrnet_wrapper import _fallback_kb

    kb = _fallback_kb()
    # n_conformers is inert on the HOSE path (it is purely topological) but verify_structure
    # still embeds the requested ensemble before falling back, so 1 is identical and cheap.
    opts = options or VerificationOptions(nucleus=nucleus, predict_n_conformers=1)

    generated = scored = truth_wins = decoy_wins = exact_ties = 0
    no_evidence = prediction_identical = rejected_on_formula = unscorable = 0
    both_consistent = 0
    examined = 0
    margins: list[float] = []
    by_kind: dict[str, dict[str, int]] = {}
    pairs: list[PairMargin] = []

    for record in test:
        if max_molecules is not None and examined >= max_molecules:
            break
        mol = molecule_from_record(record)
        if mol is None:
            continue
        observed = [
            float(a["shift_ppm"])
            for a in record.get("assignments", [])
            if a.get("nucleus") == nucleus
        ]
        if len(observed) < _MIN_OBSERVED_SHIFTS:
            continue
        try:
            truth_smiles = Chem.MolToSmiles(Chem.RemoveHs(mol))
            decoys = generate_decoys(truth_smiles)
        except (ValueError, Chem.KekulizeException, RuntimeError):
            continue
        if not decoys:
            continue

        spectrum = spectrum_for(record, observed, nucleus)
        if spectrum is None:
            continue
        try:
            truth_result = verify_structure(spectrum, truth_smiles, options=opts)
            # Same n_conformers the verifier used, so the signature describes the
            # prediction the verdict actually rested on (inert on the HOSE path, but the
            # two must not be able to diverge if an NMRNet checkpoint is present).
            truth_prediction = predict_shifts(
                truth_smiles, n_conformers=opts.predict_n_conformers
            )
        except Exception:
            continue
        truth_signature = _shift_signature(truth_prediction, nucleus)
        if truth_signature is None:
            continue
        # The truth's own predicted count must match what was observed, or the two
        # candidates are being compared against differently-shaped evidence.
        if len(truth_signature) != len(observed):
            continue
        examined += 1
        truth_has_evidence = _has_evidence(truth_result)

        for decoy in decoys:
            generated += 1
            bucket = by_kind.setdefault(
                str(decoy.kind),
                {
                    "truth_wins": 0,
                    "decoy_wins": 0,
                    "exact_ties": 0,
                    "no_evidence": 0,
                    "prediction_identical": 0,
                    "rejected_on_formula": 0,
                    "unscorable": 0,
                },
            )

            def _record(
                outcome: str,
                *,
                _bucket: dict[str, int] = bucket,
                _truth: str = truth_smiles,
                _decoy_smiles: str = decoy.smiles,
                _decoy_kind: str = str(decoy.kind),
            ) -> None:
                """Bucket one non-scored outcome. Loop state is bound at definition."""

                _bucket[outcome] += 1
                if keep_pairs:
                    pairs.append(
                        PairMargin(
                            truth_smiles=_truth,
                            decoy_smiles=_decoy_smiles,
                            decoy_kind=_decoy_kind,
                            outcome=outcome,
                        )
                    )

            if not truth_has_evidence:
                no_evidence += 1
                _record(MarginOutcome.NO_EVIDENCE)
                continue
            try:
                decoy_prediction = predict_shifts(
                    decoy.smiles, n_conformers=opts.predict_n_conformers
                )
            except Exception:
                unscorable += 1
                _record(MarginOutcome.UNSCORABLE)
                continue
            decoy_signature = _shift_signature(decoy_prediction, nucleus)
            if decoy_signature is None:
                unscorable += 1
                _record(MarginOutcome.UNSCORABLE)
                continue
            if len(decoy_signature) != len(observed):
                rejected_on_formula += 1
                _record(MarginOutcome.REJECTED_ON_FORMULA)
                continue
            if decoy_signature == truth_signature:
                prediction_identical += 1
                _record(MarginOutcome.PREDICTION_IDENTICAL)
                continue

            try:
                decoy_result = verify_structure(spectrum, decoy.smiles, options=opts)
            except Exception:
                unscorable += 1
                _record(MarginOutcome.UNSCORABLE)
                continue

            margin = _log_odds(truth_result.posterior_confidence) - _log_odds(
                decoy_result.posterior_confidence
            )
            scored += 1
            margins.append(margin)
            if truth_result.verdict == "consistent" and decoy_result.verdict == "consistent":
                both_consistent += 1
            if margin > 0.0:
                truth_wins += 1
                outcome_counter = "truth_wins"
            elif margin < 0.0:
                decoy_wins += 1
                outcome_counter = "decoy_wins"
            else:
                exact_ties += 1
                outcome_counter = "exact_ties"
            bucket[outcome_counter] += 1
            if keep_pairs:
                pairs.append(
                    PairMargin(
                        truth_smiles=truth_smiles,
                        decoy_smiles=decoy.smiles,
                        decoy_kind=str(decoy.kind),
                        outcome=MarginOutcome.SCORED,
                        truth_posterior=truth_result.posterior_confidence,
                        decoy_posterior=decoy_result.posterior_confidence,
                        log_odds_margin=margin,
                        truth_verdict=truth_result.verdict,
                        decoy_verdict=decoy_result.verdict,
                        n_applicable_truth=_n_applicable(truth_result),
                    )
                )

    notes = [
        f"Scored through verify_structure on the caller-supplied {nucleus} spectrum.",
        "Margins are log-odds differences, which are invariant to the shared prior; "
        "posterior-confidence margins are not comparable across priors.",
        "'prediction_identical' pairs got a bit-identical predicted shift multiset, so "
        "the verifier was never given anything to separate — a predictor-coverage "
        "finding, dominated by KnowledgeBase back-off on a thin table.",
        "'no_evidence' pairs had no experimental units to match; a tie there describes "
        "the spectrum, not the structures.",
        "An exact tie is counted separately and credited to neither side.",
        f"Knowledge base in force: {kb.source} ({kb.reference_count} reference atoms).",
    ]

    return VerifierMarginReport(
        nucleus=nucleus,
        molecules_examined=examined,
        pairs_generated=generated,
        pairs_scored=scored,
        truth_wins=truth_wins,
        decoy_wins=decoy_wins,
        exact_ties=exact_ties,
        no_evidence=no_evidence,
        prediction_identical=prediction_identical,
        rejected_on_formula=rejected_on_formula,
        unscorable=unscorable,
        both_consistent=both_consistent,
        kb_source=kb.source,
        kb_reference_count=kb.reference_count,
        margins=margins,
        by_kind=by_kind,
        pairs=pairs,
        notes=notes,
    )
