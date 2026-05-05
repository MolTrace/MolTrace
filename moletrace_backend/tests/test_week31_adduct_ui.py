from pathlib import Path


def test_adduct_ui_is_between_hrms_and_msms():
    web = Path("src/nmrcheck/web.py").read_text()
    hrms_idx = web.index("HRMS / Exact-Mass Constraint Layer")
    adduct_idx = web.index("Adduct + Isotope Pattern Inference")
    msms_idx = web.index("Processed MS/MS Annotation Beta")
    assert hrms_idx < adduct_idx < msms_idx
    assert "adductTargetMz" in web
    assert "adductIonMode" in web
    assert "adductIsotopeToleranceDa" in web
    assert "adductPeakList" in web
    assert "adductFormulaSearch" in web
    assert "adductInferenceBox" in web
    assert "/ms/adducts/infer/evidence" in web
    assert "function renderAdductInference" in web


def test_adduct_ui_has_handoff_helpers():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "copyHRMSToAdductInference" in web
    assert "applyBestAdductInference" in web
    assert "clearAdductInference" in web


def test_adduct_ui_explains_triage_and_raw_file_boundary():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "does not prove identity" in web
    assert "use the LC-MS/MS import bridge for mzML/mzXML or source-file imports" in web
