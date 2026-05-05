/**
 * Workflow trace for Report Composer — merged under provenance_metadata.workflow_provenance.
 * Field names are descriptive only; backend may ignore unknown nested keys.
 */

import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"
import { apiFetch } from "@/lib/api/client"
import { normalizeArtifactsListPayload, normalizeArtifactRow } from "@/src/lib/spectracheck/report-provenance-bundle"
import { normalizeWorkflowRunsList } from "@/src/lib/dashboard/overview-metrics"

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

function extractArray(root: unknown, keys: string[]): unknown[] {
  if (Array.isArray(root)) return root
  if (!isRecord(root)) return []
  for (const k of keys) {
    const v = root[k]
    if (Array.isArray(v)) return v
  }
  return []
}

/** Collect workflow_run_id from evidence queue rows (workflow handoffs). */
export function extractWorkflowRunIdsFromEvidence(items: EvidenceItem[]): string[] {
  const ids = new Set<string>()
  for (const item of items) {
    const rp = item.requestPreview
    if (isRecord(rp)) {
      const w =
        readStr(rp, ["workflow_run_id", "workflowRunId"]) ||
        (typeof rp.workflow_run_id === "string" ? rp.workflow_run_id : "")
      if (w) ids.add(w.trim())
    }
    const resp = item.response
    if (isRecord(resp)) {
      const w =
        readStr(resp, ["workflow_run_id", "workflowRunId"]) ||
        readStr(resp, ["workflow_run_id"]) ||
        ""
      if (w) ids.add(w.trim())
    }
  }
  return [...ids]
}

function parseWorkflowRunStatus(runPayload: unknown): string {
  if (!isRecord(runPayload)) return ""
  const s =
    readStr(runPayload, ["status", "workflow_status", "workflowStatus", "state", "run_status"]) ||
    (isRecord(runPayload.workflow_run) ? readStr(runPayload.workflow_run, ["status", "state"]) : "")
  return s.trim().toLowerCase().replace(/-/g, "_")
}

function parseTemplateName(runPayload: unknown): string | null {
  if (!isRecord(runPayload)) return null
  const n =
    readStr(runPayload, ["template_name", "templateName", "workflow_template_name"]) ||
    readStr(runPayload, ["template_slug", "templateSlug"]) ||
    ""
  if (n) return n
  const meta = runPayload.metadata ?? runPayload.workflow_metadata
  if (isRecord(meta)) {
    const m =
      readStr(meta, ["template_name", "templateName", "template_slug"]) ||
      ""
    if (m) return m
  }
  return null
}

function parseTemplateVersion(runPayload: unknown): string | null {
  if (!isRecord(runPayload)) return null
  const direct =
    readStr(runPayload, ["template_version", "templateVersion", "workflow_template_version", "template_semver"]) || ""
  if (direct) return direct
  const meta = runPayload.metadata ?? runPayload.workflow_metadata
  if (isRecord(meta)) {
    const mv = readStr(meta, ["template_version", "templateVersion", "workflow_template_version"]) || ""
    if (mv) return mv
  }
  return null
}

function summarizeStepsPayload(stepsPayload: unknown): string[] {
  const rows = extractArray(stepsPayload, ["steps", "workflow_steps", "items", "results"])
  const lines: string[] = []
  for (const r of rows) {
    if (!isRecord(r)) continue
    const name =
      readStr(r, ["name", "title", "label", "step_name", "stepName"]) ||
      readStr(r, ["id", "step_id"]) ||
      "step"
    const st = readStr(r, ["status", "step_status", "state"]) || "—"
    lines.push(`${name} · ${st}`)
  }
  return lines
}

function qcBlobFromRun(runPayload: unknown): unknown | null {
  if (!isRecord(runPayload)) return null
  const qc = runPayload.qc_results ?? runPayload.qc ?? runPayload.quality_control
  if (qc != null) return qc
  const keys = ["qc_status", "qcStatus", "warnings", "blocking_reason"]
  const pick: Record<string, unknown> = {}
  let any = false
  for (const k of keys) {
    if (runPayload[k] !== undefined) {
      pick[k] = runPayload[k]
      any = true
    }
  }
  return any ? pick : null
}

export type WorkflowRunProvenanceRow = {
  workflow_run_id: string
  template_name: string | null
  template_version: string | null
  workflow_run_status: string | null
  steps_completed_summary: string[]
  artifacts_included: Array<{ artifact_id: string; artifact_type: string; title: string; sha256: string | null }>
  qc_results: unknown | null
}

const MAX_RUNS_TO_FETCH = 12

export async function loadWorkflowProvenanceForReport(
  sessionId: string | null,
  selectedEvidence: EvidenceItem[],
): Promise<{ payload: Record<string, unknown>; loadErrors: string[] }> {
  const sid = sessionId?.trim() ?? ""
  const loadErrors: string[] = []
  const runIdsFromEvidence = extractWorkflowRunIdsFromEvidence(selectedEvidence)

  let sessionRunsList: Record<string, unknown>[] = []
  if (sid) {
    try {
      const sessionRunsRaw = await apiFetch<unknown>(
        `/spectracheck/sessions/${encodeURIComponent(sid)}/workflow-runs`,
        { method: "GET" },
      )
      sessionRunsList = normalizeWorkflowRunsList(sessionRunsRaw)
    } catch {
      loadErrors.push("session_workflow_runs_unavailable")
    }
  }

  const idFromRow = (r: Record<string, unknown>) =>
    readStr(r, ["workflow_run_id", "workflowRunId", "id", "run_id"]) || ""

  const idsFromSession = sessionRunsList.map(idFromRow).filter(Boolean)
  const merged = new Set<string>([...runIdsFromEvidence, ...idsFromSession])
  const runIds = [...merged].slice(0, MAX_RUNS_TO_FETCH)

  const workflow_runs: WorkflowRunProvenanceRow[] = []

  for (const rid of runIds) {
    try {
      const [runPayload, stepsPayload, artifactsPayload] = await Promise.all([
        apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}`, { method: "GET" }),
        apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}/steps`, { method: "GET" }).catch(() => null),
        apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}/artifacts`, { method: "GET" }).catch(() => null),
      ])
      const arts = normalizeArtifactsListPayload(artifactsPayload ?? [])
      const artifacts_included = arts.map((a) => {
        const n = normalizeArtifactRow(a)
        return {
          artifact_id: n.artifact_id,
          artifact_type: n.artifact_type,
          title: n.title,
          sha256: n.sha256,
        }
      })
      workflow_runs.push({
        workflow_run_id: rid,
        template_name: parseTemplateName(runPayload),
        template_version: parseTemplateVersion(runPayload),
        workflow_run_status: parseWorkflowRunStatus(runPayload) || null,
        steps_completed_summary: summarizeStepsPayload(stepsPayload),
        artifacts_included,
        qc_results: qcBlobFromRun(runPayload),
      })
    } catch {
      loadErrors.push(`workflow_run_fetch_failed:${rid}`)
    }
  }

  const evidence_queue_items_selected = selectedEvidence.map((i) => {
    const rp = i.requestPreview
    const pr = isRecord(rp) ? rp : null
    const wf = pr ? readStr(pr, ["workflow_run_id", "workflowRunId"]) || null : null
    const art = pr ? readStr(pr, ["artifact_id", "artifactId"]) || null : null
    return {
      evidence_item_id: i.id,
      layer: i.layer,
      title: i.title,
      selected_for_unified: i.selectedForUnified,
      workflow_run_id: wf,
      artifact_id: art,
      qc_status: i.qcStatus ?? null,
      readiness_status: i.readinessStatus ?? null,
    }
  })

  const payload: Record<string, unknown> = {
    workflow_runs,
    evidence_queue_items_selected,
  }

  if (loadErrors.length > 0) {
    payload.workflow_provenance_load_errors = loadErrors
  }

  return { payload, loadErrors }
}
