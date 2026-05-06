import { apiFetch } from "@/lib/api/client"
import type { QcProvenanceSectionPayload } from "@/src/lib/spectracheck/evidence-queue-qc"
import type { MethodProvenancePayload } from "@/src/lib/spectracheck/report-method-provenance"
import { normalizeSessionFileRecordList, type SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import {
  buildDashboardJobRows,
  normalizeJobsList,
  type DashboardJobRow,
} from "@/src/lib/dashboard/overview-metrics"
import type { SelectedVisualEvidenceEntry } from "@/src/lib/spectracheck/report-visual-evidence"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return null
}

/** GET /spectracheck/sessions/{id}/artifacts — list normalization (same shape as Artifact Browser). */
export function normalizeArtifactsListPayload(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.artifacts)) return data.artifacts.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

export function normalizeArtifactRow(a: Record<string, unknown>): {
  artifact_id: string
  title: string
  artifact_type: string
  job_id: string | null
  sha256: string | null
} {
  const artifact_id =
    readStr(a.artifact_id) ?? readStr(a.id) ?? readStr(a.artifactId) ?? "—"
  return {
    artifact_id,
    title: readStr(a.title) ?? readStr(a.name) ?? artifact_id,
    artifact_type: readStr(a.artifact_type) ?? readStr(a.type) ?? "other",
    job_id: readStr(a.job_id) ?? readStr(a.jobId) ?? null,
    sha256: readStr(a.sha256) ?? readStr(a.file_sha256) ?? null,
  }
}

function jobSessionId(j: Record<string, unknown>): string | null {
  return (
    readStr(j.session_id) ??
    readStr(j.sessionId) ??
    readStr(j.spectracheck_session_id) ??
    readStr(j.spectracheckSessionId)
  )
}

export function filterJobsForSession(
  jobs: Record<string, unknown>[],
  sessionId: string,
): Record<string, unknown>[] {
  const sid = sessionId.trim()
  if (!sid) return []
  return jobs.filter((j) => {
    const js = jobSessionId(j)
    return js != null && js === sid
  })
}

export type ReportProvenanceMetadata = {
  spectracheck_session_id: string | null
  sample_id: string | null
  source_file_sha256_list: string[]
  derived_artifact_sha256_list: string[]
  artifact_ids: string[]
  session_files: Array<{
    file_id: string
    filename: string
    file_kind: string
    sha256: string | null
  }>
  analysis_jobs: DashboardJobRow[]
  artifacts: Array<{
    artifact_id: string
    title: string
    artifact_type: string
    job_id: string | null
    sha256: string | null
  }>
  job_timeline_summary: string[]
  review_status_compose: string | null
  session_review: unknown | null
  audit_events: unknown[]
  evidence_queue_handoff: unknown | null
  unified_confidence_result: unknown | null
  /** Lines from compose form processing history (same as processing_history_text split). */
  processing_history_lines: string[]
  /** Session QC + selected evidence QC snapshot for compose payloads (optional). */
  qc_provenance_section?: QcProvenanceSectionPayload | null
  /** Workflow runs/steps/artifacts trace when loaded (optional nested metadata). */
  workflow_provenance?: unknown | null
  /** Method / model / scoring / threshold trace for selected evidence (optional). */
  method_provenance?: MethodProvenancePayload | null
  /** Selected queue rows with visualizable payloads (artifact refs + plot placeholders; no embedded images). */
  selected_visual_evidence?: SelectedVisualEvidenceEntry[]
  /** Optional controlled AI prediction provenance (decision-support only). */
  ai_prediction_provenance?: {
    prediction_run_id: string | null
    model_artifact_id: number | null
    deployment_candidate_id: number | null
    service_key: string | null
    confidence_score: number | null
    uncertainty: number | null
    ood_status: string | null
    human_review_required: boolean | null
    feedback_status: string | null
    model_version: string | null
    active_learning_flag: boolean | null
  } | null
}

export function buildReportProvenanceMetadata(args: {
  backendSessionId: string | null
  sampleId: string
  sessionFiles: SessionFileRecord[]
  jobsForSession: Record<string, unknown>[]
  artifactRecords: Record<string, unknown>[]
  evidenceQueueHandoff: unknown | null
  latestUnifiedConfidenceResult: unknown | null
  reviewStatusCompose: string
  sessionReviewSnapshot: unknown | null
  auditEvents: unknown[]
  processingHistoryLines: string[]
  selectedVisualEvidence: SelectedVisualEvidenceEntry[]
}): ReportProvenanceMetadata {
  const sessionFilesNorm = args.sessionFiles.map((f) => ({
    file_id: f.file_id,
    filename: f.filename,
    file_kind: f.file_kind,
    sha256: f.sha256,
  }))
  const sourceHashes = new Set<string>()
  for (const f of args.sessionFiles) {
    const h = f.sha256?.trim()
    if (h) sourceHashes.add(h)
  }

  const artifacts = args.artifactRecords.map((r) => normalizeArtifactRow(r))
  const derivedHashes = new Set<string>()
  const artifactIds: string[] = []
  for (const a of artifacts) {
    artifactIds.push(a.artifact_id)
    const h = a.sha256?.trim()
    if (h) derivedHashes.add(h)
  }

  const jobRows = buildDashboardJobRows(args.jobsForSession, 50)
  const job_timeline_summary = jobRows.map((j) => {
    const p = j.progressPercent != null ? `${Math.round(j.progressPercent)}%` : "—"
    return `${j.jobType} · ${j.status} · ${p} · ${j.updatedAt ?? "—"}`
  })

  return {
    spectracheck_session_id: args.backendSessionId?.trim() || null,
    sample_id: args.sampleId.trim() || null,
    source_file_sha256_list: [...sourceHashes],
    derived_artifact_sha256_list: [...derivedHashes],
    artifact_ids: artifactIds,
    session_files: sessionFilesNorm,
    analysis_jobs: jobRows,
    artifacts,
    job_timeline_summary,
    review_status_compose: args.reviewStatusCompose.trim() || null,
    session_review: args.sessionReviewSnapshot,
    audit_events: args.auditEvents,
    evidence_queue_handoff: args.evidenceQueueHandoff,
    unified_confidence_result: args.latestUnifiedConfidenceResult,
    processing_history_lines: args.processingHistoryLines,
    ...(args.selectedVisualEvidence.length > 0
      ? { selected_visual_evidence: args.selectedVisualEvidence }
      : {}),
  }
}

export async function fetchReportProvenanceData(sessionId: string): Promise<{
  files: SessionFileRecord[]
  allJobs: Record<string, unknown>[]
  artifacts: Record<string, unknown>[]
}> {
  const sid = encodeURIComponent(sessionId.trim())
  const [filesRaw, jobsRaw, artRaw] = await Promise.all([
    apiFetch<unknown>(`/spectracheck/sessions/${sid}/files`, { method: "GET" }),
    apiFetch<unknown>("/jobs", { method: "GET" }),
    apiFetch<unknown>(`/spectracheck/sessions/${sid}/artifacts`, { method: "GET" }),
  ])
  return {
    files: normalizeSessionFileRecordList(filesRaw),
    allJobs: normalizeJobsList(jobsRaw),
    artifacts: normalizeArtifactsListPayload(artRaw),
  }
}
