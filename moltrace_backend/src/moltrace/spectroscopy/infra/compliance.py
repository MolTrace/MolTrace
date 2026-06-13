"""Compliance document generators (Phase 0 skeletons later phases fill in).

* :func:`render_gamp5_d11_template` -- a versioned GAMP 5 Appendix D11
  Computerised System Validation (CSV) document skeleton: intended use, GxP risk
  classification, requirements traceability, IQ/OQ/PQ activities, and test
  evidence slots.  Ties to Prompt 12 (21 CFR Part 11 audit-trail controls).
* :func:`build_ich_report_stub` / :func:`render_ich_report_stub` -- a
  *deterministic* ICH Q2(R2) report stub built from a
  :class:`~moltrace.spectroscopy.infra.contract.SpectraCheckContract`, embedding
  the contract content hash so the analytical evidence is traceable.  This is the
  lightweight handoff artefact the end-to-end pipeline produces for the
  Regentry.

Everything here is pure (stdlib only) and timestamp-free, so the generated
templates are byte-reproducible and safe to version-control as controlled
templates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from moltrace.spectroscopy.infra.contract import SCHEMA_VERSION, SpectraCheckContract

__all__ = [
    "GAMP5_APPENDIX",
    "GAMP5_EDITION",
    "ICH_GUIDELINE_DEFAULT",
    "TEMPLATE_VERSION",
    "build_ich_report_stub",
    "render_gamp5_d11_template",
    "render_ich_report_stub",
]

GAMP5_EDITION = (
    "GAMP 5: A Risk-Based Approach to Compliant GxP Computerised Systems "
    "(2nd ed., ISPE, 2022)"
)
GAMP5_APPENDIX = "D11"
ICH_GUIDELINE_DEFAULT = "Q2(R2)"
# Bump when the *template structure* changes (independent of the data contract).
TEMPLATE_VERSION = "1.0.0"

_TBD = "_<to be completed>_"


def _traceability_rows(requirements: Sequence[Mapping[str, Any]] | None) -> str:
    header = (
        "| Req ID | User Requirement (URS) | Functional Spec (FS) | "
        "Risk | Test Ref | Status |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
    )
    if not requirements:
        rows = f"| {_TBD} | {_TBD} | {_TBD} | {_TBD} | {_TBD} | {_TBD} |\n"
    else:
        rows = ""
        for req in requirements:
            rows += (
                f"| {req.get('id', _TBD)} | {req.get('urs', _TBD)} | "
                f"{req.get('fs', _TBD)} | {req.get('risk', _TBD)} | "
                f"{req.get('test_ref', _TBD)} | {req.get('status', _TBD)} |\n"
            )
    return header + rows


def _evidence_block(label: str, evidence: Sequence[Mapping[str, Any]] | None) -> str:
    header = (
        "| Test ID | Objective | Expected | Actual | Result |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    if not evidence:
        body = f"| {_TBD} | {_TBD} | {_TBD} | {_TBD} | {_TBD} |\n"
    else:
        body = ""
        for row in evidence:
            body += (
                f"| {row.get('id', _TBD)} | {row.get('objective', _TBD)} | "
                f"{row.get('expected', _TBD)} | {row.get('actual', _TBD)} | "
                f"{row.get('result', _TBD)} |\n"
            )
    return f"### {label}\n\n{header}{body}"


def render_gamp5_d11_template(
    *,
    system_name: str,
    system_version: str,
    intended_use: str,
    gamp_software_category: int = 5,
    gxp_risk_class: str = "High",
    document_id: str = "VAL-D11-0001",
    document_version: str = "0.1.0",
    requirements: Sequence[Mapping[str, Any]] | None = None,
    iq_evidence: Sequence[Mapping[str, Any]] | None = None,
    oq_evidence: Sequence[Mapping[str, Any]] | None = None,
    pq_evidence: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Render a GAMP 5 Appendix D11 CSV validation-document skeleton (markdown).

    Slots not yet filled render as ``<to be completed>`` so the same call yields
    a deterministic, controllable template that later validation phases populate.
    """

    if gamp_software_category not in (1, 3, 4, 5):
        raise ValueError("GAMP software category must be one of 1, 3, 4, 5")

    return f"""# Computerised System Validation Plan & Report

**Standard:** {GAMP5_EDITION}
**Appendix:** {GAMP5_APPENDIX} (template v{TEMPLATE_VERSION}, contract schema v{SCHEMA_VERSION})

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | {document_id} |
| Document Version | {document_version} |
| System | {system_name} |
| System Version | {system_version} |
| Status | DRAFT |
| Author | {_TBD} |
| Reviewer (QA) | {_TBD} |
| Approver (System Owner) | {_TBD} |
| Effective Date | {_TBD} |

## 2. Purpose & Scope

This document defines and records the validation of **{system_name}** following a
risk-based approach per {GAMP5_EDITION}. It establishes that the system is fit
for its intended use and operates in a state of control.

## 3. Intended Use

{intended_use}

## 4. System Description

{_TBD}

## 5. GxP Risk Assessment

| Attribute | Classification |
| --- | --- |
| GAMP Software Category | {gamp_software_category} |
| GxP Risk Class | {gxp_risk_class} |
| Patient-Safety Impact | {_TBD} |
| Data-Integrity Impact | {_TBD} |

Risk controls are commensurate with the classification above; testing rigour and
review depth scale with risk.

## 6. Regulatory Framework

Electronic records and electronic signatures generated by this system are
controlled per **21 CFR Part 11** using the MolTrace audit-trail subsystem
(`moltrace.spectroscopy.audit`, Prompt 12): tamper-evident hash-chained records,
electronic-signature primitives (Part 11.50/.70), and AI model-weight checksums
for reproducibility. Full computerised-system validation and the overall
compliance determination remain the regulated user's responsibility.

## 7. Requirements Traceability Matrix

{_traceability_rows(requirements)}

## 8. Validation Activities

{_evidence_block("8.1 Installation Qualification (IQ)", iq_evidence)}

{_evidence_block("8.2 Operational Qualification (OQ)", oq_evidence)}

{_evidence_block("8.3 Performance Qualification (PQ)", pq_evidence)}

## 9. Test Evidence Summary

Quantitative acceptance evidence (e.g., the Phase 0 metric vector -- RMSE, F1,
Top-k, BedROC, ECE -- and the end-to-end determinism result) is attached here:

{_TBD}

## 10. Deviations & CAPA

{_TBD}

## 11. Validation Summary & Conclusion

{_TBD}

## 12. Approvals

| Role | Name | Signature | Date |
| --- | --- | --- | --- |
| Author | {_TBD} | {_TBD} | {_TBD} |
| QA | {_TBD} | {_TBD} | {_TBD} |
| System Owner | {_TBD} | {_TBD} | {_TBD} |
"""


def build_ich_report_stub(
    contract: SpectraCheckContract,
    *,
    procedure_title: str = "NMR identity & purity confirmation",
    ich_guideline: str = ICH_GUIDELINE_DEFAULT,
) -> dict[str, Any]:
    """Build a deterministic ICH Q2(R2) report stub from a SpectraCheck contract.

    Pure function of the contract (no timestamps / random ids), so the stub --
    including the embedded ``contract_content_hash`` -- is byte-reproducible and
    safe for the end-to-end determinism gate.
    """

    body = contract.to_dict()
    spectrum = body["spectrum"]
    return {
        "report_type": "ich_report_stub",
        "ich_guideline": ich_guideline,
        "procedure_title": procedure_title,
        "schema_version": SCHEMA_VERSION,
        "status": "stub_pending_full_validation",
        "spectrum": {
            "nucleus": spectrum["nucleus"],
            "solvent": spectrum["solvent"],
            "field_mhz": spectrum["field_mhz"],
        },
        "result_summary": {
            "peak_count": len(body["peaks"]),
            "multiplet_count": len(body["multiplets"]),
            "classification_summary": body["classification_summary"],
            "integration": body.get("integration", {}),
        },
        # ICH Q2(R2) validation characteristics -- slots for later phases.
        "validation_characteristics": {
            "specificity": "pending",
            "accuracy": "pending",
            "precision": "pending",
            "range": "pending",
        },
        "evidence": {
            "contract_content_hash": contract.content_hash(),
            "pipeline_version": body["provenance"].get("pipeline_version", ""),
            "fingerprint_hash": body["provenance"].get("fingerprint_hash", ""),
        },
    }


def render_ich_report_stub(stub: Mapping[str, Any]) -> str:
    """Render an ICH report stub as human-readable markdown for the Regentry."""

    spectrum = stub.get("spectrum", {})
    summary = stub.get("result_summary", {})
    evidence = stub.get("evidence", {})
    characteristics = stub.get("validation_characteristics", {})
    char_rows = "".join(
        f"| {name} | {status} |\n" for name, status in sorted(characteristics.items())
    )
    return f"""# ICH {stub.get('ich_guideline', '')} Report (Stub)

**Procedure:** {stub.get('procedure_title', '')}
**Status:** {stub.get('status', '')}
**Contract schema:** v{stub.get('schema_version', '')}

## Sample / Spectrum

| Field | Value |
| --- | --- |
| Nucleus | {spectrum.get('nucleus', '')} |
| Solvent | {spectrum.get('solvent', '')} |
| Field (MHz) | {spectrum.get('field_mhz', '')} |

## Result Summary

- Peaks detected: {summary.get('peak_count', 0)}
- Multiplets: {summary.get('multiplet_count', 0)}
- Classification: {summary.get('classification_summary', {})}

## Validation Characteristics (ICH {stub.get('ich_guideline', '')})

| Characteristic | Status |
| --- | --- |
{char_rows}
## Evidence / Traceability

- Contract content hash: `{evidence.get('contract_content_hash', '')}`
- Pipeline version: `{evidence.get('pipeline_version', '')}`
- Spectrum fingerprint: `{evidence.get('fingerprint_hash', '')}`
"""
