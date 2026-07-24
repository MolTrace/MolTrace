"""Unit tests for R14 forward prediction (pure; the model backend is injected)."""

from __future__ import annotations

import pytest

from nmrcheck.reaction_forward import (
    ForwardPrediction,
    ReactionForwardError,
    _aggregate_screens,
    cross_check_prediction,
    predict_forward,
    topk_accuracy,
)
from nmrcheck.reaction_ml import CapabilityUnavailableError

_ENV_ON = {"MOLTRACE_REACTION_FORWARD": "1"}


# --- the frozen cross-check --------------------------------------------------------------------
def test_cross_check_annotates_a_clean_prediction():
    checked = cross_check_prediction(
        ["CCO", "CC(O)=O"],
        ForwardPrediction(
            products_smiles=["CCOC(C)=O"],
            confidence=0.9,
            conditions={"solvent": "ethanol"},
        ),
    )
    assert checked["safety"]["overall_risk"] in {"none", "low"}
    assert checked["solvent_greenness"] is not None
    assert checked["human_review_required"] is True


def test_cross_check_flags_a_hazardous_predicted_product_without_filtering_it():
    checked = cross_check_prediction(
        ["c1ccccc1"],
        ForwardPrediction(products_smiles=["O=[N+]([O-])c1ccccc1"]),
    )
    # The nitro product is flagged and SHOWN — annotated, never hidden.
    assert checked["products_smiles"] == ["O=[N+]([O-])c1ccccc1"]
    assert checked["safety"]["overall_risk"] != "none"
    assert checked["safety"]["requires_expert_review"] is True


def test_cross_check_warns_on_unknown_solvent_and_bad_confidence():
    checked = cross_check_prediction(
        ["CCO"],
        ForwardPrediction(
            products_smiles=["CCO"], confidence=1.7, conditions={"solvent": "unobtainium"}
        ),
    )
    joined = " ".join(checked["warnings"])
    assert "CHEM21" in joined
    assert "outside [0, 1]" in joined


def test_cross_check_requires_products():
    with pytest.raises(ReactionForwardError, match="no products"):
        cross_check_prediction(["CCO"], ForwardPrediction(products_smiles=[]))


# --- governed prediction flow ------------------------------------------------------------------
def _fake_backend(_reactants, _reagents, top_k):
    return [
        ForwardPrediction(products_smiles=["CCOC(C)=O"], confidence=0.8, source="fake"),
        ForwardPrediction(products_smiles=["CCO"], confidence=0.1, source="fake"),
    ][:top_k]


def test_predict_forward_requires_the_capability():
    with pytest.raises(CapabilityUnavailableError, match="default off"):
        predict_forward(["CCO"], env={})


def test_predict_forward_cross_checks_every_candidate_with_provenance():
    result = predict_forward(
        ["CCO", "CC(O)=O"],
        env=_ENV_ON,
        probe=lambda m: m == "transformers",
        _backend=_fake_backend,
    )
    assert len(result["predictions"]) == 2
    assert all("safety" in p for p in result["predictions"])
    assert result["capability_provenance"]["name"] == "forward_prediction"
    assert result["human_review_required"] is True


def test_predict_forward_refuses_an_empty_backend_result():
    with pytest.raises(ReactionForwardError, match="no candidates"):
        predict_forward(
            ["CCO"],
            env=_ENV_ON,
            probe=lambda _m: True,
            _backend=lambda _r, _g, _k: [],
        )


def test_predict_forward_wraps_backend_failures():
    def _boom(_r, _g, _k):
        raise RuntimeError("model exploded")

    with pytest.raises(ReactionForwardError, match="model exploded"):
        predict_forward(["CCO"], env=_ENV_ON, probe=lambda _m: True, _backend=_boom)


# --- top-k validation --------------------------------------------------------------------------
def test_topk_accuracy_matches_canonical_forms():
    cases = [
        {"predictions": ["OCC", "CCN"], "truth": "CCO"},  # top-1 via canonicalisation
        {"predictions": ["CCN", "CCO"], "truth": "CCO"},  # top-2 only
        {"predictions": ["CCN", "CCC"], "truth": "CCO"},  # miss
    ]
    report = topk_accuracy(cases, ks=(1, 2))
    assert report["n_scored"] == 3
    assert report["accuracy"]["top_1"] == pytest.approx(1 / 3)
    assert report["accuracy"]["top_2"] == pytest.approx(2 / 3)


def test_unparseable_prediction_counts_as_wrong_and_bad_truth_is_invalid():
    cases = [
        {"predictions": ["not-a-smiles"], "truth": "CCO"},  # wrong, not skipped
        {"predictions": ["CCO"], "truth": "also-not-smiles"},  # invalid case, reported
    ]
    report = topk_accuracy(cases, ks=(1,))
    assert report["n_scored"] == 1
    assert report["invalid_case_indices"] == [1]
    assert report["accuracy"]["top_1"] == 0.0


def test_topk_refuses_when_nothing_is_scoreable():
    with pytest.raises(ReactionForwardError, match="refusing"):
        topk_accuracy([{"predictions": ["C"], "truth": "nope-not-smiles"}])
    with pytest.raises(ReactionForwardError, match="No evaluation cases"):
        topk_accuracy([])


# --- remediation-verification regressions (adversarial re-review) -------------------------------
def test_unreadable_reactant_is_unknown_not_low():
    """The frozen engine drops "unknown" species before aggregating, falling back to "low".

    A reactant RDKit cannot parse therefore disappears from ``overall_risk`` as long as one
    sibling parses. The Phase-C overlay re-reads the per-species records so an unreadable
    structure can never be laundered into a clean verdict. The frozen engine stays untouched.
    """

    base = {
        "overall_risk": "low",
        "requires_expert_review": True,
        "energetic_groups_found": [],
        "species": [
            {"smiles": "CCO", "parsed": True, "overall_risk": "low"},
            {"smiles": "not-a-smiles", "parsed": False, "overall_risk": "unknown"},
        ],
    }
    aggregate = _aggregate_screens(base, [{"parsed": True, "overall_risk": "low"}])
    assert aggregate["overall_risk"] == "unknown"
    assert aggregate["requires_expert_review"] is True


def test_all_species_readable_keeps_the_base_risk():
    base = {
        "overall_risk": "medium",
        "requires_expert_review": False,
        "energetic_groups_found": [],
        "species": [{"smiles": "CCO", "parsed": True, "overall_risk": "medium"}],
    }
    aggregate = _aggregate_screens(base, [{"parsed": True, "overall_risk": "low"}])
    assert aggregate["overall_risk"] == "medium"


@pytest.mark.parametrize(
    "cases",
    [
        [{"predictions": [""], "truth": ""}],
        [{"predictions": ["  "], "truth": "   "}],
    ],
)
def test_blank_truth_never_scores_as_a_hit(cases):
    """RDKit's MolFromSmiles("") returns an EMPTY MOL, not None — it canonicalises back to "".

    Without an explicit guard a blank prediction would "match" a blank truth and inflate top-1.
    """

    with pytest.raises(ReactionForwardError, match="Every evaluation case was invalid"):
        topk_accuracy(cases, ks=(1,))


def test_blank_prediction_is_not_credited_against_a_real_truth():
    result = topk_accuracy([{"predictions": ["", "CCO"], "truth": "CCO"}], ks=(1, 2))
    assert result["accuracy"]["top_1"] == 0.0
    assert result["accuracy"]["top_2"] == 1.0


@pytest.mark.parametrize("ks", [(), (0,), (-1,), (1, 0), (True,), (1.5,)])
def test_topk_refuses_a_nonsensical_k(ks):
    with pytest.raises(ReactionForwardError, match="positive integers"):
        topk_accuracy([{"predictions": ["CCO"], "truth": "CCO"}], ks=ks)
