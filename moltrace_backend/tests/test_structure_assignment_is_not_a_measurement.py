"""A3: what the structure-constrained assignment (P3) actually measures.

Scoring P3 against the ``expected`` proton block over seven real nmrshiftdb2
spectra gives a total class error of **0.0 H**, against 33.0 H for the legacy
ppm-window classifier. Read naively that says P3 is perfect and should be turned
on by default.

It says no such thing. P3's per-class numbers cannot disagree with the structure,
because the solver pins them:

    # structure_assignment.py, equality constraints
    for j in range(n_cols):
        ...
        b_eq.append(demand[j])          # demand[j] = that environment's
                                        # proton count, taken from the STRUCTURE

Every environment receives exactly its structural proton count as a hard
equality, so summing environments by class necessarily reproduces the structure's
own composition. ``class_rollup`` is therefore an identity, not a measurement,
and scoring it against a structure-derived expectation compares the structure
with itself.

That is the same circularity as the reported TOTAL, which
``_normalize_integrations_to_target`` pins to the structural proton count in both
arms -- which is why all seven spectra report a total exactly equal to the true
count in both arms.

What IS spectrum-dependent is ``total_cost``: the transport cost of moving the
observed signal onto the structure's environments. Measured on indole, feeding a
matching spectrum versus a purely aliphatic one moves it by a factor of ~1200.
That is a real structure-vs-spectrum mismatch signal, and it is currently not
surfaced as any kind of verdict -- ``feasible`` stays True and ``status`` stays
``ok`` for a spectrum belonging to a different compound entirely.

These tests exist to stop the tautology being mistaken for accuracy again, and to
pin the cost signal so it is not lost before something uses it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from nmrcheck.chemistry import structure_summary_from_smiles
from nmrcheck.peak_categorization import _build_structure_assignment

INDOLE = "c1ccc2[nH]ccc2c1"  # 6 aromatic CH + 1 N-H


@contextmanager
def _p3_enabled() -> Iterator[None]:
    previous = os.environ.get("MOLTRACE_STRUCTURE_ASSIGNMENT")
    os.environ["MOLTRACE_STRUCTURE_ASSIGNMENT"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MOLTRACE_STRUCTURE_ASSIGNMENT", None)
        else:
            os.environ["MOLTRACE_STRUCTURE_ASSIGNMENT"] = previous


def _assign(peaks: list[dict]) -> dict:
    with _p3_enabled():
        result = _build_structure_assignment(
            peaks=peaks,
            structure=structure_summary_from_smiles(INDOLE),
            solvent="CDCl3",
        )
    assert result is not None
    return result


_MATCHING = [
    {"shift_ppm": 7.6, "integration_h": 6.0, "category": "aromatic"},
    {"shift_ppm": 8.1, "integration_h": 1.0, "category": "labile"},
]
_WRONG_COMPOUND = [{"shift_ppm": 1.2, "integration_h": 7.0, "category": "aliphatic"}]
_MEANINGLESS = [{"shift_ppm": 4.0, "integration_h": 7.0, "category": "aliphatic"}]


def test_the_class_rollup_is_independent_of_the_spectrum() -> None:
    """The tautology, stated as a test.

    If this ever FAILS, P3's rollup has become spectrum-sensitive -- which would
    be an improvement, not a regression. Re-baseline it deliberately and say so.
    """
    rollups = [
        {k: v for k, v in (_assign(peaks).get("class_rollup") or {}).items() if v}
        for peaks in (_MATCHING, _WRONG_COMPOUND, _MEANINGLESS)
    ]
    assert rollups[0] == {"aromatic": 6.0, "labile": 1.0}
    assert rollups[0] == rollups[1] == rollups[2], (
        "class_rollup differed across spectra; if P3 now reads the spectrum "
        f"this is progress and needs a deliberate re-baseline: {rollups}"
    )


def test_the_rollup_therefore_must_not_be_presented_as_observed() -> None:
    """Guard the consequence, not just the mechanism.

    A purely aliphatic spectrum yields '6 aromatic H observed' for indole. Any
    surface that labels this an OBSERVED inventory, or sets it beside the
    expected inventory as corroboration, is showing the structure agreeing with
    itself.
    """
    rollup = _assign(_WRONG_COMPOUND).get("class_rollup") or {}
    assert rollup.get("aromatic") == 6.0, (
        "a spectrum with no aromatic signal at all still reports 6 aromatic H"
    )


def test_transport_cost_does_discriminate_and_is_the_real_signal() -> None:
    """``total_cost`` is what actually carries structure-vs-spectrum agreement."""
    good = _assign(_MATCHING)["total_cost"]
    bad = _assign(_WRONG_COMPOUND)["total_cost"]
    assert bad > good * 50, (
        f"transport cost failed to separate a matching spectrum ({good:.3f}) "
        f"from one belonging to a different compound ({bad:.3f}); if this "
        "stops holding, the only spectrum-dependent signal P3 produces is gone"
    )


def test_feasible_and_status_do_not_discriminate() -> None:
    """Pinned because it is the trap: the fields a caller would naturally trust.

    A reviewer reading ``feasible: true, status: ok`` would reasonably conclude
    the spectrum is consistent with the structure. It is not -- these peaks come
    from a different compound. Until something consumes ``total_cost``, neither
    field carries that judgement.
    """
    wrong = _assign(_WRONG_COMPOUND)
    assert wrong["feasible"] is True
    assert wrong["status"] == "ok"
    assert not wrong.get("notes"), (
        "a note now flags the mismatch; if so, wire it into the verdict and "
        "re-baseline this test"
    )
