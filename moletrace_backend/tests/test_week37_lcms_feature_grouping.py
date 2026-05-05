from nmrcheck.lcms_grouping import group_lcms_features
from nmrcheck.models import LCMSFeatureGroupingRequest, LCMSFeatureGroupingRunInput


def _sample_text(include_isotope: bool = False) -> str:
    isotope = "" if not include_isotope else """
s_ms1_001,1,0.00,48.05250,1,
s_ms1_002,1,0.10,48.05250,4,
s_ms1_003,1,0.20,48.05250,7,
s_ms1_004,1,0.30,48.05250,4,
s_ms1_005,1,0.40,48.05250,1,
"""
    return f"""scan_id,ms_level,rt_min,mz,intensity,precursor_mz
s_ms1_001,1,0.00,47.04914,10,
s_ms1_002,1,0.10,47.04914,70,
s_ms1_003,1,0.20,47.04914,140,
s_ms1_004,1,0.30,47.04914,65,
s_ms1_005,1,0.40,47.04914,12,
{isotope}s_ms2_001,2,0.20,29.03858,100,47.04914
"""


def _blank_text(high: bool = False) -> str:
    if high:
        peak = (8, 90, 9)
    else:
        peak = (2, 4, 3)
    return f"""scan_id,ms_level,rt_min,mz,intensity,precursor_mz
b_ms1_001,1,0.02,47.04914,{peak[0]},
b_ms1_002,1,0.12,47.04914,{peak[1]},
b_ms1_003,1,0.22,47.04914,{peak[2]},
"""


def test_lcms_feature_grouping_aligns_blank_and_subtracts_background():
    result = group_lcms_features(
        LCMSFeatureGroupingRequest(
            runs=[
                LCMSFeatureGroupingRunInput(run_id="sample", role="sample", source_text=_sample_text()),
                LCMSFeatureGroupingRunInput(run_id="blank", role="blank", source_text=_blank_text()),
            ],
            target_mz_text="47.04914",
            min_scans_per_feature=2,
            group_rt_tolerance_min=0.15,
        )
    )
    assert result.label == "ready_for_candidate_scoring"
    assert result.run_count == 2
    assert result.group_count == 1
    assert result.sample_enriched_group_count == 1
    assert result.background_group_count == 0
    group = result.groups[0]
    assert group.label == "sample_enriched_feature"
    assert group.sample_area > group.blank_area
    assert group.blank_subtracted_area > 0
    assert group.blank_ratio < 0.3
    blank_alignment = [x for x in result.alignment_summaries if x.run_id == "blank"][0]
    assert abs(blank_alignment.rt_shift_min) > 0.001
    assert result.feature_table_text.startswith("group_id,representative_mz")


def test_lcms_feature_grouping_flags_blank_like_features():
    result = group_lcms_features(
        LCMSFeatureGroupingRequest(
            runs=[
                LCMSFeatureGroupingRunInput(run_id="sample", role="sample", source_text=_sample_text()),
                LCMSFeatureGroupingRunInput(run_id="blank", role="blank", source_text=_blank_text(high=True)),
            ],
            target_mz_text="47.04914",
            min_scans_per_feature=1,
            blank_area_ratio_threshold=0.30,
        )
    )
    assert result.label == "review_background_before_scoring"
    assert result.background_group_count == 1
    assert result.groups[0].label == "blank_like_feature"
    assert result.groups[0].blank_ratio >= 0.3
    assert any("background" in warning.lower() or "blank" in warning.lower() for warning in result.warnings)


def test_lcms_feature_grouping_annotates_isotope_feature_family():
    result = group_lcms_features(
        LCMSFeatureGroupingRequest(
            runs=[LCMSFeatureGroupingRunInput(run_id="sample", role="sample", source_text=_sample_text(include_isotope=True))],
            target_mz_text="47.04914,48.05250",
            min_scans_per_feature=2,
            group_rt_tolerance_min=0.10,
            family_rt_tolerance_min=0.25,
        )
    )
    assert result.group_count >= 2
    assert result.relationship_count >= 2
    assert any(rel.relationship_type.startswith("isotope") for group in result.groups for rel in group.relationships)


def test_lcms_feature_grouping_requires_sample_run():
    try:
        group_lcms_features(
            LCMSFeatureGroupingRequest(
                runs=[LCMSFeatureGroupingRunInput(run_id="blank", role="blank", source_text=_blank_text())],
                target_mz_text="47.04914",
            )
        )
    except Exception as exc:
        assert "sample" in str(exc).lower()
    else:
        raise AssertionError("feature grouping should require at least one sample run")
