"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { AlertCircle, ArrowRight, CheckCircle2, LockKeyhole, PackageCheck } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch } from "@/lib/api/client"
import { useTenant, type TenantModuleAccess } from "@/src/lib/tenant/tenant-context"

type Row = Record<string, unknown>

type ProcurementPackageSummary = {
  id: string
  title: string
  status: string
  packageType: string
  sha256: string
}

type MobileTenantSummary = {
  tenantStatus: string
  pilotStatus: string
  onboardingStatus: string
  onboardingBlockers: string[]
  healthScore: string
  healthStatus: string
  nextTask: string
  primaryContact: string
  recommendedActions: string[]
  procurementPackages: ProcurementPackageSummary[]
  warnings: string[]
}

const LOCAL_TENANT_ID = "local-development"
const DEFAULT_TASK_ORDER = ["SpectraCheck setup", "Regulatory Hub setup", "Reaction Optimization setup"]

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function asRows(payload: unknown, keys: string[] = []): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []

  for (const key of [...keys, "items", "results", "rows", "data"]) {
    const value = payload[key]
    if (Array.isArray(value)) return value.filter(isRecord)
  }

  return []
}

function unwrapRecord(payload: unknown, keys: string[] = []): Row | null {
  if (!isRecord(payload)) return null

  for (const key of [...keys, "item", "record", "data"]) {
    const value = payload[key]
    if (isRecord(value)) return value
  }

  return payload
}

function readString(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return value ? "true" : "false"
  return ""
}

function readFirst(row: Row | null | undefined, keys: string[]): string {
  if (!row) return ""
  for (const key of keys) {
    const value = readString(row[key])
    if (value) return value
  }
  return ""
}

function normalizeLabel(value: string) {
  return value ? value.replace(/_/g, " ") : "Not available"
}

function statusVariant(status: string): "destructive" | "secondary" | "outline" {
  const normalized = status.toLowerCase()
  if (normalized.includes("blocked") || normalized.includes("risk") || normalized.includes("failed")) return "destructive"
  if (
    normalized.includes("active") ||
    normalized.includes("healthy") ||
    normalized.includes("ready") ||
    normalized.includes("completed")
  ) {
    return "secondary"
  }
  return "outline"
}

function toSafeList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item.trim()
        if (isRecord(item)) return readFirst(item, ["title", "summary", "action", "status", "name"])
        return ""
      })
      .filter(Boolean)
  }

  if (isRecord(value)) {
    const item = readFirst(value, ["title", "summary", "action", "status", "name"])
    return item ? [item] : []
  }

  const item = readString(value)
  return item ? [item] : []
}

function firstStatus(rows: Row[], preferredStatuses: string[]) {
  return (
    rows.find((row) => preferredStatuses.includes(readFirst(row, ["status"]).toLowerCase())) ??
    rows[0] ??
    null
  )
}

function defaultTaskRank(row: Row) {
  const title = readFirst(row, ["title", "name"])
  const rank = DEFAULT_TASK_ORDER.findIndex((label) => title.toLowerCase().includes(label.toLowerCase()))
  return rank === -1 ? DEFAULT_TASK_ORDER.length : rank
}

function findNextTask(tasks: Row[]) {
  const actionableTasks = tasks.filter((task) => {
    const status = readFirst(task, ["status"]).toLowerCase()
    return status === "blocked" || status === "in_progress" || status === "open"
  })

  const nextTask = [...actionableTasks].sort((a, b) => defaultTaskRank(a) - defaultTaskRank(b))[0]
  return readFirst(nextTask, ["title", "name"]) || "No next onboarding task"
}

function shortHash(value: string) {
  return value.length > 16 ? `${value.slice(0, 16)}...` : value
}

async function fetchSafe(path: string, tenantId: string, label: string, warnings: string[]) {
  try {
    return await apiFetch<unknown>(path, {
      method: "GET",
      headers: { "x-tenant-id": tenantId },
    })
  } catch (error) {
    if (error instanceof Error) warnings.push(`${label} unavailable`)
    return null
  }
}

function emptySummary(tenantStatus: string, tenantDisplayName: string): MobileTenantSummary {
  return {
    tenantStatus: tenantStatus || "local",
    pilotStatus: tenantDisplayName === "Local development tenant" ? "local development" : "Not available",
    onboardingStatus: "Not available",
    onboardingBlockers: [],
    healthScore: "Not available",
    healthStatus: "unknown",
    nextTask: "No next onboarding task",
    primaryContact: "Not available",
    recommendedActions: [],
    procurementPackages: [],
    warnings: [],
  }
}

function MobileMetric({
  label,
  value,
  status,
}: {
  label: string
  value: string
  status?: string
}) {
  return (
    <div className="min-w-0 rounded-md border bg-card p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-2 flex min-w-0 items-center justify-between gap-2">
        <p className="min-w-0 break-words text-sm font-semibold text-foreground">{value}</p>
        {status ? (
          <Badge variant={statusVariant(status)} className="shrink-0 capitalize">
            {normalizeLabel(status)}
          </Badge>
        ) : null}
      </div>
    </div>
  )
}

function ModuleOrderCard({ moduleAccess }: { moduleAccess: TenantModuleAccess[] }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="text-base">Program Order</CardTitle>
        <CardDescription>Locked modules stay visible in MolTrace's core sequence.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {moduleAccess.map((module, index) => (
          <div key={module.key} className="flex min-w-0 items-center justify-between gap-3 rounded-md border p-3">
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">Program {index + 1}</p>
              <p className="break-words text-sm font-semibold">{module.label}</p>
            </div>
            <Badge variant={module.enabled ? "secondary" : "outline"} className="shrink-0">
              {module.enabled ? "Enabled" : "Locked"}
            </Badge>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export function MobileTenantSummaryWorkspace() {
  const { currentTenantId, tenantDisplayName, tenantStatus, moduleAccess, isAdmin, loading: tenantLoading } = useTenant()
  const [summary, setSummary] = useState<MobileTenantSummary>(() => emptySummary(tenantStatus, tenantDisplayName))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false

    async function loadSummary() {
      setLoading(true)
      setError("")

      if (!currentTenantId || currentTenantId === LOCAL_TENANT_ID) {
        if (!cancelled) {
          setSummary(emptySummary(tenantStatus, tenantDisplayName))
          setLoading(false)
        }
        return
      }

      const warnings: string[] = []
      try {
        const [tenantPayload, pilotPayload, onboardingPayload, healthPayload, packagePayload] = await Promise.all([
          fetchSafe(`/tenants/${encodeURIComponent(currentTenantId)}`, currentTenantId, "Tenant status", warnings),
          fetchSafe(
            `/tenants/${encodeURIComponent(currentTenantId)}/pilot-programs`,
            currentTenantId,
            "Pilot status",
            warnings,
          ),
          fetchSafe(
            `/tenants/${encodeURIComponent(currentTenantId)}/onboarding-projects`,
            currentTenantId,
            "Onboarding status",
            warnings,
          ),
          fetchSafe(
            `/tenants/${encodeURIComponent(currentTenantId)}/health-score`,
            currentTenantId,
            "Health score",
            warnings,
          ),
          fetchSafe(
            `/tenants/${encodeURIComponent(currentTenantId)}/procurement-packages`,
            currentTenantId,
            "Procurement packages",
            warnings,
          ),
        ])

        const tenant = unwrapRecord(tenantPayload, ["tenant"])
        const pilots = asRows(pilotPayload, ["pilot_programs", "pilots"])
        const onboardingProjects = asRows(onboardingPayload, ["onboarding_projects", "projects"])
        const health = unwrapRecord(healthPayload, ["health_score", "score"])
        const packages = asRows(packagePayload, ["procurement_packages", "packages"])

        const activePilot = firstStatus(pilots, ["active", "planned", "paused", "completed"])
        const activeOnboarding = firstStatus(onboardingProjects, ["blocked", "in_progress", "ready_for_go_live", "not_started"])
        const onboardingProjectId = readFirst(activeOnboarding, ["id", "project_id"])

        let tasks: Row[] = []
        if (onboardingProjectId) {
          const taskPayload = await fetchSafe(
            `/onboarding-projects/${encodeURIComponent(onboardingProjectId)}/tasks`,
            currentTenantId,
            "Onboarding tasks",
            warnings,
          )
          tasks = asRows(taskPayload, ["implementation_tasks", "tasks"])
        }

        const blockedTasks = tasks
          .filter((task) => readFirst(task, ["status"]).toLowerCase() === "blocked")
          .map((task) => readFirst(task, ["title", "name"]))
          .filter(Boolean)
        const healthBlockers = toSafeList(health?.blockers_json).slice(0, 4)
        const procurementPackages = packages.slice(0, 4).map((item) => ({
          id: readFirst(item, ["id", "package_id"]),
          title: readFirst(item, ["title", "name"]) || "Procurement evidence package",
          status: readFirst(item, ["status", "package_status"]) || "Not available",
          packageType: readFirst(item, ["package_type"]) || "Not available",
          sha256: readFirst(item, ["package_sha256", "sha256"]),
        }))

        if (!cancelled) {
          setSummary({
            tenantStatus: readFirst(tenant, ["status"]) || tenantStatus || "unknown",
            pilotStatus: readFirst(activePilot, ["status"]) || "Not available",
            onboardingStatus: readFirst(activeOnboarding, ["status"]) || "Not available",
            onboardingBlockers: (blockedTasks.length > 0 ? blockedTasks : healthBlockers).slice(0, 4),
            healthScore: readFirst(health, ["score"]) || "Not available",
            healthStatus: readFirst(health, ["status"]) || "unknown",
            nextTask: findNextTask(tasks),
            primaryContact: readFirst(tenant, ["primary_contact_email", "primary_contact"]) || "Not available",
            recommendedActions: toSafeList(health?.recommended_actions_json).slice(0, 4),
            procurementPackages,
            warnings: warnings.slice(0, 3),
          })
        }
      } catch {
        if (!cancelled) {
          setError("Tenant mobile summary is unavailable.")
          setSummary(emptySummary(tenantStatus, tenantDisplayName))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadSummary()

    return () => {
      cancelled = true
    }
  }, [currentTenantId, tenantDisplayName, tenantStatus])

  const busy = loading || tenantLoading

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-0 pb-8 sm:px-2">
      <div className="min-w-0 space-y-2">
        <Badge variant="outline" className="w-fit">
          Mobile review
        </Badge>
        <div className="min-w-0">
          <h1 className="break-words text-2xl font-semibold tracking-tight">Tenant Summary</h1>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            Review tenant onboarding, customer success health, and procurement package status.
          </p>
        </div>
      </div>

      <Alert>
        <LockKeyhole className="h-4 w-4" />
        <AlertDescription>
          Mobile tenant views are for review and triage. Do not enter raw secrets, connector credentials, or raw
          scientific data.
        </AlertDescription>
      </Alert>

      {!isAdmin ? (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>Non-admin users can review the current tenant only.</AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle className="break-words text-lg">{tenantDisplayName}</CardTitle>
          <CardDescription>Customer deployment snapshot</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <MobileMetric label="Tenant status" value={normalizeLabel(summary.tenantStatus)} status={summary.tenantStatus} />
            <MobileMetric label="Pilot status" value={normalizeLabel(summary.pilotStatus)} status={summary.pilotStatus} />
            <MobileMetric
              label="Onboarding blockers"
              value={busy ? "Loading" : String(summary.onboardingBlockers.length)}
              status={summary.onboardingBlockers.length > 0 ? "blocked" : "ready"}
            />
            <MobileMetric
              label="Health score"
              value={busy ? "Loading" : summary.healthScore}
              status={summary.healthStatus}
            />
            <MobileMetric label="Next task" value={busy ? "Loading" : summary.nextTask} />
            <MobileMetric label="Primary contact" value={busy ? "Loading" : summary.primaryContact} />
          </div>
        </CardContent>
      </Card>

      <ModuleOrderCard moduleAccess={moduleAccess} />

      <Card id="onboarding" className="scroll-mt-24 overflow-hidden">
        <CardHeader>
          <CardTitle className="text-base">Onboarding</CardTitle>
          <CardDescription>Review blockers and the next customer task.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex min-w-0 items-center justify-between gap-3 rounded-md border p-3">
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">Onboarding status</p>
              <p className="break-words text-sm font-semibold">{normalizeLabel(summary.onboardingStatus)}</p>
            </div>
            <Badge variant={statusVariant(summary.onboardingStatus)} className="shrink-0 capitalize">
              {normalizeLabel(summary.onboardingStatus)}
            </Badge>
          </div>

          {summary.onboardingBlockers.length > 0 ? (
            <div className="space-y-2">
              {summary.onboardingBlockers.map((blocker) => (
                <div key={blocker} className="flex min-w-0 items-start gap-2 rounded-md border p-3 text-sm">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                  <span className="min-w-0 break-words">{blocker}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex min-w-0 items-start gap-2 rounded-md border p-3 text-sm text-muted-foreground">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 break-words">No onboarding blockers returned.</span>
            </div>
          )}
        </CardContent>
      </Card>

      <Card id="health-score" className="scroll-mt-24 overflow-hidden">
        <CardHeader>
          <CardTitle className="text-base">Health Score</CardTitle>
          <CardDescription>Review customer success status and recommended actions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex min-w-0 items-center justify-between gap-3 rounded-md border p-3">
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">Status</p>
              <p className="break-words text-sm font-semibold">{normalizeLabel(summary.healthStatus)}</p>
            </div>
            <Badge variant={statusVariant(summary.healthStatus)} className="shrink-0 capitalize">
              {normalizeLabel(summary.healthStatus)}
            </Badge>
          </div>

          {summary.recommendedActions.length > 0 ? (
            <div className="space-y-2">
              {summary.recommendedActions.map((action) => (
                <div key={action} className="flex min-w-0 items-start gap-2 rounded-md border p-3 text-sm">
                  <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 break-words">{action}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-md border p-3 text-sm text-muted-foreground">No recommended actions returned.</p>
          )}
        </CardContent>
      </Card>

      <Card id="procurement-packages" className="scroll-mt-24 overflow-hidden">
        <CardHeader>
          <CardTitle className="text-base">Procurement Packages</CardTitle>
          <CardDescription>Review safe package summaries without raw data or secrets.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {summary.procurementPackages.length > 0 ? (
            summary.procurementPackages.map((item) => (
              <div key={item.id || item.title} className="min-w-0 rounded-md border p-3">
                <div className="flex min-w-0 items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="break-words text-sm font-semibold">{item.title}</p>
                    <p className="mt-1 break-words text-xs text-muted-foreground">{normalizeLabel(item.packageType)}</p>
                  </div>
                  <Badge variant={statusVariant(item.status)} className="shrink-0 capitalize">
                    {normalizeLabel(item.status)}
                  </Badge>
                </div>
                <p className="mt-2 break-words text-xs text-muted-foreground">
                  SHA-256: {item.sha256 ? shortHash(item.sha256) : "Not available"}
                </p>
              </div>
            ))
          ) : (
            <div className="flex min-w-0 items-start gap-2 rounded-md border p-3 text-sm text-muted-foreground">
              <PackageCheck className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 break-words">No procurement packages returned.</span>
            </div>
          )}

          {currentTenantId && currentTenantId !== LOCAL_TENANT_ID ? (
            <Button asChild variant="outline" className="w-full">
              <Link href={`/admin/tenants/${encodeURIComponent(currentTenantId)}`}>Open full tenant record</Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {summary.warnings.length > 0 ? (
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">Status Notes</CardTitle>
            <CardDescription>Some tenant signals were unavailable.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {summary.warnings.map((warning) => (
              <p key={warning} className="break-words rounded-md border p-3 text-sm text-muted-foreground">
                {warning}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
