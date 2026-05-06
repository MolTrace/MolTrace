from pathlib import Path


def test_lcms_import_bridge_ui_is_after_report_before_processed_spectrum_upload():
    web = Path("src/nmrcheck/web.py").read_text()
    report_idx = web.index("Regulatory-ready Structure Elucidation Report Composer")
    lcms_idx = web.index("Raw LC-MS/MS mzML + Processed Peak Import Bridge")
    upload_idx = web.index("Processed spectrum upload")
    assert report_idx < lcms_idx < upload_idx
    assert "lcmsImportFile" in web
    assert "lcmsImportText" in web
    assert "runLCMSImportBridge" in web
    assert "/ms/lcms/import/bridge/evidence" in web
    assert "/ms/lcms/import/bridge/upload" in web


def test_lcms_import_bridge_can_copy_to_ms_workflows_and_report():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "function copyLCMSToMSWorkflows" in web
    assert "function copyLCMSHashToReport" in web
    assert "adductPeakList" in web
    assert "msmsPeakList" in web
    assert "fragTreePeakList" in web
    assert "structureReportRawHash" in web
