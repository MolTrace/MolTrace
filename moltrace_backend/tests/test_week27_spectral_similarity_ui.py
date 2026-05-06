from __future__ import annotations

from pathlib import Path


def test_spectral_similarity_ui_is_after_candidate_comparison_before_spectrum_upload() -> None:
    web = Path("src/nmrcheck/web.py").read_text()
    candidate_idx = web.index("Candidate Comparison Engine")
    similarity_idx = web.index("Spectral Similarity Scoring")
    spectrum_idx = web.index("Processed spectrum upload")

    assert candidate_idx < similarity_idx < spectrum_idx
    assert 'id="spectralSimilarityPanel"' in web
    assert "spectralSimilarityBox" in web
    assert "similarityReference1H" in web
    assert "similarityReference13C" in web
    assert "similarityReference2DFile" in web
    assert "similarity2DExperiment" in web
    assert "/similarity/score/evidence" in web
    assert "Similarity is a confidence aid" in web


def test_spectral_similarity_ui_uses_current_observed_spectra_read_only() -> None:
    web = Path("src/nmrcheck/web.py").read_text()
    start = web.index("async function scoreSpectralSimilarity()")
    end = web.index("function clearSpectralSimilarity()", start)
    body = web[start:end]

    assert 'const observed1H = el("nmrText") ? el("nmrText").value.trim() : "";' in body
    assert 'const observed13C = el("carbon13Text") ? el("carbon13Text").value.trim() : "";' in body
    assert 'formData.append("observed_proton_text", observed1H);' in body
    assert 'formData.append("observed_carbon13_text", observed13C);' in body
    assert 'formData.append("reference_proton_text", reference1H);' in body
    assert 'formData.append("reference_carbon13_text", reference13C);' in body
    assert 'formData.append("observed_nmr2d_file", observed2D);' in body
    assert 'formData.append("reference_nmr2d_file", reference2D);' in body
    assert 'el("nmrText").value =' not in body
    assert 'el("carbon13Text").value =' not in body
    assert 'el("nmr2dFile").value =' not in body
