"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, API_BASE, apiFetch } from "@/lib/api/client"
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
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ServerOff } from "lucide-react"

const DEPLOYMENT_SETTINGS_TOOLTIP =
  "Deployment Settings helps verify that frontend, backend, storage, database, jobs, and environment configuration are ready for deployment."

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
    if (typeof v === "boolean") return String(v)
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

function dependencyBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === "ok") return "border-success/50 text-success"
  if (s === "warning") return "border-warning/50 text-warning"
  if (s === "error") return "border-destructive/50 text-destructive"
  return "text-muted-foreground"
}

function pickDependency(rows: Record<string, unknown>[], name: string): Record<string, unknown> | null {
  for (const r of rows) {
    if (readStr(r, ["name"]) === name) return r
  }
  return null
}

/** Safe display for public_variables — no secret values; strings reported as length only. */
function formatPublicValue(value: unknown): string {
  if (value == null) return "—"
  if (typeof value === "boolean" || typeof value === "number") return String(value)
  if (typeof value === "string") {
    return value.length === 0 ? "(empty)" : `(string, ${value.length} chars)`
  }
  if (Array.isArray(value)) {
    return JSON.stringify(value)
  }
  if (isRecord(value)) {
    return "{…}"
  }
  return "—"
}

export function DeploymentSettingsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [envCheck, setEnvCheck] = useState<Record<string, unknown> | null>(null)
  const [version, setVersion] = useState<Record<string, unknown> | null>(null)
  const [deps, setDeps] = useState<Record<string, unknown>[]>([])

  const [errEnv, setErrEnv] = useState("")
  const [errVersion, setErrVersion] = useState("")
  const [errDeps, setErrDeps] = useState("")

  const [origin, setOrigin] = useState("")

  useEffect(() => {
    if (typeof window !== "undefined") setOrigin(window.location.origin)
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setErrEnv("")
    setErrVersion("")
    setErrDeps("")

    try {
      const e = await apiFetch<Record<string, unknown>>("/system/environment-check", { method: "GET" })
      setEnvCheck(e ?? null)
    } catch (err) {
      setErrEnv(formatErr(err, "Could not load /system/environment-check."))
      setEnvCheck(null)
    }

    try {
      const v = await apiFetch<Record<string, unknown>>("/system/version", { method: "GET" })
      setVersion(v ?? null)
    } catch (err) {
      setErrVersion(formatErr(err, "Could not load /system/version."))
      setVersion(null)
    }

    try {
      const d = await apiFetch<unknown>("/system/dependencies", { method: "GET" })
      const list = Array.isArray(d) ? d.filter(isRecord) : []
      setDeps(list as Record<string, unknown>[])
    } catch (err) {
      setErrDeps(formatErr(err, "Could not load /system/dependencies."))
      setDeps([])
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const dbRow = useMemo(() => pickDependency(deps, "database"), [deps])
  const storageRow = useMemo(() => pickDependency(deps, "storage"), [deps])
  const openapiRow = useMemo(() => pickDependency(deps, "openapi"), [deps])
  const jobRow = useMemo(() => pickDependency(deps, "job_queue"), [deps])
  const workerRow = useMemo(() => pickDependency(deps, "worker"), [deps])

  const openapiAvailable =
    openapiRow && readStr(openapiRow, ["status"]).toLowerCase() === "ok" ? true : openapiRow ? false : null

  const missingVars = envCheck && Array.isArray(envCheck.missing_variables) ? envCheck.missing_variables : []
  const unsafeVars = envCheck && Array.isArray(envCheck.unsafe_variables) ? envCheck.unsafe_variables : []
  const publicVars = envCheck && isRecord(envCheck.public_variables) ? envCheck.public_variables : null

  const frontendBuild =
    typeof process.env.NEXT_PUBLIC_APP_BUILD !== "undefined"
      ? process.env.NEXT_PUBLIC_APP_BUILD
      : typeof process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA !== "undefined"
        ? process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA
        : ""

  const hasPartialErr = Boolean(errEnv || errVersion || errDeps)
  const allFailed = !loading && errEnv && errVersion && errDeps

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Deployment Settings</h1>
            <InfoTooltip content={DEPLOYMENT_SETTINGS_TOOLTIP} label="About Deployment Settings" />
          </div>
          <p className="text-muted-foreground">
            Environment and dependency snapshot from the backend (admin-capable routes).
          </p>
          {!loading && allFailed ? (
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

      {allFailed ? (
        <Alert variant="destructive">
          <AlertTitle>Backend unavailable</AlertTitle>
          <AlertDescription className="text-xs">
            Deployment data is not reachable. Verify you&apos;re signed in as an administrator and try again.
          </AlertDescription>
        </Alert>
      ) : null}

      {!allFailed && hasPartialErr ? (
        <Alert variant="destructive">
          <AlertTitle>Partial load</AlertTitle>
          <AlertDescription className="space-y-1 text-xs">
            {errEnv ? <p>Environment check: {errEnv}</p> : null}
            {errVersion ? <p>Version info: {errVersion}</p> : null}
            {errDeps ? <p>Dependency status: {errDeps}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">environment</CardTitle>
            <CardDescription>Active deployment environment label.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            {loading ? (
              <p className="text-muted-foreground">…</p>
            ) : envCheck ? (
              <p className="font-mono text-xs">{readStr(envCheck, ["environment"]) || "—"}</p>
            ) : (
              <p className="text-xs text-destructive">—</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">frontend URL</CardTitle>
            <CardDescription>Browser origin</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <p className="break-all font-mono text-xs">{origin || "—"}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">backend status</CardTitle>
            <CardDescription>openapi.json reachability</CardDescription>
          </CardHeader>
          <CardContent>
            <BackendStatusIndicator />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">API base URL</CardTitle>
            <CardDescription>Next.js API proxy base</CardDescription>
          </CardHeader>
          <CardContent className="break-all font-mono text-xs">{API_BASE}</CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">OpenAPI availability</CardTitle>
            <CardDescription>dependency name openapi</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">…</p>
            ) : errDeps ? (
              <p className="text-xs text-destructive">Unavailable</p>
            ) : openapiAvailable === null ? (
              <Badge variant="outline" className="font-normal">
                unknown
              </Badge>
            ) : openapiAvailable ? (
              <Badge variant="outline" className="border-success/50 font-normal text-success">
                available
              </Badge>
            ) : (
              <Badge variant="outline" className="border-destructive/50 font-normal text-destructive">
                unavailable
              </Badge>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">backend version</CardTitle>
            <CardDescription>Backend service build identifier.</CardDescription>
          </CardHeader>
          <CardContent className="font-mono text-xs">
            {loading ? "…" : version ? readStr(version, ["backend_version"]) || "—" : "—"}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">frontend build</CardTitle>
            <CardDescription>NEXT_PUBLIC_APP_BUILD or NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA</CardDescription>
          </CardHeader>
          <CardContent className="font-mono text-xs">
            {frontendBuild ? frontendBuild : <span className="text-muted-foreground">Not configured</span>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">database status</CardTitle>
            <CardDescription>dependency name database</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              "…"
            ) : dbRow ? (
              <Badge
                variant="outline"
                className={`font-normal ${dependencyBadgeClass(readStr(dbRow, ["status"]))}`}
              >
                {readStr(dbRow, ["status"]) || "unknown"}
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">storage backend</CardTitle>
            <CardDescription>dependency name storage</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              "…"
            ) : storageRow ? (
              <Badge
                variant="outline"
                className={`font-normal ${dependencyBadgeClass(readStr(storageRow, ["status"]))}`}
              >
                {readStr(storageRow, ["status"]) || "unknown"}
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">job backend</CardTitle>
            <CardDescription>dependency name job_queue</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              "…"
            ) : jobRow ? (
              <Badge variant="outline" className={`font-normal ${dependencyBadgeClass(readStr(jobRow, ["status"]))}`}>
                {readStr(jobRow, ["status"]) || "unknown"}
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">worker status</CardTitle>
            <CardDescription>dependency name worker</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              "…"
            ) : workerRow ? (
              <Badge
                variant="outline"
                className={`font-normal ${dependencyBadgeClass(readStr(workerRow, ["status"]))}`}
              >
                {readStr(workerRow, ["status"]) || "unknown"}
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">required variables</CardTitle>
          <CardDescription>
            required_variables_present · missing_variables — secret values are never returned by the API.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">required_variables_present</span>
            {loading ? (
              <span>…</span>
            ) : envCheck && typeof envCheck.required_variables_present === "boolean" ? (
              <Badge variant="outline" className="font-normal">
                {String(envCheck.required_variables_present)}
              </Badge>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">missing_variables (names only)</p>
            {missingVars.length === 0 ? (
              <p className="text-xs text-muted-foreground">None listed.</p>
            ) : (
              <ul className="mt-1 list-inside list-disc font-mono text-xs">
                {(missingVars as unknown[]).filter((x): x is string => typeof x === "string").map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">unsafe config warnings</CardTitle>
          <CardDescription>unsafe_variables — configuration keys flagged as unsafe for production.</CardDescription>
        </CardHeader>
        <CardContent>
          {unsafeVars.length === 0 ? (
            <p className="text-sm text-muted-foreground">None listed.</p>
          ) : (
            <ul className="list-inside list-disc font-mono text-xs">
              {(unsafeVars as unknown[]).filter((x): x is string => typeof x === "string").map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {envCheck && Array.isArray(envCheck.warnings) && envCheck.warnings.length > 0 ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">warnings</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc text-xs">
              {(envCheck.warnings as unknown[])
                .filter((x): x is string => typeof x === "string")
                .map((w, i) => (
                  <li key={`${i}-${w.slice(0, 20)}`}>{w}</li>
                ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">public_variables</CardTitle>
          <CardDescription>
            Non-secret fields returned under public_variables. Values may be truncated; SECRET_LIKE_VARIABLES_PRESENT lists
            names only.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!publicVars ? (
            <p className="text-sm text-muted-foreground">—</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">name</TableHead>
                    <TableHead className="text-xs">value (sanitized display)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(publicVars).map(([key, val]) => (
                    <TableRow key={key}>
                      <TableCell className="font-mono text-[10px]">{key}</TableCell>
                      <TableCell className="max-w-[28rem] font-mono text-[10px]">{formatPublicValue(val)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Dependency checks</CardTitle>
          <CardDescription>Health of every external service the platform connects to.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : deps.length === 0 ? (
            <p className="text-sm text-muted-foreground">{errDeps || "No rows."}</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">name</TableHead>
                    <TableHead className="text-xs">status</TableHead>
                    <TableHead className="text-xs">message</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deps.map((row, i) => (
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
                      <TableCell className="max-w-[24rem] text-xs">{readStr(row, ["message"]) || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Version payload</CardTitle>
          <CardDescription>Full version metadata: API, build hash, branch, build time.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 font-mono text-xs">
          <p>
            <span className="text-muted-foreground">api_version </span>
            {version ? readStr(version, ["api_version"]) || "—" : "—"}
          </p>
          <p>
            <span className="text-muted-foreground">environment </span>
            {version ? readStr(version, ["environment"]) || "—" : "—"}
          </p>
          <p>
            <span className="text-muted-foreground">timestamp </span>
            {version ? readStr(version, ["timestamp"]) || "—" : "—"}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
