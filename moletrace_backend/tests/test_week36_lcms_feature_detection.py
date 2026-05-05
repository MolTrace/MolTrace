from nmrcheck.lcms_features import detect_lcms_features
from nmrcheck.models import LCMSFeatureDetectionRequest


def _clean_feature_text(coelution: bool = False) -> str:
    extra = "" if not coelution else """
ms1_001,1,0.00,59.04914,8,
ms1_002,1,0.10,59.04914,40,
ms1_003,1,0.20,59.04914,90,
ms1_004,1,0.30,59.04914,50,
ms1_005,1,0.40,59.04914,8,
"""
    if not coelution:
        extra = "ms1_003,1,0.20,59.04914,0.3,\n"
    return f"""scan_id,ms_level,rt_min,mz,intensity,precursor_mz
ms1_001,1,0.00,47.04914,10,
ms1_002,1,0.10,47.04914,55,
ms1_003,1,0.20,47.04914,100,
ms1_004,1,0.30,47.04914,50,
ms1_005,1,0.40,47.04914,12,
{extra}ms2_001,2,0.20,29.03858,100,47.04914
ms2_001,2,0.20,31.01839,25,47.04914
"""


def test_lcms_feature_detection_extracts_xic_peak_and_links_msms():
    result = detect_lcms_features(
        LCMSFeatureDetectionRequest(
            filename="ethanol_lcms.csv",
            source_text=_clean_feature_text(coelution=False),
            target_mz_text="47.04914",
            purity_rt_window_min=0.20,
        )
    )
    assert result.source_format == "processed_peak_table"
    assert result.scan_count == 6
    assert result.ms1_scan_count == 5
    assert result.ms2_scan_count == 1
    assert result.feature_count == 1
    feature = result.features[0]
    assert feature.label == "clean_feature"
    assert feature.apex_rt_min == 0.2
    assert feature.apex_intensity == 100
    assert feature.purity.label == "high_purity"
    assert feature.purity.purity_percent > 95
    assert feature.linked_msms_spectra[0].scan_id == "ms2_001"
    assert any(point.target_mz == 47.04914 for point in result.xic_points)
    assert result.file_sha256
    assert result.immutable_raw_data is True


def test_lcms_feature_detection_flags_coelution_by_peak_purity():
    result = detect_lcms_features(
        LCMSFeatureDetectionRequest(
            filename="coeluting_lcms.csv",
            source_text=_clean_feature_text(coelution=True),
            target_mz_text="47.04914",
            purity_rt_window_min=0.20,
        )
    )
    feature = result.features[0]
    assert feature.label == "possible_coelution"
    assert feature.purity.label in {"possible_coelution", "poor_peak_purity"}
    assert feature.purity.purity_percent < 90
    assert feature.purity.top_coeluting_ions
    assert abs(feature.purity.top_coeluting_ions[0].mz - 59.04914) < 0.0001
    assert result.coeluting_feature_count == 1
    assert any("coelution" in warning.lower() for warning in result.warnings)


def test_lcms_feature_detection_auto_selects_targets_from_ms1_when_missing():
    result = detect_lcms_features(
        LCMSFeatureDetectionRequest(
            filename="auto_targets.csv",
            source_text=_clean_feature_text(coelution=False),
            target_mz_text=None,
            max_features=3,
        )
    )
    assert result.target_count >= 1
    assert result.feature_count >= 1
    assert abs(result.best_feature.target_mz - 47.04914) < 0.001
    assert any("auto-selected" in warning for warning in result.warnings)


def test_lcms_feature_detection_unsupported_vendor_requires_conversion():
    try:
        detect_lcms_features(
            LCMSFeatureDetectionRequest(filename="sample.raw", source_format="unsupported_vendor", source_text="vendor bytes")
        )
    except Exception as exc:
        assert "Convert" in str(exc) or "conversion" in str(exc).lower()
    else:
        raise AssertionError("unsupported vendor input should not be parsed for features")
