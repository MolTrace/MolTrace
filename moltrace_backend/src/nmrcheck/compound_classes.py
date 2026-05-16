"""Canonical compound-class taxonomy shared across SpectraCheck routes.

The SpectraCheck workspace lets the user pick a structural class for the
sample being analyzed (carbohydrates, lipids, peptides, …). Every preview /
analyze endpoint accepts an optional ``compound_class`` form parameter; this
module is the single source of truth for the allowed values and for the
``normalize_compound_class`` helper used by every route to validate and
canonicalize the input.

Keep this list in sync with
``moltrace_frontend/src/lib/spectracheck/compound-classes.ts``.
"""

from __future__ import annotations

from typing import Final

COMPOUND_CLASS_UNSPECIFIED: Final[str] = "unspecified"

# Canonical class identifiers — the strings the frontend sends and the
# backend stores. Order is not significant.
COMPOUND_CLASS_VALUES: Final[frozenset[str]] = frozenset(
    {
        # Alphabetical by canonical identifier; ``unspecified`` last to mirror
        # the frontend's user-visible ordering.
        "alkaloids",
        "carbohydrates",
        "fatty_acids",
        "flavonoids",
        "glycoproteins",
        "lipids",
        "macrocycles",
        "macromolecules",
        "natural_products",
        "new_scaffolds",
        "nucleic_acids",
        "organometallics",
        "peptides",
        "polymers",
        "proteins",
        "small_molecules",
        "steroids",
        "terpenoids",
        COMPOUND_CLASS_UNSPECIFIED,
    }
)


def normalize_compound_class(value: str | None) -> str | None:
    """Return the canonical compound-class string or ``None``.

    - ``None`` / empty input → ``None`` (no class hint).
    - Recognised value (case-insensitive, trim-tolerant) → canonical lowercase
      identifier, with the sentinel ``unspecified`` mapped to ``None`` so
      downstream code only has to check truthiness.
    - Unrecognised value → ``None`` (caller may surface a warning).
    """
    if value is None:
        return None
    trimmed = str(value).strip().lower()
    if not trimmed:
        return None
    if trimmed not in COMPOUND_CLASS_VALUES:
        return None
    if trimmed == COMPOUND_CLASS_UNSPECIFIED:
        return None
    return trimmed


def is_known_compound_class(value: str | None) -> bool:
    """True if ``value`` is a recognised class identifier (including unspecified)."""
    if value is None:
        return False
    return str(value).strip().lower() in COMPOUND_CLASS_VALUES
