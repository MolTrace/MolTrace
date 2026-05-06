from pathlib import Path


def test_msms_ui_is_after_hrms_before_processed_spectrum_upload():
    web = Path("src/nmrcheck/web.py").read_text()
    hrms_idx = web.index("HRMS / Exact-Mass Constraint Layer")
    msms_idx = web.index("Processed MS/MS Annotation Beta")
    spectrum_idx = web.index("Processed spectrum upload")
    assert hrms_idx < msms_idx < spectrum_idx
    assert "msmsPrecursorMz" in web
    assert "msmsPeakList" in web
    assert "msmsCandidateList" in web
    assert "msmsAnnotationBox" in web
    assert "/ms/msms/annotate/evidence" in web


def test_msms_ui_has_copy_and_clear_functions():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "function copyCandidatesToMSMS" in web
    assert "function copyHRMSToMSMS" in web
    assert "function clearMSMSAnnotation" in web
    assert "function renderMSMSAnnotation" in web


def test_msms_ui_states_processed_only_and_review_needed():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "Use processed centroid peak tables only" in web
    assert "do not prove complete connectivity or stereochemistry" in web
    assert "does not perform raw LC-MS/MS import" in web
