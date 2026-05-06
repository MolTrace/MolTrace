from pathlib import Path


def _web() -> str:
    return Path("src/nmrcheck/web.py").read_text()


def test_regulatory_report_ui_is_after_unified_before_spectrum_upload():
    web = _web()
    unified_idx = web.index("Unified Candidate Confidence Engine")
    report_idx = web.index("Regulatory-ready Structure Elucidation Report Composer")
    spectrum_idx = web.index("Processed spectrum upload")
    assert unified_idx < report_idx < spectrum_idx
    assert "structureReportTitle" in web
    assert "structureReportRawHash" in web
    assert "structureReportProcessingHistory" in web
    assert "structureReportBox" in web
    assert "/reports/structure-elucidation/compose/evidence" in web


def test_regulatory_report_ui_has_download_and_render_functions():
    web = _web()
    assert "function renderStructureReport" in web
    assert "function runStructureReportComposer" in web
    assert "function downloadStructureReportJson" in web
    assert "function downloadStructureReportHtml" in web
    assert "Copy unified inputs" in web


def test_regulatory_report_ui_does_not_replace_unified_confidence():
    web = _web()
    assert "function runUnifiedCandidateConfidence" in web
    assert "function unifiedConfidenceFormData" in web
    assert "state.latestUnifiedConfidence" in web
    assert "state.latestStructureReport" in web
