from pathlib import Path


def test_lcms_consensus_ui_is_between_grouping_and_processed_upload():
    web = Path("src/nmrcheck/web.py").read_text()
    grouping_idx = web.index("LC-MS Feature Grouping + Blank Subtraction + RT Alignment")
    consensus_idx = web.index("LC-MS Isotope/Adduct Consensus + Feature-Family Confidence")
    upload_idx = web.index("Processed spectrum upload")
    assert grouping_idx < consensus_idx < upload_idx
    assert "lcmsConsensusFeatureTable" in web
    assert "runLCMSFeatureConsensus" in web
    assert "/ms/lcms/features/consensus" in web
    assert "copyLCMSConsensusToReport" in web


def test_lcms_consensus_ui_has_family_scoring_controls():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "lcmsConsensusFormula" in web
    assert "lcmsConsensusAdduct" in web
    assert "lcmsConsensusMinScore" in web
    assert "lcmsConsensusBlankRatio" in web
    assert "family_table_text" in web
