"""Experiment / run tracking for the ComplianceCore (Prompt 19).

Each evaluation or training run logs its params, the :class:`RegulatoryMetricVector`
(Prompt 17), the rule-set + model versions (Prompt 13), the corpus version
(Prompt 20), and the code git SHA — keyed by ``run_id`` so the run links to the
registry. Reuse-first: the tracker is the tested spectroscopy
:class:`~moltrace.spectroscopy.infra.tracking.ExperimentTracker` — MLflow when the
``infra`` extra is installed, a native file-based run store otherwise — so this is
a thin regulatory facade, not a second implementation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from moltrace.regulatory.infra.eval import RegulatoryMetricVector
from moltrace.spectroscopy.infra.tracking import ExperimentTracker, NativeRunStore, RunHandle

__all__ = [
    "ExperimentTracker",
    "NativeRunStore",
    "RunHandle",
    "log_regulatory_run",
    "regulatory_tracker",
]


def regulatory_tracker(
    *,
    experiment: str = "moltrace-regulatory",
    tracking_root: str = "moltrace_runs",
    backend: str = "auto",
) -> ExperimentTracker:
    """A tracker scoped to the ComplianceCore experiment (native store by default)."""

    return ExperimentTracker(experiment=experiment, tracking_root=tracking_root, backend=backend)


def log_regulatory_run(
    tracker: ExperimentTracker,
    *,
    run_name: str,
    metric_vector: RegulatoryMetricVector,
    rule_set_version: str,
    model_versions: Mapping[str, str] | None = None,
    corpus_version: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> str:
    """Log one regulatory evaluation/training run and return its ``run_id``.

    The metric vector, rule-set version, model versions, corpus version, and git
    SHA are all recorded so the run is reproducible and linkable to the Prompt 13
    registry. The git SHA is stamped by the tracker automatically.
    """

    run_params: dict[str, Any] = dict(params or {})
    run_params["rule_set_version"] = rule_set_version
    if corpus_version is not None:
        run_params["corpus_version"] = corpus_version
    if model_versions:
        run_params["model_versions"] = json.dumps(dict(sorted(model_versions.items())))

    with tracker.start_run(run_name, params=run_params) as run:
        run.log_metrics(metric_vector.metric_items())
        tags: dict[str, Any] = {"rule_set_version": rule_set_version}
        if corpus_version is not None:
            tags["corpus_version"] = corpus_version
            run.set_dataset_version(corpus_version)
        run.set_tags(tags)
        return run.run_id
