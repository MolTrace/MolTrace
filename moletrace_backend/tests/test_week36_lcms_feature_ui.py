from pathlib import Path


def test_lcms_feature_detection_ui_is_after_import_bridge_before_processed_spectrum_upload():
    web = Path("src/nmrcheck/web.py").read_text()
    import_idx = web.index("Raw LC-MS/MS mzML + Processed Peak Import Bridge")
    feature_idx = web.index("LC-MS Feature Detection + EIC/XIC + Peak Purity")
    upload_idx = web.index("Processed spectrum upload")
    assert import_idx < feature_idx < upload_idx
    assert "lcmsFeatureText" in web
    assert "lcmsFeatureTargets" in web
    assert "runLCMSFeatureDetection" in web
    assert "/ms/lcms/features/detect/evidence" in web
    assert "/ms/lcms/features/detect/upload" in web


def test_lcms_feature_detection_can_copy_to_ms_workflows_and_report():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "function copyLCMSFeatureToMSWorkflows" in web
    assert "function copyLCMSFeaturePurityToReport" in web
    assert "hrmsObservedMz" in web
    assert "msmsPrecursorMz" in web
    assert "structureReportProcessingHistory" in web
