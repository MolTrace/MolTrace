"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ApiError, apiFetch } from "@/src/lib/api/client"
import { trackJobCompleted, trackJobStarted } from "@/src/lib/analytics/analytics-client"

export type AnalysisJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled"

export type AnalysisJobEvent = {
  id?: string
  type?: string
  message?: string
  timestamp?: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string | undefined {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v
    if (typeof v === "number") return String(v)
  }
  return undefined
}

function readNum(o: Record<string, unknown>, keys: string[]): number | undefined {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  }
  return undefined
}

export function normalizeJobStatus(raw: unknown): AnalysisJobStatus | null {
  if (typeof raw !== "string") return null
  const s = raw.trim().toLowerCase().replace(/-/g, "_")
  if (s === "cancelled") return "canceled"
  if (s === "success" || s === "completed") return "succeeded"
  if (s === "error") return "failed"
  if (
    s === "queued" ||
    s === "running" ||
    s === "succeeded" ||
    s === "failed" ||
    s === "canceled"
  ) {
    return s as AnalysisJobStatus
  }
  return null
}

function isTerminalStatus(s: AnalysisJobStatus | null): boolean {
  return s === "succeeded" || s === "failed" || s === "canceled"
}

function formatHookError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback
  if (err instanceof Error) return err.message || fallback
  return fallback
}

function isUnavailableError(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true
  if (err.status === 0 || err.status >= 502) return true
  return false
}

function extractJobId(data: unknown): string | null {
  if (!isRecord(data)) return null
  const sid = readStr(data, ["job_id", "jobId", "id"])
  if (sid) return sid
  if (typeof data.id === "number") return String(data.id)
  return null
}

export function normalizeEventsPayload(data: unknown): AnalysisJobEvent[] {
  let rows: unknown[] = []
  if (Array.isArray(data)) rows = data
  else if (isRecord(data)) {
    if (Array.isArray(data.events)) rows = data.events
    else if (Array.isArray(data.items)) rows = data.items
    else if (Array.isArray(data.results)) rows = data.results
  }
  const out: AnalysisJobEvent[] = []
  for (const row of rows) {
    if (!isRecord(row)) continue
    out.push({
      id: readStr(row, ["id", "event_id", "eventId"]),
      type: readStr(row, ["type", "event_type", "eventType", "kind"]),
      message: readStr(row, ["message", "msg", "detail", "description"]),
      timestamp: readStr(row, ["timestamp", "created_at", "createdAt", "time"]),
    })
  }
  return out
}

function normalizeArtifactIds(data: unknown): string[] {
  if (!isRecord(data)) return []
  const raw =
    data.artifact_ids ??
    data.artifactIds ??
    data.artifacts ??
    data.artifact_ids_list
  if (Array.isArray(raw)) {
    return raw
      .map((x) => (typeof x === "string" ? x : typeof x === "number" ? String(x) : null))
      .filter((x): x is string => Boolean(x))
  }
  return []
}

function readJobTypeFromPayload(data: unknown): string {
  if (!isRecord(data)) return "unknown"
  const t =
    readStr(data, ["job_type", "jobType", "analysis_job_type", "analysis_job_type_slug", "type"]) ?? ""
  return t.trim() || "unknown"
}

function readDurationSecondsFromPayload(data: unknown): number | undefined {
  if (!isRecord(data)) return undefined
  const n = readNum(data, ["duration_seconds", "durationSeconds", "wall_time_seconds", "elapsed_seconds"])
  return n != null && Number.isFinite(n) ? n : undefined
}

export function applyJobRecord(data: unknown): {
  status: AnalysisJobStatus | null
  progressPercent: number | null
  currentStep: string | null
  result: unknown
  artifactIds: string[]
} {
  if (!isRecord(data)) {
    return { status: null, progressPercent: null, currentStep: null, result: null, artifactIds: [] }
  }
  const status =
    normalizeJobStatus(readStr(data, ["status", "job_status", "state"])) ??
    normalizeJobStatus(readStr(data, ["phase"])) ??
    null
  let progress = readNum(data, ["progress_percent", "progressPercent", "progress"])
  if (progress != null && progress > 0 && progress <= 1) progress = Math.round(progress * 100)
  if (progress != null && (progress < 0 || progress > 100)) progress = Math.max(0, Math.min(100, progress))
  const currentStep =
    readStr(data, ["current_step", "currentStep", "step", "message"]) ?? null
  const result = data.result ?? data.payload ?? data.output ?? null
  const artifactIds = normalizeArtifactIds(data)
  return {
    status,
    progressPercent: progress ?? null,
    currentStep,
    result,
    artifactIds,
  }
}

export type UseAnalysisJobReturn = {
  jobId: string | null
  status: AnalysisJobStatus | null
  progressPercent: number | null
  currentStep: string | null
  result: unknown
  error: string | null
  events: AnalysisJobEvent[]
  artifactIds: string[]
  backendUnavailable: boolean
  rawJob: unknown | null
  rawEventsPayload: unknown | null
  polling: boolean
  cancelBusy: boolean
  createJob: (payload: unknown) => Promise<string | null>
  pollJob: (jobId: string) => Promise<void>
  cancelJob: (jobId?: string) => Promise<void>
  loadJobEvents: (jobId?: string) => Promise<void>
  reset: () => void
}

/**
 * Delay before each successive poll, in ms — a backoff ladder rather than a flat interval.
 *
 * Raw-FID processing is typically well under a second, but the old fixed 2 s interval meant a
 * finished job could sit undiscovered for up to 2 s, so every analysis felt like it took at least
 * two seconds. Starting fast catches the common case almost immediately; the delay then grows back
 * to the previous cadence, so a genuinely long job issues no more requests than it used to.
 *
 * The cumulative schedule is 0 · 250 · 500 · 1000 · 2000 · then every 2000 ms. It deliberately
 * LANDS ON 2000 so that from there it coincides with the old grid — that guarantees no job is ever
 * discovered later than it used to be. (An earlier ladder summed to 2350 ms and would have made
 * jobs finishing near 2 s *slower*; the accompanying test pins this invariant.)
 */
export const ANALYSIS_JOB_POLL_DELAYS_MS = [0, 250, 250, 500, 1000, 2000] as const

export function useAnalysisJob(): UseAnalysisJobReturn {
  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<AnalysisJobStatus | null>(null)
  const [progressPercent, setProgressPercent] = useState<number | null>(null)
  const [currentStep, setCurrentStep] = useState<string | null>(null)
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [events, setEvents] = useState<AnalysisJobEvent[]>([])
  const [artifactIds, setArtifactIds] = useState<string[]>([])
  const [backendUnavailable, setBackendUnavailable] = useState(false)
  const [rawJob, setRawJob] = useState<unknown | null>(null)
  const [rawEventsPayload, setRawEventsPayload] = useState<unknown | null>(null)
  const [polling, setPolling] = useState(false)
  const [cancelBusy, setCancelBusy] = useState(false)

  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const jobCompletionTrackedRef = useRef<Set<string>>(new Set())

  const stopPolling = useCallback(() => {
    if (pollTimeoutRef.current != null) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
    setPolling(false)
  }, [])

  const applyJobResponse = useCallback(
    (data: unknown) => {
      setRawJob(data)
      const parsed = applyJobRecord(data)
      setStatus(parsed.status)
      setProgressPercent(parsed.progressPercent)
      setCurrentStep(parsed.currentStep)
      setResult(parsed.result)
      setArtifactIds(parsed.artifactIds)
      return parsed.status
    },
    [],
  )

  const fetchOnce = useCallback(
    async (id: string): Promise<AnalysisJobStatus | null> => {
      // Status and events are independent endpoints — fetching them in parallel halves the
      // wall time of every poll tick. Events stay optional: a failure there must not fail the poll.
      const [jobData, evData] = await Promise.all([
        apiFetch<unknown>(`/jobs/${encodeURIComponent(id)}`, { method: "GET" }),
        apiFetch<unknown>(`/jobs/${encodeURIComponent(id)}/events`, { method: "GET" }).catch(
          () => null,
        ),
      ])
      const st = applyJobResponse(jobData)
      if (evData != null) {
        setRawEventsPayload(evData)
        setEvents(normalizeEventsPayload(evData))
      }
      if (st && isTerminalStatus(st) && !jobCompletionTrackedRef.current.has(id)) {
        jobCompletionTrackedRef.current.add(id)
        trackJobCompleted({
          job_id: id,
          status: st,
          duration_seconds: readDurationSecondsFromPayload(jobData),
          metadata: {
            job_type: readJobTypeFromPayload(jobData),
          },
        })
      }
      return st
    },
    [applyJobResponse],
  )

  useEffect(() => {
    if (!jobId) {
      stopPolling()
      return
    }

    let alive = true
    let attempt = 0

    const scheduleNext = () => {
      if (!alive) return
      const delay = ANALYSIS_JOB_POLL_DELAYS_MS[
        Math.min(attempt, ANALYSIS_JOB_POLL_DELAYS_MS.length - 1)
      ]!
      attempt += 1
      pollTimeoutRef.current = setTimeout(() => {
        void runTick()
      }, delay)
    }

    const runTick = async () => {
      if (!alive) return
      try {
        const st = await fetchOnce(jobId)
        if (!alive) return
        setError(null)
        setBackendUnavailable(false)
        if (st && isTerminalStatus(st)) {
          stopPolling()
          return
        }
      } catch (err) {
        setError(formatHookError(err, "Job poll failed."))
        setBackendUnavailable(isUnavailableError(err))
        stopPolling()
        return
      }
      scheduleNext()
    }

    stopPolling()
    setPolling(true)
    // Poll on a backoff rather than a flat 2 s grid: FID processing usually finishes well under a
    // second, and a fixed interval quantised that to whole 2 s buckets — the job was done but the
    // UI did not know for up to 2 s. Early ticks are cheap and catch the common case immediately;
    // the delay then grows to the old cadence so genuinely long jobs cost no extra requests.
    alive = true
    void runTick()

    return () => {
      alive = false
      stopPolling()
    }
  }, [jobId, fetchOnce, stopPolling])

  const createJob = useCallback(
    async (payload: unknown): Promise<string | null> => {
      setError(null)
      stopPolling()
      try {
        const data = await apiFetch<unknown>("/jobs", {
          method: "POST",
          body: payload ?? {},
        })
        const id = extractJobId(data)
        if (!id) {
          throw new Error("No job id returned.")
        }
        setJobId(id)
        applyJobResponse(data)
        setBackendUnavailable(false)
        trackJobStarted({
          job_id: id,
          metadata: {
            job_type: readJobTypeFromPayload(data),
          },
        })
        const snap = applyJobRecord(data)
        if (snap.status && isTerminalStatus(snap.status) && !jobCompletionTrackedRef.current.has(id)) {
          jobCompletionTrackedRef.current.add(id)
          trackJobCompleted({
            job_id: id,
            status: snap.status,
            duration_seconds: readDurationSecondsFromPayload(data),
            metadata: {
              job_type: readJobTypeFromPayload(data),
            },
          })
        }
        return id
      } catch (err) {
        setError(formatHookError(err, "Could not create job."))
        setBackendUnavailable(isUnavailableError(err))
        return null
      }
    },
    [applyJobResponse, stopPolling],
  )

  const pollJob = useCallback(
    async (jid: string) => {
      setJobId(jid)
      setError(null)
      try {
        await fetchOnce(jid)
        setBackendUnavailable(false)
      } catch (err) {
        setError(formatHookError(err, "Could not load job."))
        setBackendUnavailable(isUnavailableError(err))
      }
    },
    [fetchOnce],
  )

  const cancelJob = useCallback(
    async (jid?: string) => {
      const target = jid ?? jobId
      if (!target) return
      setCancelBusy(true)
      setError(null)
      try {
        await apiFetch(`/jobs/${encodeURIComponent(target)}/cancel`, {
          method: "POST",
          body: {},
        })
        const st = await fetchOnce(target)
        setBackendUnavailable(false)
        if (st && isTerminalStatus(st)) {
          stopPolling()
        }
      } catch (err) {
        setError(formatHookError(err, "Could not cancel job."))
        setBackendUnavailable(isUnavailableError(err))
      } finally {
        setCancelBusy(false)
      }
    },
    [fetchOnce, jobId, stopPolling],
  )

  const loadJobEvents = useCallback(
    async (jid?: string) => {
      const target = jid ?? jobId
      if (!target) return
      try {
        const evData = await apiFetch<unknown>(`/jobs/${encodeURIComponent(target)}/events`, {
          method: "GET",
        })
        setRawEventsPayload(evData)
        setEvents(normalizeEventsPayload(evData))
        setBackendUnavailable(false)
      } catch (err) {
        setError(formatHookError(err, "Could not load job events."))
        setBackendUnavailable(isUnavailableError(err))
      }
    },
    [jobId],
  )

  const reset = useCallback(() => {
    stopPolling()
    jobCompletionTrackedRef.current.clear()
    setJobId(null)
    setStatus(null)
    setProgressPercent(null)
    setCurrentStep(null)
    setResult(null)
    setError(null)
    setEvents([])
    setArtifactIds([])
    setBackendUnavailable(false)
    setRawJob(null)
    setRawEventsPayload(null)
  }, [stopPolling])

  return {
    jobId,
    status,
    progressPercent,
    currentStep,
    result,
    error,
    events,
    artifactIds,
    backendUnavailable,
    rawJob,
    rawEventsPayload,
    polling,
    cancelBusy,
    createJob,
    pollJob,
    cancelJob,
    loadJobEvents,
    reset,
  }
}
