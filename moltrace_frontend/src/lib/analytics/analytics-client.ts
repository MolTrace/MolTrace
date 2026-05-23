import { apiFetch } from "@/lib/api/client"

/** Keys stripped from metadata — may contain raw scientific content or secrets. */
const SENSITIVE_METADATA_KEYS = new Set([
  "rawSpectrum",
  "spectrum",
  "nmrText",
  "protonText",
  "carbonText",
  "smiles",
  "candidates",
  "candidates_text",
  "observed_proton_text",
  "observed_carbon13_text",
  "msms_peak_list_text",
  "fileContent",
  "token",
  "password",
  "secret",
  "accessToken",
  "refreshToken",
  "report_html",
  "html_report",
  "json_report",
  "requestor_notes",
  "reviewer_comment",
  "question",
  "answer_text",
  "answer",
  "rationale",
  "requirement_text",
  "preferred_name",
  "preferredName",
  "original_structure_input",
  "originalStructureInput",
  "registry_id",
  "registryId",
  "inchikey",
  "inchiKey",
  "canonical_smiles",
  "canonicalSmiles",
  "molfile",
  "batch_code",
  "batchCode",
  "lot_code",
  "lotCode",
  "aliquot_code",
  "aliquotCode",
  "structure_text",
  "risk_signals_json",
  "solvents_json",
  "explainability_summary_json",
  "citations_json",
  "notes_json",
])

export type AnalyticsId = string | number | undefined

/** Payload POSTed to GET/POST /analytics/events — privacy-safe fields only. */
export type UsageAnalyticsEvent = {
  event_type: string
  project_id?: AnalyticsId
  sample_id?: AnalyticsId
  session_id?: AnalyticsId
  workflow_run_id?: AnalyticsId
  job_id?: AnalyticsId
  artifact_id?: AnalyticsId
  report_id?: AnalyticsId
  status?: string
  duration_seconds?: number
  estimated_minutes_saved?: number
  event_source: "frontend"
  metadata?: Record<string, unknown>
}

export type UsageAnalyticsEventInput = Omit<UsageAnalyticsEvent, "event_source"> & {
  metadata?: Record<string, unknown>
}

function sanitizeMetadataValue(value: unknown): unknown {
  if (value === null || value === undefined) return value
  if (Array.isArray(value)) return value.map(sanitizeMetadataValue)
  if (typeof value === "object") {
    return sanitizeMetadataObject(value as Record<string, unknown>)
  }
  return value
}

function sanitizeMetadataObject(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(obj)) {
    if (SENSITIVE_METADATA_KEYS.has(key)) continue
    out[key] = sanitizeMetadataValue(value)
  }
  return out
}

function sanitizeMetadata(metadata: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (metadata == null) return undefined
  const cleaned = sanitizeMetadataObject(metadata)
  return Object.keys(cleaned).length > 0 ? cleaned : undefined
}

function buildPayload(input: UsageAnalyticsEventInput): UsageAnalyticsEvent {
  const { metadata, ...rest } = input
  return {
    ...rest,
    event_source: "frontend",
    metadata: sanitizeMetadata(metadata),
  }
}

async function postAnalyticsEvent(payload: UsageAnalyticsEvent): Promise<void> {
  try {
    await apiFetch<unknown>("/analytics/events", {
      method: "POST",
      body: payload,
    })
  } catch (err) {
    if (process.env.NODE_ENV === "development") {
      console.warn("[analytics] Failed to send event:", payload.event_type, err)
    }
  }
}

/**
 * Sends a privacy-safe usage event to POST /analytics/events.
 * Failures are swallowed; dev-only console warning.
 */
export function trackUsageEvent(event: UsageAnalyticsEventInput): void {
  void postAnalyticsEvent(buildPayload(event))
}

/** Safe fields for lifecycle helpers (no event_type — set by each tracker). */
export type WorkflowLifecyclePayload = Omit<UsageAnalyticsEventInput, "event_type">

export function trackWorkflowStarted(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "workflow_started" })
}

export function trackWorkflowCompleted(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "workflow_completed" })
}

export function trackJobCompleted(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "job_completed" })
}

export function trackReportGenerated(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "report_generated" })
}

export function trackEvidenceAdded(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "evidence_added" })
}

export function trackQcCompleted(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "qc_completed" })
}

export function trackFeedback(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "feedback" })
}

export function trackFileUploaded(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "file_uploaded" })
}

export function trackJobStarted(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "job_started" })
}

export function trackUnifiedEvidenceBuilt(payload: WorkflowLifecyclePayload): void {
  trackUsageEvent({ ...payload, event_type: "unified_evidence_built" })
}

export type CoreAnalyticsModule =
  | "spectracheck"
  | "regulatory_hub"
  | "reactioniq"
  | "regulatory"
  | "reactions"
  | string

export type CoreModuleOpenedPayload = Omit<UsageAnalyticsEventInput, "event_type" | "metadata"> & {
  surface?: string
  metadata?: Record<string, unknown>
}

export function trackCoreModuleOpened(
  module: CoreAnalyticsModule,
  payload: CoreModuleOpenedPayload = {},
): void {
  const { metadata, surface, ...rest } = payload
  trackUsageEvent({
    ...rest,
    event_type: "core_module_opened",
    metadata: {
      ...metadata,
      module,
      surface: surface ?? module,
    },
  })
}

/** Connector/interoperability analytics metadata whitelist (privacy-safe categorical/count fields only). */
export type ConnectorInteropAnalyticsMetadata = {
  connector_type?: string
  target_program?: string
  status?: string
  file_kind?: string
  source_format?: string
  target_format?: string
  success_count?: number
  failure_count?: number
  warning_count?: number
}

function connectorInteropMetadata(meta: ConnectorInteropAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (typeof meta.connector_type === "string" && meta.connector_type.trim()) {
    out.connector_type = meta.connector_type.trim().slice(0, 120)
  }
  if (typeof meta.target_program === "string" && meta.target_program.trim()) {
    out.target_program = meta.target_program.trim().slice(0, 120)
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim().slice(0, 120)
  }
  if (typeof meta.file_kind === "string" && meta.file_kind.trim()) {
    out.file_kind = meta.file_kind.trim().slice(0, 120)
  }
  if (typeof meta.source_format === "string" && meta.source_format.trim()) {
    out.source_format = meta.source_format.trim().slice(0, 120)
  }
  if (typeof meta.target_format === "string" && meta.target_format.trim()) {
    out.target_format = meta.target_format.trim().slice(0, 120)
  }
  if (typeof meta.success_count === "number" && Number.isFinite(meta.success_count)) {
    out.success_count = Math.max(0, Math.round(meta.success_count))
  }
  if (typeof meta.failure_count === "number" && Number.isFinite(meta.failure_count)) {
    out.failure_count = Math.max(0, Math.round(meta.failure_count))
  }
  if (typeof meta.warning_count === "number" && Number.isFinite(meta.warning_count)) {
    out.warning_count = Math.max(0, Math.round(meta.warning_count))
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function trackConnectorInteropEvent(event_type: string, meta: ConnectorInteropAnalyticsMetadata): void {
  trackUsageEvent({ event_type, metadata: connectorInteropMetadata(meta) })
}

export function trackConnectorCreated(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("connector_created", meta)
}

export function trackConnectorHealthCheckRun(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("connector_health_check_run", meta)
}

export function trackWatchFolderScanRun(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("watch_folder_scan_run", meta)
}

export function trackIngestionRunStarted(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("ingestion_run_started", meta)
}

export function trackIngestionRunCompleted(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("ingestion_run_completed", meta)
}

export function trackFileNormalizationRun(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("file_normalization_run", meta)
}

export function trackExternalObjectLinkCreated(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("external_object_link_created", meta)
}

export function trackMappingTemplateCreated(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("mapping_template_created", meta)
}

export function trackOutboundSyncJobCreated(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("outbound_sync_job_created", meta)
}

export function trackSubmissionPackageCreated(meta: ConnectorInteropAnalyticsMetadata): void {
  trackConnectorInteropEvent("submission_package_created", meta)
}

/** Tenant SaaS analytics metadata whitelist — categorical fields only; no tenant notes, domains, IPs, secrets, or raw data. */
export type TenantSaasAnalyticsMetadata = {
  tenant_type?: string
  program?: string
  feature_key?: string
  status?: string
  implementation_stage?: string
  package_type?: string
  health_status?: string
  task_type?: string
}

function tenantSaasString(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, 160) : ""
}

function tenantSaasMetadata(meta: TenantSaasAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  const tenantType = tenantSaasString(meta.tenant_type)
  const program = tenantSaasString(meta.program)
  const featureKey = tenantSaasString(meta.feature_key)
  const status = tenantSaasString(meta.status)
  const implementationStage = tenantSaasString(meta.implementation_stage)
  const packageType = tenantSaasString(meta.package_type)
  const healthStatus = tenantSaasString(meta.health_status)
  const taskType = tenantSaasString(meta.task_type)

  if (tenantType) out.tenant_type = tenantType
  if (program) out.program = program
  if (featureKey) out.feature_key = featureKey
  if (status) out.status = status
  if (implementationStage) out.implementation_stage = implementationStage
  if (packageType) out.package_type = packageType
  if (healthStatus) out.health_status = healthStatus
  if (taskType) out.task_type = taskType

  return Object.keys(out).length > 0 ? out : undefined
}

function trackTenantSaasEvent(event_type: string, meta: TenantSaasAnalyticsMetadata = {}): void {
  trackUsageEvent({ event_type, metadata: tenantSaasMetadata(meta) })
}

export function trackTenantCreated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("tenant_created", meta)
}

export function trackTenantEnvironmentCreated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("tenant_environment_created", meta)
}

export function trackEntitlementUpdated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("entitlement_updated", meta)
}

export function trackFeatureFlagUpdated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("feature_flag_updated", meta)
}

export function trackPilotProgramCreated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("pilot_program_created", meta)
}

export function trackOnboardingProjectCreated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("onboarding_project_created", meta)
}

export function trackOnboardingTaskCompleted(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("onboarding_task_completed", meta)
}

export function trackDataBoundaryCreated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("data_boundary_created", meta)
}

export function trackSecurityProfileUpdated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("security_profile_updated", meta)
}

export function trackValidationProfileUpdated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("validation_profile_updated", meta)
}

export function trackProcurementPackageCreated(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("procurement_package_created", meta)
}

export function trackTenantAuditExportRequested(meta: TenantSaasAnalyticsMetadata): void {
  trackTenantSaasEvent("tenant_audit_export_requested", meta)
}

/** Allowed metadata for controlled AI inference analytics only. */
export type AiInferenceAnalyticsMetadata = {
  service_key?: string
  target_module?: string
  task_key?: string
  status?: string
  confidence_bucket?: string
  ood_status?: string
  feedback_type?: string
  active_learning_reason?: string
  warning_count?: number
}

function aiInferenceMetadata(meta: AiInferenceAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (typeof meta.service_key === "string" && meta.service_key.trim()) out.service_key = meta.service_key.trim()
  if (typeof meta.target_module === "string" && meta.target_module.trim()) out.target_module = meta.target_module.trim()
  if (typeof meta.task_key === "string" && meta.task_key.trim()) out.task_key = meta.task_key.trim()
  if (typeof meta.status === "string" && meta.status.trim()) out.status = meta.status.trim()
  if (typeof meta.confidence_bucket === "string" && meta.confidence_bucket.trim()) {
    out.confidence_bucket = meta.confidence_bucket.trim()
  }
  if (typeof meta.ood_status === "string" && meta.ood_status.trim()) out.ood_status = meta.ood_status.trim()
  if (typeof meta.feedback_type === "string" && meta.feedback_type.trim()) out.feedback_type = meta.feedback_type.trim()
  if (typeof meta.active_learning_reason === "string" && meta.active_learning_reason.trim()) {
    out.active_learning_reason = meta.active_learning_reason.trim()
  }
  if (typeof meta.warning_count === "number" && Number.isFinite(meta.warning_count)) {
    out.warning_count = Math.max(0, Math.round(meta.warning_count))
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackAiPredictionRunStarted(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_prediction_run_started", metadata: aiInferenceMetadata(meta) })
}

export function trackAiPredictionRunCompleted(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_prediction_run_completed", metadata: aiInferenceMetadata(meta) })
}

export function trackAiPredictionFeedbackSubmitted(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_prediction_feedback_submitted", metadata: aiInferenceMetadata(meta) })
}

export function trackAiActiveLearningCandidateCreated(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_active_learning_candidate_created", metadata: aiInferenceMetadata(meta) })
}

export function trackAiShadowEvaluationStarted(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_shadow_evaluation_started", metadata: aiInferenceMetadata(meta) })
}

export function trackAiShadowEvaluationCompleted(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_shadow_evaluation_completed", metadata: aiInferenceMetadata(meta) })
}

export function trackAiCanaryDeploymentCreated(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_canary_deployment_created", metadata: aiInferenceMetadata(meta) })
}

export function trackAiCanaryDeploymentApproved(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_canary_deployment_approved", metadata: aiInferenceMetadata(meta) })
}

export function trackAiCanaryDeploymentRejected(meta: AiInferenceAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "ai_canary_deployment_rejected", metadata: aiInferenceMetadata(meta) })
}

/** Allowed reaction ROI metadata only — no schemes, SMILES, conditions, supplier pricing, or free-text notes. */
export type ReactionAnalyticsMetadata = {
  reaction_project_id?: number
  experiment_count?: number
  objective?: string
  objective_type?: string
  advisor_mode?: string
  algorithm?: string
  batch_size?: number
  bo_run_id?: number
  status?: string
  duration_seconds?: number
  has_spectracheck_link?: boolean
  completed_experiment_count?: number
  recommendation_count?: number
  warning_count?: number
}

function reactionAnalyticsMetadata(meta: ReactionAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (meta.reaction_project_id != null && Number.isFinite(meta.reaction_project_id)) {
    out.reaction_project_id = meta.reaction_project_id
  }
  if (meta.experiment_count != null && Number.isFinite(meta.experiment_count)) {
    out.experiment_count = Math.max(0, Math.round(meta.experiment_count))
  }
  if (typeof meta.objective === "string" && meta.objective.trim()) {
    out.objective = meta.objective.trim()
  }
  if (typeof meta.objective_type === "string" && meta.objective_type.trim()) {
    out.objective_type = meta.objective_type.trim()
  }
  if (typeof meta.advisor_mode === "string" && meta.advisor_mode.trim()) {
    out.advisor_mode = meta.advisor_mode.trim()
  }
  if (typeof meta.algorithm === "string" && meta.algorithm.trim()) {
    out.algorithm = meta.algorithm.trim()
  }
  if (meta.batch_size != null && Number.isFinite(meta.batch_size)) {
    out.batch_size = Math.max(1, Math.round(meta.batch_size))
  }
  if (meta.bo_run_id != null && Number.isFinite(meta.bo_run_id)) {
    out.bo_run_id = Math.max(0, Math.round(meta.bo_run_id))
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim()
  }
  if (meta.duration_seconds != null && Number.isFinite(meta.duration_seconds)) {
    out.duration_seconds = Math.round(meta.duration_seconds * 1000) / 1000
  }
  if (meta.has_spectracheck_link === true || meta.has_spectracheck_link === false) {
    out.has_spectracheck_link = meta.has_spectracheck_link
  }
  if (meta.completed_experiment_count != null && Number.isFinite(meta.completed_experiment_count)) {
    out.completed_experiment_count = Math.max(0, Math.round(meta.completed_experiment_count))
  }
  if (meta.recommendation_count != null && Number.isFinite(meta.recommendation_count)) {
    out.recommendation_count = Math.max(0, Math.round(meta.recommendation_count))
  }
  if (meta.warning_count != null && Number.isFinite(meta.warning_count)) {
    out.warning_count = Math.max(0, Math.round(meta.warning_count))
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackReactionProjectCreated(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_project_created", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionExperimentAdded(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_experiment_added", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionOutcomeRecorded(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_outcome_recorded", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionOptimizationRunStarted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_optimization_run_started", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionOptimizationRunCompleted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_optimization_run_completed", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionRecommendationApproved(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_recommendation_approved", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionRecommendationRejected(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_recommendation_rejected", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackSpectracheckLinkedToReaction(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "spectracheck_linked_to_reaction", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionObjectiveProfileSaved(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_objective_profile_saved", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionCostProfileSaved(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_cost_profile_saved", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionSafetyProfileSaved(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_safety_profile_saved", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionBoRunStarted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_bo_run_started", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionBoRunCompleted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_bo_run_completed", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionRecommendationBatchCreated(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_recommendation_batch_created", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionBenchmarkRunStarted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_benchmark_run_started", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionBenchmarkRunCompleted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_benchmark_run_completed", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionAdvisorRunStarted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_advisor_run_started", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionAdvisorRunCompleted(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_advisor_run_completed", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionRecommendationCritiqued(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_recommendation_critiqued", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionMechanisticHypothesisCreated(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_mechanistic_hypothesis_created",
    metadata: reactionAnalyticsMetadata(meta),
  })
}

export function trackReactionPriorAdded(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_prior_added", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionBoAdvisorComparisonRun(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_bo_advisor_comparison_run", metadata: reactionAnalyticsMetadata(meta) })
}

export function trackReactionAdvisorReviewSaved(meta: ReactionAnalyticsMetadata): void {
  trackUsageEvent({ event_type: "reaction_advisor_review_saved", metadata: reactionAnalyticsMetadata(meta) })
}

/** Privacy-safe fields only — never conditions, outcomes, SMILES, notes, or analytical raw payloads. */
export type ReactionClosedLoopAnalyticsMetadata = {
  reaction_project_id?: number
  batch_id?: number
  item_id?: number
  status?: string
  result_type?: string
  has_spectracheck_link?: boolean
  has_artifact_id?: boolean
  outcome_fields_count?: number
  cycle_number?: number
}

export const CLOSED_LOOP_OUTCOME_SCALAR_KEYS = [
  "yield_percent",
  "conversion_percent",
  "selectivity_percent",
  "impurity_percent",
  "isolated_yield_percent",
  "lcms_area_percent",
  "nmr_purity_percent",
] as const

/** Count discrete outcome dimensions present — keys only; does not serialize values into analytics metadata. */
export function countClosedLoopOutcomeFieldKeys(po: Record<string, unknown>): number {
  let c = 0
  for (const k of CLOSED_LOOP_OUTCOME_SCALAR_KEYS) {
    const v = po[k]
    if (typeof v === "number" && Number.isFinite(v)) c++
  }
  const n = po.notes
  if (typeof n === "string" && n.trim()) c++
  return Math.min(c, 32)
}

function closedLoopReactionMetadata(meta: ReactionClosedLoopAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (meta.reaction_project_id != null && Number.isFinite(meta.reaction_project_id)) {
    out.reaction_project_id = Math.max(1, Math.round(meta.reaction_project_id))
  }
  if (meta.batch_id != null && Number.isFinite(meta.batch_id)) {
    out.batch_id = Math.max(1, Math.round(meta.batch_id))
  }
  if (meta.item_id != null && Number.isFinite(meta.item_id)) {
    out.item_id = Math.max(1, Math.round(meta.item_id))
  }
  if (typeof meta.status === "string" && meta.status.trim()) out.status = meta.status.trim().slice(0, 240)
  if (typeof meta.result_type === "string" && meta.result_type.trim()) {
    out.result_type = meta.result_type.trim().slice(0, 120)
  }
  if (meta.has_spectracheck_link === true || meta.has_spectracheck_link === false) {
    out.has_spectracheck_link = meta.has_spectracheck_link
  }
  if (meta.has_artifact_id === true || meta.has_artifact_id === false) {
    out.has_artifact_id = meta.has_artifact_id
  }
  if (meta.outcome_fields_count != null && Number.isFinite(meta.outcome_fields_count)) {
    out.outcome_fields_count = Math.max(0, Math.min(32, Math.round(meta.outcome_fields_count)))
  }
  if (meta.cycle_number != null && Number.isFinite(meta.cycle_number)) {
    out.cycle_number = Math.max(1, Math.round(meta.cycle_number))
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackReactionRecommendationConvertedToExperiment(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_recommendation_converted_to_experiment",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionExecutionBatchCreated(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_execution_batch_created",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionExecutionItemStarted(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_execution_item_started",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionExecutionItemCompleted(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_execution_item_completed",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionExecutionItemFailed(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_execution_item_failed",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionAnalyticalResultLinked(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_analytical_result_linked",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionOutcomeExtractionRun(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_outcome_extraction_run",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionOutcomeConfirmed(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_outcome_confirmed",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionOptimizationCycleCreated(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_optimization_cycle_created",
    metadata: closedLoopReactionMetadata(meta),
  })
}

export function trackReactionCycleDecisionSaved(meta: ReactionClosedLoopAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "reaction_cycle_decision_saved",
    metadata: closedLoopReactionMetadata(meta),
  })
}

/** Privacy-safe regulatory ROI metadata — ids, counts, and categorical labels only (no Q&A or scientific payloads). */
export type RegulatoryAnalyticsMetadata = {
  dossier_id?: number
  jurisdiction_id?: number | null
  status?: string
  requirement_count?: number
  evidence_link_count?: number
  risk_level?: string
  review_status?: string
}

function regulatoryAnalyticsMetadata(meta: RegulatoryAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (meta.dossier_id != null && Number.isFinite(meta.dossier_id)) {
    out.dossier_id = Math.max(1, Math.round(meta.dossier_id))
  }
  if (meta.jurisdiction_id === null) {
    out.jurisdiction_id = null
  } else if (meta.jurisdiction_id != null && Number.isFinite(meta.jurisdiction_id)) {
    out.jurisdiction_id = Math.max(1, Math.round(meta.jurisdiction_id))
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim().slice(0, 120)
  }
  if (meta.requirement_count != null && Number.isFinite(meta.requirement_count)) {
    out.requirement_count = Math.max(0, Math.round(meta.requirement_count))
  }
  if (meta.evidence_link_count != null && Number.isFinite(meta.evidence_link_count)) {
    out.evidence_link_count = Math.max(0, Math.round(meta.evidence_link_count))
  }
  if (typeof meta.risk_level === "string" && meta.risk_level.trim()) {
    out.risk_level = meta.risk_level.trim().slice(0, 64)
  }
  if (typeof meta.review_status === "string" && meta.review_status.trim()) {
    out.review_status = meta.review_status.trim().slice(0, 120)
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackRegulatoryDossierCreated(meta: RegulatoryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_dossier_created",
    metadata: regulatoryAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryRequirementAdded(meta: RegulatoryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_requirement_added",
    metadata: regulatoryAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryQueryAnswered(meta: RegulatoryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_query_answered",
    metadata: regulatoryAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryReadinessReportGenerated(meta: RegulatoryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_readiness_report_generated",
    metadata: regulatoryAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryReviewCompleted(meta: RegulatoryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_review_completed",
    metadata: regulatoryAnalyticsMetadata(meta),
  })
}

/**
 * Privacy-safe regulatory compliance engine signals — whitelist only (no free text, structures, spectra, or legal prose).
 * Allowed keys: dossier_id, action_type, severity, status, risk_category, readiness_status, jurisdiction_count,
 * action_item_count, has_citations.
 */
export type RegulatoryComplianceEngineAnalyticsMetadata = {
  dossier_id?: number
  action_type?: string
  severity?: string
  status?: string
  risk_category?: string
  readiness_status?: string
  jurisdiction_count?: number
  action_item_count?: number
  has_citations?: boolean
}

function regulatoryComplianceEngineMetadata(
  meta: RegulatoryComplianceEngineAnalyticsMetadata,
): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (meta.dossier_id != null && Number.isFinite(meta.dossier_id)) {
    out.dossier_id = Math.max(1, Math.round(meta.dossier_id))
  }
  if (typeof meta.action_type === "string" && meta.action_type.trim()) {
    out.action_type = meta.action_type.trim().slice(0, 120)
  }
  if (typeof meta.severity === "string" && meta.severity.trim()) {
    out.severity = meta.severity.trim().slice(0, 64)
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim().slice(0, 120)
  }
  if (typeof meta.risk_category === "string" && meta.risk_category.trim()) {
    out.risk_category = meta.risk_category.trim().slice(0, 120)
  }
  if (typeof meta.readiness_status === "string" && meta.readiness_status.trim()) {
    out.readiness_status = meta.readiness_status.trim().slice(0, 120)
  }
  if (meta.jurisdiction_count != null && Number.isFinite(meta.jurisdiction_count)) {
    out.jurisdiction_count = Math.max(0, Math.round(meta.jurisdiction_count))
  }
  if (meta.action_item_count != null && Number.isFinite(meta.action_item_count)) {
    out.action_item_count = Math.max(0, Math.round(meta.action_item_count))
  }
  if (meta.has_citations === true || meta.has_citations === false) {
    out.has_citations = meta.has_citations
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackRegulatoryImpurityRegisterCreated(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_impurity_register_created",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryResidualSolventAssessed(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_residual_solvent_assessed",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryNitrosamineWatchRun(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_nitrosamine_watch_run",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryQnmrComplianceAssessed(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_qnmr_compliance_assessed",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryMethodValidationAssessed(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_method_validation_assessed",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryAiGovernanceRecordCreated(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_ai_governance_record_created",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryJurisdictionalMapCreated(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_jurisdictional_map_created",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryActionItemCreated(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_action_item_created",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryActionItemResolved(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_action_item_resolved",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

export function trackRegulatoryBatchAssessmentRun(meta: RegulatoryComplianceEngineAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_batch_assessment_run",
    metadata: regulatoryComplianceEngineMetadata(meta),
  })
}

/**
 * Regulatory Surveillance analytics — explicit whitelist only (no source text, diffs, dossier copy, structures, spectra,
 * tokens, or secrets).
 */
export type RegulatorySurveillanceAnalyticsMetadata = {
  watcher_id?: number
  source_type?: string
  jurisdiction_id?: number | null
  change_type?: string
  severity?: string
  affected_dossier_count?: number
  affected_rule_count?: number
  proposal_type?: string
  status?: string
}

function regulatorySurveillanceAnalyticsMetadata(
  meta: RegulatorySurveillanceAnalyticsMetadata,
): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (meta.watcher_id != null && Number.isFinite(meta.watcher_id)) {
    out.watcher_id = Math.max(1, Math.round(meta.watcher_id))
  }
  if (typeof meta.source_type === "string" && meta.source_type.trim()) {
    out.source_type = meta.source_type.trim().slice(0, 64)
  }
  if (meta.jurisdiction_id === null) {
    out.jurisdiction_id = null
  } else if (meta.jurisdiction_id != null && Number.isFinite(meta.jurisdiction_id)) {
    out.jurisdiction_id = Math.max(1, Math.round(meta.jurisdiction_id))
  }
  if (typeof meta.change_type === "string" && meta.change_type.trim()) {
    out.change_type = meta.change_type.trim().slice(0, 64)
  }
  if (typeof meta.severity === "string" && meta.severity.trim()) {
    out.severity = meta.severity.trim().slice(0, 64)
  }
  if (meta.affected_dossier_count != null && Number.isFinite(meta.affected_dossier_count)) {
    out.affected_dossier_count = Math.max(0, Math.round(meta.affected_dossier_count))
  }
  if (meta.affected_rule_count != null && Number.isFinite(meta.affected_rule_count)) {
    out.affected_rule_count = Math.max(0, Math.round(meta.affected_rule_count))
  }
  if (typeof meta.proposal_type === "string" && meta.proposal_type.trim()) {
    out.proposal_type = meta.proposal_type.trim().slice(0, 64)
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim().slice(0, 120)
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackRegulatoryWatcherCreated(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_watcher_created",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatorySurveillanceRunStarted(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_surveillance_run_started",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryChangeDetectedViewed(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_change_detected_viewed",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryImpactAssessmentRun(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_impact_assessment_run",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryRuleUpdateProposalCreated(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_rule_update_proposal_created",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryRuleUpdateProposalApproved(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_rule_update_proposal_approved",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryRuleUpdateProposalRejected(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_rule_update_proposal_rejected",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

export function trackRegulatoryNotificationResolved(meta: RegulatorySurveillanceAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "regulatory_notification_resolved",
    metadata: regulatorySurveillanceAnalyticsMetadata(meta),
  })
}

/** Privacy-safe compound registry analytics — ids and categorical flags only (no structures, names, or free text). */
export type CompoundRegistryAnalyticsMetadata = {
  compound_id?: number
  batch_id?: number
  compound_type?: string
  source_type?: string
  has_structure?: boolean
  has_batch?: boolean
  linked_resource_type?: string
  status?: string
}

function compoundRegistryAnalyticsMetadata(
  meta: CompoundRegistryAnalyticsMetadata,
): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (meta.compound_id != null && Number.isFinite(meta.compound_id)) {
    out.compound_id = Math.max(1, Math.round(meta.compound_id))
  }
  if (meta.batch_id != null && Number.isFinite(meta.batch_id)) {
    out.batch_id = Math.max(1, Math.round(meta.batch_id))
  }
  if (typeof meta.compound_type === "string" && meta.compound_type.trim()) {
    out.compound_type = meta.compound_type.trim().slice(0, 64)
  }
  if (typeof meta.source_type === "string" && meta.source_type.trim()) {
    out.source_type = meta.source_type.trim().slice(0, 64)
  }
  if (typeof meta.has_structure === "boolean") {
    out.has_structure = meta.has_structure
  }
  if (typeof meta.has_batch === "boolean") {
    out.has_batch = meta.has_batch
  }
  if (typeof meta.linked_resource_type === "string" && meta.linked_resource_type.trim()) {
    out.linked_resource_type = meta.linked_resource_type.trim().slice(0, 64)
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim().slice(0, 120)
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function trackCompoundCreated(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "compound_created",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

export function trackCompoundLinkedToSpectracheck(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "compound_linked_to_spectracheck",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

export function trackCompoundLinkedToReaction(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "compound_linked_to_reaction",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

export function trackCompoundLinkedToRegulatoryDossier(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "compound_linked_to_regulatory_dossier",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

export function trackBatchCreated(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "batch_created",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

export function trackAliquotCreated(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "aliquot_created",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

export function trackCompoundGraphViewed(meta: CompoundRegistryAnalyticsMetadata): void {
  trackUsageEvent({
    event_type: "compound_graph_viewed",
    metadata: compoundRegistryAnalyticsMetadata(meta),
  })
}

/** Whitelist: task_key, model_family, target_module, status, dataset_type, metric_count, warning_count, has_model_card, approval_status — no raw payloads. */
export type MlFactoryAnalyticsMetadata = {
  task_key?: string
  model_family?: string
  target_module?: string
  status?: string
  dataset_type?: string
  metric_count?: number
  warning_count?: number
  has_model_card?: boolean
  approval_status?: string
}

/** Count top-level keys in a JSON object — cardinality only, values never sent. */
export function countMetricKeysForAnalytics(obj: unknown): number | undefined {
  if (obj == null || typeof obj !== "object" || Array.isArray(obj)) return undefined
  const n = Object.keys(obj as Record<string, unknown>).length
  return Number.isFinite(n) ? Math.min(n, 500_000) : undefined
}

function mlFactoryAnalyticsMetadata(meta: MlFactoryAnalyticsMetadata): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  if (typeof meta.task_key === "string" && meta.task_key.trim()) {
    out.task_key = meta.task_key.trim().slice(0, 200)
  }
  if (typeof meta.model_family === "string" && meta.model_family.trim()) {
    out.model_family = meta.model_family.trim().slice(0, 120)
  }
  if (typeof meta.target_module === "string" && meta.target_module.trim()) {
    out.target_module = meta.target_module.trim().slice(0, 120)
  }
  if (typeof meta.status === "string" && meta.status.trim()) {
    out.status = meta.status.trim().slice(0, 120)
  }
  if (typeof meta.dataset_type === "string" && meta.dataset_type.trim()) {
    out.dataset_type = meta.dataset_type.trim().slice(0, 160)
  }
  if (typeof meta.metric_count === "number" && Number.isFinite(meta.metric_count) && meta.metric_count >= 0) {
    out.metric_count = Math.min(Math.floor(meta.metric_count), 1_000_000)
  }
  if (typeof meta.warning_count === "number" && Number.isFinite(meta.warning_count) && meta.warning_count >= 0) {
    out.warning_count = Math.min(Math.floor(meta.warning_count), 1_000_000)
  }
  if (typeof meta.has_model_card === "boolean") {
    out.has_model_card = meta.has_model_card
  }
  if (typeof meta.approval_status === "string" && meta.approval_status.trim()) {
    out.approval_status = meta.approval_status.trim().slice(0, 120)
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function trackMlFactoryEvent(event_type: string, meta: MlFactoryAnalyticsMetadata): void {
  trackUsageEvent({ event_type, metadata: mlFactoryAnalyticsMetadata(meta) })
}

export function trackMlTrainingRunStarted(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_training_run_started", meta)
}

export function trackMlTrainingRunCompleted(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_training_run_completed", meta)
}

export function trackMlEvaluationRunStarted(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_evaluation_run_started", meta)
}

export function trackMlEvaluationRunCompleted(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_evaluation_run_completed", meta)
}

export function trackMlModelCardCreated(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_model_card_created", meta)
}

export function trackMlCalibrationAssessmentCreated(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_calibration_assessment_created", meta)
}

export function trackMlErrorAnalysisCreated(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_error_analysis_created", meta)
}

export function trackMlOodAssessmentCreated(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_ood_assessment_created", meta)
}

export function trackMlDeploymentCandidateCreated(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_deployment_candidate_created", meta)
}

export function trackMlDeploymentCandidateApproved(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_deployment_candidate_approved", meta)
}

export function trackMlDeploymentCandidateRejected(meta: MlFactoryAnalyticsMetadata): void {
  trackMlFactoryEvent("ml_deployment_candidate_rejected", meta)
}
