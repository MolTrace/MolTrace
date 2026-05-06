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

export function OverviewDataProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [sessionsDataAvailable, setSessionsDataAvailable] = useState(false)
  const [jobsDataAvailable, setJobsDataAvailable] = useState(false)
  const [projectsDataAvailable, setProjectsDataAvailable] = useState(false)
  const [projects, setProjects] = useState<unknown[]>([])
  const [sessions, setSessions] = useState<Record<string, unknown>[]>([])
  const [jobs, setJobs] = useState<Record<string, unknown>[]>([])
  const [workflowRuns, setWorkflowRuns] = useState<Record<string, unknown>[]>([])
  const [workflowRunsDataAvailable, setWorkflowRunsDataAvailable] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    void Promise.allSettled([
      apiFetch<unknown>("/projects", { method: "GET" }),
      fetchSpectraCheckSessionsList(),
      apiFetch<unknown>("/jobs", { method: "GET" }),
      apiFetch<unknown>("/workflow-runs", { method: "GET" }),
    ]).then((results) => {
      if (!active) return
      const [pr, sr, jr, wr] = results
      if (pr.status === "fulfilled") {
        setProjects(normalizeProjectListPayload(pr.value))
        setProjectsDataAvailable(true)
      } else {
        setProjects([])
        setProjectsDataAvailable(false)
      }
      if (sr.status === "fulfilled") {
        setSessions(normalizeSpectraCheckSessionsList(sr.value))
        setSessionsDataAvailable(true)
      } else {
        setSessions([])
        setSessionsDataAvailable(false)
      }
      if (jr.status === "fulfilled") {
        setJobs(normalizeJobsList(jr.value))
        setJobsDataAvailable(true)
      } else {
        setJobs([])
        setJobsDataAvailable(false)
      }
      if (wr.status === "fulfilled") {
        setWorkflowRuns(normalizeWorkflowRunsList(wr.value))
        setWorkflowRunsDataAvailable(true)
      } else {
        setWorkflowRuns([])
        setWorkflowRunsDataAvailable(false)
      }
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [])

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
