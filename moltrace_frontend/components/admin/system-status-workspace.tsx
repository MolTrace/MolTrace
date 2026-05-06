"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ChevronDown, ServerOff } from "lucide-react"

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
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">System Status</h1>
            <InfoTooltip content={SYSTEM_STATUS_TOOLTIP} label="About System Status" />
          </div>
          <p className="text-muted-foreground">
            Operational visibility for backend health, dependencies, and environment checks.
          </p>
          {!loading && backendUnreachable ? (
            <p className="mt-1 flex items-center gap-1.5 text-xs text-destructive">
              <ServerOff className="h-3.5 w-3.5 shrink-0" aria-hidden />
              Backend unavailable — check connectivity and <code className="text-xs">/api/backend</code> proxy.
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
        <Alert variant="destructive">
          <AlertTitle>Backend unavailable</AlertTitle>
          <AlertDescription className="text-xs">
            System status endpoints could not be reached. Fix proxy or backend availability and refresh.
          </AlertDescription>
        </Alert>
      ) : null}

      {!backendUnreachable && (errHealth || errStatus || errVersion || errDeps || errEnv) ? (
        <Alert variant="destructive">
          <AlertTitle>Partial load</AlertTitle>
          <AlertDescription className="space-y-1 text-xs">
            {errHealth ? <p>GET /system/health: {errHealth}</p> : null}
            {errStatus ? <p>GET /system/status: {errStatus}</p> : null}
            {errVersion ? <p>GET /system/version: {errVersion}</p> : null}
            {errDeps ? <p>GET /system/dependencies: {errDeps}</p> : null}
            {errEnv ? <p>GET /system/environment-check: {errEnv}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {/* 1. Overall system health */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Overall system health</h2>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Overall health</CardTitle>
            <CardDescription>
              From <code className="text-xs">GET /system/health</code> and{" "}
              <code className="text-xs">GET /system/status</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
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
          </CardContent>
        </Card>
      </div>

      {/* 2. Backend version */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Backend version</h2>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Backend version</CardTitle>
            <CardDescription>
              From <code className="text-xs">GET /system/version</code> and embedded fields on health/status when present.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
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
          </CardContent>
        </Card>
      </div>

      {/* 3. Dependency checks */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Dependency checks</h2>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Dependency checks</CardTitle>
            <CardDescription>
              From <code className="text-xs">GET /system/dependencies</code> and{" "}
              <code className="text-xs">checks</code> on <code className="text-xs">GET /system/health</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
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
                      checks (GET /system/health)
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
          </CardContent>
        </Card>
      </div>

      {/* 4–6 Grid: Database, Storage, Jobs/Workers + OpenAPI + Environment */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Database, storage, jobs, OpenAPI, environment</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Database</CardTitle>
              <CardDescription className="text-xs">
                <code className="text-xs">database_status</code> from <code className="text-xs">GET /system/status</code>
              </CardDescription>
            </CardHeader>
            <CardContent>
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
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Storage</CardTitle>
              <CardDescription className="text-xs">
                <code className="text-xs">storage_status</code> from <code className="text-xs">GET /system/status</code>
              </CardDescription>
            </CardHeader>
            <CardContent>
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
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Jobs / Workers</CardTitle>
              <CardDescription className="text-xs">
                <code className="text-xs">job_queue_status</code>, <code className="text-xs">worker_status</code>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
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
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">OpenAPI</CardTitle>
              <CardDescription className="text-xs">
                <code className="text-xs">openapi_available</code> from <code className="text-xs">GET /system/status</code>
              </CardDescription>
            </CardHeader>
            <CardContent>
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
            </CardContent>
          </Card>

          <Card className="sm:col-span-2 lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Environment</CardTitle>
              <CardDescription className="text-xs">
                From <code className="text-xs">GET /system/environment-check</code>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
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
            </CardContent>
          </Card>
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
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Recent warnings</CardTitle>
            <CardDescription>
              Combined <code className="text-xs">warnings</code> and <code className="text-xs">notes</code> from health,
              status, and environment-check payloads when present.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {mergedWarnings.length === 0 ? (
              <p className="text-sm text-muted-foreground">No warnings merged from loaded payloads.</p>
            ) : (
              <ul className="list-inside list-disc space-y-1 text-xs">
                {mergedWarnings.map((w, i) => (
                  <li key={`${i}-${w.slice(0, 24)}`}>{w}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
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
