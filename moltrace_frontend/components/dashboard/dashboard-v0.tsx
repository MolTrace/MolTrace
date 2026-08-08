"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch, AUTH_USER_STORAGE_KEY } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Activity,
  AlertCircle,
  FileText,
  Clock,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Eye,
  FlaskConical,
  FolderOpen,
  LayoutDashboard,
  Microscope,
  Cpu,
  ShieldCheck,
} from "lucide-react"
import {
  DashboardSection,
  setAllDashboardSectionsOpen,
  type DashboardSectionSignal,
  type DashboardSectionSignalTone,
} from "@/components/dashboard/dashboard-section"
import { DashboardGreeting } from "@/components/dashboard/dashboard-greeting"
import {
  DashboardPriorityCallout,
  type DashboardPriority,
} from "@/components/dashboard/dashboard-priority-callout"
import { GoldenPathCard } from "@/components/dashboard/golden-path-card"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { StatusFilterPills } from "@/components/dashboard/status-filter-pills"
import { RegulatoryNotificationsCompactCard } from "@/components/regulatory-hub/regulatory-notifications-compact-card"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { useOverviewData } from "@/components/app/overview-data-context"
import { useIsMobile } from "@/hooks/use-mobile"
import { humanizeField, statusLabel } from "@/lib/ui/status"
import { useTenant } from "@/src/lib/tenant/tenant-context"
import {
  fetchDashboardQcAlertsAggregate,
  type DashboardRecentFailedQcRow,
} from "@/src/lib/dashboard/dashboard-qc-alerts"
import { fetchDashboardCollaborationAggregate } from "@/src/lib/dashboard/dashboard-collaboration-aggregate"
import {
  fetchDashboardMethodHealthAggregate,
  type DashboardMethodHealthRollup,
} from "@/src/lib/dashboard/dashboard-method-health"
import {
  fetchDashboardOperationsSummary,
  type DashboardOperationsRollup,
} from "@/src/lib/dashboard/dashboard-operations-summary"
import { fetchDashboardRegulatorySummary } from "@/src/lib/dashboard/dashboard-regulatory-summary"
import {
  fetchRegulatoryComplianceCardData,
  type RegulatoryComplianceCardData,
} from "@/src/lib/dashboard/dashboard-regulatory-compliance-card"
import { fetchDashboardRegulatorySurveillanceSummary } from "@/src/lib/dashboard/dashboard-regulatory-surveillance-summary"
import { fetchDashboardCompoundRegistrySummary } from "@/src/lib/dashboard/dashboard-compound-registry-summary"
import { fetchDashboardRoiSnapshot } from "@/src/lib/dashboard/dashboard-roi-snapshot"
import {
  fetchDashboardMlFactoryRollup,
  type DashboardMlFactoryRollup,
} from "@/src/lib/dashboard/dashboard-ml-factory-health"
import {
  fetchDashboardAiInferenceSummary,
  type DashboardAiInferenceSummary,
} from "@/src/lib/dashboard/dashboard-ai-inference-summary"
import {
  fetchDashboardCrossModuleCommandCenter,
  type DashboardCrossModuleCommandCenter,
} from "@/src/lib/dashboard/dashboard-cross-module-command-center"
import {
  fetchDashboardCoreModuleActivity,
  type DashboardCoreModuleActivity,
  type DashboardCoreModuleKey,
} from "@/src/lib/dashboard/dashboard-core-module-activity"
import { ValidationReadinessDashboardCards } from "@/components/validation/validation-readiness-summary"
import type { RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"
import type { DashboardActivityRow, DashboardJobRow } from "@/src/lib/dashboard/overview-metrics"
import { useIncludedModules } from "@/src/lib/modules/included-modules-provider"
import { MODULE_DISPLAY_NAMES } from "@/src/lib/modules/module-routes"
import {
  fetchDashboardReactionSummary,
  type DashboardReactionSummary,
} from "@/src/lib/dashboard/dashboard-reaction-summary"

const ACTIVITY_STRIPE_COLOR: Record<DashboardActivityRow["status"], string> = {
  approved: "var(--mt-green)",
  review: "var(--mt-amber)",
  running: "var(--mt-cyan)",
  contradiction: "var(--mt-red)",
}

function jobStripeColor(status: string): string | undefined {
  const s = status.toLowerCase()
  if (s === "running") return "var(--mt-cyan)"
  if (s === "queued" || s === "pending") return "var(--mt-amber)"
  if (s === "succeeded" || s === "completed" || s === "success") return "var(--mt-green)"
  if (s === "failed" || s === "error") return "var(--mt-red)"
  return undefined
}

function jobBadgeColor(status: string): string | undefined {
  return jobStripeColor(status)
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRows(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (isRecord(payload) && Array.isArray(payload.items)) return payload.items.filter(isRecord)
  return []
}

function readNum(o: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  }
  return null
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
  }
  return ""
}

/** Extra detail worth showing a reader when a summary card can't load. Returns a
 *  server-supplied message only when it reads as a sentence — transport-level
 *  messages (which carry status numbers) and single machine codes are dropped, so
 *  callers should pair this with their own plain-language fallback. */
function formatApiErr(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") {
      const detail = d.detail.trim()
      if (detail && !/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(detail)) return detail
    }
  }
  return ""
}

function formatJobTimeLabel(iso: string | null): string {
  if (!iso) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

/** Readable names for the analysis job kinds the dashboard commonly shows; anything
 *  else falls back to sentence-cased words so a reader never sees a raw identifier. */
const JOB_TYPE_LABELS: Record<string, string> = {
  nmr_processed_analyze: "NMR analysis (processed spectrum)",
  nmr_raw_fid_process: "NMR raw FID processing",
  lcms_import: "LC-MS import",
}

function formatJobTypeLabel(jobType: string): string {
  const raw = jobType.trim()
  if (!raw) return "—"
  return JOB_TYPE_LABELS[raw.toLowerCase()] ?? humanizeField(raw)
}

function formatCoreModuleActivityTime(iso: string | null): string {
  if (!iso) return "No activity yet"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

/** Every summary card shows an em dash rather than a zero for a count it could not
 *  read, so "nothing to do" never gets confused with "we don't know". */
function fmtCount(n: number | null | undefined): string {
  if (n == null) return "—"
  return String(n)
}

/** A header pill for a collapsed section. Returns null for a count we can't read,
 *  so a section header never advertises "— open items". A zero stays neutral: the
 *  tone is a call to action, and there is nothing to act on. */
function countSignal(
  value: number | null | undefined,
  label: string,
  tone: DashboardSectionSignalTone = "neutral",
): DashboardSectionSignal | null {
  if (value == null) return null
  return { label: `${value} ${label}`, tone: value > 0 ? tone : "neutral" }
}

function compactSignals(items: (DashboardSectionSignal | null)[]): DashboardSectionSignal[] {
  return items.filter((item): item is DashboardSectionSignal => item != null)
}

type CustomerDeploymentSummary = {
  onboardingStatus: string
  pilotStatus: string
  validationReadiness: string
  healthScore: string
  nextOnboardingTask: string
}

/* No demo statistics.
 *
 * This block used to hold DEMO_STATS (23 active, 7 in review, 12 reports, 156
 * hours, 94.2 % model confidence) and DEMO_RECENT (five activity rows reviewed
 * by "Dr. Chen", "Dr. Patel" and "Dr. Kim" against sample "API-Q4-BATCH-12").
 * They rendered whenever live data was unavailable -- which is exactly the
 * state a new deployment is in at first login, and the moment a regulated buyer
 * decides whether the numbers on this screen can be trusted. Nothing on the
 * card distinguished them from measurements.
 *
 * The replacement is not a blank screen. Hiding a tile is its own dishonesty:
 * a reader cannot tell a metric that is genuinely zero from one that failed to
 * load. The card stays, the number becomes UNAVAILABLE_VALUE, and the subtext
 * says why.
 */

/* Stable empty collections, and they are load-bearing.
 *
 * `setState` bails out of a re-render when the new value is reference-equal to
 * the old one. The demo constants these replace were module-level, so setting
 * them repeatedly was a no-op. A fresh `[]` in their place has a new identity
 * every time, so each call is a real state change.
 *
 * That matters because the QC effect depends on `overview.sessions`, which is a
 * new array on every render from the overview context. The effect therefore
 * re-runs each render, and with a fresh `[]` it would set new state each time
 * and re-render forever. The fabricated constants were masking that: they held
 * the loop shut by accident, and removing them exposed it.
 */
const NO_ACTIVITY_ROWS: DashboardActivityRow[] = []
const NO_JOB_ROWS: DashboardJobRow[] = []
const NO_QC_ROWS: DashboardRecentFailedQcRow[] = []

/** Shown in place of a number that could not be loaded. Not zero -- unknown. */
const UNAVAILABLE_VALUE = "—"

function UnavailableSub({ what }: { what: string }) {
  return <p className="text-xs text-muted-foreground">Live {what} isn't available right now.</p>
}

export function DashboardV0() {
  const overview = useOverviewData()
  const isMobile = useIsMobile()
  const { isIncluded } = useIncludedModules()
  // Which products this deployment actually serves. The dashboard is the one page that reaches
  // into all three, so on a single-product deployment it is where absent modules show up worst:
  // sections that open onto refused requests, and a cross-module panel with nothing to cross.
  const hasRegulatory = isIncluded("regulatory_hub")
  const hasSpectraCheck = isIncluded("spectracheck")
  const hasReaction = isIncluded("reaction_optimization")
  // A panel about how the products connect only means something when there are two to connect.
  const showCrossModule = [hasSpectraCheck, hasRegulatory, hasReaction].filter(Boolean).length >= 2
  const tenantContext = useTenant()
  const {
    currentTenantId,
    tenant,
    tenantDisplayName,
    isAdmin,
    moduleAccess,
  } = tenantContext
  const live = overview.metrics != null
  const metrics = overview.metrics
  const recentRows =
    overview.recentActivityMerged != null && overview.recentActivityMerged.length > 0
      ? overview.recentActivityMerged
      : overview.sessionsDataAvailable
        ? overview.recentActivity ?? NO_ACTIVITY_ROWS
        : NO_ACTIVITY_ROWS
  const jobRows = overview.jobsDataAvailable ? overview.recentJobs ?? NO_JOB_ROWS : NO_JOB_ROWS

  const wfSummaryDisplay =
    overview.workflowRunsDataAvailable && overview.workflowStatusSummary
      ? overview.workflowStatusSummary
      : { active: null, reviewRequired: null, failed: null, completed: null }

  const [qcLoading, setQcLoading] = useState(false)
  const [qcBackendAvailable, setQcBackendAvailable] = useState(false)
  const [qcWarnings, setQcWarnings] = useState<number | null>(null)
  const [qcFailures, setQcFailures] = useState<number | null>(null)
  const [qcSessionsReview, setQcSessionsReview] = useState<number | null>(null)
  const [qcRecentFailed, setQcRecentFailed] = useState<DashboardRecentFailedQcRow[]>(NO_QC_ROWS)

  const [viewerEmail, setViewerEmail] = useState<string | null>(null)
  const [collabLoading, setCollabLoading] = useState(false)
  const [collabRollup, setCollabRollup] = useState<Awaited<
    ReturnType<typeof fetchDashboardCollaborationAggregate>
  > | null>(null)

  const [methodHealthLoading, setMethodHealthLoading] = useState(false)
  const [methodHealthRollup, setMethodHealthRollup] = useState<DashboardMethodHealthRollup | null>(null)

  const [opsLoading, setOpsLoading] = useState(false)
  const [opsRollup, setOpsRollup] = useState<DashboardOperationsRollup | null>(null)

  const [roiLoading, setRoiLoading] = useState(false)
  const [roiSnapshot, setRoiSnapshot] = useState<RoiSnapshotData | null>(null)

  const [regulatoryLoading, setRegulatoryLoading] = useState(true)
  const [regulatorySummary, setRegulatorySummary] = useState<Awaited<
    ReturnType<typeof fetchDashboardRegulatorySummary>
  > | null>(null)

  const [regulatoryComplianceLoading, setRegulatoryComplianceLoading] = useState(true)
  const [regulatoryCompliance, setRegulatoryCompliance] = useState<RegulatoryComplianceCardData | null>(null)

  const [surveillanceLoading, setSurveillanceLoading] = useState(true)
  const [regulatorySurveillanceSummary, setRegulatorySurveillanceSummary] = useState<Awaited<
    ReturnType<typeof fetchDashboardRegulatorySurveillanceSummary>
  > | null>(null)

  const [crLoading, setCrLoading] = useState(true)
  const [crSummary, setCrSummary] = useState<Awaited<ReturnType<typeof fetchDashboardCompoundRegistrySummary>> | null>(
    null,
  )

  const [reactionLoading, setReactionLoading] = useState(true)
  const [reactionSummary, setReactionSummary] = useState<DashboardReactionSummary | null>(null)

  const [mlLoading, setMlLoading] = useState(true)
  const [mlRollup, setMlRollup] = useState<DashboardMlFactoryRollup | null>(null)
  const [aiSummaryLoading, setAiSummaryLoading] = useState(true)
  const [aiSummary, setAiSummary] = useState<DashboardAiInferenceSummary | null>(null)
  const [crossModuleLoading, setCrossModuleLoading] = useState(true)
  const [crossModuleSummary, setCrossModuleSummary] = useState<DashboardCrossModuleCommandCenter | null>(null)
  const [coreModuleActivityLoading, setCoreModuleActivityLoading] = useState(true)
  const [coreModuleActivity, setCoreModuleActivity] = useState<DashboardCoreModuleActivity | null>(null)
  const [connectorSummaryLoading, setConnectorSummaryLoading] = useState(true)
  const [connectorSummaryBackendUnavailable, setConnectorSummaryBackendUnavailable] = useState(false)
  const [connectorSummaryError, setConnectorSummaryError] = useState("")
  const [activeConnectors, setActiveConnectors] = useState<number | null>(null)
  const [ingestionRunsToday, setIngestionRunsToday] = useState<number | null>(null)
  const [failedIngestions, setFailedIngestions] = useState<number | null>(null)
  const [filesNeedNormalizationReview, setFilesNeedNormalizationReview] = useState<number | null>(null)
  const [failedSyncJobs, setFailedSyncJobs] = useState<number | null>(null)
  const [deploymentSummaryLoading, setDeploymentSummaryLoading] = useState(false)
  const [deploymentSummary, setDeploymentSummary] = useState<CustomerDeploymentSummary | null>(null)
  const [deploymentSummaryError, setDeploymentSummaryError] = useState("")
  const crossModuleDisplay = crossModuleSummary ?? {
    available: false,
    partial: false,
    sourceEndpoint: "/cross-module/command-center",
    spectracheckSummary: null,
    regulatorySummary: null,
    reactionSummary: null,
    latestSpectraCheckEvidenceStatus: null,
    linkedRegulatoryActionItems: null,
    openRegulatoryBlockers: null,
    reactionConstraintsCreated: null,
    optimizationRecommendationsAffectedByCompliance: null,
    openCrossModuleActionItems: null,
    warnings: [],
    nextRecommendedAction: null,
  }

  // Products this workspace serves, named the way the sidebar names them, for the copy that used
  // to list all three unconditionally.
  const includedProducts = useMemo(() => {
    const names: string[] = []
    if (hasSpectraCheck) names.push(MODULE_DISPLAY_NAMES.spectracheck)
    if (hasRegulatory) names.push(MODULE_DISPLAY_NAMES.regulatory_hub)
    if (hasReaction) names.push(MODULE_DISPLAY_NAMES.reaction_optimization)
    return names
  }, [hasSpectraCheck, hasRegulatory, hasReaction])
  const includedProductsSentence =
    includedProducts.length > 2
      ? `${includedProducts.slice(0, -1).join(", ")}, and ${includedProducts[includedProducts.length - 1]}`
      : includedProducts.length === 2
        ? `${includedProducts[0]} and ${includedProducts[1]}` // no comma before "and" for a pair
        : (includedProducts[0] ?? "the modules in this workspace")
  const crossModuleDescription = `How ${includedProductsSentence} connect.`

  // Activity is reported per module; keep only the ones this deployment serves so the count and
  // the tiles agree with what the workspace actually shows.
  const coreModuleActivityRows = useMemo(() => {
    const included: Record<DashboardCoreModuleKey, boolean> = {
      spectracheck: hasSpectraCheck,
      regulatory_hub: hasRegulatory,
      reactioniq: hasReaction,
    }
    return (coreModuleActivity?.rows ?? []).filter((row) => included[row.module])
  }, [coreModuleActivity, hasSpectraCheck, hasRegulatory, hasReaction])
  const coreModuleActivityTotal = coreModuleActivityRows.reduce((sum, row) => sum + row.count, 0)

  // Section eyebrows carry a running number, so it has to follow what is actually rendered —
  // hardcoded ones would read "01, 02, 04, 05" on a workspace without Regentry.
  const sectionEyebrow = useMemo(() => {
    const order = [
      "Dashboard",
      "Spectroscopy",
      ...(hasRegulatory ? ["Regulatory"] : []),
      ...(hasReaction ? ["Reactions"] : []),
      "Operations",
      "Activity",
    ]
    const out: Record<string, string> = {}
    order.forEach((label, i) => {
      out[label] = `${String(i + 1).padStart(2, "0")} · ${label}`
    })
    return out
  }, [hasRegulatory, hasReaction])

  const showCustomerDeploymentCard = isAdmin || tenant.tenant_type === "internal"

  useEffect(() => {
    if (!showCustomerDeploymentCard || !currentTenantId || currentTenantId === "local-development") {
      setDeploymentSummary(null)
      setDeploymentSummaryLoading(false)
      setDeploymentSummaryError("")
      return
    }

    let cancelled = false
    setDeploymentSummaryLoading(true)
    setDeploymentSummaryError("")

    async function loadDeploymentSummary() {
      const encodedTenantId = encodeURIComponent(currentTenantId)
      const [onboardingPayload, pilotsPayload, validationPayload, healthPayload] = await Promise.all([
        apiFetch<unknown>(`/tenants/${encodedTenantId}/onboarding-projects`, { method: "GET" }),
        apiFetch<unknown>(`/tenants/${encodedTenantId}/pilot-programs`, { method: "GET" }),
        apiFetch<unknown>(`/tenants/${encodedTenantId}/validation-profile`, { method: "GET" }),
        apiFetch<unknown>(`/tenants/${encodedTenantId}/health-score`, { method: "GET" }),
      ])

      const onboardingRows = asRows(onboardingPayload)
      const pilotRows = asRows(pilotsPayload)
      const validationProfile = isRecord(validationPayload) ? validationPayload : null
      const healthScore = isRecord(healthPayload) ? healthPayload : null
      const firstOnboarding = onboardingRows[0] ?? null
      let nextOnboardingTask = "—"

      if (firstOnboarding) {
        const projectId = readStr(firstOnboarding, ["id", "project_id", "onboarding_project_id"])
        if (projectId) {
          const taskPayload = await apiFetch<unknown>(`/onboarding-projects/${encodeURIComponent(projectId)}/tasks`, {
            method: "GET",
          })
          const tasks = asRows(taskPayload)
          const nextTask = tasks.find((task) => {
            const status = readStr(task, ["status"]).toLowerCase()
            return status === "open" || status === "in_progress" || status === "blocked"
          })
          nextOnboardingTask = nextTask ? readStr(nextTask, ["title"]) || "—" : "—"
        }
      }

      const healthScoreValue = healthScore ? readNum(healthScore, ["score"]) : null

      return {
        onboardingStatus: firstOnboarding ? readStr(firstOnboarding, ["status"]) || "—" : "—",
        pilotStatus: pilotRows[0] ? readStr(pilotRows[0], ["status"]) || "—" : "—",
        validationReadiness: validationProfile ? readStr(validationProfile, ["status"]) || "—" : "—",
        healthScore: healthScore
          ? healthScoreValue != null
            ? String(healthScoreValue)
            : readStr(healthScore, ["status"]) || "—"
          : "—",
        nextOnboardingTask,
      }
    }

    void loadDeploymentSummary()
      .then((summary) => {
        if (!cancelled) setDeploymentSummary(summary)
      })
      .catch((err) => {
        if (!cancelled) {
          setDeploymentSummary(null)
          setDeploymentSummaryError(
            formatApiErr(err) || "Onboarding and readiness details couldn't load right now.",
          )
        }
      })
      .finally(() => {
        if (!cancelled) setDeploymentSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [currentTenantId, showCustomerDeploymentCard])

  useEffect(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(AUTH_USER_STORAGE_KEY) : null
      if (!raw) return
      const o = JSON.parse(raw) as { email?: string }
      if (typeof o.email === "string" && o.email.trim()) setViewerEmail(o.email.trim())
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setConnectorSummaryLoading(true)
    setConnectorSummaryBackendUnavailable(false)
    setConnectorSummaryError("")

    void Promise.all([
      apiFetch<unknown>("/connectors", { method: "GET" }),
      apiFetch<unknown>("/ingestion-runs", { method: "GET" }),
      apiFetch<unknown>("/outbound-sync-jobs", { method: "GET" }),
    ])
      .then(([connectorsPayload, ingestionPayload, outboundSyncPayload]) => {
        if (cancelled) return
        const connectors = asRows(connectorsPayload)
        const ingestionRuns = asRows(ingestionPayload)
        const outboundSyncJobs = asRows(outboundSyncPayload)

        const activeConnectorCount = connectors.filter((row) => {
          const status = readStr(row, ["status", "health_status", "state"]).toLowerCase()
          return status === "active" || status === "enabled" || status === "connected" || status === "healthy"
        }).length

        const startOfToday = new Date()
        startOfToday.setHours(0, 0, 0, 0)
        const endOfToday = new Date(startOfToday)
        endOfToday.setDate(endOfToday.getDate() + 1)
        const createdTodayCount = ingestionRuns.filter((row) => {
          const ts =
            readStr(row, ["created_at", "started_at", "updated_at", "submitted_at"]) ||
            readStr(row, ["createdAt", "startedAt", "updatedAt", "submittedAt"])
          if (!ts) return false
          const ms = Date.parse(ts)
          return Number.isFinite(ms) && ms >= startOfToday.getTime() && ms < endOfToday.getTime()
        }).length

        const failedIngestionCount = ingestionRuns.filter((row) => {
          const status = readStr(row, ["status", "run_status"]).toLowerCase()
          return status === "failed" || status === "error"
        }).length

        const normalizationReviewCount = ingestionRuns.reduce((sum, row) => {
          const directCount = readNum(row, [
            "files_requiring_normalization_review",
            "normalization_review_required_count",
            "requires_normalization_review_count",
          ])
          if (directCount != null) return sum + Math.max(0, Math.floor(directCount))
          const normalizationStatus = readStr(row, ["normalization_status", "normalization_review_status"]).toLowerCase()
          return normalizationStatus === "review_required" ? sum + 1 : sum
        }, 0)

        const failedSyncCount = outboundSyncJobs.filter((row) => {
          const status = readStr(row, ["status", "job_status"]).toLowerCase()
          return status === "failed" || status === "error"
        }).length

        setActiveConnectors(activeConnectorCount)
        setIngestionRunsToday(createdTodayCount)
        setFailedIngestions(failedIngestionCount)
        setFilesNeedNormalizationReview(normalizationReviewCount)
        setFailedSyncJobs(failedSyncCount)
      })
      .catch((err) => {
        if (cancelled) return
        setConnectorSummaryBackendUnavailable(true)
        setConnectorSummaryError(formatApiErr(err))
      })
      .finally(() => {
        if (!cancelled) setConnectorSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    // "Cross-module" needs at least two modules to cross. On a single-product deployment the
    // panel is hidden, so don't pay for the request either.
    if (!showCrossModule) {
      setCrossModuleLoading(false)
      return
    }
    function readScopedId(row: unknown, keys: string[]): number | null {
      if (!row || typeof row !== "object" || Array.isArray(row)) return null
      const rec = row as Record<string, unknown>
      for (const key of keys) {
        const value = rec[key]
        if (typeof value === "number" && Number.isFinite(value)) return Math.floor(value)
        if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Math.floor(Number(value))
      }
      return null
    }

    const firstSession = overview.sessionsDataAvailable && overview.sessions.length > 0 ? overview.sessions[0] : null
    const projectId = readScopedId(firstSession, ["project_id", "reaction_project_id"])
    const compoundId = readScopedId(firstSession, ["compound_id", "linked_compound_id"])
    const batchId = readScopedId(firstSession, ["batch_id", "linked_batch_id"])
    let cancelled = false
    setCrossModuleLoading(true)
    void fetchDashboardCrossModuleCommandCenter({ projectId, compoundId, batchId })
      .then((summary) => {
        if (cancelled) return
        setCrossModuleSummary(summary)
      })
      .finally(() => {
        if (!cancelled) setCrossModuleLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [overview.sessionsDataAvailable, overview.sessions, showCrossModule])

  useEffect(() => {
    // Only rendered inside the cross-module card, so it follows the same gate.
    if (!showCrossModule) {
      setCoreModuleActivityLoading(false)
      return
    }
    let cancelled = false
    setCoreModuleActivityLoading(true)
    void fetchDashboardCoreModuleActivity()
      .then((activity) => {
        if (cancelled) return
        setCoreModuleActivity(activity)
      })
      .finally(() => {
        if (!cancelled) setCoreModuleActivityLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [showCrossModule])

  useEffect(() => {
    if (!overview.sessionsDataAvailable) {
      setCollabLoading(false)
      setCollabRollup(null)
      return
    }
    if (overview.sessions.length === 0) {
      setCollabLoading(false)
      setCollabRollup({
        available: true,
        partial: false,
        openReviewTasks: 0,
        commentsUnresolved: 0,
        reportsPendingApproval: 0,
        releasedReports: 0,
        assignedToMe: 0,
      })
      return
    }
    let cancelled = false
    setCollabLoading(true)
    void fetchDashboardCollaborationAggregate(overview.sessions, viewerEmail).then((agg) => {
      if (cancelled) return
      setCollabLoading(false)
      setCollabRollup(agg)
    })
    return () => {
      cancelled = true
    }
  }, [overview.sessionsDataAvailable, overview.sessions, viewerEmail])

  useEffect(() => {
    if (!overview.sessionsDataAvailable) {
      setQcLoading(false)
      setQcBackendAvailable(false)
      setQcWarnings(null)
      setQcFailures(null)
      setQcSessionsReview(null)
      setQcRecentFailed(NO_QC_ROWS)
      return
    }
    if (overview.sessions.length === 0) {
      setQcLoading(false)
      setQcBackendAvailable(true)
      setQcWarnings(0)
      setQcFailures(0)
      setQcSessionsReview(0)
      setQcRecentFailed(NO_QC_ROWS)
      return
    }
    let cancelled = false
    setQcLoading(true)
    void fetchDashboardQcAlertsAggregate(overview.sessions).then((res) => {
      if (cancelled) return
      setQcLoading(false)
      setQcBackendAvailable(res.available)
      if (res.available) {
        setQcWarnings(res.aggregate.qc_warnings_count)
        setQcFailures(res.aggregate.qc_failures_count)
        setQcSessionsReview(res.aggregate.sessions_requiring_qc_review)
        setQcRecentFailed(res.aggregate.recent_failed_qc_items)
      } else {
        setQcWarnings(null)
        setQcFailures(null)
        setQcSessionsReview(null)
        setQcRecentFailed(NO_QC_ROWS)
      }
    })
    return () => {
      cancelled = true
    }
  }, [overview.sessionsDataAvailable, overview.sessions])

  useEffect(() => {
    let cancelled = false
    setMethodHealthLoading(true)
    void fetchDashboardMethodHealthAggregate().then((agg) => {
      if (cancelled) return
      setMethodHealthRollup(agg)
      setMethodHealthLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setOpsLoading(true)
    void fetchDashboardOperationsSummary().then((rollup) => {
      if (cancelled) return
      setOpsRollup(rollup)
      setOpsLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setRoiLoading(true)
    void fetchDashboardRoiSnapshot().then((snap) => {
      if (cancelled) return
      setRoiSnapshot(snap)
      setRoiLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // The three regulatory fetches below back a section this deployment may not serve. Skip them
  // rather than let them be refused, and clear "loading" so the section never sits on a spinner.
  useEffect(() => {
    if (!hasRegulatory) {
      setRegulatoryLoading(false)
      return
    }
    let cancelled = false
    setRegulatoryLoading(true)
    void fetchDashboardRegulatorySummary().then((summary) => {
      if (cancelled) return
      setRegulatorySummary(summary)
      setRegulatoryLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [hasRegulatory])

  useEffect(() => {
    if (!hasRegulatory) {
      setRegulatoryComplianceLoading(false)
      return
    }
    let cancelled = false
    setRegulatoryComplianceLoading(true)
    void fetchRegulatoryComplianceCardData().then((data) => {
      if (cancelled) return
      setRegulatoryCompliance(data)
      setRegulatoryComplianceLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [hasRegulatory])

  useEffect(() => {
    if (!hasRegulatory) {
      setSurveillanceLoading(false)
      return
    }
    let cancelled = false
    setSurveillanceLoading(true)
    void fetchDashboardRegulatorySurveillanceSummary().then((data) => {
      if (cancelled) return
      setRegulatorySurveillanceSummary(data)
      setSurveillanceLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [hasRegulatory])

  useEffect(() => {
    if (!hasReaction) {
      setReactionLoading(false)
      return
    }
    let cancelled = false
    setReactionLoading(true)
    void fetchDashboardReactionSummary().then((summary) => {
      if (cancelled) return
      setReactionSummary(summary)
      setReactionLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [hasReaction])

  useEffect(() => {
    let cancelled = false
    setCrLoading(true)
    void fetchDashboardCompoundRegistrySummary().then((summary) => {
      if (cancelled) return
      setCrSummary(summary)
      setCrLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setMlLoading(true)
    void fetchDashboardMlFactoryRollup()
      .then((rollup) => {
        if (cancelled) return
        setMlRollup(rollup)
      })
      .finally(() => {
        if (!cancelled) setMlLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setAiSummaryLoading(true)
    void fetchDashboardAiInferenceSummary()
      .then((rollup) => {
        if (cancelled) return
        setAiSummary(rollup)
      })
      .finally(() => {
        if (!cancelled) setAiSummaryLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const activeSub =
    !live || !metrics
      ? <UnavailableSub what="analysis data" />
      : overview.jobsDataAvailable
        ? (
            <>
              <p className="text-xs text-muted-foreground">Live analysis jobs</p>
              <p className="text-xs text-muted-foreground">
                {metrics.jobsCompleted ?? 0} completed · {metrics.jobsFailed ?? 0} failed
              </p>
            </>
          )
        : (
            <p className="text-xs text-muted-foreground">From saved SpectraCheck sessions</p>
          )

  const reviewSub =
    live && metrics ? (
      <p className="text-xs text-muted-foreground">
        {metrics.reviewRequired > 0
          ? metrics.reviewRequiredWithContradictions > 0
            ? `${metrics.reviewRequiredWithContradictions} with contradictions`
            : "Sessions awaiting review"
          : "None pending"}
      </p>
    ) : (
      <UnavailableSub what="review data" />
    )

  /* The mean confidence of the sessions actually on screen, or null.
   *
   * `confidenceFromSession` yields 0 for a session that reports no confidence
   * at all, so averaging the raw column would silently drag the mean toward
   * zero in proportion to how much data is MISSING -- a number that responds to
   * coverage while looking like it responds to quality. Sessions without a
   * score are excluded and the denominator is reported instead. */
  /* The mean confidence of the sessions actually on screen, or null.
   *
   * `confidenceFromSession` yields 0 for a session that reports no confidence at
   * all, so averaging the raw column would drag the mean toward zero in
   * proportion to how much data is MISSING -- a number that responds to coverage
   * while looking like it responds to quality. Sessions without a score are
   * excluded and the denominator is reported instead. */
  const meanConfidence = useMemo(() => {
    const scored = recentRows.filter(
      (row) => typeof row.confidence === "number" && row.confidence > 0,
    )
    if (scored.length === 0) return null
    const total = scored.reduce((acc, row) => acc + row.confidence, 0)
    return {
      value: Math.round(total / scored.length),
      count: scored.length,
      total: recentRows.length,
    }
  }, [recentRows])

  const reportsSub = live ? (
    <p className="text-xs text-muted-foreground">Approved or saved reports</p>
  ) : (
    <UnavailableSub what="report data" />
  )

  const collabUseDemoRest =
    !overview.sessionsDataAvailable ||
    collabLoading ||
    (overview.sessions.length > 0 && collabRollup != null && !collabRollup.available)

  const NO_COLLAB_ROLLUP = {
    openReviewTasks: null,
    commentsUnresolved: null,
    reportsPendingApproval: null,
    releasedReports: null,
    assignedToMe: null,
  }
  const collabRestDisplay = collabUseDemoRest
    ? NO_COLLAB_ROLLUP
    : collabRollup ?? NO_COLLAB_ROLLUP

  // null, not 0: "no sessions need review" and "we could not find out" are
  // different answers, and only one of them should colour the card.
  const reviewRequiredCount = live && metrics ? metrics.reviewRequired : null
  const reviewRequiredForCollabCard = reviewRequiredCount

  /* No demo branch. The shape below already yields null for every field when
     the rollup is missing, which is the truthful answer; the demo object simply
     sat on top of it claiming 12 active methods and a validation run that had
     "succeeded". */
  const methodHealthUnavailable =
    !methodHealthLoading && (methodHealthRollup == null || !methodHealthRollup.available)

  const methodHealthDisplay = {
        activeMethods: methodHealthRollup?.activeMethods ?? null,
        experimentalMethods: methodHealthRollup?.experimentalMethods ?? null,
        deprecatedMethods: methodHealthRollup?.deprecatedMethods ?? null,
        openDriftAlerts: methodHealthRollup?.openDriftAlerts ?? null,
        latestValidationRunStatus: methodHealthRollup?.latestValidationRunStatus ?? null,
      }

  /* Likewise, and this one mattered most: the demo object reported
     systemHealthStatus "healthy" precisely when the health endpoint could not be
     reached. A fabricated count is wrong; a fabricated green light is wrong in
     the reassuring direction, on the signal a reviewer would act on. */
  const opsUnavailable = !opsLoading && (opsRollup == null || !opsRollup.available)

  const opsDisplay = {
        systemHealthStatus: opsRollup?.systemHealthStatus ?? null,
        activeJobs: opsRollup?.activeJobs ?? null,
        failedJobs: opsRollup?.failedJobs ?? null,
        securityWarnings: opsRollup?.securityWarnings ?? null,
        openDriftAlerts: opsRollup?.openDriftAlerts ?? null,
      }

  function fmtOpsHealth(status: string | null): string {
    return statusLabel(status)
  }

  /* Each of the four summaries below arrives as a discriminated union, so a card
     that reads its fields directly can only render once the data is available —
     which is why the Science and Regulatory sections used to open onto nothing.
     Flattening to a nullable shape lets every card render its own layout up
     front and fill in "—" where a value is still unknown. */
  const regulatoryDisplay = regulatorySummary?.available
    ? {
        activeDossiers: regulatorySummary.activeDossiers as number | null,
        inReview: regulatorySummary.inReview as number | null,
        reqsNeedEvidence: regulatorySummary.reqsNeedEvidence as number | null,
        highRisk: regulatorySummary.highRisk as number | null,
      }
    : { activeDossiers: null, inReview: null, reqsNeedEvidence: null, highRisk: null }

  const complianceDisplay = regulatoryCompliance?.available
    ? {
        openActionItems: regulatoryCompliance.openActionItems as number | null,
        criticalActionItems: regulatoryCompliance.criticalActionItems as number | null,
        blockedDossiers: regulatoryCompliance.blockedDossiers as number | null,
        qNmrGaps: regulatoryCompliance.qNmrGaps as number | null,
        nitrosamineReviewItems: regulatoryCompliance.nitrosamineReviewItems as number | null,
      }
    : {
        openActionItems: null,
        criticalActionItems: null,
        blockedDossiers: null,
        qNmrGaps: null,
        nitrosamineReviewItems: null,
      }

  const surveillanceDisplay = regulatorySurveillanceSummary?.available
    ? {
        changesDetected: regulatorySurveillanceSummary.changesDetected as number | null,
        highImpactChanges: regulatorySurveillanceSummary.highImpactChanges as number | null,
        dossiersAffected: regulatorySurveillanceSummary.dossiersAffected as number | null,
        pendingRuleUpdateProposals: regulatorySurveillanceSummary.pendingRuleUpdateProposals as number | null,
        unreadRegulatoryNotifications: regulatorySurveillanceSummary.unreadRegulatoryNotifications as number | null,
      }
    : {
        changesDetected: null,
        highImpactChanges: null,
        dossiersAffected: null,
        pendingRuleUpdateProposals: null,
        unreadRegulatoryNotifications: null,
      }

  const reactionDisplay = reactionSummary?.available
    ? {
        totalProjects: reactionSummary.totalProjects as number | null,
        activeProjects: reactionSummary.activeProjects as number | null,
        draftProjects: reactionSummary.draftProjects as number | null,
        completedProjects: reactionSummary.completedProjects as number | null,
        latestProjectId: reactionSummary.latestProjectId,
        latestProjectName: reactionSummary.latestProjectName,
      }
    : {
        totalProjects: null,
        activeProjects: null,
        draftProjects: null,
        completedProjects: null,
        latestProjectId: null,
        latestProjectName: null,
      }

  const compoundRegistryDisplay = crSummary?.available
    ? {
        activeCompounds: crSummary.activeCompounds as number | null,
        activeBatches: crSummary.activeBatches,
        compoundsNeedingReview: crSummary.compoundsNeedingReview as number | null,
        evidenceLinkedCompounds: crSummary.evidenceLinkedCompounds as number | null,
        partial: crSummary.partial === true,
      }
    : {
        activeCompounds: null,
        activeBatches: null,
        compoundsNeedingReview: null,
        evidenceLinkedCompounds: null,
        partial: false,
      }

  const roiLive = roiSnapshot != null
  const hoursSavedDisplay = roiLoading
    ? "…"
    : roiLive
      ? roiSnapshot.total_hours_saved.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 })
      : UNAVAILABLE_VALUE

  function fmtRoiInt(n: number | null | undefined): string {
    if (roiLoading) return "…"
    if (!roiLive || n == null) return "—"
    return String(Math.round(n))
  }

  type ActivityStatusFilter = "all" | DashboardActivityRow["status"]
  type JobsStatusFilter = "all" | "running" | "queued" | "succeeded" | "failed"

  const [activityFilter, setActivityFilter] = useState<ActivityStatusFilter>("all")
  const [jobsFilter, setJobsFilter] = useState<JobsStatusFilter>("all")

  const activityStatusCounts = useMemo(() => {
    const counts = { approved: 0, review: 0, running: 0, contradiction: 0 }
    for (const row of recentRows) counts[row.status]++
    return counts
  }, [recentRows])

  const jobsStatusCounts = useMemo(() => {
    const counts: Record<JobsStatusFilter, number> = {
      all: 0,
      running: 0,
      queued: 0,
      succeeded: 0,
      failed: 0,
    }
    for (const j of jobRows) {
      const s = j.status.toLowerCase()
      if (s === "running") counts.running++
      else if (s === "queued" || s === "pending") counts.queued++
      else if (s === "succeeded" || s === "completed" || s === "success") counts.succeeded++
      else if (s === "failed" || s === "error") counts.failed++
    }
    return counts
  }, [jobRows])

  const filteredActivityRows = useMemo(
    () => (activityFilter === "all" ? recentRows : recentRows.filter((r) => r.status === activityFilter)),
    [recentRows, activityFilter],
  )

  const filteredJobRows = useMemo(() => {
    if (jobsFilter === "all") return jobRows
    return jobRows.filter((j) => {
      const s = j.status.toLowerCase()
      if (jobsFilter === "running") return s === "running"
      if (jobsFilter === "queued") return s === "queued" || s === "pending"
      if (jobsFilter === "succeeded") return s === "succeeded" || s === "completed" || s === "success"
      if (jobsFilter === "failed") return s === "failed" || s === "error"
      return true
    })
  }, [jobRows, jobsFilter])

  const priorities = useMemo<DashboardPriority[]>(() => {
    const items: DashboardPriority[] = []

    if (regulatoryCompliance?.available && regulatoryCompliance.criticalActionItems > 0) {
      const n = regulatoryCompliance.criticalActionItems
      items.push({
        severity: "critical",
        text: `${n} critical compliance ${n === 1 ? "item" : "items"} need attention`,
        href: "/regulatory",
        cta: "Open regulatory",
      })
    }

    if (qcBackendAvailable && qcFailures != null && qcFailures > 0) {
      items.push({
        severity: "warning",
        text: `${qcFailures} QC ${qcFailures === 1 ? "failure" : "failures"} across recent sessions`,
        href: "/spectracheck",
        cta: "Open SpectraCheck",
      })
    }

    if (live && metrics && metrics.reviewRequired > 0) {
      const n = metrics.reviewRequired
      items.push({
        severity: "warning",
        text: `${n} ${n === 1 ? "analysis" : "analyses"} awaiting review`,
        href: "/review",
        cta: "Open reviews",
      })
    }

    if (opsRollup?.available && (opsRollup.failedJobs ?? 0) > 0) {
      const n = opsRollup.failedJobs as number
      items.push({
        severity: "warning",
        text: `${n} ${n === 1 ? "job" : "jobs"} failed recently`,
        href: "/dashboard",
        cta: "View jobs",
      })
    }

    return items
  }, [regulatoryCompliance, qcBackendAvailable, qcFailures, live, metrics, opsRollup])

  /* Header pills, so a section that a reader has collapsed still reports what is
     happening inside it — on a phone that is often the only thing on screen. */
  const overviewSignals = compactSignals([
    countSignal(live && metrics ? metrics.activeAnalyses : null, "active"),
    countSignal(reviewRequiredCount, "to review", "warning"),
    countSignal(live && metrics ? metrics.reportsReady : null, "reports ready", "info"),
  ])

  const scienceSignals = compactSignals([
    countSignal(mlRollup?.activeModelCount, "models serving", "info"),
    countSignal(aiSummary?.predictionsRequiringReview, "predictions to review", "warning"),
    countSignal(compoundRegistryDisplay.activeCompounds, "compounds"),
    countSignal(coreModuleActivity?.available ? coreModuleActivityTotal : null, "module opens"),
  ])

  const reactionSignals = compactSignals([
    countSignal(reactionDisplay.activeProjects, "active projects"),
    countSignal(reactionDisplay.draftProjects, "drafts", "info"),
  ])

  const regulatorySignals = compactSignals([
    countSignal(regulatoryDisplay.activeDossiers, "dossiers"),
    countSignal(complianceDisplay.openActionItems, "open items", "warning"),
    countSignal(complianceDisplay.criticalActionItems, "critical", "critical"),
    countSignal(surveillanceDisplay.highImpactChanges, "high-impact changes", "warning"),
  ])

  const operationsSignals = compactSignals([
    opsDisplay.systemHealthStatus
      ? {
          label: fmtOpsHealth(opsDisplay.systemHealthStatus),
          tone:
            opsDisplay.systemHealthStatus.toLowerCase() === "healthy"
              ? ("positive" as const)
              : ("warning" as const),
        }
      : null,
    countSignal(opsDisplay.activeJobs, "active jobs", "info"),
    countSignal(opsDisplay.failedJobs, "failed", "critical"),
    countSignal(qcFailures, "QC failures", "critical"),
  ])

  const activitySignals = compactSignals([
    countSignal(recentRows.length, "analyses"),
    countSignal(jobRows.length, "jobs"),
    countSignal(activityStatusCounts.contradiction, "contradictions", "critical"),
  ])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <DashboardGreeting
          email={viewerEmail}
          tenantName={tenantDisplayName}
          eyebrow="MolTrace · Dashboard"
        />
        <BackendStatusIndicator />
      </div>

      <DashboardPriorityCallout priorities={priorities} />

      {isMobile ? (
        <MobileCommandCenter />
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => setAllDashboardSectionsOpen(true)}
          className="inline-flex min-h-9 items-center rounded-md border px-3 font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
        >
          Expand all
        </button>
        <button
          type="button"
          onClick={() => setAllDashboardSectionsOpen(false)}
          className="inline-flex min-h-9 items-center rounded-md border px-3 font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
        >
          Collapse all
        </button>
      </div>

      <DashboardSection
        title="Overview"
        description="Top metrics, validation readiness, and tenant onboarding."
        icon={LayoutDashboard}
        accent="teal"
        eyebrow={sectionEyebrow.Dashboard}
        storageKey="overview"
        signals={overviewSignals}
        defaultOpen
      >
      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <KpiCard
          title="Active Analyses"
          icon={Activity}
          href="/spectracheck"
          accent="teal"
          value={live && metrics ? metrics.activeAnalyses : UNAVAILABLE_VALUE}
          sub={
            <>
              {activeSub}
              {overview.workflowRunsDataAvailable && overview.workflowStatusSummary ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Workflows active (queued / running): {overview.workflowStatusSummary.active}
                </p>
              ) : null}
            </>
          }
        />

        <KpiCard
          title="Review Required"
          icon={AlertCircle}
          href="/review"
          accent="cyan"
          severity={reviewRequiredCount != null && reviewRequiredCount > 0 ? "warning" : "neutral"}
          value={reviewRequiredCount ?? UNAVAILABLE_VALUE}
          sub={
            <>
              {reviewSub}
              {overview.workflowRunsDataAvailable && overview.workflowStatusSummary ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Workflows requiring review: {overview.workflowStatusSummary.reviewRequired}
                </p>
              ) : null}
            </>
          }
        />

        <KpiCard
          title="Reports Ready"
          icon={FileText}
          href="/reports"
          accent="cyan"
          value={live && metrics ? metrics.reportsReady : UNAVAILABLE_VALUE}
          sub={reportsSub}
        />

        {/* "Hours saved" is Σ(completed tasks × a fixed per-task constant), not a measured
            duration — the ORM column is `estimated_minutes_saved` and the API model drops the
            qualifier on the way out. So the qualifier goes back on here, and the basis stays
            one click away. The counts on the other tiles are real event counts. */}
        <KpiCard
          title="Hours Saved (estimated)"
          icon={Clock}
          href="/roi"
          accent="violet"
          value={hoursSavedDisplay}
          sub={
            roiLoading ? (
              <p className="mt-1 text-xs text-muted-foreground">Loading ROI snapshot…</p>
            ) : roiLive ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Estimated from your per-task time-saved assumptions, not measured.
              </p>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">
                Live ROI data couldn&apos;t load, so there is no total to show.
              </p>
            )
          }
        />

        {/* Was "Model Confidence", hard-coded to 94.2 % with no live branch at
            all -- not a fallback, a permanent fiction, and an overclaim twice
            over: no model-confidence metric exists anywhere in the product, and
            a mean of per-session scores would not be model accuracy if it did.
            Now the mean of the confidence the sessions in view actually report,
            named for what it is and carrying its denominator, because a mean
            over an unstated subset is the defect this codebase keeps finding. */}
        <KpiCard
          title="Mean Session Confidence"
          icon={TrendingUp}
          href="/ml"
          accent="teal"
          value={meanConfidence == null ? UNAVAILABLE_VALUE : `${meanConfidence.value}%`}
          sub={
            meanConfidence == null ? (
              <UnavailableSub what="session confidence" />
            ) : (
              <>
                <Progress value={meanConfidence.value} className="mt-2 h-1.5" />
                <p className="mt-1 text-xs text-muted-foreground">
                  Across {meanConfidence.count} of {meanConfidence.total} recent sessions that
                  report one
                </p>
              </>
            )
          }
        />
      </div>

      <ValidationReadinessDashboardCards />

      {/* The golden path spans all three products, so it sits in Overview rather than under any
          one module — it is the thing that makes them one arc instead of three screens. */}
      <GoldenPathCard />

      {showCustomerDeploymentCard ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle className="text-base">Customer Deployment</CardTitle>
                <CardDescription>Tenant onboarding and readiness summary.</CardDescription>
              </div>
              <Badge variant="outline">{statusLabel(tenant.status)}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {deploymentSummaryError ? <p className="text-xs text-muted-foreground">{deploymentSummaryError}</p> : null}
            {deploymentSummaryLoading ? <p className="text-xs text-muted-foreground">Loading deployment summary…</p> : null}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
              <div>
                <p className="text-xs text-muted-foreground">tenant</p>
                <p className="font-medium">{tenantDisplayName}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">onboarding status</p>
                <p className="font-medium">{statusLabel(deploymentSummary?.onboardingStatus)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">pilot status</p>
                <p className="font-medium">{statusLabel(deploymentSummary?.pilotStatus)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">validation readiness</p>
                <p className="font-medium">{statusLabel(deploymentSummary?.validationReadiness)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">health score</p>
                <p className="font-medium">{statusLabel(deploymentSummary?.healthScore)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">next onboarding task</p>
                <p className="font-medium">{deploymentSummary?.nextOnboardingTask ?? "—"}</p>
              </div>
            </div>
            {/* Order only. The "licensed / not licensed" badge that used to sit on each
                tile read tenant entitlement rows, which enforce nothing — see the note in
                `components/app/tenant-selector.tsx`. */}
            <div className="grid gap-2 sm:grid-cols-3">
              {moduleAccess.map((module, index) => (
                <div key={module.key} className="rounded-md border bg-muted/20 px-3 py-2">
                  <span>
                    {index + 1}. {module.label}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      </DashboardSection>

      <DashboardSection
        title="Science"
        description="Methods, compounds, ML and AI summaries."
        icon={Microscope}
        accent="teal"
        eyebrow={sectionEyebrow.Spectroscopy}
        storageKey="science"
        signals={scienceSignals}
        defaultOpen
      >
        <ModuleCard
          accent="teal"
          eyebrow="Spectroscopy · ML"
          title="ML factory health"
          icon={Cpu}
          description="Review status of the models powering your analyses."
          href="/ml"
          ctaLabel="Open ML Model Factory"
        >
          {mlLoading ? (
            <p className="text-xs text-muted-foreground">Loading ML model health…</p>
          ) : null}
          {!mlLoading && !mlRollup?.available ? (
            <p className="text-xs text-muted-foreground">
              Live ML model health isn't available right now.
            </p>
          ) : null}
          {!mlLoading && mlRollup?.available && mlRollup.partial ? (
            <p className="text-xs text-muted-foreground">
              Some live data didn't load — values may be partial.
            </p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Active serving configs</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.activeModelCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Approved deployment candidates</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.approvedDeploymentCandidateCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Models / deployment review queue</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.modelsRequiringReviewHint)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Failed evaluations</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.failedEvaluationsCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Open deployment candidates</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.openDeploymentCandidatesCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Error-analysis warning signals</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.errorAnalysisWarningsHint)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Drift / dataset warning signals</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(mlRollup?.driftWarningsHint)}</p>
            </div>
          </div>
        </ModuleCard>

        <ModuleCard
          accent="teal"
          eyebrow="Spectroscopy · AI"
          title="AI inference summary"
          icon={Cpu}
          description="Live AI predictions and the active-learning queue across your tenant."
          href="/ai"
          ctaLabel="Open AI Services"
        >
          {aiSummaryLoading ? (
            <p className="text-xs text-muted-foreground">Loading AI inference summary…</p>
          ) : null}
          {!aiSummaryLoading && !aiSummary?.available ? (
            <p className="text-xs text-muted-foreground">
              Live AI inference data isn't available right now.
            </p>
          ) : null}
          {!aiSummaryLoading && aiSummary?.available && aiSummary.partial ? (
            <p className="text-xs text-muted-foreground">
              Some AI live data didn't load — values may be partial.
            </p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Active AI services</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(aiSummary?.activeAiServices)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Predictions requiring review</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(aiSummary?.predictionsRequiringReview)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Low-confidence predictions</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(aiSummary?.lowConfidencePredictions)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">OOD predictions</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(aiSummary?.oodPredictions)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Active-learning candidates</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(aiSummary?.activeLearningCandidates)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Service failures</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(aiSummary?.serviceFailures)}</p>
            </div>
          </div>
        </ModuleCard>

      {showCrossModule ? (
      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">Cross-Module Command Center</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </div>
          <CardDescription>
            {crossModuleDescription} Draft summary — review before action.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {/* One tile per product this deployment serves. A tile for an absent product could only
              ever read "—", which looks like missing data rather than a product you don't have. */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {hasSpectraCheck ? (
            <div className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">SpectraCheck summary</p>
              <p className="mt-2 text-xs text-muted-foreground">latest SpectraCheck evidence status</p>
              <p className="text-sm font-medium">
                {statusLabel(crossModuleDisplay.latestSpectraCheckEvidenceStatus)}
              </p>
            </div>
            ) : null}
            {hasRegulatory ? (
            <div className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">Regentry summary</p>
              <p className="mt-2 text-xs text-muted-foreground">linked regulatory action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(crossModuleDisplay.linkedRegulatoryActionItems)}</p>
              <p className="mt-2 text-xs text-muted-foreground">open regulatory blockers</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(crossModuleDisplay.openRegulatoryBlockers)}</p>
            </div>
            ) : null}
            {hasReaction ? (
            <div className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">Repho summary</p>
              <p className="mt-2 text-xs text-muted-foreground">reaction constraints created</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(crossModuleDisplay.reactionConstraintsCreated)}</p>
              <p className="mt-2 text-xs text-muted-foreground">recommendations affected by compliance</p>
              <p className="text-2xl font-bold tabular-nums">
                {fmtCount(crossModuleDisplay.optimizationRecommendationsAffectedByCompliance)}
              </p>
            </div>
            ) : null}
          </div>
          <div className="rounded-md border bg-card p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-medium uppercase text-muted-foreground">Core module activity</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Live opens logged from {includedProductsSentence} in this testing phase.
                </p>
              </div>
              <Badge variant="outline" className="w-fit">
                {coreModuleActivityLoading ? "Loading" : `${coreModuleActivityTotal} opens`}
              </Badge>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {coreModuleActivityRows.map((row) => (
                <div key={row.module} className="rounded-md border bg-muted/20 px-3 py-2">
                  <p className="text-xs text-muted-foreground">{row.label}</p>
                  <p className="text-2xl font-bold tabular-nums">{row.count}</p>
                  <p className="text-[11px] text-muted-foreground">{formatCoreModuleActivityTime(row.latestAt)}</p>
                </div>
              ))}
            </div>
            {coreModuleActivityLoading ? (
              <p className="mt-3 text-xs text-muted-foreground">Loading core module activity…</p>
            ) : null}
            {!coreModuleActivityLoading && coreModuleActivity && !coreModuleActivity.available ? (
              <p className="mt-3 text-xs text-muted-foreground">Live module activity isn't available right now.</p>
            ) : null}
            {!coreModuleActivityLoading && coreModuleActivity?.available && coreModuleActivityTotal === 0 ? (
              <p className="mt-3 text-xs text-muted-foreground">Nothing logged yet.</p>
            ) : null}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border bg-card p-3">
              <p className="text-xs text-muted-foreground">Open cross-module action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(crossModuleDisplay.openCrossModuleActionItems)}</p>
            </div>
            <div className="rounded-md border bg-card p-3">
              <p className="text-xs text-muted-foreground">Next recommended action</p>
              <p className="mt-1 text-sm">{crossModuleDisplay.nextRecommendedAction ?? "—"}</p>
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">warnings</p>
            {crossModuleDisplay.warnings.length > 0 ? (
              <ul className="list-inside list-disc text-xs text-muted-foreground">
                {crossModuleDisplay.warnings.map((warning, i) => (
                  <li key={`${warning}-${i}`}>{warning}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">—</p>
            )}
          </div>
          {crossModuleLoading ? (
            <p className="text-xs text-muted-foreground">Loading cross-module command center summary…</p>
          ) : null}
          {!crossModuleLoading && !crossModuleDisplay.available ? (
            <p className="text-xs text-muted-foreground">Live cross-module summary isn't available right now.</p>
          ) : null}
        </CardContent>
      </Card>
      ) : null}

        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Compound Registry</CardTitle>
              <Microscope className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardDescription>
              Compounds and batches — traceability counts only, not identity or
              release certification.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Active compounds</p>
                <p className="text-2xl font-bold tabular-nums">
                  {fmtCount(compoundRegistryDisplay.activeCompounds)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Active batches</p>
                <p className="text-2xl font-bold tabular-nums">
                  {fmtCount(compoundRegistryDisplay.activeBatches)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Compounds needing review</p>
                <p className="text-2xl font-bold tabular-nums">
                  {fmtCount(compoundRegistryDisplay.compoundsNeedingReview)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Evidence-linked compounds</p>
                <p className="text-2xl font-bold tabular-nums">
                  {fmtCount(compoundRegistryDisplay.evidenceLinkedCompounds)}
                </p>
              </div>
            </div>
            {crLoading ? (
              <p className="text-xs text-muted-foreground">Loading compound registry summary…</p>
            ) : null}
            {!crLoading && !crSummary?.available ? (
              <p className="text-xs text-muted-foreground">
                Live compound registry data isn't available right now.
              </p>
            ) : null}
            {!crLoading && compoundRegistryDisplay.partial ? (
              <p className="text-xs text-muted-foreground">
                Batch summary didn't load — active batch count is hidden until it does.
              </p>
            ) : null}
            <p className="flex flex-wrap gap-x-4 gap-y-1">
              <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/compounds">
                Open Compounds
              </Link>
              <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/batches">
                Open Batches
              </Link>
            </p>
          </CardContent>
        </Card>

      </DashboardSection>

      {/* Whole section belongs to Regentry — drop it rather than open it onto empty cards. */}
      {hasRegulatory ? (
      <DashboardSection
        title="Regulatory"
        description="Dossiers, compliance, surveillance, and notifications."
        icon={ShieldCheck}
        accent="cyan"
        eyebrow={sectionEyebrow.Regulatory}
        storageKey="regulatory"
        signals={regulatorySignals}
        defaultOpen
      >
        <ModuleCard
          accent="cyan"
          eyebrow="Regulatory · Hub"
          title="Regentry"
          icon={FolderOpen}
          description="Active dossiers and review workload — not a legal or compliance certification."
          href="/regulatory"
          ctaLabel="Open Regentry"
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Active dossiers</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(regulatoryDisplay.activeDossiers)}</p>
              <p className="text-xs text-muted-foreground">Excludes archived.</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Dossiers in review</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(regulatoryDisplay.inReview)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Requirements needing evidence</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(regulatoryDisplay.reqsNeedEvidence)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">High-risk dossiers</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(regulatoryDisplay.highRisk)}</p>
              <p className="text-xs text-muted-foreground">Latest risk assessment high or critical.</p>
            </div>
          </div>
          {regulatoryLoading ? (
            <p className="text-xs text-muted-foreground">Loading dossier summary…</p>
          ) : null}
          {!regulatoryLoading && !regulatorySummary?.available ? (
            <p className="text-xs text-muted-foreground">Live dossier data isn't available right now.</p>
          ) : null}
        </ModuleCard>

        <ModuleCard
          accent="cyan"
          eyebrow="Regulatory · Compliance"
          title="Regulatory compliance"
          icon={AlertTriangle}
          description="Open action items, blocked dossiers, and triage by category — workflow signals, not legal conclusions."
          href="/regulatory"
          ctaLabel="Open regulatory workspace"
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <p className="text-xs text-muted-foreground">Open action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(complianceDisplay.openActionItems)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Critical action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(complianceDisplay.criticalActionItems)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Dossiers blocked</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(complianceDisplay.blockedDossiers)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">qNMR gaps (open items)</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(complianceDisplay.qNmrGaps)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Nitrosamine review items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(complianceDisplay.nitrosamineReviewItems)}</p>
            </div>
          </div>
          {regulatoryComplianceLoading ? (
            <p className="text-xs text-muted-foreground">Loading compliance summary…</p>
          ) : null}
          {!regulatoryComplianceLoading && !regulatoryCompliance?.available ? (
            <p className="text-xs text-muted-foreground">Live compliance data isn't available right now.</p>
          ) : null}
        </ModuleCard>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Regulatory Surveillance</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardDescription>
              External rule changes, dossiers affected, and pending rule-update proposals.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <p className="text-xs text-muted-foreground">Source changes detected</p>
                <p className="text-2xl font-bold tabular-nums">{fmtCount(surveillanceDisplay.changesDetected)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">High-impact changes</p>
                <p className="text-2xl font-bold tabular-nums">{fmtCount(surveillanceDisplay.highImpactChanges)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Dossiers affected</p>
                <p className="text-2xl font-bold tabular-nums">{fmtCount(surveillanceDisplay.dossiersAffected)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Pending rule update proposals</p>
                <p className="text-2xl font-bold tabular-nums">
                  {fmtCount(surveillanceDisplay.pendingRuleUpdateProposals)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Unread regulatory notifications</p>
                <p className="text-2xl font-bold tabular-nums">
                  {fmtCount(surveillanceDisplay.unreadRegulatoryNotifications)}
                </p>
              </div>
            </div>
            {surveillanceLoading ? (
              <p className="text-xs text-muted-foreground">Loading regulatory surveillance summary…</p>
            ) : null}
            {!surveillanceLoading && !regulatorySurveillanceSummary?.available ? (
              <p className="text-xs text-muted-foreground">
                Live regulatory surveillance data isn't available right now.
              </p>
            ) : null}
            <p>
              <Link
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                href="/regulatory/surveillance"
              >
                Open Regulatory Surveillance
              </Link>
            </p>
          </CardContent>
        </Card>

      <RegulatoryNotificationsCompactCard />

      </DashboardSection>
      ) : null}

      {/* Repho had no dashboard presence at all, so a reaction-only workspace opened onto a page
          about other people's products. Deliberately a way back into the work rather than a
          restatement of optimization results, which only read correctly inside a project. */}
      {hasReaction ? (
      <DashboardSection
        title="Reactions"
        description="Reaction optimization projects in flight."
        icon={FlaskConical}
        accent="violet"
        eyebrow={sectionEyebrow.Reactions}
        storageKey="reactions"
        signals={reactionSignals}
        defaultOpen
      >
        <ModuleCard
          accent="violet"
          eyebrow="Reactions · Optimization"
          title="Repho"
          icon={FlaskConical}
          description="Your reaction optimization projects — proposals are decision support, reviewed by a chemist before anything runs."
          href="/reactions"
          ctaLabel="Open Repho"
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Active projects</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(reactionDisplay.activeProjects)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Drafts</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(reactionDisplay.draftProjects)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Completed</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(reactionDisplay.completedProjects)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">All projects</p>
              <p className="text-2xl font-bold tabular-nums">{fmtCount(reactionDisplay.totalProjects)}</p>
              <p className="text-xs text-muted-foreground">Excludes archived.</p>
            </div>
          </div>
          {reactionDisplay.latestProjectId != null ? (
            <p className="text-xs text-muted-foreground">
              Most recently updated:{" "}
              <Link className="underline underline-offset-2" href={`/reactions/${reactionDisplay.latestProjectId}`}>
                {reactionDisplay.latestProjectName ?? "Open project"}
              </Link>
            </p>
          ) : null}
          {reactionLoading ? <p className="text-xs text-muted-foreground">Loading reaction projects…</p> : null}
          {!reactionLoading && !reactionSummary?.available ? (
            <p className="text-xs text-muted-foreground">Live reaction project data isn&apos;t available right now.</p>
          ) : null}
          {!reactionLoading && reactionSummary?.available && reactionSummary.totalProjects === 0 ? (
            <p className="text-xs text-muted-foreground">No reaction projects yet.</p>
          ) : null}
        </ModuleCard>
      </DashboardSection>
      ) : null}

      <DashboardSection
        title="Operations"
        description="System health, QC, workflows, jobs, and ROI."
        icon={Cpu}
        accent="violet"
        eyebrow={sectionEyebrow.Operations}
        storageKey="operations"
        signals={operationsSignals}
        defaultOpen
      >
      {/* Automation ROI — GET /analytics/roi */}
      <ModuleCard
        accent="violet"
        eyebrow="Operations · ROI"
        title="Automation ROI"
        description="Hours saved, tasks automated, reports generated, and workflows completed."
        href="/roi"
        ctaLabel="Open ROI dashboard"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">Hours saved</p>
            <p className="text-2xl font-bold tabular-nums">{hoursSavedDisplay}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Tasks automated</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtRoiInt(roiSnapshot?.tasks_automated)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Reports generated</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtRoiInt(roiSnapshot?.reports_generated)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Workflows completed</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtRoiInt(roiSnapshot?.workflows_completed)}
            </p>
          </div>
        </div>
        {roiLoading ? (
          <p className="text-xs text-muted-foreground">Loading ROI snapshot…</p>
        ) : null}
        {!roiLoading && !roiLive ? (
          <p className="text-xs text-muted-foreground">
            Live ROI data didn't load — only hours are shown, mirroring the summary card above.
          </p>
        ) : null}
      </ModuleCard>

      {/* Operations summary — parallel GETs: /system/health, /system/jobs/summary, /security/summary, /model-health/drift-alerts; QC failures align with Quality Alerts */}
      <ModuleCard
        accent="violet"
        eyebrow="Operations · Health"
        title="Operations summary"
        icon={Cpu}
        description="System health, running and failed jobs, security warnings, and drift alerts. QC failures match the Quality Alerts card above."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">System health</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtOpsHealth(opsDisplay.systemHealthStatus)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Active jobs</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtCount(opsDisplay.activeJobs)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Failed jobs</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtCount(opsDisplay.failedJobs)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Security warnings</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtCount(opsDisplay.securityWarnings)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Open drift alerts</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtCount(opsDisplay.openDriftAlerts)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">QC failures</p>
            <p className="text-2xl font-bold tabular-nums">{qcFailures}</p>
          </div>
        </div>
        {opsLoading ? (
          <p className="text-xs text-muted-foreground">Loading operations summary…</p>
        ) : null}
        {!opsLoading && opsUnavailable ? (
          <p className="text-xs text-muted-foreground">
            Live operations data isn&apos;t available right now, so these values are not shown.
          </p>
        ) : null}
        {!opsLoading && opsRollup?.available && opsRollup.partial ? (
          <p className="text-xs text-muted-foreground">
            Some operations data didn't load — summary may be partial.
          </p>
        ) : null}
      </ModuleCard>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Connector and ingestion summary</CardTitle>
          <CardDescription>
            Connector health, today's ingestion runs, and outbound sync status.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <p className="text-xs text-muted-foreground">Active connectors</p>
              <p className="text-2xl font-bold tabular-nums">{activeConnectors ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Ingestion runs today</p>
              <p className="text-2xl font-bold tabular-nums">{ingestionRunsToday ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Failed ingestions</p>
              <p className="text-2xl font-bold tabular-nums">{failedIngestions ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Files requiring normalization review</p>
              <p className="text-2xl font-bold tabular-nums">{filesNeedNormalizationReview ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Failed sync jobs</p>
              <p className="text-2xl font-bold tabular-nums">{failedSyncJobs ?? "—"}</p>
            </div>
          </div>
          {connectorSummaryLoading ? (
            <p className="text-xs text-muted-foreground">Loading connector and ingestion summary…</p>
          ) : null}
          {!connectorSummaryLoading && connectorSummaryBackendUnavailable ? (
            <p className="text-xs text-muted-foreground">
              Live connector and ingestion data isn't available right now.
            </p>
          ) : null}
          {!connectorSummaryLoading && connectorSummaryError && connectorSummaryBackendUnavailable ? (
            <p className="text-xs text-muted-foreground">Details: {connectorSummaryError}</p>
          ) : null}
        </CardContent>
      </Card>

      {/* Quality Alerts — QC from GET /quality-control/sessions/{session_id} when sessions list is available */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Quality Alerts</CardTitle>
          <CardDescription>
            QC rollup from your saved sessions; newest scanned first.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">QC warnings</p>
              <p className="text-2xl font-bold tabular-nums">{qcWarnings}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">QC failures</p>
              <p className="text-2xl font-bold tabular-nums">{qcFailures}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Sessions requiring QC review</p>
              <p className="text-2xl font-bold tabular-nums">{qcSessionsReview}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Recent failed QC items</p>
              <p className="text-2xl font-bold tabular-nums">{qcRecentFailed.length}</p>
            </div>
          </div>
          {qcRecentFailed.length > 0 ? (
            <div className="rounded-md border bg-muted/30 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">Latest failed QC findings (error severity)</p>
              <ul className="mt-2 space-y-2 text-xs">
                {qcRecentFailed.slice(0, 5).map((row, idx) => (
                  <li key={`${row.session_id}-${row.title}-${idx}`} className="border-b border-border/50 pb-2 last:border-0 last:pb-0">
                    <span className="font-mono text-[10px] text-muted-foreground">{row.session_label}</span>
                    <span className="text-muted-foreground"> · </span>
                    <span className="font-medium">{row.title}</span>
                    {row.message ? (
                      <p className="mt-0.5 text-muted-foreground line-clamp-2">{row.message}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No failed QC findings with error severity in scanned sessions.</p>
          )}
          {overview.sessionsDataAvailable && qcLoading ? (
            <p className="text-xs text-muted-foreground">Loading QC summaries…</p>
          ) : null}
          {!overview.sessionsDataAvailable ? (
            <p className="text-xs text-muted-foreground">Session data couldn't load — QC summary shows example values.</p>
          ) : null}
          {overview.sessionsDataAvailable && !qcLoading && !qcBackendAvailable ? (
            <p className="text-xs text-muted-foreground">
              QC data couldn't load — showing example values.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {/* Method health — GET /model-health + GET /model-health/drift-alerts */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Method Health</CardTitle>
          <CardDescription>
            Registered methods, validation status, and open drift alerts.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <p className="text-xs text-muted-foreground">Active methods</p>
              <p className="text-2xl font-bold tabular-nums">
                {fmtCount(methodHealthDisplay.activeMethods)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Experimental methods</p>
              <p className="text-2xl font-bold tabular-nums">
                {fmtCount(methodHealthDisplay.experimentalMethods)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Deprecated methods</p>
              <p className="text-2xl font-bold tabular-nums">
                {fmtCount(methodHealthDisplay.deprecatedMethods)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Open drift alerts</p>
              <p className="text-2xl font-bold tabular-nums">
                {fmtCount(methodHealthDisplay.openDriftAlerts)}
              </p>
            </div>
            <div className="lg:col-span-1">
              <p className="text-xs text-muted-foreground">Latest validation run status</p>
              <p className="mt-1 break-words text-xs leading-snug">
                {statusLabel(methodHealthDisplay.latestValidationRunStatus)}
              </p>
            </div>
          </div>
          {methodHealthLoading ? (
            <p className="text-xs text-muted-foreground">Loading method health…</p>
          ) : null}
          {!methodHealthLoading && methodHealthUnavailable ? (
            <p className="text-xs text-muted-foreground">
              Method health data isn&apos;t available right now, so these values are not shown.
            </p>
          ) : null}
          {!methodHealthLoading &&
          methodHealthRollup?.available &&
          methodHealthRollup.partial ? (
            <p className="text-xs text-muted-foreground">
              Some method health data didn't load — metrics may be partial.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {/* Collaboration & review — per-session review-tasks, comments, reports (no global index) */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Collaboration &amp; review</CardTitle>
          <CardDescription>
            Open review tasks, unresolved comments, and reports awaiting approval.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Review required</p>
              <p className="text-2xl font-bold tabular-nums">{reviewRequiredForCollabCard}</p>
              <p className="mt-1 text-xs text-muted-foreground">Sessions awaiting review (same signal as summary card)</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Open review tasks</p>
              <p className="text-2xl font-bold tabular-nums">{collabRestDisplay.openReviewTasks}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Comments unresolved</p>
              <p className="text-2xl font-bold tabular-nums">{collabRestDisplay.commentsUnresolved}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Reports pending approval</p>
              <p className="text-2xl font-bold tabular-nums">{collabRestDisplay.reportsPendingApproval}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Released reports</p>
              <p className="text-2xl font-bold tabular-nums">{collabRestDisplay.releasedReports}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Assigned to me</p>
              <p className="text-2xl font-bold tabular-nums">
                {viewerEmail ? collabRestDisplay.assignedToMe : "—"}
              </p>
              {!viewerEmail ? (
                <p className="mt-1 text-xs text-muted-foreground">Sign in to match assignments on your account.</p>
              ) : null}
            </div>
          </div>
          {!overview.sessionsDataAvailable ? (
            <p className="text-xs text-muted-foreground">
              Session data couldn't load — collaboration summary shows example values.
            </p>
          ) : null}
          {overview.sessionsDataAvailable && collabRollup?.partial ? (
            <p className="text-xs text-muted-foreground">Some collaboration data didn't load.</p>
          ) : null}
        </CardContent>
      </Card>

      {/* Workflow run status — GET /workflow-runs */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Workflow runs</CardTitle>
          <CardDescription>
            Queued/running, review, failed, and completed counts.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Active (queued / running)</p>
              <p className="text-2xl font-bold tabular-nums">{wfSummaryDisplay.active}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Review required</p>
              <p className="text-2xl font-bold tabular-nums">{wfSummaryDisplay.reviewRequired}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Failed</p>
              <p className="text-2xl font-bold tabular-nums">{wfSummaryDisplay.failed}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Completed</p>
              <p className="text-2xl font-bold tabular-nums">{wfSummaryDisplay.completed}</p>
            </div>
          </div>
          {!overview.workflowRunsDataAvailable ? (
            <p className="text-xs text-muted-foreground">Workflow runs data couldn't load — showing example values.</p>
          ) : null}
        </CardContent>
      </Card>

      {/* Recent jobs (live when GET /jobs succeeds) */}
      <ModuleCard
        accent="violet"
        eyebrow="Operations · Jobs"
        title="Recent jobs"
        icon={Cpu}
        description={
          overview.jobsDataAvailable
            ? "Latest analysis jobs and their progress."
            : "Showing example jobs while live data loads."
        }
      >
          <StatusFilterPills
            label="Filter jobs by status"
            value={jobsFilter}
            onChange={setJobsFilter}
            options={[
              { value: "all", label: "All", count: jobRows.length },
              { value: "running", label: "Running", count: jobsStatusCounts.running },
              { value: "queued", label: "Queued", count: jobsStatusCounts.queued },
              { value: "succeeded", label: "Succeeded", count: jobsStatusCounts.succeeded },
              { value: "failed", label: "Failed", count: jobsStatusCounts.failed },
            ]}
          />
          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead>Sample / session</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredJobRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                      {jobRows.length === 0
                        ? "No jobs yet."
                        : `No jobs match the "${jobsFilter}" filter.`}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredJobRows.map((j) => {
                    const stripe = jobStripeColor(j.status)
                    const badge = jobBadgeColor(j.status)
                    return (
                      <TableRow
                        key={j.id}
                        style={stripe ? { boxShadow: `inset 3px 0 0 0 ${stripe}` } : undefined}
                      >
                        <TableCell className="max-w-[180px] truncate text-xs">
                          {formatJobTypeLabel(j.jobType)}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className="text-[10px] font-normal"
                            style={badge ? { borderColor: badge, color: badge } : undefined}
                          >
                            {statusLabel(j.status)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Progress value={j.progressPercent ?? 0} className="h-1.5 w-20" />
                            <span className="font-mono text-xs text-muted-foreground">
                              {j.progressPercent != null ? `${Math.round(j.progressPercent)}%` : "—"}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="max-w-[220px]">
                          <div className="flex flex-col gap-0.5 text-xs">
                            <span className="truncate font-mono">{j.sampleLabel}</span>
                            <span className="truncate font-mono text-muted-foreground">{j.sessionLabel}</span>
                          </div>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatJobTimeLabel(j.updatedAt)}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
      </ModuleCard>

      </DashboardSection>

      <DashboardSection
        title="Recent Activity"
        description="Latest sessions and workflow runs."
        icon={Activity}
        accent="green"
        eyebrow={sectionEyebrow.Activity}
        storageKey="activity"
        signals={activitySignals}
        defaultOpen
      >
      {/* Recent Activity Table */}
      <ModuleCard
        accent="teal"
        eyebrow="Activity · Sessions"
        title="Recent Activity"
        icon={Activity}
        description="SpectraCheck sessions and workflow runs. Newest first when workflow data is available."
      >
          <StatusFilterPills
            label="Filter activity by status"
            value={activityFilter}
            onChange={setActivityFilter}
            options={[
              { value: "all", label: "All", count: recentRows.length },
              { value: "approved", label: "Approved", count: activityStatusCounts.approved },
              { value: "review", label: "Review", count: activityStatusCounts.review },
              { value: "running", label: "Running", count: activityStatusCounts.running },
              { value: "contradiction", label: "Contradiction", count: activityStatusCounts.contradiction },
            ]}
          />
          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Analysis ID</TableHead>
                  <TableHead>Sample ID</TableHead>
                  <TableHead>Module</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Reviewer</TableHead>
                  <TableHead>Report</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredActivityRows.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      {recentRows.length === 0
                        ? "No saved SpectraCheck sessions yet."
                        : `No analyses match the "${activityFilter}" filter.`}
                    </TableCell>
                  </TableRow>
                ) : null}
                {filteredActivityRows.map((item: DashboardActivityRow) => {
                  const stripe = ACTIVITY_STRIPE_COLOR[item.status]
                  return (
                    <TableRow
                      key={item.id}
                      className="hover:bg-muted/50"
                      style={{ boxShadow: `inset 3px 0 0 0 ${stripe}` }}
                    >
                      <TableCell className="font-mono text-sm">
                        <Link
                          href={`/spectracheck?sessionId=${encodeURIComponent(item.id)}`}
                          className="hover:underline"
                        >
                          {item.id}
                        </Link>
                      </TableCell>
                      <TableCell className="text-sm">{item.sampleId}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{item.module}</Badge>
                      </TableCell>
                      <TableCell>
                        {item.status === "approved" && (
                          <Badge
                            variant="outline"
                            className="gap-1"
                            style={{ borderColor: "var(--mt-green)", color: "var(--mt-green)" }}
                          >
                            <CheckCircle2 className="h-3 w-3" />
                            Approved
                          </Badge>
                        )}
                        {item.status === "review" && (
                          <Badge
                            variant="outline"
                            className="gap-1"
                            style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }}
                          >
                            <Eye className="h-3 w-3" />
                            Review
                          </Badge>
                        )}
                        {item.status === "running" && (
                          <Badge
                            variant="outline"
                            className="gap-1"
                            style={{ borderColor: "var(--mt-cyan-ink)", color: "var(--mt-cyan-ink)" }}
                          >
                            <Activity className="h-3 w-3" />
                            Running
                          </Badge>
                        )}
                        {item.status === "contradiction" && (
                          <Badge
                            variant="outline"
                            className="gap-1"
                            style={{ borderColor: "var(--mt-red)", color: "var(--mt-red)" }}
                          >
                            <AlertTriangle className="h-3 w-3" />
                            Contradiction
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={item.confidence} className="h-1.5 w-16" />
                          <span className="font-mono text-sm">{item.confidence}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">{item.reviewer}</TableCell>
                      <TableCell>
                        {item.reportStatus === "ready" ? (
                          <Badge
                            variant="outline"
                            style={{ borderColor: "var(--mt-green)", color: "var(--mt-green)" }}
                          >
                            Ready
                          </Badge>
                        ) : (
                          <Badge variant="secondary">Pending</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
      </ModuleCard>
      </DashboardSection>
    </div>
  )
}
