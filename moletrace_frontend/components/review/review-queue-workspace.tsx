"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { fetchSpectraCheckSessionsList } from "@/src/lib/spectracheck/spectracheck-backend-session"
import { normalizeSpectraCheckSessionsList } from "@/src/lib/dashboard/overview-metrics"
import { sessionRecordId, sampleIdFromSession } from "@/src/lib/reports/saved-reports"
import {
  fetchSessionReviewTasks,
  linkedRefsFromTaskMetadata,
  normalizeTaskStatus,
  patchSessionReviewTask,
  type TaskStatusGroup,
} from "@/src/lib/spectracheck/review-queue"
import { ExternalLink, Loader2 } from "lucide-react"

type EnrichedTask = {
  task: Record<string, unknown>
  sessionId: string
  sessionSampleLabel: string
}

const COLUMNS: { key: TaskStatusGroup; label: string }[] = [
  { key: "open", label: "Open" },
  { key: "in_progress", label: "In progress" },
  { key: "resolved", label: "Resolved" },
  { key: "dismissed", label: "Dismissed" },
]

function readStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = row[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return "—"
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function priorityVariant(p: string): "default" | "secondary" | "destructive" | "outline" {
  switch (p) {
    case "critical":
      return "destructive"
    case "high":
      return "default"
    case "low":
      return "secondary"
    default:
      return "outline"
  }
}

export default function ReviewQueueWorkspace() {
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")
  const [partialErr, setPartialErr] = useState("")
  const [tasks, setTasks] = useState<EnrichedTask[]>([])
  const [patchBusyKey, setPatchBusyKey] = useState<string | null>(null)
  const [patchErr, setPatchErr] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    setPartialErr("")
    setTasks([])
    let sessionsPayload: unknown
    try {
      sessionsPayload = await fetchSpectraCheckSessionsList()
    } catch (err) {
      setLoadErr(formatApiError(err, "Could not load SpectraCheck sessions."))
      setLoading(false)
      return
    }

    const sessions = normalizeSpectraCheckSessionsList(sessionsPayload)
    const collected: EnrichedTask[] = []
    let sessionErrors = 0
    const batchSize = 6

    for (let i = 0; i < sessions.length; i += batchSize) {
      const chunk = sessions.slice(i, i + batchSize)
      const chunkResults = await Promise.all(
        chunk.map(async (session) => {
          const sid = sessionRecordId(session)
          if (!sid) return { sid: null as string | null, rows: [] as Record<string, unknown>[], ok: true }
          try {
            const rows = await fetchSessionReviewTasks(sid)
            return { sid, rows, ok: true }
          } catch {
            return { sid, rows: [] as Record<string, unknown>[], ok: false }
          }
        }),
      )
      for (const part of chunkResults) {
        if (!part.sid) continue
        if (!part.ok) {
          sessionErrors += 1
          continue
        }
        const sessionRow = sessions.find((s) => sessionRecordId(s) === part.sid)
        const sample = sampleIdFromSession(sessionRow ?? {})
        const sessionSampleLabel = sample && sample !== "—" ? sample : part.sid
        for (const row of part.rows) {
          collected.push({
            task: row,
            sessionId: part.sid,
            sessionSampleLabel,
          })
        }
      }
    }

    if (sessionErrors > 0) {
      setPartialErr(
        `${sessionErrors} session(s) had tasks that could not be loaded (permissions or connectivity).`,
      )
    }
    setTasks(collected)
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const grouped = useMemo(() => {
    const buckets: Record<TaskStatusGroup, EnrichedTask[]> = {
      open: [],
      in_progress: [],
      resolved: [],
      dismissed: [],
    }
    for (const et of tasks) {
      const k = normalizeTaskStatus(et.task)
      buckets[k].push(et)
    }
    return buckets
  }, [tasks])

  async function patchStatus(et: EnrichedTask, status: TaskStatusGroup) {
    const tid = readStr(et.task, ["id", "task_id"])
    if (tid === "—") return
    const key = `${et.sessionId}:${tid}:${status}`
    setPatchBusyKey(key)
    setPatchErr("")
    try {
      await patchSessionReviewTask(et.sessionId, tid, { status })
      await load()
    } catch (err) {
      setPatchErr(formatApiError(err, "Update failed."))
    } finally {
      setPatchBusyKey(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Review Queue</h1>
          <p className="text-muted-foreground">
            Review tasks collected per SpectraCheck session. There is no global review-task index in this API — tasks are
            merged from{" "}
            <code className="text-xs">GET /spectracheck/sessions/{'{session_id}'}/review-tasks</code> for each session
            returned by <code className="text-xs">GET /spectracheck/sessions</code>.
          </p>
          {loadErr ? <p className="mt-1 text-xs text-destructive">{loadErr}</p> : null}
          {partialErr ? <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">{partialErr}</p> : null}
          {patchErr ? <p className="mt-1 text-xs text-destructive">{patchErr}</p> : null}
        </div>
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading sessions and tasks…
        </div>
      ) : null}

      {!loading && tasks.length === 0 && !loadErr ? (
        <Card className="border-muted">
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No review tasks returned for your sessions yet.
          </CardContent>
        </Card>
      ) : null}

      {!loading && tasks.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-4">
          {COLUMNS.map((col) => (
            <div key={col.key} className="min-w-0 space-y-3">
              <div className="flex items-center justify-between gap-2 border-b pb-2">
                <h2 className="text-sm font-semibold">{col.label}</h2>
                <Badge variant="secondary" className="tabular-nums">
                  {grouped[col.key].length}
                </Badge>
              </div>
              <div className="space-y-3">
                {grouped[col.key].length === 0 ? (
                  <p className="text-xs text-muted-foreground">None</p>
                ) : (
                  grouped[col.key].map((et) => {
                    const row = et.task
                    const title = readStr(row, ["title", "summary"])
                    const priority = String(row.priority ?? "—").toLowerCase()
                    const assigned = readStr(row, ["assigned_to", "assignedTo", "assignee"])
                    const status = String(row.status ?? "—")
                    const created = formatWhen(
                      typeof row.created_at === "string"
                        ? row.created_at
                        : typeof row.createdAt === "string"
                          ? row.createdAt
                          : undefined,
                    )
                    const { evidenceId, reportId } = linkedRefsFromTaskMetadata(row)
                    const taskId = readStr(row, ["id", "task_id"])
                    const busyBase = `${et.sessionId}:${taskId}`
                    return (
                      <Card key={`${et.sessionId}-${taskId}`} className="border-muted shadow-sm">
                        <CardHeader className="space-y-1 pb-2">
                          <CardTitle className="text-base leading-snug">{title}</CardTitle>
                          <CardDescription className="text-xs">
                            Session / sample:{" "}
                            <span className="font-mono text-[11px]">{et.sessionSampleLabel}</span>
                            <span className="text-muted-foreground"> · session_id </span>
                            <span className="font-mono text-[11px]">{et.sessionId}</span>
                          </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge variant={priorityVariant(priority)} className="font-normal capitalize">
                              {priority}
                            </Badge>
                            <Badge variant="outline" className="font-normal">
                              {status}
                            </Badge>
                          </div>
                          <div className="space-y-0.5 text-xs text-muted-foreground">
                            <p>
                              <span className="font-medium text-foreground">Assigned:</span> {assigned}
                            </p>
                            <p>
                              <span className="font-medium text-foreground">Created:</span> {created}
                            </p>
                          </div>
                          {evidenceId || reportId ? (
                            <div className="rounded-md border bg-muted/30 px-2 py-1.5 text-[11px] text-muted-foreground">
                              {evidenceId ? (
                                <span>
                                  evidence_id: <span className="font-mono text-foreground">{evidenceId}</span>
                                </span>
                              ) : null}
                              {evidenceId && reportId ? <span className="mx-1">·</span> : null}
                              {reportId ? (
                                <span>
                                  report_id: <span className="font-mono text-foreground">{reportId}</span>
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              className="h-8 text-xs"
                              disabled={
                                normalizeTaskStatus(row) === "in_progress" ||
                                normalizeTaskStatus(row) === "resolved" ||
                                normalizeTaskStatus(row) === "dismissed" ||
                                patchBusyKey?.startsWith(busyBase)
                              }
                              onClick={() => void patchStatus(et, "in_progress")}
                            >
                              {patchBusyKey === `${busyBase}:in_progress` ? "…" : "Mark in progress"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 text-xs"
                              disabled={
                                normalizeTaskStatus(row) === "resolved" ||
                                normalizeTaskStatus(row) === "dismissed" ||
                                patchBusyKey?.startsWith(busyBase)
                              }
                              onClick={() => void patchStatus(et, "resolved")}
                            >
                              {patchBusyKey === `${busyBase}:resolved` ? "…" : "Resolve"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 text-xs"
                              disabled={
                                normalizeTaskStatus(row) === "dismissed" ||
                                normalizeTaskStatus(row) === "resolved" ||
                                patchBusyKey?.startsWith(busyBase)
                              }
                              onClick={() => void patchStatus(et, "dismissed")}
                            >
                              {patchBusyKey === `${busyBase}:dismissed` ? "…" : "Dismiss"}
                            </Button>
                            <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2 text-xs" asChild>
                              <Link
                                href={`/spectracheck?sessionId=${encodeURIComponent(et.sessionId)}`}
                                className="inline-flex items-center"
                              >
                                Open session
                                <ExternalLink className="h-3 w-3 opacity-70" />
                              </Link>
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    )
                  })
                )}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
