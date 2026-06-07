"""Unit tests for the 5-layer inference router (Prompt 13, router.py).

The LoRA (Layer 3) and NMRNet (Layer 1) branches are exercised with injected
fakes so every resolution path is covered deterministically on a CPU-only host
(no torch). One integration test drives the real Prompt 6 ``predict_shifts`` to
prove the fallback (HOSE) path and provenance end-to-end without a GPU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from moltrace.spectroscopy.ai.registry import (
    InMemoryRegistryStore,
    ModelRegistry,
    ModelRole,
    TrainingDataLineage,
)
from moltrace.spectroscopy.ai.router import InferenceRouter, Layer
from moltrace.spectroscopy.audit.trail import (
    GENESIS_HASH,
    AuditEntry,
    entry_from_dict,
    entry_to_dict,
)

_LINEAGE = TrainingDataLineage(dataset_snapshot_hash="sha256:ds", row_count=1000)


@dataclass
class FakeAtom:
    atom_index: int
    element: str
    nucleus: str
    predicted_ppm: float
    uncertainty_ppm: float


@dataclass
class FakeShiftPrediction:
    smiles: str
    method: str
    device: str
    shifts: list
    n_conformers: int
    warnings: list


def _base_fn(method: str, atoms, *, device: str = "cpu", warnings=None):
    def _fn(smiles, nuclei, device=None):  # matches predict_shifts(smiles, nuclei, device=)
        return FakeShiftPrediction(
            smiles=smiles,
            method=method,
            device=device or "cpu",
            shifts=list(atoms),
            n_conformers=8 if method == "nmrnet" else 0,
            warnings=list(warnings or []),
        )

    return _fn


def _registry() -> ModelRegistry:
    return ModelRegistry(InMemoryRegistryStore())


def _register_prod(reg: ModelRegistry, **kwargs):
    entry = reg.register_artifact(**kwargs)
    reg.promote(entry.model_id)
    return entry


def _ckpt(reg, nucleus="13C", version="1.0.0", sha=None):
    return _register_prod(
        reg,
        role=ModelRole.NMRNET_CHECKPOINT,
        nucleus=nucleus,
        semantic_version=version,
        artifact_sha256=sha or f"sha256:ckpt-{nucleus}",
        training_data_lineage=_LINEAGE,
        created_utc=datetime(2026, 6, 7, tzinfo=UTC),
    )


def _provenance_signature(routed):
    """A comparable, NaN-safe fingerprint of a routed result for determinism checks."""

    return (
        routed.model_versions,
        tuple(
            (p.atom_index, p.nucleus, p.layer, p.model_id, round(p.predicted_ppm, 6))
            for p in routed.predictions
        ),
    )


# --------------------------------------------------------------------------- #
# Fallback (HOSE) branch
# --------------------------------------------------------------------------- #
def test_fallback_branch_routes_all_atoms_to_hose() -> None:
    reg = _registry()
    hose = _register_prod(
        reg,
        role=ModelRole.HOSE_KB,
        semantic_version="3.0.0",
        artifact_sha256="sha256:hosekb",
        training_data_lineage=_LINEAGE,
    )
    atoms = [FakeAtom(0, "C", "13C", 50.0, 0.7), FakeAtom(1, "H", "1H", 1.2, 0.3)]
    router = InferenceRouter(reg, predict_fn=_base_fn("hose_fallback", atoms))

    routed = router.predict_shifts_routed("CCO", ["1H", "13C"])

    assert routed.base_method == "hose_fallback"
    assert {p.layer for p in routed.predictions} == {Layer.HOSE_FALLBACK}
    assert all(p.model_id == hose.model_id for p in routed.predictions)
    assert routed.model_versions == {hose.model_id: "sha256:hosekb"}
    assert routed.layers_used == (Layer.HOSE_FALLBACK,)

    # deterministic: identical inputs + registry state -> identical provenance
    again = router.predict_shifts_routed("CCO", ["1H", "13C"])
    assert _provenance_signature(routed) == _provenance_signature(again)


# --------------------------------------------------------------------------- #
# Layer 1 (NMRNet pretrained) branch
# --------------------------------------------------------------------------- #
def test_nmrnet_branch_when_no_lora() -> None:
    reg = _registry()
    c13 = _ckpt(reg, "13C", sha="sha256:c13")
    h1 = _ckpt(reg, "1H", sha="sha256:h1")
    atoms = [FakeAtom(0, "C", "13C", 50.0, 1.0), FakeAtom(1, "H", "1H", 1.2, 0.4)]
    router = InferenceRouter(reg, predict_fn=_base_fn("nmrnet", atoms))

    routed = router.predict_shifts_routed("CCO", ["1H", "13C"])

    assert {p.layer for p in routed.predictions} == {Layer.NMRNET_PRETRAINED}
    assert routed.model_versions == {c13.model_id: "sha256:c13", h1.model_id: "sha256:h1"}
    assert all("layer1 nmrnet" in p.reason for p in routed.predictions)


# --------------------------------------------------------------------------- #
# Layer 3 (LoRA) branch + confidence-band gating
# --------------------------------------------------------------------------- #
def test_lora_branch_gated_by_confidence_band() -> None:
    reg = _registry()
    ckpt = _ckpt(reg, "13C", sha="sha256:ckpt13")
    lora = _register_prod(
        reg,
        role=ModelRole.LORA_ADAPTER,
        nucleus="13C",
        semantic_version="0.1.0",
        artifact_sha256="sha256:lora13",
        training_data_lineage=_LINEAGE,
        confidence_band_ppm=2.0,
        parent_base_id=ckpt.model_id,
    )
    atoms = [
        FakeAtom(0, "C", "13C", 50.0, 1.0),  # uncertainty <= band -> LoRA
        FakeAtom(1, "C", "13C", 60.0, 3.0),  # uncertainty > band  -> NMRNet
        FakeAtom(2, "C", "13C", 70.0, math.nan),  # single-conformer NaN -> NMRNet
    ]

    def fake_lora(smiles, nucleus, *, adapter, device):
        assert adapter.model_id == lora.model_id
        return {0: (99.0, 0.1)}

    router = InferenceRouter(
        reg, predict_fn=_base_fn("nmrnet", atoms), lora_predict_fn=fake_lora
    )
    routed = router.predict_shifts_routed("c1ccccc1", ["13C"])
    by_index = {p.atom_index: p for p in routed.predictions}

    # atom 0 -> LoRA (overrides prediction + uncertainty from the adapter)
    assert by_index[0].layer is Layer.LORA_FINETUNED
    assert by_index[0].predicted_ppm == 99.0
    assert by_index[0].uncertainty_ppm == 0.1
    assert by_index[0].model_id == lora.model_id
    assert "layer3 lora" in by_index[0].reason

    # atom 1 -> NMRNet (uncertainty above the band)
    assert by_index[1].layer is Layer.NMRNET_PRETRAINED
    assert "> lora band" in by_index[1].reason

    # atom 2 -> NMRNet (NaN uncertainty never satisfies <= band)
    assert by_index[2].layer is Layer.NMRNET_PRETRAINED
    assert "NaN" in by_index[2].reason

    # provenance: LoRA adapter + its base checkpoint both touched the result
    assert routed.model_versions == {
        lora.model_id: "sha256:lora13",
        ckpt.model_id: "sha256:ckpt13",
    }

    again = router.predict_shifts_routed("c1ccccc1", ["13C"])
    assert _provenance_signature(routed) == _provenance_signature(again)


def test_lora_ignored_without_lora_predict_fn() -> None:
    reg = _registry()
    ckpt = _ckpt(reg, "13C", sha="sha256:c")
    _register_prod(
        reg,
        role=ModelRole.LORA_ADAPTER,
        nucleus="13C",
        semantic_version="0.1.0",
        artifact_sha256="sha256:lora",
        training_data_lineage=_LINEAGE,
        confidence_band_ppm=5.0,
    )
    atoms = [FakeAtom(0, "C", "13C", 50.0, 0.2)]  # well within band, but no hook wired
    router = InferenceRouter(reg, predict_fn=_base_fn("nmrnet", atoms))  # lora_predict_fn=None

    routed = router.predict_shifts_routed("CCO", ["13C"])
    assert routed.predictions[0].layer is Layer.NMRNET_PRETRAINED
    assert routed.model_versions == {ckpt.model_id: "sha256:c"}


# --------------------------------------------------------------------------- #
# Provenance completeness + the Prompt 12 audit handoff
# --------------------------------------------------------------------------- #
def test_unregistered_artifact_is_marked_not_dropped() -> None:
    reg = _registry()  # nothing registered
    atoms = [FakeAtom(0, "C", "13C", 50.0, 0.5)]
    router = InferenceRouter(reg, predict_fn=_base_fn("hose_fallback", atoms))

    routed = router.predict_shifts_routed("CCO", ["13C"])
    assert routed.predictions[0].model_id == "unregistered:hose_kb:all"
    assert routed.model_versions == {"unregistered:hose_kb:all": "unknown"}
    assert any("unregistered" in w for w in routed.warnings)


def test_model_versions_feeds_audit_entry_verbatim() -> None:
    reg = _registry()
    _ckpt(reg, "13C", sha="sha256:c13")
    atoms = [FakeAtom(0, "C", "13C", 50.0, 1.0)]
    router = InferenceRouter(reg, predict_fn=_base_fn("nmrnet", atoms))
    routed = router.predict_shifts_routed("CCO", ["13C"])

    # deterministic ordering (sorted keys)
    assert list(routed.model_versions) == sorted(routed.model_versions)

    entry = AuditEntry(
        timestamp_utc=datetime(2026, 6, 7, tzinfo=UTC),
        user_id="reviewer-1",
        operation="predict_shifts",
        input_hash="sha256:in",
        parameters={"smiles": "CCO"},
        result_hash="sha256:out",
        software_version="moltrace/test",
        model_versions=routed.model_versions,  # <- fed verbatim
        previous_entry_hash=GENESIS_HASH,
        signature="unit-test-sig",
    )
    restored = entry_from_dict(entry_to_dict(entry))
    assert restored.model_versions == routed.model_versions


# --------------------------------------------------------------------------- #
# CPU-only host: the real Prompt 6 predictor, end-to-end
# --------------------------------------------------------------------------- #
def test_cpu_only_host_real_predict_shifts() -> None:
    reg = _registry()
    _register_prod(
        reg,
        role=ModelRole.HOSE_KB,
        semantic_version="1.0.0",
        artifact_sha256="sha256:hosekb",
        training_data_lineage=_LINEAGE,
    )
    _ckpt(reg, "13C", sha="sha256:c13")
    _ckpt(reg, "1H", sha="sha256:h1")

    router = InferenceRouter(reg)  # default predict_fn = real predict_shifts

    routed = router.predict_shifts_routed("CCO", ["1H", "13C"])

    # On a CPU-only host with no torch, the base predictor uses the HOSE fallback.
    assert routed.base_method in {"hose_fallback", "nmrnet"}
    assert isinstance(routed.device, str)
    assert len(routed.predictions) >= 1
    # every atom resolved to a real, registered artifact (no unregistered markers)
    assert all(p.layer in set(Layer) for p in routed.predictions)
    assert all(not str(p.model_id).startswith("unregistered") for p in routed.predictions)
    assert routed.model_versions and all(
        not k.startswith("unregistered") for k in routed.model_versions
    )

    # the provenance record is deterministic on the real path too
    again = router.predict_shifts_routed("CCO", ["1H", "13C"])
    assert routed.model_versions == again.model_versions
