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
import { AlertCircle, CheckCircle2, ClipboardCheck, Clock, ExternalLink, Loader2, PlayCircle, X } from "lucide-react"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { StatusFilterPills } from "@/components/dashboard/status-filter-pills"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"

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

type PriorityBucket = "critical" | "high" | "normal" | "low"
type PriorityFilter = "all" | PriorityBucket

function priorityBucketOf(row: Record<string, unknown>): PriorityBucket {
  const raw = String(row.priority ?? "").toLowerCase()
  if (raw === "critical") return "critical"
  if (raw === "high") return "high"
  if (raw === "low") return "low"
  return "normal"
}

function humanizeStatus(status: string): string {
  const trimmed = status.trim()
  if (!trimmed || trimmed === "—") return "—"
  const spaced = trimmed.replace(/[_-]+/g, " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase()
}

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
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all")

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
        `Couldn't load tasks for ${sessionErrors} session${sessionErrors === 1 ? "" : "s"} — check permissions or connection.`,
      )
    }
    setTasks(collected)
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const priorityCounts = useMemo(() => {
    const counts: Record<PriorityBucket, number> = { critical: 0, high: 0, normal: 0, low: 0 }
    for (const et of tasks) counts[priorityBucketOf(et.task)]++
    return counts
  }, [tasks])

  const filteredTasks = useMemo(() => {
    if (priorityFilter === "all") return tasks
    return tasks.filter((et) => priorityBucketOf(et.task) === priorityFilter)
  }, [tasks, priorityFilter])

  const grouped = useMemo(() => {
    const buckets: Record<TaskStatusGroup, EnrichedTask[]> = {
      open: [],
      in_progress: [],
      resolved: [],
      dismissed: [],
    }
    for (const et of filteredTasks) {
      const k = normalizeTaskStatus(et.task)
      buckets[k].push(et)
    }
    return buckets
  }, [filteredTasks])

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
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-cyan)" }}
          >
            MolTrace · Review
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Review Queue</h1>
          <p className="text-sm text-muted-foreground">
            Tasks awaiting review across your SpectraCheck sessions.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
          Refresh
        </Button>
      </div>

      {loadErr ? (
        <AlertCard variant="error" title="Failed to load review queue" description={loadErr} />
      ) : null}
      {partialErr ? (
        <AlertCard variant="warning" title="Partial data loaded" description={partialErr} />
      ) : null}
      {patchErr ? (
        <AlertCard variant="error" title="Action failed" description={patchErr} />
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading sessions and tasks…
        </div>
      ) : null}

      {!loading && tasks.length === 0 && !loadErr ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ClipboardCheck />
            </EmptyMedia>
            <EmptyTitle>No review tasks yet</EmptyTitle>
            <EmptyDescription>
              Tasks appear here when SpectraCheck flags an analysis for human review. When your sessions
              produce findings, they&apos;ll show up in this queue.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild>
              <Link href="/spectracheck">Open SpectraCheck</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}

      {!loading && tasks.length > 0 ? (
        <>
          <StatusFilterPills
            label="Filter by priority"
            value={priorityFilter}
            onChange={setPriorityFilter}
            options={[
              { value: "all", label: "All", count: tasks.length },
              { value: "critical", label: "Critical", count: priorityCounts.critical },
              { value: "high", label: "High", count: priorityCounts.high },
              { value: "normal", label: "Normal", count: priorityCounts.normal },
              { value: "low", label: "Low", count: priorityCounts.low },
            ]}
          />
          <div className="grid gap-4 sm:grid-cols-3">
            <KpiCard
              title="Open"
              icon={AlertCircle}
              accent="cyan"
              severity={grouped.open.length > 0 ? "warning" : "neutral"}
              value={grouped.open.length}
              sub={
                <p className="text-xs text-muted-foreground">
                  {grouped.open.length === 0 ? "Nothing waiting" : "Tasks waiting to be picked up"}
                </p>
              }
            />
            <KpiCard
              title="In progress"
              icon={Clock}
              accent="cyan"
              value={grouped.in_progress.length}
              sub={
                <p className="text-xs text-muted-foreground">
                  {grouped.in_progress.length === 0 ? "Nothing in progress" : "Tasks currently being worked"}
                </p>
              }
            />
            <KpiCard
              title="Resolved"
              icon={CheckCircle2}
              accent="cyan"
              severity={grouped.resolved.length > 0 ? "success" : "neutral"}
              value={grouped.resolved.length}
              sub={
                <p className="text-xs text-muted-foreground">
                  {grouped.resolved.length === 0 ? "Nothing resolved yet" : "Completed reviews"}
                </p>
              }
            />
          </div>
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
                            Sample <span className="font-mono text-[11px]">{et.sessionSampleLabel}</span>
                          </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge variant={priorityVariant(priority)} className="font-normal capitalize">
                              {priority}
                            </Badge>
                            <Badge variant="outline" className="font-normal">
                              {humanizeStatus(status)}
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
                                  Linked evidence{" "}
                                  <span className="font-mono text-foreground">#{evidenceId}</span>
                                </span>
                              ) : null}
                              {evidenceId && reportId ? <span className="mx-1">·</span> : null}
                              {reportId ? (
                                <span>
                                  Linked report{" "}
                                  <span className="font-mono text-foreground">#{reportId}</span>
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              className="h-8 gap-1.5 text-xs"
                              disabled={
                                normalizeTaskStatus(row) === "in_progress" ||
                                normalizeTaskStatus(row) === "resolved" ||
                                normalizeTaskStatus(row) === "dismissed" ||
                                patchBusyKey?.startsWith(busyBase)
                              }
                              onClick={() => void patchStatus(et, "in_progress")}
                            >
                              {patchBusyKey === `${busyBase}:in_progress` ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <PlayCircle className="h-3 w-3" />
                              )}
                              Start review
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 gap-1.5 text-xs"
                              disabled={
                                normalizeTaskStatus(row) === "resolved" ||
                                normalizeTaskStatus(row) === "dismissed" ||
                                patchBusyKey?.startsWith(busyBase)
                              }
                              onClick={() => void patchStatus(et, "resolved")}
                            >
                              {patchBusyKey === `${busyBase}:resolved` ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <CheckCircle2 className="h-3 w-3" />
                              )}
                              Resolve
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 gap-1.5 text-xs"
                              disabled={
                                normalizeTaskStatus(row) === "dismissed" ||
                                normalizeTaskStatus(row) === "resolved" ||
                                patchBusyKey?.startsWith(busyBase)
                              }
                              onClick={() => void patchStatus(et, "dismissed")}
                            >
                              {patchBusyKey === `${busyBase}:dismissed` ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <X className="h-3 w-3" />
                              )}
                              Dismiss
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
        </>
      ) : null}
    </div>
  )
}
