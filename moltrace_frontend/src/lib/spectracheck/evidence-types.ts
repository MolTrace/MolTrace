/**
 * SpectraCheck Evidence Orchestration — shared types for the evidence queue / registry.
 */

export type EvidenceLayerType =
  | "nmr_text_candidates"
  | "processed_1h"
  | "processed_13c"
  | "raw_fid_1h"
  | "raw_fid_13c"
  | "dept_apt"
  | "nmr_2d"
  | "predicted_nmr"
  | "spectral_similarity"
  | "hrms_exact_mass"
  | "formula_search"
  | "adduct_isotope"
  | "msms_annotation"
  | "fragmentation_tree"
  | "lcms_import"
  | "lcms_feature_detection"
  | "lcms_feature_grouping"
  | "lcms_feature_family_consensus"
  | "lcms_dereplication"
  | "lcms_confidence_bridge"
  | "unified_confidence"
  | "report"

export type EvidenceItemStatus = "ready" | "warning" | "error" | "pending_review"

/** QC outcome from `/quality-control/evidence/{id}` assessment (optional until assessed). */
export type EvidenceQcStatus =
  | "qc_pass"
  | "qc_warning"
  | "qc_fail"
  | "requires_human_review"
  | "not_assessed"

/** Whether an evidence row may enter Unified Evidence under current overrides. */
export type EvidenceReadinessStatus =
  | "ready_for_unified_evidence"
  | "usable_with_warnings"
  | "blocked_until_review"
  | "not_ready"

export type EvidenceProvenance = {
  filename?: string
  sha256?: string
  rawDataPreserved?: boolean
  processingPreset?: string
}

export type EvidenceItem = {
  id: string
  layer: EvidenceLayerType
  title: string
  sourceTab: string
  sampleId?: string
  status: EvidenceItemStatus
  score?: number
  label?: string
  summary?: string
  evidenceSummary?: string[]
  contradictions?: string[]
  warnings?: string[]
  notes?: string[]
  endpoint?: string
  requestPreview?: unknown
  response: unknown
  createdAt: string
  selectedForUnified: boolean
  provenance?: EvidenceProvenance
  /** When persisted to the backend SpectraCheck session, used for PATCH updates. */
  backendEvidenceId?: number
  /** Server QC assessment id when returned by quality-control endpoints. */
  qualityAssessmentId?: string
  qcStatus?: EvidenceQcStatus
  readinessStatus?: EvidenceReadinessStatus
  /** Reviewer decision label when an override is recorded locally (e.g. allow_with_warning). */
  overrideStatus?: string
  /** Free-text justification for overrides (required when overriding). */
  overrideReason?: string
  /** Local-only: previews/visualizations were inspected in the queue (not scientific approval). */
  visualReviewed?: boolean
  /** Optional note alongside {@link visualReviewed}. */
  visualReviewComment?: string

  /** Optional registry identifiers when returned by analysis or session evidence APIs. */
  methodId?: string
  methodName?: string
  methodVersion?: string
  modelVersionId?: string
  modelName?: string
  modelVersion?: string
  scoringProfileId?: string
  scoringProfileName?: string
  thresholdProfileId?: string
  thresholdProfileName?: string

  /** ML Model Factory / registry echoes when APIs include them */
  modelArtifactId?: number
  datasetVersionId?: number
  evaluationRunId?: number
  deploymentCandidateId?: number
  modelCardId?: number
  approvalStatus?: string
}

/** Fields supplied when enqueueing; `id`, `createdAt`, and `selectedForUnified` are filled by the registry unless provided. */
export type AddEvidenceItemInput = Omit<EvidenceItem, "id" | "createdAt" | "selectedForUnified"> &
  Partial<Pick<EvidenceItem, "id" | "createdAt" | "selectedForUnified">>
