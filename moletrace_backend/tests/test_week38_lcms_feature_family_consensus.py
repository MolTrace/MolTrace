from nmrcheck.lcms_consensus import score_lcms_feature_family_consensus
from nmrcheck.models import (
    LCMSFeatureFamilyConsensusRequest,
    LCMSFeatureGroup,
    LCMSFeatureGroupMember,
)


def _member(group_id: str, mz: float, rt: float, area: float, *, msms: int = 0, purity: float = 96.0) -> LCMSFeatureGroupMember:
    return LCMSFeatureGroupMember(
        run_id="sample",
        role="sample",
        source_format="processed_peak_table",
        file_sha256="abc123",
        feature_id=f"{group_id}_sample",
        target_mz=mz,
        observed_mz=mz,
        raw_apex_rt_min=rt,
        aligned_apex_rt_min=rt,
        rt_shift_applied_min=0.0,
        area=area,
        apex_intensity=area,
        purity_percent=purity,
        purity_label="high_purity" if purity >= 90 else "possible_coelution",
        feature_label="clean_feature" if purity >= 90 else "possible_coelution",
        linked_msms_count=msms,
        warnings=[],
    )


def _group(group_id: str, mz: float, rt: float, area: float, *, blank: float = 0.0, msms: int = 0, label: str = "sample_enriched_feature", purity: float = 96.0) -> LCMSFeatureGroup:
    return LCMSFeatureGroup(
        group_id=group_id,
        representative_mz=mz,
        representative_rt_min=rt,
        label=label,  # type: ignore[arg-type]
        member_count=1,
        roles_present=["sample"],
        sample_area=area,
        blank_area=blank,
        blank_ratio=(blank / area) if area else 0.0,
        blank_subtracted_area=max(area - blank, 0.0),
        members=[_member(group_id, mz, rt, area, msms=msms, purity=purity)],
        relationships=[],
        evidence_summary=[],
        warnings=[],
    )


def test_lcms_feature_family_consensus_promotes_isotope_adduct_loss_family():
    anchor_mz = 301.200000
    groups = [
        _group("G001", anchor_mz, 5.0, 1000.0, blank=10.0, msms=1),
        _group("G002", anchor_mz + 1.003355, 5.01, 220.0, blank=0.0),
        _group("G003", anchor_mz + 2.006710, 5.01, 28.0, blank=0.0),
        _group("G004", anchor_mz + 21.981943, 5.02, 85.0, blank=0.0),
        _group("G005", anchor_mz - 18.010565, 5.00, 65.0, blank=0.0),
    ]
    result = score_lcms_feature_family_consensus(
        LCMSFeatureFamilyConsensusRequest(
            groups=groups,
            formula="C20H30O",
            anchor_group_id="G001",
            min_consensus_score_to_promote=0.60,
        )
    )
    assert result.label == "ready_for_candidate_scoring"
    assert result.promoted_family_count == 1
    assert result.best_family is not None
    assert result.best_family.promoted_for_candidate_scoring is True
    assert result.best_family.relationship_count >= 4
    assert result.best_family.consensus_score >= 0.60
    assert any(rel.relationship_type == "isotope_m_plus_1_z1" for rel in result.best_family.relationships)
    assert any(rel.relationship_type == "adduct_pair_na_h" for rel in result.best_family.relationships)
    assert any(layer.layer == "msms_linkage" and layer.score == 1.0 for layer in result.best_family.layer_scores)
    assert result.family_table_text.startswith("family_id,anchor_group_id")


def test_lcms_feature_family_consensus_flags_blank_like_anchor():
    groups = [
        _group("G001", 301.2, 5.0, 1000.0, blank=500.0, label="blank_like_feature"),
        _group("G002", 302.203355, 5.0, 100.0, blank=0.0),
    ]
    result = score_lcms_feature_family_consensus(
        LCMSFeatureFamilyConsensusRequest(
            groups=groups,
            anchor_group_id="G001",
            include_background_groups=True,
            require_sample_enrichment=False,
            formula="C10H12O3",
        )
    )
    assert result.label == "review_conflicting_families"
    assert result.conflicting_family_count == 1
    assert result.best_family is not None
    assert result.best_family.label == "conflicting_or_background_family"
    assert any(layer.layer == "blank_subtraction" and layer.contradiction for layer in result.best_family.layer_scores)


def test_lcms_feature_family_consensus_accepts_week37_feature_table_text():
    table = """group_id,representative_mz,aligned_rt_min,label,sample_area,blank_area,blank_ratio,blank_subtracted_area,member_count,roles_present
G001,301.200000,5.000000,sample_enriched_feature,1000.000000,0.000000,0.000000,1000.000000,1,sample
G002,302.203355,5.010000,sample_enriched_feature,220.000000,0.000000,0.000000,220.000000,1,sample
"""
    result = score_lcms_feature_family_consensus(
        LCMSFeatureFamilyConsensusRequest(
            feature_table_text=table,
            formula="C20H30O",
            min_consensus_score_to_promote=0.3,
        )
    )
    assert result.input_group_count == 2
    assert result.family_count >= 1
    assert result.best_family is not None
    assert any(rel.relationship_type == "isotope_m_plus_1_z1" for rel in result.best_family.relationships)
    assert any("No run-level purity" in warning for warning in result.best_family.warnings)


def test_lcms_feature_family_consensus_requires_groups():
    try:
        score_lcms_feature_family_consensus(LCMSFeatureFamilyConsensusRequest())
    except Exception as exc:
        assert "grouping" in str(exc).lower() or "feature" in str(exc).lower()
    else:
        raise AssertionError("consensus should require grouped LC-MS features")
