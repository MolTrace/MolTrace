from pathlib import Path


def test_week39_unified_ui_exposes_lcms_consensus_bridge_controls():
    web = Path("src/nmrcheck/web.py").read_text()
    assert "LC-MS consensus bridge" in web
    assert "unifiedUseLCMSConsensus" in web
    assert "unifiedLCMSMinScore" in web
    assert "lcms_family_table_text" in web
    assert "LC-MS feature-family consensus" in web


def test_week39_unified_bridge_endpoint_is_registered():
    api = Path("src/nmrcheck/api.py").read_text()
    assert "/confidence/candidates/lcms-consensus-bridge" in api
    assert "/confidence/candidates/unified/lcms-bridge" in api
    assert "confidence.candidates.unified.lcms_bridge" in api
