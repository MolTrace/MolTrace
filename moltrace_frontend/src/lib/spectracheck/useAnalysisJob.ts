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

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const jobCompletionTrackedRef = useRef<Set<string>>(new Set())

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current != null) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
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
      const jobData = await apiFetch<unknown>(`/jobs/${encodeURIComponent(id)}`, { method: "GET" })
      const st = applyJobResponse(jobData)
      try {
        const evData = await apiFetch<unknown>(`/jobs/${encodeURIComponent(id)}/events`, {
          method: "GET",
        })
        setRawEventsPayload(evData)
        setEvents(normalizeEventsPayload(evData))
      } catch {
        /* events optional */
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

    const tick = async () => {
      if (!alive) return
      try {
        const st = await fetchOnce(jobId)
        setError(null)
        setBackendUnavailable(false)
        if (st && isTerminalStatus(st)) {
          stopPolling()
        }
      } catch (err) {
        setError(formatHookError(err, "Job poll failed."))
        setBackendUnavailable(isUnavailableError(err))
        stopPolling()
      }
    }

    void tick()

    stopPolling()
    setPolling(true)
    pollIntervalRef.current = setInterval(() => {
      void (async () => {
        try {
          const st = await fetchOnce(jobId)
          setError(null)
          setBackendUnavailable(false)
          if (st && isTerminalStatus(st)) {
            stopPolling()
          }
        } catch (err) {
          setError(formatHookError(err, "Job poll failed."))
          setBackendUnavailable(isUnavailableError(err))
          stopPolling()
        }
      })()
    }, 2000)

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
