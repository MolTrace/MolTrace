/**
 * Scientific method provenance for Report Composer — merged under provenance_metadata.method_provenance.
 * Nested keys are descriptive; backends may ignore unknown fields.
 */

import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"
import { hasMethodProvenanceFields } from "@/src/lib/spectracheck/evidence-method-provenance"
import { mergeMlModelProvenancePreferItem, hasRenderableMlRegistryProvenance } from "@/src/lib/ml/model-provenance-extract"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function workflowRunIdFromEvidence(item: EvidenceItem): string | null {
  const rp = item.requestPreview
  if (isRecord(rp)) {
    const w = readStr(rp, ["workflow_run_id", "workflowRunId"])
    if (w) return w.trim()
  }
  const resp = item.response
  if (isRecord(resp)) {
    const w = readStr(resp, ["workflow_run_id", "workflowRunId"])
    if (w) return w.trim()
  }
  return null
}

function findWorkflowRunRow(runs: unknown, runId: string | null): Record<string, unknown> | null {
  if (!runId?.trim() || !Array.isArray(runs)) return null
  const rid = runId.trim()
  for (const r of runs) {
    if (!isRecord(r)) continue
    const id =
      readStr(r, ["workflow_run_id", "workflowRunId", "id", "run_id"]) ||
      (typeof r.id === "number" ? String(r.id) : "")
    if (id && id === rid) return r
  }
  return null
}

function pickTemplateVersionFromRunRow(row: Record<string, unknown> | null): string | null {
  if (!row) return null
  const tv =
    readStr(row, ["template_version", "templateVersion", "workflow_template_version"]) ||
    readStr(row, ["template_semver"])
  return tv || null
}

function unifiedValidationLabel(unified: unknown): string | null {
  if (!isRecord(unified)) return null
  return (
    readStr(unified, ["validation_status", "validationStatus", "review_status", "reviewStatus", "status"]) || null
  )
}

export type MethodProvenancePayload = {
  evidence_items: Array<Record<string, unknown>>
  composer_context: { intended_use: string | null; review_status: string | null }
  qc_session_snapshot_present: boolean
  unified_confidence_snapshot_present: boolean
  unified_validation_status: string | null
  warning_legacy_evidence_without_method_provenance: boolean
  warning_legacy_evidence_without_ml_registry_provenance: boolean
}

export function buildMethodProvenanceForReport(args: {
  selectedEvidence: EvidenceItem[]
  workflowProvenanceMerged: Record<string, unknown> | null
  sessionQcRaw: unknown | null
  latestUnifiedResult: unknown | null
  intendedUse: string
  reviewStatus: string
}): MethodProvenancePayload {
  const workflowRuns = args.workflowProvenanceMerged?.workflow_runs

  const evidence_items = args.selectedEvidence.map((i) => {
    const wfId = workflowRunIdFromEvidence(i)
    const wr = findWorkflowRunRow(workflowRuns, wfId)
    const templateVersion = pickTemplateVersionFromRunRow(wr)
    const templateName = wr ? readStr(wr, ["template_name", "templateName"]) || null : null

    const methodName = i.methodName ?? i.methodId ?? null
    const methodVersion = i.methodVersion ?? null
    const modelVersionParts = [i.modelName, i.modelVersion, i.modelVersionId].filter(
      (x): x is string => typeof x === "string" && x.trim().length > 0,
    )
    const modelVersion = modelVersionParts.length > 0 ? modelVersionParts.join(" · ") : null
    const scoring = i.scoringProfileName ?? i.scoringProfileId ?? null
    const threshold = i.thresholdProfileName ?? i.thresholdProfileId ?? null

    const qcParts: string[] = []
    if (i.qcStatus) qcParts.push(String(i.qcStatus))
    if (i.readinessStatus) qcParts.push(String(i.readinessStatus))
    const validationStatus = qcParts.length > 0 ? qcParts.join(" · ") : null

    const workflowTemplateLabel = templateVersion?.trim() || templateName?.trim() || null

    const ml = mergeMlModelProvenancePreferItem(
      {
        modelArtifactId: i.modelArtifactId,
        datasetVersionId: i.datasetVersionId,
        evaluationRunId: i.evaluationRunId,
        deploymentCandidateId: i.deploymentCandidateId,
        modelCardId: i.modelCardId,
        approvalStatus: i.approvalStatus,
        modelName: i.modelName,
        modelVersion: i.modelVersion,
        methodId: i.methodId,
      },
      i.response,
      i.requestPreview,
    )
    const modelLine =
      ml.modelName || ml.modelVersion
        ? [ml.modelName, ml.modelVersion].filter((x): x is string => typeof x === "string" && x.trim().length > 0).join(" · ")
        : null

    return {
      evidence_item_id: i.id,
      evidence_layer: i.layer,
      method_name: methodName,
      method_version: methodVersion,
      model_version: modelVersion,
      scoring_profile: scoring,
      threshold_profile: threshold,
      workflow_template_version: workflowTemplateLabel,
      workflow_template_name: templateName,
      workflow_run_id: wfId,
      validation_status: validationStatus,
      quality_assessment_id: i.qualityAssessmentId ?? null,
      method_provenance_recorded: hasMethodProvenanceFields(i),
      model_artifact_id: ml.modelArtifactId ?? null,
      dataset_version_id: ml.datasetVersionId ?? null,
      evaluation_run_id: ml.evaluationRunId ?? null,
      deployment_candidate_id: ml.deploymentCandidateId ?? null,
      model_card_id: ml.modelCardId ?? null,
      approval_status: ml.approvalStatus ?? null,
      registry_method_id: ml.methodId ?? null,
      registry_model_display: modelLine,
      ml_registry_provenance_recorded: hasRenderableMlRegistryProvenance(ml),
    }
  })

  const someMissing =
    args.selectedEvidence.length > 0 && args.selectedEvidence.some((i) => !hasMethodProvenanceFields(i))
  const someMlMissing =
    args.selectedEvidence.length > 0 &&
    args.selectedEvidence.some((i) => {
      const ml = mergeMlModelProvenancePreferItem(
        {
          modelArtifactId: i.modelArtifactId,
          datasetVersionId: i.datasetVersionId,
          evaluationRunId: i.evaluationRunId,
          deploymentCandidateId: i.deploymentCandidateId,
          modelCardId: i.modelCardId,
          approvalStatus: i.approvalStatus,
          modelName: i.modelName,
          modelVersion: i.modelVersion,
          methodId: i.methodId,
        },
        i.response,
        i.requestPreview,
      )
      return !hasRenderableMlRegistryProvenance(ml)
    })

  return {
    evidence_items,
    composer_context: {
      intended_use: args.intendedUse.trim() || null,
      review_status: args.reviewStatus.trim() || null,
    },
    qc_session_snapshot_present: args.sessionQcRaw != null,
    unified_confidence_snapshot_present: args.latestUnifiedResult != null,
    unified_validation_status: unifiedValidationLabel(args.latestUnifiedResult),
    warning_legacy_evidence_without_method_provenance: someMissing,
    warning_legacy_evidence_without_ml_registry_provenance: someMlMissing,
  }
}
