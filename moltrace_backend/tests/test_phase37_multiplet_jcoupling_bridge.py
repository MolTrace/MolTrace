"""Phase 37 — multiplet J-coupling -> unified-confidence evidence layer.

Covers four surfaces:

1. ``jcoupling_prediction.predict_proton_couplings_from_smiles`` — the
   topological-empirical J predictor (aromatic ortho/meta, heteroaromatic
   alpha-beta, terminal vinyl, defined-stereo alkene cis/trans, aliphatic
   vicinal, invalid structure, near-duplicate compaction).
2. ``multiplet_jcoupling_bridge.score_multiplets_against_candidates`` — the
   greedy J-set scorer (strong agreement vs. saturated-decoy contradiction,
   no-observed / no-predicted / invalid-candidate branches, mutual-coupling
   compaction).
3. ``POST /candidates/compare/jcoupling`` — endpoint contract + audit event.
4. ``build_unified_candidate_confidence`` integration — the new layer must
   leave the weight denominator byte-identical when no multiplet input is
   present (regression guard), and must rank/contradict correctly when it is.
"""

from __future__ import annotations

import pytest

from nmrcheck.jcoupling_prediction import predict_proton_couplings_from_smiles
from nmrcheck.models import (
    CandidateInput,
    MultipletDescriptor,
    MultipletJCouplingBridgeRequest,
    UnifiedCandidateConfidenceRequest,
)
from nmrcheck.multiplet_jcoupling_bridge import (
    collect_observed_couplings,
    score_multiplets_against_candidates,
)
from nmrcheck.unified_confidence import (
    DEFAULT_LAYER_WEIGHTS,
    build_unified_candidate_confidence,
)

QUININE = "COC1=CC2=NC=CC(=C2C=C1)C(C3CC4CCN3CC4C=C)O"
# 2-methylcyclohexanol: fully saturated -> only ~7 Hz vicinal couplings,
# cannot produce the ~17 Hz / ~10 Hz alkene couplings quinine shows.
SATURATED_DECOY = "CC1CCCCC1O"
# A realistic recovered observed J set for quinine (Prompt 4 analyser output):
# vinyl trans/cis, aromatic ortho, aliphatic vicinal, heteroaromatic a-b, meta.
QUININE_OBSERVED = [17.4, 10.4, 9.2, 7.5, 4.5, 2.7]


# --------------------------------------------------------------------------- #
# 1. Topological J predictor                                                  #
# --------------------------------------------------------------------------- #


def test_predict_benzene_ortho_and_meta() -> None:
    result = predict_proton_couplings_from_smiles("c1ccccc1")
    assert not result.invalid_structure
    assert result.couplings_hz == [7.8, 2.0]
    assert result.category_counts.get("aromatic_ortho")
    assert result.category_counts.get("aromatic_meta")


def test_predict_pyridine_emits_heteroaromatic_alpha_beta() -> None:
    result = predict_proton_couplings_from_smiles("c1ccncc1")
    assert 4.8 in result.couplings_hz  # H2-H3 alpha,beta coupling
    assert result.category_counts.get("heteroaromatic_alpha_beta")


def test_predict_terminal_vinyl_emits_both_cis_and_trans() -> None:
    result = predict_proton_couplings_from_smiles("C=Cc1ccccc1")  # styrene
    assert 17.0 in result.couplings_hz  # vinyl trans
    assert 10.8 in result.couplings_hz  # vinyl cis


def test_predict_defined_stereo_alkene_cis_vs_trans() -> None:
    trans = predict_proton_couplings_from_smiles("C/C=C/C")  # (E)-2-butene
    cis = predict_proton_couplings_from_smiles("C/C=C\\C")  # (Z)-2-butene
    assert 16.5 in trans.couplings_hz and 11.0 not in trans.couplings_hz
    assert 11.0 in cis.couplings_hz and 16.5 not in cis.couplings_hz


def test_predict_aliphatic_vicinal_only() -> None:
    result = predict_proton_couplings_from_smiles("CCO")  # ethanol
    assert result.couplings_hz == [7.0]


def test_predict_no_diagnostic_couplings_for_tert_butanol() -> None:
    result = predict_proton_couplings_from_smiles("CC(C)(C)O")
    assert not result.invalid_structure
    assert result.couplings_hz == []
    assert result.warnings  # explains why nothing was emitted


def test_predict_compacts_near_duplicate_vicinals() -> None:
    # Quinine has 8 distinct aliphatic vicinal couplings, all ~7.0 Hz; they
    # must collapse to a single representative so the similarity denominator
    # is not inflated by near-duplicates.
    result = predict_proton_couplings_from_smiles(QUININE)
    assert result.couplings_hz == [17.0, 10.8, 7.8, 7.0, 4.8, 2.0]
    assert result.category_counts["aliphatic_vicinal"] == 8
    assert result.couplings_hz.count(7.0) == 1


def test_predict_invalid_structure_does_not_raise() -> None:
    result = predict_proton_couplings_from_smiles("not_a_smiles")
    assert result.invalid_structure
    assert result.couplings_hz == []
    assert result.warnings


# --------------------------------------------------------------------------- #
# 2. Bridge scoring                                                           #
# --------------------------------------------------------------------------- #


def _bridge_req(**kwargs) -> MultipletJCouplingBridgeRequest:
    base = dict(
        candidates=[
            CandidateInput(name="quinine", smiles=QUININE),
            CandidateInput(name="2-methylcyclohexanol", smiles=SATURATED_DECOY),
        ],
        observed_j_couplings_hz=QUININE_OBSERVED,
    )
    base.update(kwargs)
    return MultipletJCouplingBridgeRequest(**base)


def test_bridge_ranks_quinine_over_saturated_decoy() -> None:
    result = score_multiplets_against_candidates(_bridge_req())
    assert result.best_match is not None
    assert result.best_match.name == "quinine"
    assert result.best_match.label == "strong_j_agreement"
    assert result.best_match.score >= 0.72
    assert not result.best_match.contradiction

    decoy = next(m for m in result.matches if m.name == "2-methylcyclohexanol")
    assert decoy.contradiction is True
    assert decoy.label == "j_coupling_contradiction"
    # contradiction caps the score so coincidental matches cannot rank it high
    assert decoy.score <= 0.25
    assert decoy.rank > result.best_match.rank
    assert result.metadata["parser_version"] == "phase37_multiplet_jcoupling_bridge_v1"


def test_bridge_no_observed_couplings_scores_zero() -> None:
    req = _bridge_req(observed_j_couplings_hz=[])
    result = score_multiplets_against_candidates(req)
    assert result.observed_coupling_count == 0
    for match in result.matches:
        assert match.label == "no_observed_couplings"
        assert match.score == 0.0
        assert not match.contradiction
    assert any("No observed J couplings" in w for w in result.warnings)


def test_bridge_no_predicted_couplings_contradicts_large_observed() -> None:
    req = MultipletJCouplingBridgeRequest(
        candidates=[CandidateInput(name="tert-butanol", smiles="CC(C)(C)O")],
        observed_j_couplings_hz=[16.0],  # a trans-alkene coupling
    )
    result = score_multiplets_against_candidates(req)
    match = result.matches[0]
    assert match.label == "no_predicted_couplings"
    assert match.contradiction is True
    assert match.predicted_j_couplings_hz == []


def test_bridge_invalid_candidate_is_flagged() -> None:
    req = MultipletJCouplingBridgeRequest(
        candidates=[CandidateInput(name="bad", smiles="not_a_smiles")],
        observed_j_couplings_hz=[7.0],
    )
    result = score_multiplets_against_candidates(req)
    match = result.matches[0]
    assert match.label == "candidate_invalid"
    assert match.contradiction is True
    assert match.score == 0.0


def test_bridge_compacts_mutual_couplings_from_multiplets() -> None:
    # A mutual coupling J_AB appears in BOTH partner multiplets; the bridge
    # must compact the duplicate so it is counted once.
    multiplets = [
        MultipletDescriptor(
            name="A",
            center_ppm=5.0,
            range_ppm=(4.95, 5.05),
            multiplicity_label="d",
            j_couplings_hz=[7.5],
            num_nuclides=1,
        ),
        MultipletDescriptor(
            name="B",
            center_ppm=3.0,
            range_ppm=(2.95, 3.05),
            multiplicity_label="d",
            j_couplings_hz=[7.5],
            num_nuclides=1,
        ),
    ]
    req = MultipletJCouplingBridgeRequest(
        candidates=[CandidateInput(name="ethanol", smiles="CCO")],
        observed_multiplets=multiplets,
    )
    observed, raw_count = collect_observed_couplings(req)
    assert raw_count == 2
    assert observed == [7.5]  # mutual coupling counted once
    result = score_multiplets_against_candidates(req)
    assert result.observed_coupling_count == 1


# --------------------------------------------------------------------------- #
# 3. Endpoint contract                                                        #
# --------------------------------------------------------------------------- #


def test_jcoupling_endpoint_contract_and_audit(client, api_headers) -> None:
    payload = {
        "sample_id": "phase37-endpoint",
        "candidates": [
            {"name": "quinine", "smiles": QUININE},
            {"name": "2-methylcyclohexanol", "smiles": SATURATED_DECOY},
        ],
        "observed_j_couplings_hz": QUININE_OBSERVED,
    }
    headers = api_headers
    with client:
        res = client.post("/candidates/compare/jcoupling", headers=headers, json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["best_match"]["name"] == "quinine"
        assert data["best_match"]["label"] == "strong_j_agreement"
        decoy = next(m for m in data["matches"] if m["name"] == "2-methylcyclohexanol")
        assert decoy["contradiction"] is True
        # contract: evidence table header + matched-pair shape
        assert data["evidence_table_text"].splitlines()[0].startswith("rank,name,smiles")
        pair = data["best_match"]["matched_pairs"][0]
        assert {"observed_hz", "predicted_hz", "delta_hz", "score"} <= set(pair)

        # audit event emitted
        audit = client.get(
            "/audit/events",
            headers=headers,
            params={"event_type": "confidence.candidates.multiplet_jcoupling_bridge"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
        assert len(events) >= 1
        meta = events[0]["metadata"]
        assert meta["candidate_count"] == 2
        assert meta["observed_coupling_count"] == 6
        assert meta["contradiction_count"] >= 1
        assert meta["human_review_required"] is True

    # empty candidate list is rejected by request validation (422)
    with client:
        bad = client.post(
            "/candidates/compare/jcoupling", headers=headers, json={"candidates": []}
        )
        assert bad.status_code == 422


# --------------------------------------------------------------------------- #
# 4. Unified-confidence integration                                           #
# --------------------------------------------------------------------------- #


def _candidates() -> list[CandidateInput]:
    return [
        CandidateInput(name="quinine", smiles=QUININE),
        CandidateInput(name="2-methylcyclohexanol", smiles=SATURATED_DECOY),
    ]


def test_unified_without_jcoupling_input_keeps_default_denominator() -> None:
    """REGRESSION: with no multiplet input the weight set must be byte-identical
    to DEFAULT_LAYER_WEIGHTS and no candidate may carry the new layer."""
    req = UnifiedCandidateConfidenceRequest(sample_id="reg", candidates=_candidates())
    result = build_unified_candidate_confidence(req)
    assert result.component_metadata["layer_weights"] == DEFAULT_LAYER_WEIGHTS
    assert "multiplet_jcoupling" not in result.component_metadata["layer_weights"]
    for item in result.ranked_candidates:
        assert all(layer.layer != "multiplet_jcoupling" for layer in item.layers)


def test_unified_with_jcoupling_input_adds_layer_and_ranks() -> None:
    req = UnifiedCandidateConfidenceRequest(
        sample_id="j",
        candidates=_candidates(),
        observed_j_couplings_hz=QUININE_OBSERVED,
    )
    result = build_unified_candidate_confidence(req)
    weights = result.component_metadata["layer_weights"]
    assert weights["multiplet_jcoupling"] == 0.10
    # the bridge result is referenced (with a content hash) in metadata
    assert "multiplet_jcoupling_bridge" in result.component_metadata
    assert result.component_metadata["multiplet_jcoupling_bridge"]["bridge_result_sha256"]

    top = result.ranked_candidates[0]
    assert top.name == "quinine"
    mj = next(layer for layer in top.layers if layer.layer == "multiplet_jcoupling")
    assert mj.used and mj.score is not None and mj.score >= 0.72
    assert not mj.contradiction

    decoy = next(it for it in result.ranked_candidates if it.name == "2-methylcyclohexanol")
    decoy_layer = next(
        layer for layer in decoy.layers if layer.layer == "multiplet_jcoupling"
    )
    assert decoy_layer.contradiction is True
    assert any("J coupling" in c for c in result.global_contradictions)


def test_unified_jcoupling_layer_label_registered() -> None:
    req = UnifiedCandidateConfidenceRequest(
        sample_id="lbl",
        candidates=[CandidateInput(name="quinine", smiles=QUININE)],
        observed_j_couplings_hz=QUININE_OBSERVED,
    )
    result = build_unified_candidate_confidence(req)
    assert "Multiplet J-coupling agreement" in result.evidence_layers_used


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
