class NMRCheckError(Exception):
    """Base package exception."""


class StructureParseError(NMRCheckError):
    """Raised when a SMILES string cannot be parsed."""


class PeakParseError(NMRCheckError):
    """Raised when 1H NMR text cannot be parsed."""
