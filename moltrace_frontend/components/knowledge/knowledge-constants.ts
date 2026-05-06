/** Mirrors backend KnowledgeSourceType — do not rename values (API contract). */
export const KNOWLEDGE_SOURCE_TYPES = [
  "journal_article",
  "patent",
  "supporting_information",
  "regulatory_guidance",
  "internal_sop",
  "analytical_report",
  "eln_export",
  "project_note",
  "method_validation_document",
  "spectracheck_report",
  "reaction_report",
  "regulatory_report",
  "other",
] as const

/** Mirrors backend KnowledgeReliabilityLabel */
export const KNOWLEDGE_RELIABILITY_LABELS = ["high", "medium", "low", "unknown"] as const

/** Mirrors backend KnowledgeSourceStatus */
export const KNOWLEDGE_SOURCE_STATUS = ["draft", "active", "archived", "deprecated", "needs_review"] as const

/** Mirrors backend KnowledgeExtractionType */
export const KNOWLEDGE_EXTRACTION_TYPES = [
  "reaction",
  "analytical",
  "regulatory",
  "mixed",
  "citation_only",
  "training_candidate",
  "benchmark_candidate",
] as const

/** Mirrors backend KnowledgeTargetType */
export const KNOWLEDGE_LINK_TARGET_TYPES = [
  "compound",
  "batch",
  "spectracheck_session",
  "reaction_project",
  "reaction_experiment",
  "regulatory_dossier",
  "report",
  "method_registry_entry",
  "workflow_template",
  "training_dataset_candidate",
  "benchmark_dataset_candidate",
  "model_improvement_queue_item",
  "other",
] as const

/** Mirrors backend CompoundConfidenceLabel */
export const KNOWLEDGE_LINK_CONFIDENCE_LABELS = ["low", "medium", "high", "requires_review"] as const

/** Mirrors backend KnowledgeTrainingDatasetType */
export const KNOWLEDGE_TRAINING_DATASET_TYPES = [
  "nmr_prediction",
  "nmr_structure_elucidation",
  "msms_annotation",
  "lcms_feature",
  "reaction_optimization",
  "regulatory_extraction",
  "method_validation",
  "ai_governance",
] as const

/** Mirrors backend KnowledgeBenchmarkType */
export const KNOWLEDGE_BENCHMARK_TYPES = [
  "nmr_candidate_ranking",
  "nmr_shift_prediction",
  "msms_annotation",
  "lcms_feature_consensus",
  "reaction_optimization",
  "regulatory_rag",
  "regulatory_compliance",
] as const

/** Mirrors backend KnowledgeTaskStatus */
export const KNOWLEDGE_TASK_STATUSES = [
  "open",
  "in_review",
  "accepted",
  "rejected",
  "needs_changes",
  "deferred",
] as const

/** Mirrors backend KnowledgeCandidateStatus */
export const KNOWLEDGE_CANDIDATE_STATUSES = ["proposed", "accepted", "rejected", "needs_review"] as const

/** Mirrors backend DatasetSplitRecommendation */
export const DATASET_SPLIT_RECOMMENDATIONS = ["train", "validation", "test", "holdout", "unknown"] as const

/** Mirrors backend LeakageRiskLabel */
export const LEAKAGE_RISK_LABELS = ["low", "medium", "high", "unknown"] as const

/** Mirrors backend DatasetVersionStatus */
export const DATASET_VERSION_STATUSES = ["draft", "ready_for_review", "approved", "archived"] as const

/** Mirrors backend ModelImprovementSourceType */
export const MODEL_IMPROVEMENT_SOURCE_TYPES = [
  "error_case",
  "low_confidence_prediction",
  "failed_qc",
  "human_override",
  "new_reviewed_record",
  "benchmark_failure",
  "drift_alert",
] as const

/** Mirrors backend ModelImprovementTargetModule */
export const MODEL_IMPROVEMENT_TARGET_MODULES = [
  "spectracheck",
  "msms",
  "lcms",
  "reaction_optimization",
  "regulatory",
  "report",
] as const

/** Mirrors backend ModelImprovementPriority */
export const MODEL_IMPROVEMENT_PRIORITIES = ["low", "medium", "high", "critical"] as const

/** Mirrors backend ModelImprovementStatus */
export const MODEL_IMPROVEMENT_STATUSES = ["open", "in_review", "resolved", "dismissed"] as const

/** Mirrors backend KnowledgeReviewRecordType (subset used when registering dataset candidates from extracted records) */
export const KNOWLEDGE_REVIEW_RECORD_TYPES = [
  "reaction",
  "analytical",
  "regulatory",
  "citation",
  "training_candidate",
  "benchmark_candidate",
] as const
