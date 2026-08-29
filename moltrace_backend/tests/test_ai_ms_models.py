"""Unit tests for the MS / structure-ranking pretrained models (Prompt 21).

Covers the CSI:FingerID wrapper (injected backend + graceful unavailability),
the DP4-AI posterior (reusing the in-house dp4_scoring), METLIN RT corroboration,
the calibrated fusion of orthogonal signals, Prompt 13 registration, and the
Prompt 7 verifier handoff (the arbiter). Runs on a CPU-only host (no SIRIUS /
METLIN install; injected fakes).
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.ai import (
    InMemoryRegistryStore,
    ModelRegistry,
    ModelRole,
    MSCandidate,
    MSModelsError,
    MSMSSpectrum,
    NMRCandidate,
    arbitrate,
    dp4_candidate_posterior,
    fuse_candidates,
    predict_msms_candidates,
    predict_retention_times,
    register_ms_models,
    rt_corroboration,
)


# --------------------------------------------------------------------------- #
# 1. CSI:FingerID wrapper
# --------------------------------------------------------------------------- #
def test_csi_fingerid_unavailable_without_backend() -> None:
    result = predict_msms_candidates(MSMSSpectrum(peaks=((100.0, 9.0),), precursor_mz=180.0))
    assert result.available is False
    assert result.candidates == ()
    assert result.warnings  # explains how to configure a backend


def test_csi_fingerid_injected_backend_ranks_candidates() -> None:
    def backend(spectrum):
        return [("CCC", -9.0), ("CCO", -5.0)]  # returned worst-first on purpose

    result = predict_msms_candidates(MSMSSpectrum(peaks=((100.0, 9.0),)), backend=backend, top_k=1)
    assert result.available is True
    assert len(result.candidates) == 1  # top_k respected
    top = result.candidates[0]
    assert top.smiles == "CCO" and top.rank == 1  # sorted by score desc
    assert top.inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"  # ethanol, via RDKit


def test_csi_fingerid_accepts_mscandidate_objects() -> None:
    def backend(spectrum):
        return [MSCandidate("c1ccccc1", 0.91, source="csi_fingerid")]

    result = predict_msms_candidates(MSMSSpectrum(peaks=((78.0, 1.0),)), backend=backend)
    assert result.candidates[0].smiles == "c1ccccc1"


# --------------------------------------------------------------------------- #
# 2. DP4-AI posterior (reuses nmrcheck.dp4_scoring)
# --------------------------------------------------------------------------- #
def test_dp4_posterior_prefers_matching_candidate() -> None:
    observed = [20.0, 60.0, 130.0]
    candidates = [
        NMRCandidate("match", (20.1, 60.2, 129.8), smiles="CCO"),
        NMRCandidate("decoy", (5.0, 90.0, 200.0), smiles="CCC"),
    ]
    posteriors = dp4_candidate_posterior(
        observed_shifts_ppm=observed, candidates=candidates, nucleus="13C"
    )
    by_id = {p.candidate_id: p for p in posteriors}
    assert by_id["match"].dp4_probability > by_id["decoy"].dp4_probability
    # calibrated: probabilities sum to 1.0 across the suite
    assert sum(p.dp4_probability for p in posteriors) == pytest.approx(1.0)
    assert by_id["match"].matched_peaks == 3


def test_dp4_posterior_empty_candidates() -> None:
    assert dp4_candidate_posterior(observed_shifts_ppm=[1.0], candidates=[], nucleus="1H") == []


# --------------------------------------------------------------------------- #
# 3. METLIN retention-time corroboration
# --------------------------------------------------------------------------- #
def test_rt_corroboration_downweights_inconsistent() -> None:
    weights = rt_corroboration({"A": 5.0, "B": 9.0}, observed_rt=5.0, tolerance_min=0.5)
    assert weights["A"] == pytest.approx(1.0)  # perfect match
    assert weights["B"] < 0.01  # far from observed -> strongly down-weighted


def test_rt_corroboration_abstains_when_unknown() -> None:
    assert rt_corroboration({"A": None}, observed_rt=5.0)["A"] == 1.0
    assert rt_corroboration({"A": 5.0}, observed_rt=None)["A"] == 1.0


def test_predict_retention_times_pluggable() -> None:
    assert predict_retention_times({"A": "CCO"}) == {"A": None}  # no predictor
    rts = predict_retention_times({"A": "CCO", "B": "CCC"}, predictor=lambda s: 3.0)
    assert rts == {"A": 3.0, "B": 3.0}


# --------------------------------------------------------------------------- #
# 4. Fusion (calibrated, decision-support only)
# --------------------------------------------------------------------------- #
def test_fuse_requires_a_signal() -> None:
    with pytest.raises(MSModelsError):
        fuse_candidates()


def test_fuse_is_calibrated_and_rt_downweights() -> None:
    # tie on DP4; RT corroboration alone must demote B
    fused = fuse_candidates(
        dp4={"A": 0.5, "B": 0.5},
        rt_weights={"A": 1.0, "B": 0.1},
        smiles={"A": "CCO", "B": "CCC"},
    )
    assert [f.candidate_id for f in fused] == ["A", "B"]  # A ranked first
    assert fused[0].combined_score > fused[1].combined_score
    assert sum(f.combined_score for f in fused) == pytest.approx(1.0)  # calibrated
    assert fused[1].signals["rt_corroboration"] == pytest.approx(0.1)


def test_absolute_msms_support_survives_the_fusion() -> None:
    """Min-max normalisation erases how good the MS evidence actually was.

    It maps the best candidate to 1.0 whatever its raw score, so a set whose CSI scores are
    two orders of magnitude worse fuses to byte-identical output. Measured before this: CSI
    {0.95, 0.60, 0.20} and {0.0095, 0.0060, 0.0020} both produced msms 1.0 and a combined
    score of 0.5921 for the leader. Relative ordering is the right thing for the blend --
    the raw scale is not comparable across runs -- but the absolute support has to survive
    somewhere, or nothing downstream can gate on "the MS evidence was weak".
    """

    dp4 = {"a": 0.5, "b": 0.3, "c": 0.2}
    strong = fuse_candidates(dp4=dp4, msms={"a": 0.95, "b": 0.60, "c": 0.20})[0]
    weak = fuse_candidates(dp4=dp4, msms={"a": 0.0095, "b": 0.0060, "c": 0.0020})[0]

    # The normalised blend is still relative, and still identical -- that part is by design.
    assert strong.signals["msms"] == weak.signals["msms"] == 1.0

    # The raw score is what tells them apart, and it must be there.
    assert strong.signals["msms_raw"] == pytest.approx(0.95)
    assert weak.signals["msms_raw"] == pytest.approx(0.0095)


def test_a_fusion_without_ms_says_so_rather_than_scoring_zero() -> None:
    """An absent signal and a signal that found nothing are different claims.

    ``signals`` carries a key only for signals present, so a consumer reading
    ``signals.get("msms", 0.0)`` gets 0.0 for a run where MS was never performed -- the same
    value it would get if MS had run and supported nothing.
    """

    only_nmr = fuse_candidates(dp4={"a": 0.6, "b": 0.4})[0]
    assert "msms" not in only_nmr.signals
    assert "msms_raw" not in only_nmr.signals
    assert any("MS/MS" in note for note in only_nmr.notes), only_nmr.notes

    with_ms = fuse_candidates(dp4={"a": 0.6, "b": 0.4}, msms={"a": 0.9, "b": 0.1})[0]
    assert not [note for note in with_ms.notes if "MS/MS" in note and "no" in note.lower()]


def test_fuse_renormalises_when_a_signal_is_missing() -> None:
    # A has both NMR + MS evidence; B has only NMR — weights renormalise per candidate
    fused = fuse_candidates(dp4={"A": 0.6, "B": 0.4}, msms={"A": -5.0})
    by_id = {f.candidate_id: f for f in fused}
    assert "msms" in by_id["A"].signals and "msms" not in by_id["B"].signals
    assert by_id["A"].combined_score > by_id["B"].combined_score
    assert sum(f.combined_score for f in fused) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 5. Prompt 13 registration
# --------------------------------------------------------------------------- #
def test_register_ms_models_registers_three_roles_with_version_and_sha() -> None:
    reg = ModelRegistry(InMemoryRegistryStore())
    entries = register_ms_models(
        reg,
        csi_version="5.8.0",
        csi_sha256="sha256:csi",
        rt_version="1.2.0",
        rt_sha256="sha256:rt",
        promote=True,
    )
    assert set(entries) == {ModelRole.CSI_FINGERID, ModelRole.RT_PREDICTOR, ModelRole.DP4_RANKER}
    assert entries[ModelRole.CSI_FINGERID].artifact_sha256 == "sha256:csi"
    # DP4 is code, not weights -> a deterministic content hash
    assert entries[ModelRole.DP4_RANKER].artifact_sha256.startswith("sha256:")
    # promoted -> resolvable as production
    assert reg.resolve(ModelRole.CSI_FINGERID).model_id == entries[ModelRole.CSI_FINGERID].model_id
    assert reg.resolve(ModelRole.DP4_RANKER) is not None


# --------------------------------------------------------------------------- #
# 6. Verifier handoff — the Prompt 7 verifier remains the arbiter
# --------------------------------------------------------------------------- #
def test_arbitrate_delegates_to_the_verifier() -> None:
    calls = {}

    def fake_verifier(spectrum, smiles, *, prior_confidence, options):
        calls["args"] = (spectrum, smiles, prior_confidence, options)
        return {"verdict": "consistent", "proposed_smiles": smiles}

    result = arbitrate("spectrum-stub", "CCO", prior_confidence=0.6, verifier=fake_verifier)
    assert result["verdict"] == "consistent"
    assert calls["args"] == ("spectrum-stub", "CCO", 0.6, None)
