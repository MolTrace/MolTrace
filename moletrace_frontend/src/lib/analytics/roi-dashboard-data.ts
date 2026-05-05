import { apiFetch, ApiError } from "@/lib/api/client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  return null
}

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  return null
}

/** GET /analytics/roi — RoiSnapshot (admin). */
export type RoiSnapshotData = {
  total_minutes_saved: number
  total_hours_saved: number
  tasks_automated: number
  reports_generated: number
  workflows_completed: number
  analyses_completed: number
  review_tasks_completed: number
  failed_jobs: number
  qc_warnings: number
  /** Optional — filled from metadata_json when backend supplies counts. */
  evidence_items_generated: number | null
  period_start?: string
  period_end?: string
  metadata_json: Record<string, unknown>
}

function readEvidenceItemsFromMetadata(meta: Record<string, unknown>): number | null {
  const n =
    readNum(meta.evidence_items_generated) ??
    readNum(meta.evidence_items_count) ??
    readNum(meta.evidence_event_count)
  return n != null ? Math.round(n) : null
}

export function parseRoiSnapshot(raw: unknown): RoiSnapshotData | null {
  if (!isRecord(raw)) return null
  const th = readNum(raw.total_hours_saved)
  if (th == null) return null
  const ta = readNum(raw.tasks_automated) ?? 0
  const meta = raw.metadata_json
  const metaObj = isRecord(meta) ? meta : {}
  return {
    total_minutes_saved: readNum(raw.total_minutes_saved) ?? 0,
    total_hours_saved: th,
    tasks_automated: ta,
    reports_generated: readNum(raw.reports_generated) ?? 0,
    workflows_completed: readNum(raw.workflows_completed) ?? 0,
    analyses_completed: readNum(raw.analyses_completed) ?? 0,
    review_tasks_completed: readNum(raw.review_tasks_completed) ?? 0,
    failed_jobs: readNum(raw.failed_jobs) ?? 0,
    qc_warnings: readNum(raw.qc_warnings) ?? 0,
    evidence_items_generated: readEvidenceItemsFromMetadata(metaObj),
    period_start: readStr(raw.period_start) ?? undefined,
    period_end: readStr(raw.period_end) ?? undefined,
    metadata_json: metaObj,
  }
}

/** GET /analytics/automation-tasks — list[AutomationTaskDefinition]. */
export type AutomationTaskRow = {
  id: number
  task_key: string
  name: string
  category: string
  default_minutes_saved: number
  enabled: boolean
}

export function parseAutomationTasksList(raw: unknown): AutomationTaskRow[] {
  if (!Array.isArray(raw)) return []
  const out: AutomationTaskRow[] = []
  for (const item of raw) {
    if (!isRecord(item)) continue
    const id = readNum(item.id)
    const name = readStr(item.name)
    const taskKey = readStr(item.task_key)
    const category = readStr(item.category) ?? "—"
    const dms = readNum(item.default_minutes_saved)
    if (id == null || !name || !taskKey || dms == null) continue
    out.push({
      id,
      task_key: taskKey,
      name,
      category,
      default_minutes_saved: dms,
      enabled: Boolean(item.enabled),
    })
  }
  return out
}

/** GET /analytics/workflows/summary — WorkflowAnalyticsSummary (admin). */
export type WorkflowSummaryData = {
  workflows_started: number
  workflows_completed: number
  workflows_failed: number
  total_minutes_saved: number
  metadata: Record<string, unknown>
}

export function parseWorkflowSummary(raw: unknown): WorkflowSummaryData | null {
  if (!isRecord(raw)) return null
  const ws = readNum(raw.workflows_started)
  const wc = readNum(raw.workflows_completed)
  const wf = readNum(raw.workflows_failed)
  const tm = readNum(raw.total_minutes_saved)
  if (ws == null || wc == null || wf == null || tm == null) return null
  const meta = raw.metadata
  return {
    workflows_started: ws,
    workflows_completed: wc,
    workflows_failed: wf,
    total_minutes_saved: tm,
    metadata: isRecord(meta) ? meta : {},
  }
}

/** GET /analytics/feedback — list[UserFeedbackEvent] (admin). */
export type FeedbackRow = {
  id: number
  feedback_type: string
  rating: number | null
  comment: string | null
  created_at: string
}

export function parseFeedbackList(raw: unknown): FeedbackRow[] {
  if (!Array.isArray(raw)) return []
  const out: FeedbackRow[] = []
  for (const item of raw) {
    if (!isRecord(item)) continue
    const id = readNum(item.id)
    const ft = readStr(item.feedback_type)
    const created = readStr(item.created_at)
    if (id == null || !ft || !created) continue
    const rating = readNum(item.rating)
    const commentRaw = item.comment
    const comment =
      commentRaw === null || commentRaw === undefined
        ? null
        : typeof commentRaw === "string"
          ? commentRaw
          : null
    out.push({
      id,
      feedback_type: ft,
      rating: rating != null ? Math.round(rating) : null,
      comment,
      created_at: created,
    })
  }
  return out
}

export type TrendPoint = { label: string; hours_saved: number; tasks_automated: number }

/** Optional future shape: metadata_json.trends_weekly as array of points. */
export function parseTrendSeriesFromRoiMetadata(meta: Record<string, unknown>): TrendPoint[] | null {
  const raw = meta.trends_weekly ?? meta.hours_tasks_trend
  if (!Array.isArray(raw) || raw.length === 0) return null
  const points: TrendPoint[] = []
  for (const row of raw) {
    if (!isRecord(row)) continue
    const label = readStr(row.week ?? row.label ?? row.period) ?? ""
    const hs = readNum(row.hours_saved ?? row.total_hours_saved)
    const ta = readNum(row.tasks_automated ?? row.tasks)
    if (!label || hs == null || ta == null) continue
    points.push({ label, hours_saved: hs, tasks_automated: ta })
  }
  return points.length > 0 ? points : null
}

export type RoiDashboardLoadResult = {
  roi: RoiSnapshotData | null
  tasks: AutomationTaskRow[]
  workflow: WorkflowSummaryData | null
  feedback: FeedbackRow[]
  ok: {
    roi: boolean
    tasks: boolean
    workflow: boolean
    feedback: boolean
  }
  /** Human-readable error hints (no secrets). */
  errors: Partial<Record<"roi" | "tasks" | "workflow" | "feedback", string>>
}

function errLabel(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Administrator access required."
    if (err.status === 401) return "Sign in required."
    return `Request failed (${err.status}).`
  }
  return "Request failed."
}

export async function loadRoiDashboardData(): Promise<RoiDashboardLoadResult> {
  const errors: RoiDashboardLoadResult["errors"] = {}
  let roi: RoiSnapshotData | null = null
  let tasks: AutomationTaskRow[] = []
  let workflow: WorkflowSummaryData | null = null
  let feedback: FeedbackRow[] = []
  const ok = { roi: false, tasks: false, workflow: false, feedback: false }

  const [rT, tT, wT, fT] = await Promise.allSettled([
    apiFetch<unknown>("/analytics/roi", { method: "GET" }),
    apiFetch<unknown>("/analytics/automation-tasks", { method: "GET" }),
    apiFetch<unknown>("/analytics/workflows/summary", { method: "GET" }),
    apiFetch<unknown>("/analytics/feedback", { method: "GET" }),
  ])

  if (rT.status === "fulfilled") {
    roi = parseRoiSnapshot(rT.value)
    ok.roi = roi != null
    if (!roi) errors.roi = "Unexpected ROI payload."
  } else {
    errors.roi = errLabel(rT.reason)
  }

  if (tT.status === "fulfilled") {
    tasks = parseAutomationTasksList(tT.value)
    ok.tasks = true
  } else {
    errors.tasks = errLabel(tT.reason)
  }

  if (wT.status === "fulfilled") {
    workflow = parseWorkflowSummary(wT.value)
    ok.workflow = workflow != null
    if (!workflow) errors.workflow = "Unexpected workflow summary payload."
  } else {
    errors.workflow = errLabel(wT.reason)
  }

  if (fT.status === "fulfilled") {
    feedback = parseFeedbackList(fT.value)
    ok.feedback = true
  } else {
    errors.feedback = errLabel(fT.reason)
  }

  return { roi, tasks, workflow, feedback, ok, errors }
}
