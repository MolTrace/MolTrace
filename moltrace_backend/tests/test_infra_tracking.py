"""Unit tests for experiment tracking (infra.tracking).

The native run store is exercised end-to-end; the MLflow backend is covered with
``importorskip`` so it runs only when the optional infra extra is installed.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.infra.eval import MetricVector
from moltrace.spectroscopy.infra.tracking import ExperimentTracker, NativeRunStore


def _tracker(tmp_path) -> ExperimentTracker:
    return ExperimentTracker(
        experiment="unit-test",
        tracking_root=tmp_path / "runs",
        backend="native",
        git_sha="abc123sha",
    )


def test_native_run_logs_everything(tmp_path) -> None:
    tracker = _tracker(tmp_path)
    artifact = tmp_path / "report.txt"
    artifact.write_text("hello")

    with tracker.start_run("run-1", params={"level": 2}) as run:
        run.log_metrics(MetricVector(rmse=0.1, f1=0.9, top_k={1: 0.5}))
        run.set_dataset_version("gold-v3")
        run.log_artifact(artifact)
        run_id = run.run_id

    store = NativeRunStore(tmp_path / "runs")
    record = store.read("unit-test", run_id)
    assert record["params"]["level"] == "2"
    assert record["metrics"]["rmse"] == pytest.approx(0.1)
    assert record["metrics"]["top_1_accuracy"] == pytest.approx(0.5)
    assert record["git_sha"] == "abc123sha"
    assert record["tags"]["git_sha"] == "abc123sha"
    assert record["dataset_version"] == "gold-v3"
    assert record["tags"]["dataset_version"] == "gold-v3"
    assert record["artifacts"] == [f"unit-test/{run_id}/artifacts/report.txt"]


def test_native_run_id_is_unique(tmp_path) -> None:
    tracker = _tracker(tmp_path)
    with tracker.start_run("a") as r1:
        id1 = r1.run_id
    with tracker.start_run("b") as r2:
        id2 = r2.run_id
    assert id1 != id2
    assert set(NativeRunStore(tmp_path / "runs").list_runs("unit-test")) == {id1, id2}


def test_metrics_accept_plain_mapping(tmp_path) -> None:
    tracker = _tracker(tmp_path)
    with tracker.start_run("m") as run:
        run.log_metrics({"custom": 3})
        run_id = run.run_id
    record = NativeRunStore(tmp_path / "runs").read("unit-test", run_id)
    assert record["metrics"]["custom"] == pytest.approx(3.0)


def test_link_registry_model_records_checksum(tmp_path) -> None:
    from moltrace.spectroscopy.audit.trail import MODEL_REGISTRY

    MODEL_REGISTRY.register("nmrnet-prod", "deadbeef")
    try:
        tracker = _tracker(tmp_path)
        with tracker.start_run("with-model") as run:
            checksum = run.link_registry_model("nmrnet-prod")
            run_id = run.run_id
        assert checksum == "deadbeef"
        record = NativeRunStore(tmp_path / "runs").read("unit-test", run_id)
        assert record["tags"]["registry.model_name"] == "nmrnet-prod"
        assert record["tags"]["registry.model_checksum"] == "deadbeef"
    finally:
        MODEL_REGISTRY.clear()


def test_link_registry_model_unknown_raises(tmp_path) -> None:
    tracker = _tracker(tmp_path)
    with tracker.start_run("x") as run:
        with pytest.raises(KeyError):
            run.link_registry_model("does-not-exist")


def test_mlflow_backend_requires_install() -> None:
    pytest.importorskip("mlflow", reason="MLflow backend only when infra extra installed")
    # If mlflow is present, the tracker must construct without error.
    tracker = ExperimentTracker(backend="mlflow", tracking_root="mlruns")
    assert tracker.backend == "mlflow"


def test_explicit_mlflow_without_install_raises() -> None:
    if ExperimentTracker(backend="auto").backend == "mlflow":
        pytest.skip("mlflow installed; cannot test the missing-backend error")
    with pytest.raises(RuntimeError):
        ExperimentTracker(backend="mlflow")
