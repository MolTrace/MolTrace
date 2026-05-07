"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
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
  Microscope,
  Cpu,
} from "lucide-react"
import { RegulatoryNotificationsCompactCard } from "@/components/regulatory-hub/regulatory-notifications-compact-card"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { useOverviewData } from "@/components/app/overview-data-context"
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
import { ValidationReadinessDashboardCards } from "@/components/validation/validation-readiness-summary"
import type { RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"
import type { DashboardActivityRow, DashboardJobRow } from "@/src/lib/dashboard/overview-metrics"

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

const DEMO_STATS = {
  active: 23,
  activeSub: (
    <p className="text-xs text-muted-foreground">
      <span className="text-success">+4</span> from yesterday
    </p>
  ),
  review: 7,
  reviewSub: <p className="text-xs text-muted-foreground">2 with contradictions</p>,
  reports: 12,
  reportsSub: <p className="text-xs text-muted-foreground">Ready for export</p>,
  hours: 156,
  hoursSub: (
    <p className="text-xs text-muted-foreground">
      <span className="text-success">+12%</span> this week
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
  const [connectorSummaryLoading, setConnectorSummaryLoading] = useState(true)
  const [connectorSummaryBackendUnavailable, setConnectorSummaryBackendUnavailable] = useState(false)
  const [connectorSummaryError, setConnectorSummaryError] = useState("")
  const [activeConnectors, setActiveConnectors] = useState<number | null>(null)
  const [ingestionRunsToday, setIngestionRunsToday] = useState<number | null>(null)
  const [failedIngestions, setFailedIngestions] = useState<number | null>(null)
  const [filesNeedNormalizationReview, setFilesNeedNormalizationReview] = useState<number | null>(null)
  const [failedSyncJobs, setFailedSyncJobs] = useState<number | null>(null)
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

  const reviewRequiredForCollabCard =
    live && metrics ? metrics.reviewRequired : DEMO_STATS.review

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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Overview of your analytical workflows and pending reviews.
          </p>
          {!overview.loading && !overview.sessionsDataAvailable ? (
            <p className="mt-1 text-xs text-muted-foreground">Saved session data unavailable.</p>
          ) : null}
          {!overview.loading && !overview.jobsDataAvailable ? (
            <p className="mt-1 text-xs text-muted-foreground">Job telemetry unavailable.</p>
          ) : null}
          {!mlLoading && (!mlRollup || !mlRollup.available) ? (
            <p className="mt-1 text-xs text-muted-foreground">ML factory health unavailable.</p>
          ) : null}
          {!overview.loading && overview.sessionsDataAvailable && collabLoading ? (
            <p className="mt-1 text-xs text-muted-foreground">Loading collaboration summary…</p>
          ) : null}
          {!overview.loading &&
          overview.sessionsDataAvailable &&
          !collabLoading &&
          collabRollup &&
          !collabRollup.available &&
          overview.sessions.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Collaboration endpoints unavailable — summary uses illustrative values.
            </p>
          ) : null}
          {!crLoading && crSummary && !crSummary.available ? (
            <p className="mt-1 text-xs text-muted-foreground">Compound registry summary unavailable.</p>
          ) : null}
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="lg:hidden">
        <MobileCommandCenter />
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Active Analyses</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{live && metrics ? metrics.activeAnalyses : DEMO_STATS.active}</div>
            {activeSub}
            {overview.workflowRunsDataAvailable && overview.workflowStatusSummary ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Workflows active (queued / running): {overview.workflowStatusSummary.active}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Review Required</CardTitle>
            <AlertCircle className="h-4 w-4 text-warning" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{live && metrics ? metrics.reviewRequired : DEMO_STATS.review}</div>
            {reviewSub}
            {overview.workflowRunsDataAvailable && overview.workflowStatusSummary ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Workflows requiring review: {overview.workflowStatusSummary.reviewRequired}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Reports Ready</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{live && metrics ? metrics.reportsReady : DEMO_STATS.reports}</div>
            {reportsSub}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Hours Saved</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">{hoursSavedDisplay}</div>
            {roiLoading ? (
              <p className="mt-1 text-xs text-muted-foreground">Loading ROI snapshot…</p>
            ) : roiLive ? (
              <p className="mt-1 text-xs text-muted-foreground">From GET /analytics/roi (total_hours_saved).</p>
            ) : (
              <>
                {DEMO_STATS.hoursSub}
                <p className="mt-1 text-xs text-muted-foreground">ROI snapshot unavailable — illustrative total shown.</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Model Confidence</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold">{DEMO_STATS.modelPct}%</span>
            </div>
            <Progress value={DEMO_STATS.modelPct} className="mt-2 h-1.5" />
          </CardContent>
        </Card>
      </div>

      <ValidationReadinessDashboardCards />

      {!mlLoading && mlRollup?.available ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">ML factory health</CardTitle>
              <Cpu className="h-4 w-4 text-muted-foreground" aria-hidden />
            </div>
            <CardDescription>
              <code className="text-xs">GET /ml/model-health</code>, <code className="text-xs">GET /ml/deployment-candidates</code>,{" "}
              <code className="text-xs">GET /ml/evaluation-runs</code> — aggregate counts only.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {mlRollup.partial ? (
              <p className="text-xs text-muted-foreground">
                One or more list endpoints did not complete — some values may be omitted.
              </p>
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Active serving configs</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.activeModelCount)}</p>
                <p className="text-[11px] text-muted-foreground">active_model_count</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Approved deployment candidates</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.approvedDeploymentCandidateCount)}</p>
                <p className="text-[11px] text-muted-foreground">approved_deployment_candidate_count</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Models / deployment review queue</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.modelsRequiringReviewHint)}</p>
                <p className="text-[11px] text-muted-foreground">metadata or proposed / in_review candidates</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Failed evaluations</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.failedEvaluationsCount)}</p>
                <p className="text-[11px] text-muted-foreground">evaluation_runs status failed</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Open deployment candidates</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.openDeploymentCandidatesCount)}</p>
                <p className="text-[11px] text-muted-foreground">status proposed or in_review</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Error-analysis warning signals</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.errorAnalysisWarningsHint)}</p>
                <p className="text-[11px] text-muted-foreground">metadata or model-health warnings</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Drift / dataset warning signals</p>
                <p className="text-2xl font-bold tabular-nums">{fmtMlCount(mlRollup.driftWarningsHint)}</p>
                <p className="text-[11px] text-muted-foreground">metadata or model-health warnings</p>
              </div>
            </div>
            <p>
              <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/ml">
                Open ML Model Factory
              </Link>
            </p>
          </CardContent>
        </Card>
      ) : null}

      {!aiSummaryLoading && aiSummary?.available ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">AI inference summary</CardTitle>
              <Cpu className="h-4 w-4 text-muted-foreground" aria-hidden />
            </div>
            <CardDescription>
              <code className="text-xs">GET /ai/model-monitoring</code>, <code className="text-xs">GET /ai/services</code>,{" "}
              <code className="text-xs">GET /ai/predictions</code>, <code className="text-xs">GET /ai/active-learning/candidates</code> — aggregate counts only.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {aiSummary.partial ? (
              <p className="text-xs text-muted-foreground">
                One or more AI list endpoints did not complete — some values may be omitted.
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
            <p>
              <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/ai">
                Open AI Services
              </Link>
            </p>
          </CardContent>
        </Card>
      ) : null}
      {!aiSummaryLoading && aiSummary != null && !aiSummary.available ? (
        <p className="text-xs text-muted-foreground">AI inference summary unavailable — current dashboard content continues.</p>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">Cross-Module Command Center</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </div>
          <CardDescription>
            <code className="text-xs">{`GET ${crossModuleDisplay.sourceEndpoint}`}</code> with fallback to{" "}
            <code className="text-xs">GET /cross-module/command-center</code> — integrated workflow summary is draft and
            requires review.
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
              <p className="text-xs font-medium uppercase text-muted-foreground">2. Regulatory Hub summary</p>
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
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border bg-card p-3">
              <p className="text-xs text-muted-foreground">open cross-module action items</p>
              <p className="text-2xl font-bold tabular-nums">{fmtMlCount(crossModuleDisplay.openCrossModuleActionItems)}</p>
            </div>
            <div className="rounded-md border bg-card p-3">
              <p className="text-xs text-muted-foreground">next recommended action</p>
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
            <p className="text-xs text-muted-foreground">Cross-module command center summary unavailable.</p>
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
              <code className="text-xs">GET /compound-registry/compounds</code>,{" "}
              <code className="text-xs">GET /compound-registry/batches</code> — counts for traceability; not identity or
              release certification.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Active compounds</p>
                <p className="text-2xl font-bold tabular-nums">{crSummary.activeCompounds}</p>
                <p className="text-xs text-muted-foreground">status active</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Active batches</p>
                <p className="text-2xl font-bold tabular-nums">
                  {crSummary.activeBatches != null ? crSummary.activeBatches : "—"}
                </p>
                <p className="text-xs text-muted-foreground">status active</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Compounds needing review</p>
                <p className="text-2xl font-bold tabular-nums">{crSummary.compoundsNeedingReview}</p>
                <p className="text-xs text-muted-foreground">needs_review status or review flags on list rows.</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Evidence-linked compounds</p>
                <p className="text-2xl font-bold tabular-nums">{crSummary.evidenceLinkedCompounds}</p>
                <p className="text-xs text-muted-foreground">Non-zero evidence link counts or flags when present.</p>
              </div>
            </div>
            {crSummary.partial ? (
              <p className="text-xs text-muted-foreground">
                GET /compound-registry/batches did not complete — active batch count omitted.
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

      {!regulatoryLoading && regulatorySummary?.available ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Regulatory Hub</CardTitle>
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardDescription>
              <code className="text-xs">GET /regulatory/dossiers</code> — workflow counts from your tenant; not legal or
              compliance certification.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Active dossiers</p>
                <p className="text-2xl font-bold tabular-nums">{regulatorySummary.activeDossiers}</p>
                <p className="text-xs text-muted-foreground">Excludes archived.</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Dossiers in review</p>
                <p className="text-2xl font-bold tabular-nums">{regulatorySummary.inReview}</p>
                <p className="text-xs text-muted-foreground">status in_review</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Requirements needing evidence</p>
                <p className="text-2xl font-bold tabular-nums">{regulatorySummary.reqsNeedEvidence}</p>
                <p className="text-xs text-muted-foreground">Sum of evidence_needed rows.</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">High-risk dossiers</p>
                <p className="text-2xl font-bold tabular-nums">{regulatorySummary.highRisk}</p>
                <p className="text-xs text-muted-foreground">Latest risk assessment high or critical.</p>
              </div>
            </div>
            <p>
              <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/regulatory">
                Open Regulatory Hub
              </Link>
            </p>
          </CardContent>
        </Card>
      ) : null}

      {!regulatoryComplianceLoading && regulatoryCompliance?.available ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Regulatory compliance</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardDescription>
              <code className="text-xs">GET /regulatory/action-items</code>,{" "}
              <code className="text-xs">GET /regulatory/dossiers</code> — open workflow items and triage labels from your
              tenant; not legal conclusions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
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
                <p className="text-[11px] text-muted-foreground">action_type qnmr_validation_gap</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Nitrosamine review items</p>
                <p className="text-2xl font-bold tabular-nums">{regulatoryCompliance.nitrosamineReviewItems}</p>
                <p className="text-[11px] text-muted-foreground">action_type nitrosamine_risk_review</p>
              </div>
            </div>
            <p>
              <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/regulatory">
                Open regulatory workspace
              </Link>
            </p>
          </CardContent>
        </Card>
      ) : null}

      {!surveillanceLoading && regulatorySurveillanceSummary?.available ? (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Regulatory Surveillance</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardDescription>
              <code className="text-xs">GET /regulatory/changes</code>,{" "}
              <code className="text-xs">GET /regulatory/notifications</code>,{" "}
              <code className="text-xs">GET /regulatory/rule-update-proposals</code> — tenant workflow signals only.
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
        <p className="text-xs text-muted-foreground">Regulatory surveillance summary unavailable.</p>
      ) : null}

      <RegulatoryNotificationsCompactCard />

      {/* Automation ROI — GET /analytics/roi */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Automation ROI</CardTitle>
          <CardDescription>
            <code className="text-xs">GET /analytics/roi</code> — aggregate automation value (no event logs).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
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
              ROI snapshot unavailable — hours match the summary card above; task and workflow counts not loaded.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {/* Operations summary — parallel GETs: /system/health, /system/jobs/summary, /security/summary, /model-health/drift-alerts; QC failures align with Quality Alerts */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Operations summary</CardTitle>
          <CardDescription>
            <code className="text-xs">GET /system/health</code>, <code className="text-xs">GET /system/jobs/summary</code>,{" "}
            <code className="text-xs">GET /security/summary</code>, <code className="text-xs">GET /model-health/drift-alerts</code>
            ; QC failures match the Quality Alerts card.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
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
              Operations endpoints unavailable — illustrative values shown (QC failures follow Quality Alerts).
            </p>
          ) : null}
          {!opsLoading && opsRollup?.available && opsRollup.partial ? (
            <p className="text-xs text-muted-foreground">
              Some operations endpoints did not complete — summary may be partial.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Connector and ingestion summary</CardTitle>
          <CardDescription>
            <code className="text-xs">GET /connectors</code>, <code className="text-xs">GET /ingestion-runs</code>,{" "}
            <code className="text-xs">GET /outbound-sync-jobs</code> — aggregate operational counts only.
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
              Connector and ingestion summary unavailable — current dashboard content continues.
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
            <p className="text-xs text-muted-foreground">Saved session list unavailable — QC rollup shows illustrative values.</p>
          ) : null}
          {overview.sessionsDataAvailable && !qcLoading && !qcBackendAvailable ? (
            <p className="text-xs text-muted-foreground">
              QC endpoint unavailable — illustrative values shown.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {/* Method health — GET /model-health + GET /model-health/drift-alerts */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Method Health</CardTitle>
          <CardDescription>
            Registry snapshot from <code className="text-xs">GET /model-health</code> and drift signals from{" "}
            <code className="text-xs">GET /model-health/drift-alerts</code>.
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
              Model health endpoints unavailable — illustrative values shown.
            </p>
          ) : null}
          {!methodHealthLoading &&
          methodHealthRollup?.available &&
          methodHealthRollup.partial ? (
            <p className="text-xs text-muted-foreground">
              One method health request did not complete — some metrics may be unavailable.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {/* Collaboration & review — per-session review-tasks, comments, reports (no global index) */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Collaboration &amp; review</CardTitle>
          <CardDescription>
            Rolled up from <code className="text-xs">/spectracheck/sessions</code> plus per-session review tasks, comments,
            and reports when endpoints respond.
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
              Saved session list unavailable — collaboration rollup shows illustrative values.
            </p>
          ) : null}
          {overview.sessionsDataAvailable && collabRollup?.partial ? (
            <p className="text-xs text-muted-foreground">Some session collaboration requests did not complete.</p>
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
            <p className="text-xs text-muted-foreground">Workflow runs unavailable — illustrative values.</p>
          ) : null}
        </CardContent>
      </Card>

      {/* Recent jobs (live when GET /jobs succeeds) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent jobs</CardTitle>
          <CardDescription>
            {overview.jobsDataAvailable
              ? "Latest analysis jobs and their progress."
              : "Illustrative preview when job telemetry is unavailable."}
          </CardDescription>
        </CardHeader>
        <CardContent>
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
                {jobRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                      No jobs yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  jobRows.map((j) => (
                    <TableRow key={j.id}>
                      <TableCell className="max-w-[180px] truncate font-mono text-xs">{j.jobType}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] font-normal">
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
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Recent Activity Table */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>
            Latest SpectraCheck sessions and workflow runs (newest first when workflow data is available).
          </CardDescription>
        </CardHeader>
        <CardContent>
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
                {recentRows.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      No saved SpectraCheck sessions yet.
                    </TableCell>
                  </TableRow>
                ) : null}
                {recentRows.map((item: DashboardActivityRow) => (
                  <TableRow key={item.id} className="cursor-pointer hover:bg-muted/50">
                    <TableCell className="font-mono text-sm">{item.id}</TableCell>
                    <TableCell className="text-sm">{item.sampleId}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{item.module}</Badge>
                    </TableCell>
                    <TableCell>
                      {item.status === "approved" && (
                        <Badge variant="outline" className="gap-1 border-success/50 text-success">
                          <CheckCircle2 className="h-3 w-3" />
                          Approved
                        </Badge>
                      )}
                      {item.status === "review" && (
                        <Badge variant="outline" className="gap-1 border-accent/50 text-accent">
                          <Eye className="h-3 w-3" />
                          Review
                        </Badge>
                      )}
                      {item.status === "running" && (
                        <Badge variant="secondary" className="gap-1">
                          <Activity className="h-3 w-3" />
                          Running
                        </Badge>
                      )}
                      {item.status === "contradiction" && (
                        <Badge variant="outline" className="gap-1 border-warning/50 text-warning">
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
                        <Badge className="bg-success text-success-foreground">Ready</Badge>
                      ) : (
                        <Badge variant="secondary">Pending</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
