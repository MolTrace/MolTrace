from pathlib import Path


def test_fragmentation_tree_ui_placement_and_controls():
    web = Path("src/nmrcheck/web.py").read_text()
    msms_idx = web.index("Processed MS/MS Annotation Beta")
    tree_idx = web.index("MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning")
    spectrum_idx = web.index("Processed spectrum upload")
    assert msms_idx < tree_idx < spectrum_idx
    assert "fragTreePrecursorMz" in web
    assert "fragTreePeakList" in web
    assert "fragTreeCandidateList" in web
    assert "fragmentationTreeBox" in web
    assert "function renderFragmentationTree" in web
    assert "/ms/msms/fragmentation-tree/evidence" in web


def test_fragmentation_tree_ui_state_and_copy_helpers():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "latestFragmentationTree" in web
    assert "function copyMSMSToFragmentationTree" in web
    assert "function copyCandidatesToFragmentationTree" in web
    assert "function clearFragmentationTree" in web


def test_fragmentation_tree_ui_explains_human_review_boundary():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "final identity still requires HRMS, adduct/isotope evidence, MS/MS annotation, NMR, and human review" in web
    assert "use the LC-MS/MS import bridge to extract peak-list views from mzML/mzXML or source files" in web
