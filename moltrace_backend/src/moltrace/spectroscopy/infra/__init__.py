"""Phase 0 foundation (Prompt 19): evaluation, data lineage, validation, docs.

This package is the methodological bedrock the rest of the platform builds on:

* :mod:`.eval` -- the calibrated metric layer (RMSE, F1, Top-k, BedROC, ECE):
  the single source of truth for "better".
* :mod:`.contract` -- the versioned, canonically-serialised SpectraCheck output
  contract + content hashing (deterministic byte-identical JSON).
* :mod:`.versioning` -- content-addressed dataset versioning (sha256 manifests)
  with a DVC + S3 remote adapter and a zero-dependency local fallback.
* :mod:`.tracking` -- experiment tracking (params / metrics / artifacts /
  dataset tag / git sha) on MLflow, with a native file-based run store fallback.
* :mod:`.validation` -- data validation gates (schema, nucleus/field ranges,
  NaNs, value ranges) backed by Great Expectations when available, native
  otherwise; both fail loudly.
* :mod:`.compliance` -- GAMP 5 Appendix D11 validation-document template and a
  deterministic ICH report stub generator.

Design rule: the *native* path of every module works with only the core
dependencies (numpy/scipy).  Installing the optional ``infra`` extra
(``pip install nmrcheck[infra]``) upgrades the lineage/validation paths to the
industry-standard tools (MLflow, DVC+S3, Great Expectations) without changing
any call sites.
"""

from __future__ import annotations

from moltrace.spectroscopy.infra.compliance import (
    build_ich_report_stub,
    render_gamp5_d11_template,
    render_ich_report_stub,
)
from moltrace.spectroscopy.infra.contract import (
    SCHEMA_VERSION,
    SpectraCheckContract,
    build_spectracheck_contract,
    canonical_json,
    content_hash,
    contract_from_pipeline,
)
from moltrace.spectroscopy.infra.eval import (
    PRF,
    MetricVector,
    bedroc,
    classification_f1,
    expected_calibration_error,
    f1_score,
    peak_detection_f1,
    reliability_bins,
    rmse,
    top_k_accuracy,
)
from moltrace.spectroscopy.infra.tracking import (
    ExperimentTracker,
    NativeRunStore,
    RunHandle,
)
from moltrace.spectroscopy.infra.validation import (
    DataValidationError,
    ValidationReport,
    assert_valid_spectrum_input,
    validate_spectrum_input,
    validate_with_great_expectations,
)
from moltrace.spectroscopy.infra.versioning import (
    DatasetVersion,
    DvcS3Remote,
    LocalDatasetRemote,
    current_git_sha,
    dataset_hash,
)

__all__ = [
    "PRF",
    "SCHEMA_VERSION",
    "DataValidationError",
    "DatasetVersion",
    "DvcS3Remote",
    "ExperimentTracker",
    "LocalDatasetRemote",
    "MetricVector",
    "NativeRunStore",
    "RunHandle",
    "SpectraCheckContract",
    "ValidationReport",
    "assert_valid_spectrum_input",
    "bedroc",
    "build_ich_report_stub",
    "build_spectracheck_contract",
    "canonical_json",
    "classification_f1",
    "content_hash",
    "contract_from_pipeline",
    "current_git_sha",
    "dataset_hash",
    "expected_calibration_error",
    "f1_score",
    "peak_detection_f1",
    "reliability_bins",
    "render_gamp5_d11_template",
    "render_ich_report_stub",
    "rmse",
    "top_k_accuracy",
    "validate_spectrum_input",
    "validate_with_great_expectations",
]
