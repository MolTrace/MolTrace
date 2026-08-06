"""Reaction kinetics from an ordered series of spectra.

A rate constant here is a fit over integration values, and integration accuracy is an open
programme in this codebase — the peak detector over-picks on real spectra. So the contract is
absolute: every call returns either a :class:`KineticFit` carrying ``k`` **with its standard
error, R² and residual diagnostics**, or a :class:`KineticRefusal` naming the cause. There is no
bare point estimate anywhere in this module, because a rate constant without its uncertainty is
the exact shape of a confident number with nothing behind it.

Two orders are supported, each linearised so the fit is an ordinary least-squares line whose
standard error is exact rather than iterative:

* first order — ``ln[A] = -kt + ln[A]₀``, slope ``-k``
* second order — ``1/[A] = kt + 1/[A]₀``, slope ``k``

:func:`identify_order` refuses rather than choosing the higher R² when the data cannot tell the
two apart. Picking the better fit would report an order the measurement does not support.

Pure: no ORM, no HTTP, no clock, no randomness.
"""

from moltrace.spectroscopy.kinetics.rates import (
    KineticFit,
    KineticRefusal,
    fit_first_order,
    fit_second_order,
    identify_order,
)

__all__ = [
    "KineticFit",
    "KineticRefusal",
    "fit_first_order",
    "fit_second_order",
    "identify_order",
]
