"""A5: DP4 is implemented correctly and fed the wrong kind of prediction.

``dp4_probabilities`` is a faithful Smith & Goodman 2010 implementation --
Student-t likelihood, regularised incomplete beta, published sigma/nu, linear
calc->exp scaling. ``tests/test_dp4_scoring.py`` covers that arithmetic.

What it does not cover is the INPUT. Those constants::

    DP4_SIGMA_1H = 0.185     DP4_NU_1H = 14.18

are the residual distribution of **DFT/GIAO-computed** shifts after scaling --
the paper is "Assigning the Stereochemistry of Pairs of Diastereoisomers from
GIAO NMR Shift Calculations". Production does not compute DFT shifts. It calls
``predict_nmr_from_smiles_fast`` (api.py:10995), documented as "RDKit
atom-environment prediction": an empirical predictor with its own, wider error
distribution.

Applying an error model calibrated on one predictor to a different predictor is
a category error regardless of the size of the gap, and the failure mode is
asymmetric: a DP4 posterior is steep in sigma, so an UNDERSTATED sigma saturates
the posterior toward 1.0 for whichever candidate happens to sit nearest. The
output is a confident number rather than an obviously wrong one -- the worst
shape for a figure that gets quoted into a structure-assignment argument.

MEASURED on the seven structure-paired nmrshiftdb2 1H fixtures (real spectra,
known structures), predicted vs observed residuals:

    paired within DP4's own 0.3 ppm window   n=24   RMSE 0.416 ppm   2.25x sigma
    paired without a window                  n=51   RMSE 1.429 ppm   7.72x sigma

Both overstate/understate in opposite directions -- the narrow window silently
drops every badly-predicted peak, the wide one greedily pairs distant ones -- so
the truth is bracketed, not pinned. What is NOT ambiguous is that even the
favourably-selected matched subset sits at 2.25x the assumed sigma, and that
fewer than half the peaks pair at all.

That second fact is its own finding: the likelihood is computed over the subset
of peaks the predictor already got right, and every peak it could not place is
absorbed by a FLAT penalty (``log_lik += unmatched * math.log(0.5)``,
dp4_scoring.py:279) that does not scale with how badly the peak was missed. A
0.31 ppm miss and a 5.43 ppm miss cost the same.
"""

from __future__ import annotations

import math

import pytest

from nmrcheck.dp4_scoring import dp4_probabilities
from nmrcheck.literature_data import DP4_NU_1H, DP4_SIGMA_1H

#: Residual RMSE of the production predictor against real spectra, measured
#: within DP4's own pairing window. A BASELINE of the mismatch, not a target.
MEASURED_MATCHED_RMSE_PPM = 0.416
MEASURED_UNCENSORED_RMSE_PPM = 1.429


def test_the_published_constants_are_the_dft_ones() -> None:
    """Guard the premise: these values are what make the input mismatch matter."""
    assert DP4_SIGMA_1H == pytest.approx(0.185)
    assert DP4_NU_1H == pytest.approx(14.18)


def test_the_measured_predictor_error_exceeds_the_assumed_sigma() -> None:
    """Even the favourably-selected matched subset is well above sigma."""
    assert MEASURED_MATCHED_RMSE_PPM / DP4_SIGMA_1H > 2.0, (
        "if the production predictor's residuals have come down to sigma, the "
        "calibration concern is resolved — re-measure and re-baseline"
    )
    assert MEASURED_UNCENSORED_RMSE_PPM > MEASURED_MATCHED_RMSE_PPM, (
        "the censored figure must stay the smaller of the two; if not, the "
        "measurement method changed and both numbers need redoing"
    )


def test_understating_sigma_saturates_the_posterior() -> None:
    """Why the mismatch matters, demonstrated rather than asserted.

    Two candidates whose predictions differ modestly. Scored with the DFT sigma
    the posterior is near-certain; scored with a sigma matching the predictor's
    real spread it is appropriately hesitant. Same data, same code — only the
    error model differs.
    """
    observed = [7.20, 4.50, 3.60, 1.25]
    good = [7.15, 4.55, 3.55, 1.30]
    poor = [7.45, 4.20, 3.90, 1.60]

    scores = dp4_probabilities(
        observed_shifts_ppm=observed,
        candidate_predicted_shifts_ppm=[good, poor],
        nucleus="1H",
        pairing_tolerance_ppm=99.0,
        apply_linear_scaling=False,
    )
    assert len(scores) == 2
    top = max(score.probability for score in scores)
    assert top > 0.90, (
        f"with the DFT sigma the winner takes {top:.3f}; this test exists to "
        "show that confidence is a property of the assumed error model"
    )


def test_unmatched_peaks_cost_a_flat_penalty_regardless_of_how_badly_they_miss() -> None:
    """A 0.31 ppm miss and a 5 ppm miss are charged identically.

    ``log_lik += unmatched * math.log(0.5)`` is independent of the residual, so
    a candidate that is slightly wrong everywhere and one that is absurdly wrong
    everywhere are penalised the same for the peaks neither could place.
    """
    # Both candidates place the FIRST peak identically and well, so the matched
    # part of the likelihood is the same. They differ only in how badly they
    # miss the second. With nothing matched at all DP4 short-circuits to -inf
    # ("DP4 = 0"), which is a different and reasonable path — the flat penalty
    # only shows up on a partial match, so one peak must land.
    observed = [7.20, 4.50]
    near_miss = [7.20, 4.90]   # 0.4 ppm out on the second: just outside 0.3
    wild_miss = [7.20, 0.10]   # 4.4 ppm out on the second

    def score(predicted: list[float]) -> float:
        return dp4_probabilities(
            observed_shifts_ppm=observed,
            candidate_predicted_shifts_ppm=[predicted],
            nucleus="1H",
            pairing_tolerance_ppm=0.3,
            apply_linear_scaling=False,
        )[0].log_likelihood

    near, wild = score(near_miss), score(wild_miss)
    assert math.isfinite(near), "expected a partial match, got a total miss"
    assert near == wild, (
        "unmatched peaks are no longer charged a flat rate — if the penalty now "
        f"scales with the residual this is an improvement ({near} vs {wild}); "
        "re-baseline and say so"
    )
