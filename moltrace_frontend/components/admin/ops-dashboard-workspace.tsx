"use client"

import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  CheckCircle2,
  GitBranch,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  XCircle,
} from "lucide-react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
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
import { cn } from "@/lib/utils"
import type { components } from "@/src/lib/api/schema"

/**
 * Admin Ops dashboard (Prompt 18 MLOps layer).
 *
 * Two read-only, admin-gated GET routes:
 *   - GET /admin/ops/deployment-gate → OpsDeploymentGateStatus
 *       the fail-closed release-control posture (four-check policy + the live
 *       self-check that the gate machinery still fails closed) plus the
 *       monitoring thresholds that the future drift panel will read.
 *   - GET /admin/ops/model-lineage   → OpsModelLineageResponse
 *       one row per production model; empty + registry_configured=false until
 *       a model registry is wired and a model promoted (current state).
 *
 * Both are admin-only server-side (require_admin → 401/403). apiFetch attaches
 * the stored Bearer token automatically; we surface a focused "admin access
 * required" state on 401/403 rather than a generic error.
 *
 * Deferred (handoff §7): the live drift panels (input-PSI / confidence /
 * override-rate / latency) need telemetry not yet plumbed into the API. A
 * GET /admin/ops/drift endpoint will follow. The layout leaves a labelled
 * slot for it so it can drop in without a restructure.
 */

type GateStatus = components["schemas"]["OpsDeploymentGateStatus"]
type LineageResponse = components["schemas"]["OpsModelLineageResponse"]
type LineageRow = components["schemas"]["OpsModelLineageRow"]

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) {
      return "Admin access required to view ops telemetry."
    }
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

/** True when the failure is specifically an auth/permission denial. */
function isAuthErr(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 401 || err.status === 403)
}

/** Humanize a monitoring-threshold key: psi_warn → "psi warn". */
function humanizeKey(key: string): string {
  return key.replace(/_/g, " ")
}

/** drift_status → badge palette (matches the dependency-badge convention). */
function driftBadgeClass(status: string): string {
  switch (status.toLowerCase()) {
    case "ok":
      return "border-success/50 text-success"
    case "warn":
      return "border-warning/50 text-warning"
    case "breach":
      return "border-destructive/50 text-destructive"
    default:
      return "text-muted-foreground"
  }
}

/** data_mode → badge palette. "live" is the healthy/default state. */
function dataModeClass(mode: string): string {
  switch (mode) {
    case "live":
      return "border-success/50 text-success"
    case "stale":
    case "partially_synced":
      return "border-warning/50 text-warning"
    case "unavailable":
      return "border-destructive/50 text-destructive"
    default:
      return "text-muted-foreground"
  }
}

function DataModeFooter({ mode, generatedAt }: { mode: string; generatedAt?: string }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3 text-[10px] text-muted-foreground">
      <Badge variant="outline" className={cn("font-normal", dataModeClass(mode))}>
        {mode}
      </Badge>
      {generatedAt ? <span className="font-mono">generated {generatedAt}</span> : null}
    </div>
  )
}

export function OpsDashboardWorkspace() {
  const [gate, setGate] = useState<GateStatus | null>(null)
  const [lineage, setLineage] = useState<LineageResponse | null>(null)
  const [gateErr, setGateErr] = useState("")
  const [lineageErr, setLineageErr] = useState("")
  const [gateAuthErr, setGateAuthErr] = useState(false)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    setLoading(true)
    setGateErr("")
    setLineageErr("")
    setGateAuthErr(false)

    await Promise.all([
      apiFetch<GateStatus>("/admin/ops/deployment-gate", { method: "GET" })
        .then((data) => setGate(data ?? null))
        .catch((e) => {
          setGate(null)
          setGateAuthErr(isAuthErr(e))
          setGateErr(formatErr(e, "Could not load the deployment gate."))
        }),
      apiFetch<LineageResponse>("/admin/ops/model-lineage", { method: "GET" })
        .then((data) => setLineage(data ?? null))
        .catch((e) => {
          setLineage(null)
          setLineageErr(formatErr(e, "Could not load model lineage."))
        }),
    ])

    setLoading(false)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const checks = gate?.checks ?? []
  const selfCheckFailures = gate?.self_check_failures ?? []
  const thresholds = gate?.monitoring_thresholds ?? {}
  const thresholdEntries = Object.entries(thresholds)
  const rows: LineageRow[] = lineage?.rows ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-slate)" }}
          >
            MolTrace · Admin · Ops
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Release control &amp; model lineage</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            The fail-closed deployment-gate posture and per-model lineage from the Prompt 18 MLOps
            layer. Read-only and admin-gated; the backend computes the gate live and owns the
            release policy — this surface renders it as-is.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void reload()}>
          {loading ? (
            <>
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden />
              Loading…
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden />
              Refresh
            </>
          )}
        </Button>
      </div>

      {/* Admin-gating: a 401/403 on the gate route means this whole surface is
          not available to the current user. Surface it once, prominently. */}
      {gateAuthErr ? (
        <AlertCard
          variant="error"
          title="Admin access required"
          description="These ops endpoints are admin-only. Sign in with an admin account to view the deployment gate and model lineage."
        />
      ) : null}

      {/* ── Release-control panel ← /admin/ops/deployment-gate ───────────── */}
      <ModuleCard
        accent="slate"
        eyebrow="Release control"
        title="Deployment gate"
        icon={ShieldCheck}
        description="A model or pipeline change reaches production only if all four checks pass. The gate is verified to fail closed on every request."
      >
        {loading && !gate ? (
          <p className="text-sm text-muted-foreground">Loading deployment gate…</p>
        ) : gateErr && !gateAuthErr ? (
          <AlertCard variant="error" title="Deployment gate unavailable" description={gateErr} />
        ) : gate ? (
          <div className="space-y-5">
            {/* Headline guarantee + self-check verdict */}
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-xs font-bold uppercase tracking-[0.14em]",
                  gate.fails_closed
                    ? "border-success/50 text-success"
                    : "border-destructive/50 text-destructive",
                )}
              >
                {gate.fails_closed ? (
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
                )}
                {gate.fails_closed ? "Fails closed" : "NOT fail-closed"}
              </span>

              <Badge
                variant="outline"
                className={cn(
                  "gap-1 font-normal",
                  gate.self_check_passed
                    ? "border-success/50 text-success"
                    : "border-destructive/50 text-destructive",
                )}
              >
                {gate.self_check_passed ? (
                  <CheckCircle2 className="h-3 w-3" aria-hidden />
                ) : (
                  <XCircle className="h-3 w-3" aria-hidden />
                )}
                Self-check {gate.self_check_passed ? "passed" : "FAILED"}
              </Badge>

              <span className="font-mono text-[10px] text-muted-foreground">
                output contract v{gate.output_contract_schema_version}
              </span>
            </div>

            {/* self_check_failures — non-empty only if the gate logic regressed */}
            {selfCheckFailures.length > 0 ? (
              <AlertCard variant="error" title={`Self-check failures · ${selfCheckFailures.length}`}>
                <ul className="ml-4 list-disc space-y-0.5 text-xs text-foreground/90">
                  {selfCheckFailures.map((f, i) => (
                    <li key={`scf-${i}`}>{f}</li>
                  ))}
                </ul>
              </AlertCard>
            ) : null}

            {/* The four-check release policy */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Release policy · {checks.length} check{checks.length === 1 ? "" : "s"}
              </p>
              <ul className="space-y-1.5">
                {checks.map((c) => (
                  <li key={c.name} className="flex items-start gap-2 rounded-md border bg-muted/20 px-3 py-2">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden />
                    <div className="min-w-0">
                      <span className="font-mono text-xs font-semibold text-foreground">{c.name}</span>
                      <p className="text-xs text-muted-foreground">{c.description}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* monitoring_thresholds — the drift-config sub-panel */}
            <div className="space-y-2">
              <p className="inline-flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                <SlidersHorizontal className="h-3 w-3" aria-hidden />
                Monitoring thresholds
              </p>
              {thresholdEntries.length === 0 ? (
                <p className="text-xs text-muted-foreground">No thresholds reported.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {thresholdEntries.map(([key, value]) => (
                    <div key={key} className="rounded-md border bg-muted/10 px-3 py-2">
                      <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                        {humanizeKey(key)}
                      </p>
                      <p className="font-mono text-sm font-bold tabular-nums">{value}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <DataModeFooter mode={gate.data_mode} generatedAt={gate.generated_at} />
          </div>
        ) : null}
      </ModuleCard>

      {/* ── Model-lineage panel ← /admin/ops/model-lineage ───────────────── */}
      <ModuleCard
        accent="slate"
        eyebrow="Model lineage"
        title="Production model lineage"
        icon={GitBranch}
        description="One row per production model: version, training-snapshot hash, metric vector, promotion provenance, and drift status."
      >
        {loading && !lineage ? (
          <p className="text-sm text-muted-foreground">Loading model lineage…</p>
        ) : lineageErr ? (
          <AlertCard variant="error" title="Model lineage unavailable" description={lineageErr} />
        ) : lineage ? (
          lineage.registry_configured === false || rows.length === 0 ? (
            // Empty state — surface the backend note rather than a blank table.
            <div className="space-y-3">
              <div className="flex flex-col items-center gap-2 rounded-md border border-dashed bg-muted/20 px-4 py-8 text-center">
                <GitBranch className="h-6 w-6 text-muted-foreground" aria-hidden />
                <p className="text-sm font-medium text-foreground">No model lineage yet</p>
                <p className="max-w-md text-xs text-muted-foreground">
                  {lineage.note ??
                    "No model registry is configured on this deployment yet; lineage appears once a fine-tuned model is promoted to production."}
                </p>
              </div>
              <DataModeFooter mode={lineage.data_mode} generatedAt={lineage.generated_at} />
            </div>
          ) : (
            <div className="space-y-3">
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">model_id</TableHead>
                      <TableHead className="text-xs">role</TableHead>
                      <TableHead className="text-xs">nucleus</TableHead>
                      <TableHead className="text-xs">version</TableHead>
                      <TableHead className="text-xs">metrics</TableHead>
                      <TableHead className="text-xs">promoted</TableHead>
                      <TableHead className="text-xs">drift</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((row, i) => (
                      <TableRow key={`${row.model_id}-${i}`}>
                        <TableCell className="max-w-[16rem] truncate font-mono text-[10px]" title={row.model_id}>
                          {row.model_id}
                        </TableCell>
                        <TableCell className="font-mono text-[10px]">{row.role}</TableCell>
                        <TableCell className="font-mono text-[10px]">{row.nucleus ?? "—"}</TableCell>
                        <TableCell className="font-mono text-[10px]">{row.semantic_version}</TableCell>
                        <TableCell className="font-mono text-[10px]">
                          {Object.entries(row.metric_vector ?? {})
                            .map(([k, v]) => `${k}=${v}`)
                            .join(", ") || "—"}
                        </TableCell>
                        <TableCell
                          className="max-w-[12rem] truncate font-mono text-[10px]"
                          title={row.promotion_reason ?? undefined}
                        >
                          {row.promoted_utc ?? "—"}
                        </TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className={cn("font-normal", driftBadgeClass(row.drift_status))}>
                            {row.drift_status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <DataModeFooter mode={lineage.data_mode} generatedAt={lineage.generated_at} />
            </div>
          )
        ) : null}
      </ModuleCard>

      {/* ── Deferred: live drift panels (handoff §7) ─────────────────────────
          The input-PSI / confidence / override-rate / latency panels need a
          training baseline + assembled telemetry not yet plumbed into the API
          (GET /admin/ops/drift, a future backend prompt). This labelled slot
          marks where that panel drops in; the thresholds it will compare
          against already render in the Release-control panel above. */}
      <ModuleCard
        accent="slate"
        eyebrow="Coming soon"
        title="Live drift monitoring"
        icon={Activity}
        description="Input-PSI, confidence, override-rate, and latency over production telemetry — against the monitoring thresholds above."
      >
        <div className="flex flex-col items-center gap-2 rounded-md border border-dashed bg-muted/20 px-4 py-8 text-center">
          <Activity className="h-6 w-6 text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium text-foreground">Drift telemetry not wired yet</p>
          <p className="max-w-md text-xs text-muted-foreground">
            The live drift panels arrive once a training baseline and assembled production telemetry
            are plumbed into the API (a future <code className="font-mono">GET /admin/ops/drift</code>{" "}
            endpoint). The gate posture and lineage above ship now.
          </p>
        </div>
      </ModuleCard>
    </div>
  )
}
