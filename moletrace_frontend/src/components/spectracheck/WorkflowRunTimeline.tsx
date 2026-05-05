"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { trackWorkflowCompleted } from "@/src/lib/analytics/analytics-client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

const TIMELINE_TOOLTIP =
  "Workflow runs coordinate multiple analysis jobs, QC checks, evidence selection, unified confidence, and report draft generation."

/** Polling stops after this many ticks (2s each) even if status stays ambiguous — avoids polling forever. */
const MAX_POLL_TICKS = 900

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

function readNum(o: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string" && v.trim()) {
      const n = Number(v)
      if (Number.isFinite(n)) return n
    }
  }
  return null
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

function normalizeStatus(raw: unknown): string {
  if (typeof raw !== "string") return ""
  return raw.trim().toLowerCase().replace(/-/g, "_")
}

/** Continue polling while status is unknown (empty) or actively progressing. */
function statusShouldPoll(norm: string): boolean {
  if (!norm) return true
  return norm === "queued" || norm === "running" || norm === "pending"
}

/** Stop polling when run reached a settled outcome (backend shapes may vary — normalize common aliases). */
function statusIsTerminal(norm: string): boolean {
  if (!norm) return false
  if (norm === "succeeded" || norm === "success" || norm === "completed" || norm === "done") return true
  if (norm === "failed" || norm === "failure" || norm === "error") return true
  if (norm === "canceled" || norm === "cancelled") return true
  if (norm === "requires_review" || norm === "needs_review" || norm === "blocked") return true
  return false
}

/** Successful completion — fetch workflow artifacts for Evidence Queue / Unified / Report handoff. */
function statusIsSuccessful(norm: string): boolean {
  if (!norm) return false
  return norm === "succeeded" || norm === "success" || norm === "completed" || norm === "done"
}

function parseRunStatus(raw: unknown): string {
  if (!isRecord(raw)) return ""
  const s =
    readStr(raw, ["status", "workflow_status", "workflowStatus", "state", "run_status", "runStatus"]) ||
    (isRecord(raw.workflow_run) ? readStr(raw.workflow_run, ["status", "state"]) : "") ||
    (isRecord(raw.run) ? readStr(raw.run, ["status", "state"]) : "")
  return normalizeStatus(s)
}

function parseProgressPercent(raw: unknown): number | null {
  if (!isRecord(raw)) return null
  const n =
    readNum(raw, ["progress_percent", "progressPercent", "percent_complete", "percentComplete"]) ??
    readNum(raw, ["progress"]) ??
    (isRecord(raw.workflow_run) ? readNum(raw.workflow_run, ["progress_percent", "progress"]) : null)
  if (n == null || !Number.isFinite(n)) return null
  return Math.max(0, Math.min(100, n))
}

function parseCurrentStep(raw: unknown): string {
  if (!isRecord(raw)) return ""
  return (
    readStr(raw, [
      "current_step",
      "currentStep",
      "current_step_name",
      "currentStepName",
      "active_step",
      "activeStep",
    ]) ?? ""
  )
}

function parseWarnings(raw: unknown): string[] {
  const root = isRecord(raw) ? raw : {}
  const w = Array.isArray(root.warnings)
    ? root.warnings
    : extractArray(root, ["warnings"]) ||
      (Array.isArray(root.warning_messages) ? root.warning_messages : [])
  const out: string[] = []
  for (const item of w) {
    if (typeof item === "string" && item.trim()) out.push(item.trim())
    else if (isRecord(item)) {
      const m = readStr(item, ["message", "text", "detail", "description"])
      if (m) out.push(m)
    }
  }
  return out
}

function parseNotes(raw: unknown): string | null {
  if (!isRecord(raw)) return null
  const n =
    readStr(raw, ["notes", "note", "workflow_notes", "workflowNotes"]) ||
    (typeof raw.notes === "string" ? raw.notes : "")
  return n.trim() ? n.trim() : null
}

type ArtifactRow = { id: string; label: string }

function parseArtifacts(raw: unknown): ArtifactRow[] {
  const arr = extractArray(raw, ["artifacts", "artifact_refs", "produced_artifacts", "outputs"])
  const out: ArtifactRow[] = []
  for (const item of arr) {
    if (typeof item === "string" && item.trim()) {
      out.push({ id: item.trim(), label: item.trim() })
      continue
    }
    if (!isRecord(item)) continue
    const id =
      readStr(item, ["artifact_id", "artifactId", "id", "file_id", "fileId"]) ||
      readStr(item, ["sha256"]) ||
      ""
    const label = readStr(item, ["title", "name", "label", "filename"]) || id
    if (id) out.push({ id, label })
  }
  return out
}

export type WorkflowStepRow = {
  id: string
  name: string
  statusNorm: string
  blockingReason: string | null
  requiredMissingInput: string | null
}

function normalizeStepStatus(raw: unknown): string {
  const s = typeof raw === "string" ? raw : ""
  return normalizeStatus(s || "pending")
}

function parseStepsPayload(data: unknown): WorkflowStepRow[] {
  const rows = extractArray(data, ["steps", "workflow_steps", "items", "results"])
  const out: WorkflowStepRow[] = []
  for (const r of rows) {
    if (!isRecord(r)) continue
    const id = readStr(r, ["id", "step_id", "stepId", "key", "slug"]) || `step-${out.length}`
    const name =
      readStr(r, ["name", "title", "label", "step_name", "stepName", "description"]) || id
    const statusNorm = normalizeStepStatus(
      readStr(r, ["status", "step_status", "stepStatus", "state"]) || "pending",
    )
    const blockingReason =
      readStr(r, ["blocking_reason", "blockingReason", "block_reason", "blocked_reason"]) || null
    const requiredMissingInput =
      readStr(r, [
        "required_missing_input",
        "requiredMissingInput",
        "missing_input",
        "missingInput",
        "missing_inputs",
      ]) || null
    out.push({
      id,
      name,
      statusNorm,
      blockingReason: blockingReason?.trim() ? blockingReason.trim() : null,
      requiredMissingInput: requiredMissingInput?.trim() ? requiredMissingInput.trim() : null,
    })
  }
  return out
}

export type WorkflowEventRow = {
  ts: string | null
  type: string | null
  message: string | null
}

function parseEventsPayload(data: unknown): WorkflowEventRow[] {
  const rows = extractArray(data, ["events", "items", "results", "log"])
  const out: WorkflowEventRow[] = []
  for (const r of rows) {
    if (!isRecord(r)) continue
    out.push({
      ts: readStr(r, ["timestamp", "created_at", "createdAt", "time", "ts"]) || null,
      type: readStr(r, ["type", "event_type", "eventType", "kind", "level"]) || null,
      message:
        readStr(r, ["message", "msg", "detail", "description", "text"]) ||
        (typeof r.message === "string" ? r.message : null),
    })
  }
  return out
}

function stepBadgeClass(statusNorm: string): string {
  switch (statusNorm) {
    case "pending":
      return "border-muted-foreground/40 text-muted-foreground"
    case "queued":
      return "border-muted-foreground/40 text-muted-foreground"
    case "running":
      return "border-accent/50 text-accent"
    case "succeeded":
    case "success":
    case "completed":
      return "border-success/50 text-success"
    case "failed":
    case "failure":
    case "error":
      return "border-destructive/60 text-destructive"
    case "skipped":
      return "border-warning/50 text-warning"
    case "blocked":
      return "border-orange-500/50 text-orange-900 dark:text-orange-200"
    default:
      return "border-muted-foreground/40 text-muted-foreground"
  }
}

function statusBadgeClass(norm: string): string {
  switch (norm) {
    case "queued":
    case "pending":
      return "border-muted-foreground/40 text-muted-foreground"
    case "running":
      return "border-accent/50 text-accent"
    case "succeeded":
    case "success":
    case "completed":
      return "border-success/50 text-success"
    case "failed":
    case "failure":
    case "error":
      return "border-destructive/60 text-destructive"
    case "canceled":
    case "cancelled":
      return "border-warning/50 text-warning"
    case "requires_review":
    case "needs_review":
      return "border-amber-600/50 text-amber-950 dark:text-amber-100"
    default:
      return "border-muted-foreground/40 text-muted-foreground"
  }
}

export type WorkflowRunTimelineProps = {
  workflowRunId: string | null
  onNavigateToTab?: (tab: string) => void
  sampleId?: string
  workflowTemplateSlug?: string | null
}

function estimateDurationSecondsFromWorkflowEvents(events: WorkflowEventRow[]): number | undefined {
  const ms = events
    .map((e) => (e.ts ? Date.parse(e.ts) : NaN))
    .filter((n) => Number.isFinite(n))
  if (ms.length < 2) return undefined
  const delta = (Math.max(...ms) - Math.min(...ms)) / 1000
  return delta > 0 ? Math.round(delta) : undefined
}

export function WorkflowRunTimeline({
  workflowRunId,
  workflowTemplateSlug = null,
}: WorkflowRunTimelineProps) {
  const rid = workflowRunId?.trim() ?? ""
  const [runPayload, setRunPayload] = useState<unknown>(null)
  const [eventsPayload, setEventsPayload] = useState<unknown>(null)
  const [stepsPayload, setStepsPayload] = useState<unknown>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [cancelBusy, setCancelBusy] = useState(false)
  const [polling, setPolling] = useState(false)
  const pollTicksRef = useRef(0)
  const artifactsFetchedForRunRef = useRef<string | null>(null)
  const workflowTerminalTrackedRef = useRef<Set<string>>(new Set())
  const [artifactsPayload, setArtifactsPayload] = useState<unknown>(null)
  const [artifactsError, setArtifactsError] = useState<string | null>(null)
  const [artifactsLoading, setArtifactsLoading] = useState(false)

  const derived = useMemo(
    () => ({
      runStatus: parseRunStatus(runPayload),
      progressPercent: parseProgressPercent(runPayload),
      currentStep: parseCurrentStep(runPayload),
      warnings: parseWarnings(runPayload),
      notes: parseNotes(runPayload),
      artifacts: parseArtifacts(runPayload),
      steps: parseStepsPayload(stepsPayload),
      events: parseEventsPayload(eventsPayload),
    }),
    [runPayload, eventsPayload, stepsPayload],
  )

  const pollOnce = useCallback(async (): Promise<boolean> => {
    if (!rid) return false
    pollTicksRef.current += 1
    if (pollTicksRef.current > MAX_POLL_TICKS) {
      setFetchError("Stopped polling after maximum duration.")
      return false
    }
    try {
      const [runData, evData, stData] = await Promise.all([
        apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}`, { method: "GET" }),
        apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}/events`, { method: "GET" }),
        apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}/steps`, { method: "GET" }),
      ])
      setRunPayload(runData)
      setEventsPayload(evData)
      setStepsPayload(stData)
      setFetchError(null)
      const st = parseRunStatus(runData)
      return statusShouldPoll(st) && !statusIsTerminal(st)
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message || `Failed (${err.status})`
          : err instanceof Error
            ? err.message
            : "Failed to load workflow run."
      setFetchError(msg)
      return false
    }
  }, [rid])

  useEffect(() => {
    if (!rid) {
      setRunPayload(null)
      setEventsPayload(null)
      setStepsPayload(null)
      setFetchError(null)
      setPolling(false)
      pollTicksRef.current = 0
      return
    }
    pollTicksRef.current = 0
    let intervalId: ReturnType<typeof setInterval> | undefined
    let busy = false

    async function tick() {
      if (busy) return
      busy = true
      setPolling(true)
      try {
        const continuePolling = await pollOnce()
        if (!continuePolling) {
          if (intervalId != null) {
            clearInterval(intervalId)
            intervalId = undefined
          }
        }
      } finally {
        busy = false
        setPolling(false)
      }
    }

    void tick()
    intervalId = setInterval(() => void tick(), 2000)

    return () => {
      if (intervalId != null) clearInterval(intervalId)
    }
  }, [rid, pollOnce])

  useEffect(() => {
    artifactsFetchedForRunRef.current = null
    setArtifactsPayload(null)
    setArtifactsError(null)
    setArtifactsLoading(false)
  }, [rid])

  useEffect(() => {
    if (!rid) return
    const st = derived.runStatus
    if (!statusIsTerminal(st)) return
    if (workflowTerminalTrackedRef.current.has(rid)) return
    workflowTerminalTrackedRef.current.add(rid)
    trackWorkflowCompleted({
      workflow_run_id: rid,
      status: st,
      duration_seconds: estimateDurationSecondsFromWorkflowEvents(derived.events),
      metadata: {
        workflow_template_slug: workflowTemplateSlug ?? "unknown",
      },
    })
  }, [rid, derived.runStatus, derived.events, workflowTemplateSlug])

  useEffect(() => {
    if (!rid) return
    if (!statusIsSuccessful(derived.runStatus)) return
    if (artifactsFetchedForRunRef.current === rid) return
    artifactsFetchedForRunRef.current = rid
    let cancelled = false
    setArtifactsLoading(true)
    setArtifactsError(null)
    void (async () => {
      try {
        const data = await apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}/artifacts`, { method: "GET" })
        if (!cancelled) setArtifactsPayload(data)
      } catch (err) {
        if (!cancelled) {
          const msg =
            err instanceof ApiError
              ? err.message || `Artifacts failed (${err.status})`
              : err instanceof Error
                ? err.message
                : "Failed to load workflow artifacts."
          setArtifactsError(msg)
        }
      } finally {
        if (!cancelled) setArtifactsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [rid, derived.runStatus])

  async function handleCancel() {
    if (!rid) return
    setCancelBusy(true)
    setFetchError(null)
    try {
      await apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(rid)}/cancel`, { method: "POST", body: {} })
      await pollOnce()
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message || `Cancel failed (${err.status})`
          : err instanceof Error
            ? err.message
            : "Cancel request failed."
      setFetchError(msg)
    } finally {
      setCancelBusy(false)
    }
  }

  if (!rid) return null

  const runStatus = derived.runStatus
  const canCancel = runStatus === "queued" || runStatus === "running" || runStatus === "pending"

  const progressValue =
    derived.progressPercent != null && Number.isFinite(derived.progressPercent)
      ? Math.max(0, Math.min(100, derived.progressPercent))
      : runStatus === "succeeded" || runStatus === "success" || runStatus === "completed"
        ? 100
        : 0

  return (
    <Card className="min-w-0 border-muted">
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Workflow run timeline
          <InfoTooltip content={TIMELINE_TOOLTIP} label="Workflow run timeline information" />
        </CardTitle>
        <CardDescription>
          Live status from <code className="text-xs">GET /workflow-runs/{"{id}"}</code>,{" "}
          <code className="text-xs">/events</code>, and <code className="text-xs">/steps</code>. Polling pauses when the run
          settles.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="font-mono text-[10px] text-muted-foreground break-all">workflow_run_id: {rid}</p>

        {fetchError ? <p className="text-sm text-destructive">{fetchError}</p> : null}

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Status</span>
          <Badge variant="outline" className={cn("gap-1", statusBadgeClass(runStatus))}>
            {runStatus || "—"}
          </Badge>
          {polling ? (
            <Badge variant="secondary" className="text-[10px]">
              polling
            </Badge>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground">Progress</span>
            <span className="font-mono text-muted-foreground">
              {derived.progressPercent != null ? `${Math.round(progressValue)}%` : "—"}
            </span>
          </div>
          <Progress value={progressValue} className="h-2" />
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Current step</p>
          <p className="text-sm">{derived.currentStep.trim() ? derived.currentStep : "—"}</p>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Steps</p>
          <div className="table-scroll max-h-64 overflow-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Step</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {derived.steps.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className="text-xs text-muted-foreground">
                      No steps returned yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  derived.steps.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="max-w-[200px] text-xs font-medium">{s.name}</TableCell>
                      <TableCell className="text-xs">
                        <Badge variant="outline" className={cn("text-[10px] font-normal", stepBadgeClass(s.statusNorm))}>
                          {s.statusNorm}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[280px] text-xs text-muted-foreground">
                        {s.blockingReason || s.requiredMissingInput ? (
                          <span className="block space-y-1">
                            {s.blockingReason ? (
                              <span className="block text-foreground">Blocking reason: {s.blockingReason}</span>
                            ) : null}
                            {s.requiredMissingInput ? (
                              <span className="block">Required missing input: {s.requiredMissingInput}</span>
                            ) : null}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Events</p>
          <ScrollArea className="max-h-48 rounded-md border">
            <ul className="divide-y p-2 text-sm">
              {derived.events.length === 0 ? (
                <li className="list-none px-1 py-2 text-muted-foreground">No events yet.</li>
              ) : (
                derived.events.map((ev, i) => (
                  <li key={`${ev.ts ?? "t"}-${ev.type ?? "ty"}-${i}`} className="list-none space-y-0.5 py-2">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {ev.ts ? <span>{ev.ts}</span> : null}
                      {ev.type ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {ev.type}
                        </Badge>
                      ) : null}
                    </div>
                    {ev.message ? <p className="text-sm">{ev.message}</p> : null}
                  </li>
                ))
              )}
            </ul>
          </ScrollArea>
        </div>

        {derived.warnings.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Warnings</p>
            <ul className="list-inside list-disc space-y-1 text-sm text-amber-950 dark:text-amber-100">
              {derived.warnings.map((w, i) => (
                <li key={`${w}-${i}`}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {derived.notes ? (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Notes</p>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">{derived.notes}</p>
          </div>
        ) : null}

        {derived.artifacts.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Artifacts produced</p>
            <ul className="space-y-1 text-sm">
              {derived.artifacts.map((a) => (
                <li key={a.id} className="rounded-md border bg-muted/20 px-2 py-1.5 font-mono text-[10px]">
                  <span className="text-foreground">{a.label}</span>
                  <span className="text-muted-foreground"> · </span>
                  <span>{a.id}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={!canCancel || cancelBusy}
            onClick={() => void handleCancel()}
          >
            {cancelBusy ? "Canceling…" : "Cancel workflow run"}
          </Button>
        </div>

        {artifactsLoading ? <p className="text-xs text-muted-foreground">Loading workflow artifacts payload…</p> : null}
        {artifactsError ? <p className="text-xs text-destructive">{artifactsError}</p> : null}

        <Collapsible className="rounded-lg border">
          <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium hover:bg-muted/40">
            <span>Developer JSON</span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
          </CollapsibleTrigger>
          <CollapsibleContent className="border-t px-3 pb-3">
            <DeveloperJsonPanel
              data={{
                run: runPayload,
                events: eventsPayload,
                steps: stepsPayload,
                artifacts: artifactsPayload,
              }}
            />
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}
