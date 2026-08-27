"""Distribution-free prediction intervals for shift prediction (L1/D1).

The measured defect this closes. The held-out evaluation in :mod:`.shift_accuracy`
showed the predictor's reported ¹³C σ is **optimistic by roughly 3× in its tightest
bin** — atoms claiming σ ≤ 0.5 ppm have a mean absolute error of 0.76 ppm — while
being conservative in the wide bins. That is the worst possible shape, because a
tight σ is exactly what the verifier's ``_significance_from_sigma`` scores highest:
confidence is overstated precisely on the atoms the arbiter leans on hardest.

Why conformal rather than more calibration of σ. Platt and temperature scaling
(``ai.finetune``) calibrate a *classifier's* probabilities; neither gives a
regression predictor a coverage guarantee. Split conformal prediction does, and its
guarantee is the one a regulated buyer actually needs: **distribution-free and
finite-sample**. Calibrate on a held-out split and a 90 % interval covers the truth
at least 90 % of the time, whatever the model is and however wrong σ happens to be.
It assumes only exchangeability between calibration and test data — which the
molecule-level split in :mod:`.shift_accuracy` is built to provide.

Mondrian, not pooled. Binning the calibration residuals by nucleus × reported-σ
decile is what repairs the tight-σ bin *specifically*. A single pooled quantile
would widen every interval uniformly to cover the tight bin's true error — punishing
the atoms the predictor genuinely knows well, which is the opposite of useful.

What this module does not do. It does not replace σ: σ is the model's *claim*, the
interval is the *guarantee*, and reporting both is the honest form. It does not
decide anything — the deterministic verifier remains the sole arbiter of
correctness. And it never invents an interval it cannot support: a bin with too few
calibration points falls back to the nucleus-pooled quantile and records that it
did; an atom with no usable σ (an element-prior abstention) gets no interval at all.
"""

from __future__ import annotations

import json
import logging
import math
import os
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from moltrace.spectroscopy.infra.contract import content_hash

__all__ = [
    "CALIBRATION_PATH_ENV",
    "ConformalBin",
    "ConformalCalibration",
    "CoverageReport",
    "Interval",
    "conformal_calibration_status",
    "fit_conformal",
    "load_deployed_calibration",
    "measure_coverage",
    "min_calibration_size",
]

#: Bump when the fitting procedure changes in a way that makes an old calibration
#: incomparable. A persisted calibration's numbers cannot detect a change in how
#: they were produced — the same lesson the similarity encoder version records.
CALIBRATION_VERSION = "conformal-v1"

_DEFAULT_COVERAGE = 0.90
_DEFAULT_BINS = 10


def min_calibration_size(target_coverage: float) -> int:
    """Smallest calibration set that can support ``target_coverage``.

    Split conformal takes the ``ceil((n+1)·target)``-th smallest absolute residual as
    the interval half-width, so that index must exist: ``ceil((n+1)·target) ≤ n``. At
    90 % that is 9 points — a bound derived from the method, not a round number chosen
    for comfort. Below it the guarantee is simply unavailable, and the honest answer is
    to say so rather than to quote the widest residual seen and call it an interval.

    Solved by searching the *same* expression :func:`_conformal_quantile` evaluates,
    not by the closed form ``ceil(1/α) − 1``. The two disagree under floating point —
    ``1 − 0.90`` is ``0.09999…``, so ``ceil(1/α)`` is 11 and the closed form returns
    10 for a bound that is really 9. A guard computed by a different route than the
    one that enforces it will eventually contradict it.
    """

    target = float(target_coverage)
    if not 0.0 < target < 1.0:
        raise ValueError(f"target_coverage must be in (0, 1); got {target_coverage!r}")
    n = 1
    while math.ceil((n + 1) * target) > n:
        n += 1
    return n


def _conformal_quantile(residuals: Sequence[float], target_coverage: float) -> float:
    """The finite-sample conformal quantile of ``residuals``.

    Not ``numpy.quantile``: the ``(n+1)`` correction is what makes the coverage
    guarantee hold at finite ``n`` rather than only asymptotically.
    """

    ordered = sorted(float(r) for r in residuals)
    n = len(ordered)
    rank = int(math.ceil((n + 1) * float(target_coverage)))
    if rank > n:  # pragma: no cover - callers check min_calibration_size first
        raise ValueError(
            f"cannot reach {target_coverage:.0%} coverage from {n} calibration points"
        )
    return ordered[rank - 1]


@dataclass(frozen=True)
class ConformalBin:
    """One (nucleus, σ-range) taxon and the half-width that covers it."""

    nucleus: str
    sigma_lo: float
    sigma_hi: float  # inclusive upper edge; +inf on the last bin
    n: int
    half_width_ppm: float
    #: Mean reported σ in this bin, kept so the *shape* of the miscalibration stays
    #: visible: a bin whose half-width is far above its mean σ is one where the
    #: predictor was overconfident.
    mean_sigma_ppm: float

    def contains(self, sigma: float) -> bool:
        return self.sigma_lo <= sigma <= self.sigma_hi


@dataclass(frozen=True)
class Interval:
    """A prediction interval, and the basis on which it was issued."""

    half_width_ppm: float | None
    basis: str  # 'bin' | 'nucleus_pooled' | 'unavailable'
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.half_width_ppm is not None


@dataclass(frozen=True)
class ConformalCalibration:
    """A fitted calibration: σ → interval half-width, per nucleus."""

    target_coverage: float
    bins: tuple[ConformalBin, ...]
    pooled: Mapping[str, float]  # nucleus -> half-width from all its residuals
    n_calibration: Mapping[str, int]
    version: str = CALIBRATION_VERSION
    notes: tuple[str, ...] = field(default_factory=tuple)

    def interval(self, nucleus: str, sigma: float) -> Interval:
        """Half-width for one atom, or an explicit refusal.

        An atom with no usable σ is an abstention, not a prediction, and gets no
        interval: issuing one would put a guarantee on a number the predictor
        declined to make.
        """

        if sigma is None or not math.isfinite(float(sigma)) or float(sigma) < 0.0:
            return Interval(
                None,
                "unavailable",
                "no usable predicted uncertainty for this atom, so no interval is issued",
            )
        sigma = float(sigma)
        for b in self.bins:
            if b.nucleus == nucleus and b.contains(sigma):
                return Interval(b.half_width_ppm, "bin")
        pooled = self.pooled.get(nucleus)
        if pooled is not None:
            return Interval(
                pooled,
                "nucleus_pooled",
                f"no calibrated band covers a reported uncertainty of {sigma:.3f} ppm "
                f"for {nucleus}; using the nucleus-wide interval",
            )
        # Distinguish "never seen" from "seen too thinly": they call for different
        # actions — collect this nucleus at all, versus collect more of it.
        seen = self.n_calibration.get(nucleus)
        if seen:
            return Interval(
                None,
                "unavailable",
                f"{nucleus} had {seen} calibration point(s), below the "
                f"{min_calibration_size(self.target_coverage)} a "
                f"{self.target_coverage:.0%} guarantee requires",
            )
        return Interval(
            None,
            "unavailable",
            f"{nucleus} was not represented in the calibration set",
        )

    def fingerprint(self) -> str:
        """Content address of this calibration, for the provenance record."""

        return content_hash(
            {
                "version": self.version,
                "target_coverage": self.target_coverage,
                "bins": [
                    {
                        "nucleus": b.nucleus,
                        "sigma_lo": round(b.sigma_lo, 6),
                        "sigma_hi": None if math.isinf(b.sigma_hi) else round(b.sigma_hi, 6),
                        "n": b.n,
                        "half_width_ppm": round(b.half_width_ppm, 6),
                    }
                    for b in self.bins
                ],
                "pooled": {k: round(v, 6) for k, v in sorted(self.pooled.items())},
            }
        )

    def reference_half_width(self, nucleus: str, reference_sigma_ppm: float) -> float | None:
        """The half-width at ``reference_sigma_ppm`` — the anchor a consumer scales against.

        Consumers that used to compare a σ against a fixed reference σ need the same
        anchor expressed as an interval. Derived from *this* calibration rather than
        restated as a constant, so refitting cannot leave the anchor pointing at a
        width the bands no longer produce.
        """

        return self.interval(nucleus, reference_sigma_ppm).half_width_ppm

    def to_json(self) -> str:
        """Serialise for deployment. Round-trips to an identical fingerprint."""

        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> ConformalCalibration:
        """Load a deployed calibration.

        Refuses a payload written by a different fitting procedure rather than
        interpreting its numbers under today's assumptions: a persisted calibration
        cannot detect a change in how it was produced, so the version is checked
        explicitly — the same reason the similarity encoder carries one.
        """

        payload = json.loads(text)
        version = payload.get("version")
        if version != CALIBRATION_VERSION:
            raise ValueError(
                f"calibration was fitted by {version!r} but this build expects "
                f"{CALIBRATION_VERSION!r}; refit rather than reinterpreting it"
            )
        bins = tuple(
            ConformalBin(
                nucleus=str(b["nucleus"]),
                sigma_lo=float(b["sigma_lo_ppm"]),
                sigma_hi=math.inf if b["sigma_hi_ppm"] is None else float(b["sigma_hi_ppm"]),
                n=int(b["n"]),
                half_width_ppm=float(b["half_width_ppm"]),
                mean_sigma_ppm=float(b["mean_sigma_ppm"]),
            )
            for b in payload.get("bins", [])
        )
        loaded = cls(
            target_coverage=float(payload["target_coverage"]),
            bins=bins,
            pooled={k: float(v) for k, v in payload.get("pooled_half_width_ppm", {}).items()},
            n_calibration={k: int(v) for k, v in payload.get("n_calibration", {}).items()},
            version=str(version),
            notes=tuple(payload.get("notes", [])),
        )
        expected = payload.get("fingerprint")
        if expected and loaded.fingerprint() != expected:
            raise ValueError(
                "calibration fingerprint does not match its contents; the file has been "
                "edited or truncated since it was fitted"
            )
        return loaded

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "target_coverage": self.target_coverage,
            "fingerprint": self.fingerprint(),
            "n_calibration": dict(sorted(self.n_calibration.items())),
            "bins": [
                {
                    "nucleus": b.nucleus,
                    "sigma_lo_ppm": b.sigma_lo,
                    "sigma_hi_ppm": None if math.isinf(b.sigma_hi) else b.sigma_hi,
                    "n": b.n,
                    "mean_sigma_ppm": b.mean_sigma_ppm,
                    "half_width_ppm": b.half_width_ppm,
                }
                for b in self.bins
            ],
            "pooled_half_width_ppm": dict(sorted(self.pooled.items())),
            "notes": list(self.notes),
        }


def _bin_edges(sigmas: Sequence[float], n_bins: int) -> list[tuple[float, float]]:
    """Quantile edges over ``sigmas``, deduplicated.

    Quantile bins rather than fixed-width: reported σ is heavily right-skewed, and
    fixed-width bands would put almost every atom in the first one — which is the
    band that most needs to be resolved.
    """

    ordered = sorted(sigmas)
    n = len(ordered)
    cuts: list[float] = []
    for i in range(1, n_bins):
        idx = min(n - 1, max(0, int(round(i * n / n_bins)) - 1))
        cuts.append(ordered[idx])
    edges: list[tuple[float, float]] = []
    lo = 0.0
    for cut in cuts:
        if cut <= lo:
            continue  # a repeated σ value: merging beats an empty band
        edges.append((lo, cut))
        lo = math.nextafter(cut, math.inf)
    edges.append((lo, math.inf))
    return edges


def fit_conformal(
    pairs: Mapping[str, Sequence[tuple[float, float]]],
    *,
    target_coverage: float = _DEFAULT_COVERAGE,
    n_bins: int = _DEFAULT_BINS,
) -> ConformalCalibration:
    """Fit a Mondrian split-conformal calibration.

    ``pairs`` maps nucleus -> sequence of ``(reported_sigma_ppm, absolute_error_ppm)``
    measured on a calibration split **disjoint** from both the training data and the
    split coverage will be evaluated on. Pairs with a non-finite σ are dropped: an
    element-prior abstention has no uncertainty to bin by.

    A bin too small to support the guarantee is *merged into* the nucleus-pooled
    quantile rather than being given a quantile it cannot justify, and the merge is
    recorded in ``notes``.
    """

    minimum = min_calibration_size(target_coverage)
    bins: list[ConformalBin] = []
    pooled: dict[str, float] = {}
    counts: dict[str, int] = {}
    notes: list[str] = []

    for nucleus, raw in sorted(pairs.items()):
        usable = [
            (float(s), float(e))
            for s, e in raw
            if math.isfinite(float(s)) and math.isfinite(float(e)) and float(s) >= 0.0
        ]
        dropped = len(raw) - len(usable)
        if dropped:
            notes.append(
                f"{nucleus}: {dropped} calibration point(s) dropped for having no usable "
                "predicted uncertainty"
            )
        counts[nucleus] = len(usable)
        if len(usable) < minimum:
            notes.append(
                f"{nucleus}: {len(usable)} calibration points is below the {minimum} "
                f"needed for a {target_coverage:.0%} guarantee; no interval will be issued"
            )
            continue

        pooled[nucleus] = _conformal_quantile([e for _s, e in usable], target_coverage)

        for lo, hi in _bin_edges([s for s, _e in usable], n_bins):
            members = [(s, e) for s, e in usable if lo <= s <= hi]
            if len(members) < minimum:
                if members:
                    notes.append(
                        f"{nucleus}: σ band [{lo:.3f}, "
                        f"{'inf' if math.isinf(hi) else format(hi, '.3f')}] holds "
                        f"{len(members)} point(s), below the {minimum} needed; folded into "
                        "the nucleus-wide interval"
                    )
                continue
            bins.append(
                ConformalBin(
                    nucleus=nucleus,
                    sigma_lo=lo,
                    sigma_hi=hi,
                    n=len(members),
                    half_width_ppm=_conformal_quantile(
                        [e for _s, e in members], target_coverage
                    ),
                    mean_sigma_ppm=statistics.fmean(s for s, _e in members),
                )
            )

    return ConformalCalibration(
        target_coverage=float(target_coverage),
        bins=tuple(bins),
        pooled=pooled,
        n_calibration=counts,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class CoverageReport:
    """Empirical coverage of a fitted calibration on a disjoint split.

    Coverage alone is not a quality measure — an infinitely wide interval covers
    everything. ``mean_half_width_ppm`` is what makes it one: at equal coverage,
    narrower is better, and that is the only honest definition of "sharper".
    """

    target_coverage: float
    per_nucleus: dict[str, dict[str, float]]
    n_scored: int
    n_no_interval: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def worst_deficit(self) -> float:
        """Largest shortfall below target across nuclei; 0.0 when all meet it.

        The direction that matters. Over-coverage costs sharpness; under-coverage
        means a stated guarantee is not being kept.
        """

        deficits = [
            max(0.0, self.target_coverage - stats["coverage"])
            for stats in self.per_nucleus.values()
            if stats["n"] > 0
        ]
        return max(deficits) if deficits else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_coverage": self.target_coverage,
            "worst_deficit": self.worst_deficit,
            "per_nucleus": self.per_nucleus,
            "n_scored": self.n_scored,
            "n_no_interval": self.n_no_interval,
            "notes": list(self.notes),
        }


def measure_coverage(
    calibration: ConformalCalibration,
    pairs: Mapping[str, Sequence[tuple[float, float]]],
) -> CoverageReport:
    """Score ``calibration`` on a split it was not fitted on.

    Atoms the calibration declines to give an interval are counted separately rather
    than scored as misses: an abstention is not a failed prediction, and folding the
    two together would make refusing to answer look like answering wrongly.
    """

    per_nucleus: dict[str, dict[str, float]] = {}
    scored = 0
    no_interval = 0
    notes: list[str] = []

    for nucleus, raw in sorted(pairs.items()):
        covered = 0
        widths: list[float] = []
        pooled_used = 0
        for sigma, error in raw:
            interval = calibration.interval(nucleus, float(sigma))
            if interval.half_width_ppm is None:
                no_interval += 1
                continue
            scored += 1
            widths.append(interval.half_width_ppm)
            if interval.basis == "nucleus_pooled":
                pooled_used += 1
            if abs(float(error)) <= interval.half_width_ppm:
                covered += 1
        n = len(widths)
        per_nucleus[nucleus] = {
            "n": float(n),
            "coverage": covered / n if n else 0.0,
            "mean_half_width_ppm": statistics.fmean(widths) if widths else float("nan"),
            "median_half_width_ppm": statistics.median(widths) if widths else float("nan"),
            "pooled_fallback_fraction": pooled_used / n if n else 0.0,
        }
        if n and covered / n < calibration.target_coverage:
            notes.append(
                f"{nucleus}: empirical coverage {covered / n:.1%} is below the "
                f"{calibration.target_coverage:.0%} target on this split"
            )

    if no_interval:
        notes.append(
            f"{no_interval} atom(s) received no interval and are excluded from coverage "
            "rather than counted as misses"
        )

    return CoverageReport(
        target_coverage=calibration.target_coverage,
        per_nucleus=per_nucleus,
        n_scored=scored,
        n_no_interval=no_interval,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Deployment
# --------------------------------------------------------------------------- #
#: Path to the fitted calibration this process should score matches against.
CALIBRATION_PATH_ENV = "MOLTRACE_CONFORMAL_CALIBRATION"

_DEPLOYED: ConformalCalibration | None = None
_DEPLOYED_LOADED = False


def load_deployed_calibration() -> ConformalCalibration | None:
    """The fitted calibration this process verifies against, or ``None``.

    Unset is a legitimate configuration -- a dev checkout with no fitted artifact --
    and the verifier falls back to the predictor's claimed sigma, saying so in each
    result's ``significance_basis``. That fallback is weaker, not absent: held-out
    measurement put the sigma basis at a half-width/sigma ratio running 8.66x down to
    1.77x across bins, where a correctly scaled sigma would give a constant, and it is
    worst exactly where the arbiter leans hardest.

    **Set-and-unloadable is a misconfiguration**, and it is logged at ERROR rather
    than absorbed, for the same reason the HOSE table is: it is what a deploy that
    forgot to stage the artifact looks like, and silently substituting the basis that
    was explicitly configured away is the failure this exists to prevent. A corrupt or
    version-mismatched file is treated the same way -- ``from_json`` raises on both,
    and neither is a reason to refuse service on the weaker basis.

    Cached for the life of the process: the artifact is deployed state, not
    configuration that changes under a running service.
    """

    global _DEPLOYED, _DEPLOYED_LOADED
    if _DEPLOYED_LOADED:
        return _DEPLOYED
    _DEPLOYED_LOADED = True

    raw_path = os.environ.get(CALIBRATION_PATH_ENV)
    if not raw_path:
        return None

    log = logging.getLogger(__name__)
    path = Path(raw_path)
    if not path.exists():
        log.error(
            "%s is set to %r but no such file exists. Structure verification will fall "
            "back to the predictor's claimed sigma, which held-out measurement showed is "
            "differentially mis-scaled. Fit one with "
            "scripts/measure_conformal_calibration.py.",
            CALIBRATION_PATH_ENV,
            raw_path,
        )
        return None

    try:
        _DEPLOYED = ConformalCalibration.from_json(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception(
            "%s at %r could not be loaded; falling back to the sigma basis. A version "
            "mismatch means the calibration was fitted by a different procedure than "
            "this build expects and its numbers are not comparable; a fingerprint "
            "mismatch means the file's contents were edited after fitting.",
            CALIBRATION_PATH_ENV,
            raw_path,
        )
        return None

    log.info(
        "conformal calibration loaded: target_coverage=%s bins=%d fingerprint=%s",
        _DEPLOYED.target_coverage,
        len(_DEPLOYED.bins),
        _DEPLOYED.fingerprint(),
    )
    return _DEPLOYED


def conformal_calibration_status() -> dict[str, Any]:
    """Which significance basis this process verifies on. Cheap enough for a probe."""

    raw_path = os.environ.get(CALIBRATION_PATH_ENV)
    return {
        "configured": bool(raw_path),
        "path_present": bool(raw_path) and Path(raw_path).exists(),
        "loaded": _DEPLOYED is not None,
        "basis": "conformal" if _DEPLOYED is not None else "predicted_sigma",
        "target_coverage": None if _DEPLOYED is None else _DEPLOYED.target_coverage,
        "fingerprint": None if _DEPLOYED is None else _DEPLOYED.fingerprint(),
        "n_bins": None if _DEPLOYED is None else len(_DEPLOYED.bins),
    }
