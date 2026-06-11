"""Phase 41 — opt-in Boltzmann conformer-population weighting.

Phase 38/40 average each H-C-C-H dihedral *unweighted* across the ETKDG
ensemble; Phase 40 measured (and locked) the resulting failure: high-energy
ring-flipped conformers wash out the diagnostic ground-state diaxial, the
sugar blind spot is unfixed, and a more elaborate Karplus form (HLA) only
amplifies the artefact.  Phase 41 adds the missing piece —
``karplus_conformer_weighting='boltzmann'`` weights each conformer by
``exp(-(E - E_min)/RT)`` from its MMFF energy so the ground-state geometry
dominates.

This suite validates the **weighting maths** and the **contract threading**,
plus molecule-level anchors that it (a) stays byte-identical under the default
``'uniform'`` setting, (b) recovers a sugar diaxial toward its literature
window, and (c) keeps a mobile ring low (so discrimination is preserved, not
just inflated).  The full *corpus-level* recovery — clean separation restored,
β-D-galactose moved from 8.49 to ~10.1 — is measured and locked separately by
``tests/test_phase41_boltzmann_corpus.py``.
"""

from __future__ import annotations

import math

import pytest

from nmrcheck.jcoupling_prediction import (
    BOLTZMANN_RT_KCAL_MOL,
    KARPLUS_CATEGORY_GENERIC,
    _boltzmann_weights,
    predict_proton_couplings_from_smiles,
)
from nmrcheck.models import (
    CandidateInput,
    MultipletJCouplingBridgeRequest,
    UnifiedCandidateConfidenceRequest,
)
from nmrcheck.multiplet_jcoupling_bridge import score_multiplets_against_candidates
from nmrcheck.unified_confidence import _bridge_multiplet_jcoupling_request

# beta-D-galactopyranose: the Phase 40 worst case (generic/uniform 8.49 Hz vs
# literature ~9.9).  Boltzmann weighting is expected to recover it.
BETA_D_GALACTOSE = "OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@H]1O"
# beta-D-glucopyranose: a locked-chair sugar (generic/uniform ~9.59 Hz).
BETA_D_GLUCOSE = "OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O"
# Cyclohexane: freely ring-flipping -> the diaxial must stay *averaged away*
# even under Boltzmann weighting (its two chairs are degenerate).
CYCLOHEXANE = "C1CCCCC1"
ETHANOL = "CCO"


def _max_generic(smiles: str, weighting: str | None) -> float | None:
    kwargs: dict = {"use_karplus": True, "karplus_method": "generic"}
    if weighting is not None:
        kwargs["karplus_conformer_weighting"] = weighting
    result = predict_proton_couplings_from_smiles(smiles, **kwargs)
    js = [d.j_hz for d in result.details if d.category == KARPLUS_CATEGORY_GENERIC]
    return max(js) if js else None


# --------------------------------------------------------------------------- #
# The weighting maths (pure function).
# --------------------------------------------------------------------------- #
def test_boltzmann_weights_degenerate_energies_equal_uniform() -> None:
    """Equal energies => equal weights (recovers the uniform mean)."""

    w = _boltzmann_weights([3.0, 3.0, 3.0, 3.0])
    assert w is not None
    assert all(abs(wi - 0.25) < 1e-12 for wi in w)
    assert abs(math.fsum(w) - 1.0) < 1e-12


def test_boltzmann_weights_favor_the_low_energy_conformer() -> None:
    """A conformer several kcal/mol below the rest dominates the population."""

    w = _boltzmann_weights([0.0, 5.0, 5.0])
    assert w is not None
    # exp(-5/0.5925) ~ 2e-4, so the ground state carries essentially all weight.
    assert w[0] > 0.99
    assert w[0] > 100 * w[1]
    assert abs(math.fsum(w) - 1.0) < 1e-12
    # Explicit Boltzmann ratio sanity for the two excited conformers.
    assert abs(w[1] - w[2]) < 1e-12
    assert w[1] == pytest.approx(math.exp(-5.0 / BOLTZMANN_RT_KCAL_MOL) * w[0], rel=1e-9)


def test_boltzmann_weights_reject_unusable_energies() -> None:
    """Empty / non-finite energies return None so the caller uses uniform."""

    assert _boltzmann_weights([]) is None
    assert _boltzmann_weights([0.0, float("inf")]) is None
    assert _boltzmann_weights([0.0, float("nan")]) is None


# --------------------------------------------------------------------------- #
# Predictor-level behaviour.
# --------------------------------------------------------------------------- #
def test_uniform_default_is_byte_identical() -> None:
    """The default weighting is 'uniform' and equals omitting the argument."""

    default = predict_proton_couplings_from_smiles(BETA_D_GLUCOSE, use_karplus=True)
    explicit = predict_proton_couplings_from_smiles(
        BETA_D_GLUCOSE, use_karplus=True, karplus_conformer_weighting="uniform"
    )
    assert default.couplings_hz == explicit.couplings_hz
    assert [d.j_hz for d in default.details] == [d.j_hz for d in explicit.details]
    # And it is a plausible locked-chair value (~9.59 Hz measured).
    assert 9.0 <= max(d.j_hz for d in default.details if d.category == KARPLUS_CATEGORY_GENERIC) <= 10.0


def test_boltzmann_recovers_sugar_diaxial_toward_literature() -> None:
    """β-D-galactose: Boltzmann weighting lifts the diaxial toward ~9.9 Hz.

    Under uniform averaging the generic relation gives ~8.49 Hz (the Phase 40
    blind spot); Boltzmann weighting moves it to ~10.1 Hz, on the literature
    value, because the ground-state ⁴C₁ chair stops being diluted by
    high-energy ring-flipped conformers.
    """

    uni = _max_generic(BETA_D_GALACTOSE, "uniform")
    boltz = _max_generic(BETA_D_GALACTOSE, "boltzmann")
    assert uni is not None and boltz is not None
    assert uni < 9.0, f"uniform galactose {uni} unexpectedly high (Phase 40 was 8.49)"
    assert boltz >= 9.5, f"Boltzmann galactose {boltz} did not reach the literature window"
    assert (boltz - uni) >= 1.0, f"Boltzmann gain {(boltz - uni):.2f} Hz too small (measured ~1.6)"


def test_boltzmann_keeps_mobile_ring_averaged() -> None:
    """Cyclohexane: Boltzmann weighting must NOT inflate a freely-flipping ring.

    Its two chairs are degenerate, so the population stays split and the
    diaxial keeps averaging out — the property that preserves the
    locked-vs-mobile discrimination (contrast HLA/uniform, which ballooned it).
    """

    uni = _max_generic(CYCLOHEXANE, "uniform")
    boltz = _max_generic(CYCLOHEXANE, "boltzmann")
    assert uni is not None and boltz is not None
    assert boltz < 8.0, f"Boltzmann cyclohexane {boltz} ballooned out of the averaged regime"


def test_boltzmann_is_deterministic() -> None:
    """Fixed seed => byte-identical Boltzmann-weighted couplings across runs."""

    def run() -> tuple:
        r = predict_proton_couplings_from_smiles(
            BETA_D_GALACTOSE, use_karplus=True, karplus_conformer_weighting="boltzmann"
        )
        return tuple(sorted(round(d.j_hz, 4) for d in r.details))

    assert run() == run()


def test_unknown_weighting_falls_back_to_uniform_with_warning() -> None:
    """A bogus weighting warns and reproduces the uniform result (no crash)."""

    bogus = predict_proton_couplings_from_smiles(
        BETA_D_GALACTOSE, use_karplus=True, karplus_conformer_weighting="nonsense"
    )
    uniform = predict_proton_couplings_from_smiles(
        BETA_D_GALACTOSE, use_karplus=True, karplus_conformer_weighting="uniform"
    )
    assert any("conformer_weighting" in w for w in bogus.warnings)
    assert bogus.couplings_hz == uniform.couplings_hz


def test_weighting_is_ignored_when_karplus_off() -> None:
    """With use_karplus=False the weighting is moot: no refinement, no warning."""

    off = predict_proton_couplings_from_smiles(
        ETHANOL, use_karplus=False, karplus_conformer_weighting="boltzmann"
    )
    plain = predict_proton_couplings_from_smiles(ETHANOL)
    assert off.couplings_hz == plain.couplings_hz
    assert not any("conformer_weighting" in w for w in off.warnings)
    assert not any(d.category == KARPLUS_CATEGORY_GENERIC for d in off.details)


# --------------------------------------------------------------------------- #
# Contract threading: bridge / unified / endpoint.
# --------------------------------------------------------------------------- #
def test_bridge_threads_weighting_and_flips_note() -> None:
    base = dict(
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=[9.4, 8.1, 3.4],
    )
    boltz = score_multiplets_against_candidates(
        MultipletJCouplingBridgeRequest(
            **base, use_karplus=True, karplus_conformer_weighting="boltzmann",
            karplus_max_conformers=10,
        )
    )
    uni = score_multiplets_against_candidates(
        MultipletJCouplingBridgeRequest(**base, use_karplus=True, karplus_max_conformers=10)
    )
    assert boltz.metadata["karplus_conformer_weighting"] == "boltzmann"
    assert any("Boltzmann-weighted" in n for n in boltz.notes)
    assert uni.metadata["karplus_conformer_weighting"] == "uniform"
    assert any("unweighted" in n for n in uni.notes)


def test_unified_threads_weighting_into_bridge_request() -> None:
    req = UnifiedCandidateConfidenceRequest(
        sample_id="k",
        candidates=[CandidateInput(name="glucose", smiles=BETA_D_GLUCOSE)],
        observed_j_couplings_hz=[9.4],
        multiplet_jcoupling_use_karplus=True,
        multiplet_jcoupling_conformer_weighting="boltzmann",
        multiplet_jcoupling_max_conformers=9,
    )
    bridged = _bridge_multiplet_jcoupling_request(req)
    assert bridged.use_karplus is True
    assert bridged.karplus_conformer_weighting == "boltzmann"
    assert bridged.karplus_max_conformers == 9


def test_jcoupling_endpoint_accepts_weighting(client, api_headers) -> None:
    payload = {
        "sample_id": "phase41-endpoint",
        "candidates": [{"name": "galactose", "smiles": BETA_D_GALACTOSE}],
        "observed_j_couplings_hz": [9.9, 8.1, 3.4],
        "use_karplus": True,
        "karplus_conformer_weighting": "boltzmann",
        "karplus_max_conformers": 8,
    }
    headers = api_headers
    with client:
        res = client.post("/candidates/compare/jcoupling", headers=headers, json=payload)
        assert res.status_code == 200, res.text
        assert res.json()["metadata"]["karplus_conformer_weighting"] == "boltzmann"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
