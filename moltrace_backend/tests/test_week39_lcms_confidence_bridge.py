from nmrcheck.lcms_confidence_bridge import score_lcms_candidates_against_consensus
from nmrcheck.models import (
    CandidateInput,
    LCMSConsensusCandidateBridgeRequest,
    StructureElucidationReportRequest,
    UnifiedCandidateConfidenceRequest,
)
from nmrcheck.regulatory_report import compose_structure_elucidation_report
from nmrcheck.unified_confidence import build_unified_candidate_confidence


ETHANOL_FAMILY_TABLE = """family_id,anchor_group_id,anchor_mz,anchor_rt_min,label,consensus_score,promoted,relationship_count,member_count
F001,G001,47.049141,1.250000,moderate_confidence_feature_family,0.8300,true,2,3
"""


def test_lcms_bridge_scores_candidate_adduct_against_promoted_family():
    result = score_lcms_candidates_against_consensus(
        LCMSConsensusCandidateBridgeRequest(
            sample_id="week39-ethanol",
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
            lcms_family_table_text=ETHANOL_FAMILY_TABLE,
            adduct="[M+H]+",
        )
    )
    assert result.eligible_family_count == 1
    assert result.best_match is not None
    assert result.best_match.name == "ethanol"
    assert result.best_match.label == "matches_promoted_feature_family"
    assert result.best_match.score > 0.80
    methanol = next(match for match in result.matches if match.name == "methanol")
    assert methanol.contradiction is True
    assert "feature-family" in " ".join(result.notes)


def test_unified_confidence_uses_lcms_feature_family_layer_when_supplied():
    result = build_unified_candidate_confidence(
        UnifiedCandidateConfidenceRequest(
            sample_id="week39-unified",
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
            lcms_family_table_text=ETHANOL_FAMILY_TABLE,
            lcms_anchor_adduct="[M+H]+",
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert "LC-MS feature-family consensus" in result.evidence_layers_used
    lcms_layer = next(layer for layer in result.best_candidate.layers if layer.layer == "lcms_feature_family")
    assert lcms_layer.used is True
    assert lcms_layer.score is not None and lcms_layer.score > 0.80
    assert result.component_metadata["lcms_feature_family_bridge"]["eligible_family_count"] == 1


def test_structure_report_includes_lcms_bridge_provenance_section_items():
    report = compose_structure_elucidation_report(
        StructureElucidationReportRequest(
            sample_id="week39-report",
            processing_history=["Week 38 LC-MS consensus scored", "Week 39 LC-MS bridge added to unified confidence"],
            unified_confidence_request=UnifiedCandidateConfidenceRequest(
                sample_id="week39-report",
                candidates=[CandidateInput(name="ethanol", smiles="CCO")],
                lcms_family_table_text=ETHANOL_FAMILY_TABLE,
                lcms_anchor_adduct="[M+H]+",
            ),
        )
    )
    joined = "\n".join(item for section in report.sections for item in section.items)
    assert "LC-MS consensus bridge included" in joined
    assert "LC-MS bridge result SHA-256" in joined
    assert "LC-MS feature-family consensus" in report.html_report
