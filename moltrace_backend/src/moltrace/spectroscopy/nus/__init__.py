"""Non-uniform sampling (NUS) reconstruction — IST baseline + JTF-Net (Prompt 11).

:mod:`~moltrace.spectroscopy.nus.reconstruct` reconstructs non-uniformly sampled
FIDs onto the full Nyquist grid. It ships the classical, always-available
iterative soft-thresholding (IST-S) baseline (Stern-Donoho-Hoch 2007; Hyberts
et al. 2012) and an optional, lazily-loaded JTF-Net joint time-frequency backend
(Luo et al., Nat. Commun. 16, 2342, 2025), plus the reference-free REQUIRER
quality ratio via :func:`assess_reconstruction_quality`.
"""

from __future__ import annotations

from moltrace.spectroscopy.nus.reconstruct import (
    JTFNetUnavailable,
    ReconstructionResult,
    assess_reconstruction_quality,
    reconstruct_ist,
    reconstruct_jtfnet,
)

__all__ = [
    "JTFNetUnavailable",
    "ReconstructionResult",
    "assess_reconstruction_quality",
    "reconstruct_ist",
    "reconstruct_jtfnet",
]
