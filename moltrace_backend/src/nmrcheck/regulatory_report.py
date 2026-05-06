from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from html import escape as html_escape
from typing import Any

from .models import (
    EvidenceReportSection,
    StructureElucidationReleaseGate,
    StructureElucidationReportCandidateSummary,
    StructureElucidationReportRequest,
    StructureElucidationReportResult,
    StructureElucidationReportStatus,
    UnifiedCandidateConfidenceItem,
    UnifiedCandidateConfidenceResult,
)
from .unified_confidence import UnifiedConfidenceError, build_unified_candidate_confidence


class StructureElucidationReportError(ValueError):
    """Raised when a structure elucidation report cannot be composed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_summary(candidate: UnifiedCandidateConfidenceItem) -> StructureElucidationReportCandidateSummary:
    return StructureElucidationReportCandidateSummary(
        rank=candidate.rank,
        name=candidate.name,
        role=candidate.role,
        smiles=candidate.smiles,
        formula=candidate.formula,
        exact_mass=candidate.exact_mass,
        confidence_score=candidate.confidence_score,
        confidence_band=candidate.confidence_band,
        label=candidate.label,
        evidence_completeness=candidate.evidence_completeness,
        agreement_count=candidate.agreement_count,
        contradiction_count=candidate.contradiction_count,
        missing_layers=list(candidate.missing_layers),
        evidence_summary=list(candidate.evidence_summary),
        contradictions=list(candidate.contradictions),
        warnings=list(candidate.warnings),
    )


def _pick_status(
    request: StructureElucidationReportRequest,
    unified: UnifiedCandidateConfidenceResult,
    best: StructureElucidationReportCandidateSummary | None,
) -> tuple[StructureElucidationReportStatus, StructureElucidationReleaseGate]:
    contradiction_count = len(unified.global_contradictions) + (best.contradiction_count if best else 0)
    if best is None or not unified.evidence_layers_used or (best and best.confidence_band == "insufficient"):
        return "insufficient_evidence", "insufficient_evidence"
    if contradiction_count > 0 or (best and best.label == "conflicting_evidence"):
        return "blocked_by_contradictions", "blocked_by_contradictions"
    if request.review_status == "approved":
        return "approved_for_release", "approved_for_release"
    if request.require_human_approval:
        return "draft_requires_review", "requires_human_review"
    return "review_ready", "requires_human_review"


def _lcms_bridge_items(unified: UnifiedCandidateConfidenceResult) -> list[str]:
    metadata = dict((unified.component_metadata or {}).get("lcms_feature_family_bridge") or {})
    best_layer = None
    if unified.best_candidate is not None:
        best_layer = next(
            (layer for layer in unified.best_candidate.layers if layer.layer == "lcms_feature_family"),
            None,
        )
    if not metadata and best_layer is None:
        return []

    items = [
        "LC-MS consensus bridge included promoted/reviewed feature-family evidence as a candidate-confidence layer.",
    ]
    if metadata:
        items.extend(
            [
                f"LC-MS bridge adduct assumption: {metadata.get('adduct', 'not supplied')}.",
                f"LC-MS families considered: {metadata.get('family_count', 'not supplied')}; eligible families: {metadata.get('eligible_family_count', 'not supplied')}; promoted families: {metadata.get('promoted_family_count', 'not supplied')}.",
                f"LC-MS bridge result SHA-256: {metadata.get('bridge_result_sha256', 'not supplied')}.",
            ]
        )
    if best_layer is not None:
        items.extend(
            [
                f"Top-candidate LC-MS layer score: {best_layer.score if best_layer.score is not None else 'not scored'}; status: {best_layer.status}.",
                *(best_layer.evidence_summary[:4] or ["No LC-MS layer evidence summary was supplied for the top candidate."]),
            ]
        )
        if best_layer.warnings:
            items.extend([f"LC-MS warning: {warning}" for warning in best_layer.warnings[:4]])
    items.append(
        "LC-MS feature-family support is orthogonal evidence and does not prove molecular identity without NMR/MS/MS review."
    )
    return items


def _report_sections(
    *,
    request: StructureElucidationReportRequest,
    unified: UnifiedCandidateConfidenceResult,
    best: StructureElucidationReportCandidateSummary | None,
    ranked: list[StructureElucidationReportCandidateSummary],
    status: StructureElucidationReportStatus,
    release_gate: StructureElucidationReleaseGate,
    provenance: dict[str, Any],
) -> list[EvidenceReportSection]:
    best_name = best.name or best.smiles if best else "No supported candidate"
    top_delta_note = "Only one candidate was ranked."
    if len(ranked) >= 2:
        top_delta_note = f"Top-two confidence separation: {ranked[0].confidence_score - ranked[1].confidence_score:.3f}."

    contradiction_items = list(unified.global_contradictions)
    if best is not None:
        contradiction_items.extend(best.contradictions)
    if not contradiction_items:
        contradiction_items = ["No blocking contradictions were detected by the current evidence stack."]

    missing_layers = list(best.missing_layers if best else [])
    if not missing_layers:
        missing_layers = ["No missing layers were reported for the top candidate."]

    return [
        EvidenceReportSection(
            title="Executive decision summary",
            items=[
                f"Report status: {status}.",
                f"Release gate: {release_gate}.",
                f"Best supported candidate: {best_name}.",
                f"Selected adduct: {unified.selected_adduct}.",
                top_delta_note,
                "This report is a decision-support record, not an autonomous legal or regulatory determination.",
            ],
        ),
        EvidenceReportSection(
            title="Candidate confidence table",
            items=[
                f"#{item.rank} {item.name or item.smiles}: {item.confidence_score:.3f} confidence, {item.confidence_band} band, {item.agreement_count} agreeing layer(s), {item.contradiction_count} contradiction(s)."
                for item in ranked[:10]
            ]
            or ["No candidates were available."],
        ),
        EvidenceReportSection(
            title="Evidence layer coverage",
            items=[
                f"Evidence layers used: {', '.join(unified.evidence_layers_used) if unified.evidence_layers_used else 'none'}.",
                f"Top-candidate evidence completeness: {best.evidence_completeness:.3f}." if best else "Top-candidate evidence completeness: unavailable.",
                f"Missing top-candidate layers: {', '.join(missing_layers)}.",
                *_lcms_bridge_items(unified),
                "Missing evidence is reported explicitly rather than silently converted into a release claim.",
            ],
        ),
        EvidenceReportSection(
            title="Contradictions, ambiguity, and review triggers",
            items=[
                *contradiction_items,
                *(unified.ambiguity_alerts or ["No ambiguity alerts were generated."]),
                "Any contradiction or close top-candidate separation should trigger human review before release.",
            ],
        ),
        EvidenceReportSection(
            title="Provenance and chain of custody",
            items=[
                f"Raw data SHA-256: {request.raw_data_sha256 or 'not supplied'}.",
                f"Source files: {', '.join(request.source_files) if request.source_files else 'not supplied'}.",
                f"Request SHA-256: {provenance.get('request_sha256')}.",
                f"Unified evidence SHA-256: {provenance.get('unified_result_sha256')}.",
                f"Processing history SHA-256: {provenance.get('processing_history_sha256')}.",
                f"Report payload SHA-256: {provenance.get('report_sha256', 'pending')}.",
                "Raw spectral data should remain immutable; processing and interpretation are separate metadata.",
            ],
        ),
        EvidenceReportSection(
            title="Processing history",
            items=request.processing_history
            or [
                "No processing history was supplied.",
                "Recommended: include raw upload hash, FT/phase/baseline parameters, referencing, peak picking, integration, and manual edits.",
            ],
        ),
        EvidenceReportSection(
            title="Human approval and HITL gate",
            items=[
                f"Human approval required: {'yes' if request.require_human_approval else 'no'}.",
                f"Review status: {request.review_status or 'not reviewed'}.",
                f"Prepared by: {request.prepared_by or 'not supplied'}.",
                f"Reviewer: {request.reviewer_name or 'not supplied'}.",
                f"Reviewer comment: {request.reviewer_comment or 'not supplied'}.",
            ],
        ),
        EvidenceReportSection(
            title="Scientific and regulatory limitations",
            items=[
                "NMR evidence supports connectivity and stereochemical reasoning, but ambiguous or overlapping spectra can still require orthogonal confirmation.",
                "HRMS exact mass constrains formula and candidate plausibility, but exact mass alone does not prove connectivity or stereochemistry.",
                "MS/MS fragmentation evidence is supportive and may be instrument-, collision-energy-, and adduct-dependent.",
                "LC-MS feature-family consensus supports chromatographic feature provenance, isotope/adduct review, and precursor triage, but does not prove structure by itself.",
                "This report is suitable as an audit-ready internal record only after reviewer approval and local quality-system validation.",
            ],
        ),
    ]


def render_structure_elucidation_report_html(report: StructureElucidationReportResult) -> str:
    section_html = "".join(
        f"<section class='card'><h2>{html_escape(section.title)}</h2><ul>"
        + "".join(f"<li>{html_escape(item)}</li>" for item in section.items)
        + "</ul></section>"
        for section in report.sections
    )
    candidate_rows = "".join(
        "<tr>"
        f"<td>{item.rank}</td>"
        f"<td><strong>{html_escape(item.name or item.smiles)}</strong><br><span class='muted'>{html_escape(item.smiles)}</span></td>"
        f"<td>{html_escape(item.formula or 'not assigned')}</td>"
        f"<td>{item.confidence_score:.3f}</td>"
        f"<td>{html_escape(item.confidence_band)}</td>"
        f"<td>{item.agreement_count}</td>"
        f"<td>{item.contradiction_count}</td>"
        f"<td>{html_escape(item.label)}</td>"
        "</tr>"
        for item in report.ranked_candidates
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_escape(report.report_title)}</title>
  <style>
    :root{{color-scheme:light;--ink:#172033;--muted:#5d6b82;--line:#dce2ee;--card:#fff;--bg:#f6f8fb}}
    body{{font-family:Arial,Helvetica,sans-serif;max-width:1080px;margin:0 auto;padding:2rem 1rem;background:var(--bg);color:var(--ink)}}
    h1,h2{{margin:.1rem 0 .7rem}} .card{{border:1px solid var(--line);border-radius:8px;padding:1rem;margin:0 0 1rem;background:var(--card)}}
    .muted{{color:var(--muted)}} .badge{{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:.25rem .6rem;background:#fff}}
    table{{width:100%;border-collapse:collapse;background:#fff}} th,td{{padding:.55rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.75rem}}
    @media print{{body{{background:white}} .card{{break-inside:avoid}}}}
  </style>
</head>
<body>
  <h1>{html_escape(report.report_title)}</h1>
  <p class="muted">Generated {html_escape(report.generated_at.isoformat())} - Report ID {html_escape(report.report_id)}</p>
  <section class="card">
    <div class="grid">
      <div><strong>Status</strong><br><span class="badge">{html_escape(report.status)}</span></div>
      <div><strong>Release gate</strong><br><span class="badge">{html_escape(report.release_gate)}</span></div>
      <div><strong>Sample</strong><br>{html_escape(report.sample_id or 'not supplied')}</div>
      <div><strong>Project</strong><br>{html_escape(report.project_name or 'not supplied')}</div>
    </div>
  </section>
  <section class="card">
    <h2>Ranked candidates</h2>
    <table>
      <thead><tr><th>Rank</th><th>Candidate</th><th>Formula</th><th>Confidence</th><th>Band</th><th>Agreement</th><th>Contradictions</th><th>Status</th></tr></thead>
      <tbody>{candidate_rows or "<tr><td colspan='8'>No candidates reported.</td></tr>"}</tbody>
    </table>
  </section>
  {section_html}
</body>
</html>"""


def compose_structure_elucidation_report(
    request: StructureElucidationReportRequest,
) -> StructureElucidationReportResult:
    if request.unified_confidence_result is None and request.unified_confidence_request is None:
        raise StructureElucidationReportError("Provide either unified_confidence_result or unified_confidence_request.")

    try:
        unified = request.unified_confidence_result or build_unified_candidate_confidence(
            request.unified_confidence_request  # type: ignore[arg-type]
        )
    except UnifiedConfidenceError:
        raise
    except Exception as exc:
        raise StructureElucidationReportError(str(exc)) from exc

    ranked = [_candidate_summary(item) for item in unified.ranked_candidates]
    best = _candidate_summary(unified.best_candidate) if unified.best_candidate else (ranked[0] if ranked else None)
    status, release_gate = _pick_status(request, unified, best)
    generated_at = datetime.now(UTC)

    request_payload = request.model_dump(mode="json", exclude={"unified_confidence_result"})
    unified_payload = unified.model_dump(mode="json")
    processing_history_payload = {
        "source_files": request.source_files,
        "processing_history": request.processing_history,
        "raw_data_sha256": request.raw_data_sha256,
    }
    provenance: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "request_sha256": _sha256_text(_canonical_json(request_payload)),
        "unified_result_sha256": _sha256_text(_canonical_json(unified_payload)),
        "processing_history_sha256": _sha256_text(_canonical_json(processing_history_payload)),
        "raw_data_sha256": request.raw_data_sha256,
        "source_files": list(request.source_files),
        "report_schema_version": "week34.1",
    }

    sections = _report_sections(
        request=request,
        unified=unified,
        best=best,
        ranked=ranked,
        status=status,
        release_gate=release_gate,
        provenance=provenance,
    )
    human_review_approved = request.review_status == "approved" and release_gate == "approved_for_release"
    notes = list(unified.notes)
    if request.requestor_notes:
        notes.append(f"Requestor notes: {request.requestor_notes}")
    if request.require_human_approval and not human_review_approved:
        notes.append("Human approval is required before this report should be treated as release-ready.")
    if release_gate == "blocked_by_contradictions":
        notes.append("Report is blocked because at least one contradiction must be resolved.")

    report_payload: dict[str, Any] = {
        "report_title": request.report_title,
        "sample_id": request.sample_id or unified.sample_id,
        "project_name": request.project_name,
        "prepared_by": request.prepared_by,
        "reviewer_name": request.reviewer_name,
        "review_status": request.review_status,
        "intended_use": request.intended_use,
        "status": status,
        "release_gate": release_gate,
        "best_candidate": best.model_dump(mode="json") if best else None,
        "ranked_candidates": [item.model_dump(mode="json") for item in ranked],
        "evidence_layers_used": list(unified.evidence_layers_used),
        "global_contradictions": list(unified.global_contradictions),
        "ambiguity_alerts": list(unified.ambiguity_alerts),
        "warnings": list(unified.warnings),
        "notes": notes,
        "provenance": dict(provenance),
        "sections": [section.model_dump(mode="json") for section in sections],
        "generated_at": generated_at.isoformat(),
    }
    report_sha256 = _sha256_text(_canonical_json(report_payload))
    provenance["report_sha256"] = report_sha256
    report_id = f"SER-{report_sha256[:12].upper()}"
    report_payload["report_id"] = report_id
    report_payload["provenance"] = dict(provenance)

    result = StructureElucidationReportResult(
        report_id=report_id,
        generated_at=generated_at,
        report_title=request.report_title,
        sample_id=request.sample_id or unified.sample_id,
        project_name=request.project_name,
        prepared_by=request.prepared_by,
        reviewer_name=request.reviewer_name,
        review_status=request.review_status,
        reviewer_comment=request.reviewer_comment,
        intended_use=request.intended_use,
        status=status,
        release_gate=release_gate,
        human_review_required=request.require_human_approval,
        human_review_approved=human_review_approved,
        best_candidate=best,
        ranked_candidates=ranked,
        selected_adduct=unified.selected_adduct,
        evidence_layers_used=list(unified.evidence_layers_used),
        evidence_completeness=best.evidence_completeness if best else 0.0,
        agreement_count=best.agreement_count if best else 0,
        contradiction_count=len(unified.global_contradictions) + (best.contradiction_count if best else 0),
        global_contradictions=list(unified.global_contradictions),
        ambiguity_alerts=list(unified.ambiguity_alerts),
        warnings=list(unified.warnings),
        notes=notes,
        provenance=provenance,
        sections=sections,
        json_report=report_payload,
    )
    html_report = render_structure_elucidation_report_html(result)
    html_report_sha256 = _sha256_text(html_report)
    result.html_report = html_report
    result.provenance["html_report_sha256"] = html_report_sha256
    result.json_report["html_report_sha256"] = html_report_sha256
    result.json_report["provenance"] = dict(result.provenance)
    return result
