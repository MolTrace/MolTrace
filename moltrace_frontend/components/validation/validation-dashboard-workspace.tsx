"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  FlaskConical,
  Layers,
  ServerOff,
  Eye,
} from "lucide-react"

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

function extractRows(data: unknown, arrayKeys: string[]): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of arrayKeys) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function summarizeUnknown(v: unknown, maxLen = 200): string {
  if (v == null || v === "") return "—"
  if (typeof v === "string") return v.trim() || "—"
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  if (Array.isArray(v)) {
    const joined = v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(", ")
    return joined.length > maxLen ? `${joined.slice(0, maxLen)}…` : joined || "—"
  }
  if (isRecord(v)) {
    const s = JSON.stringify(v)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return "—"
}

function extractDriftRows(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of ["drift_alerts", "alerts", "items", "results", "rows"]) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

/** Normalize status for grouping without asserting scientific outcome. */
function normalizeRunStatus(raw: Record<string, unknown>): string {
  return readStr(raw, ["status", "run_status", "state", "validation_status"]).toLowerCase().replace(/-/g, "_")
}

function isPassedLike(status: string): boolean {
  return (
    status === "passed" ||
    status === "pass" ||
    status === "succeeded" ||
    status === "success" ||
    status === "completed" ||
    status === "ok"
  )
}

function isFailedOrReviewLike(status: string): boolean {
  return (
    status === "failed" ||
    status === "fail" ||
    status === "error" ||
    status === "requires_review" ||
    status === "needs_review" ||
    status === "blocked" ||
    status === "review_required"
  )
}

function countDriftOpen(rows: Record<string, unknown>[]): number {
  const terminal = new Set(["resolved", "closed", "dismissed"])
  return rows.filter((r) => {
    const st = readStr(r, ["status", "alert_status", "state"]).toLowerCase()
    if (!st) return true
    return !terminal.has(st)
  }).length
}

function normalizeDriftStatus(row: Record<string, unknown>): string {
  return readStr(row, ["status", "alert_status", "state"]).toLowerCase()
}

function isDriftResolvedStatus(st: string): boolean {
  return st === "resolved" || st === "closed" || st === "dismissed"
}

function readDriftAlertId(row: Record<string, unknown>): string {
  return readStr(row, ["id", "alert_id"])
}

function readMethodModelLabel(row: Record<string, unknown>): string {
  const primary = readStr(row, ["method", "method_name", "model", "model_name", "model_id"])
  if (primary) return primary
  const mid = readStr(row, ["method_id"])
  const vid = readStr(row, ["model_version_id"])
  const parts: string[] = []
  if (mid) parts.push(`method ${mid}`)
  if (vid) parts.push(`model ${vid}`)
  return parts.length ? parts.join(" · ") : "—"
}

function severityBadgeVariant(severityRaw: string): "destructive" | "outline" {
  const s = severityRaw.toLowerCase()
  if (s === "critical" || s === "error") return "destructive"
  return "outline"
}

function readModelHealthCounts(raw: unknown): { active: number | null; experimental: number | null } {
  if (raw == null) return { active: null, experimental: null }
  if (Array.isArray(raw)) {
    let active = 0
    let experimental = 0
    for (const item of raw) {
      if (!isRecord(item)) continue
      const role = readStr(item, ["lifecycle", "tier", "kind", "category", "phase"]).toLowerCase()
      const exp =
        readStr(item, ["experimental", "is_experimental", "isExperimental"]).toLowerCase() === "true" ||
        role.includes("experimental")
      if (exp) experimental += 1
      else active += 1
    }
    return { active: raw.length ? active : 0, experimental: raw.length ? experimental : 0 }
  }
  if (!isRecord(raw)) return { active: null, experimental: null }
  const an = readStr(raw, ["active_methods", "activeMethods", "active_method_count", "active_count"])
  const en = readStr(raw, ["experimental_methods", "experimentalMethods", "experimental_count"])
  const ac =
    typeof raw.active_method_count === "number"
      ? raw.active_method_count
      : typeof raw.activeMethods === "number"
        ? raw.activeMethods
        : an
          ? Number(an)
          : null
  const ec =
    typeof raw.experimental_method_count === "number"
      ? raw.experimental_method_count
      : typeof raw.experimentalMethods === "number"
        ? raw.experimentalMethods
        : en
          ? Number(en)
          : null
  const activeNum = ac != null && Number.isFinite(ac) ? Math.max(0, Math.floor(ac)) : null
  const expNum = ec != null && Number.isFinite(ec) ? Math.max(0, Math.floor(ec)) : null
  if (activeNum != null || expNum != null) return { active: activeNum, experimental: expNum }
  const nested = raw.methods ?? raw.items
  if (Array.isArray(nested)) return readModelHealthCounts(nested)
  return { active: null, experimental: null }
}

export function ValidationDashboardWorkspace() {
  const [validationRuns, setValidationRuns] = useState<Record<string, unknown>[]>([])
  const [benchmarks, setBenchmarks] = useState<Record<string, unknown>[]>([])
  const [modelHealthRaw, setModelHealthRaw] = useState<unknown>(null)
  const [driftRows, setDriftRows] = useState<Record<string, unknown>[]>([])
  const [methodComparisons, setMethodComparisons] = useState<Record<string, unknown>[]>([])

  const [errRuns, setErrRuns] = useState("")
  const [errBenchmarks, setErrBenchmarks] = useState("")
  const [errHealth, setErrHealth] = useState("")
  const [errDrift, setErrDrift] = useState("")
  const [errComparisons, setErrComparisons] = useState("")

  const [driftActionId, setDriftActionId] = useState<string | null>(null)
  const [driftActionErr, setDriftActionErr] = useState<Record<string, string>>({})

  const [loading, setLoading] = useState(true)
  const refreshDrift = useCallback(async () => {
    try {
      const data = await apiFetch<unknown>("/model-health/drift-alerts", { method: "GET" })
      setDriftRows(extractDriftRows(data))
      setErrDrift("")
    } catch (e) {
      setErrDrift(formatErr(e, "Could not load drift alerts."))
      setDriftRows([])
    }
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setErrRuns("")
    setErrBenchmarks("")
    setErrHealth("")
    setErrDrift("")
    setErrComparisons("")

    const runList = async (
      path: string,
      setRows: (r: Record<string, unknown>[]) => void,
      setErr: (s: string) => void,
      keys: string[],
    ) => {
      try {
        const data = await apiFetch<unknown>(path, { method: "GET" })
        setRows(extractRows(data, keys))
      } catch (e) {
        setErr(formatErr(e, `Could not load ${path}.`))
        setRows([])
      }
    }

    await Promise.all([
      runList("/validation-runs", setValidationRuns, setErrRuns, [
        "validation_runs",
        "runs",
        "items",
        "results",
        "data",
        "rows",
      ]),
      runList("/benchmark-datasets", setBenchmarks, setErrBenchmarks, [
        "benchmark_datasets",
        "datasets",
        "items",
        "results",
        "data",
        "rows",
      ]),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/model-health", { method: "GET" })
          setModelHealthRaw(data)
        } catch (e) {
          setErrHealth(formatErr(e, "Could not load /model-health."))
          setModelHealthRaw(null)
        }
      })(),
      refreshDrift(),
      runList("/method-comparisons", setMethodComparisons, setErrComparisons, [
        "comparisons",
        "method_comparisons",
        "items",
        "results",
        "data",
        "rows",
      ]),
    ])

    setLoading(false)
  }, [refreshDrift])

  useEffect(() => {
    void reload()
  }, [reload])

  const healthCounts = useMemo(() => readModelHealthCounts(modelHealthRaw), [modelHealthRaw])

  const runStats = useMemo(() => {
    let passed = 0
    let failedReview = 0
    for (const r of validationRuns) {
      const st = normalizeRunStatus(r)
      if (!st) continue
      if (isPassedLike(st)) passed += 1
      else if (isFailedOrReviewLike(st)) failedReview += 1
    }
    return {
      total: validationRuns.length,
      passed,
      failedReview,
    }
  }, [validationRuns])

  const openDriftCount = useMemo(() => {
    if (errDrift) return null
    return countDriftOpen(driftRows)
  }, [driftRows, errDrift])

  const acknowledgeDriftAlert = useCallback(
    async (alertId: string) => {
      setDriftActionId(alertId)
      setDriftActionErr((m) => {
        const next = { ...m }
        delete next[alertId]
        return next
      })
      try {
        await apiFetch(`/model-health/drift-alerts/${encodeURIComponent(alertId)}/acknowledge`, {
          method: "POST",
        })
        await refreshDrift()
      } catch (e) {
        setDriftActionErr((m) => ({
          ...m,
          [alertId]: formatErr(e, "Acknowledge failed."),
        }))
      } finally {
        setDriftActionId(null)
      }
    },
    [refreshDrift],
  )

  const resolveDriftAlert = useCallback(
    async (alertId: string) => {
      setDriftActionId(alertId)
      setDriftActionErr((m) => {
        const next = { ...m }
        delete next[alertId]
        return next
      })
      try {
        await apiFetch(`/model-health/drift-alerts/${encodeURIComponent(alertId)}/resolve`, {
          method: "POST",
        })
        await refreshDrift()
      } catch (e) {
        setDriftActionErr((m) => ({
          ...m,
          [alertId]: formatErr(e, "Resolve failed."),
        }))
      } finally {
        setDriftActionId(null)
      }
    },
    [refreshDrift],
  )

  const hasPartialErrors = Boolean(errRuns || errBenchmarks || errHealth || errDrift || errComparisons)
  const showGlobalUnavailable =
    !loading &&
    Boolean(errRuns) &&
    Boolean(errDrift) &&
    Boolean(errHealth) &&
    Boolean(errBenchmarks) &&
    Boolean(errComparisons)

  const sortedRuns = useMemo(() => {
    const rows = [...validationRuns]
    rows.sort((a, b) => {
      const ta = readStr(a, ["finished_at", "completed_at", "updated_at", "started_at", "created_at"])
      const tb = readStr(b, ["finished_at", "completed_at", "updated_at", "started_at", "created_at"])
      const da = ta ? Date.parse(ta) : 0
      const db = tb ? Date.parse(tb) : 0
      return db - da
    })
    return rows
  }, [validationRuns])

  function statMainText(value: number | null, errored: boolean): string {
    if (loading) return "…"
    if (errored) return "—"
    if (value === null) return "—"
    return String(value)
  }

  function statSubline(opts: { empty?: boolean; errored: boolean; loading: boolean; label: string }) {
    if (opts.loading) return <p className="text-xs text-muted-foreground">Loading…</p>
    if (opts.errored) return <p className="text-xs text-muted-foreground">Unable to load from backend.</p>
    if (opts.empty) return <p className="text-xs text-muted-foreground">No data returned.</p>
    return <p className="text-xs text-muted-foreground">{opts.label}</p>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-green)" }}
          >
            MolTrace · Validation
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Validation Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Validation runs, benchmarks, model health, drift, and method comparisons from the backend.
          </p>
          {!loading && errRuns && !showGlobalUnavailable ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Validation runs list unavailable — refresh or verify the backend.
            </p>
          ) : null}
        </div>
        <BackendStatusIndicator />
      </div>

      {!loading && showGlobalUnavailable ? (
        <AlertCard
          variant="error"
          icon={ServerOff}
          title="Validation services unavailable"
          description="Try again in a moment, or contact your platform administrator."
        />
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void reload()}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>

      {hasPartialErrors ? (
        <AlertCard variant="error" title="Partial load">
          <div className="space-y-1 text-xs text-foreground/90">
            {errRuns ? <p>Validation runs: {errRuns}</p> : null}
            {errBenchmarks ? <p>Benchmark datasets: {errBenchmarks}</p> : null}
            {errHealth ? <p>Model health: {errHealth}</p> : null}
            {errDrift ? <p>Drift alerts: {errDrift}</p> : null}
            {errComparisons ? <p>Method comparisons: {errComparisons}</p> : null}
          </div>
        </AlertCard>
      ) : null}

      {/* 1. Validation run summary cards */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Validation run summary cards</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Validation runs</CardTitle>
              <Activity className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-green)" }}
              >
                {statMainText(errRuns ? null : runStats.total, Boolean(errRuns))}
              </div>
              {statSubline({
                loading,
                errored: Boolean(errRuns),
                empty: !errRuns && runStats.total === 0,
                label: "Listed runs",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Passed</CardTitle>
              <CheckCircle2 className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-green)" }}
              >
                {statMainText(errRuns ? null : runStats.passed, Boolean(errRuns))}
              </div>
              {statSubline({
                loading,
                errored: Boolean(errRuns),
                empty: !errRuns && validationRuns.length === 0,
                label: "Runs with succeeded-like status from API",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-red)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Failed / requires review</CardTitle>
              <AlertTriangle className="h-4 w-4" style={{ color: "var(--mt-red)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-red)" }}
              >
                {statMainText(errRuns ? null : runStats.failedReview, Boolean(errRuns))}
              </div>
              {statSubline({
                loading,
                errored: Boolean(errRuns),
                empty: !errRuns && validationRuns.length === 0,
                label: "Runs with failed- or review-like status from API",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-amber)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Open drift alerts</CardTitle>
              <Layers className="h-4 w-4" style={{ color: "var(--mt-amber)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-amber)" }}
              >
                {statMainText(openDriftCount, Boolean(errDrift))}
              </div>
              {statSubline({
                loading,
                errored: Boolean(errDrift),
                empty: !errDrift && driftRows.length === 0,
                label: "From drift alert feed",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-green)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Active methods</CardTitle>
              <BarChart3 className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-green)" }}
              >
                {statMainText(errHealth ? null : healthCounts.active, Boolean(errHealth))}
              </div>
              {statSubline({
                loading,
                errored: Boolean(errHealth),
                empty:
                  !errHealth &&
                  healthCounts.active === 0 &&
                  modelHealthRaw != null &&
                  !Array.isArray(modelHealthRaw) &&
                  !readStr(modelHealthRaw as Record<string, unknown>, ["active_methods"]),
                label: "From model health payload",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-violet)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Experimental methods</CardTitle>
              <FlaskConical className="h-4 w-4" style={{ color: "var(--mt-violet)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-violet)" }}
              >
                {statMainText(errHealth ? null : healthCounts.experimental, Boolean(errHealth))}
              </div>
              {statSubline({
                loading,
                errored: Boolean(errHealth),
                empty: !errHealth && healthCounts.experimental === null && modelHealthRaw != null,
                label: "From model health payload",
              })}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 2. Recent validation runs table */}
      <ModuleCard
        accent="cyan"
        eyebrow="Runs"
        title="Recent validation runs"
        icon={Activity}
        description="Latest validation runs reported by the backend."
      >
        <div>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errRuns ? (
            <div className="flex items-start gap-2 text-sm text-destructive">
              <ServerOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>Backend unavailable for validation runs.</span>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Run ID</TableHead>
                    <TableHead className="text-xs">Method</TableHead>
                    <TableHead className="text-xs">Model version</TableHead>
                    <TableHead className="text-xs">Benchmark</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-xs">Key metrics</TableHead>
                    <TableHead className="text-xs">Started / finished</TableHead>
                    <TableHead className="text-right text-xs">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedRuns.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-xs text-muted-foreground">
                        No validation runs returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    sortedRuns.map((row, i) => {
                      const id =
                        readStr(row, ["run_id", "validation_run_id", "id", "uuid"]) || `row-${i}`
                      return (
                        <TableRow key={id}>
                          <TableCell className="max-w-[10rem] font-mono text-[10px] break-all">{id}</TableCell>
                          <TableCell className="text-xs">
                            {readStr(row, ["method", "method_name", "method_id"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">
                            {readStr(row, ["model_version", "modelVersion", "version"]) || "—"}
                          </TableCell>
                          <TableCell className="max-w-[12rem] text-xs">
                            {readStr(row, ["benchmark", "benchmark_name", "benchmark_id", "dataset"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {readStr(row, ["status", "run_status", "state"]) || "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[14rem] text-xs">
                            {summarizeUnknown(row.key_metrics ?? row.metrics ?? row.summary_metrics)}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-[10px] text-muted-foreground">
                            {readStr(row, ["started_at", "startedAt"]) || "—"}
                            <span className="mx-1">·</span>
                            {readStr(row, ["finished_at", "completed_at", "finishedAt"]) || "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button type="button" variant="outline" size="sm" className="h-8 text-xs" asChild>
                              <Link href={`/validation/${encodeURIComponent(id)}`}>
                                <Eye className="mr-1 h-3 w-3" aria-hidden />
                                View details
                                <span className="sr-only"> ({id})</span>
                              </Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </ModuleCard>

      {/* 3. Benchmark datasets table */}
      <ModuleCard
        accent="cyan"
        eyebrow="Benchmarks"
        title="Benchmark datasets"
        icon={BarChart3}
        description="Benchmark datasets exposed by the API."
      >
        <div>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errBenchmarks ? (
            <div className="flex items-start gap-2 text-sm text-destructive">
              <ServerOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>Backend unavailable for benchmark datasets.</span>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">ID</TableHead>
                    <TableHead className="text-xs">Name</TableHead>
                    <TableHead className="text-xs">Description</TableHead>
                    <TableHead className="text-xs">Version</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {benchmarks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-xs text-muted-foreground">
                        No benchmark datasets returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    benchmarks.map((row, i) => (
                      <TableRow key={readStr(row, ["id", "dataset_id"]) || String(i)}>
                        <TableCell className="font-mono text-[10px]">
                          {readStr(row, ["id", "dataset_id"]) || "—"}
                        </TableCell>
                        <TableCell className="text-xs">{readStr(row, ["name", "title"]) || "—"}</TableCell>
                        <TableCell className="max-w-[24rem] text-xs">
                          {readStr(row, ["description", "summary"]) || "—"}
                        </TableCell>
                        <TableCell className="text-xs">{readStr(row, ["version"]) || "—"}</TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className="font-normal">
                            {readStr(row, ["status"]) || "—"}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </ModuleCard>

      {/* 4. Drift alerts panel */}
      <ModuleCard
        accent="amber"
        eyebrow="Drift"
        title="Drift alerts"
        icon={AlertTriangle}
        description="Model health drift signals — outstanding alerts where current values diverge from approved baselines."
      >
        <div>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errDrift ? (
            <div className="flex items-start gap-2 text-sm text-destructive">
              <ServerOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>Backend unavailable for drift alerts.</span>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Severity</TableHead>
                    <TableHead className="text-xs">Title</TableHead>
                    <TableHead className="text-xs">Method / model</TableHead>
                    <TableHead className="text-xs">Baseline value</TableHead>
                    <TableHead className="text-xs">Current value</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-right text-xs">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {driftRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-xs text-muted-foreground">
                        No drift alerts returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    driftRows.map((row, i) => {
                      const alertId = readDriftAlertId(row)
                      const driftSt = normalizeDriftStatus(row)
                      const resolvedRow = isDriftResolvedStatus(driftSt)
                      const isOpen = driftSt === "open" || driftSt === ""
                      const isAck = driftSt === "acknowledged"
                      const busy = Boolean(alertId && driftActionId === alertId)
                      const rowErr = alertId ? driftActionErr[alertId] : ""
                      const showAck = Boolean(alertId) && !resolvedRow && isOpen
                      const showResolve = Boolean(alertId) && !resolvedRow && (isOpen || isAck)
                      const sevLabel = readStr(row, ["severity", "level"]) || "—"
                      return (
                        <TableRow key={alertId || `row-${i}`}>
                          <TableCell className="text-xs">
                            <Badge variant={severityBadgeVariant(sevLabel)} className="font-normal">
                              {sevLabel}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[14rem] text-xs font-medium">
                            {readStr(row, ["title", "name", "alert_type"]) || "—"}
                          </TableCell>
                          <TableCell className="max-w-[14rem] text-xs">{readMethodModelLabel(row)}</TableCell>
                          <TableCell className="max-w-[10rem] font-mono text-[10px]">
                            {summarizeUnknown(row.baseline_value ?? row.baseline ?? row.expected)}
                          </TableCell>
                          <TableCell className="max-w-[10rem] font-mono text-[10px]">
                            {summarizeUnknown(row.current_value ?? row.current ?? row.observed)}
                          </TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {readStr(row, ["status", "alert_status", "state"]) || "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right align-top">
                            <div className="flex flex-wrap justify-end gap-1">
                              {showAck ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-8 text-xs"
                                  disabled={busy || loading}
                                  onClick={() => void acknowledgeDriftAlert(alertId)}
                                >
                                  {busy ? "…" : "Acknowledge"}
                                </Button>
                              ) : null}
                              {showResolve ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-8 text-xs"
                                  disabled={busy || loading}
                                  onClick={() => void resolveDriftAlert(alertId)}
                                >
                                  {busy ? "…" : "Resolve"}
                                </Button>
                              ) : null}
                              {!showAck && !showResolve && alertId ? (
                                <span className="text-[10px] text-muted-foreground">—</span>
                              ) : null}
                              {!alertId ? (
                                <span className="text-[10px] text-muted-foreground">No id</span>
                              ) : null}
                            </div>
                            {rowErr ? (
                              <p className="mt-1 max-w-[14rem] text-right text-[10px] text-destructive">{rowErr}</p>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </ModuleCard>

      {/* 5. Method comparison summary */}
      <ModuleCard
        accent="cyan"
        eyebrow="Method Comparison"
        title="Method comparison summary"
        icon={FlaskConical}
        description="Analytical method comparison records — matched method pairs and their performance deltas across reference and candidate procedures."
      >
        <div>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errComparisons ? (
            <div className="flex items-start gap-2 text-sm text-destructive">
              <ServerOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>Backend unavailable for method comparisons.</span>
            </div>
          ) : methodComparisons.length === 0 ? (
            <p className="text-sm text-muted-foreground">No method comparisons returned.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Comparison</TableHead>
                    <TableHead className="text-xs">Methods</TableHead>
                    <TableHead className="text-xs">Summary</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {methodComparisons.map((row, i) => (
                    <TableRow key={readStr(row, ["id", "comparison_id"]) || String(i)}>
                      <TableCell className="text-xs font-medium">
                        {readStr(row, ["name", "title", "label"]) || "—"}
                      </TableCell>
                      <TableCell className="max-w-[20rem] text-xs">{summarizeUnknown(row.methods ?? row.method_ids)}</TableCell>
                      <TableCell className="max-w-[28rem] text-xs">
                        {summarizeUnknown(row.summary ?? row.result_summary ?? row.metrics)}
                      </TableCell>
                      <TableCell className="text-xs">
                        <Badge variant="outline" className="font-normal">
                          {readStr(row, ["status"]) || "—"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </ModuleCard>

    </div>
  )
}
