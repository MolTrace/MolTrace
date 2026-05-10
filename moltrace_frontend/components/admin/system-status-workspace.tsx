"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Bell,
  BookOpen,
  Cable,
  ChevronDown,
  Database,
  HardDrive,
  Heart,
  ListChecks,
  ServerOff,
  Settings2,
  Tag,
  Workflow,
} from "lucide-react"

const SYSTEM_STATUS_TOOLTIP =
  "System Status checks whether the backend, database, storage, job queue, and environment configuration are ready for scientific workflows."

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

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

type HealthUi = "healthy" | "degraded" | "unhealthy" | "unknown"

function overallHealthUi(raw: string): HealthUi {
  const s = raw.toLowerCase()
  if (s === "healthy" || s === "degraded" || s === "unhealthy") return s
  return "unknown"
}

function healthBadgeClass(ui: HealthUi): string {
  switch (ui) {
    case "healthy":
      return "border-success/50 text-success"
    case "degraded":
      return "border-warning/50 text-warning"
    case "unhealthy":
      return "border-destructive/50 text-destructive"
    default:
      return "text-muted-foreground"
  }
}

function dependencyBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === "ok") return "border-success/50 text-success"
  if (s === "warning") return "border-warning/50 text-warning"
  if (s === "error") return "border-destructive/50 text-destructive"
  return "text-muted-foreground"
}

export function SystemStatusWorkspace() {
  const [loading, setLoading] = useState(true)
  const [health, setHealth] = useState<Record<string, unknown> | null>(null)
  const [status, setStatus] = useState<Record<string, unknown> | null>(null)
  const [version, setVersion] = useState<Record<string, unknown> | null>(null)
  const [dependencies, setDependencies] = useState<unknown[] | null>(null)
  const [environmentCheck, setEnvironmentCheck] = useState<Record<string, unknown> | null>(null)

  const [errHealth, setErrHealth] = useState("")
  const [errStatus, setErrStatus] = useState("")
  const [errVersion, setErrVersion] = useState("")
  const [errDeps, setErrDeps] = useState("")
  const [errEnv, setErrEnv] = useState("")
  const [connectorHealthLoading, setConnectorHealthLoading] = useState(true)
  const [connectorHealthError, setConnectorHealthError] = useState("")
  const [connectorHealthBackendUnavailable, setConnectorHealthBackendUnavailable] = useState(false)
  const [connectorActiveCount, setConnectorActiveCount] = useState<number | null>(null)
  const [connectorWarningCount, setConnectorWarningCount] = useState<number | null>(null)
  const [connectorLastHealthFailCount, setConnectorLastHealthFailCount] = useState<number | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setErrHealth("")
    setErrStatus("")
    setErrVersion("")
    setErrDeps("")
    setErrEnv("")

    const run = async <T,>(
      path: string,
      setter: (v: T | null) => void,
      setErr: (s: string) => void,
      empty: T | null,
    ) => {
      try {
        const data = await apiFetch<T>(path, { method: "GET" })
        setter((data ?? empty) as T | null)
      } catch (e) {
        setErr(formatErr(e, `Could not load ${path}.`))
        setter(empty)
      }
    }

    const runDeps = async () => {
      try {
        const data = await apiFetch<unknown>("/system/dependencies", { method: "GET" })
        setDependencies(Array.isArray(data) ? data : null)
        setErrDeps("")
      } catch (e) {
        setErrDeps(formatErr(e, "Could not load /system/dependencies."))
        setDependencies(null)
      }
    }

    await Promise.all([
      run<Record<string, unknown>>("/system/health", setHealth, setErrHealth, null),
      run<Record<string, unknown>>("/system/status", setStatus, setErrStatus, null),
      run<Record<string, unknown>>("/system/version", setVersion, setErrVersion, null),
      runDeps(),
      run<Record<string, unknown>>("/system/environment-check", setEnvironmentCheck, setErrEnv, null),
    ])

    setLoading(false)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    let cancelled = false
    setConnectorHealthLoading(true)
    setConnectorHealthError("")
    setConnectorHealthBackendUnavailable(false)

    void apiFetch<unknown>("/connectors", { method: "GET" })
      .then((payload) => {
        if (cancelled) return
        const rows = Array.isArray(payload)
          ? payload.filter(isRecord)
          : isRecord(payload) && Array.isArray(payload.items)
            ? payload.items.filter(isRecord)
            : []
        const active = rows.filter((row) => {
          const s = readStr(row, ["status", "health_status", "state"]).toLowerCase()
          return s === "active" || s === "enabled" || s === "connected" || s === "healthy"
        }).length
        const warnings = rows.filter((row) => {
          const s = readStr(row, ["status", "health_status", "state"]).toLowerCase()
          return s === "warning" || s === "degraded" || s === "error" || s === "failed" || s === "unhealthy"
        }).length
        const lastHealthFailed = rows.filter((row) => {
          const s = readStr(row, ["last_health_check_status", "health_check_status"]).toLowerCase()
          return s === "failed" || s === "error" || s === "unhealthy"
        }).length
        setConnectorActiveCount(active)
        setConnectorWarningCount(warnings)
        setConnectorLastHealthFailCount(lastHealthFailed)
      })
      .catch((err) => {
        if (cancelled) return
        setConnectorHealthBackendUnavailable(true)
        setConnectorHealthError(formatErr(err, "Could not load /connectors."))
      })
      .finally(() => {
        if (!cancelled) setConnectorHealthLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const backendUnreachable =
    !loading &&
    errHealth &&
    errStatus &&
    errVersion &&
    errDeps &&
    errEnv

  const overallFromHealth = health ? readStr(health, ["status"]) : ""
  const overallFromStatus = status ? readStr(status, ["status"]) : ""
  const overallUi = overallHealthUi(overallFromHealth || overallFromStatus)

  const mergedWarnings = useMemo(() => {
    const out: string[] = []
    const pushList = (label: string, v: unknown) => {
      if (!Array.isArray(v)) return
      for (const item of v) {
        if (typeof item === "string" && item.trim()) out.push(`[${label}] ${item.trim()}`)
      }
    }
    if (health) {
      pushList("health", health.warnings)
      pushList("health", health.notes)
    }
    if (status) {
      pushList("status", status.warnings)
      pushList("status", status.notes)
    }
    if (environmentCheck) {
      pushList("environment-check", environmentCheck.warnings)
      pushList("environment-check", environmentCheck.notes)
    }
    return out
  }, [health, status, environmentCheck])

  const developerBundle = useMemo(
    () => ({
      health,
      status,
      version,
      dependencies,
      environment_check: environmentCheck,
    }),
    [health, status, version, dependencies, environmentCheck],
  )

  const dependencyRows = useMemo(() => {
    if (!Array.isArray(dependencies)) return []
    return dependencies.filter(isRecord) as Record<string, unknown>[]
  }, [dependencies])

  const healthChecksRows = useMemo(() => {
    if (!health || !Array.isArray(health.checks)) return []
    return (health.checks as unknown[]).filter(isRecord) as Record<string, unknown>[]
  }, [health])

  const openapiAvailable =
    status && typeof status.openapi_available === "boolean" ? status.openapi_available : null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-slate)" }}
          >
            MolTrace · Admin · System Status
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">System Status</h1>
            <InfoTooltip content={SYSTEM_STATUS_TOOLTIP} label="About System Status" />
          </div>
          <p className="text-sm text-muted-foreground">
            Operational visibility for backend health, dependencies, and environment checks.
          </p>
          {!loading && backendUnreachable ? (
            <p className="mt-1 flex items-center gap-1.5 text-xs text-destructive">
              <ServerOff className="h-3.5 w-3.5 shrink-0" aria-hidden />
              Backend unavailable — try again in a moment, or contact your platform administrator.
            </p>
          ) : null}
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void reload()}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>

      {backendUnreachable ? (
        <AlertCard
          variant="error"
          title="Backend unavailable"
          description="System status checks could not be reached. Refresh once the backend is back online."
        />
      ) : null}

      {!backendUnreachable && (errHealth || errStatus || errVersion || errDeps || errEnv) ? (
        <AlertCard variant="error" title="Partial load">
          <div className="space-y-1 text-xs text-foreground/90">
            {errHealth ? <p>Health probe: {errHealth}</p> : null}
            {errStatus ? <p>Status check: {errStatus}</p> : null}
            {errVersion ? <p>Version info: {errVersion}</p> : null}
            {errDeps ? <p>Dependency status: {errDeps}</p> : null}
            {errEnv ? <p>Environment check: {errEnv}</p> : null}
          </div>
        </AlertCard>
      ) : null}

      {/* 1. Overall system health */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Overall system health</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Health"
          title="Overall health"
          icon={Heart}
          description="Live health probe and overall service status from the backend."
        >
          <div className="space-y-3 text-sm">
            {loading ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : errHealth && errStatus ? (
              <p className="text-xs text-destructive">Overall status unavailable — health and status requests failed.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className={`font-normal ${healthBadgeClass(overallUi)}`}>
                  {overallFromHealth || overallFromStatus || "unknown"}
                </Badge>
                {health && health.uptime_seconds != null ? (
                  <span className="text-xs text-muted-foreground">
                    uptime_seconds: {String(health.uptime_seconds)}
                  </span>
                ) : null}
                {health && readStr(health, ["timestamp"]) ? (
                  <span className="text-xs text-muted-foreground">
                    timestamp: {readStr(health, ["timestamp"])}
                  </span>
                ) : null}
              </div>
            )}
          </div>
        </ModuleCard>
      </div>

      {/* 2. Backend version */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Backend version</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Version"
          title="Backend version"
          icon={Tag}
          description="Backend service build, version, and Git commit identifier."
        >
          <div className="space-y-2 text-sm">
            {loading ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : errVersion && !health && !status ? (
              <p className="text-xs text-destructive">Version metadata unavailable.</p>
            ) : (
              <dl className="grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">backend_version</dt>
                  <dd className="font-mono">
                    {readStr(version ?? {}, ["backend_version"]) ||
                      readStr(health ?? {}, ["backend_version"]) ||
                      readStr(status ?? {}, ["backend_version"]) ||
                      "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">api_version</dt>
                  <dd className="font-mono">
                    {readStr(version ?? {}, ["api_version"]) || readStr(status ?? {}, ["api_version"]) || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">environment</dt>
                  <dd className="font-mono">
                    {readStr(version ?? {}, ["environment"]) || readStr(health ?? {}, ["environment"]) || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">timestamp</dt>
                  <dd className="font-mono">{readStr(version ?? {}, ["timestamp"]) || "—"}</dd>
                </div>
              </dl>
            )}
          </div>
        </ModuleCard>
      </div>

      {/* 3. Dependency checks */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Dependency checks</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Dependencies"
          title="Dependency checks"
          icon={ListChecks}
          description="Status of upstream services the platform depends on, plus liveness/readiness checks."
        >
          <div className="space-y-4 text-sm">
            {loading ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : (
              <>
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">name</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="text-xs">latency_ms</TableHead>
                        <TableHead className="text-xs">message</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dependencyRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="text-xs text-muted-foreground">
                            {errDeps ? String(errDeps) : "No dependency rows returned."}
                          </TableCell>
                        </TableRow>
                      ) : (
                        dependencyRows.map((row, i) => (
                          <TableRow key={`${readStr(row, ["name"])}-${i}`}>
                            <TableCell className="font-mono text-[10px]">{readStr(row, ["name"]) || "—"}</TableCell>
                            <TableCell className="text-xs">
                              <Badge
                                variant="outline"
                                className={`font-normal ${dependencyBadgeClass(readStr(row, ["status"]))}`}
                              >
                                {readStr(row, ["status"]) || "unknown"}
                              </Badge>
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {row.latency_ms != null ? String(row.latency_ms) : "—"}
                            </TableCell>
                            <TableCell className="max-w-[20rem] text-xs">{readStr(row, ["message"]) || "—"}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
                {healthChecksRows.length > 0 ? (
                  <div className="overflow-x-auto rounded-md border">
                    <p className="border-b bg-muted/30 px-3 py-2 text-xs font-medium text-muted-foreground">
                      Health check probes
                    </p>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">name</TableHead>
                          <TableHead className="text-xs">status</TableHead>
                          <TableHead className="text-xs">latency_ms</TableHead>
                          <TableHead className="text-xs">message</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {healthChecksRows.map((row, i) => (
                          <TableRow key={`hc-${readStr(row, ["name"])}-${i}`}>
                            <TableCell className="font-mono text-[10px]">{readStr(row, ["name"]) || "—"}</TableCell>
                            <TableCell className="text-xs">
                              <Badge
                                variant="outline"
                                className={`font-normal ${dependencyBadgeClass(readStr(row, ["status"]))}`}
                              >
                                {readStr(row, ["status"]) || "unknown"}
                              </Badge>
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {row.latency_ms != null ? String(row.latency_ms) : "—"}
                            </TableCell>
                            <TableCell className="max-w-[20rem] text-xs">{readStr(row, ["message"]) || "—"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </ModuleCard>
      </div>

      {/* 4–6 Grid: Database, Storage, Jobs/Workers + OpenAPI + Environment */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Database, storage, jobs, OpenAPI, environment</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ModuleCard
            accent="slate"
            eyebrow="Database"
            title="Database"
            icon={Database}
            description="Connectivity and health of the primary database."
          >
            <div>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : errStatus ? (
                <p className="text-xs text-destructive">{errStatus}</p>
              ) : status ? (
                <Badge
                  variant="outline"
                  className={`font-normal ${dependencyBadgeClass(readStr(status, ["database_status"]))}`}
                >
                  {readStr(status, ["database_status"]) || "unknown"}
                </Badge>
              ) : (
                <p className="text-xs text-muted-foreground">—</p>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="slate"
            eyebrow="Storage"
            title="Storage"
            icon={HardDrive}
            description="Object storage availability for files, artifacts, and reports."
          >
            <div>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : errStatus ? (
                <p className="text-xs text-destructive">{errStatus}</p>
              ) : status ? (
                <Badge
                  variant="outline"
                  className={`font-normal ${dependencyBadgeClass(readStr(status, ["storage_status"]))}`}
                >
                  {readStr(status, ["storage_status"]) || "unknown"}
                </Badge>
              ) : (
                <p className="text-xs text-muted-foreground">—</p>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="slate"
            eyebrow="Workers"
            title="Jobs / Workers"
            icon={Workflow}
            description="Background job queue depth and worker health."
          >
            <div className="space-y-2 text-xs">
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : errStatus ? (
                <p className="text-xs text-destructive">{errStatus}</p>
              ) : status ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground">job_queue_status</span>
                    <Badge
                      variant="outline"
                      className={`font-normal ${dependencyBadgeClass(readStr(status, ["job_queue_status"]))}`}
                    >
                      {readStr(status, ["job_queue_status"]) || "unknown"}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground">worker_status</span>
                    <Badge
                      variant="outline"
                      className={`font-normal ${dependencyBadgeClass(readStr(status, ["worker_status"]))}`}
                    >
                      {readStr(status, ["worker_status"]) || "unknown"}
                    </Badge>
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="slate"
            eyebrow="API Docs"
            title="OpenAPI"
            icon={BookOpen}
            description="Whether the public API documentation is reachable."
          >
            <div>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : errStatus ? (
                <p className="text-xs text-destructive">{errStatus}</p>
              ) : openapiAvailable === null ? (
                <Badge variant="outline" className="font-normal text-muted-foreground">
                  unknown
                </Badge>
              ) : openapiAvailable ? (
                <Badge variant="outline" className="border-success/50 font-normal text-success">
                  healthy
                </Badge>
              ) : (
                <Badge variant="outline" className="border-warning/50 font-normal text-warning">
                  degraded
                </Badge>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="slate"
            eyebrow="Environment"
            title="Environment"
            icon={Settings2}
            description="Required environment variable check for the active deployment."
            className="sm:col-span-2 lg:col-span-2"
          >
            <div className="space-y-2 text-xs">
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : errEnv ? (
                <p className="text-xs text-destructive">{errEnv}</p>
              ) : environmentCheck ? (
                <>
                  <div className="flex flex-wrap gap-4">
                    <span>
                      <span className="text-muted-foreground">environment </span>
                      <span className="font-mono">{readStr(environmentCheck, ["environment"]) || "—"}</span>
                    </span>
                    <span>
                      <span className="text-muted-foreground">required_variables_present </span>
                      <span className="font-mono">
                        {typeof environmentCheck.required_variables_present === "boolean"
                          ? String(environmentCheck.required_variables_present)
                          : "—"}
                      </span>
                    </span>
                  </div>
                  <p className="text-muted-foreground">
                    missing_variables:{" "}
                    {Array.isArray(environmentCheck.missing_variables)
                      ? (environmentCheck.missing_variables as unknown[]).filter((x) => typeof x === "string").join(", ") ||
                        "—"
                      : "—"}
                  </p>
                  <p className="text-muted-foreground">
                    unsafe_variables:{" "}
                    {Array.isArray(environmentCheck.unsafe_variables)
                      ? (environmentCheck.unsafe_variables as unknown[]).filter((x) => typeof x === "string").join(", ") ||
                        "—"
                      : "—"}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </div>
          </ModuleCard>
        </div>
      </div>

      {/* 7. Environment check summary — covered above; subsection heading per spec */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Environment check summary</h2>
        <p className="text-xs text-muted-foreground">
          Summary fields for environment checks are shown on the Environment card (required_variables_present,
          missing_variables, unsafe_variables).
        </p>
      </div>

      {/* 8. Recent warnings */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Recent warnings</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Warnings"
          title="Recent warnings"
          icon={Bell}
          description="All non-fatal warnings and notes returned across health, status, and environment checks."
        >
          <div>
            {mergedWarnings.length === 0 ? (
              <p className="text-sm text-muted-foreground">No warnings merged from loaded payloads.</p>
            ) : (
              <ul className="list-inside list-disc space-y-1 text-xs">
                {mergedWarnings.map((w, i) => (
                  <li key={`${i}-${w.slice(0, 24)}`}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        </ModuleCard>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Connector health</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Connectors"
          title="Connector health"
          icon={Cable}
          description="Status of all configured external integrations. Credentials and secrets are never displayed here."
        >
          <div className="space-y-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Active connectors</p>
                <p className="text-2xl font-bold tabular-nums">{connectorActiveCount ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Connectors with warnings</p>
                <p className="text-2xl font-bold tabular-nums">{connectorWarningCount ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Failed last health checks</p>
                <p className="text-2xl font-bold tabular-nums">{connectorLastHealthFailCount ?? "—"}</p>
              </div>
            </div>
            {connectorHealthLoading ? (
              <p className="text-xs text-muted-foreground">Loading connector health…</p>
            ) : null}
            {!connectorHealthLoading && connectorHealthBackendUnavailable ? (
              <p className="text-xs text-muted-foreground">
                Connector health unavailable — current admin system content continues.
              </p>
            ) : null}
            {!connectorHealthLoading && connectorHealthError && connectorHealthBackendUnavailable ? (
              <p className="text-xs text-muted-foreground">Details: {connectorHealthError}</p>
            ) : null}
          </div>
        </ModuleCard>
      </div>

      {/* 9. Developer JSON */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Developer JSON</h2>
        <Collapsible className="group rounded-md border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
            Raw responses
            <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className="max-h-[24rem] overflow-auto border-t bg-muted/30 p-3 font-mono text-[10px] leading-relaxed">
              {JSON.stringify(developerBundle, null, 2)}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  )
}
