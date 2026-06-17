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
  FolderOpen,
  LayoutDashboard,
  Microscope,
  Cpu,
  ShieldCheck,
} from "lucide-react"
import { DashboardSection } from "@/components/dashboard/dashboard-section"
import { DashboardGreeting } from "@/components/dashboard/dashboard-greeting"
import {
  DashboardPriorityCallout,
  type DashboardPriority,
} from "@/components/dashboard/dashboard-priority-callout"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { StatusFilterPills } from "@/components/dashboard/status-filter-pills"
import { RegulatoryNotificationsCompactCard } from "@/components/regulatory-hub/regulatory-notifications-compact-card"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { useOverviewData } from "@/components/app/overview-data-context"
import { useIsMobile } from "@/hooks/use-mobile"
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
} from "@/src/lib/dashboard/dashboard-core-module-activity"
import { ValidationReadinessDashboardCards } from "@/components/validation/validation-readiness-summary"
import type { RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"
import type { DashboardActivityRow, DashboardJobRow } from "@/src/lib/dashboard/overview-metrics"

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

function formatApiErr(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message
  }
  if (err instanceof Error) return err.message
  return "Request failed."
}

function formatJobTimeLabel(iso: string | null): string {
  if (!iso) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function formatCoreModuleActivityTime(iso: string | null): string {
  if (!iso) return "No activity yet"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

type CustomerDeploymentSummary = {
  onboardingStatus: string
  pilotStatus: string
  validationReadiness: string
  healthScore: string
  nextOnboardingTask: string
}

const DEMO_STATS = {
  active: 23,
  activeSub: (
    <p className="text-xs text-muted-foreground">
      <span style={{ color: "var(--mt-green)" }}>+4</span> from yesterday
    </p>
  ),
  review: 7,
  reviewSub: <p className="text-xs text-muted-foreground">2 with contradictions</p>,
  reports: 12,
  reportsSub: <p className="text-xs text-muted-foreground">Ready for export</p>,
  hours: 156,
  hoursSub: (
    <p className="text-xs text-muted-foreground">
      <span style={{ color: "var(--mt-green)" }}>+12%</span> this week
    </p>
  ),
  modelPct: 94.2,
}

const DEMO_RECENT: DashboardActivityRow[] = [
  {
    id: "NMR-2024-0847",
    sampleId: "API-Q4-BATCH-12",
    module: "Spectroscopy",
    status: "review",
    confidence: 87,
    reviewer: "Dr. Chen",
    reportStatus: "pending",
  },
  {
    id: "MSMS-2024-1293",
    sampleId: "MET-STUDY-089",
    module: "Spectroscopy",
    status: "approved",
    confidence: 94,
    reviewer: "Dr. Patel",
    reportStatus: "ready",
  },
  {
    id: "REG-2024-0445",
    sampleId: "API-Q4-BATCH-12",
    module: "Regulatory",
    status: "approved",
    confidence: 96,
    reviewer: "Dr. Kim",
    reportStatus: "ready",
  },
  {
    id: "RXN-OPT-2024-156",
    sampleId: "PROC-DEV-022",
    module: "Reactions",
    status: "running",
    confidence: 78,
    reviewer: "—",
    reportStatus: "pending",
  },
  {
    id: "NMR-2024-0842",
    sampleId: "IMP-PROF-017",
    module: "Spectroscopy",
    status: "contradiction",
    confidence: 72,
    reviewer: "Dr. Chen",
    reportStatus: "pending",
  },
]

/** Illustrative QC alert values when session list or QC endpoints are unavailable (v0 dashboard preview). */
const DEMO_QC_ALERTS = {
  warnings: 4,
  failures: 1,
  sessionsReview: 2,
  recentFailed: [
    {
      session_id: "demo-sc-01",
      session_label: "API-Q4-BATCH-12",
      title: "QC threshold exceeded",
      message: "Illustrative failed QC item when live data is unavailable.",
    },
  ] satisfies DashboardRecentFailedQcRow[],
}

/** Illustrative workflow run counts when GET /workflow-runs is unavailable (v0 dashboard preview). */
const DEMO_WORKFLOW_SUMMARY = {
  active: 2,
  reviewRequired: 1,
  failed: 0,
  completed: 9,
}

/** Illustrative collaboration counts when session list or collaboration endpoints are unavailable. */
const DEMO_COLLAB_ROLLUP = {
  openReviewTasks: 3,
  commentsUnresolved: 4,
  reportsPendingApproval: 2,
  releasedReports: 6,
  assignedToMe: 1,
}

/** Illustrative method health when GET /model-health or drift-alerts is unavailable. */
const DEMO_METHOD_HEALTH = {
  activeMethods: 12,
  experimentalMethods: 3,
  deprecatedMethods: 1,
  openDriftAlerts: 2,
  latestValidationRunStatus: "succeeded",
}

/** Illustrative operations metrics when system / jobs / security / drift endpoints are all unavailable. */
const DEMO_OPERATIONS = {
  systemHealthStatus: "healthy",
  activeJobs: 3,
  failedJobs: 0,
  securityWarnings: 1,
  openDriftAlerts: 2,
}

const DEMO_RECENT_JOBS: DashboardJobRow[] = [
  {
    id: "job-demo-1",
    jobType: "nmr_processed_analyze",
    status: "running",
    progressPercent: 62,
    sessionLabel: "sc-sess-01",
    sampleLabel: "BATCH-12-A",
    updatedAt: null,
  },
  {
    id: "job-demo-2",
    jobType: "lcms_import",
    status: "queued",
    progressPercent: 0,
    sessionLabel: "sc-sess-02",
    sampleLabel: "MET-089",
    updatedAt: null,
  },
  {
    id: "job-demo-3",
    jobType: "nmr_raw_fid_process",
    status: "succeeded",
    progressPercent: 100,
    sessionLabel: "sc-sess-01",
    sampleLabel: "PROC-022",
    updatedAt: null,
  },
]

export function DashboardV0() {
  const overview = useOverviewData()
  const isMobile = useIsMobile()
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
        ? overview.recentActivity ?? []
        : DEMO_RECENT
  const jobRows = overview.jobsDataAvailable ? overview.recentJobs ?? [] : DEMO_RECENT_JOBS

  const wfSummaryDisplay =
    overview.workflowRunsDataAvailable && overview.workflowStatusSummary
      ? overview.workflowStatusSummary
      : DEMO_WORKFLOW_SUMMARY

  const [qcLoading, setQcLoading] = useState(false)
  const [qcBackendAvailable, setQcBackendAvailable] = useState(false)
  const [qcWarnings, setQcWarnings] = useState(DEMO_QC_ALERTS.warnings)
  const [qcFailures, setQcFailures] = useState(DEMO_QC_ALERTS.failures)
  const [qcSessionsReview, setQcSessionsReview] = useState(DEMO_QC_ALERTS.sessionsReview)
  const [qcRecentFailed, setQcRecentFailed] = useState<DashboardRecentFailedQcRow[]>(DEMO_QC_ALERTS.recentFailed)

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
          setDeploymentSummaryError(formatApiErr(err))
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
  }, [overview.sessionsDataAvailable, overview.sessions])

  useEffect(() => {
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
  }, [])

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
      setQcWarnings(DEMO_QC_ALERTS.warnings)
      setQcFailures(DEMO_QC_ALERTS.failures)
      setQcSessionsReview(DEMO_QC_ALERTS.sessionsReview)
      setQcRecentFailed(DEMO_QC_ALERTS.recentFailed)
      return
    }
    if (overview.sessions.length === 0) {
      setQcLoading(false)
      setQcBackendAvailable(true)
      setQcWarnings(0)
      setQcFailures(0)
      setQcSessionsReview(0)
      setQcRecentFailed([])
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
        setQcWarnings(DEMO_QC_ALERTS.warnings)
        setQcFailures(DEMO_QC_ALERTS.failures)
        setQcSessionsReview(DEMO_QC_ALERTS.sessionsReview)
        setQcRecentFailed(DEMO_QC_ALERTS.recentFailed)
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

  useEffect(() => {
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
  }, [])

  useEffect(() => {
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
  }, [])

  useEffect(() => {
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
  }, [])

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

  function fmtMlCount(n: number | null | undefined): string {
    if (n == null) return "—"
    return String(n)
  }

  const activeSub =
    !live || !metrics
      ? DEMO_STATS.activeSub
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
      DEMO_STATS.reviewSub
    )

  const reportsSub = live ? (
    <p className="text-xs text-muted-foreground">Approved or saved reports</p>
  ) : (
    DEMO_STATS.reportsSub
  )

  const collabUseDemoRest =
    !overview.sessionsDataAvailable ||
    collabLoading ||
    (overview.sessions.length > 0 && collabRollup != null && !collabRollup.available)

  const collabRestDisplay = collabUseDemoRest
    ? DEMO_COLLAB_ROLLUP
    : collabRollup ?? DEMO_COLLAB_ROLLUP

  const reviewRequiredCount = live && metrics ? metrics.reviewRequired : DEMO_STATS.review
  const reviewRequiredForCollabCard = reviewRequiredCount

  const methodHealthUseDemo =
    !methodHealthLoading && (methodHealthRollup == null || !methodHealthRollup.available)

  const methodHealthDisplay = methodHealthUseDemo
    ? DEMO_METHOD_HEALTH
    : {
        activeMethods: methodHealthRollup?.activeMethods ?? null,
        experimentalMethods: methodHealthRollup?.experimentalMethods ?? null,
        deprecatedMethods: methodHealthRollup?.deprecatedMethods ?? null,
        openDriftAlerts: methodHealthRollup?.openDriftAlerts ?? null,
        latestValidationRunStatus: methodHealthRollup?.latestValidationRunStatus ?? null,
      }

  function fmtMethodHealthNum(n: number | null | undefined): string {
    if (n == null) return "—"
    return String(n)
  }

  const opsUseDemo = !opsLoading && (opsRollup == null || !opsRollup.available)

  const opsDisplay = opsUseDemo
    ? {
        systemHealthStatus: DEMO_OPERATIONS.systemHealthStatus,
        activeJobs: DEMO_OPERATIONS.activeJobs,
        failedJobs: DEMO_OPERATIONS.failedJobs,
        securityWarnings: DEMO_OPERATIONS.securityWarnings,
        openDriftAlerts: DEMO_OPERATIONS.openDriftAlerts,
      }
    : {
        systemHealthStatus: opsRollup?.systemHealthStatus ?? null,
        activeJobs: opsRollup?.activeJobs ?? null,
        failedJobs: opsRollup?.failedJobs ?? null,
        securityWarnings: opsRollup?.securityWarnings ?? null,
        openDriftAlerts: opsRollup?.openDriftAlerts ?? null,
      }

  function fmtOpsNum(n: number | null | undefined): string {
    if (n == null) return "—"
    return String(n)
  }

  function fmtOpsHealth(status: string | null): string {
    return status?.trim() || "—"
  }

  const roiLive = roiSnapshot != null
  const hoursSavedDisplay = roiLoading
    ? "…"
    : roiLive
      ? roiSnapshot.total_hours_saved.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 })
      : String(DEMO_STATS.hours)

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

    if (qcBackendAvailable && qcFailures > 0) {
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

      <DashboardSection
        title="Overview"
        description="Top metrics, validation readiness, and tenant onboarding."
        icon={LayoutDashboard}
        accent="teal"
        eyebrow="01 · Dashboard"
        defaultOpen
      >
      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <KpiCard
          title="Active Analyses"
          icon={Activity}
          href="/spectracheck"
          accent="teal"
          value={live && metrics ? metrics.activeAnalyses : DEMO_STATS.active}
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
          severity={reviewRequiredCount > 0 ? "warning" : "neutral"}
          value={reviewRequiredCount}
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
          value={live && metrics ? metrics.reportsReady : DEMO_STATS.reports}
          sub={reportsSub}
        />

        <KpiCard
          title="Hours Saved"
          icon={Clock}
          href="/roi"
          accent="violet"
          value={hoursSavedDisplay}
          sub={
            roiLoading ? (
              <p className="mt-1 text-xs text-muted-foreground">Loading ROI snapshot…</p>
            ) : roiLive ? (
              <p className="mt-1 text-xs text-muted-foreground">Total hours saved across automated workflows.</p>
            ) : (
              <>
                {DEMO_STATS.hoursSub}
                <p className="mt-1 text-xs text-muted-foreground">Live ROI data couldn't load — showing an example total.</p>
              </>
            )
          }
        />

        <KpiCard
          title="Model Confidence"
          icon={TrendingUp}
          href="/ml"
          accent="teal"
          value={`${DEMO_STATS.modelPct}%`}
          sub={<Progress value={DEMO_STATS.modelPct} className="mt-2 h-1.5" />}
        />
      </div>

      <ValidationReadinessDashboardCards />

      {showCustomerDeploymentCard ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle className="text-base">Customer Deployment</CardTitle>
                <CardDescription>Tenant onboarding and readiness summary.</CardDescription>
              </div>
              <Badge variant="outline">{tenant.status}</Badge>
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
                <p className="font-medium">{deploymentSummary?.onboardingStatus ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">pilot status</p>
                <p className="font-medium">{deploymentSummary?.pilotStatus ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">validation readiness</p>
                <p className="font-medium">{deploymentSummary?.validationReadiness ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">health score</p>
                <p className="font-medium">{deploymentSummary?.healthScore ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">next onboarding task</p>
                <p className="font-medium">{deploymentSummary?.nextOnboardingTask ?? "—"}</p>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              {moduleAccess.map((module, index) => (
                <div key={module.key} className="rounded-md border bg-muted/20 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span>
                      {index + 1}. {module.label}
                    </span>
                    <Badge variant={module.enabled ? "secondary" : "outline"}>
                      {module.enabled ? "enabled" : "locked"}
                    </Badge>
                  </div>
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
        eyebrow="02 · Spectroscopy"
      >
      {!mlLoading && mlRollup?.available ? (
        <ModuleCard
          accent="teal"
          eyebrow="Spectroscopy · ML"
          title="ML factory health"
          icon={Cpu}
          description="Health and review status of the ML models powering your analyses."
          href="/ml"
          ctaLabel="Open ML Model Factory"
        >
          {mlRollup.partial ? (
            <p className="text-xs text-muted-foreground">
              Some live data didn't load — values may be partial.
            </p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Active serving configs</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.activeModelCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Approved deployment candidates</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.approvedDeploymentCandidateCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Models / deployment review queue</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.modelsRequiringReviewHint)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Failed evaluations</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.failedEvaluationsCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Open deployment candidates</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.openDeploymentCandidatesCount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Error-analysis warning signals</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.errorAnalysisWarningsHint)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Drift / dataset warning signals</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.driftWarningsHint)}</p>
            </div>
          </div>
        </ModuleCard>
      ) : null}

      {!aiSummaryLoading && aiSummary?.available ? (
        <ModuleCard
          accent="teal"
          eyebrow="Spectroscopy · AI"
          title="AI inference summary"
          icon={Cpu}
          description="Live AI predictions and the active-learning queue across your tenant."
          href="/ai"
          ctaLabel="Open AI Services"
        >
          {aiSummary.partial ? (
            <p className="text-xs text-muted-foreground">
              Some AI live data didn't load — values may be partial.
            </p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Active AI services</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(aiSummary.activeAiServices)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Predictions requiring review</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(aiSummary.predictionsRequiringReview)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Low-confidence predictions</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(aiSummary.lowConfidencePredictions)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">OOD predictions</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(aiSummary.oodPredictions)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Active-learning candidates</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(aiSummary.activeLearningCandidates)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Service failures</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(aiSummary.serviceFailures)}</p>
            </div>
          </div>
        </ModuleCard>
      ) : null}
      {!aiSummaryLoading && aiSummary != null && !aiSummary.available ? (
        <p className="text-xs text-muted-foreground">Live AI inference data isn't available right now.</p>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">Cross-Module Command Center</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </div>
          <CardDescription>
            How SpectraCheck evidence, regulatory blockers, and reaction constraints connect across
            modules. Draft summary — review before action.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">1. SpectraCheck summary</p>
              <p className="mt-2 text-xs text-muted-foreground">latest SpectraCheck evidence status</p>
              <p className="text-sm font-medium">{crossModuleDisplay.latestSpectraCheckEvidenceStatus ?? "—"}</p>
            </div>
            <div className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">2. Regentry summary</p>
              <p className="mt-2 text-xs text-muted-foreground">linked regulatory action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(crossModuleDisplay.linkedRegulatoryActionItems)}</p>
              <p className="mt-2 text-xs text-muted-foreground">open regulatory blockers</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(crossModuleDisplay.openRegulatoryBlockers)}</p>
            </div>
            <div className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium uppercase text-muted-foreground">3. Reaction Optimization summary</p>
              <p className="mt-2 text-xs text-muted-foreground">reaction constraints created</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(crossModuleDisplay.reactionConstraintsCreated)}</p>
              <p className="mt-2 text-xs text-muted-foreground">optimization recommendations affected by compliance</p>
              <p className="text-2xl font-bold tabular-nums">
                {fmtMlCount(crossModuleDisplay.optimizationRecommendationsAffectedByCompliance)}
              </p>
            </div>
          </div>
          <div className="rounded-md border bg-card p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-medium uppercase text-muted-foreground">Core module activity</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Live opens logged from SpectraCheck, Regentry, and Repho in this testing phase.
                </p>
              </div>
              <Badge variant="outline" className="w-fit">
                {coreModuleActivityLoading ? "Loading" : `${coreModuleActivity?.total ?? 0} opens`}
              </Badge>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {(coreModuleActivity?.rows ?? []).map((row) => (
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
            {!coreModuleActivityLoading && coreModuleActivity?.available && coreModuleActivity.total === 0 ? (
              <p className="mt-3 text-xs text-muted-foreground">No core module activity has been logged yet.</p>
            ) : null}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border bg-card p-3">
              <p className="text-xs text-muted-foreground">Open cross-module action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(crossModuleDisplay.openCrossModuleActionItems)}</p>
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

      {!crLoading && crSummary?.available ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Compound Registry</CardTitle>
              <Microscope className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardDescription>
              Compounds and batches in your registry — traceability counts only, not identity or
              release certification.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Active compounds</p>
                <p className="text-2xl font-bold tabular-nums">{crSummary.activeCompounds}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Active batches</p>
                <p className="text-2xl font-bold tabular-nums">
                  {crSummary.activeBatches != null ? crSummary.activeBatches : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Compounds needing review</p>
                <p className="text-2xl font-bold tabular-nums">{crSummary.compoundsNeedingReview}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Evidence-linked compounds</p>
                <p className="text-2xl font-bold tabular-nums">{crSummary.evidenceLinkedCompounds}</p>
              </div>
            </div>
            {crSummary.partial ? (
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
      ) : null}

      </DashboardSection>

      <DashboardSection
        title="Regulatory"
        description="Dossiers, compliance, surveillance, and notifications."
        icon={ShieldCheck}
        accent="cyan"
        eyebrow="03 · Regulatory"
      >
      {!regulatoryLoading && regulatorySummary?.available ? (
        <ModuleCard
          accent="cyan"
          eyebrow="Regulatory · Hub"
          title="Regentry"
          icon={FolderOpen}
          description="Active dossiers and review workload across your tenant — not a legal or compliance certification."
          href="/spectracheck?program=regulatory_hub"
          ctaLabel="Open Regentry"
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Active dossiers</p>
              <p className="text-2xl font-bold tabular-nums">{regulatorySummary.activeDossiers}</p>
              <p className="text-xs text-muted-foreground">Excludes archived.</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Dossiers in review</p>
              <p className="text-2xl font-bold tabular-nums">{regulatorySummary.inReview}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Requirements needing evidence</p>
              <p className="text-2xl font-bold tabular-nums">{regulatorySummary.reqsNeedEvidence}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">High-risk dossiers</p>
              <p className="text-2xl font-bold tabular-nums">{regulatorySummary.highRisk}</p>
              <p className="text-xs text-muted-foreground">Latest risk assessment high or critical.</p>
            </div>
          </div>
        </ModuleCard>
      ) : null}

      {!regulatoryComplianceLoading && regulatoryCompliance?.available ? (
        <ModuleCard
          accent="cyan"
          eyebrow="Regulatory · Compliance"
          title="Regulatory compliance"
          icon={AlertTriangle}
          description="Open compliance action items, blocked dossiers, and triage by category — workflow signals, not legal conclusions."
          href="/spectracheck?program=regulatory_hub"
          ctaLabel="Open regulatory workspace"
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <p className="text-xs text-muted-foreground">Open action items</p>
              <p className="text-2xl font-bold tabular-nums">{regulatoryCompliance.openActionItems}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Critical action items</p>
              <p className="text-2xl font-bold tabular-nums">{regulatoryCompliance.criticalActionItems}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Dossiers blocked</p>
              <p className="text-2xl font-bold tabular-nums">{regulatoryCompliance.blockedDossiers}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">qNMR gaps (open items)</p>
              <p className="text-2xl font-bold tabular-nums">{regulatoryCompliance.qNmrGaps}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Nitrosamine review items</p>
              <p className="text-2xl font-bold tabular-nums">{regulatoryCompliance.nitrosamineReviewItems}</p>
            </div>
          </div>
        </ModuleCard>
      ) : null}

      {!surveillanceLoading && regulatorySurveillanceSummary?.available ? (
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
                <p className="text-2xl font-bold tabular-nums">{regulatorySurveillanceSummary.changesDetected}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">High-impact changes</p>
                <p className="text-2xl font-bold tabular-nums">{regulatorySurveillanceSummary.highImpactChanges}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Dossiers affected</p>
                <p className="text-2xl font-bold tabular-nums">{regulatorySurveillanceSummary.dossiersAffected}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Pending rule update proposals</p>
                <p className="text-2xl font-bold tabular-nums">
                  {regulatorySurveillanceSummary.pendingRuleUpdateProposals}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Unread regulatory notifications</p>
                <p className="text-2xl font-bold tabular-nums">
                  {regulatorySurveillanceSummary.unreadRegulatoryNotifications}
                </p>
              </div>
            </div>
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
      ) : null}

      {!surveillanceLoading && regulatorySurveillanceSummary && !regulatorySurveillanceSummary.available ? (
        <p className="text-xs text-muted-foreground">Live regulatory surveillance data isn't available right now.</p>
      ) : null}

      <RegulatoryNotificationsCompactCard />

      </DashboardSection>

      <DashboardSection
        title="Operations"
        description="System health, QC, workflows, jobs, and ROI."
        icon={Cpu}
        accent="violet"
        eyebrow="04 · Operations"
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
            Live ROI data didn't load — hours mirror the summary card above; task and workflow counts are hidden until it does.
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
            <p className="text-2xl font-bold tabular-nums capitalize">
              {fmtOpsHealth(opsDisplay.systemHealthStatus)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Active jobs</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtOpsNum(opsDisplay.activeJobs)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Failed jobs</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtOpsNum(opsDisplay.failedJobs)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Security warnings</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtOpsNum(opsDisplay.securityWarnings)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Open drift alerts</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtOpsNum(opsDisplay.openDriftAlerts)}
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
        {!opsLoading && opsUseDemo ? (
          <p className="text-xs text-muted-foreground">
            Live operations data couldn't load — showing example values (QC failures match the Quality Alerts card above).
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
            Session QC rollup when the API returns data; newest sessions scanned first.
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
                {methodHealthUseDemo
                  ? methodHealthDisplay.activeMethods
                  : fmtMethodHealthNum(methodHealthDisplay.activeMethods)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Experimental methods</p>
              <p className="text-2xl font-bold tabular-nums">
                {methodHealthUseDemo
                  ? methodHealthDisplay.experimentalMethods
                  : fmtMethodHealthNum(methodHealthDisplay.experimentalMethods)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Deprecated methods</p>
              <p className="text-2xl font-bold tabular-nums">
                {methodHealthUseDemo
                  ? methodHealthDisplay.deprecatedMethods
                  : fmtMethodHealthNum(methodHealthDisplay.deprecatedMethods)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Open drift alerts</p>
              <p className="text-2xl font-bold tabular-nums">
                {methodHealthUseDemo
                  ? methodHealthDisplay.openDriftAlerts
                  : fmtMethodHealthNum(methodHealthDisplay.openDriftAlerts)}
              </p>
            </div>
            <div className="lg:col-span-1">
              <p className="text-xs text-muted-foreground">Latest validation run status</p>
              <p className="mt-1 break-words font-mono text-xs leading-snug">
                {methodHealthUseDemo
                  ? methodHealthDisplay.latestValidationRunStatus
                  : methodHealthDisplay.latestValidationRunStatus?.trim() || "—"}
              </p>
            </div>
          </div>
          {methodHealthLoading ? (
            <p className="text-xs text-muted-foreground">Loading method health…</p>
          ) : null}
          {!methodHealthLoading && methodHealthUseDemo ? (
            <p className="text-xs text-muted-foreground">
              Method health data couldn't load — showing example values.
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
            Queued/running, review, failed, and completed counts from the workflow run registry.
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
                        <TableCell className="max-w-[180px] truncate font-mono text-xs">{j.jobType}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className="text-[10px] font-normal"
                            style={badge ? { borderColor: badge, color: badge } : undefined}
                          >
                            {j.status}
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
        eyebrow="05 · Activity"
      >
      {/* Recent Activity Table */}
      <ModuleCard
        accent="teal"
        eyebrow="Activity · Sessions"
        title="Recent Activity"
        icon={Activity}
        description="Latest SpectraCheck sessions and workflow runs (newest first when workflow data is available)."
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
