"""Multiplet analysis utilities for MolTrace spectroscopy pipelines.

Builds on the GSD-resolved peak list from
:mod:`moltrace.spectroscopy.peaks.gsd` to identify chemical-environment
multiplet structure (s / d / t / q / p / sext / sept / dd / dt / td /
ddd / m), recover the underlying ¹J / ²J / ³J coupling constants, and
forward-model the expected peak-position pattern for FE overlay.
"""

from .analysis import (
    Multiplet,
    detect_multiplets,
    generate_synthetic_multiplet,
)

__all__ = ["Multiplet", "detect_multiplets", "generate_synthetic_multiplet"]
