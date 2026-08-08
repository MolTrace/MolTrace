"""Say what scale a spectrum's integrals are on.

With a structure, integrals are apportioned across that molecule's proton budget
and a reported "2 H" means two protons. With no structure there is no budget, so
the scale is anchored to the smallest resolved signal instead: the ratios between
peaks are unchanged, but the absolute values are not proton counts and can run
far above the molecule's real proton total.

Measured on a real 500 MHz spectrum (validation fixture 33, MeOD) the same five
leading peaks read::

    with a 6 H budget:   0.008   0.098   0.094   1.0    0.5   H
    with no budget:      1.0    14.0    13.5   123.5   84.5  H

Eleven warnings were emitted on that spectrum and not one of them mentioned the
change of scale, so "123.5H" in an NMR string was indistinguishable from a
measurement. This module exists so that every path which can produce an
ungrounded spectrum says so in the same words.

It is a separate module rather than a helper inside ``spectrum``/``fid`` so the
two stores that call those parsers directly can import it without a cycle
(``api`` imports the stores). ``tests/test_integration_scale_disclosure.py``
enumerates the callers and fails when a new one neither supplies a budget nor
routes through :func:`disclose_relative_integrals`.
"""

from __future__ import annotations

from typing import Any, TypeVar

__all__ = ["RELATIVE_INTEGRAL_DISCLOSURE", "disclose_relative_integrals"]

# Worded around the budget rather than around the request, because the budget is
# also absent when a structure WAS supplied and could not be parsed. Saying "no
# structure was supplied" would be false in that case.
RELATIVE_INTEGRAL_DISCLOSURE = (
    "These integrals are relative. With no structure to set a proton budget, the "
    "smallest resolved signal is set to 1 H and every other signal is reported as "
    "a multiple of it, so the values are ratios between signals rather than proton "
    "counts. Supply a valid structure to scale them to its proton budget."
)

_PreviewT = TypeVar("_PreviewT")


def disclose_relative_integrals(
    preview: _PreviewT, *, expected_total_h: int | None
) -> _PreviewT:
    """Attach the disclosure to ``preview`` when nothing grounded its proton budget.

    Returns the preview either way so it can wrap a call in place. Duck-typed on
    ``warnings`` and ``inferred_peaks`` rather than typed against a preview model,
    because the two producers return different report classes.
    """
    if expected_total_h is not None:
        return preview
    warnings: Any = getattr(preview, "warnings", None)
    if warnings is None or not getattr(preview, "inferred_peaks", None):
        # Nothing was integrated, so there is no scale to disclaim.
        return preview
    if RELATIVE_INTEGRAL_DISCLOSURE not in warnings:
        warnings.append(RELATIVE_INTEGRAL_DISCLOSURE)
    return preview
