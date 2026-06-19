"""Tests for Repho R6 (engine slice): predictive process-safety screening.

Pure-engine tests (no app/client fixtures) so they are independent of the API surface.
The store/route wiring + the blocking safety gate in the closed loop land in a later slice.
"""

from rdkit import Chem, RDLogger

from nmrcheck import reaction_safety as rs

# Invalid-SMILES tests intentionally feed RDKit a bad string; silence its parse-error chatter.
RDLogger.DisableLog("rdApp.*")


def test_all_hazard_smarts_compile():
    bad = [key for (key, _l, smarts, _s, _n) in rs._ENERGETIC_GROUPS if Chem.MolFromSmarts(smarts) is None]
    assert bad == [], f"invalid SMARTS for: {bad}"
    assert len(rs._ENERGETIC_GROUPS) >= 14


def _keys(smiles: str) -> list[str]:
    return [f["key"] for f in rs.screen_smiles(smiles)["flagged_groups"]]


def test_azide_is_critical():
    r = rs.screen_smiles("CCN=[N+]=[N-]")
    assert "azide" in _keys("CCN=[N+]=[N-]")
    assert r["overall_risk"] == "critical"
    assert r["requires_expert_review"] is True


def test_peroxide_is_critical():
    assert "organic_peroxide" in _keys("CC(=O)OO")
    assert rs.screen_smiles("CC(=O)OO")["overall_risk"] == "critical"


def test_nitro_is_high_without_false_n_oxide():
    keys = _keys("c1ccccc1[N+](=O)[O-]")
    assert "nitro" in keys
    assert "n_oxide" not in keys  # a nitro N must not be mis-flagged as an amine N-oxide
    assert rs.screen_smiles("c1ccccc1[N+](=O)[O-]")["overall_risk"] == "high"


def test_polynitro_escalates_to_critical():
    tnt = rs.screen_smiles("Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]")
    nitro = next(f for f in tnt["flagged_groups"] if f["key"] == "nitro")
    assert nitro["count"] == 3
    assert nitro["severity"] == "critical"
    assert tnt["overall_risk"] == "critical"


def test_amine_and_pyridine_n_oxide_flagged():
    assert "n_oxide" in _keys("C[N+](C)(C)[O-]")  # trimethylamine N-oxide
    assert "n_oxide" in _keys("[O-][n+]1ccccc1")  # pyridine N-oxide


def test_benign_structure_clears():
    r = rs.screen_smiles("CCO")  # ethanol
    assert r["flagged_groups"] == []
    assert r["overall_risk"] == "low"
    assert r["requires_expert_review"] is False
    assert r["parsed"] is True


def test_invalid_smiles_fails_safe():
    r = rs.screen_smiles("not-a-smiles!!")
    assert r["parsed"] is False
    assert r["overall_risk"] == "unknown"
    assert r["requires_expert_review"] is True


def test_none_fails_safe():
    r = rs.screen_smiles(None)
    assert r["parsed"] is False
    assert r["requires_expert_review"] is True


def test_screen_reaction_aggregates_worst_and_lists_groups():
    r = rs.screen_reaction(reactant_smiles=["CCN=[N+]=[N-]", "CCO"], product_smiles="CCOC")
    assert r["overall_risk"] == "critical"
    assert r["requires_expert_review"] is True
    assert "azide" in r["energetic_groups_found"]
    assert len(r["species"]) == 3


def test_screen_reaction_benign_clears():
    r = rs.screen_reaction(reactant_smiles=["CCO"], product_smiles="CCOC")
    assert r["overall_risk"] == "low"
    assert r["requires_expert_review"] is False


def test_screen_reaction_empty_fails_safe():
    r = rs.screen_reaction()
    assert r["overall_risk"] == "unknown"
    assert r["requires_expert_review"] is True


def test_disclaimer_is_always_present():
    assert "PHA" in rs.screen_smiles("CCO")["disclaimer"]
    assert "decision" in rs.screen_reaction(reactant_smiles=["CCO"])["disclaimer"].lower()
