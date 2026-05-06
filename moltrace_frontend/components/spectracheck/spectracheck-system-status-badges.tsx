"use client"

import { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { apiFetch } from "@/lib/api/client"
import { cn } from "@/lib/utils"

type SubsystemHealth = "healthy" | "degraded" | "unknown"

function readRecord(data: unknown): Record<string, unknown> | null {
  if (data != null && typeof data === "object" && !Array.isArray(data)) {
    return data as Record<string, unknown>
  }
  return null
}

function mapDependencyStatus(raw: unknown): SubsystemHealth {
  if (raw === "ok") return "healthy"
  if (raw === "warning" || raw === "error" || raw === "unknown") return "degraded"
  return "unknown"
}

function formatCheckTime(iso: string | null): string {
  if (!iso) return "—"
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return "—"
  return new Date(ms).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

export function SpectraCheckSystemStatusBadges() {
  const [loading, setLoading] = useState(true)
  const [backendConnected, setBackendConnected] = useState(false)
  const [jobs, setJobs] = useState<SubsystemHealth>("unknown")
  const [storage, setStorage] = useState<SubsystemHealth>("unknown")
  const [lastHealthIso, setLastHealthIso] = useState<string | null>(null)
  const [statusOk, setStatusOk] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    let healthJson: unknown = null
    let healthHit = false
    try {
      healthJson = await apiFetch<unknown>("/system/health", { method: "GET" })
      healthHit = true
    } catch {
      /* keep healthHit false */
    }

    let statusJson: unknown = null
    let statusHit = false
    try {
      statusJson = await apiFetch<unknown>("/system/status", { method: "GET" })
      statusHit = true
    } catch {
      /* keep statusHit false */
    }

    const hRec = readRecord(healthJson)
    const tsRaw = hRec?.timestamp
    const ts =
      typeof tsRaw === "string"
        ? tsRaw
        : tsRaw != null && typeof (tsRaw as { toString?: () => string }).toString === "function"
          ? String(tsRaw)
          : null

    const sRec = readRecord(statusJson)
    const jobSt = statusHit ? mapDependencyStatus(sRec?.job_queue_status) : "unknown"
    const storSt = statusHit ? mapDependencyStatus(sRec?.storage_status) : "unknown"

    setBackendConnected(healthHit)
    setLastHealthIso(healthHit ? ts : null)
    setJobs(jobSt)
    setStorage(storSt)
    setStatusOk(statusHit)
    setLoading(false)
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), 60_000)
    return () => window.clearInterval(id)
  }, [refresh])

  const badgeBase =
    "h-5 gap-1 border-border/80 px-1.5 py-0 text-[10px] font-normal leading-none sm:text-[11px]"

  function jobsLabel(): string {
    if (!statusOk) return "Jobs —"
    if (jobs === "healthy") return "Jobs healthy"
    if (jobs === "degraded") return "Jobs degraded"
    return "Jobs —"
  }

  function storageLabel(): string {
    if (!statusOk) return "Storage —"
    if (storage === "healthy") return "Storage healthy"
    if (storage === "degraded") return "Storage degraded"
    return "Storage —"
  }

  function jobsClass(): string {
    if (!statusOk) return "text-muted-foreground"
    if (jobs === "unknown") return "border-border/80 text-muted-foreground"
    if (jobs === "healthy") return "border-success/40 text-success"
    return "border-warning/50 text-warning"
  }

  function storageClass(): string {
    if (!statusOk) return "text-muted-foreground"
    if (storage === "unknown") return "border-border/80 text-muted-foreground"
    if (storage === "healthy") return "border-success/40 text-success"
    return "border-warning/50 text-warning"
  }

  return (
    <div className="flex max-w-full flex-wrap items-center justify-end gap-1 sm:gap-1.5">
      {loading ? (
        <Badge variant="outline" className={cn(badgeBase, "text-muted-foreground")}>
          <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/70" />
          Status…
        </Badge>
      ) : (
        <>
          {backendConnected ? (
            <Badge variant="outline" className={cn(badgeBase, "border-success/40 text-success")}>
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              Backend connected
            </Badge>
          ) : (
            <Badge variant="outline" className={cn(badgeBase, "border-warning/50 text-warning")}>
              <span className="h-1.5 w-1.5 rounded-full bg-warning" />
              Backend unavailable
            </Badge>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className={cn(badgeBase, jobsClass())}>
                {jobsLabel()}
              </Badge>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-xs text-xs">
              {statusOk
                ? "From GET /system/status (job queue dependency)."
                : "Detailed job queue status requires GET /system/status (sign in if unavailable)."}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className={cn(badgeBase, storageClass())}>
                {storageLabel()}
              </Badge>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-xs text-xs">
              {statusOk
                ? "From GET /system/status (storage dependency)."
                : "Detailed storage status requires GET /system/status (sign in if unavailable)."}
            </TooltipContent>
          </Tooltip>
          <span
            className="text-[10px] tabular-nums text-muted-foreground sm:text-[11px]"
            title="Last successful GET /system/health response time"
          >
            {backendConnected ? `Checked ${formatCheckTime(lastHealthIso)}` : "No health check"}
          </span>
        </>
      )}
    </div>
  )
}
