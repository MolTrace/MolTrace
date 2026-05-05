from nmrcheck.models import (
    CandidateInput,
    StructureElucidationReportRequest,
    UnifiedCandidateConfidenceItem,
    UnifiedCandidateConfidenceRequest,
    UnifiedCandidateConfidenceResult,
    UnifiedEvidenceLayerScore,
)
from nmrcheck.regulatory_report import compose_structure_elucidation_report


def _layer(layer="hrms_exact_mass", score=0.96):
    return UnifiedEvidenceLayerScore(
        layer=layer,
        label=layer.replace("_", " "),
        used=True,
        score=score,
        weight=0.2,
        status="strong_agreement",
        agreement=True,
        contradiction=False,
        evidence_count=1,
        evidence_summary=[f"{layer} supports candidate"],
    )


def _candidate(score=0.91, contradictions=None, label="high_confidence_candidate", band="high"):
    contradictions = contradictions or []
    return UnifiedCandidateConfidenceItem(
        rank=1,
        name="Ethanol",
        role="proposed",
        smiles="CCO",
        formula="C2H6O",
        exact_mass=46.041865,
        label=label,
        confidence_band=band,
        confidence_score=score,
        raw_weighted_score=score,
        evidence_completeness=0.86,
        agreement_count=3,
        contradiction_count=len(contradictions),
        missing_layers=["fragmentation_tree"],
        layers=[_layer("predicted_nmr", 0.9), _layer("hrms_exact_mass", 0.99), _layer("msms_annotation", 0.84)],
        layer_scores={"predicted_nmr": 0.9, "hrms_exact_mass": 0.99, "msms_annotation": 0.84},
        evidence_summary=["Predicted NMR supports ethanol.", "HRMS exact mass supports C2H6O."],
        contradictions=contradictions,
    )


def _unified(candidate=None, global_contradictions=None, layers=None):
    candidate = candidate or _candidate()
    return UnifiedCandidateConfidenceResult(
        sample_id="sample-34",
        solvent="CDCl3",
        selected_adduct="[M+H]+",
        candidate_count=1,
        best_candidate=candidate,
        ranked_candidates=[candidate],
        evidence_layers_used=layers if layers is not None else ["predicted_nmr", "hrms_exact_mass", "msms_annotation"],
        global_contradictions=global_contradictions or [],
        ambiguity_alerts=[],
        notes=["Unified confidence completed."],
        warnings=[],
    )


def test_report_requires_human_review_by_default_from_unified_result():
    result = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            sample_id="sample-34",
            project_name="Week 34 Test",
            prepared_by="Analyst",
            raw_data_sha256="a" * 64,
            source_files=["sample.zip"],
            processing_history=["Raw data preserved immutable", "Unified confidence generated"],
            unified_confidence_result=_unified(),
        )
    )
    assert result.report_id.startswith("SER-")
    assert result.status == "draft_requires_review"
    assert result.release_gate == "requires_human_review"
    assert result.best_candidate is not None
    assert result.best_candidate.smiles == "CCO"
    assert result.provenance["report_sha256"]
    assert result.provenance["request_sha256"]
    assert result.provenance["unified_result_sha256"]
    assert result.provenance["html_report_sha256"]
    assert "Human approval" in " ".join(section.title for section in result.sections)
    assert "Regulatory-ready" in result.html_report


def test_report_can_run_from_unified_confidence_request():
    result = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            unified_confidence_request=UnifiedCandidateConfidenceRequest(
                candidates=[CandidateInput(name="methanol", smiles="CO"), CandidateInput(name="ethanol", smiles="CCO")],
                hrms_observed_mz=47.04914,
                hrms_adduct="[M+H]+",
            )
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert "HRMS exact mass" in result.evidence_layers_used


def test_approved_report_can_be_released_when_no_contradictions():
    result = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            review_status="approved",
            reviewer_name="QA reviewer",
            reviewer_comment="Evidence reviewed.",
            unified_confidence_result=_unified(),
        )
    )
    assert result.status == "approved_for_release"
    assert result.release_gate == "approved_for_release"
    assert result.human_review_approved is True


def test_contradictions_block_release_even_if_approved():
    result = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            review_status="approved",
            reviewer_name="QA reviewer",
            unified_confidence_result=_unified(
                candidate=_candidate(
                    contradictions=["MS/MS loss contradicts candidate chemistry."],
                    label="conflicting_evidence",
                    band="conflicting",
                )
            ),
        )
    )
    assert result.status == "blocked_by_contradictions"
    assert result.release_gate == "blocked_by_contradictions"
    assert result.human_review_approved is False
    assert result.contradiction_count >= 1


def test_missing_evidence_is_marked_insufficient():
    candidate = _candidate(score=0.2, label="insufficient_evidence", band="insufficient")
    result = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            require_human_approval=False,
            unified_confidence_result=_unified(candidate=candidate, layers=[]),
        )
    )
    assert result.status == "insufficient_evidence"
    assert result.release_gate == "insufficient_evidence"


def test_html_escapes_user_supplied_fields():
    result = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            report_title="<script>alert('x')</script>",
            project_name="<b>Project</b>",
            prepared_by="<img src=x>",
            unified_confidence_result=_unified(),
        )
    )
    assert "<script>alert" not in result.html_report
    assert "&lt;script&gt;" in result.html_report
    assert "<b>Project</b>" not in result.html_report
