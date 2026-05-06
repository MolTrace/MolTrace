from pathlib import Path


def test_hrms_ui_is_after_predicted_nmr_before_spectrum_upload():
    web = Path("src/nmrcheck/web.py").read_text()
    predicted_idx = web.index("Candidate-specific Predicted NMR Matching")
    hrms_idx = web.index("HRMS / Exact-Mass Constraint Layer")
    spectrum_idx = web.index("Processed spectrum upload")
    assert predicted_idx < hrms_idx < spectrum_idx
    assert "hrmsObservedMz" in web
    assert "hrmsAdduct" in web
    assert "hrmsCandidateList" in web
    assert "hrmsMatchBox" in web
    assert "/ms/hrms/candidates/match/evidence" in web
    assert "/ms/hrms/formulas/search" in web


def test_hrms_ui_can_copy_candidate_list_and_clear_results():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "function copyCandidateListToHRMS" in web
    assert "function clearHRMSMatch" in web
    assert 'el("hrmsCandidateList").value = el("candidateList").value;' in web


def test_hrms_ui_states_human_review_and_no_connectivity_claim():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "does not prove connectivity or stereochemistry" in web
    assert "NMR evidence inputs are not modified by HRMS matching" in web
