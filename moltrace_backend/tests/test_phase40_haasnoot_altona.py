"""Phase 40 — opt-in Haasnoot-de Leeuw-Altona generalized Karplus refinement.

Phase 38 added a *generic* three-term Karplus refinement of aliphatic vicinal
3J.  Phase 40 adds a second, opt-in relation selectable via
``karplus_method="haasnoot_altona"``: the electronegativity/orientation-
corrected generalized Karplus equation of Haasnoot, de Leeuw & Altona
(Tetrahedron 1980, 36, 2783).

This suite validates the **equation itself at known geometries** (where it is
provably more literature-faithful than the generic relation) and the **contract
threading**.  The *measured* corpus-level behaviour -- including the honest
finding that, under the current unweighted conformer averaging, HLA does NOT
improve the semi-quantitative locked-vs-mobile discrimination -- is locked
separately by ``tests/test_phase40_haasnoot_altona_corpus.py``.

Coverage:

1. ``haasnoot_altona_3j`` — curve shape, endpoints, the high pure-hydrocarbon
   antiperiplanar value the generic relation caps below, and the
   electronegativity correction that pulls a sugar diaxial down toward its
   literature window.
2. ``predict_proton_couplings_from_smiles(..., karplus_method=...)`` — the
   default ``"generic"`` path is byte-identical to Phase 38, HLA emits its own
   provenance category and is deterministic, an unknown method falls back to
   generic with a warning, and ``use_karplus=False`` ignores the method.
3. Bridge / unified / endpoint threading of ``karplus_method``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.jcoupling_prediction import (
    KARPLUS_CATEGORY_GENERIC,
    KARPLUS_CATEGORY_HAASNOOT_ALTONA,
    haasnoot_altona_3j,
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
from nmrcheck.unified_confidence import _bridge_multiplet_jcoupling_request

# trans-decalin: rigid trans-fused bicyclic (no ring flip) -> a covalently
# locked diaxial H-C-C-H.  Pure hydrocarbon, so HLA's antiperiplanar value
# (~13 Hz) is recovered far closer to the true ~11-13 Hz coupling than the
# generic relation's ~10.26 Hz cap.
TRANS_DECALIN = "C1CC[C@@H]2CCCC[C@H]2C1"
# beta-D-glucopyranose: the textbook locked-chair sugar; its diaxial couplings
# sit near ~9-10 Hz, below the generic 180-deg cap.
BETA_D_GLUCOSE = "OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O"

# A glucose-like vicinal site: two equatorial oxygens (Huggins d_chi=1.30) and
# two ring carbons (d_chi=0.40) on the coupling carbons.  xi is immaterial at
# the antiperiplanar limit, so these tuples are robust.
_SUGAR_DIAXIAL_SUBS = [(1.30, 1.0), (0.40, -1.0), (1.30, 1.0), (0.40, -1.0)]
_TWO_CARBON_SUBS = [(0.40, -1.0), (0.40, -1.0)]
_TWO_OXYGEN_SUBS = [(1.30, 1.0), (1.30, 1.0)]


# --------------------------------------------------------------------------- #
# 1. Haasnoot-Altona relation (pure function)                                 #
# --------------------------------------------------------------------------- #


def test_hla_curve_shape_and_minimum() -> None:
    """With no substituents the relation is a bare P1..P3 Karplus curve."""
    j = {d: haasnoot_altona_3j(d) for d in (0, 60, 90, 120, 180)}
    # Antiperiplanar (180) largest; eclipsed (0) next; minimum at 90.
    assert j[180] > j[0] > j[120] > j[60] > j[90]
    # P1 cos^2 + P2 cos + P3 endpoints: 13.86 -/+ 0.81.
    assert j[0] == pytest.approx(13.05, abs=0.05)
    assert j[180] == pytest.approx(14.67, abs=0.05)
    assert j[90] == pytest.approx(0.0, abs=0.05)
    # Clamped non-negative everywhere, with and without substituents.
    assert all(haasnoot_altona_3j(d) >= 0.0 for d in range(0, 361, 15))
    assert all(
        haasnoot_altona_3j(d, _SUGAR_DIAXIAL_SUBS) >= 0.0 for d in range(0, 361, 15)
    )


def test_hla_reaches_hydrocarbon_diaxial_generic_caps_below() -> None:
    """A pure-hydrocarbon antiperiplanar coupling exceeds the generic ~10.26 Hz
    cap -- HLA captures the real ~11-13 Hz diaxial the generic relation cannot."""
    hla_anti = haasnoot_altona_3j(180.0, _TWO_CARBON_SUBS)
    assert hla_anti == pytest.approx(13.29, abs=0.1)
    assert hla_anti > karplus_3j(180.0) + 2.0  # generic 180 ~ 10.26


def test_hla_electronegativity_pulls_sugar_diaxial_toward_literature() -> None:
    """Electronegative substituents lower the antiperiplanar coupling: a sugar
    diaxial lands in the literature ~9-10 Hz window, below the generic cap."""
    bare = haasnoot_altona_3j(180.0)
    two_oxygen = haasnoot_altona_3j(180.0, _TWO_OXYGEN_SUBS)
    sugar = haasnoot_altona_3j(180.0, _SUGAR_DIAXIAL_SUBS)
    # Each electronegative oxygen reduces the antiperiplanar value.
    assert two_oxygen < bare
    # The full glucose-like site lands in the literature diaxial band, and the
    # correction brings it BELOW the generic 180-deg cap (toward ~9.3 Hz lit).
    assert 9.0 < sugar < 10.0
    assert sugar < karplus_3j(180.0)


def test_hla_substituent_sign_is_negligible_at_antiperiplanar() -> None:
    """At 180 deg the orientation sign xi barely matters (the curve is locally
    symmetric), so the recovered diaxial is robust to xi assignment."""
    plus = haasnoot_altona_3j(180.0, [(1.30, 1.0), (1.30, 1.0)])
    minus = haasnoot_altona_3j(180.0, [(1.30, -1.0), (1.30, -1.0)])
    assert plus == pytest.approx(minus, abs=0.05)


# --------------------------------------------------------------------------- #
# 2. Predictor threading                                                      #
# --------------------------------------------------------------------------- #


def test_generic_method_default_is_byte_identical() -> None:
    """use_karplus=True with the default method == explicit karplus_method=
    'generic' == prior Phase 38 behaviour (the generic provenance category)."""
    a = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_max_conformers=10
    )
    b = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_method="generic", karplus_max_conformers=10
    )
    assert a.couplings_hz == b.couplings_hz
    assert a.category_counts == b.category_counts
    assert a.category_counts.get(KARPLUS_CATEGORY_GENERIC)
    assert KARPLUS_CATEGORY_HAASNOOT_ALTONA not in a.category_counts


def test_hla_emits_its_own_provenance_category() -> None:
    on = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_method="haasnoot_altona",
        karplus_max_conformers=10,
    )
    assert on.category_counts.get(KARPLUS_CATEGORY_HAASNOOT_ALTONA)
    assert KARPLUS_CATEGORY_GENERIC not in on.category_counts
    assert "aliphatic_vicinal" not in on.category_counts  # flat value refined away


def test_hla_recovers_larger_hydrocarbon_diaxial_than_generic() -> None:
    """On a covalently locked pure-hydrocarbon diaxial (trans-decalin), HLA's
    per-conformer fidelity shows up as a larger recovered coupling than the
    generic relation -- and above the generic ~10.26 Hz cap."""
    g = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_method="generic", karplus_max_conformers=10
    )
    h = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_method="haasnoot_altona",
        karplus_max_conformers=10,
    )
    assert g.couplings_hz and h.couplings_hz
    assert max(h.couplings_hz) > max(g.couplings_hz)
    assert max(h.couplings_hz) > 10.5


def test_hla_is_deterministic() -> None:
    a = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_method="haasnoot_altona",
        karplus_max_conformers=10,
    )
    b = predict_proton_couplings_from_smiles(
        TRANS_DECALIN, use_karplus=True, karplus_method="haasnoot_altona",
        karplus_max_conformers=10,
    )
    assert a.couplings_hz == b.couplings_hz
    assert a.couplings_hz


def test_unknown_method_falls_back_to_generic_with_warning() -> None:
    res = predict_proton_couplings_from_smiles(
        "CCCC", use_karplus=True, karplus_method="bogus", karplus_max_conformers=6
    )
    assert res.couplings_hz  # still produced via the generic fallback
    assert res.category_counts.get(KARPLUS_CATEGORY_GENERIC)
    assert KARPLUS_CATEGORY_HAASNOOT_ALTONA not in res.category_counts
    assert any("falling back" in w.lower() for w in res.warnings)


def test_method_is_ignored_when_karplus_off() -> None:
    """REGRESSION: karplus_method never perturbs the topology-only default."""
    off_default = predict_proton_couplings_from_smiles("CCCC")
    off_hla = predict_proton_couplings_from_smiles(
        "CCCC", use_karplus=False, karplus_method="haasnoot_altona"
    )
    assert off_default.couplings_hz == off_hla.couplings_hz == [7.0]
    assert KARPLUS_CATEGORY_HAASNOOT_ALTONA not in off_hla.category_counts
    assert KARPLUS_CATEGORY_GENERIC not in off_hla.category_counts


# --------------------------------------------------------------------------- #
# 3. Bridge / unified / endpoint threading                                    #
# --------------------------------------------------------------------------- #


def test_bridge_threads_method_and_flips_provenance_note() -> None:
    base = dict(
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=[9.4, 8.1, 3.4],
    )
    hla = score_multiplets_against_candidates(
        MultipletJCouplingBridgeRequest(
            **base, use_karplus=True, karplus_method="haasnoot_altona",
            karplus_max_conformers=10,
        )
    )
    gen = score_multiplets_against_candidates(
        MultipletJCouplingBridgeRequest(**base, use_karplus=True, karplus_max_conformers=10)
    )
    off = score_multiplets_against_candidates(MultipletJCouplingBridgeRequest(**base))

    assert hla.metadata["karplus_method"] == "haasnoot_altona"
    assert "Haasnoot-Altona" in hla.notes[0]
    assert gen.metadata["karplus_method"] == "generic"
    assert "three-term Karplus" in gen.notes[0]
    # default off path still records the default method without claiming Karplus
    assert off.metadata["karplus_method"] == "generic"
    assert "no Karplus/3D" in off.notes[0]


def test_unified_threads_method_into_bridge_request() -> None:
    req = UnifiedCandidateConfidenceRequest(
        sample_id="k",
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=[9.4],
        multiplet_jcoupling_use_karplus=True,
        multiplet_jcoupling_karplus_method="haasnoot_altona",
        multiplet_jcoupling_max_conformers=9,
    )
    bridged = _bridge_multiplet_jcoupling_request(req)
    assert bridged.use_karplus is True
    assert bridged.karplus_method == "haasnoot_altona"
    assert bridged.karplus_max_conformers == 9


def test_jcoupling_endpoint_accepts_method(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'phase40_hla.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    payload = {
        "sample_id": "phase40-endpoint",
        "candidates": [{"name": "glucose", "smiles": BETA_D_GLUCOSE}],
        "observed_j_couplings_hz": [9.4, 8.1, 3.4],
        "use_karplus": True,
        "karplus_method": "haasnoot_altona",
        "karplus_max_conformers": 8,
    }
    headers = {"x-api-key": "test-key"}
    with TestClient(app) as client:
        res = client.post("/candidates/compare/jcoupling", headers=headers, json=payload)
        assert res.status_code == 200, res.text
        assert res.json()["metadata"]["karplus_method"] == "haasnoot_altona"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
