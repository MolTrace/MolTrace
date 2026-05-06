import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function normalizeSpectraCheckSessionsList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.sessions)) return data.sessions.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function normStatus(s: Record<string, unknown>): string {
  const raw =
    readRecordString(s, "status") ??
    readRecordString(s, "session_status") ??
    readRecordString(s, "state")
  return (raw ?? "").trim().toLowerCase().replace(/\s+/g, "_")
}

function readReviewStatus(s: Record<string, unknown>): string {
  const direct = readRecordString(s, "review_status") ?? readRecordString(s, "reviewStatus")
  if (direct) return direct.trim().toLowerCase()
  const rev = s.review
  if (isRecord(rev)) {
    const r = readRecordString(rev, "review_status") ?? readRecordString(rev, "reviewStatus")
    if (r) return r.trim().toLowerCase()
  }
  return ""
}

function warnCount(s: Record<string, unknown>): number {
  const w = s.warnings
  if (Array.isArray(w)) return w.length
  const n = readRecordNumber(s, "warning_count")
  return n != null && n >= 0 ? n : 0
}

function contraCount(s: Record<string, unknown>): number {
  const c = s.contradictions
  if (Array.isArray(c)) return c.length
  const n = readRecordNumber(s, "contradiction_count")
  return n != null && n >= 0 ? n : 0
}

function readUpdatedAtMs(s: Record<string, unknown>): number {
  for (const k of ["updated_at", "modified_at", "saved_at", "created_at", "last_saved_at"]) {
    const t = readRecordString(s, k)
    if (t) {
      const d = Date.parse(t)
      if (!Number.isNaN(d)) return d
    }
  }
  return 0
}

function sessionIdOf(s: Record<string, unknown>): string {
  const sid =
    readRecordString(s, "id") ??
    readRecordString(s, "session_id") ??
    readRecordString(s, "sessionId")
  if (sid) return sid
  const n = readRecordNumber(s, "id")
  return n != null ? String(n) : "—"
}

function sampleIdOf(s: Record<string, unknown>): string {
  return (
    readRecordString(s, "sample_id") ??
    readRecordString(s, "sampleId") ??
    readRecordString(s, "sample_record_id") ??
    "—"
  )
}

function sessionHasReportArtifact(s: Record<string, unknown>): boolean {
  const arts = s.artifacts
  if (!Array.isArray(arts)) return false
  for (const a of arts) {
    if (!isRecord(a)) continue
    const t =
      readRecordString(a, "artifact_type") ??
      readRecordString(a, "type") ??
      readRecordString(a, "kind")
    if (t) {
      const n = t.toLowerCase()
      if (n.includes("report_json") || n.includes("report_html") || n === "report" || n.includes("report")) {
        return true
      }
    }
  }
  return false
}

function sessionReportsReady(s: Record<string, unknown>): boolean {
  if (sessionHasReportArtifact(s)) return true
  const st = normStatus(s)
  if (["report_ready", "approved_for_release", "released", "published"].includes(st)) return true
  const flag =
    s.has_saved_report === true ||
    s.report_saved === true ||
    s.has_report === true ||
    s.report_ready === true
  if (flag) return true
  const rs = readReviewStatus(s)
  if (rs === "approved_plausible" || rs === "approved_confirmed") return true
  return false
}

export type DashboardMetricCounts = {
  activeAnalyses: number
  reviewRequired: number
  reviewRequiredWithContradictions: number
  reportsReady: number
  evidenceQueue: number
  /** From GET /jobs when available */
  jobsCompleted?: number
  jobsFailed?: number
}

function parseJobStatusRaw(j: Record<string, unknown>): string {
  const raw =
    readRecordString(j, "status") ??
    readRecordString(j, "job_status") ??
    readRecordString(j, "state") ??
    readRecordString(j, "phase")
  return (raw ?? "").trim().toLowerCase().replace(/-/g, "_")
}

function isJobQueuedOrRunning(st: string): boolean {
  return st === "queued" || st === "running" || st === "pending" || st === "processing"
}

function isJobSucceeded(st: string): boolean {
  return st === "succeeded" || st === "success" || st === "completed"
}

function isJobFailed(st: string): boolean {
  return st === "failed" || st === "error"
}

export function normalizeJobsList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.jobs)) return data.jobs.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function countJobsByLifecycle(jobs: Record<string, unknown>[]): {
  active: number
  completed: number
  failed: number
} {
  let active = 0
  let completed = 0
  let failed = 0
  for (const j of jobs) {
    const st = parseJobStatusRaw(j)
    if (isJobQueuedOrRunning(st)) active += 1
    else if (isJobSucceeded(st)) completed += 1
    else if (isJobFailed(st)) failed += 1
  }
  return { active, completed, failed }
}

export type DashboardJobRow = {
  id: string
  jobType: string
  status: string
  progressPercent: number | null
  sessionLabel: string
  sampleLabel: string
  updatedAt: string | null
}

function readJobProgress(j: Record<string, unknown>): number | null {
  const keys = ["progress_percent", "progressPercent", "progress"] as const
  for (const k of keys) {
    const v = j[k]
    if (typeof v === "number" && Number.isFinite(v)) {
      let p = v
      if (p > 0 && p <= 1) p = Math.round(p * 100)
      return Math.max(0, Math.min(100, p))
    }
    if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) {
      const n = Number(v)
      let p = n
      if (p > 0 && p <= 1) p = Math.round(p * 100)
      return Math.max(0, Math.min(100, p))
    }
  }
  return null
}

function readJobTime(j: Record<string, unknown>): string | null {
  for (const k of ["updated_at", "modified_at", "created_at", "started_at", "last_updated"]) {
    const t = readRecordString(j, k)
    if (t?.trim()) return t.trim()
  }
  return null
}

export function buildDashboardJobRows(jobs: Record<string, unknown>[], limit = 8): DashboardJobRow[] {
  const sorted = [...jobs].sort((a, b) => {
    const ta = Date.parse(readJobTime(a) ?? "") || 0
    const tb = Date.parse(readJobTime(b) ?? "") || 0
    return tb - ta
  })
  return sorted.slice(0, limit).map((j) => {
    const id =
      readRecordString(j, "job_id") ??
      readRecordString(j, "jobId") ??
      readRecordString(j, "id") ??
      (readRecordNumber(j, "id") != null ? String(readRecordNumber(j, "id")) : "—")
    const jobType =
      readRecordString(j, "job_type") ?? readRecordString(j, "jobType") ?? readRecordString(j, "type") ?? "—"
    const status = parseJobStatusRaw(j) || "—"
    return {
      id,
      jobType,
      status,
      progressPercent: readJobProgress(j),
      sessionLabel:
        readRecordString(j, "session_id") ??
        readRecordString(j, "sessionId") ??
        readRecordString(j, "spectracheck_session_id") ??
        "—",
      sampleLabel: readRecordString(j, "sample_id") ?? readRecordString(j, "sampleId") ?? "—",
      updatedAt: readJobTime(j),
    }
  })
}

export type DashboardMetricsOptions = {
  jobs?: Record<string, unknown>[]
  jobsDataAvailable?: boolean
  sessionsDataAvailable?: boolean
}

export function computeDashboardMetricCounts(
  sessions: Record<string, unknown>[],
  options?: DashboardMetricsOptions,
): DashboardMetricCounts {
  let activeAnalyses = 0
  let reviewRequired = 0
  let reviewRequiredWithContradictions = 0
  let reportsReady = 0
  let evidenceQueue = 0
  let jobsCompleted: number | undefined
  let jobsFailed: number | undefined

  const jobs = options?.jobs ?? []
  const jobsOk = Boolean(options?.jobsDataAvailable)

  if (jobsOk) {
    const jc = countJobsByLifecycle(jobs)
    activeAnalyses = jc.active
    jobsCompleted = jc.completed
    jobsFailed = jc.failed
  }

  for (const s of sessions) {
    const st = normStatus(s)
    if (!jobsOk && ["analyzing", "evidence_ready", "review_required"].includes(st)) {
      activeAnalyses += 1
    }
    if (st === "review_required" || st === "evidence_ready") {
      reviewRequired += 1
      if (st === "review_required" && contraCount(s) > 0) reviewRequiredWithContradictions += 1
    }
    if (sessionReportsReady(s)) {
      reportsReady += 1
    }
    const wc = warnCount(s)
    const cc = contraCount(s)
    if (st === "review_required" || wc > 0 || cc > 0) {
      evidenceQueue += 1
    }
  }

  const out: DashboardMetricCounts = {
    activeAnalyses,
    reviewRequired,
    reviewRequiredWithContradictions,
    reportsReady,
    evidenceQueue,
  }
  if (jobsCompleted !== undefined) out.jobsCompleted = jobsCompleted
  if (jobsFailed !== undefined) out.jobsFailed = jobsFailed
  return out
}

export type DashboardActivityRow = {
  id: string
  sampleId: string
  module: string
  status: "approved" | "review" | "running" | "contradiction"
  confidence: number
  reviewer: string
  reportStatus: "ready" | "pending"
}

function mapSessionToActivityStatus(s: Record<string, unknown>): DashboardActivityRow["status"] {
  const st = normStatus(s)
  if (contraCount(s) > 0 || st.includes("contradiction")) return "contradiction"
  if (["approved_for_release", "approved", "released", "report_ready"].includes(st)) return "approved"
  if (st === "review_required" || readReviewStatus(s) === "needs_changes") return "review"
  if (["analyzing", "processing", "running", "pending"].includes(st)) return "running"
  if (st === "evidence_ready") return "review"
  return "running"
}

function confidenceFromSession(s: Record<string, unknown>): number {
  const n =
    readRecordNumber(s, "confidence_score") ??
    readRecordNumber(s, "confidence") ??
    readRecordNumber(s, "model_confidence")
  if (n != null && Number.isFinite(n)) {
    const v = n <= 1 && n >= 0 ? Math.round(n * 100) : Math.round(n)
    return Math.max(0, Math.min(100, v))
  }
  return 0
}

function reviewerFromSession(s: Record<string, unknown>): string {
  const r = readRecordString(s, "reviewer_name") ?? readRecordString(s, "reviewerName")
  if (r) return r
  const rev = s.review
  if (isRecord(rev)) {
    return readRecordString(rev, "reviewer_name") ?? readRecordString(rev, "reviewerName") ?? "—"
  }
  return "—"
}

export function buildRecentActivityRows(sessions: Record<string, unknown>[], limit = 8): DashboardActivityRow[] {
  const sorted = [...sessions].sort((a, b) => readUpdatedAtMs(b) - readUpdatedAtMs(a))
  const slice = sorted.slice(0, limit)
  return slice.map((s) => ({
    id: sessionIdOf(s),
    sampleId: sampleIdOf(s),
    module: "Spectroscopy",
    status: mapSessionToActivityStatus(s),
    confidence: confidenceFromSession(s),
    reviewer: reviewerFromSession(s),
    reportStatus: sessionReportsReady(s) ? "ready" : "pending",
  }))
}

export type EvidenceQueueCard = {
  id: string
  type: string
  confidence: number
  status: "contradiction" | "high_confidence" | "pending"
  project: string
  timeAgo: string
}

function formatTimeAgo(ms: number): string {
  if (!ms) return "—"
  const diff = Date.now() - ms
  if (diff < 60_000) return "Just now"
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} min ago`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} hr ago`
  return `${Math.floor(diff / 86400_000)} d ago`
}

function projectLabelForSession(
  s: Record<string, unknown>,
  projectById: Map<string, string>,
): string {
  const pid =
    readRecordString(s, "project_id") ?? readRecordString(s, "projectId") ?? readRecordString(s, "project")
  if (pid && projectById.has(pid)) return projectById.get(pid) ?? pid
  if (pid) return pid
  return "—"
}

function mapSessionToQueueStatus(s: Record<string, unknown>): EvidenceQueueCard["status"] {
  const st = normStatus(s)
  if (contraCount(s) > 0 || st.includes("contradiction")) return "contradiction"
  if (st === "review_required" || readReviewStatus(s) === "needs_changes") return "pending"
  if (warnCount(s) > 0) return "pending"
  return "high_confidence"
}

export function buildEvidenceQueueCards(
  sessions: Record<string, unknown>[],
  projectById: Map<string, string>,
  limit = 6,
): EvidenceQueueCard[] {
  const filtered = sessions.filter((s) => {
    const st = normStatus(s)
    return st === "review_required" || warnCount(s) > 0 || contraCount(s) > 0
  })
  const sorted = [...filtered].sort((a, b) => readUpdatedAtMs(b) - readUpdatedAtMs(a))
  return sorted.slice(0, limit).map((s) => ({
    id: sessionIdOf(s),
    type: "SpectraCheck session",
    confidence: confidenceFromSession(s) || 72,
    status: mapSessionToQueueStatus(s),
    project: projectLabelForSession(s, projectById),
    timeAgo: formatTimeAgo(readUpdatedAtMs(s)),
  }))
}

export function buildProjectNameIndex(projects: unknown[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const p of projects) {
    if (!isRecord(p)) continue
    const id =
      readRecordString(p, "id") ?? (readRecordNumber(p, "id") != null ? String(readRecordNumber(p, "id")) : undefined)
    const name = readRecordString(p, "name") ?? readRecordString(p, "project_name") ?? id
    if (id && name) m.set(String(id), name)
  }
  return m
}

/** GET /workflow-runs or session-scoped workflow-runs list shapes. */
export function normalizeWorkflowRunsList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.workflow_runs)) return data.workflow_runs.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.workflowRuns)) return data.workflowRuns.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.runs)) return data.runs.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function parseWorkflowRunStatusRaw(r: Record<string, unknown>): string {
  const raw =
    readRecordString(r, "status") ??
    readRecordString(r, "workflow_status") ??
    readRecordString(r, "workflowStatus") ??
    readRecordString(r, "state") ??
    readRecordString(r, "run_status")
  return (raw ?? "").trim().toLowerCase().replace(/-/g, "_")
}

export type WorkflowRunStatusCounts = {
  active: number
  reviewRequired: number
  failed: number
  completed: number
}

export function countWorkflowRunStatuses(runs: Record<string, unknown>[]): WorkflowRunStatusCounts {
  let active = 0
  let reviewRequired = 0
  let failed = 0
  let completed = 0
  for (const r of runs) {
    const st = parseWorkflowRunStatusRaw(r)
    if (st === "queued" || st === "running" || st === "pending") active += 1
    else if (st === "requires_review" || st === "needs_review" || st === "blocked") reviewRequired += 1
    else if (
      st === "failed" ||
      st === "failure" ||
      st === "error" ||
      st === "canceled" ||
      st === "cancelled"
    )
      failed += 1
    else if (st === "succeeded" || st === "success" || st === "completed" || st === "done") completed += 1
  }
  return { active, reviewRequired, failed, completed }
}

function readWorkflowRunTimeMs(r: Record<string, unknown>): number {
  for (const k of ["updated_at", "modified_at", "created_at", "started_at"]) {
    const t = readRecordString(r, k)
    if (t) {
      const d = Date.parse(t)
      if (!Number.isNaN(d)) return d
    }
  }
  return 0
}

function workflowRunIdOf(r: Record<string, unknown>): string {
  return (
    readRecordString(r, "workflow_run_id") ??
    readRecordString(r, "workflowRunId") ??
    readRecordString(r, "id") ??
    (readRecordNumber(r, "id") != null ? String(readRecordNumber(r, "id")) : "—")
  )
}

function sampleLabelFromWorkflowRun(r: Record<string, unknown>): string {
  return (
    readRecordString(r, "sample_id") ??
    readRecordString(r, "sampleId") ??
    readRecordString(r, "session_id") ??
    readRecordString(r, "sessionId") ??
    "—"
  )
}

function mapWorkflowStatusToActivity(st: string): DashboardActivityRow["status"] {
  if (st === "succeeded" || st === "success" || st === "completed" || st === "done") return "approved"
  if (st === "failed" || st === "failure" || st === "error" || st === "canceled" || st === "cancelled")
    return "contradiction"
  if (st === "requires_review" || st === "needs_review" || st === "blocked") return "review"
  if (st === "queued" || st === "running" || st === "pending") return "running"
  return "review"
}

function confidenceFromWorkflowRun(r: Record<string, unknown>): number {
  const n =
    readRecordNumber(r, "progress_percent") ??
    readRecordNumber(r, "progressPercent") ??
    readRecordNumber(r, "progress")
  if (n != null && Number.isFinite(n)) {
    let p = n
    if (p > 0 && p <= 1) p = Math.round(p * 100)
    return Math.max(0, Math.min(100, Math.round(p)))
  }
  return 0
}

/** Map workflow runs to dashboard activity rows (same table shape as SpectraCheck sessions). */
export function buildWorkflowActivityRowsFromRuns(
  runs: Record<string, unknown>[],
  limit = 8,
): DashboardActivityRow[] {
  const sorted = [...runs].sort((a, b) => readWorkflowRunTimeMs(b) - readWorkflowRunTimeMs(a))
  return sorted.slice(0, limit).map((r) => {
    const st = parseWorkflowRunStatusRaw(r)
    return {
      id: workflowRunIdOf(r),
      sampleId: sampleLabelFromWorkflowRun(r),
      module: "Workflow",
      status: mapWorkflowStatusToActivity(st),
      confidence: confidenceFromWorkflowRun(r),
      reviewer: "—",
      reportStatus: "pending" as const,
    }
  })
}

function readActivityRowTimeMs(row: DashboardActivityRow, sessionsById: Map<string, Record<string, unknown>>): number {
  const s = sessionsById.get(row.id)
  if (s) return readUpdatedAtMs(s)
  return 0
}

/** Merge SpectraCheck session activity with workflow runs by newest timestamp (mixed feed). */
export function mergeDashboardActivityRows(
  sessionRows: DashboardActivityRow[],
  sessions: Record<string, unknown>[],
  workflowRuns: Record<string, unknown>[],
  limit = 8,
): DashboardActivityRow[] {
  const wfRows = buildWorkflowActivityRowsFromRuns(workflowRuns, workflowRuns.length)
  const sessionIndex = new Map<string, Record<string, unknown>>()
  for (const s of sessions) {
    sessionIndex.set(sessionIdOf(s), s)
  }
  const merged: { t: number; row: DashboardActivityRow }[] = []
  for (const row of sessionRows) {
    merged.push({
      t: readActivityRowTimeMs(row, sessionIndex),
      row,
    })
  }
  const runById = new Map<string, Record<string, unknown>>()
  for (const w of workflowRuns) {
    runById.set(workflowRunIdOf(w), w)
  }
  for (const row of wfRows) {
    const w = runById.get(row.id)
    merged.push({
      t: w ? readWorkflowRunTimeMs(w) : 0,
      row,
    })
  }
  merged.sort((a, b) => b.t - a.t)
  const seen = new Set<string>()
  const out: DashboardActivityRow[] = []
  for (const { row } of merged) {
    const key = `${row.module}:${row.id}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(row)
    if (out.length >= limit) break
  }
  return out
}
