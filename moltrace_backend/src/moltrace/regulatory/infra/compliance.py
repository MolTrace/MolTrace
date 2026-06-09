"""GAMP 5 Appendix D11 / CSV validation-document skeleton (Prompt 19).

Produces a **versioned** Computer-System-Validation document template — intended
use, GxP risk class, requirements-traceability, and test-evidence slots — pinned
to the exact rule-set version it validates. The Prompt 21 validation suite fills
the slots with the formal CSV evidence (worked examples, property-based tests,
external validation, the formula→citation map).

Reuse-first: the D11 markdown template itself is the tested spectroscopy
:func:`~moltrace.spectroscopy.infra.compliance.render_gamp5_d11_template`; this
module is a regulatory facade that sets the Regulatory-Hub defaults and pins the
document to a rule-set version. Deterministic: identical inputs render byte-identical
output (slots show ``<to be completed>``), so the same version always produces the
same document.

Language guardrail (Prompt 12/18): the template states the software provides
**controls that support** 21 CFR Part 11 / GAMP 5 / draft Annex 22 — full
computerised-system validation and the compliance determination remain the
regulated user's responsibility. Never emit "compliant" claims.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from moltrace.regulatory.infra.eval import RegulatoryMetricVector
from moltrace.spectroscopy.infra.compliance import render_gamp5_d11_template

__all__ = [
    "build_regulatory_validation_document",
    "metric_evidence_block",
    "render_gamp5_d11_template",
]

_SYSTEM_NAME = "MolTrace Regulatory Hub"
_INTENDED_USE_DEFAULT = (
    "Decision-support for regulatory impurity assessment and submission drafting. "
    "All quantitative and classification outputs are produced by a deterministic, "
    "version-pinned rule engine tied to a named guidance revision; LLM assistance "
    "is limited to narrative drafting, retrieval, and triage and never produces a "
    "regulated number. Every output requires review and sign-off by a qualified "
    "regulatory-affairs / toxicology professional and is not a regulatory "
    "determination or final filing content as generated."
)


def metric_evidence_block(vector: RegulatoryMetricVector) -> str:
    """A markdown table of the Phase 0 regulatory metric vector for the evidence slot."""

    rows = "\n".join(
        f"| {name} | {value} |" for name, value in sorted(vector.metric_items().items())
    )
    return "| Metric | Value |\n| --- | --- |\n" + (rows or "| (none measured) | — |")


def build_regulatory_validation_document(
    *,
    rule_set_version: str,
    intended_use: str = _INTENDED_USE_DEFAULT,
    document_id: str = "VAL-REG-D11-0001",
    document_version: str = "0.1.0",
    gxp_risk_class: str = "High",
    requirements: Sequence[Mapping[str, Any]] | None = None,
    iq_evidence: Sequence[Mapping[str, Any]] | None = None,
    oq_evidence: Sequence[Mapping[str, Any]] | None = None,
    pq_evidence: Sequence[Mapping[str, Any]] | None = None,
    metric_vector: RegulatoryMetricVector | None = None,
) -> str:
    """Render the versioned GAMP 5 D11 CSV skeleton for a Regulatory-Hub rule-set version.

    The document's ``System Version`` is the ``rule_set_version`` content hash, so
    the validation evidence is pinned to the exact rule-set it covers. When a
    Phase 0 ``metric_vector`` is supplied its values are appended as pre-filled
    test evidence; otherwise the evidence slots remain ``<to be completed>`` for
    Prompt 21 to fill.
    """

    document = render_gamp5_d11_template(
        system_name=_SYSTEM_NAME,
        system_version=rule_set_version,
        intended_use=intended_use,
        gamp_software_category=5,
        gxp_risk_class=gxp_risk_class,
        document_id=document_id,
        document_version=document_version,
        requirements=requirements,
        iq_evidence=iq_evidence,
        oq_evidence=oq_evidence,
        pq_evidence=pq_evidence,
    )
    if metric_vector is not None:
        document += (
            "\n## 9a. Phase 0 Metric Vector (pre-filled)\n\n"
            + metric_evidence_block(metric_vector)
            + "\n"
        )
    return document
