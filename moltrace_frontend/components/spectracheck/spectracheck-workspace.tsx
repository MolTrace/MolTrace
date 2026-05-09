"use client"

import {
  FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { FeedbackButton, toFeedbackProjectId, toFeedbackSessionId } from "@/src/components/analytics/FeedbackButton"
import { useRouter, useSearchParams } from "next/navigation"
import { apiFetch, ApiError } from "@/lib/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { extractFirstSmiles, formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  SpectraCheckConfidenceAdvProvider,
  SpectraCheckConfidenceSuite,
} from "@/components/spectracheck/spectracheck-confidence-suite"
import { SpectraCheckMsEvidenceStudio } from "@/components/spectracheck/spectracheck-ms-evidence-studio"
import {
  DeveloperJsonPanel,
  SummarizedEvidenceView,
  TabResultSection,
} from "@/components/spectracheck/spectracheck-result-panels"
import { SpectraCheckProcessedSpectrumSection } from "@/components/spectracheck/spectracheck-processed-spectrum-section"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
import {
  getNmrSolventForApi,
  NMR_SOLVENT_OPTIONS,
  NMR_SOLVENT_OTHER_VALUE,
} from "@/src/lib/nmr/solvents"
import {
  clearSpectraCheckEvidenceSession,
  consumeSpectraCheckSessionHydration,
  saveSpectraCheckEvidenceSession,
  sanitizeEvidenceItemsForStorage,
} from "@/src/lib/spectracheck/spectracheck-evidence-session"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"
import { SpectraCheckEvidenceProvider, useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import {
  SpectraCheckEvidenceQueuePanel,
  SpectraCheckEvidenceQueueUnifiedSummary,
} from "@/components/spectracheck/spectracheck-evidence-queue"
import { SpectraCheckReviewCollaborationPanel } from "@/components/spectracheck/spectracheck-review-collaboration-panel"
import { cn } from "@/lib/utils"
import { normalizeProjectListPayload } from "@/components/projects/project-workspace-utils"
import {
  applySharedInputsFromJson,
  buildSharedInputsJson,
  fetchSpectraCheckSessionBundle,
  mapEvidencePayloadToItems,
  parseProjectSampleIds,
  parseSessionIdFromRecord,
  parseSharedInputsJson,
  parseUnifiedEvidenceResponse,
  patchSessionEvidence,
  patchSpectraCheckSession,
  postSessionEvidence,
  postSessionReview,
  postSpectraCheckSession,
  postUnifiedEvidence,
} from "@/src/lib/spectracheck/spectracheck-backend-session"
import { SessionValueSummaryCard } from "@/components/spectracheck/session-value-summary-card"
import { SpectraCheckLinkedCompoundCard } from "@/components/spectracheck/spectracheck-linked-compound-card"
import { SpectraCheckKnowledgeLinksCard } from "@/components/knowledge/knowledge-links-integration"
import { SpectraCheckSessionControls } from "@/components/spectracheck/spectracheck-session-controls"
import { SpectraCheckSystemStatusBadges } from "@/components/spectracheck/spectracheck-system-status-badges"
import type { SessionSaveFeedback } from "@/components/spectracheck/spectracheck-session-controls"
import { SpectraCheckWorkspaceSessionProvider } from "@/components/spectracheck/spectracheck-workspace-session-context"
import { trackEvidenceAdded, trackUnifiedEvidenceBuilt } from "@/src/lib/analytics/analytics-client"
import { UploadCenter } from "@/src/components/spectracheck/UploadCenter"
import { ArtifactBrowser } from "@/src/components/spectracheck/ArtifactBrowser"
import { SessionEvidenceReadinessCard } from "@/src/components/spectracheck/SessionEvidenceReadinessCard"
import { SpectraCheckRegulatoryImpactCard } from "@/components/spectracheck/spectracheck-regulatory-impact-card"
import { RecentAnalysisJobsSection } from "@/src/components/spectracheck/RecentAnalysisJobsSection"
import type { WorkflowTemplateCardModel } from "@/src/components/spectracheck/WorkflowTemplateGallery"
import { WorkflowTemplateGallery } from "@/src/components/spectracheck/WorkflowTemplateGallery"
import { WorkflowRunLauncher } from "@/src/components/spectracheck/WorkflowRunLauncher"
import type { SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { normalizeSessionFileRecordList } from "@/src/lib/spectracheck/session-file-record"
import { SpectraCheckValidationReadinessCard } from "@/components/validation/validation-readiness-summary"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"
import { DataState, DataStateBadge, type DataStateKind } from "@/components/science/data-state"
import { EvidenceCard, type EvidenceRiskLevel, type EvidenceStatus } from "@/components/science/evidence-card"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCircle, AlertTriangle, BarChart3, FileText } from "lucide-react"

function SpectraCheckTabWithTooltip({
  value,
  className,
  tooltip,
  children,
}: {
  value: string
  className?: string
  tooltip: string
  children: ReactNode
}) {
  return (
    <TabsTrigger value={value} className={className} data-testid={`spectracheck-tab-${value}`}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex w-full items-center justify-center gap-1 text-center">{children}</span>
        </TooltipTrigger>
        <TooltipContent sideOffset={4} className="max-w-xs text-xs">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </TabsTrigger>
  )
}

const tabTriggerClass = cn(
  "shrink-0 whitespace-normal text-left text-xs sm:text-sm sm:text-center sm:whitespace-nowrap",
  "font-mono",
  "data-[state=active]:[background-color:var(--mt-teal)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm",
  "data-[state=inactive]:text-muted-foreground",
)

const defaultCandidates = `Ethanol | CCO | proposed
Methanol | CO | starting material
Propanol | CCCO | possible impurity`

const defaultProton =
  "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"

const defaultCarbon = "13C NMR (101 MHz, CDCl3) δ 58.3, 18.2."

function mapEvidenceCardStatus(item: EvidenceItem): EvidenceStatus {
  if ((item.contradictions?.length ?? 0) > 0) return "contradiction"
  if (item.status === "pending_review" || item.status === "warning") return "pending_review"
  if (item.status === "error") return "unavailable"
  return "draft"
}

function mapEvidenceRisk(item: EvidenceItem): EvidenceRiskLevel {
  if ((item.contradictions?.length ?? 0) > 0) return "high"
  if (item.status === "warning" || item.status === "pending_review") return "medium"
  if (item.status === "error") return "critical"
  return "unknown"
}

type SpectraCheckWorkspaceProps = {
  /** Used by tests or embeds; defaults to Overview. */
  defaultTab?: string
}

export function SpectraCheckWorkspace(props: SpectraCheckWorkspaceProps = {}) {
  return (
    <SpectraCheckConfidenceAdvProvider>
      <SpectraCheckEvidenceProvider>
        <SpectraCheckWorkspaceInner {...props} />
      </SpectraCheckEvidenceProvider>
    </SpectraCheckConfidenceAdvProvider>
  )
}

function SpectraCheckWorkspaceInner({ defaultTab = "tab-overview" }: SpectraCheckWorkspaceProps = {}) {
  const {
    evidenceItems,
    latestUnifiedConfidenceResult,
    latestReportResult,
    clearEvidenceItems,
    setLatestUnifiedConfidenceResult,
    setLatestReportResult,
    replaceEvidenceItems,
  } = useSpectraCheckEvidence()
  const overview = useOptionalOverviewData()

  const router = useRouter()
  const searchParams = useSearchParams()

  const [backendSessionId, setBackendSessionId] = useState<string | null>(null)
  const [spectracheckSessionFiles, setSpectracheckSessionFiles] = useState<SessionFileRecord[]>([])
  const [recentAnalysisJobIds, setRecentAnalysisJobIds] = useState<string[]>([])
  const [selectedWorkflowTemplate, setSelectedWorkflowTemplate] = useState<WorkflowTemplateCardModel | null>(null)

  const refreshSpectracheckSessionFiles = useCallback(async () => {
    const sid = backendSessionId?.trim()
    if (!sid) {
      setSpectracheckSessionFiles([])
      return
    }
    try {
      const data = await apiFetch<unknown>(
        `/spectracheck/sessions/${encodeURIComponent(sid)}/files`,
        { method: "GET" },
      )
      setSpectracheckSessionFiles(normalizeSessionFileRecordList(data))
    } catch {
      setSpectracheckSessionFiles([])
    }
  }, [backendSessionId])

  useEffect(() => {
    void refreshSpectracheckSessionFiles()
  }, [refreshSpectracheckSessionFiles])

  const registerSpectracheckAnalysisJob = useCallback((jobId: string) => {
    setRecentAnalysisJobIds((prev) => [jobId, ...prev.filter((id) => id !== jobId)].slice(0, 30))
  }, [])
  const [selectedProjectId, setSelectedProjectId] = useState("")
  const [selectedSampleId, setSelectedSampleId] = useState("")
  const [projectsRows, setProjectsRows] = useState<unknown[]>([])
  const [samplesRows, setSamplesRows] = useState<unknown[]>([])
  const [sessionIdInput, setSessionIdInput] = useState("")
  const [reviewState, setReviewState] = useState<unknown>(null)
  const [saveFeedback, setSaveFeedback] = useState<SessionSaveFeedback>("idle")
  const [saveMessage, setSaveMessage] = useState("")
  const [sessionBusy, setSessionBusy] = useState(false)
  const snapshotRef = useRef("")
  const urlSessionHandledRef = useRef<string | null>(null)

  const [activeTab, setActiveTab] = useState(defaultTab)
  const [sessionRecord, setSessionRecord] = useState<unknown>(null)

  const feedbackProjectId = useMemo(() => toFeedbackProjectId(selectedProjectId), [selectedProjectId])
  const feedbackSessionId = useMemo(() => toFeedbackSessionId(backendSessionId), [backendSessionId])
  const [sampleId, setSampleId] = useState("SAMPLE-001")
  const [solventChoice, setSolventChoice] = useState("CDCl3")
  const [customSolvent, setCustomSolvent] = useState("")
  const solventForApi = useMemo(
    () => getNmrSolventForApi(solventChoice, customSolvent),
    [solventChoice, customSolvent],
  )
  const [candidatesText, setCandidatesText] = useState(defaultCandidates)
  const [protonText, setProtonText] = useState(defaultProton)
  const [carbonText, setCarbonText] = useState(defaultCarbon)

  const [nmrResult, setNmrResult] = useState<unknown>(null)
  const [nmrError, setNmrError] = useState("")
  const [nmrLoading, setNmrLoading] = useState(false)

  const deptFileRef = useRef<HTMLInputElement>(null)
  const [deptExperimentType, setDeptExperimentType] = useState("")
  const [deptAptPositive, setDeptAptPositive] = useState("CH_CH3")
  const [deptPreviewResult, setDeptPreviewResult] = useState<unknown>(null)
  const [deptPreviewError, setDeptPreviewError] = useState("")
  const [deptPreviewLoading, setDeptPreviewLoading] = useState(false)
  const [deptAnalyzeResult, setDeptAnalyzeResult] = useState<unknown>(null)
  const [deptAnalyzeError, setDeptAnalyzeError] = useState("")
  const [deptAnalyzeLoading, setDeptAnalyzeLoading] = useState(false)

  const nmr2dFileRef = useRef<HTMLInputElement>(null)
  const nmr2dDeptFileRef = useRef<HTMLInputElement>(null)
  const [nmr2dSmiles, setNmr2dSmiles] = useState(() => extractFirstSmiles(defaultCandidates))
  const [nmr2dExperiment, setNmr2dExperiment] = useState("HSQC")
  const [nmr2dContour, setNmr2dContour] = useState(false)
  const [nmr2dDeptExperiment, setNmr2dDeptExperiment] = useState("")
  const [nmr2dResult, setNmr2dResult] = useState<unknown>(null)
  const [nmr2dError, setNmr2dError] = useState("")
  const [nmr2dLoading, setNmr2dLoading] = useState(false)

  const [refProton, setRefProton] = useState("")
  const [refCarbon, setRefCarbon] = useState("")
  const obs2dRef = useRef<HTMLInputElement>(null)
  const ref2dRef = useRef<HTMLInputElement>(null)
  const [simExperimentType, setSimExperimentType] = useState("")
  const [simResult, setSimResult] = useState<unknown>(null)
  const [simError, setSimError] = useState("")
  const [simLoading, setSimLoading] = useState(false)

  const candNmr2dRef = useRef<HTMLInputElement>(null)
  const candDeptRef = useRef<HTMLInputElement>(null)
  const [candDeptExperiment, setCandDeptExperiment] = useState("")
  const [candNmr2dExperiment, setCandNmr2dExperiment] = useState("")
  const [candResult, setCandResult] = useState<unknown>(null)
  const [candError, setCandError] = useState("")
  const [candLoading, setCandLoading] = useState(false)

  async function runNmrEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNmrLoading(true)
    setNmrError("")
    setNmrResult(null)

    const formData = new FormData()
    formData.append("candidates_text", candidatesText)
    formData.append("observed_proton_text", protonText)
    formData.append("observed_carbon13_text", carbonText)
    formData.append("solvent", solventForApi)
    formData.append("sample_id", sampleId)

    try {
      const data = await apiFetch<unknown>("/prediction/nmr/match/evidence", {
        method: "POST",
        body: formData,
      })
      setNmrResult(data)
    } catch (err) {
      setNmrError(formatApiError(err, "SpectraCheck analysis failed"))
    } finally {
      setNmrLoading(false)
    }
  }

  async function runDeptPreview() {
    const file = deptFileRef.current?.files?.[0]
    if (!file) {
      setDeptPreviewError("Choose a DEPT/APT peak table file (CSV / TSV / JSON).")
      return
    }
    setDeptPreviewLoading(true)
    setDeptPreviewError("")
    setDeptPreviewResult(null)
    const fd = new FormData()
    fd.append("file", file)
    if (deptExperimentType.trim()) fd.append("experiment_type", deptExperimentType.trim())
    fd.append("apt_positive", deptAptPositive)
    try {
      const data = await apiFetch<unknown>("/carbon13/dept/preview", { method: "POST", body: fd })
      setDeptPreviewResult(data)
    } catch (err) {
      setDeptPreviewError(formatApiError(err, "DEPT/APT preview failed"))
    } finally {
      setDeptPreviewLoading(false)
    }
  }

  async function runDeptAnalyze() {
    const file = deptFileRef.current?.files?.[0]
    if (!file) {
      setDeptAnalyzeError("Choose a DEPT/APT peak table file (CSV / TSV / JSON).")
      return
    }
    setDeptAnalyzeLoading(true)
    setDeptAnalyzeError("")
    setDeptAnalyzeResult(null)
    const fd = new FormData()
    fd.append("file", file)
    fd.append("carbon13_text", carbonText)
    fd.append("solvent", solventForApi)
    if (deptExperimentType.trim()) fd.append("experiment_type", deptExperimentType.trim())
    fd.append("apt_positive", deptAptPositive)
    try {
      const data = await apiFetch<unknown>("/carbon13/dept/analyze", { method: "POST", body: fd })
      setDeptAnalyzeResult(data)
    } catch (err) {
      setDeptAnalyzeError(formatApiError(err, "DEPT/APT analyze failed"))
    } finally {
      setDeptAnalyzeLoading(false)
    }
  }

  async function runNmr2dAnalyze() {
    const file = nmr2dFileRef.current?.files?.[0]
    if (!file) {
      setNmr2dError("Upload a processed 2D peak table (CSV / TSV / JSON).")
      return
    }
    if (!nmr2dSmiles.trim()) {
      setNmr2dError("Enter a SMILES string for the structure being tested (required by the 2D analyzer).")
      return
    }
    setNmr2dLoading(true)
    setNmr2dError("")
    setNmr2dResult(null)
    const fd = new FormData()
    fd.append("file", file)
    fd.append("smiles", nmr2dSmiles.trim())
    fd.append("sample_id", sampleId)
    fd.append("solvent", solventForApi)
    fd.append("proton_nmr_text", protonText)
    fd.append("carbon13_text", carbonText)
    if (nmr2dExperiment.trim()) fd.append("experiment", nmr2dExperiment.trim())
    fd.append("include_contour_preview", nmr2dContour ? "true" : "false")
    fd.append("save_run", "true")
    fd.append("apt_positive", deptAptPositive)
    const deptF = nmr2dDeptFileRef.current?.files?.[0]
    if (deptF) {
      fd.append("dept_apt_file", deptF)
      if (nmr2dDeptExperiment.trim()) fd.append("dept_apt_experiment_type", nmr2dDeptExperiment.trim())
    }
    try {
      const data = await apiFetch<unknown>("/nmr2d/analyze", { method: "POST", body: fd })
      setNmr2dResult(data)
    } catch (err) {
      setNmr2dError(formatApiError(err, "2D NMR analyze failed"))
    } finally {
      setNmr2dLoading(false)
    }
  }

  async function runSimilarity() {
    setSimLoading(true)
    setSimError("")
    setSimResult(null)
    const fd = new FormData()
    fd.append("observed_proton_text", protonText)
    fd.append("observed_carbon13_text", carbonText)
    if (refProton.trim()) fd.append("reference_proton_text", refProton.trim())
    if (refCarbon.trim()) fd.append("reference_carbon13_text", refCarbon.trim())
    fd.append("solvent", solventForApi)
    fd.append("sample_id", sampleId)
    if (simExperimentType.trim()) fd.append("nmr2d_experiment_type", simExperimentType.trim())
    const o2 = obs2dRef.current?.files?.[0]
    const r2 = ref2dRef.current?.files?.[0]
    if (o2 && r2) {
      fd.append("observed_nmr2d_file", o2)
      fd.append("reference_nmr2d_file", r2)
    }
    try {
      const data = await apiFetch<unknown>("/similarity/score/evidence", { method: "POST", body: fd })
      setSimResult(data)
    } catch (err) {
      setSimError(formatApiError(err, "Spectral similarity scoring failed"))
    } finally {
      setSimLoading(false)
    }
  }

  async function runCandidateCompare() {
    setCandLoading(true)
    setCandError("")
    setCandResult(null)
    const fd = new FormData()
    fd.append("candidates_text", candidatesText)
    fd.append("proton_nmr_text", protonText)
    fd.append("carbon13_text", carbonText)
    fd.append("solvent", solventForApi)
    fd.append("sample_id", sampleId)
    fd.append("apt_positive", deptAptPositive)
    const d = candDeptRef.current?.files?.[0]
    if (d) {
      fd.append("dept_apt_file", d)
      if (candDeptExperiment.trim()) fd.append("dept_apt_experiment_type", candDeptExperiment.trim())
    }
    const n2 = candNmr2dRef.current?.files?.[0]
    if (n2) {
      fd.append("nmr2d_file", n2)
      if (candNmr2dExperiment.trim()) fd.append("nmr2d_experiment_type", candNmr2dExperiment.trim())
    }
    try {
      const data = await apiFetch<unknown>("/candidates/compare/evidence", { method: "POST", body: fd })
      setCandResult(data)
    } catch (err) {
      setCandError(formatApiError(err, "Candidate comparison failed"))
    } finally {
      setCandLoading(false)
    }
  }

  function fillSmilesFromCandidates() {
    setNmr2dSmiles(extractFirstSmiles(candidatesText))
  }

  const buildSnapshot = useCallback(() => {
    return JSON.stringify({
      sampleId,
      solventChoice,
      customSolvent,
      candidatesText,
      protonText,
      carbonText,
      evidenceKeys: evidenceItems.map((e) => `${e.id}:${e.backendEvidenceId ?? ""}`).join(","),
      hasUnified: latestUnifiedConfidenceResult != null,
      hasReport: latestReportResult != null,
      rev: reviewState === null ? "null" : "set",
    })
  }, [
    sampleId,
    solventChoice,
    customSolvent,
    candidatesText,
    protonText,
    carbonText,
    evidenceItems,
    latestUnifiedConfidenceResult,
    latestReportResult,
    reviewState,
  ])

  const establishSnapshot = useCallback(() => {
    snapshotRef.current = buildSnapshot()
  }, [buildSnapshot])

  useEffect(() => {
    if (!snapshotRef.current) {
      snapshotRef.current = buildSnapshot()
      return
    }
    if (buildSnapshot() !== snapshotRef.current) {
      setSaveFeedback((f) => (f === "saving" ? f : "unsaved"))
    }
  }, [buildSnapshot])

  const loadSessionById = useCallback(
    async (sid: string) => {
      setSessionBusy(true)
      setSaveMessage("")
      setSaveFeedback("saving")
      try {
        const bundle = await fetchSpectraCheckSessionBundle(sid)
        const session = bundle.session
        setSessionRecord(session ?? null)
        const resolvedId = parseSessionIdFromRecord(session) ?? sid
        setBackendSessionId(resolvedId)
        setSessionIdInput(resolvedId)
        const shared = parseSharedInputsJson(session)
        if (shared) {
          applySharedInputsFromJson(shared, {
            setSampleId,
            setSolventChoice,
            setCustomSolvent,
            setCandidatesText,
            setProtonText,
            setCarbonText,
          })
          const sc = shared as Record<string, unknown>
          const ct =
            typeof sc.candidates_text === "string"
              ? sc.candidates_text
              : typeof sc.candidatesText === "string"
                ? sc.candidatesText
                : null
          if (ct != null) setNmr2dSmiles(extractFirstSmiles(ct))
        }
        const { projectId: p, sampleId: smp } = parseProjectSampleIds(session)
        if (p) setSelectedProjectId(p)
        if (smp) setSelectedSampleId(smp)
        replaceEvidenceItems(mapEvidencePayloadToItems(bundle.evidence))
        setLatestUnifiedConfidenceResult(parseUnifiedEvidenceResponse(bundle.unifiedEvidence))
        setReviewState(bundle.review)
        establishSnapshot()
        setSaveFeedback("saved")
      } catch (err) {
        urlSessionHandledRef.current = null
        setSessionRecord(null)
        setSaveFeedback("error")
        setSaveMessage(formatApiError(err, "Failed to load SpectraCheck session."))
        if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
          setSaveFeedback("unavailable")
        }
      } finally {
        setSessionBusy(false)
      }
    },
    [establishSnapshot, replaceEvidenceItems, setLatestUnifiedConfidenceResult],
  )

  const refreshLoadedSession = useCallback(async () => {
    const sid = backendSessionId?.trim()
    if (!sid) return
    await loadSessionById(sid)
  }, [backendSessionId, loadSessionById])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch<unknown>("/projects", { method: "GET" })
        if (!cancelled) setProjectsRows(normalizeProjectListPayload(data))
      } catch {
        if (!cancelled) setProjectsRows([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedProjectId.trim()) {
      setSamplesRows([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch<unknown>(
          `/projects/${encodeURIComponent(selectedProjectId)}/samples`,
          { method: "GET" },
        )
        if (!cancelled) setSamplesRows(normalizeProjectListPayload(data))
      } catch {
        if (!cancelled) setSamplesRows([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedProjectId])

  const sessionIdFromUrl = searchParams.get("sessionId")
  useEffect(() => {
    const id = sessionIdFromUrl?.trim()
    if (!id) {
      urlSessionHandledRef.current = null
      return
    }
    if (urlSessionHandledRef.current === id) return
    urlSessionHandledRef.current = id
    void loadSessionById(id)
  }, [sessionIdFromUrl, loadSessionById])

  async function handleSaveSession() {
    setSessionBusy(true)
    setSaveMessage("")
    setSaveFeedback("saving")
    try {
      const shared = buildSharedInputsJson({
        sampleId,
        solventChoice,
        customSolvent,
        candidatesText,
        protonText,
        carbonText,
      })
      const body: Record<string, unknown> = {
        project_id: selectedProjectId.trim() ? Number(selectedProjectId) : null,
        sample_id: selectedSampleId.trim() || null,
        shared_inputs_json: shared,
      }
      if (backendSessionId) {
        await patchSpectraCheckSession(backendSessionId, body)
      } else {
        const created = await postSpectraCheckSession(body)
        const newId = parseSessionIdFromRecord(created)
        if (newId) {
          setBackendSessionId(newId)
          setSessionIdInput(newId)
          urlSessionHandledRef.current = newId
          router.replace(`/spectracheck?sessionId=${encodeURIComponent(newId)}`)
        }
      }
      establishSnapshot()
      setSaveFeedback("saved")
    } catch (err) {
      setSaveFeedback("error")
      setSaveMessage(formatApiError(err, "Save session failed."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setSaveFeedback("unavailable")
      }
    } finally {
      setSessionBusy(false)
    }
  }

  async function handleSaveEvidenceQueue() {
    if (!backendSessionId) return
    setSessionBusy(true)
    setSaveMessage("")
    setSaveFeedback("saving")
    try {
      for (const item of evidenceItems) {
        if (item.backendEvidenceId != null) {
          await patchSessionEvidence(backendSessionId, item)
        } else {
          await postSessionEvidence(backendSessionId, item)
        }
      }
      establishSnapshot()
      setSaveFeedback("saved")
      {
        const layers = new Set(evidenceItems.map((i) => i.layer))
        const evidence_layer =
          layers.size === 0 ? "none" : layers.size === 1 ? [...layers][0]! : "multiple"
        const has_warnings = evidenceItems.some(
          (i) => (i.warnings?.length ?? 0) > 0 || i.status === "warning",
        )
        const has_contradictions = evidenceItems.some((i) => (i.contradictions?.length ?? 0) > 0)
        trackEvidenceAdded({
          session_id: backendSessionId ?? undefined,
          metadata: {
            evidence_layer,
            source_tab: "session_controls",
            has_warnings,
            has_contradictions,
          },
        })
      }
    } catch (err) {
      setSaveFeedback("error")
      setSaveMessage(formatApiError(err, "Save evidence queue failed."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setSaveFeedback("unavailable")
      }
    } finally {
      setSessionBusy(false)
    }
  }

  async function handleSaveUnified() {
    if (!backendSessionId) return
    setSessionBusy(true)
    setSaveMessage("")
    setSaveFeedback("saving")
    try {
      await postUnifiedEvidence(backendSessionId, latestUnifiedConfidenceResult)
      establishSnapshot()
      setSaveFeedback("saved")
      {
        const evidence_layer_count = evidenceItems.filter((i) => i.selectedForUnified).length
        const contradiction_count = evidenceItems.reduce((acc, i) => acc + (i.contradictions?.length ?? 0), 0)
        const warning_count = evidenceItems.reduce((acc, i) => acc + (i.warnings?.length ?? 0), 0)
        trackUnifiedEvidenceBuilt({
          session_id: backendSessionId,
          metadata: {
            evidence_layer_count,
            contradiction_count,
            warning_count,
          },
        })
      }
    } catch (err) {
      setSaveFeedback("error")
      setSaveMessage(formatApiError(err, "Save unified evidence failed."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setSaveFeedback("unavailable")
      }
    } finally {
      setSessionBusy(false)
    }
  }

  async function handleSaveReview() {
    if (!backendSessionId) return
    setSessionBusy(true)
    setSaveMessage("")
    setSaveFeedback("saving")
    try {
      await postSessionReview(backendSessionId, reviewState ?? {})
      establishSnapshot()
      setSaveFeedback("saved")
    } catch (err) {
      setSaveFeedback("error")
      setSaveMessage(formatApiError(err, "Save review failed."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setSaveFeedback("unavailable")
      }
    } finally {
      setSessionBusy(false)
    }
  }

  function handleLoadSessionClick() {
    const id = sessionIdInput.trim()
    if (!id) {
      setSaveMessage("Enter a session id to load.")
      setSaveFeedback("error")
      return
    }
    urlSessionHandledRef.current = null
    router.replace(`/spectracheck?sessionId=${encodeURIComponent(id)}`)
  }

  function handleNewSession() {
    setBackendSessionId(null)
    setSessionRecord(null)
    setSessionIdInput("")
    setReviewState(null)
    replaceEvidenceItems([])
    setLatestUnifiedConfidenceResult(null)
    setLatestReportResult(null)
    urlSessionHandledRef.current = null
    snapshotRef.current = ""
    router.replace("/spectracheck")
    setSaveFeedback("idle")
    setSaveMessage("")
  }

  const [devSnapshots, setDevSnapshots] = useState<Record<string, unknown>>({})
  const registerDev = useCallback((key: string, value: unknown) => {
    setDevSnapshots((prev) => ({ ...prev, [key]: value }))
  }, [])
  const regulatoryEvidenceItemIds = useMemo(
    () =>
      evidenceItems
        .map((item) => item.backendEvidenceId)
        .filter((v): v is number => typeof v === "number"),
    [evidenceItems],
  )
  const overviewDataState: DataStateKind =
    overview?.loading === true ? "loading" : overview?.sessionsDataAvailable === true ? "live" : "unavailable"
  const localAnalysisCount =
    recentAnalysisJobIds.length +
    (nmrResult != null ? 1 : 0) +
    (deptAnalyzeResult != null ? 1 : 0) +
    (nmr2dResult != null ? 1 : 0) +
    (simResult != null ? 1 : 0) +
    (candResult != null ? 1 : 0)
  const totalAnalyses =
    overview?.sessionsDataAvailable === true ? overview.sessions.length : localAnalysisCount
  const pendingReviewCount =
    overview?.sessionsDataAvailable === true && overview.metrics
      ? overview.metrics.reviewRequired
      : evidenceItems.filter((item) => item.status === "pending_review" || item.status === "warning").length
  const contradictionCount =
    overview?.sessionsDataAvailable === true && overview.metrics
      ? overview.metrics.reviewRequiredWithContradictions
      : evidenceItems.filter((item) => (item.contradictions?.length ?? 0) > 0).length
  const reportsReadyCount =
    overview?.sessionsDataAvailable === true && overview.metrics
      ? overview.metrics.reportsReady
      : latestReportResult != null
        ? 1
        : 0

  const workspaceHydratedRef = useRef(false)
  useLayoutEffect(() => {
    if (workspaceHydratedRef.current) return
    workspaceHydratedRef.current = true
    const s = consumeSpectraCheckSessionHydration()
    if (!s) return
    if (s.sampleId.trim()) setSampleId(s.sampleId)
    if (s.solventChoice.trim()) setSolventChoice(s.solventChoice)
    setCustomSolvent(s.customSolvent ?? "")
    if (typeof s.candidatesText === "string" && s.candidatesText.trim()) setCandidatesText(s.candidatesText)
    if (typeof s.protonText === "string") setProtonText(s.protonText)
    if (typeof s.carbonText === "string") setCarbonText(s.carbonText)
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (backendSessionId) return
    const t = window.setTimeout(() => {
      saveSpectraCheckEvidenceSession({
        v: 1,
        sampleId,
        solventChoice,
        customSolvent,
        candidatesText,
        protonText,
        carbonText,
        evidenceItems: sanitizeEvidenceItemsForStorage(evidenceItems),
        latestUnifiedConfidenceResult,
        latestReportResult,
      })
    }, 400)
    return () => window.clearTimeout(t)
  }, [
    backendSessionId,
    sampleId,
    solventChoice,
    customSolvent,
    candidatesText,
    protonText,
    carbonText,
    evidenceItems,
    latestUnifiedConfidenceResult,
    latestReportResult,
  ])

  function clearSessionEvidence() {
    clearSpectraCheckEvidenceSession()
    setSampleId("SAMPLE-001")
    setSolventChoice("CDCl3")
    setCustomSolvent("")
    setCandidatesText(defaultCandidates)
    setProtonText(defaultProton)
    setCarbonText(defaultCarbon)
    clearEvidenceItems()
    setLatestUnifiedConfidenceResult(null)
    setLatestReportResult(null)
  }

  return (
    <div className="min-w-0 space-y-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-teal)" }}
        >
          MolTrace · SpectraCheck
        </p>
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">SpectraCheck</h1>
            <InfoTooltip
              className="shrink-0"
              content="SpectraCheck combines NMR and MS evidence to rank candidate structures, surface contradictions, and prepare report-ready results."
              label="About SpectraCheck"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <FeedbackButton module="spectracheck" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
            <SpectraCheckSystemStatusBadges />
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Review spectral evidence, structure candidates, contradictions, and human sign-off.
        </p>
      </div>

      <SpectraCheckSessionControls
        projects={projectsRows}
        samples={samplesRows}
        selectedProjectId={selectedProjectId}
        selectedSampleId={selectedSampleId}
        onProjectChange={setSelectedProjectId}
        onSampleChange={setSelectedSampleId}
        backendSessionId={backendSessionId}
        sessionIdInput={sessionIdInput}
        onSessionIdInputChange={setSessionIdInput}
        reviewState={reviewState}
        saveFeedback={saveFeedback}
        saveMessage={saveMessage}
        busy={sessionBusy}
        onLoadSession={handleLoadSessionClick}
        onSaveSession={() => void handleSaveSession()}
        onNewSession={handleNewSession}
        onSaveEvidenceQueue={() => void handleSaveEvidenceQueue()}
        onSaveUnified={() => void handleSaveUnified()}
        onSaveReview={() => void handleSaveReview()}
      />

      <SpectraCheckKnowledgeLinksCard backendSessionId={backendSessionId} />

      <AlertCard
        variant="warning"
        title="Human review required · local session"
        description="AI spectral interpretation requires chemist review before final reporting. Session state is stored locally in this browser — not for regulated storage."
        action={
          <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={clearSessionEvidence}>
            Clear session evidence
          </Button>
        }
      />

      <SpectraCheckWorkspaceSessionProvider
        value={{
          backendSessionId,
          workspaceSampleId: sampleId,
          sessionFiles: spectracheckSessionFiles,
          refreshSessionFiles: refreshSpectracheckSessionFiles,
          registerAnalysisJob: registerSpectracheckAnalysisJob,
          recentJobIds: recentAnalysisJobIds,
        }}
      >
      <div className="min-h-0 min-w-0">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full min-w-0">
        <div className="min-w-0 overflow-x-auto pb-2 [-webkit-overflow-scrolling:touch]">
          <TabsList className="inline-flex h-auto min-h-9 w-max min-w-0 max-w-full flex-nowrap justify-start gap-1 sm:flex-wrap">
            <SpectraCheckTabWithTooltip
              value="tab-overview"
              className={tabTriggerClass}
              tooltip="Summary of available evidence, backend connection status, and next recommended actions."
            >
              Overview
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-workflow"
              className={tabTriggerClass}
              tooltip="Workflow templates run a predefined sequence of analysis, QC, evidence, unified confidence, and report steps so the session can be reproduced."
            >
              Workflow
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-nmr-text"
              className={tabTriggerClass}
              tooltip="Enter candidate structures and literature-style 1H/13C NMR text for quick structure-evidence comparison."
            >
              NMR text + candidates
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-processed"
              className={tabTriggerClass}
              tooltip="Upload processed spectrum files such as CSV, TSV, TXT, or JCAMP-DX for preview, peak picking, and evidence matching."
            >
              Processed 1H / 13C upload
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-raw-fid"
              className={tabTriggerClass}
              tooltip="Upload raw Bruker or Agilent/Varian FID archives for non-destructive processing. Raw data should remain immutable."
            >
              Raw FID upload
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-dept-2d"
              className={tabTriggerClass}
              tooltip="Use DEPT/APT carbon typing and COSY, HSQC/HMQC, or HMBC correlations as supporting connectivity evidence."
            >
              DEPT/APT + 2D NMR
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-predicted"
              className={tabTriggerClass}
              tooltip="Compare observed NMR evidence against candidate-specific predicted 1H, 13C, and HSQC-style signals."
            >
              Predicted NMR matching
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-ms-evidence"
              className={tabTriggerClass}
              tooltip="HRMS, formula search, adduct inference, MS/MS, fragmentation, and optional LC-MS feature workflows using shared session inputs."
            >
              MS Evidence
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-evidence-queue"
              className={tabTriggerClass}
              tooltip="Queue session evidence items for triage, review, and unified-evidence preparation."
            >
              Evidence Queue
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-unified"
              className={tabTriggerClass}
              tooltip="Combine available NMR/MS evidence layers into a transparent candidate confidence summary."
            >
              Unified evidence
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-report"
              className={tabTriggerClass}
              tooltip="Prepare a reviewer-ready structure elucidation report with evidence, warnings, provenance, and human approval state."
            >
              Report
            </SpectraCheckTabWithTooltip>
            <SpectraCheckTabWithTooltip
              value="tab-dev-json"
              className={tabTriggerClass}
              tooltip="Raw backend responses for debugging, validation, and frontend/backend schema inspection."
            >
              Developer JSON
            </SpectraCheckTabWithTooltip>
          </TabsList>
        </div>

        <TabsContent value="tab-overview" className="mt-4 space-y-4">
          <section className="space-y-3" aria-labelledby="spectracheck-summary-heading">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 id="spectracheck-summary-heading" className="font-mono text-lg font-bold tracking-tight">
                  Analysis summary
                </h2>
                <p className="text-sm text-muted-foreground">
                  Current SpectraCheck activity from saved sessions and local workbench state.
                </p>
              </div>
              <DataStateBadge state={overviewDataState} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard
                title="Total analyses"
                icon={BarChart3}
                accent="teal"
                value={overview?.loading ? "…" : totalAnalyses}
                sub={
                  <p className="mt-1 text-xs text-muted-foreground">
                    {overview?.sessionsDataAvailable ? "Saved SpectraCheck sessions." : "Local analysis activity only."}
                  </p>
                }
              />
              <KpiCard
                title="Pending review"
                icon={AlertCircle}
                accent="teal"
                severity={!overview?.loading && pendingReviewCount > 0 ? "warning" : "neutral"}
                value={overview?.loading ? "…" : pendingReviewCount}
                sub={<p className="mt-1 text-xs text-muted-foreground">Items requiring reviewer attention.</p>}
                onClick={() => setActiveTab("tab-evidence-queue")}
                onClickLabel="Open Evidence Queue tab"
              />
              <KpiCard
                title="Contradictions"
                icon={AlertTriangle}
                accent="teal"
                severity={!overview?.loading && contradictionCount > 0 ? "critical" : "neutral"}
                value={overview?.loading ? "…" : contradictionCount}
                sub={<p className="mt-1 text-xs text-muted-foreground">Conflicting evidence signals.</p>}
                onClick={() => setActiveTab("tab-evidence-queue")}
                onClickLabel="Open Evidence Queue tab"
              />
              <KpiCard
                title="Reports ready"
                icon={FileText}
                accent="teal"
                severity={!overview?.loading && reportsReadyCount > 0 ? "success" : "neutral"}
                value={overview?.loading ? "…" : reportsReadyCount}
                sub={<p className="mt-1 text-xs text-muted-foreground">Report-ready or locally generated outputs.</p>}
                onClick={() => setActiveTab("tab-report")}
                onClickLabel="Open Report tab"
              />
            </div>
            {!overview?.loading && totalAnalyses === 0 ? (
              <DataState
                state={overviewDataState === "live" ? "empty" : overviewDataState}
                title="No SpectraCheck analyses yet."
                description="Use the existing session controls or upload/start-analysis areas below to begin; no new upload flow is created here."
              />
            ) : null}
          </section>

          <section className="space-y-3" aria-labelledby="spectracheck-evidence-workbench-heading">
            <div>
              <h2 id="spectracheck-evidence-workbench-heading" className="font-mono text-lg font-bold tracking-tight">
                Evidence queue
              </h2>
              <p className="text-sm text-muted-foreground">
                Human-review view of queued spectral evidence and contradictions.
              </p>
            </div>
            {evidenceItems.length > 0 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                {evidenceItems.slice(0, 2).map((item) => (
                  <EvidenceCard
                    key={item.id}
                    title={item.title}
                    module="spectracheck"
                    status={mapEvidenceCardStatus(item)}
                    confidence_score={item.score}
                    confidence_label={item.label}
                    risk_level={mapEvidenceRisk(item)}
                    summary={item.summary ?? item.evidenceSummary?.[0] ?? "Queued evidence is available for review."}
                    evidence_items={item.evidenceSummary ?? item.notes ?? []}
                    contradictions={item.contradictions ?? []}
                    citations={[]}
                    model_name={item.modelName}
                    model_version={item.modelVersion}
                    last_updated_at={item.createdAt}
                    review_status={item.qcStatus ?? item.readinessStatus ?? item.status}
                    onOpenDetails={() => setActiveTab("tab-evidence-queue")}
                  />
                ))}
              </div>
            ) : (
              <EvidenceCard
                title="SpectraCheck evidence queue"
                module="spectracheck"
                status="unavailable"
                risk_level="unknown"
                summary="No queued spectral evidence is available in this session."
                evidence_items={["No SpectraCheck analyses yet."]}
                citations={[]}
                review_status="empty"
                onOpenDetails={() => setActiveTab("tab-evidence-queue")}
              />
            )}
          </section>

          <SessionValueSummaryCard sessionId={backendSessionId} />
          <SpectraCheckLinkedCompoundCard
            backendSessionId={backendSessionId}
            sessionRecord={sessionRecord}
            candidatesText={candidatesText}
            onSessionRefresh={refreshLoadedSession}
          />
          <div className="grid gap-4 lg:grid-cols-2">
            <ModuleCard
              accent="teal"
              eyebrow="Spectroscopy · Workflow"
              title="How the workflow runs"
              description="From session inputs to a reviewer-ready report."
            >
              <p className="text-muted-foreground">
                Set the session inputs above (project, sample, candidates, NMR text). Then use the tabs
                to upload spectra, run predictions, build cross-modal evidence, and generate a report.
              </p>
            </ModuleCard>
            <ModuleCard
              accent="teal"
              eyebrow="Spectroscopy · Evidence"
              title="How to read the evidence"
              description="Scores help you triage; the spectra decide."
            >
              <p className="text-muted-foreground">
                Confidence numbers help prioritize what to review first. Cited measurements and the
                underlying spectra are the source of truth — not the score.
              </p>
            </ModuleCard>
          </div>
          <SessionEvidenceReadinessCard sessionId={backendSessionId} />
          <SpectraCheckValidationReadinessCard sessionId={backendSessionId} />
          <SpectraCheckRegulatoryImpactCard sessionId={backendSessionId} evidenceItemIds={regulatoryEvidenceItemIds} />
          <div className="min-w-0 space-y-4">
            <UploadCenter sessionId={backendSessionId} />
            <ArtifactBrowser sessionId={backendSessionId} />
            <RecentAnalysisJobsSection jobIds={recentAnalysisJobIds} />
          </div>
        </TabsContent>

        <TabsContent value="tab-workflow" className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <FeedbackButton module="workflow" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
          </div>
          <WorkflowTemplateGallery
            selectedTemplateId={selectedWorkflowTemplate?.id ?? null}
            onTemplateSelect={setSelectedWorkflowTemplate}
          />
          <WorkflowRunLauncher
            selectedTemplate={selectedWorkflowTemplate}
            backendSessionId={backendSessionId}
            sampleId={sampleId}
            solvent={solventForApi}
            candidatesText={candidatesText}
            protonText={protonText}
            carbonText={carbonText}
            sessionFiles={spectracheckSessionFiles}
            onNavigateToTab={setActiveTab}
          />
        </TabsContent>

        <TabsContent value="tab-nmr-text" className="mt-4 space-y-6">
          <ModuleCard
            accent="teal"
            eyebrow="Spectroscopy · Session"
            title={
              <span className="inline-flex items-center gap-2">
                Shared session inputs
                <InfoTooltip
                  content="These values are shared across SpectraCheck tabs and are sent with analysis requests when available."
                  label="About Shared session inputs"
                />
              </span>
            }
            description="Paste or edit once — every tab sends these fields when relevant. Nothing here is required until you run an action in a tab."
          >
            <div className="space-y-5">
              <div className="block space-y-2">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <label htmlFor="spectracheck-sample-id">Sample ID</label>
                  <InfoTooltip
                    content="A user-editable identifier used to connect uploads, spectra, candidate ranking, and reports for the same sample."
                    label="About Sample ID"
                  />
                </div>
                <Input id="spectracheck-sample-id" value={sampleId} onChange={(e) => setSampleId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  NMR solvent
                  <InfoTooltip
                    content="Select the solvent used during acquisition. This helps interpret residual solvent peaks and chemical-shift context."
                    label="About NMR solvent"
                  />
                </span>
                <Select value={solventChoice} onValueChange={setSolventChoice}>
                  <SelectTrigger id="spectracheck-solvent" className="w-full">
                    <SelectValue placeholder="Select solvent" />
                  </SelectTrigger>
                  <SelectContent>
                    {NMR_SOLVENT_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {solventChoice === NMR_SOLVENT_OTHER_VALUE && (
                  <Input
                    aria-label="Custom solvent"
                    value={customSolvent}
                    onChange={(e) => setCustomSolvent(e.target.value)}
                  />
                )}
              </div>
              <div className="block space-y-2">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <label htmlFor="spectracheck-candidates">Candidate structures</label>
                  <InfoTooltip
                    content='Use one candidate per line. Recommended format: Name | SMILES | role.'
                    label="About Candidate structures"
                  />
                </div>
                <Textarea
                  id="spectracheck-candidates"
                  value={candidatesText}
                  onChange={(e) => setCandidatesText(e.target.value)}
                  rows={5}
                />
              </div>
              <div className="block space-y-2">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <label htmlFor="spectracheck-proton">1H NMR text</label>
                  <InfoTooltip
                    content="Paste literature-style proton NMR text including shifts, multiplicities, couplings, and integrations when available."
                    label="About 1H NMR text"
                  />
                </div>
                <Textarea id="spectracheck-proton" value={protonText} onChange={(e) => setProtonText(e.target.value)} rows={5} />
              </div>
              <div className="block space-y-2">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <label htmlFor="spectracheck-carbon">13C NMR text</label>
                  <InfoTooltip
                    content="Paste literature-style carbon NMR text or a comma-separated list of 13C chemical shifts."
                    label="About 13C NMR text"
                  />
                </div>
                <Textarea id="spectracheck-carbon" value={carbonText} onChange={(e) => setCarbonText(e.target.value)} rows={3} />
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="teal"
            eyebrow="Spectroscopy · NMR text"
            title="NMR text + candidates"
            description="Controlled by the Shared session inputs card above this tab strip."
          >
            <p className="text-muted-foreground">
              Candidate lines support <code className="text-xs">Label | SMILES | role</code> formatting; SMILES is used for 2D and MS workflows when needed.
            </p>
            <p className="text-muted-foreground">1H and 13C paste fields feed prediction and similarity tools unless you override with uploads in other tabs.</p>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="tab-processed" className="mt-4">
          <SpectraCheckProcessedSpectrumSection
            sampleId={sampleId}
            onSampleIdChange={setSampleId}
            solvent={solventForApi}
            candidatesText={candidatesText}
            registerDev={registerDev}
          />
        </TabsContent>

        <TabsContent value="tab-raw-fid" className="mt-4">
          <SpectraCheckRawFidSection
            sampleId={sampleId}
            onSampleIdChange={setSampleId}
            solvent={solventForApi}
            registerDev={registerDev}
          />
        </TabsContent>

        <TabsContent value="tab-dept-2d" className="mt-4 space-y-16">
          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · DEPT / APT
            </p>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
              <ModuleCard
                accent="teal"
                eyebrow="DEPT · Form"
                title="DEPT / APT peak table"
                description="Preview parses the table; analyze combines it with shared 13C text and solvent."
                className="min-w-0"
              >
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="dept-file">Peak table file</Label>
                    <Input id="dept-file" ref={deptFileRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Experiment type (optional)</span>
                    <Input
                      value={deptExperimentType}
                      onChange={(e) => setDeptExperimentType(e.target.value)}
                      placeholder="e.g. DEPT135"
                    />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">APT positive convention</span>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                      value={deptAptPositive}
                      onChange={(e) => setDeptAptPositive(e.target.value)}
                    >
                      <option value="CH_CH3">CH + CH3 positive</option>
                      <option value="CH_only">CH only positive</option>
                    </select>
                  </label>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Button
                      type="button"
                      variant="secondary"
                      className="w-full sm:w-auto"
                      disabled={deptPreviewLoading}
                      onClick={runDeptPreview}
                    >
                      {deptPreviewLoading ? "Previewing…" : "Preview"}
                    </Button>
                    <Button type="button" className="w-full sm:w-auto" disabled={deptAnalyzeLoading} onClick={runDeptAnalyze}>
                      {deptAnalyzeLoading ? "Analyzing…" : "Analyze"}
                    </Button>
                  </div>
                </div>
              </ModuleCard>
              <div className="min-w-0 space-y-6">
                {deptPreviewError && (
                  <AlertCard
                    variant="error"
                    title="Preview error"
                    description={deptPreviewError}
                  />
                )}
                {deptAnalyzeError && (
                  <AlertCard
                    variant="error"
                    title="Analyze error"
                    description={deptAnalyzeError}
                  />
                )}
                {deptPreviewLoading && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Running DEPT preview</CardTitle>
                      <CardDescription>Generating a quick DEPT carbon-typing preview…</CardDescription>
                    </CardHeader>
                  </Card>
                )}
                {deptAnalyzeLoading && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Running DEPT analysis</CardTitle>
                      <CardDescription>Computing carbon multiplicities from your DEPT/APT data…</CardDescription>
                    </CardHeader>
                  </Card>
                )}
                {deptPreviewResult != null && !deptPreviewLoading && (
                  <div className="space-y-3">
                    <p className="text-sm font-medium text-muted-foreground">Preview result</p>
                    <SummarizedEvidenceView
                      result={deptPreviewResult}
                      unifiedEvidence={{
                        layer: "dept_apt",
                        sourceTab: "DEPT/APT + 2D NMR",
                        title: "DEPT/APT preview",
                        endpoint: "/carbon13/dept/preview",
                        sampleId: sampleId.trim() || undefined,
                      }}
                    />
                  </div>
                )}
                {deptAnalyzeResult != null && !deptAnalyzeLoading && (
                  <div className="space-y-3">
                    <p className="text-sm font-medium text-muted-foreground">Analyze result</p>
                    <SummarizedEvidenceView
                      result={deptAnalyzeResult}
                      unifiedEvidence={{
                        layer: "dept_apt",
                        sourceTab: "DEPT/APT + 2D NMR",
                        title: "DEPT/APT analyze",
                        endpoint: "/carbon13/dept/analyze",
                        sampleId: sampleId.trim() || undefined,
                      }}
                    />
                  </div>
                )}
                {!deptPreviewResult &&
                  !deptAnalyzeResult &&
                  !deptPreviewLoading &&
                  !deptAnalyzeLoading &&
                  !deptPreviewError &&
                  !deptAnalyzeError && (
                    <Card>
                      <CardContent className="border-dashed p-8 text-center text-sm text-muted-foreground">
                        Upload a table and choose Preview or Analyze.
                      </CardContent>
                    </Card>
                  )}
              </div>
            </div>
          </section>

          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · 2D NMR
            </p>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
              <ModuleCard
                accent="teal"
                eyebrow="2D NMR · Form"
                title="2D NMR analyze"
                description="Submit a 2D peak table for HSQC, HMBC, or COSY correlation analysis against a candidate SMILES structure."
                className="min-w-0"
              >
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="nmr2d-file">2D peak table file</Label>
                    <Input id="nmr2d-file" ref={nmr2dFileRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">SMILES (required)</span>
                    <Input value={nmr2dSmiles} onChange={(e) => setNmr2dSmiles(e.target.value)} placeholder="e.g. CCO" />
                    <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={fillSmilesFromCandidates}>
                      Use first candidate SMILES
                    </Button>
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Experiment (optional)</span>
                    <Input value={nmr2dExperiment} onChange={(e) => setNmr2dExperiment(e.target.value)} placeholder="HSQC, HMBC, …" />
                  </label>
                  <div className="flex items-center gap-2">
                    <Checkbox id="nmr2d-contour" checked={nmr2dContour} onCheckedChange={(v) => setNmr2dContour(v === true)} />
                    <Label htmlFor="nmr2d-contour" className="text-sm font-normal">
                      Include contour preview (if enabled server-side)
                    </Label>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="nmr2d-dept-file">Optional DEPT/APT file</Label>
                    <Input id="nmr2d-dept-file" ref={nmr2dDeptFileRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">DEPT experiment type (optional)</span>
                    <Input value={nmr2dDeptExperiment} onChange={(e) => setNmr2dDeptExperiment(e.target.value)} />
                  </label>
                  <Button type="button" className="w-full sm:w-auto" disabled={nmr2dLoading} onClick={runNmr2dAnalyze}>
                    {nmr2dLoading ? "Analyzing…" : "Analyze 2D NMR"}
                  </Button>
                </div>
              </ModuleCard>
              <TabResultSection
                error={nmr2dError}
                loading={nmr2dLoading}
                loadingTitle="Running 2D NMR analysis"
                loadingHint="Analyzing 2D NMR correlations…"
                emptyHint="Attach a processed 2D peak table and SMILES, then analyze."
                result={nmr2dResult}
                unifiedEvidence={{
                  layer: "nmr_2d",
                  sourceTab: "DEPT/APT + 2D NMR",
                  title: "2D NMR analyze",
                  endpoint: "/nmr2d/analyze",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
            </div>
          </section>
        </TabsContent>

        <TabsContent value="tab-predicted" className="mt-4 space-y-16">
          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Evidence Match
            </p>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
              <ModuleCard
                accent="teal"
                eyebrow="Predicted · 1H/13C"
                title="1H / 13C evidence match"
                description="Match observed NMR chemical shifts against predicted spectra for each candidate structure."
                className="min-w-0"
              >
                <form onSubmit={runNmrEvidence} className="space-y-4">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex w-full sm:w-auto">
                          <Button type="submit" disabled={nmrLoading} className="w-full sm:w-auto">
                            {nmrLoading ? "Running…" : "Run SpectraCheck Analysis"}
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                        Submit the candidate list and NMR text to the backend for candidate-specific predicted NMR matching.
                      </TooltipContent>
                    </Tooltip>
                  </form>
              </ModuleCard>
              <TabResultSection
                error={nmrError}
                loading={nmrLoading}
                loadingTitle="Running 1H / 13C evidence match"
                loadingHint="Matching predicted NMR signals to candidates…"
                emptyHint="Use the shared session inputs above, then run the analyzer."
                result={nmrResult}
                unifiedEvidence={{
                  layer: "predicted_nmr",
                  sourceTab: "Predicted NMR matching",
                  title: "1H / 13C evidence match",
                  endpoint: "/prediction/nmr/match/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
            </div>
          </section>

          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Similarity
            </p>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
              <ModuleCard
                accent="teal"
                eyebrow="Predicted · Similarity"
                title="Spectral similarity"
                description="Observed spectra default from shared 1H / 13C text. Optionally add reference spectra or paired 2D files."
                className="min-w-0"
              >
                <div className="space-y-4">
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Reference 1H text (optional)</span>
                    <Textarea
                      value={refProton}
                      onChange={(e) => setRefProton(e.target.value)}
                      rows={3}
                      placeholder="Leave empty to score observed-only layers."
                    />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Reference 13C text (optional)</span>
                    <Textarea value={refCarbon} onChange={(e) => setRefCarbon(e.target.value)} rows={3} />
                  </label>
                  <div className="space-y-2">
                    <Label>Observed 2D file (optional)</Label>
                    <Input ref={obs2dRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <div className="space-y-2">
                    <Label>Reference 2D file (optional)</Label>
                    <Input ref={ref2dRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">2D experiment type (optional)</span>
                    <Input value={simExperimentType} onChange={(e) => setSimExperimentType(e.target.value)} placeholder="HSQC" />
                  </label>
                  <Button type="button" className="w-full sm:w-auto" disabled={simLoading} onClick={runSimilarity}>
                    {simLoading ? "Scoring…" : "Score similarity"}
                  </Button>
                </div>
              </ModuleCard>
              <TabResultSection
                error={simError}
                loading={simLoading}
                loadingTitle="Scoring spectral similarity"
                loadingHint="Scoring spectral similarity…"
                emptyHint="Run scoring — 2D files require both observed and reference uploads."
                result={simResult}
                unifiedEvidence={{
                  layer: "spectral_similarity",
                  sourceTab: "Predicted NMR matching",
                  title: "Spectral similarity",
                  endpoint: "/similarity/score/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
            </div>
          </section>

          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Candidate Compare
            </p>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
              <ModuleCard
                accent="teal"
                eyebrow="Predicted · Compare"
                title="Candidate prediction / comparison"
                description="Compare candidates using predicted vs. observed NMR chemical shifts. Accepts optional DEPT/APT data and 2D correlation tables."
                className="min-w-0"
              >
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="cand-dept">Optional DEPT/APT file</Label>
                    <Input id="cand-dept" ref={candDeptRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">DEPT experiment type (optional)</span>
                    <Input value={candDeptExperiment} onChange={(e) => setCandDeptExperiment(e.target.value)} />
                  </label>
                  <div className="space-y-2">
                    <Label htmlFor="cand-nmr2d">Optional 2D peak table</Label>
                    <Input id="cand-nmr2d" ref={candNmr2dRef} type="file" accept=".csv,.tsv,.txt,.json" />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">2D experiment type (optional)</span>
                    <Input value={candNmr2dExperiment} onChange={(e) => setCandNmr2dExperiment(e.target.value)} />
                  </label>
                  <Button type="button" className="w-full sm:w-auto" disabled={candLoading} onClick={runCandidateCompare}>
                    {candLoading ? "Comparing…" : "Compare candidates (evidence)"}
                  </Button>
                </div>
              </ModuleCard>
              <TabResultSection
                error={candError}
                loading={candLoading}
                loadingTitle="Comparing candidates"
                loadingHint="Comparing candidate structures…"
                emptyHint="Uses shared candidates and NMR text; add uploads only if you have them."
                result={candResult}
                unifiedEvidence={{
                  layer: "predicted_nmr",
                  sourceTab: "Predicted NMR matching",
                  title: "Candidate prediction / comparison",
                  endpoint: "/candidates/compare/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
            </div>
          </section>
        </TabsContent>

        <TabsContent value="tab-ms-evidence" className="mt-4">
          <SpectraCheckMsEvidenceStudio sampleId={sampleId} candidatesText={candidatesText} />
        </TabsContent>

        <TabsContent value="tab-evidence-queue" className="mt-4">
          <SpectraCheckEvidenceQueuePanel
            sessionId={backendSessionId}
            onSendToUnified={() => setActiveTab("tab-unified")}
          />
        </TabsContent>

        <TabsContent value="tab-unified" className="mt-4 space-y-10">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <FeedbackButton module="unified_evidence" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
          </div>
          <SpectraCheckRegulatoryImpactCard sessionId={backendSessionId} evidenceItemIds={regulatoryEvidenceItemIds} />
          <SpectraCheckEvidenceQueueUnifiedSummary />
          <SpectraCheckConfidenceSuite
            embedMode="unified-only"
            sampleId={sampleId}
            solvent={solventForApi}
            candidatesText={candidatesText}
            protonText={protonText}
            carbonText={carbonText}
            backendSessionId={backendSessionId}
          />
          <SpectraCheckReviewCollaborationPanel sessionId={backendSessionId} />
        </TabsContent>

        <TabsContent value="tab-report" className="mt-4 space-y-10">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <FeedbackButton module="report" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
          </div>
          <SpectraCheckConfidenceSuite
            embedMode="report-only"
            sampleId={sampleId}
            solvent={solventForApi}
            candidatesText={candidatesText}
            protonText={protonText}
            carbonText={carbonText}
            backendSessionId={backendSessionId}
          />
          <SpectraCheckReviewCollaborationPanel sessionId={backendSessionId} />
        </TabsContent>

        <TabsContent value="tab-dev-json" className="mt-4 space-y-6">
          <ModuleCard
            accent="teal"
            eyebrow="Spectroscopy · Developer JSON"
            title={
              <span className="inline-flex items-center gap-2">
                Developer JSON hub
                <InfoTooltip
                  content="Use this for debugging backend response shape, warnings, and raw evidence data."
                  label="About Developer JSON hub"
                />
              </span>
            }
            description="Latest payloads returned in this browser session (including upload previews)."
          >
            <div className="space-y-6">
              {nmrResult != null && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">1H / 13C evidence</p>
                  <DeveloperJsonPanel data={nmrResult} />
                </div>
              )}
              {deptPreviewResult != null && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">DEPT preview</p>
                  <DeveloperJsonPanel data={deptPreviewResult} />
                </div>
              )}
              {deptAnalyzeResult != null && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">DEPT analyze</p>
                  <DeveloperJsonPanel data={deptAnalyzeResult} />
                </div>
              )}
              {nmr2dResult != null && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">2D NMR</p>
                  <DeveloperJsonPanel data={nmr2dResult} />
                </div>
              )}
              {simResult != null && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Similarity</p>
                  <DeveloperJsonPanel data={simResult} />
                </div>
              )}
              {candResult != null && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Candidates compare</p>
                  <DeveloperJsonPanel data={candResult} />
                </div>
              )}
              {Object.entries(devSnapshots).map(([k, v]) => (
                <div key={k} className="space-y-2">
                  <p className="text-sm font-medium">{k}</p>
                  <DeveloperJsonPanel data={v} />
                </div>
              ))}
              {nmrResult == null &&
                deptPreviewResult == null &&
                deptAnalyzeResult == null &&
                nmr2dResult == null &&
                simResult == null &&
                candResult == null &&
                Object.keys(devSnapshots).length === 0 && (
                  <p className="text-sm text-muted-foreground">Run an action in any tab to populate JSON snapshots.</p>
                )}
            </div>
          </ModuleCard>
        </TabsContent>
      </Tabs>
      </div>
      </SpectraCheckWorkspaceSessionProvider>
    </div>
  )
}
