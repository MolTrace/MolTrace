"""Formula -> citation map (Prompt 21, Phase 7).

Every implemented regulated formula must trace to its exact guideline source + section/table +
effective date. The map is built from the engine modules' own GUIDELINE / TABLE_REFERENCE /
EFFECTIVE_YEAR constants (the single source of truth — so the citation can never drift from the
code, and only genuinely-encoded references appear). A formula with no traceable source **fails
the build** via :func:`enforce_traceable_formulas`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.impurities import (
    cpca_classifier,
    m7_classifier,
    q3ab_calculator,
    q3c_solvents,
    q3d_elements,
)

__all__ = [
    "CitationError",
    "FormulaCitation",
    "enforce_traceable_formulas",
    "formula_citation_map",
    "implemented_formulas",
    "untraceable_formulas",
]


class CitationError(ValueError):
    """Raised when an implemented formula has no traceable guideline source."""


@dataclass(frozen=True)
class FormulaCitation:
    """One implemented formula's traceable guideline source."""

    formula: str
    guideline: str
    section_or_table: str
    effective_date: str

    def is_traceable(self) -> bool:
        return bool(
            self.guideline.strip() and self.section_or_table.strip() and self.effective_date.strip()
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "formula": self.formula,
            "guideline": self.guideline,
            "section_or_table": self.section_or_table,
            "effective_date": self.effective_date,
            "traceable": self.is_traceable(),
        }


def formula_citation_map() -> dict[str, FormulaCitation]:
    """Each implemented formula -> its citation, read from the engine constants."""

    q3a = q3ab_calculator.GUIDANCE_Q3A
    q3b = q3ab_calculator.GUIDANCE_Q3B
    entries = [
        FormulaCitation(
            "q3a_thresholds", q3a["guideline"], q3a["table_reference"], q3a["effective_year"]
        ),
        FormulaCitation(
            "q3b_thresholds", q3b["guideline"], q3b["table_reference"], q3b["effective_year"]
        ),
        FormulaCitation(
            "q3c_residual_solvent_pde",
            q3c_solvents.GUIDELINE,
            q3c_solvents.TABLE_REFERENCE,
            q3c_solvents.EFFECTIVE_YEAR,
        ),
        FormulaCitation(
            "q3d_elemental_pde",
            q3d_elements.GUIDELINE,
            q3d_elements.TABLE_REFERENCE,
            q3d_elements.EFFECTIVE_YEAR,
        ),
        FormulaCitation(
            "m7_class",
            m7_classifier.GUIDELINE,
            m7_classifier.CLASS_SCHEME_REFERENCE,
            m7_classifier.EFFECTIVE_YEAR,
        ),
        FormulaCitation(
            "m7_staged_ttc",
            m7_classifier.GUIDELINE,
            m7_classifier.TTC_TABLE_REFERENCE,
            m7_classifier.EFFECTIVE_YEAR,
        ),
        FormulaCitation(
            "cpca_category_and_ai_limit",
            cpca_classifier.GUIDELINE,
            cpca_classifier.METHOD_REFERENCE,
            cpca_classifier.EFFECTIVE_YEAR,
        ),
    ]
    return {e.formula: e for e in entries}


def implemented_formulas() -> tuple[str, ...]:
    """The in-scope formulas the validation suite covers."""

    return tuple(formula_citation_map())


def untraceable_formulas() -> list[str]:
    """Implemented formulas whose citation is incomplete (sorted)."""

    return sorted(f for f, c in formula_citation_map().items() if not c.is_traceable())


def enforce_traceable_formulas() -> None:
    """Raise :class:`CitationError` if any implemented formula has no traceable source."""

    missing = untraceable_formulas()
    if missing:
        raise CitationError(
            f"formula(s) with no traceable guideline source (the build fails): {missing}"
        )
