"""Tests for the nitrosamine CPCA classifier (Prompt 5) — canonical FDA CPCA.

Pins the FDA Carcinogenic Potency Categorization Approach: the alpha-hydrogen score
table, the activating / deactivating feature point-values, the flowchart, the AI
ladder (26.5/100/400/1500/1500 ng/day; EMA Category 1 = 18), and the cumulative-risk
rule. The published validation nitrosamines (NDMA, NDEA, NDPA, NDBA, NMBzA) are
**all Category 1** under the real CPCA algorithm (the prompt's NDPA->2 / NDBA->3 /
NMBzA->3 targets reflected a non-canonical scheme; NDMA/NDEA->1 were correct).

The alpha-H scoring, flowchart, AI ladder, ring, carboxylic-acid, tertiary-alpha,
and benzylic features are exact (transcribed from the FDA featurize-nitrosamines
reference tool). The chain-length, EWG, beta-hydroxyl, and beta-methyl detectors are
faithful but approximate rdkit reimplementations and are flagged for verification
against the FDA tool for complex structures.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.impurities import (
    calculate_cumulative_risk,
    classify_cpca,
    cpca_rule_set,
)
from moltrace.regulatory.infra.validation import DataValidationError

# --------------------------------------------------------------------------- #
# Published validation nitrosamines -> all Category 1 (AI 26.5 ng/day, FDA)
# --------------------------------------------------------------------------- #
_VALIDATION = {
    "NDMA": "CN(C)N=O",
    "NDEA": "CCN(CC)N=O",
    "NDPA": "CCCN(CCC)N=O",
    "NDBA": "CCCCN(CCCC)N=O",
    "NMBzA": "O=NN(C)Cc1ccccc1",
}


@pytest.mark.parametrize("name, smiles", list(_VALIDATION.items()))
def test_validation_compounds_are_category1(name, smiles):
    c = classify_cpca(smiles)
    assert c.category == 1, (name, c.category)
    assert c.ai_limit_ng_per_day == 26.5
    assert c.coc_flag is True


def test_validation_compounds_ema_category1_is_18():
    for smiles in _VALIDATION.values():
        assert classify_cpca(smiles, authority="EMA").ai_limit_ng_per_day == 18.0


# --------------------------------------------------------------------------- #
# alpha-Hydrogen score table (FDA values)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "smiles, expected_dist, expected_score",
    [
        ("CN(C)N=O", "3,3", 1),  # NDMA
        ("CCN(CC)N=O", "2,2", 1),  # NDEA
        ("CCN(C)N=O", "2,3", 1),  # N-nitrosomethylethylamine
        ("O=NN(C)c1ccccc1", "0,3", 2),  # N-methyl-N-nitrosoaniline (aryl side = 0 H)
        ("CCN(N=O)C(C)C", "1,2", 3),  # ethyl(2) + isopropyl methine(1)
    ],
)
def test_alpha_h_score_table(smiles, expected_dist, expected_score):
    c = classify_cpca(smiles)
    assert c.alpha_h_distribution == expected_dist
    assert c.alpha_h_score == expected_score


def test_rule_set_alpha_h_table_matches_fda():
    table = cpca_rule_set()["alpha_h_score_table"]
    assert table["2,2"] == 1 and table["3,3"] == 1 and table["2,3"] == 1
    assert table["0,2"] == 3 and table["0,3"] == 2 and table["1,2"] == 3 and table["1,3"] == 3
    assert table["0,0"] == 5 and table["0,1"] == 4 and table["1,1"] == 4  # force Category 5


# --------------------------------------------------------------------------- #
# Forced Category 5 (no/low alpha-H or tertiary alpha-carbon)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "smiles",
    [
        "O=NN(C(C)(C)C)C(C)(C)C",  # di-tert-butyl: tertiary alpha-carbon
        "CC(C)N(N=O)C(C)C",  # diisopropyl: (1,1) alpha-H
    ],
)
def test_forced_category5(smiles):
    c = classify_cpca(smiles)
    assert c.category == 5
    assert c.ai_limit_ng_per_day == 1500.0
    assert c.potency_score is None  # not scored when forced


# --------------------------------------------------------------------------- #
# Ring features (deactivating)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, smiles, expected_category, feature",
    [
        ("nitrosopyrrolidine", "O=NN1CCCC1", 4, "nno_in_pyrrolidine_ring"),  # 1 + 3
        ("nitrosomorpholine", "O=NN1CCOCC1", 2, "nno_in_morpholine_ring"),  # 1 + 1
        ("nitrosopiperidine", "O=NN1CCCCC1", 3, "nno_in_5_or_6_ring"),  # 1 + 2
        ("nitrosothiomorpholine", "O=NN1CCSCC1", 4, "nno_in_6ring_with_sulfur"),  # 1 + 3
    ],
)
def test_ring_features(name, smiles, expected_category, feature):
    c = classify_cpca(smiles)
    assert c.category == expected_category, (name, c.category)
    assert feature in c.deactivating_features


# --------------------------------------------------------------------------- #
# Carboxylic acid, beta-hydroxyl, benzylic, beta-methyl
# --------------------------------------------------------------------------- #
def test_carboxylic_acid_only_no_double_count():
    # N-nitrososarcosine: alpha-H (2,3)=1 + COOH(+3) = 4 -> Category 4.
    # The free acid must NOT also trigger EWG or beta-hydroxyl (no double-count).
    c = classify_cpca("O=NN(C)CC(=O)O")
    assert c.deactivating_features == ("carboxylic_acid",)
    assert c.potency_score == 4
    assert c.category == 4


def test_genuine_beta_hydroxyl_counts():
    # N-nitroso-N-methyl-2-aminoethanol: alpha-H (2,3)=1 + beta-OH one side(+1) = 2.
    c = classify_cpca("O=NN(C)CCO")
    assert "beta_hydroxyl_one_side" in c.deactivating_features
    assert c.category == 2


def test_benzylic_is_activating():
    c = classify_cpca("O=NN(C)Cc1ccccc1")  # NMBzA
    assert "aryl_on_alpha_benzylic" in c.activating_features
    assert c.feature_evidence["aryl_on_alpha_benzylic"] == -1


def test_beta_methyl_requires_secondary_methine():
    # n-propyl (beta CH2, 2 H) must NOT count a beta-methyl...
    assert "methyl_on_beta_carbon" not in classify_cpca("CCCN(CCC)N=O").activating_features
    # ...but di-isobutyl (beta CH methine bearing methyls) DOES.
    c = classify_cpca("O=NN(CC(C)C)CC(C)C")
    assert "methyl_on_beta_carbon" in c.activating_features


# --------------------------------------------------------------------------- #
# Flowchart: potency score -> category
# --------------------------------------------------------------------------- #
def test_score_to_category_mapping():
    # piperidine ring (+2) over the (2,2)=1 base sweeps scores 1->3->...:
    assert classify_cpca("CCN(CC)N=O").category == 1  # score 1
    assert classify_cpca("O=NN1CCOCC1").category == 2  # score 2 (morpholine)
    assert classify_cpca("O=NN1CCCCC1").category == 3  # score 3 (piperidine)
    assert classify_cpca("O=NN1CCCC1").category == 4  # score 4 (pyrrolidine)


# --------------------------------------------------------------------------- #
# Cumulative risk (FDA Rev 2): sum(measured / AI limit) < 1
# --------------------------------------------------------------------------- #
def test_cumulative_risk_pass():
    r = calculate_cumulative_risk([("CN(C)N=O", 10.0), ("CCN(CC)N=O", 10.0)])
    assert r.total_risk_ratio == pytest.approx(10 / 26.5 + 10 / 26.5)
    assert r.passes is True
    assert len(r.components) == 2


def test_cumulative_risk_fail():
    r = calculate_cumulative_risk([("CN(C)N=O", 20.0), ("CCN(CC)N=O", 20.0)])
    assert r.total_risk_ratio > 1.0
    assert r.passes is False


def test_cumulative_risk_single_at_limit():
    # Exactly at the AI limit -> ratio 1.0 -> NOT < 1 -> fails.
    r = calculate_cumulative_risk([("CN(C)N=O", 26.5)])
    assert r.total_risk_ratio == pytest.approx(1.0)
    assert r.passes is False


def test_cumulative_risk_rejects_negative():
    with pytest.raises(DataValidationError):
        calculate_cumulative_risk([("CN(C)N=O", -1.0)])


# --------------------------------------------------------------------------- #
# Metadata, disclaimer, fail-loud, determinism
# --------------------------------------------------------------------------- #
def test_disclaimer_present_in_result_and_notes():
    c = classify_cpca("CN(C)N=O")
    assert "decision-support" in c.disclaimer.lower()
    assert "not a regulatory determination" in c.disclaimer.lower()
    assert any("decision-support" in n.lower() for n in c.notes)
    assert c.regulatory_basis.startswith("FDA Nitrosamine Guidance")


def test_coc_flag_always_true_for_nitrosamine():
    for smiles in _VALIDATION.values():
        assert classify_cpca(smiles).coc_flag is True


def test_is_ndsri_heuristic():
    assert classify_cpca("CN(C)N=O").is_ndsri is False  # small molecule
    # a larger API-related nitrosamine
    assert classify_cpca("O=NN(C)CCc1ccc(OCCN2CCCCC2)cc1").is_ndsri is True


def test_non_nitrosamine_and_invalid_fail_loud():
    with pytest.raises(DataValidationError):
        classify_cpca("CCO")  # not a nitrosamine
    with pytest.raises(DataValidationError):
        classify_cpca("not_a_smiles")
    with pytest.raises(DataValidationError):
        classify_cpca("CN(C)N=O", authority="MHRA")  # unknown authority


def test_result_is_deterministic():
    assert classify_cpca("CN(C)N=O").content_hash() == classify_cpca("CN(C)N=O").content_hash()
    assert cpca_rule_set() == cpca_rule_set()
    a = calculate_cumulative_risk([("CN(C)N=O", 5.0)]).as_dict()
    b = calculate_cumulative_risk([("CN(C)N=O", 5.0)]).as_dict()
    assert a == b
