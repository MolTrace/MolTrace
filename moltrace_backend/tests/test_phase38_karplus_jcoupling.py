"""Phase 38 — opt-in Karplus 3J refinement for the multiplet J-coupling layer.

The Phase 37 predictor assigns a single flat empirical value (~7.0 Hz) to every
aliphatic vicinal coupling.  Phase 38 adds an *opt-in* geometry-aware refinement
(``use_karplus=True``) that replaces that flat value with a conformer-averaged
Karplus ``3J`` read from an RDKit ETKDG ensemble — sharpening Layer 40's ability
to discriminate candidates whose locked geometry produces a large diaxial
coupling from those that cannot.

Coverage:

1. ``karplus_3j`` — the pure dihedral->coupling relation (curve shape).
2. ``predict_proton_couplings_from_smiles(..., use_karplus=...)`` — the opt-in
   refinement, including the **byte-identical regression guarantee** for the
   default (topology-only) path, the locked-ring diaxial recovery, mobile
   conformational averaging, the aromatic no-op, and determinism.
3. ``score_multiplets_against_candidates`` — the bridge threads the flag, the
   provenance note flips, and the refinement materially improves agreement for
   a locked candidate against a diaxial-rich observed set.
4. ``_bridge_multiplet_jcoupling_request`` / ``build_unified_candidate_confidence``
   — the unified engine threads the flag and the new fields never perturb the
   weight denominator when no multiplet input is present.
5. ``POST /candidates/compare/jcoupling`` — the route accepts ``use_karplus``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.jcoupling_prediction import (
    KARPLUS_DEFAULT_MAX_CONFORMERS,
    karplus_3j,
    predict_proton_couplings_from_smiles,
)
from nmrcheck.models import (
    CandidateInput,
    MultipletJCouplingBridgeRequest,
    UnifiedCandidateConfidenceRequest,
)
from nmrcheck.multiplet_jcoupling_bridge import score_multiplets_against_candidates
from nmrcheck.settings import Settings
from nmrcheck.unified_confidence import (
    DEFAULT_LAYER_WEIGHTS,
    _bridge_multiplet_jcoupling_request,
    build_unified_candidate_confidence,
)

# trans-decalin: rigid trans-fused bicyclic (no ring flip) -> the diaxial
# H-C-C-H stays antiperiplanar, so the ensemble average preserves a ~10 Hz
# coupling the flat 7.0 predictor can never produce.
TRANS_DECALIN = "C1CC[C@@H]2CCCC[C@H]2C1"
# beta-D-glucopyranose: the textbook Karplus case -- a locked 4C1 chair whose
# ring protons show large trans-diaxial couplings (~9-10 Hz).
BETA_D_GLUCOSE = "OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O"
# 2,4-dimethylpentane: saturated, freely rotating -> only averaged ~5-7 Hz
# vicinal couplings, no large diaxial.
ACYCLIC_DECOY = "CC(C)CC(C)C"


# --------------------------------------------------------------------------- #
# 1. Karplus relation (pure function)                                         #
# --------------------------------------------------------------------------- #


def test_karplus_curve_shape_and_minimum() -> None:
    j = {d: karplus_3j(d) for d in (0, 60, 90, 120, 180)}
    # Antiperiplanar (180) is the largest; eclipsed (0) next; minimum near 90.
    assert j[180] > j[0] > j[120] > j[60] > j[90]
    assert 0.0 <= j[90] < 2.0
    # Endpoints land on the textbook generic-Karplus values.
    assert j[0] == pytest.approx(8.06, abs=0.05)
    assert j[180] == pytest.approx(10.26, abs=0.05)
    # Clamped non-negative for every angle.
    assert all(karplus_3j(d) >= 0.0 for d in range(0, 361, 15))


# --------------------------------------------------------------------------- #
# 2. Predictor opt-in refinement                                              #
# --------------------------------------------------------------------------- #

# Known Phase-37 topology-only coupling sets that must NOT change with the
# refinement landed but unrequested (the default path).
_TOPOLOGY_ONLY = {
    "c1ccccc1": [7.8, 2.0],          # benzene ortho + meta
    "C=C": [17.0, 10.8],             # ethylene terminal vinyl
    "C/C=C/C": [16.5, 7.0],          # E-2-butene (trans alkene + vicinal)
    "C/C=C\\C": [11.0, 7.0],         # Z-2-butene (cis alkene + vicinal)
    "CCO": [7.0],                    # ethanol aliphatic vicinal
    "C1CCCCC1": [7.0],               # cyclohexane (flat, pre-Karplus)
    "CC(C)(C)O": [],                 # tert-butanol: no diagnostic couplings
    TRANS_DECALIN: [7.0],
    BETA_D_GLUCOSE: [7.0],
}


@pytest.mark.parametrize("smiles,expected", list(_TOPOLOGY_ONLY.items()))
def test_karplus_off_is_byte_identical_to_topology(smiles: str, expected: list[float]) -> None:
    """REGRESSION GUARANTEE: the default path is byte-identical to Phase 37, and
    an explicit ``use_karplus=False`` matches the default exactly."""
    default = predict_proton_couplings_from_smiles(smiles)
    explicit_off = predict_proton_couplings_from_smiles(smiles, use_karplus=False)
    assert default.couplings_hz == expected
    assert explicit_off.couplings_hz == expected
    # the Karplus-only provenance category must never appear on the off path
    assert "aliphatic_vicinal_karplus" not in default.category_counts
    assert "aliphatic_vicinal_karplus" not in explicit_off.category_counts


@pytest.mark.parametrize("smiles,floor", [(TRANS_DECALIN, 8.5), (BETA_D_GLUCOSE, 8.0)])
def test_karplus_locked_ring_recovers_large_diaxial(smiles: str, floor: float) -> None:
    """A conformationally locked ring recovers a large trans-diaxial coupling
    that the flat 7.0 predictor can never produce."""
    off = predict_proton_couplings_from_smiles(smiles)
    on = predict_proton_couplings_from_smiles(smiles, use_karplus=True, karplus_max_conformers=10)
    assert (max(off.couplings_hz) if off.couplings_hz else 0.0) <= 7.001
    assert max(on.couplings_hz) > floor
    assert on.category_counts.get("aliphatic_vicinal_karplus")
    assert "aliphatic_vicinal" not in on.category_counts  # refined away


@pytest.mark.parametrize("smiles", ["CCO", "CCC", "CCCC"])
def test_karplus_mobile_acyclic_averages_into_band(smiles: str) -> None:
    """Freely rotating acyclic chains average into a plausible vicinal band
    (no spurious diaxial coupling) -- demonstrates conformational averaging."""
    on = predict_proton_couplings_from_smiles(smiles, use_karplus=True, karplus_max_conformers=10)
    assert on.couplings_hz  # at least one vicinal coupling
    assert all(1.5 <= j <= 9.0 for j in on.couplings_hz)


def test_karplus_aromatic_only_is_noop() -> None:
    """Benzene has no aliphatic vicinal coupling, so the refinement is a no-op."""
    on = predict_proton_couplings_from_smiles("c1ccccc1", use_karplus=True)
    assert on.couplings_hz == [7.8, 2.0]
    assert "aliphatic_vicinal_karplus" not in on.category_counts


def test_karplus_is_deterministic() -> None:
    """The ETKDG ensemble is seeded, so repeated calls are reproducible."""
    a = predict_proton_couplings_from_smiles(TRANS_DECALIN, use_karplus=True, karplus_max_conformers=10)
    b = predict_proton_couplings_from_smiles(TRANS_DECALIN, use_karplus=True, karplus_max_conformers=10)
    assert a.couplings_hz == b.couplings_hz
    assert a.couplings_hz  # non-empty


def test_karplus_default_conformer_count_is_exposed() -> None:
    assert KARPLUS_DEFAULT_MAX_CONFORMERS >= 1


def test_karplus_invalid_structure_does_not_raise() -> None:
    res = predict_proton_couplings_from_smiles("not-a-smiles", use_karplus=True)
    assert res.invalid_structure is True
    assert res.couplings_hz == []


# --------------------------------------------------------------------------- #
# 3. Bridge threading                                                         #
# --------------------------------------------------------------------------- #


def test_bridge_threads_karplus_flag_and_flips_provenance_note() -> None:
    base = dict(
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=[9.4, 8.1, 3.4],
    )
    on = score_multiplets_against_candidates(
        MultipletJCouplingBridgeRequest(**base, use_karplus=True, karplus_max_conformers=10)
    )
    off = score_multiplets_against_candidates(MultipletJCouplingBridgeRequest(**base))

    assert on.metadata["use_karplus"] is True
    assert on.metadata["karplus_max_conformers"] == 10
    assert "Karplus" in on.notes[0]

    assert off.metadata["use_karplus"] is False
    assert "no Karplus/3D" in off.notes[0]


def test_bridge_karplus_improves_agreement_for_locked_candidate() -> None:
    """Against a diaxial-rich observed set, the Karplus refinement lets a locked
    sugar explain the large coupling, raising its agreement score."""
    observed = [9.4, 8.1, 3.4]
    req_on = MultipletJCouplingBridgeRequest(
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=observed,
        use_karplus=True,
        karplus_max_conformers=10,
    )
    req_off = req_on.model_copy(update={"use_karplus": False})
    on = score_multiplets_against_candidates(req_on).matches[0]
    off = score_multiplets_against_candidates(req_off).matches[0]

    assert on.max_predicted_j_hz is not None and on.max_predicted_j_hz > 8.0
    assert (off.max_predicted_j_hz or 0.0) <= 7.001
    # geometry-aware prediction explains the large observed diaxial -> better score
    assert on.score > off.score


# --------------------------------------------------------------------------- #
# 4. Unified-confidence integration                                           #
# --------------------------------------------------------------------------- #


def test_unified_threads_karplus_into_bridge_request() -> None:
    req = UnifiedCandidateConfidenceRequest(
        sample_id="k",
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=[9.4],
        multiplet_jcoupling_use_karplus=True,
        multiplet_jcoupling_max_conformers=9,
    )
    bridged = _bridge_multiplet_jcoupling_request(req)
    assert bridged.use_karplus is True
    assert bridged.karplus_max_conformers == 9


def test_unified_karplus_defaults_do_not_perturb_denominator() -> None:
    """REGRESSION: the new opt-in fields default off, so with no multiplet input
    the weight set stays byte-identical to DEFAULT_LAYER_WEIGHTS."""
    req = UnifiedCandidateConfidenceRequest(
        sample_id="reg",
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
    )
    result = build_unified_candidate_confidence(req)
    assert result.component_metadata["layer_weights"] == DEFAULT_LAYER_WEIGHTS
    assert "multiplet_jcoupling" not in result.component_metadata["layer_weights"]


# --------------------------------------------------------------------------- #
# 5. Endpoint contract                                                        #
# --------------------------------------------------------------------------- #


def test_jcoupling_endpoint_accepts_use_karplus(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'phase38_karplus.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    payload = {
        "sample_id": "phase38-endpoint",
        "candidates": [{"name": "glucose", "smiles": BETA_D_GLUCOSE}],
        "observed_j_couplings_hz": [9.4, 8.1, 3.4],
        "use_karplus": True,
        "karplus_max_conformers": 8,
    }
    headers = {"x-api-key": "test-key"}
    with TestClient(app) as client:
        res = client.post("/candidates/compare/jcoupling", headers=headers, json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["metadata"]["use_karplus"] is True
        assert data["best_match"]["max_predicted_j_hz"] > 8.0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
