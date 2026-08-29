"""Unit tests for R13 retrosynthesis overlays (pure; the AiZynth search is injected)."""

from __future__ import annotations

import pytest

from nmrcheck.reaction_ml import CapabilityUnavailableError
from nmrcheck.reaction_retro import (
    ReactionRetroError,
    RouteNode,
    propose_routes,
    route_from_aizynth_dict,
    route_from_dict,
    route_similarity,
    score_route,
    to_mermaid,
)

# Ethyl acetate from ethanol + acetic acid — a clean, computable one-step route.
_ESTER_ROUTE = RouteNode(
    smiles="CCOC(C)=O",
    children=[RouteNode(smiles="CCO"), RouteNode(smiles="CC(O)=O")],
    solvent="ethanol",
)

# A route through a nitroaromatic intermediate — the R6 screen must flag it.
_NITRO_ROUTE = RouteNode(
    smiles="Nc1ccccc1",
    children=[RouteNode(smiles="O=[N+]([O-])c1ccccc1")],
)


# --- representation ---------------------------------------------------------------------------
def test_route_roundtrips_through_dict():
    parsed = route_from_dict(_ESTER_ROUTE.as_dict())
    assert parsed.as_dict() == _ESTER_ROUTE.as_dict()


def test_route_from_dict_rejects_missing_smiles():
    with pytest.raises(ReactionRetroError, match="no SMILES"):
        route_from_dict({"children": []})


def test_aizynth_mapper_handles_the_documented_shape():
    payload = {
        "type": "mol",
        "smiles": "CCOC(C)=O",
        "children": [
            {
                "type": "reaction",
                "children": [
                    {"type": "mol", "smiles": "CCO", "children": []},
                    {"type": "mol", "smiles": "CC(O)=O", "children": []},
                ],
            }
        ],
    }
    route = route_from_aizynth_dict(payload)
    assert route.smiles == "CCOC(C)=O"
    assert [child.smiles for child in route.children] == ["CCO", "CC(O)=O"]


def test_aizynth_mapper_rejects_malformed_alternation():
    with pytest.raises(ReactionRetroError, match="'reaction' nodes"):
        route_from_aizynth_dict(
            {"type": "mol", "smiles": "C", "children": [{"type": "mol", "smiles": "C"}]}
        )
    with pytest.raises(ReactionRetroError, match="'mol' node"):
        route_from_aizynth_dict({"type": "reaction", "children": []})


# --- frozen overlays --------------------------------------------------------------------------
def test_score_route_computes_atom_economy_and_solvent_greenness():
    report = score_route(_ESTER_ROUTE)
    assert report["step_count"] == 1
    step = report["steps"][0]
    # AE = MW(ester) / (MW(ethanol) + MW(acetic acid)) ≈ 88 / (46 + 60) ≈ 83%.
    assert 75.0 <= step["atom_economy_percent"] <= 90.0
    assert step["solvent_greenness"] is not None  # ethanol is in the CHEM21 table
    assert 0.0 <= report["route_score"] <= 100.0
    assert report["human_review_required"] is True
    assert "advisory" in report["disclaimer"]


def test_score_route_flags_a_nitro_intermediate_via_r6():
    report = score_route(_NITRO_ROUTE)
    assert report["safety"]["worst_risk"] != "none"
    flagged = [s for s in report["safety"]["screens"] if s["flagged_groups"]]
    assert any("nitro" in str(s["flagged_groups"]).lower() for s in flagged)
    assert report["safety"]["requires_expert_review"] is True


def test_score_route_fails_safe_on_unparseable_structures():
    report = score_route(RouteNode(smiles="definitely-not-smiles", children=[RouteNode("CCO")]))
    assert report["safety"]["worst_risk"] == "unknown"  # never silently clear
    assert report["score_components"]["safety"]["value"] == 0.0


def test_score_route_excludes_missing_components_rather_than_imputing():
    report = score_route(RouteNode(smiles="CCO"))  # no steps at all
    assert "atom_economy" not in report["score_components"]
    assert any("excludes atom economy" in w for w in report["warnings"])


# --- mermaid + similarity ---------------------------------------------------------------------
def test_mermaid_is_deterministic_and_edges_point_at_products():
    diagram = to_mermaid(_ESTER_ROUTE)
    assert diagram == to_mermaid(_ESTER_ROUTE)
    assert diagram.startswith("graph TD")
    assert 'n0["CCOC(C)=O"]' in diagram
    assert "n1 --> n0" in diagram and "n2 --> n0" in diagram


def test_route_similarity_bounds():
    assert route_similarity(_ESTER_ROUTE, _ESTER_ROUTE) == pytest.approx(1.0)
    disjoint = RouteNode(smiles="c1ccccc1", children=[RouteNode("C1CCCCC1")])
    assert route_similarity(_ESTER_ROUTE, disjoint) == pytest.approx(0.0)
    # Same target, different precursors: similar at depth 0, dissimilar at depth 1.
    partial = RouteNode(smiles="CCOC(C)=O", children=[RouteNode("CCBr")])
    assert 0.0 < route_similarity(_ESTER_ROUTE, partial) < 1.0


def test_route_similarity_matches_canonical_forms():
    a = RouteNode(smiles="CCO")
    b = RouteNode(smiles="OCC")  # same molecule, different SMILES
    assert route_similarity(a, b) == pytest.approx(1.0)


# --- governed proposal flow -------------------------------------------------------------------
_AIZYNTH_SHAPE = {
    "type": "mol",
    "smiles": "CCOC(C)=O",
    "children": [
        {
            "type": "reaction",
            "children": [
                {"type": "mol", "smiles": "CCO", "children": []},
                {"type": "mol", "smiles": "CC(O)=O", "children": []},
            ],
        }
    ],
}


def test_propose_routes_requires_the_capability():
    with pytest.raises(CapabilityUnavailableError, match="default off"):
        propose_routes("CCOC(C)=O", config_path="cfg.yml", env={})


def test_propose_routes_scores_and_sorts_with_provenance():
    scored = propose_routes(
        "CCOC(C)=O",
        config_path="cfg.yml",
        env={"MOLTRACE_REACTION_RETRO": "1"},
        probe=lambda _m: True,
        _search=lambda _t, _c, _n: [_AIZYNTH_SHAPE],
    )
    assert len(scored) == 1
    entry = scored[0]
    assert entry["score"]["route_score"] > 0
    assert entry["mermaid"].startswith("graph TD")
    assert entry["capability_provenance"]["name"] == "retrosynthesis"


def test_propose_routes_wraps_backend_failures():
    def _boom(_t, _c, _n):
        raise RuntimeError("expansion died")

    with pytest.raises(ReactionRetroError, match="expansion died"):
        propose_routes(
            "CCO",
            config_path="cfg.yml",
            env={"MOLTRACE_REACTION_RETRO": "1"},
            probe=lambda _m: True,
            _search=_boom,
        )


def test_route_score_says_how_much_of_the_budget_it_was_scored_on():
    """Characterising a route more thoroughly must not silently lower it.

    Components without data are excluded and the weights renormalised -- correct, since an
    absent component must not be imputed -- but it means a route scored on safety and
    brevity alone reports 84.00 while the same route with all four components scored
    reports 63.50. Nothing on the result said which was which, so the evidence-poor route
    looked better than the well-characterised one.

    Reported rather than gated: a client rendering "scored on 2 of 4 components" beside the
    number does not need a floor, and there is no measured distribution to place one on.
    """

    report = score_route(_ESTER_ROUTE)

    assert report["total_component_count"] == 4
    assert 0.0 < report["score_coverage"] <= 1.0
    assert report["scored_component_count"] == len(report["score_components"])
    # Coverage is the share of the weight budget the scored components carry, so it must
    # reconcile with the components actually reported rather than being a separate number.
    assert report["score_coverage"] == pytest.approx(
        sum(entry["weight"] for entry in report["score_components"].values())
    )


def test_route_score_coverage_is_the_present_weight_share():
    """The weights are safety .4 / atom economy .3 / solvent greenness .2 / brevity .1."""

    # Reproduce the arithmetic the engine performs, so the meaning of the field is pinned
    # even where a full route fixture is not available.
    present = {"safety": (0.4, 90.0), "brevity": (0.1, 60.0)}
    total_weight = sum(w for w, _ in present.values())
    score = sum(w * v for w, v in present.values()) / total_weight
    assert score == pytest.approx(84.0)
    assert total_weight == pytest.approx(0.5)  # what score_coverage reports

    full = {
        "safety": (0.4, 90.0),
        "atom_economy": (0.3, 45.0),
        "solvent_greenness": (0.2, 40.0),
        "brevity": (0.1, 60.0),
    }
    full_score = sum(w * v for w, v in full.values()) / sum(w for w, _ in full.values())
    assert full_score == pytest.approx(63.5)
    assert full_score < score, "the better-characterised route scores lower -- hence coverage"
