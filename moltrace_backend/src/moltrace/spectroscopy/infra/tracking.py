"""Experiment tracking: log every run's params, metrics, artifacts, dataset
version, and code git SHA, and link it to the model registry by run id.

Backends
--------
* **MLflow** (when the optional ``infra`` extra is installed) -- a thin adapter
  over a local file store (``mlruns/`` by default, or ``$MLFLOW_TRACKING_URI``).
* **Native** (always available) -- a zero-dependency JSON run store that mirrors
  the same data so experiment tracking works out of the box in CI and offline.

Both backends present the identical :class:`RunHandle` API, so call sites never
branch on the backend.  Every run records the
:class:`~moltrace.spectroscopy.infra.eval.MetricVector` metrics, the dataset
version tag/hash, and the code revision, and can be linked
to a model in the audit ``MODEL_REGISTRY`` (Prompt 13 reproducibility registry)
by run id -- closing the loop from "which code + which data + which model
produced this metric".
"""

from __future__ import annotations

import importlib.util
import shutil
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moltrace.spectroscopy.infra.contract import canonical_json
from moltrace.spectroscopy.infra.eval import MetricVector
from moltrace.spectroscopy.infra.versioning import current_git_sha

__all__ = [
    "ExperimentTracker",
    "NativeRunStore",
    "RunHandle",
    "RunRecord",
    "mlflow_available",
]


def mlflow_available() -> bool:
    return importlib.util.find_spec("mlflow") is not None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return repr(value)


# --------------------------------------------------------------------------- #
# Run record + native store
# --------------------------------------------------------------------------- #
@dataclass
class RunRecord:
    run_id: str
    experiment: str
    backend: str
    git_sha: str
    dataset_version: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "backend": self.backend,
            "git_sha": self.git_sha,
            "dataset_version": self.dataset_version,
            "params": dict(sorted(self.params.items())),
            "metrics": dict(sorted(self.metrics.items())),
            "tags": dict(sorted(self.tags.items())),
            "artifacts": list(self.artifacts),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


class NativeRunStore:
    """Zero-dependency JSON run store under ``root/<experiment>/<run_id>/``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def run_dir(self, experiment: str, run_id: str) -> Path:
        return self.root / experiment / run_id

    def copy_artifact(self, experiment: str, run_id: str, src: str | Path) -> str:
        artifacts_dir = self.run_dir(experiment, run_id) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        dest = artifacts_dir / Path(src).name
        shutil.copy2(src, dest)
        return dest.relative_to(self.root).as_posix()

    def write(self, record: RunRecord) -> Path:
        run_dir = self.run_dir(record.experiment, record.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "run.json"
        path.write_text(canonical_json(record.as_dict()), encoding="utf-8")
        return path

    def read(self, experiment: str, run_id: str) -> dict[str, Any]:
        import json

        path = self.run_dir(experiment, run_id) / "run.json"
        if not path.exists():
            raise KeyError(f"no run {run_id!r} in experiment {experiment!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self, experiment: str) -> list[str]:
        base = self.root / experiment
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if (p / "run.json").exists())


# --------------------------------------------------------------------------- #
# Tracker + run handle
# --------------------------------------------------------------------------- #
def _resolve_backend(preference: str) -> str:
    if preference == "native":
        return "native"
    if preference == "mlflow":
        if not mlflow_available():
            raise RuntimeError(
                "backend='mlflow' requested but MLflow is not installed; install "
                "the optional infra extra (`pip install nmrcheck[infra]`)."
            )
        return "mlflow"
    if preference == "auto":
        return "mlflow" if mlflow_available() else "native"
    raise ValueError(f"unknown backend preference {preference!r}")


class ExperimentTracker:
    """Create and persist experiment runs against MLflow or the native store."""

    def __init__(
        self,
        *,
        experiment: str = "moltrace-phase0",
        tracking_root: str | Path = "moltrace_runs",
        backend: str = "auto",
        git_sha: str | None = None,
    ) -> None:
        self.experiment = experiment
        self.backend = _resolve_backend(backend)
        self.git_sha = git_sha or current_git_sha()
        self._store: NativeRunStore | None = None
        self._mlflow: Any = None

        if self.backend == "mlflow":
            import mlflow  # optional dep, present by construction

            self._mlflow = mlflow
            import os

            uri = os.environ.get("MLFLOW_TRACKING_URI")
            if not uri:
                uri = (Path(tracking_root) / "mlruns").resolve().as_uri()
            self._mlflow.set_tracking_uri(uri)
            self._mlflow.set_experiment(experiment)
        else:
            self._store = NativeRunStore(tracking_root)

    @contextmanager
    def start_run(
        self,
        run_name: str | None = None,
        *,
        params: Mapping[str, Any] | None = None,
        tags: Mapping[str, Any] | None = None,
    ) -> Iterator[RunHandle]:
        handle = RunHandle(self, run_name=run_name)
        handle._begin()
        try:
            handle.set_git_sha(self.git_sha)
            if params:
                handle.log_params(params)
            if tags:
                handle.set_tags(tags)
            yield handle
        finally:
            handle._end()


class RunHandle:
    """A single in-progress run; logs params/metrics/artifacts/tags uniformly."""

    def __init__(self, tracker: ExperimentTracker, *, run_name: str | None = None) -> None:
        self._tracker = tracker
        self.run_name = run_name
        self.run_id = ""
        self.record = RunRecord(
            run_id="", experiment=tracker.experiment, backend=tracker.backend, git_sha=""
        )
        self._mlflow_run: Any = None

    # -- lifecycle ------------------------------------------------------- #
    def _begin(self) -> None:
        self.record.started_at = _utc_now_iso()
        if self._tracker.backend == "mlflow":
            self._mlflow_run = self._tracker._mlflow.start_run(run_name=self.run_name)
            self.run_id = self._mlflow_run.info.run_id
        else:
            self.run_id = uuid.uuid4().hex
            if self.run_name:
                self.record.tags["run_name"] = self.run_name
        self.record.run_id = self.run_id

    def _end(self) -> None:
        self.record.ended_at = _utc_now_iso()
        if self._tracker.backend == "mlflow":
            self._tracker._mlflow.end_run()
        else:
            assert self._tracker._store is not None
            self._tracker._store.write(self.record)

    # -- logging --------------------------------------------------------- #
    def log_params(self, params: Mapping[str, Any]) -> None:
        clean = {str(k): _stringify(v) for k, v in params.items()}
        self.record.params.update(clean)
        if self._tracker.backend == "mlflow":
            self._tracker._mlflow.log_params(clean)

    def log_metrics(
        self, metrics: MetricVector | Mapping[str, float], *, step: int | None = None
    ) -> None:
        flat = metrics.as_dict() if isinstance(metrics, MetricVector) else {
            str(k): float(v) for k, v in metrics.items()
        }
        self.record.metrics.update(flat)
        if self._tracker.backend == "mlflow":
            self._tracker._mlflow.log_metrics(flat, step=step)

    def set_tags(self, tags: Mapping[str, Any]) -> None:
        clean = {str(k): _stringify(v) for k, v in tags.items()}
        self.record.tags.update(clean)
        if self._tracker.backend == "mlflow":
            self._tracker._mlflow.set_tags(clean)

    def set_git_sha(self, sha: str) -> None:
        self.record.git_sha = sha
        self.set_tags({"git_sha": sha})

    def set_dataset_version(self, version: str) -> None:
        """Pin this run to a dataset version tag or content hash."""

        self.record.dataset_version = version
        self.set_tags({"dataset_version": version})

    def link_registry_model(self, name: str) -> str:
        """Link this run to a model in the audit MODEL_REGISTRY by checksum.

        Records ``registry.model_name`` and ``registry.model_checksum`` tags so
        the run id resolves to the exact model weights that produced its metrics.
        Returns the checksum.  Raises ``KeyError`` if the model is not registered.
        """

        from moltrace.spectroscopy.audit.trail import MODEL_REGISTRY

        snapshot = MODEL_REGISTRY.snapshot()
        if name not in snapshot:
            raise KeyError(f"model {name!r} is not registered in MODEL_REGISTRY")
        checksum = snapshot[name]
        self.set_tags({"registry.model_name": name, "registry.model_checksum": checksum})
        return checksum

    def log_artifact(self, path: str | Path) -> None:
        if self._tracker.backend == "mlflow":
            self._tracker._mlflow.log_artifact(str(path))
            self.record.artifacts.append(Path(path).name)
        else:
            assert self._tracker._store is not None
            rel = self._tracker._store.copy_artifact(self._tracker.experiment, self.run_id, path)
            self.record.artifacts.append(rel)
