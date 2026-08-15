"use client"

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { apiFetch } from "@/lib/api/client"
import { normalizeProjectListPayload } from "@/components/projects/project-workspace-utils"
import { fetchSpectraCheckSessionsList } from "@/src/lib/spectracheck/spectracheck-backend-session"
import {
  isShellSnapshotFresh,
  loadShellSnapshot,
  readShellSnapshot,
  SHELL_SNAPSHOT_KEYS,
  SHELL_SNAPSHOT_MAX_AGE_MS,
} from "@/src/lib/shell/shell-snapshot-cache"
import {
  buildDashboardJobRows,
  buildEvidenceQueueCards,
  buildProjectNameIndex,
  buildRecentActivityRows,
  computeDashboardMetricCounts,
  countWorkflowRunStatuses,
  mergeDashboardActivityRows,
  normalizeJobsList,
  normalizeSpectraCheckSessionsList,
  normalizeWorkflowRunsList,
  type DashboardActivityRow,
  type DashboardJobRow,
  type DashboardMetricCounts,
  type EvidenceQueueCard,
  type WorkflowRunStatusCounts,
} from "@/src/lib/dashboard/overview-metrics"
import { useIncludedModules } from "@/src/lib/modules/included-modules-provider"

export type OverviewDataContextValue = {
  loading: boolean
  /** True when GET /spectracheck/sessions succeeded (including empty list). */
  sessionsDataAvailable: boolean
  /** True when GET /jobs succeeded (including empty list). */
  jobsDataAvailable: boolean
  /** True when GET /projects succeeded (including empty list). */
  projectsDataAvailable: boolean
  projects: unknown[]
  sessions: Record<string, unknown>[]
  jobs: Record<string, unknown>[]
  metrics: DashboardMetricCounts | null
  recentActivity: DashboardActivityRow[] | null
  /** Sessions + workflow runs merged when both sources exist. */
  recentActivityMerged: DashboardActivityRow[] | null
  recentJobs: DashboardJobRow[] | null
  evidenceQueue: EvidenceQueueCard[] | null
  projectById: Map<string, string>
  /** True when GET /workflow-runs succeeded (including empty list). */
  workflowRunsDataAvailable: boolean
  workflowRuns: Record<string, unknown>[]
  workflowStatusSummary: WorkflowRunStatusCounts | null
}

const OverviewDataContext = createContext<OverviewDataContextValue | null>(null)

/** The four workspace lists this provider owns, in one resolved shape. */
type OverviewSnapshot = {
  projects: unknown[]
  projectsDataAvailable: boolean
  sessions: Record<string, unknown>[]
  sessionsDataAvailable: boolean
  jobs: Record<string, unknown>[]
  jobsDataAvailable: boolean
  workflowRuns: Record<string, unknown>[]
  workflowRunsDataAvailable: boolean
}

const EMPTY_OVERVIEW_SNAPSHOT: OverviewSnapshot = {
  projects: [],
  projectsDataAvailable: false,
  sessions: [],
  sessionsDataAvailable: false,
  jobs: [],
  jobsDataAvailable: false,
  workflowRuns: [],
  workflowRunsDataAvailable: false,
}

/**
 * Shell-wide snapshot, fetched on every page.
 *
 * `includesSpectraCheck` gates the SpectraCheck sessions request: on a deployment that does not
 * serve it, that route is refused, and a UI that hides the product while still requesting its
 * data has not actually been gated. Defaults to true so an unknown capability readout keeps
 * today's behaviour.
 */
async function fetchOverviewSnapshot(includesSpectraCheck = true): Promise<OverviewSnapshot> {
  const [pr, sr, jr, wr] = await Promise.allSettled([
    apiFetch<unknown>("/projects", { method: "GET" }),
    includesSpectraCheck ? fetchSpectraCheckSessionsList() : Promise.reject(new Error("not included")),
    apiFetch<unknown>("/jobs", { method: "GET" }),
    apiFetch<unknown>("/workflow-runs", { method: "GET" }),
  ])
  return {
    projects: pr.status === "fulfilled" ? normalizeProjectListPayload(pr.value) : [],
    projectsDataAvailable: pr.status === "fulfilled",
    sessions: sr.status === "fulfilled" ? normalizeSpectraCheckSessionsList(sr.value) : [],
    sessionsDataAvailable: sr.status === "fulfilled",
    jobs: jr.status === "fulfilled" ? normalizeJobsList(jr.value) : [],
    jobsDataAvailable: jr.status === "fulfilled",
    workflowRuns: wr.status === "fulfilled" ? normalizeWorkflowRunsList(wr.value) : [],
    workflowRunsDataAvailable: wr.status === "fulfilled",
  }
}

export function OverviewDataProvider({ children }: { children: ReactNode }) {
  const { isIncluded, loading: modulesLoading } = useIncludedModules()
  // The shell is re-created on every top-level route change (each page renders
  // its own <AppShell>), so seed from the cross-navigation snapshot instead of
  // re-issuing all four requests and flashing a loading state on every tap.
  const cached = readShellSnapshot<OverviewSnapshot>(SHELL_SNAPSHOT_KEYS.overviewData)
  const seed = cached ?? EMPTY_OVERVIEW_SNAPSHOT
  const [loading, setLoading] = useState(cached == null)
  const [sessionsDataAvailable, setSessionsDataAvailable] = useState(seed.sessionsDataAvailable)
  const [jobsDataAvailable, setJobsDataAvailable] = useState(seed.jobsDataAvailable)
  const [projectsDataAvailable, setProjectsDataAvailable] = useState(seed.projectsDataAvailable)
  const [projects, setProjects] = useState<unknown[]>(seed.projects)
  const [sessions, setSessions] = useState<Record<string, unknown>[]>(seed.sessions)
  const [jobs, setJobs] = useState<Record<string, unknown>[]>(seed.jobs)
  const [workflowRuns, setWorkflowRuns] = useState<Record<string, unknown>[]>(seed.workflowRuns)
  const [workflowRunsDataAvailable, setWorkflowRunsDataAvailable] = useState(
    seed.workflowRunsDataAvailable,
  )

  useEffect(() => {
    // A fresh snapshot is already on screen — nothing to do until it ages out.
    if (isShellSnapshotFresh(SHELL_SNAPSHOT_KEYS.overviewData, SHELL_SNAPSHOT_MAX_AGE_MS)) return

    let active = true
    if (readShellSnapshot<OverviewSnapshot>(SHELL_SNAPSHOT_KEYS.overviewData) == null) {
      setLoading(true)
    }
    // While the capabilities readout is unresolved, isIncluded() answers false
    // for everything, so a snapshot built now would omit sessions. Fetch anyway:
    // three of the four requests do not depend on that answer, and apiFetch
    // carries no timeout — so *waiting* on a stalled /system/capabilities would
    // leave the dashboard permanently empty, which is worse than the bug being
    // fixed. The provisional result is simply never written into the snapshot
    // cache, so when `loading` flips this effect re-runs and refetches with the
    // real answer instead of being short-circuited by the freshness gate above.
    // (Baking "no sessions" into a *fresh* snapshot was the original defect.)
    const pending = modulesLoading
      ? fetchOverviewSnapshot(false)
      : loadShellSnapshot(SHELL_SNAPSHOT_KEYS.overviewData, () =>
          fetchOverviewSnapshot(isIncluded("spectracheck")),
        )
    void pending.then((next) => {
      if (!active) return
      setProjects(next.projects)
      setProjectsDataAvailable(next.projectsDataAvailable)
      setSessions(next.sessions)
      setSessionsDataAvailable(next.sessionsDataAvailable)
      setJobs(next.jobs)
      setJobsDataAvailable(next.jobsDataAvailable)
      setWorkflowRuns(next.workflowRuns)
      setWorkflowRunsDataAvailable(next.workflowRunsDataAvailable)
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [isIncluded, modulesLoading])

  const value = useMemo((): OverviewDataContextValue => {
    const projectById = buildProjectNameIndex(projects)
    if (!sessionsDataAvailable && !jobsDataAvailable && !workflowRunsDataAvailable) {
      return {
        loading,
        sessionsDataAvailable: false,
        jobsDataAvailable: false,
        projectsDataAvailable,
        projects,
        sessions,
        jobs,
        metrics: null,
        recentActivity: null,
        recentActivityMerged: null,
        recentJobs: null,
        evidenceQueue: null,
        projectById,
        workflowRunsDataAvailable: false,
        workflowRuns: [],
        workflowStatusSummary: null,
      }
    }
    const sessionRows = sessionsDataAvailable ? sessions : []
    const jobRows = jobsDataAvailable ? jobs : []
    const wfRows = workflowRunsDataAvailable ? workflowRuns : []
    const metrics =
      sessionsDataAvailable || jobsDataAvailable
        ? computeDashboardMetricCounts(sessionRows, {
            jobs: jobRows,
            jobsDataAvailable,
            sessionsDataAvailable,
          })
        : null
    const recentActivity = sessionsDataAvailable ? buildRecentActivityRows(sessionRows) : null
    let recentActivityMerged: DashboardActivityRow[] | null = null
    if (sessionsDataAvailable && recentActivity) {
      if (workflowRunsDataAvailable && wfRows.length > 0) {
        recentActivityMerged = mergeDashboardActivityRows(recentActivity, sessionRows, wfRows, 8)
      } else {
        recentActivityMerged = recentActivity
      }
    } else if (workflowRunsDataAvailable && wfRows.length > 0) {
      recentActivityMerged = mergeDashboardActivityRows([], [], wfRows, 8)
    }
    return {
      loading,
      sessionsDataAvailable,
      jobsDataAvailable,
      projectsDataAvailable,
      projects,
      sessions: sessionRows,
      jobs: jobRows,
      metrics,
      recentActivity,
      recentActivityMerged,
      recentJobs: jobsDataAvailable ? buildDashboardJobRows(jobRows) : null,
      evidenceQueue:
        sessionsDataAvailable && sessionRows.length > 0
          ? buildEvidenceQueueCards(sessionRows, projectById)
          : null,
      projectById,
      workflowRunsDataAvailable,
      workflowRuns: wfRows,
      workflowStatusSummary: workflowRunsDataAvailable ? countWorkflowRunStatuses(wfRows) : null,
    }
  }, [
    loading,
    sessionsDataAvailable,
    jobsDataAvailable,
    projectsDataAvailable,
    projects,
    sessions,
    jobs,
    workflowRunsDataAvailable,
    workflowRuns,
  ])

  return <OverviewDataContext.Provider value={value}>{children}</OverviewDataContext.Provider>
}

export function useOverviewData(): OverviewDataContextValue {
  const ctx = useContext(OverviewDataContext)
  if (!ctx) {
    throw new Error("useOverviewData must be used within OverviewDataProvider")
  }
  return ctx
}

export function useOptionalOverviewData(): OverviewDataContextValue | null {
  return useContext(OverviewDataContext)
}
