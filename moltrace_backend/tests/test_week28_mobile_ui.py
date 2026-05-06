from pathlib import Path


def test_candidate_specific_predicted_nmr_ui_placement():
    web = Path("src/nmrcheck/web.py").read_text()
    similarity_idx = web.index("Spectral Similarity Scoring")
    predicted_idx = web.index("Candidate-specific Predicted NMR Matching")
    spectrum_idx = web.index("Processed spectrum upload")
    assert similarity_idx < predicted_idx < spectrum_idx
    assert "predictedCandidateList" in web
    assert "predictedNMRMatchBox" in web
    assert "/prediction/nmr/match/evidence" in web


def test_mobile_responsive_css_is_present():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "@media (max-width: 760px)" in web
    assert ".nav-list { display:flex" in web
    assert "table { display:block; overflow-x:auto" in web
    assert "button, input, select, textarea { font-size:16px;" in web


def test_prediction_ui_uses_current_evidence_read_only():
    web = Path("src/nmrcheck/web.py").read_text()
    assert 'const protonText = el("nmrText") ? el("nmrText").value.trim() : "";' in web
    assert 'const carbonText = el("carbon13Text") ? el("carbon13Text").value.trim() : "";' in web
    assert 'formData.append("observed_proton_text", protonText);' in web
    assert 'formData.append("observed_carbon13_text", carbonText);' in web
    assert 'formData.append("observed_nmr2d_file", nmr2dFile);' in web
