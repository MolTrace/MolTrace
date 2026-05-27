"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, API_BASE, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Activity, AlertTriangle, Download, FileCog, ListChecks, Settings2 } from "lucide-react"
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
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { parseReleaseHealthDiagnostics } from "@/src/lib/admin/release-health"
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

function readinessBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === "passed" || s === "candidate_ready_for_manual_promotion" || s === "eligible_for_manual_promotion") {
    return "border-success/50 text-success"
  }
  if (s === "review_required") return "border-warning/50 text-warning"
  if (s === "failed" || s === "blocked" || s === "blocked_no_fixtures") {
    return "border-destructive/50 text-destructive"
  }
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

function formatDiagnosticValue(value: unknown): string {
  if (value == null) return "—"
  if (typeof value === "string") return value.trim() || "—"
  if (typeof value === "boolean" || typeof value === "number") return String(value)
  if (Array.isArray(value) || isRecord(value)) return JSON.stringify(value)
  return "—"
}

function csvEscape(value: unknown): string {
  const raw = formatDiagnosticValue(value)
  return /[",\n\r]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw
}

function rawFidFixtureRowsToCsv(rows: Record<string, unknown>[]): string {
  const preferredColumns = [
    "fixture_id",
    "archive",
    "archive_sha256",
    "archive_size_bytes",
    "nucleus",
    "legacy_peak_count",
    "prompt_peak_count",
    "reference_peak_count",
    "safe_to_activate",
    "activation_readiness_status",
    "validation_visibility",
  ]
  const extraColumns = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row)).filter((key) => !preferredColumns.includes(key))),
  ).sort()
  const columns = [...preferredColumns, ...extraColumns]
  return [columns.join(","), ...rows.map((row) => columns.map((column) => csvEscape(row[column])).join(","))].join(
    "\n",
  )
}

function downloadTextFile(filename: string, contents: string, mimeType: string) {
  if (typeof window === "undefined" || typeof document === "undefined") return
  const createObjectUrl = window.URL?.createObjectURL
  const revokeObjectUrl = window.URL?.revokeObjectURL
  if (!createObjectUrl) return

  const blob = new Blob([contents], { type: mimeType })
  const url = createObjectUrl.call(window.URL, blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.style.display = "none"
  document.body.appendChild(anchor)
  anchor.click()
  if (anchor.parentNode) anchor.parentNode.removeChild(anchor)
  if (revokeObjectUrl) revokeObjectUrl.call(window.URL, url)
}

export function DeploymentSettingsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [envCheck, setEnvCheck] = useState<Record<string, unknown> | null>(null)
  const [version, setVersion] = useState<Record<string, unknown> | null>(null)
  const [deps, setDeps] = useState<Record<string, unknown>[]>([])
  const [releaseHealth, setReleaseHealth] = useState<Record<string, unknown> | null>(null)
  const [fixtureReport, setFixtureReport] = useState<Record<string, unknown> | null>(null)

  const [errEnv, setErrEnv] = useState("")
  const [errVersion, setErrVersion] = useState("")
  const [errDeps, setErrDeps] = useState("")
  const [errReleaseHealth, setErrReleaseHealth] = useState("")
  const [errFixtureReport, setErrFixtureReport] = useState("")
  const [fixtureReportLoading, setFixtureReportLoading] = useState(false)

  const [origin, setOrigin] = useState("")

  useEffect(() => {
    if (typeof window !== "undefined") setOrigin(window.location.origin)
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setErrEnv("")
    setErrVersion("")
    setErrDeps("")
    setErrReleaseHealth("")

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

    try {
      const r = await apiFetch<Record<string, unknown>>("/admin/release-health", { method: "GET" })
      setReleaseHealth(r ?? null)
    } catch (err) {
      setErrReleaseHealth(formatErr(err, "Could not load /admin/release-health."))
      setReleaseHealth(null)
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const runFixtureReport = useCallback(async () => {
    setFixtureReportLoading(true)
    setErrFixtureReport("")
    try {
      const report = await apiFetch<Record<string, unknown>>(
        "/admin/raw-fid/prompt-sidecar/fixture-report?limit=1&include_varian=false",
        { method: "GET" },
      )
      setFixtureReport(report ?? null)
    } catch (err) {
      setErrFixtureReport(formatErr(err, "Could not run the raw FID sidecar fixture report."))
      setFixtureReport(null)
    } finally {
      setFixtureReportLoading(false)
    }
  }, [])

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
  const releaseHealthDiagnostics = useMemo(() => parseReleaseHealthDiagnostics(releaseHealth), [releaseHealth])
  const rawFidPromptSmoke = releaseHealthDiagnostics.rawFidPromptSidecarSmoke
  const manualPromotionGate = rawFidPromptSmoke?.manualPromotionGate ?? null
  const manualPromotionDesign = rawFidPromptSmoke?.manualPromotionDesign ?? null
  const provenanceChecksumArtifact = rawFidPromptSmoke?.provenanceChecksumArtifact ?? null
  const provenanceChecksumFiles = provenanceChecksumArtifact?.files ?? []
  const shadowComparisonArtifact = rawFidPromptSmoke?.shadowComparisonArtifact ?? null
  const shadowComparisonFiles = shadowComparisonArtifact?.files ?? []
  const releaseReadinessArtifact = rawFidPromptSmoke?.releaseReadinessArtifact ?? null
  const releaseReadinessFiles = releaseReadinessArtifact?.files ?? []
  const fixtureRows =
    fixtureReport && Array.isArray(fixtureReport.rows) ? fixtureReport.rows.filter(isRecord) : []
  const fixtureSmoke =
    fixtureReport && isRecord(fixtureReport.reporting_only_smoke) ? fixtureReport.reporting_only_smoke : null
  const fixturePromotionGate =
    fixtureReport && isRecord(fixtureReport.promotion_gate) ? fixtureReport.promotion_gate : null
  const fixturePromotionFailures =
    fixturePromotionGate && Array.isArray(fixturePromotionGate.failures)
      ? fixturePromotionGate.failures.filter((failure): failure is string => typeof failure === "string")
      : []
  const activationReadiness =
    fixtureReport && isRecord(fixtureReport.activation_readiness)
      ? fixtureReport.activation_readiness
      : null
  const activationReadinessGates =
    activationReadiness && Array.isArray(activationReadiness.gates)
      ? activationReadiness.gates.filter(isRecord)
      : []
  const fixtureProvenance =
    fixtureReport && isRecord(fixtureReport.provenance) ? fixtureReport.provenance : null
  const fixtureProvenanceParameters =
    fixtureProvenance && isRecord(fixtureProvenance.parameters) ? fixtureProvenance.parameters : null
  const fixtureShadowComparison =
    fixtureReport && isRecord(fixtureReport.shadow_comparison_summary)
      ? fixtureReport.shadow_comparison_summary
      : null
  const fixtureShadowRuntimeEffect =
    fixtureShadowComparison && isRecord(fixtureShadowComparison.runtime_effect)
      ? fixtureShadowComparison.runtime_effect
      : null
  const fixtureShadowReviewIds =
    fixtureShadowComparison && Array.isArray(fixtureShadowComparison.review_fixture_ids)
      ? fixtureShadowComparison.review_fixture_ids.filter((fixtureId): fixtureId is string => typeof fixtureId === "string")
      : []

  const frontendBuild =
    typeof process.env.NEXT_PUBLIC_APP_BUILD !== "undefined"
      ? process.env.NEXT_PUBLIC_APP_BUILD
      : typeof process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA !== "undefined"
        ? process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA
        : ""

  const hasPartialErr = Boolean(errEnv || errVersion || errDeps || errReleaseHealth)
  const allFailed = !loading && errEnv && errVersion && errDeps

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-slate)" }}
          >
            MolTrace · Settings · Deployment
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">Deployment Settings</h1>
            <InfoTooltip content={DEPLOYMENT_SETTINGS_TOOLTIP} label="About Deployment Settings" />
          </div>
          <p className="text-sm text-muted-foreground">
            Environment and dependency snapshot from the backend (admin-capable routes).
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void reload()}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>

      {!loading && allFailed ? (
        <AlertCard
          variant="error"
          icon={ServerOff}
          title="Backend unavailable"
          description="Deployment data is not reachable. Verify you're signed in as an administrator and try again."
        />
      ) : null}

      {!allFailed && hasPartialErr ? (
        <AlertCard variant="error" title="Partial load">
          <div className="space-y-1 text-xs text-foreground/90">
            {errEnv ? <p>Environment check: {errEnv}</p> : null}
            {errVersion ? <p>Version info: {errVersion}</p> : null}
            {errDeps ? <p>Dependency status: {errDeps}</p> : null}
            {errReleaseHealth ? <p>Release health: {errReleaseHealth}</p> : null}
          </div>
        </AlertCard>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">environment</CardTitle>
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

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">frontend URL</CardTitle>
            <CardDescription>Browser origin</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <p className="break-all font-mono text-xs">{origin || "—"}</p>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">backend status</CardTitle>
            <CardDescription>openapi.json reachability</CardDescription>
          </CardHeader>
          <CardContent>
            <BackendStatusIndicator />
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">API base URL</CardTitle>
            <CardDescription>Next.js API proxy base</CardDescription>
          </CardHeader>
          <CardContent className="break-all font-mono text-xs">{API_BASE}</CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">OpenAPI availability</CardTitle>
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

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">backend version</CardTitle>
            <CardDescription>Backend service build identifier.</CardDescription>
          </CardHeader>
          <CardContent className="font-mono text-xs">
            {loading ? "…" : version ? readStr(version, ["backend_version"]) || "—" : "—"}
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">frontend build</CardTitle>
            <CardDescription>NEXT_PUBLIC_APP_BUILD or NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA</CardDescription>
          </CardHeader>
          <CardContent className="font-mono text-xs">
            {frontendBuild ? frontendBuild : <span className="text-muted-foreground">Not configured</span>}
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">database status</CardTitle>
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

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">storage backend</CardTitle>
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

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">job backend</CardTitle>
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

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-slate)" }}
        >
          <CardHeader className="gap-1 pt-5 pb-2">
            <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">worker status</CardTitle>
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

      <ModuleCard
        accent="slate"
        eyebrow="Variables"
        title="Required variables"
        icon={ListChecks}
        description="required_variables_present · missing_variables — secret values are never returned by the API."
      >
        <div className="space-y-3 text-sm">
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="cyan"
        eyebrow="Raw FID Guardrail"
        title="Prompt 1/2 sidecar smoke"
        icon={FileCog}
        description="Read-only release diagnostic for the nmrglue FID reader and phase/baseline sidecar. It does not activate the active SpectraCheck raw-FID or processed-spectrum pipelines."
      >
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : errReleaseHealth ? (
          <p className="text-sm text-destructive">{errReleaseHealth}</p>
        ) : rawFidPromptSmoke ? (
          <div className="space-y-3 text-xs">
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="font-normal">
                status {rawFidPromptSmoke.status || "unknown"}
              </Badge>
              <Badge variant="outline" className="font-normal">
                active visible pipeline {rawFidPromptSmoke.activeVisiblePipeline || "—"}
              </Badge>
              <Badge variant="outline" className="font-normal">
                prompt active {String(rawFidPromptSmoke.promptPipelineActive)}
              </Badge>
            </div>
            <dl className="grid gap-2 md:grid-cols-2">
              <div>
                <dt className="font-medium text-muted-foreground">policy</dt>
                <dd className="font-mono break-all">{rawFidPromptSmoke.policy || "—"}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted-foreground">failure scope</dt>
                <dd className="font-mono break-all">{rawFidPromptSmoke.failureScope || "—"}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted-foreground">admin report endpoint</dt>
                <dd className="font-mono break-all">{rawFidPromptSmoke.adminReportEndpoint || "—"}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted-foreground">CI smoke command</dt>
                <dd className="font-mono break-all">{rawFidPromptSmoke.ciCommand || "—"}</dd>
              </div>
            </dl>
            {Object.keys(rawFidPromptSmoke.runtimeEffect).length > 0 ? (
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="mb-2 font-medium text-muted-foreground">runtime effect</p>
                <dl className="grid gap-2 md:grid-cols-3">
                  {Object.entries(rawFidPromptSmoke.runtimeEffect).map(([key, val]) => (
                    <div key={key}>
                      <dt className="font-mono text-[10px] text-muted-foreground">{key}</dt>
                      <dd className="font-mono text-[10px]">{formatDiagnosticValue(val)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : null}
            {manualPromotionGate ? (
              <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-muted-foreground">manual promotion gate</p>
                  <Badge
                    variant="outline"
                    className={`font-normal ${readinessBadgeClass(manualPromotionGate.status)}`}
                  >
                    status {manualPromotionGate.status || "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    runtime activation allowed {String(manualPromotionGate.runtimeActivationAllowed)}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    manual code change {String(manualPromotionGate.requiresManualCodeChange)}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  CI/admin diagnostic only. This gate publishes evidence for review and cannot switch the
                  SpectraCheck runtime path.
                </p>
                <dl className="grid gap-2 md:grid-cols-2">
                  <div>
                    <dt className="font-medium text-muted-foreground">policy</dt>
                    <dd className="font-mono break-all">{manualPromotionGate.policy || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">visibility</dt>
                    <dd className="font-mono break-all">{manualPromotionGate.visibility || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI artifact</dt>
                    <dd className="font-mono break-all">{manualPromotionGate.ciArtifact || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI step</dt>
                    <dd className="font-mono break-all">{manualPromotionGate.ciStep || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">CI promotion command</dt>
                    <dd className="font-mono break-all">{manualPromotionGate.ciCommand || "—"}</dd>
                  </div>
                </dl>
              </div>
            ) : null}
            {manualPromotionDesign ? (
              <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-muted-foreground">manual promotion design</p>
                  <Badge
                    variant="outline"
                    className={`font-normal ${readinessBadgeClass(manualPromotionDesign.status)}`}
                  >
                    status {manualPromotionDesign.status || "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    runtime activation allowed {String(manualPromotionDesign.runtimeActivationAllowed)}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Design-document status for the Prompt 1/2 promotion path. It documents required gates and
                  rollback only; it does not activate or alter the SpectraCheck runtime.
                </p>
                <dl className="grid gap-2 md:grid-cols-2">
                  <div>
                    <dt className="font-medium text-muted-foreground">policy</dt>
                    <dd className="font-mono break-all">{manualPromotionDesign.policy || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">visibility</dt>
                    <dd className="font-mono break-all">{manualPromotionDesign.visibility || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">doc</dt>
                    <dd className="font-mono break-all">
                      {manualPromotionDesign.docPath || manualPromotionDesign.docTitle || "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">rollback mode</dt>
                    <dd className="font-mono break-all">{manualPromotionDesign.rollbackMode || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">required guardrail command</dt>
                    <dd className="font-mono break-all">{manualPromotionDesign.requiredGuardrailCommand || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">required gates</dt>
                    <dd className="font-mono break-all">
                      {manualPromotionDesign.requiredGates.length > 0
                        ? manualPromotionDesign.requiredGates.join(", ")
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">promotion stages</dt>
                    <dd className="font-mono break-all">
                      {manualPromotionDesign.promotionStages.length > 0
                        ? manualPromotionDesign.promotionStages.join(", ")
                        : "—"}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
            {provenanceChecksumArtifact ? (
              <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-muted-foreground">provenance checksum artifact</p>
                  <Badge
                    variant="outline"
                    className={`font-normal ${readinessBadgeClass(provenanceChecksumArtifact.status)}`}
                  >
                    status {provenanceChecksumArtifact.status || "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    runtime activation allowed {String(provenanceChecksumArtifact.runtimeActivationAllowed)}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  CI emits deterministic sidecar checksums for review. These files are audit evidence only and do
                  not activate the Prompt 1/2 runtime path.
                </p>
                <dl className="grid gap-2 md:grid-cols-2">
                  <div>
                    <dt className="font-medium text-muted-foreground">policy</dt>
                    <dd className="font-mono break-all">{provenanceChecksumArtifact.policy || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">visibility</dt>
                    <dd className="font-mono break-all">{provenanceChecksumArtifact.visibility || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI artifact</dt>
                    <dd className="font-mono break-all">{provenanceChecksumArtifact.ciArtifact || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI step</dt>
                    <dd className="font-mono break-all">{provenanceChecksumArtifact.ciStep || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">output directory</dt>
                    <dd className="font-mono break-all">{provenanceChecksumArtifact.outputDir || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">CI checksum command</dt>
                    <dd className="font-mono break-all">{provenanceChecksumArtifact.ciCommand || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">artifact files</dt>
                    <dd className="font-mono break-all">
                      {provenanceChecksumFiles.length > 0 ? provenanceChecksumFiles.join(", ") : "—"}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
            {shadowComparisonArtifact ? (
              <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-muted-foreground">shadow comparison artifact</p>
                  <Badge
                    variant="outline"
                    className={`font-normal ${readinessBadgeClass(shadowComparisonArtifact.status)}`}
                  >
                    status {shadowComparisonArtifact.status || "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    runtime activation allowed {String(shadowComparisonArtifact.runtimeActivationAllowed)}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  CI emits a compact shadow comparison summary for release review. It is read-only and does
                  not alter the visible legacy raw-FID or processed-spectrum pipelines.
                </p>
                <dl className="grid gap-2 md:grid-cols-2">
                  <div>
                    <dt className="font-medium text-muted-foreground">policy</dt>
                    <dd className="font-mono break-all">{shadowComparisonArtifact.policy || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">visibility</dt>
                    <dd className="font-mono break-all">{shadowComparisonArtifact.visibility || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI artifact</dt>
                    <dd className="font-mono break-all">{shadowComparisonArtifact.ciArtifact || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI step</dt>
                    <dd className="font-mono break-all">{shadowComparisonArtifact.ciStep || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">output directory</dt>
                    <dd className="font-mono break-all">{shadowComparisonArtifact.outputDir || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">CI shadow command</dt>
                    <dd className="font-mono break-all">{shadowComparisonArtifact.ciCommand || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">artifact files</dt>
                    <dd className="font-mono break-all">
                      {shadowComparisonFiles.length > 0 ? shadowComparisonFiles.join(", ") : "—"}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
            {releaseReadinessArtifact ? (
              <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-muted-foreground">release readiness artifact</p>
                  <Badge
                    variant="outline"
                    className={`font-normal ${readinessBadgeClass(releaseReadinessArtifact.status)}`}
                  >
                    status {releaseReadinessArtifact.status || "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    runtime activation allowed {String(releaseReadinessArtifact.runtimeActivationAllowed)}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  CI emits a single markdown readiness summary combining the manual-promotion gate,
                  provenance hashes, and shadow comparison status. It is read-only and cannot activate
                  Prompt 1/2.
                </p>
                <dl className="grid gap-2 md:grid-cols-2">
                  <div>
                    <dt className="font-medium text-muted-foreground">policy</dt>
                    <dd className="font-mono break-all">{releaseReadinessArtifact.policy || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">visibility</dt>
                    <dd className="font-mono break-all">{releaseReadinessArtifact.visibility || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI artifact</dt>
                    <dd className="font-mono break-all">{releaseReadinessArtifact.ciArtifact || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">CI step</dt>
                    <dd className="font-mono break-all">{releaseReadinessArtifact.ciStep || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">output directory</dt>
                    <dd className="font-mono break-all">{releaseReadinessArtifact.outputDir || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">CI readiness command</dt>
                    <dd className="font-mono break-all">{releaseReadinessArtifact.ciCommand || "—"}</dd>
                  </div>
                  <div className="md:col-span-2">
                    <dt className="font-medium text-muted-foreground">artifact files</dt>
                    <dd className="font-mono break-all">
                      {releaseReadinessFiles.length > 0 ? releaseReadinessFiles.join(", ") : "—"}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
            <div className="flex flex-wrap items-center gap-3 border-t pt-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={fixtureReportLoading}
                onClick={() => void runFixtureReport()}
              >
                <Activity className="h-4 w-4" aria-hidden />
                {fixtureReportLoading ? "Running…" : "Run fixture smoke report"}
              </Button>
              <p className="text-[11px] text-muted-foreground">
                Runs one Bruker fixture, excludes Varian, and reports only diagnostic rows.
              </p>
            </div>
            {errFixtureReport ? <p className="text-sm text-destructive">{errFixtureReport}</p> : null}
            {fixtureReport ? (
              <div className="space-y-3 rounded-md border bg-background/60 p-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="font-normal">
                    report {readStr(fixtureReport, ["version"]) || "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    fixtures {readStr(fixtureReport, ["fixture_count"]) || "0"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    smoke passed {fixtureSmoke ? readStr(fixtureSmoke, ["passed"]) || "false" : "unknown"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    prompt active {readStr(fixtureReport, ["prompt_pipeline_active"]) || "false"}
                  </Badge>
                </div>
                <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 p-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      downloadTextFile(
                        "raw-fid-prompt-sidecar-report.json",
                        JSON.stringify(fixtureReport, null, 2),
                        "application/json;charset=utf-8",
                      )
                    }
                  >
                    <Download className="h-4 w-4" aria-hidden />
                    Download JSON report
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={fixtureRows.length === 0}
                    onClick={() =>
                      downloadTextFile(
                        "raw-fid-prompt-sidecar-fixture-rows.csv",
                        rawFidFixtureRowsToCsv(fixtureRows),
                        "text/csv;charset=utf-8",
                      )
                    }
                  >
                    <Download className="h-4 w-4" aria-hidden />
                    Download CSV rows
                  </Button>
                  <p className="text-[11px] text-muted-foreground">
                    Local export of this read-only diagnostic response; no runtime pipeline is changed.
                  </p>
                </div>
                {fixtureProvenance ? (
                  <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-normal">
                        provenance {readStr(fixtureProvenance, ["version"]) || "unknown"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        fixtures {readStr(fixtureProvenance, ["fixture_count"]) || "0"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        rows {readStr(fixtureProvenance, ["row_count"]) || "0"}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Checksums identify the exact fixture set, stable row fingerprint, and exported report payload.
                    </p>
                    <dl className="grid gap-2 md:grid-cols-2">
                      <div>
                        <dt className="font-medium text-muted-foreground">fixture identity SHA-256</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureProvenance, ["fixture_identity_sha256"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">stable row fingerprint SHA-256</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureProvenance, ["row_fingerprint_sha256"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">report payload SHA-256</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureProvenance, ["report_payload_sha256"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">shadow comparison SHA-256</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureProvenance, ["shadow_comparison_sha256"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">runtime effect SHA-256</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureProvenance, ["runtime_effect_sha256"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">route policy</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureProvenance, ["route_policy"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">parameters</dt>
                        <dd className="font-mono break-all">
                          {formatDiagnosticValue(fixtureProvenanceParameters)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                ) : null}
                {fixtureShadowComparison ? (
                  <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-normal">
                        shadow comparison {readStr(fixtureShadowComparison, ["version"]) || "unknown"}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={`font-normal ${readinessBadgeClass(readStr(fixtureShadowComparison, ["status"]))}`}
                      >
                        status {readStr(fixtureShadowComparison, ["status"]) || "unknown"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        runtime activation allowed {readStr(fixtureShadowComparison, ["runtime_activation_allowed"]) || "false"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        fixtures {readStr(fixtureShadowComparison, ["fixture_count"]) || "0"}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Compact read-only comparison of Prompt 1/2 fixture behavior against references. It is
                      review evidence only and cannot switch the active SpectraCheck pipeline.
                    </p>
                    <dl className="grid gap-2 md:grid-cols-2">
                      <div>
                        <dt className="font-medium text-muted-foreground">policy</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["reporting_policy"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">decision guidance</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["decision_guidance"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">prompt sidecar available</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["prompt_sidecar_available"]) || "0"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">reference rows</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["reference_rows"]) || "0"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">peak-count review rows</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["prompt_peak_count_review_required"]) || "0"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">ppm review rows</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["prompt_reference_ppm_review_required"]) || "0"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">max prompt/reference peak delta</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["max_prompt_reference_peak_count_delta"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">max prompt/reference ppm error</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["max_prompt_reference_ppm_error"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">max runtime ms</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixtureShadowComparison, ["max_prompt_runtime_ms"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">activation status counts</dt>
                        <dd className="font-mono break-all">
                          {formatDiagnosticValue(fixtureShadowComparison.activation_status_counts)}
                        </dd>
                      </div>
                      <div className="md:col-span-2">
                        <dt className="font-medium text-muted-foreground">review fixture IDs</dt>
                        <dd className="font-mono break-all">
                          {fixtureShadowReviewIds.length > 0 ? fixtureShadowReviewIds.join(", ") : "—"}
                        </dd>
                      </div>
                      <div className="md:col-span-2">
                        <dt className="font-medium text-muted-foreground">runtime effect</dt>
                        <dd className="font-mono break-all">
                          {formatDiagnosticValue(fixtureShadowRuntimeEffect)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                ) : null}
                <dl className="grid gap-2 md:grid-cols-2">
                  <div>
                    <dt className="font-medium text-muted-foreground">route policy</dt>
                    <dd className="font-mono break-all">{readStr(fixtureReport, ["route_policy"]) || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-muted-foreground">activation policy</dt>
                    <dd className="font-mono break-all">{readStr(fixtureReport, ["activation_policy"]) || "—"}</dd>
                  </div>
                </dl>
                {fixturePromotionGate ? (
                  <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-normal">
                        promotion gate {readStr(fixturePromotionGate, ["version"]) || "unknown"}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={`font-normal ${readinessBadgeClass(readStr(fixturePromotionGate, ["status"]))}`}
                      >
                        status {readStr(fixturePromotionGate, ["status"]) || "unknown"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        eligible {readStr(fixturePromotionGate, ["eligible_for_manual_promotion"]) || "false"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        failures {readStr(fixturePromotionGate, ["failure_count"]) || "0"}
                      </Badge>
                    </div>
                    <dl className="grid gap-2 md:grid-cols-2">
                      <div>
                        <dt className="font-medium text-muted-foreground">visibility</dt>
                        <dd className="font-mono break-all">{readStr(fixturePromotionGate, ["visibility"]) || "—"}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">active visible pipeline</dt>
                        <dd className="font-mono break-all">
                          {readStr(fixturePromotionGate, ["active_visible_pipeline"]) || "—"}
                        </dd>
                      </div>
                      <div className="md:col-span-2">
                        <dt className="font-medium text-muted-foreground">CI promotion command</dt>
                        <dd className="font-mono break-all">{readStr(fixturePromotionGate, ["ci_command"]) || "—"}</dd>
                      </div>
                    </dl>
                    {fixturePromotionFailures.length > 0 ? (
                      <ul className="list-inside list-disc space-y-1 font-mono text-[10px] text-muted-foreground">
                        {fixturePromotionFailures.slice(0, 6).map((failure) => (
                          <li key={failure}>{failure}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-[11px] text-muted-foreground">No promotion-gate failures returned.</p>
                    )}
                  </div>
                ) : null}
                {activationReadiness ? (
                  <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-normal">
                        readiness report {readStr(activationReadiness, ["version"]) || "unknown"}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={`font-normal ${readinessBadgeClass(
                          readStr(activationReadiness, ["overall_status"]),
                        )}`}
                      >
                        readiness {readStr(activationReadiness, ["overall_status"]) || "unknown"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        activation allowed {readStr(activationReadiness, ["activation_allowed"]) || "false"}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        gates {readStr(activationReadiness, ["gate_count"]) || "0"}
                      </Badge>
                    </div>
                    <dl className="grid gap-2 md:grid-cols-2">
                      <div>
                        <dt className="font-medium text-muted-foreground">visibility</dt>
                        <dd className="font-mono break-all">
                          {readStr(activationReadiness, ["visibility"]) || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-muted-foreground">promotion policy</dt>
                        <dd className="font-mono break-all">
                          {readStr(activationReadiness, ["activation_policy"]) || "—"}
                        </dd>
                      </div>
                    </dl>
                    {activationReadinessGates.length > 0 ? (
                      <div className="overflow-x-auto rounded-md border bg-background">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="text-xs">gate</TableHead>
                              <TableHead className="text-xs">status</TableHead>
                              <TableHead className="text-xs">target</TableHead>
                              <TableHead className="text-xs">passed</TableHead>
                              <TableHead className="text-xs">review</TableHead>
                              <TableHead className="text-xs">failed</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {activationReadinessGates.map((gate, index) => {
                              const gateStatus = readStr(gate, ["status"])
                              return (
                                <TableRow key={`${readStr(gate, ["name"]) || "gate"}-${index}`}>
                                  <TableCell className="font-mono text-[10px]">
                                    {readStr(gate, ["name"]) || "—"}
                                  </TableCell>
                                  <TableCell className="font-mono text-[10px]">
                                    <Badge
                                      variant="outline"
                                      className={`font-normal ${readinessBadgeClass(gateStatus)}`}
                                    >
                                      {gateStatus || "unknown"}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="min-w-64 text-[10px] text-muted-foreground">
                                    {readStr(gate, ["target"]) || "—"}
                                  </TableCell>
                                  <TableCell className="font-mono text-[10px]">
                                    {readStr(gate, ["passed"]) || "0"}
                                  </TableCell>
                                  <TableCell className="font-mono text-[10px]">
                                    {readStr(gate, ["review_required"]) || "0"}
                                  </TableCell>
                                  <TableCell className="font-mono text-[10px]">
                                    {readStr(gate, ["failed"]) || "0"}
                                  </TableCell>
                                </TableRow>
                              )
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">No activation-readiness gates returned.</p>
                    )}
                  </div>
                ) : null}
                {fixtureRows.length > 0 ? (
                  <div className="overflow-x-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">fixture</TableHead>
                          <TableHead className="text-xs">nucleus</TableHead>
                          <TableHead className="text-xs">legacy peaks</TableHead>
                          <TableHead className="text-xs">prompt peaks</TableHead>
                          <TableHead className="text-xs">reference peaks</TableHead>
                          <TableHead className="text-xs">readiness</TableHead>
                          <TableHead className="text-xs">visibility</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {fixtureRows.slice(0, 3).map((row, index) => (
                          <TableRow key={`${readStr(row, ["fixture_id"]) || "fixture"}-${index}`}>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["fixture_id"]) || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["nucleus"]) || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["legacy_peak_count"]) || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["prompt_peak_count"]) || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["reference_peak_count"]) || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["activation_readiness_status"]) || "—"}
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">
                              {readStr(row, ["validation_visibility"]) || "—"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No fixture rows returned.</p>
                )}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Raw FID sidecar smoke is not reported by this backend.</p>
        )}
      </ModuleCard>

      <ModuleCard
        accent={unsafeVars.length > 0 ? "amber" : "slate"}
        eyebrow="Warnings"
        title="Unsafe config warnings"
        icon={AlertTriangle}
        description="unsafe_variables — configuration keys flagged as unsafe for production."
      >
        <div>
          {unsafeVars.length === 0 ? (
            <p className="text-sm text-muted-foreground">None listed.</p>
          ) : (
            <ul className="list-inside list-disc font-mono text-xs">
              {(unsafeVars as unknown[]).filter((x): x is string => typeof x === "string").map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          )}
        </div>
      </ModuleCard>

      {envCheck && Array.isArray(envCheck.warnings) && envCheck.warnings.length > 0 ? (
        <ModuleCard
          accent="amber"
          eyebrow="Warnings"
          title="Warnings"
          icon={AlertTriangle}
        >
          <ul className="list-inside list-disc text-xs">
            {(envCheck.warnings as unknown[])
              .filter((x): x is string => typeof x === "string")
              .map((w, i) => (
                <li key={`${i}-${w.slice(0, 20)}`}>{w}</li>
              ))}
          </ul>
        </ModuleCard>
      ) : null}

      <ModuleCard
        accent="slate"
        eyebrow="Public Vars"
        title="public_variables"
        icon={Settings2}
        description="Non-secret fields returned under public_variables. Values may be truncated; SECRET_LIKE_VARIABLES_PRESENT lists names only."
      >
        <div>
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Dependencies"
        title="Dependency checks"
        icon={Activity}
        description="Health of every external service the platform connects to."
      >
        <div>
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Version"
        title="Version payload"
        icon={FileCog}
        description="Full version metadata: API, build hash, branch, build time."
      >
        <div className="space-y-2 font-mono text-xs">
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
        </div>
      </ModuleCard>
    </div>
  )
}
