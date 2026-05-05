from pathlib import Path


def test_lcms_feature_grouping_ui_is_after_feature_detection_before_processed_upload():
    web = Path("src/nmrcheck/web.py").read_text()
    feature_idx = web.index("LC-MS Feature Detection + EIC/XIC + Peak Purity")
    grouping_idx = web.index("LC-MS Feature Grouping + Blank Subtraction + RT Alignment")
    upload_idx = web.index("Processed spectrum upload")
    assert feature_idx < grouping_idx < upload_idx
    assert "lcmsGroupSampleText" in web
    assert "lcmsGroupBlankText" in web
    assert "runLCMSFeatureGrouping" in web
    assert "/ms/lcms/features/group/evidence" in web
    assert "copyLCMSFeatureGroupingToReport" in web


def test_lcms_feature_grouping_ui_has_blank_subtraction_controls():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "lcmsGroupBlankRatio" in web
    assert "lcmsGroupBackgroundRatio" in web
    assert "lcmsGroupRtTol" in web
    assert "lcmsGroupAnchorMz" in web
    assert "feature_table_text" in web
