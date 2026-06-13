"""GAMP 5 Computer System Validation (CSV) package generator (Prompt 21, Phase 7).

Assembles the per-version validation evidence into one CSV package: intended use + risk class, the
worked-example / property-based / external-validation results, the formula->citation map, and a
sign-off slot for the independent regulatory-affairs expert audit (budget ~40 h; captures reviewer
identity + outcome). Built on the GAMP 5 D11 skeleton (:func:`build_regulatory_validation_document`,
which states the software provides *controls that support* — never a "compliant" claim) and the
Phase 7 :func:`evaluate_launch_gate`. Ties to Prompts 12 (Annex 22) and 19 (metric layer).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from moltrace.regulatory.infra.compliance import build_regulatory_validation_document
from moltrace.regulatory.infra.eval import RegulatoryMetricVector
from moltrace.regulatory.validation.citation_map import FormulaCitation, formula_citation_map
from moltrace.regulatory.validation.launch_gate import LaunchGateResult, evaluate_launch_gate

__all__ = ["CSVPackage", "ExpertSignOff", "build_csv_package"]

_PENDING = "<to be completed>"


@dataclass(frozen=True)
class ExpertSignOff:
    """The independent regulatory-affairs expert audit slot (Prompt 21: budget ~40 h)."""

    reviewer_id: str | None = None
    reviewer_role: str = "Independent regulatory-affairs / toxicology expert"
    hours_budgeted: int = 40
    outcome: str | None = None  # 'approved' | 'rejected' | None (pending)
    signed_date: str | None = None
    notes: str | None = None

    @property
    def is_signed(self) -> bool:
        return self.reviewer_id is not None and self.outcome is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "hours_budgeted": self.hours_budgeted,
            "outcome": self.outcome,
            "signed_date": self.signed_date,
            "notes": self.notes,
            "is_signed": self.is_signed,
        }

    def render(self) -> str:
        return (
            "\n## 12. Independent Regulatory-Affairs Expert Audit (sign-off)\n\n"
            f"- Reviewer role: {self.reviewer_role}\n"
            f"- Review budget (hours): {self.hours_budgeted}\n"
            f"- Reviewer identity: {self.reviewer_id or _PENDING}\n"
            f"- Outcome: {self.outcome or _PENDING}\n"
            f"- Date: {self.signed_date or _PENDING}\n"
            f"- Notes: {self.notes or _PENDING}\n"
            f"- Status: {'SIGNED' if self.is_signed else 'PENDING'}\n"
        )


@dataclass(frozen=True)
class CSVPackage:
    """The assembled CSV validation package for one rule-set version."""

    rule_set_version: str
    document: str  # the full GAMP 5 markdown document
    launch_gate: LaunchGateResult
    formula_citations: dict[str, FormulaCitation]
    sign_off: ExpertSignOff
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_set_version": self.rule_set_version,
            "launch_gate": self.launch_gate.as_dict(),
            "formula_citations": {f: c.as_dict() for f, c in self.formula_citations.items()},
            "sign_off": self.sign_off.as_dict(),
            "metadata": self.metadata,
        }


def _render_citation_table(citations: dict[str, FormulaCitation]) -> str:
    rows = "\n".join(
        f"| {c.formula} | {c.guideline} | {c.section_or_table} | {c.effective_date} | "
        f"{'yes' if c.is_traceable() else 'NO — BUILD FAILS'} |"
        for c in citations.values()
    )
    return (
        "\n## 11. Formula → Citation Map\n\n"
        "| Formula | Guideline | Section / Table | Effective | Traceable |\n"
        "| --- | --- | --- | --- | --- |\n" + rows + "\n"
    )


def build_csv_package(
    *,
    rule_set_version: str,
    sign_off: ExpertSignOff | None = None,
    metric_vector: RegulatoryMetricVector | None = None,
    document_id: str = "VAL-REG-CSV-0001",
    document_version: str = "0.1.0",
) -> CSVPackage:
    """Assemble the CSV validation package for ``rule_set_version``.

    The launch-gate result (worked-example / property / external evidence) fills the OQ evidence
    slots and the formula->citation map fills the requirements-traceability; the document then
    appends the citation table and the expert sign-off slot.
    """

    gate = evaluate_launch_gate()
    citations = formula_citation_map()
    sign_off = sign_off if sign_off is not None else ExpertSignOff()

    requirements = [
        {
            "id": c.formula,
            "requirement": f"Reproduce {c.guideline} ({c.section_or_table}) exactly.",
            "source": f"{c.guideline} — {c.section_or_table} (effective {c.effective_date})",
        }
        for c in citations.values()
    ]
    oq_evidence = [
        {"test": chk.name, "result": "PASS" if chk.passed else "FAIL", "detail": chk.detail}
        for chk in gate.checks
    ]

    document = build_regulatory_validation_document(
        rule_set_version=rule_set_version,
        document_id=document_id,
        document_version=document_version,
        requirements=requirements,
        oq_evidence=oq_evidence,
        metric_vector=metric_vector,
    )
    document += _render_citation_table(citations) + sign_off.render()

    return CSVPackage(
        rule_set_version=rule_set_version,
        document=document,
        launch_gate=gate,
        formula_citations=citations,
        sign_off=sign_off,
        metadata={"launch_gate_passed": gate.passed, "document_id": document_id},
    )
