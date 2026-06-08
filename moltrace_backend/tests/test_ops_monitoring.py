"""Unit tests for the MLOps monitoring + deployment gate (Prompt 18, ops/).

Covers the four acceptance criteria:

1. drift metrics (input / confidence / override / latency) computed + alerted;
2. the lineage dashboard reads the Prompt 13 registry;
3. the CI deployment gate fails closed unless all four checks pass; and
4. the versioned output contract is documented / pinned for downstream modules.

Everything runs on a CPU-only host: the observability sink, the pager, and every
data input are injected fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from moltrace.spectroscopy.ai.registry import (
    ModelRegistry,
    ModelRole,
    TrainingDataLineage,
)
from moltrace.spectroscopy.audit.trail import AuditRecorder, InMemoryAuditLog, static_key
from moltrace.spectroscopy.eval.harness import GoldMetricVector
from moltrace.spectroscopy.feedback.capture import FeedbackEvent, FeedbackVerdict, OutputKind
from moltrace.spectroscopy.infra.contract import SCHEMA_VERSION, build_spectracheck_contract
from moltrace.spectroscopy.ops.deployment_gate import main as gate_cli
from moltrace.spectroscopy.ops.deployment_gate import self_check
from moltrace.spectroscopy.ops.monitoring import (
    ConfidenceSample,
    DriftMetric,
    GateCheck,
    MonitorStatus,
    check_audit_chain,
    check_data_leakage,
    check_dominance,
    confidence_drift,
    evaluate_deployment_gate,
    input_drift,
    latency_drift,
    lineage_dashboard,
    numeric_psi,
    override_rate_drift,
    percentile,
    population_stability_index,
    production_monitors,
    run_deployment_gate,
    snapshot_distributions,
)

_NOW = "2026-06-01T00:00:00+00:00"
_RECENT = "2026-05-20T00:00:00+00:00"
_PRIOR = "2026-04-20T00:00:00+00:00"
_KEY = b"k" * 32
_VERSIONS = {"adapter": "lora_adapter:13C:1.0.0"}


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@dataclass
class _Snap:
    """Duck-typed stand-in for a Prompt 15 training Snapshot."""

    nucleus_distribution: dict[str, float] = field(default_factory=dict)
    field_distribution: dict[str, float] = field(default_factory=dict)
    solvent_distribution: dict[str, float] = field(default_factory=dict)
    gold_checksum: str = ""
    record_hashes: tuple[str, ...] = ()


def _gmv(**overrides: float) -> GoldMetricVector:
    base: dict[str, Any] = dict(
        top1_accuracy=0.85,
        top3_accuracy=0.95,
        shift_mae_1h=0.10,
        shift_mae_13c=1.50,
        ece=0.06,
        false_confirmation_rate=0.05,
        recall_at_k=0.90,
        uncertainty_auroc=0.80,
        robustness=0.90,
        reviewer_agreement_rate=0.92,
        latency_p50_ms=400.0,
        latency_p95_ms=900.0,
    )
    base.update(overrides)
    return GoldMetricVector(**base)


def _event(verdict: FeedbackVerdict, created_utc: str, *, correction: bool = False) -> FeedbackEvent:
    return FeedbackEvent(
        output_kind=OutputKind.PREDICTED_SHIFT,
        output_ref=f"o:{created_utc}:{verdict}",
        verdict=verdict,
        model_versions=_VERSIONS,
        record_hash=f"r:{created_utc}" if correction else None,
        corrected_value={"ppm": 1.0} if correction else None,
        created_utc=created_utc,
    )


def _valid_audit_log() -> InMemoryAuditLog:
    recorder = AuditRecorder(log=InMemoryAuditLog(), key_provider=static_key(_KEY))
    recorder.record(operation="a", user_id="u", input_obj={"x": 1}, result_obj={"y": 2})
    recorder.record(operation="b", user_id="u", input_obj={"x": 3}, result_obj={"y": 4})
    return recorder.log  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Criterion 1: drift metrics (input / confidence / override / latency)
# --------------------------------------------------------------------------- #
def test_population_stability_index_bands():
    same = population_stability_index({"1H": 80, "13C": 20}, {"1H": 80, "13C": 20})
    moderate = population_stability_index({"1H": 80, "13C": 20}, {"1H": 65, "13C": 35})
    severe = population_stability_index({"1H": 80, "13C": 20}, {"1H": 20, "13C": 80})
    new_chem = population_stability_index({"1H": 100}, {"1H": 50, "19F": 50})

    assert same == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < moderate < severe
    assert severe > 0.25  # significant shift
    assert new_chem > severe  # brand-new chemistry the model never saw


def test_numeric_psi_detects_shift():
    expected = [float(i) for i in range(100)]
    assert numeric_psi(expected, expected) == pytest.approx(0.0, abs=1e-9)
    shifted = [v + 200.0 for v in expected]
    assert numeric_psi(expected, shifted) > 0.25


def test_input_drift_from_snapshot():
    snap = _Snap(
        nucleus_distribution={"1H": 700, "13C": 300},
        field_distribution={"400": 600, "600": 400},
        solvent_distribution={"CDCl3": 800, "DMSO": 200},
    )
    expected = snapshot_distributions(snap)
    assert set(expected) == {"nucleus", "field", "solvent"}

    # Live data dominated by a solvent the training set barely saw -> high PSI.
    live = {
        "nucleus": {"1H": 700, "13C": 300},  # unchanged
        "field": {"400": 600, "600": 400},  # unchanged
        "solvent": {"CDCl3": 100, "DMSO": 900},  # flipped
    }
    metrics = {m.name: m for m in input_drift(expected, live)}
    assert metrics["input_drift.nucleus"].status is MonitorStatus.OK
    assert metrics["input_drift.solvent"].status is MonitorStatus.BREACH


def test_confidence_drift_uncertainty_and_grounding():
    samples = (
        # prior window: low uncertainty, high grounding
        [ConfidenceSample(_PRIOR, uncertainty=0.10, grounding=0.90) for _ in range(5)]
        # recent window: high uncertainty, low grounding -> both degrade
        + [ConfidenceSample(_RECENT, uncertainty=0.40, grounding=0.60) for _ in range(5)]
    )
    metrics = {m.name: m for m in confidence_drift(samples, now_utc=_NOW)}
    assert metrics["confidence_drift.uncertainty"].value == pytest.approx(0.30)
    assert metrics["confidence_drift.uncertainty"].status is MonitorStatus.BREACH
    assert metrics["confidence_drift.grounding"].value == pytest.approx(0.30)
    assert metrics["confidence_drift.grounding"].status is MonitorStatus.BREACH


def test_override_rate_drift_rising_means_degrading():
    events = (
        [_event(FeedbackVerdict.UP, _PRIOR) for _ in range(8)]
        + [_event(FeedbackVerdict.DOWN, _PRIOR) for _ in range(2)]  # prior override 0.2
        + [_event(FeedbackVerdict.UP, _RECENT) for _ in range(2)]
        + [_event(FeedbackVerdict.DOWN, _RECENT) for _ in range(8)]  # recent override 0.8
    )
    metric = override_rate_drift(events, now_utc=_NOW)
    assert metric is not None
    assert metric.value == pytest.approx(0.6)  # 0.8 - 0.2
    assert metric.status is MonitorStatus.BREACH


def test_override_rate_drift_none_without_two_windows():
    events = [_event(FeedbackVerdict.DOWN, _RECENT) for _ in range(3)]
    assert override_rate_drift(events, now_utc=_NOW) is None


def test_percentile_and_latency_drift():
    assert percentile([10, 20, 30, 40], 50) == pytest.approx(25.0)
    latencies = [100.0] * 18 + [5000.0] * 2
    metrics = {m.name: m for m in latency_drift(latencies, slo_p95_ms=2000.0, slo_p50_ms=800.0)}
    assert metrics["latency.p95_ms"].status is MonitorStatus.BREACH  # 5000 > 2000
    assert metrics["latency.p50_ms"].status is MonitorStatus.OK  # 100 < 800


def test_production_monitors_aggregates_emits_and_pages():
    emitted: list[str] = []
    paged: list[DriftMetric] = []

    report = production_monitors(
        expected_distributions={"solvent": {"CDCl3": 900, "DMSO": 100}},
        live_distributions={"solvent": {"CDCl3": 100, "DMSO": 900}},  # breach
        latencies_ms=[100.0] * 18 + [9000.0] * 2,  # p95 breach
        slo_p95_ms=2000.0,
        now_utc=_NOW,
        emit_fn=lambda name, payload: emitted.append(name),
        alert_fn=lambda metric: paged.append(metric),
    )

    assert report.status is MonitorStatus.BREACH
    assert "input_drift.solvent" in report.breached
    assert "latency.p95_ms" in report.breached
    # every metric emitted to observability; only breaches paged.
    assert "input_drift.solvent" in emitted and "latency.p50_ms" in emitted
    assert {m.name for m in paged} == set(report.breached)


def test_production_monitors_clean_is_ok():
    report = production_monitors(
        expected_distributions={"nucleus": {"1H": 80, "13C": 20}},
        live_distributions={"nucleus": {"1H": 80, "13C": 20}},
        latencies_ms=[100.0, 110.0, 120.0],
        slo_p95_ms=2000.0,
    )
    assert report.status is MonitorStatus.OK
    assert report.breached == ()


# --------------------------------------------------------------------------- #
# Criterion 2: lineage dashboard reads the registry
# --------------------------------------------------------------------------- #
def _registry_with_production_model() -> tuple[ModelRegistry, str]:
    registry = ModelRegistry()
    lineage = TrainingDataLineage(
        dataset_snapshot_hash="sha256:snap-1",
        row_count=1200,
        dataset_tag="in-house-2026Q2",
        source="in_house",
    )
    entry = registry.register_artifact(
        role=ModelRole.LORA_ADAPTER,
        nucleus="13C",
        semantic_version="1.0.0",
        artifact_sha256="sha256:adapter-abc",
        training_data_lineage=lineage,
        metric_snapshot={"top1_accuracy": 0.91, "shift_mae_13c": 1.40},
    )
    registry.promote(entry.model_id, reason="dominance gate passed")
    return registry, entry.model_id


def test_lineage_dashboard_reads_production_models():
    registry, model_id = _registry_with_production_model()
    dashboard = lineage_dashboard(registry, drift_status={model_id: "ok"})

    assert len(dashboard.rows) == 1
    row = dashboard.rows[0]
    assert row.model_id == model_id
    assert row.semantic_version == "1.0.0"
    assert row.training_snapshot_hash == "sha256:snap-1"
    assert row.metric_vector["top1_accuracy"] == pytest.approx(0.91)
    assert row.promotion_reason == "dominance gate passed"
    assert row.promoted_utc is not None
    assert row.drift_status == "ok"


def test_lineage_dashboard_excludes_non_production():
    registry = ModelRegistry()
    lineage = TrainingDataLineage(dataset_snapshot_hash="sha256:snap-x", row_count=10)
    registry.register_artifact(
        role=ModelRole.LORA_ADAPTER,
        nucleus="1H",
        semantic_version="0.1.0",
        artifact_sha256="sha256:cand",
        training_data_lineage=lineage,
    )  # stays a candidate
    dashboard = lineage_dashboard(registry)
    assert dashboard.rows == ()


# --------------------------------------------------------------------------- #
# Criterion 3: deployment gate fails closed unless all four checks pass
# --------------------------------------------------------------------------- #
def test_check_dominance():
    incumbent = _gmv()
    better = _gmv(top1_accuracy=0.90)  # strictly better, no regression
    assert check_dominance(better, incumbent).passed is True
    # safety-critical regression (more false confirmations) blocks even with a gain.
    unsafe = _gmv(top1_accuracy=0.95, false_confirmation_rate=0.10)
    assert check_dominance(unsafe, incumbent).passed is False
    # no incumbent -> first model promotable; no candidate -> fail closed.
    assert check_dominance(better, None).passed is True
    assert check_dominance(None, incumbent).passed is False


def test_check_audit_chain():
    log = _valid_audit_log()
    assert check_audit_chain(log).passed is True  # keyless link check
    assert check_audit_chain(log, key=_KEY).passed is True  # + signatures
    assert check_audit_chain(log, key=b"x" * 32).passed is False  # wrong key -> tamper
    assert check_audit_chain(None).passed is False  # no provenance -> fail closed


def test_check_data_leakage():
    clean = _Snap(gold_checksum="sha256:gold", record_hashes=("h1", "h2", "h3"))
    assert check_data_leakage(
        clean, gold_checksum="sha256:gold", holdout_hashes={"hX", "hY"}
    ).passed is True
    leaked = _Snap(gold_checksum="sha256:gold", record_hashes=("h1", "hX"))
    assert check_data_leakage(
        leaked, gold_checksum="sha256:gold", holdout_hashes={"hX"}
    ).passed is False
    # snapshot bound to a different gold set, or missing -> fail closed.
    assert check_data_leakage(
        clean, gold_checksum="sha256:other", holdout_hashes=set()
    ).passed is False
    assert check_data_leakage(None, gold_checksum="sha256:gold", holdout_hashes=set()).passed is False


def test_evaluate_deployment_gate_fails_closed():
    passing = dict(dominance=True, audit_chain=True, tests_green=True, data_leakage=True)
    assert evaluate_deployment_gate(**passing).allowed is True
    # each single failure blocks the deploy.
    for failing in ("dominance", "audit_chain", "tests_green", "data_leakage"):
        kwargs = dict(passing)
        kwargs[failing] = False
        decision = evaluate_deployment_gate(**kwargs)
        assert decision.allowed is False
        assert failing in decision.reason


def test_evaluate_deployment_gate_preserves_check_detail():
    decision = evaluate_deployment_gate(
        dominance=GateCheck("dominance", True, "dominates incumbent"),
        audit_chain=GateCheck("audit_chain", False, "chain broken at entry 2"),
        tests_green=True,
        data_leakage=True,
    )
    assert decision.allowed is False
    detail = {c.name: c.detail for c in decision.checks}
    assert detail["audit_chain"] == "chain broken at entry 2"


def test_run_deployment_gate_all_inputs_pass():
    decision = run_deployment_gate(
        candidate_metrics=_gmv(top1_accuracy=0.90),
        incumbent_metrics=_gmv(),
        audit_log=_valid_audit_log(),
        audit_key=_KEY,
        tests_green=True,
        snapshot=_Snap(gold_checksum="sha256:gold", record_hashes=("h1", "h2")),
        gold_checksum="sha256:gold",
        holdout_hashes={"hX"},
    )
    assert decision.allowed is True
    assert decision.reason == "all gates passed"


def test_run_deployment_gate_underspecified_blocks():
    # Only tests green; no candidate, no audit log, no gold checksum -> fail closed.
    decision = run_deployment_gate(tests_green=True)
    assert decision.allowed is False
    for name in ("dominance", "audit_chain", "data_leakage"):
        assert name in decision.reason


def test_run_deployment_gate_blocks_on_leakage():
    decision = run_deployment_gate(
        candidate_metrics=_gmv(top1_accuracy=0.90),
        incumbent_metrics=_gmv(),
        audit_log=_valid_audit_log(),
        audit_key=_KEY,
        tests_green=True,
        snapshot=_Snap(gold_checksum="sha256:gold", record_hashes=("h1", "hX")),
        gold_checksum="sha256:gold",
        holdout_hashes={"hX"},  # h X leaked into training
    )
    assert decision.allowed is False
    assert "data_leakage" in decision.reason


def test_deployment_gate_cli_self_check_and_modes():
    ok, failures = self_check()
    assert ok is True and failures == []
    # CLI: self-check exits 0; all four flags -> 0; a missing flag -> 1 (fail closed).
    assert gate_cli(["--self-check"]) == 0
    assert gate_cli(["--dominance-pass", "--audit-pass", "--tests-green", "--leakage-pass"]) == 0
    assert gate_cli(["--dominance-pass", "--audit-pass", "--tests-green"]) == 1
    assert gate_cli([]) == 0  # no args -> self-check


# --------------------------------------------------------------------------- #
# Criterion 4: versioned output contract documented for downstream modules
# --------------------------------------------------------------------------- #
def test_output_contract_is_versioned_and_addressable():
    # The contract downstream modules (Regulatory Hub, ReactionIQ) depend on is
    # versioned and content-addressed; pin the schema version + envelope shape.
    assert SCHEMA_VERSION == "1.0.0"
    contract = build_spectracheck_contract(
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=400.0,
        ppm_range=(0.0, 12.0),
        n_points=16384,
        peaks=[{"ppm": 7.26, "category": "solvent"}],
    )
    envelope = contract.to_envelope()
    assert envelope["schema_version"] == SCHEMA_VERSION
    assert envelope["content_hash"].startswith("sha256:")
    assert "contract" in envelope
