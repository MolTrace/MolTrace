from pathlib import Path


def _web() -> str:
    return Path("src/nmrcheck/web.py").read_text()


def test_unified_confidence_ui_is_after_fragmentation_tree_before_spectrum_upload():
    web = _web()
    frag_idx = web.index("MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning")
    unified_idx = web.index("Unified Candidate Confidence Engine")
    upload_idx = web.index("Processed spectrum upload")
    assert frag_idx < unified_idx < upload_idx
    assert "unifiedCandidateList" in web
    assert "unifiedHrmsMz" in web
    assert "unifiedMS1PeakList" in web
    assert "unifiedMSMSPeakList" in web
    assert "unifiedConfidenceBox" in web
    assert "/confidence/candidates/unified/evidence" in web


def test_unified_confidence_ui_has_copy_and_clear_controls():
    web = _web()
    assert "function copyInputsToUnifiedConfidence" in web
    assert "function runUnifiedCandidateConfidence" in web
    assert "function clearUnifiedCandidateConfidence" in web
    assert "state.latestUnifiedConfidence" in web


def test_unified_confidence_ui_preserves_existing_inputs_read_only():
    web = _web()
    form_start = web.index("function unifiedConfidenceFormData")
    form_end = web.index("async function runUnifiedCandidateConfidence", form_start)
    form_code = web[form_start:form_end]
    assert 'el("nmrText")?.value' in form_code
    assert 'el("carbon13Text")?.value' in form_code
    assert 'el("nmrText").value =' not in form_code
    assert 'el("carbon13Text").value =' not in form_code
