"""ComplianceCore Phase 0 foundation (Prompt 19) — measurement + reproducibility.

The methodological bedrock for the whole module, built reuse-first over the
spectroscopy Phase 0 foundation (``moltrace.spectroscopy.infra``):

* :mod:`.eval` — the regulatory metric layer (the single source of truth for
  "better") with the two zero-tolerance hard gates: calculation-error rate 0 and
  formula coverage 100%.
* :mod:`.versioning` — content-addressed versioning of rule-sets, corpus
  snapshots, and gold sets (DVC + S3 remote; no blobs in git).
* :mod:`.tracking` — run tracking (params / metric vector / rule-set + model +
  corpus versions / git SHA), MLflow when the ``infra`` extra is installed.
* :mod:`.validation` — fail-loud schema gates for every structured input
  (compound record, dose, impurity list from SpectraCheck, corpus document).
* :mod:`.compliance` — the versioned GAMP 5 Appendix D11 / CSV validation-document
  skeleton that Prompt 21 fills with the formal evidence.
"""

from __future__ import annotations

from moltrace.regulatory.infra.compliance import (
    build_regulatory_validation_document,
    metric_evidence_block,
    render_gamp5_d11_template,
)
from moltrace.regulatory.infra.eval import (
    CalculationCheck,
    CitationCheck,
    ClaimCheck,
    ClassificationAccuracy,
    HardGateError,
    NarrativeReview,
    RegulatoryEvalError,
    RegulatoryMetricVector,
    calculation_error_rate,
    calculation_errors,
    citation_correctness,
    classification_accuracy,
    enforce_full_coverage,
    enforce_hard_gates,
    enforce_zero_calculation_errors,
    formula_coverage,
    hallucination_rate,
    levenshtein,
    mean_edit_distance,
    missing_formulas,
    narrative_acceptance_rate,
    needs_review_precision,
    normalized_edit_distance,
)
from moltrace.regulatory.infra.tracking import (
    ExperimentTracker,
    NativeRunStore,
    RunHandle,
    log_regulatory_run,
    regulatory_tracker,
)
from moltrace.regulatory.infra.validation import (
    DataValidationError,
    ValidationFailure,
    ValidationReport,
    assert_valid_compound_record,
    assert_valid_corpus_document,
    assert_valid_dose,
    assert_valid_impurity_list,
    validate_compound_record,
    validate_corpus_document,
    validate_dose,
    validate_impurity_list,
)
from moltrace.regulatory.infra.versioning import (
    DatasetVersion,
    DvcS3Remote,
    LocalDatasetRemote,
    RegulatoryArtifact,
    artifact_for,
    content_hash,
    corpus_snapshot_version,
    current_git_sha,
    dataset_hash,
    gold_set_version,
    rule_set_version,
)

__all__ = [
    "CalculationCheck",
    "CitationCheck",
    "ClaimCheck",
    "ClassificationAccuracy",
    "DataValidationError",
    "DatasetVersion",
    "DvcS3Remote",
    "ExperimentTracker",
    "HardGateError",
    "LocalDatasetRemote",
    "NarrativeReview",
    "NativeRunStore",
    "RegulatoryArtifact",
    "RegulatoryEvalError",
    "RegulatoryMetricVector",
    "RunHandle",
    "ValidationFailure",
    "ValidationReport",
    "artifact_for",
    "assert_valid_compound_record",
    "assert_valid_corpus_document",
    "assert_valid_dose",
    "assert_valid_impurity_list",
    "build_regulatory_validation_document",
    "calculation_error_rate",
    "calculation_errors",
    "citation_correctness",
    "classification_accuracy",
    "content_hash",
    "corpus_snapshot_version",
    "current_git_sha",
    "dataset_hash",
    "enforce_full_coverage",
    "enforce_hard_gates",
    "enforce_zero_calculation_errors",
    "formula_coverage",
    "gold_set_version",
    "hallucination_rate",
    "levenshtein",
    "log_regulatory_run",
    "mean_edit_distance",
    "metric_evidence_block",
    "missing_formulas",
    "narrative_acceptance_rate",
    "needs_review_precision",
    "normalized_edit_distance",
    "regulatory_tracker",
    "render_gamp5_d11_template",
    "rule_set_version",
    "validate_compound_record",
    "validate_corpus_document",
    "validate_dose",
    "validate_impurity_list",
]
