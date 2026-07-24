"""Unit tests for the Phase-C capability registry (pure; probes/env injected, no heavy deps)."""

from __future__ import annotations

import pytest

from nmrcheck.reaction_ml import (
    CAPABILITIES,
    CapabilityUnavailableError,
    all_capability_statuses,
    capability_status,
    require_capability,
    resolve_backend,
)

# A real R11 gate pass: `reaction_eval.gold_set_checksum` emits sha256:<64 hex>.
_GOLD = "sha256:3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f"
_EVIDENCE_OK = {
    "exit_code": 0,
    "gold_checksum": _GOLD,
    "model_version": "mpnn.v3",
}


def _probe_all(_module: str) -> bool:
    return True


def _probe_none(_module: str) -> bool:
    return False


def test_every_capability_is_default_off():
    for status in all_capability_statuses(probe=_probe_all, env={}):
        assert status.enabled is False
        assert status.active is False
        assert "default off" in status.reason


def test_unknown_capability_raises():
    with pytest.raises(KeyError):
        capability_status("nope", env={})


def test_flag_alone_is_not_enough_without_deps():
    status = capability_status(
        "retrosynthesis", probe=_probe_none, env={"MOLTRACE_REACTION_RETRO": "1"}
    )
    assert status.enabled is True
    assert status.available is False
    assert status.active is False
    assert "aizynthfinder" in str(status.missing_modules)
    assert "pip install" in status.reason


def test_forward_prediction_accepts_any_one_backend():
    # rxn4chemistry OR transformers satisfies the probe.
    only_transformers = capability_status(
        "forward_prediction",
        probe=lambda m: m == "transformers",
        env={"MOLTRACE_REACTION_FORWARD": "1"},
    )
    assert only_transformers.available is True
    assert only_transformers.active is True


def test_yield_gnn_requires_promotion_evidence():
    env = {"MOLTRACE_REACTION_YIELD_GNN": "1"}
    without = capability_status("yield_gnn", probe=_probe_all, env=env)
    assert without.enabled and without.available
    assert without.active is False  # flag + deps are NOT enough
    assert "evidence" in without.reason

    with_evidence = capability_status(
        "yield_gnn", probe=_probe_all, env=env, promotion_evidence=_EVIDENCE_OK
    )
    assert with_evidence.active is True
    assert with_evidence.provenance["promotion_model_version"] == "mpnn.v3"


@pytest.mark.parametrize(
    "evidence",
    [
        {"exit_code": 1, "gold_checksum": _GOLD, "model_version": "v"},  # blocked run
        {"exit_code": 0, "gold_checksum": "", "model_version": "v"},  # no gold checksum
        {"exit_code": 0, "gold_checksum": _GOLD, "model_version": " "},  # no version
        # `False == 0` in Python: a mis-mapped "passed" flag whose False means FAILURE
        # must never read as the gate's 0 exit code.
        {"exit_code": False, "gold_checksum": _GOLD, "model_version": "v"},
        {"exit_code": 0.0, "gold_checksum": _GOLD, "model_version": "v"},  # float, not int
        {"exit_code": "0", "gold_checksum": _GOLD, "model_version": "v"},  # string, not int
        # Truthy-but-fake digests: not the shape the gate emits.
        {"exit_code": 0, "gold_checksum": "sha256:abc", "model_version": "v"},
        {"exit_code": 0, "gold_checksum": "PASSED", "model_version": "v"},
        {"exit_code": 0, "gold_checksum": _GOLD.upper(), "model_version": "v"},  # not lower hex
        {"exit_code": 0, "gold_checksum": _GOLD, "model_version": 3},  # not a string
        {"exit_code": 0, "gold_checksum": _GOLD},  # version absent entirely
        [("exit_code", 0)],  # not a mapping at all
        None,
    ],
)
def test_invalid_promotion_evidence_blocks_activation(evidence):
    status = capability_status(
        "yield_gnn",
        probe=_probe_all,
        env={"MOLTRACE_REACTION_YIELD_GNN": "1"},
        promotion_evidence=evidence,
    )
    assert status.active is False


def test_resolve_backend_fallback_and_unavailable():
    # yield_gnn has a real fallback; retrosynthesis has none.
    fallback = resolve_backend("yield_gnn", probe=_probe_none, env={})
    assert fallback.backend == "fallback"
    assert "sklearn" in fallback.reason
    unavailable = resolve_backend("retrosynthesis", probe=_probe_none, env={})
    assert unavailable.backend == "unavailable"


def test_resolve_backend_heavy_with_full_governance():
    decision = resolve_backend(
        "yield_gnn",
        probe=_probe_all,
        env={"MOLTRACE_REACTION_YIELD_GNN": "1"},
        promotion_evidence=_EVIDENCE_OK,
    )
    assert decision.backend == "heavy"
    # The decision carries auditable provenance for the caller to persist.
    prov = decision.provenance
    assert prov["provenance"]["flag_env"] == "MOLTRACE_REACTION_YIELD_GNN"
    assert prov["provenance"]["probed_modules"] == {"torch": True}


def test_require_capability_raises_with_honest_reason():
    with pytest.raises(CapabilityUnavailableError, match="default off"):
        require_capability("sdl_execution", env={})


def test_sdl_needs_no_python_modules():
    status = capability_status("sdl_execution", probe=_probe_none, env={"MOLTRACE_REACTION_SDL": "on"})
    assert status.available is True  # gated by flag + driver, not by a package
    assert status.active is True


def test_registry_documents_fallbacks():
    for spec in CAPABILITIES.values():
        assert spec.fallback  # every capability states its fallback (or the absence of one)


def test_evidence_must_be_bound_to_the_gold_set_and_model_being_activated():
    """A genuine gate pass earned elsewhere must not unlock *this* activation."""

    env = {"MOLTRACE_REACTION_YIELD_GNN": "1"}
    other_gold = "sha256:" + "ab" * 32

    wrong_gold = capability_status(
        "yield_gnn",
        probe=_probe_all,
        env=env,
        promotion_evidence=_EVIDENCE_OK,
        expected_gold_checksum=other_gold,
    )
    assert wrong_gold.active is False
    assert "gold set" in wrong_gold.reason

    wrong_model = capability_status(
        "yield_gnn",
        probe=_probe_all,
        env=env,
        promotion_evidence=_EVIDENCE_OK,
        expected_model_version="mpnn.v4",
    )
    assert wrong_model.active is False
    assert "mpnn.v4" in wrong_model.reason

    bound = capability_status(
        "yield_gnn",
        probe=_probe_all,
        env=env,
        promotion_evidence=_EVIDENCE_OK,
        expected_gold_checksum=_GOLD,
        expected_model_version="mpnn.v3",
    )
    assert bound.active is True


def test_require_capability_propagates_evidence_binding():
    env = {"MOLTRACE_REACTION_YIELD_GNN": "1"}
    with pytest.raises(CapabilityUnavailableError):
        require_capability(
            "yield_gnn",
            probe=_probe_all,
            env=env,
            promotion_evidence=_EVIDENCE_OK,
            expected_model_version="mpnn.v9",
        )
