from __future__ import annotations

from pathlib import Path


def test_candidate_comparison_ui_is_after_2d_and_before_processed_spectrum() -> None:
    web = Path("src/nmrcheck/web.py").read_text()
    studio_idx = web.index("DEPT/APT + 2D NMR Evidence Studio")
    candidate_idx = web.index("Candidate Comparison Engine")
    spectrum_idx = web.index("Processed spectrum upload")

    assert studio_idx < candidate_idx < spectrum_idx
    assert 'id="candidateComparisonPanel"' in web
    assert 'id="candidateList"' in web
    assert 'id="candidateComparisonBox"' in web
    assert "compareCandidates()" in web
    assert "clearCandidateComparison()" in web
    assert "/candidates/compare/evidence" in web
    assert "This is evidence ranking, not final structure confirmation." in web


def test_candidate_ui_sends_current_evidence_layers_read_only() -> None:
    web = Path("src/nmrcheck/web.py").read_text()
    start = web.index("async function compareCandidates()")
    end = web.index("function clearCandidateComparison()", start)
    body = web[start:end]

    assert 'formData.append("proton_nmr_text", protonText);' in body
    assert 'formData.append("carbon13_text", carbonText);' in body
    assert 'formData.append("dept_apt_file", deptFile);' in body
    assert 'formData.append("dept_apt_experiment_type", deptExp);' in body
    assert 'formData.append("apt_positive", aptPositive || "CH_CH3");' in body
    assert 'formData.append("nmr2d_file", nmr2dFile);' in body
    assert 'formData.append("nmr2d_experiment_type", nmr2dExp);' in body
    assert "nmrText" in body
    assert "carbon13Text" in body
    assert "deptAptFile" in body
    assert "nmr2dFile" in body
    assert 'el("nmrText").value =' not in body
    assert 'el("carbon13Text").value =' not in body
    assert 'el("deptAptFile").value =' not in body
    assert 'el("nmr2dFile").value =' not in body
