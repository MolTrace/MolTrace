"""Region-integration methods (Mnova-equivalent Sum / Edited Sum / Peaks)."""

from .methods import (
    IntegrationResult,
    integrate,
    integrate_edited_sum,
    integrate_peaks,
    integrate_sum,
)

__all__ = [
    "IntegrationResult",
    "integrate",
    "integrate_edited_sum",
    "integrate_peaks",
    "integrate_sum",
]
