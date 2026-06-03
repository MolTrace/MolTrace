"""Chemical-shift prediction (NMRNet wrapper + HOSE-code fallback)."""

from .nmrnet_wrapper import (
    AtomShift,
    NMRNetUnavailable,
    ShiftPrediction,
    build_seed_knowledge_base,
    hose_code,
    load_knowledge_base,
    predict_shifts,
)

__all__ = [
    "AtomShift",
    "NMRNetUnavailable",
    "ShiftPrediction",
    "build_seed_knowledge_base",
    "hose_code",
    "load_knowledge_base",
    "predict_shifts",
]
