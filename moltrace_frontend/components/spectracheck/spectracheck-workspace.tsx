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
import { SPECTRACHECK_TEXT_SPECTRUM_ACCEPT } from "@/src/lib/spectracheck/spectrum-file-formats"
import { SpectraCheckValidationReadinessCard } from "@/components/validation/validation-readiness-summary"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"
import { DataState, DataStateBadge, type DataStateKind } from "@/components/science/data-state"
import { EvidenceCard, type EvidenceRiskLevel, type EvidenceStatus } from "@/components/science/evidence-card"
import { KpiCard } from "@/components/dashboard/kpi-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  AlertCircle,
  AlertTriangle,
  Atom,
  BarChart3,
  ChevronDown,
  Eye,
  FileText,
  Network,
  Settings2,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

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

  // ── Drop-zone state for DEPT/2D file inputs (mirrors processed/raw FID pattern) ─────
  const [deptDragOver, setDeptDragOver] = useState(false)
  const [deptSelectedFile, setDeptSelectedFile] = useState<File | null>(null)
  const [deptSelectedFileName, setDeptSelectedFileName] = useState<string | null>(null)
  const [nmr2dDragOver, setNmr2dDragOver] = useState(false)
  const [nmr2dSelectedFile, setNmr2dSelectedFile] = useState<File | null>(null)
  const [nmr2dSelectedFileName, setNmr2dSelectedFileName] = useState<string | null>(null)
  const [nmr2dAdvancedOpen, setNmr2dAdvancedOpen] = useState(false)
  const [nmr2dDeptDragOver, setNmr2dDeptDragOver] = useState(false)
  const [nmr2dDeptSelectedFile, setNmr2dDeptSelectedFile] = useState<File | null>(null)
  const [nmr2dDeptSelectedFileName, setNmr2dDeptSelectedFileName] = useState<string | null>(null)

  function attachFileToRef(
    fileRef: React.RefObject<HTMLInputElement | null>,
    setSelectedFile: (f: File | null) => void,
    setSelectedFileName: (n: string | null) => void,
  ) {
    return (file: File) => {
      setSelectedFile(file)
      setSelectedFileName(file.name)
      if (fileRef.current && typeof DataTransfer !== "undefined") {
        try {
          const dt = new DataTransfer()
          dt.items.add(file)
          fileRef.current.files = dt.files
        } catch {
          // some test envs disallow assigning FileList
        }
      }
    }
  }

  const attachDeptFile = attachFileToRef(deptFileRef, setDeptSelectedFile, setDeptSelectedFileName)
  const attachNmr2dFile = attachFileToRef(nmr2dFileRef, setNmr2dSelectedFile, setNmr2dSelectedFileName)
  const attachNmr2dDeptFile = attachFileToRef(
    nmr2dDeptFileRef,
    setNmr2dDeptSelectedFile,
    setNmr2dDeptSelectedFileName,
  )

  function clearDeptFile() {
    if (deptFileRef.current) deptFileRef.current.value = ""
    setDeptSelectedFile(null)
    setDeptSelectedFileName(null)
  }
  function clearNmr2dFile() {
    if (nmr2dFileRef.current) nmr2dFileRef.current.value = ""
    setNmr2dSelectedFile(null)
    setNmr2dSelectedFileName(null)
  }
  function clearNmr2dDeptFile() {
    if (nmr2dDeptFileRef.current) nmr2dDeptFileRef.current.value = ""
    setNmr2dDeptSelectedFile(null)
    setNmr2dDeptSelectedFileName(null)
  }

  // Predicted-NMR drop-zone helpers (similarity + compare sections)
  // — declared here so they reference the refs below; closures capture the latest setters.
  function makeAttachClear(
    fileRef: { current: HTMLInputElement | null },
    setFile: (f: File | null) => void,
    setName: (n: string | null) => void,
  ) {
    return {
      attach: (file: File) => {
        setFile(file)
        setName(file.name)
        if (fileRef.current && typeof DataTransfer !== "undefined") {
          try {
            const dt = new DataTransfer()
            dt.items.add(file)
            fileRef.current.files = dt.files
          } catch {
            // best-effort
          }
        }
      },
      clear: () => {
        if (fileRef.current) fileRef.current.value = ""
        setFile(null)
        setName(null)
      },
    }
  }

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

  // ── Predicted-NMR drop-zone state (4 file inputs across Similarity + Compare) ─────
  const [obs2dDragOver, setObs2dDragOver] = useState(false)
  const [obs2dSelectedFile, setObs2dSelectedFile] = useState<File | null>(null)
  const [obs2dSelectedFileName, setObs2dSelectedFileName] = useState<string | null>(null)
  const [ref2dDragOver, setRef2dDragOver] = useState(false)
  const [ref2dSelectedFile, setRef2dSelectedFile] = useState<File | null>(null)
  const [ref2dSelectedFileName, setRef2dSelectedFileName] = useState<string | null>(null)
  const [candDeptDragOver, setCandDeptDragOver] = useState(false)
  const [candDeptSelectedFile, setCandDeptSelectedFile] = useState<File | null>(null)
  const [candDeptSelectedFileName, setCandDeptSelectedFileName] = useState<string | null>(null)
  const [candNmr2dDragOver, setCandNmr2dDragOver] = useState(false)
  const [candNmr2dSelectedFile, setCandNmr2dSelectedFile] = useState<File | null>(null)
  const [candNmr2dSelectedFileName, setCandNmr2dSelectedFileName] = useState<string | null>(null)
  const [predictedAdvancedOpen, setPredictedAdvancedOpen] = useState(false)
  const [compareAdvancedOpen, setCompareAdvancedOpen] = useState(false)

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
    const file = deptFileRef.current?.files?.[0] ?? deptSelectedFile
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
    const file = deptFileRef.current?.files?.[0] ?? deptSelectedFile
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
    const file = nmr2dFileRef.current?.files?.[0] ?? nmr2dSelectedFile
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
    const deptF = nmr2dDeptFileRef.current?.files?.[0] ?? nmr2dDeptSelectedFile
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
    const o2 = obs2dRef.current?.files?.[0] ?? obs2dSelectedFile
    const r2 = ref2dRef.current?.files?.[0] ?? ref2dSelectedFile
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
    const d = candDeptRef.current?.files?.[0] ?? candDeptSelectedFile
    if (d) {
      fd.append("dept_apt_file", d)
      if (candDeptExperiment.trim()) fd.append("dept_apt_experiment_type", candDeptExperiment.trim())
    }
    const n2 = candNmr2dRef.current?.files?.[0] ?? candNmr2dSelectedFile
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

        <TabsContent value="tab-overview" className="mt-4 space-y-12">
          {/* ── Section 1 · KPI summary ───────────────────────────────────────────── */}
          <section className="space-y-4" aria-labelledby="spectracheck-summary-heading">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="space-y-1">
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Spectroscopy · At a glance
                </p>
                <h2 id="spectracheck-summary-heading" className="font-mono text-xl font-bold tracking-tight">
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

          {/* ── Section 2 · Evidence preview ──────────────────────────────────────── */}
          <section className="space-y-4" aria-labelledby="spectracheck-evidence-workbench-heading">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Triage
              </p>
              <h2 id="spectracheck-evidence-workbench-heading" className="font-mono text-xl font-bold tracking-tight">
                Evidence queue preview
              </h2>
              <p className="text-sm text-muted-foreground">
                Top items from the human-review queue — full list lives in the Evidence Queue tab.
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

          {/* ── Section 3 · Session context (value + linked compound) ─────────────── */}
          <section className="space-y-4">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Session context
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Saved-session value & linked compound</h2>
              <p className="text-sm text-muted-foreground">
                Snapshot of the current backend session and any compound it is bound to.
              </p>
            </div>
            <div className="space-y-4">
              <SessionValueSummaryCard sessionId={backendSessionId} />
              <SpectraCheckLinkedCompoundCard
                backendSessionId={backendSessionId}
                sessionRecord={sessionRecord}
                candidatesText={candidatesText}
                onSessionRefresh={refreshLoadedSession}
              />
            </div>
          </section>

          {/* ── Section 4 · Workflow + Evidence guidance cards ────────────────────── */}
          <section className="space-y-4">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · How it works
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Quick orientation</h2>
              <p className="text-sm text-muted-foreground">
                Two short reads — what the workflow does, and how to interpret the evidence panel.
              </p>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <ModuleCard
                accent="teal"
                eyebrow="Workflow · Guide"
                title="How the workflow runs"
                icon={Network}
                description="From session inputs to a reviewer-ready report."
              >
                <p className="text-muted-foreground">
                  Set the session inputs above (project, sample, candidates, NMR text). Then use the tabs
                  to upload spectra, run predictions, build cross-modal evidence, and generate a report.
                </p>
              </ModuleCard>
              <ModuleCard
                accent="teal"
                eyebrow="Evidence · Guide"
                title="How to read the evidence"
                icon={Eye}
                description="Scores help you triage; the spectra decide."
              >
                <p className="text-muted-foreground">
                  Confidence numbers help prioritize what to review first. Cited measurements and the
                  underlying spectra are the source of truth — not the score.
                </p>
              </ModuleCard>
            </div>
          </section>

          {/* ── Section 5 · Readiness & impact stack ──────────────────────────────── */}
          <section className="space-y-4">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Readiness & impact
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Evidence, validation & regulatory readiness</h2>
              <p className="text-sm text-muted-foreground">
                Pre-flight checks across analytical evidence, validation packages, and regulatory exposure.
              </p>
            </div>
            <div className="space-y-4">
              <SessionEvidenceReadinessCard sessionId={backendSessionId} />
              <SpectraCheckValidationReadinessCard sessionId={backendSessionId} />
              <SpectraCheckRegulatoryImpactCard sessionId={backendSessionId} evidenceItemIds={regulatoryEvidenceItemIds} />
            </div>
          </section>

          {/* ── Section 6 · Activity (uploads + artifacts + recent jobs) ──────────── */}
          <section className="space-y-4">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Activity
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Uploads, artifacts & recent jobs</h2>
              <p className="text-sm text-muted-foreground">
                Files attached to this session, downstream artifacts, and the most recent analysis runs.
              </p>
            </div>
            <div className="min-w-0 space-y-4">
              <UploadCenter sessionId={backendSessionId} />
              <ArtifactBrowser sessionId={backendSessionId} />
              <RecentAnalysisJobsSection jobIds={recentAnalysisJobIds} />
            </div>
          </section>
        </TabsContent>

        <TabsContent value="tab-workflow" className="mt-4 space-y-12">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Workflow Runner
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Pre-built analysis pipelines</h2>
              <p className="text-sm text-muted-foreground">
                Pick a template, then launch it against the current session — no need to wire up tabs by hand.
              </p>
            </div>
            <FeedbackButton module="workflow" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
          </div>

          {/* Step 1 — Choose workflow template */}
          <ModuleCard
            accent="teal"
            eyebrow="Workflow · Step 1 · Setup"
            title="Choose a workflow template"
            icon={Network}
            description="Each template bundles a sequence of SpectraCheck analyses tailored to a specific scenario."
            className="min-w-0"
          >
            <WorkflowTemplateGallery
              selectedTemplateId={selectedWorkflowTemplate?.id ?? null}
              onTemplateSelect={setSelectedWorkflowTemplate}
            />
          </ModuleCard>

          {/* Step 2 — Launch the chosen workflow */}
          <ModuleCard
            accent="teal"
            eyebrow="Workflow · Step 2 · Run"
            title="Launch & monitor the workflow"
            icon={Zap}
            description={
              selectedWorkflowTemplate
                ? `Selected: ${selectedWorkflowTemplate.name}. Review session inputs below, then launch.`
                : "Choose a template above to enable launching."
            }
            className="min-w-0"
          >
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
          </ModuleCard>
        </TabsContent>

        <TabsContent value="tab-nmr-text" className="mt-4 space-y-12">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Shared Session
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">NMR text & candidate structures</h2>
            <p className="text-sm text-muted-foreground">
              These values flow into every analyzer in SpectraCheck. Edit once, use everywhere.
            </p>
          </div>

          {/* Step 1 — Session identity (Sample ID + Solvent) */}
          <ModuleCard
            accent="teal"
            eyebrow="Session · Step 1 · Identify"
            title="Sample identity & solvent"
            icon={Atom}
            description="Bind this workspace to a sample ID and select the acquisition solvent for chemical-shift context."
            className="min-w-0"
          >
            <div className="space-y-5">
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="spectracheck-sample-id" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Sample ID
                  </Label>
                  <InfoTooltip
                    content="A user-editable identifier used to connect uploads, spectra, candidate ranking, and reports for the same sample."
                    label="About Sample ID"
                  />
                </div>
                <Input
                  id="spectracheck-sample-id"
                  value={sampleId}
                  onChange={(e) => setSampleId(e.target.value)}
                  className="font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    NMR solvent
                  </Label>
                  <InfoTooltip
                    content="Select the solvent used during acquisition. This helps interpret residual solvent peaks and chemical-shift context."
                    label="About NMR solvent"
                  />
                </div>
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
                    placeholder="Type custom solvent…"
                    className="font-mono"
                  />
                )}
              </div>
            </div>
          </ModuleCard>

          {/* Step 2 — Candidate structures */}
          <ModuleCard
            accent="teal"
            eyebrow="Session · Step 2 · Candidates"
            title="Candidate structures"
            icon={Network}
            description="One candidate per line. Format: Name | SMILES | role. Used by predicted matching, similarity, MS, and 2D workflows."
            className="min-w-0"
          >
            <div className="space-y-3">
              <div className="flex items-center gap-1.5">
                <Label htmlFor="spectracheck-candidates" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Candidate structures
                </Label>
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
                className="font-mono text-xs"
              />
              <div className="flex flex-wrap gap-2">
                <span
                  className="rounded-md border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                  style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                >
                  {candidatesText.split("\n").filter((l) => l.trim()).length} line{candidatesText.split("\n").filter((l) => l.trim()).length === 1 ? "" : "s"}
                </span>
                <span
                  className="rounded-md border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground"
                  style={{ borderColor: "var(--border)" }}
                >
                  Format: Name | SMILES | role
                </span>
              </div>
            </div>
          </ModuleCard>

          {/* Step 3 — Observed NMR text (1H + 13C) */}
          <ModuleCard
            accent="teal"
            eyebrow="Session · Step 3 · Observed NMR"
            title="Paste 1H and 13C NMR text"
            icon={FileText}
            description="Literature-style text fields. These feed prediction & similarity tools unless overridden by uploads in other tabs."
            className="min-w-0"
          >
            <div className="space-y-5">
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="spectracheck-proton" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    1H NMR text
                  </Label>
                  <InfoTooltip
                    content="Paste literature-style proton NMR text including shifts, multiplicities, couplings, and integrations when available."
                    label="About 1H NMR text"
                  />
                  <span
                    className="ml-auto rounded-md border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                    style={{
                      borderColor: protonText.trim() ? "var(--mt-teal)" : "var(--border)",
                      color: protonText.trim() ? "var(--mt-teal)" : "var(--muted-foreground)",
                      backgroundColor: protonText.trim() ? "var(--mt-teal-soft)" : "transparent",
                    }}
                  >
                    {protonText.trim() ? "Detected ✓" : "Empty"}
                  </span>
                </div>
                <Textarea
                  id="spectracheck-proton"
                  value={protonText}
                  onChange={(e) => setProtonText(e.target.value)}
                  rows={5}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="spectracheck-carbon" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    13C NMR text
                  </Label>
                  <InfoTooltip
                    content="Paste literature-style carbon NMR text or a comma-separated list of 13C chemical shifts."
                    label="About 13C NMR text"
                  />
                  <span
                    className="ml-auto rounded-md border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                    style={{
                      borderColor: carbonText.trim() ? "var(--mt-teal)" : "var(--border)",
                      color: carbonText.trim() ? "var(--mt-teal)" : "var(--muted-foreground)",
                      backgroundColor: carbonText.trim() ? "var(--mt-teal-soft)" : "transparent",
                    }}
                  >
                    {carbonText.trim() ? "Detected ✓" : "Empty"}
                  </span>
                </div>
                <Textarea
                  id="spectracheck-carbon"
                  value={carbonText}
                  onChange={(e) => setCarbonText(e.target.value)}
                  rows={3}
                  className="font-mono text-xs"
                />
              </div>
            </div>
          </ModuleCard>

          {/* Tip card */}
          <div
            className="rounded-xl border px-4 py-3"
            style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
          >
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Tip
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Candidate lines accept <code className="rounded bg-background/60 px-1 font-mono text-xs">Label | SMILES | role</code>.
              The SMILES is what 2D and MS workflows pick up automatically.
            </p>
          </div>
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
          {/* ── DEPT / APT section ──────────────────────────────────────── */}
          <section className="space-y-6">
            {/* Step 1 — Setup & Upload (DEPT) */}
            <ModuleCard
              accent="teal"
              eyebrow="DEPT · Step 1 · Setup"
              title="Configure & upload DEPT/APT peak table"
              icon={Upload}
              description="Set the experiment type and APT convention, then drop a peak table (CSV / TSV / JSON)."
              className="min-w-0"
            >
              <div className="space-y-5">
                {/* Experiment type pill toggle */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Experiment type
                  </Label>
                  <div className="inline-flex flex-wrap rounded-lg border border-input bg-background p-0.5">
                    {[
                      { value: "", label: "Auto" },
                      { value: "DEPT45", label: "DEPT45" },
                      { value: "DEPT90", label: "DEPT90" },
                      { value: "DEPT135", label: "DEPT135" },
                      { value: "APT", label: "APT" },
                    ].map((option) => (
                      <button
                        key={option.value || "auto"}
                        type="button"
                        onClick={() => setDeptExperimentType(option.value)}
                        className={cn(
                          "rounded-md px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-wide transition-colors",
                          deptExperimentType === option.value
                            ? "shadow-sm"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                        style={
                          deptExperimentType === option.value
                            ? { backgroundColor: "var(--mt-teal)", color: "#04080F" }
                            : undefined
                        }
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Sent as <code className="text-[10px]">experiment_type</code> when set.
                  </p>
                </div>

                {/* APT positive convention pill toggle */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    APT positive convention
                  </Label>
                  <div className="inline-flex rounded-lg border border-input bg-background p-0.5">
                    {[
                      { value: "CH_CH3", label: "CH + CH3" },
                      { value: "CH_only", label: "CH only" },
                    ].map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setDeptAptPositive(option.value)}
                        className={cn(
                          "rounded-md px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-wide transition-colors",
                          deptAptPositive === option.value
                            ? "shadow-sm"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                        style={
                          deptAptPositive === option.value
                            ? { backgroundColor: "var(--mt-teal)", color: "#04080F" }
                            : undefined
                        }
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Shared with 2D NMR. Determines which carbons appear positive in the DEPT spectrum.
                  </p>
                </div>

                {/* Drop-zone file picker */}
                <div className="space-y-1.5">
                  <Label htmlFor="dept-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Peak table file
                  </Label>
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label="Drop DEPT/APT peak table or press Enter to browse"
                    onClick={() => deptFileRef.current?.click()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        deptFileRef.current?.click()
                      }
                    }}
                    onDragOver={(e) => {
                      e.preventDefault()
                      setDeptDragOver(true)
                    }}
                    onDragLeave={() => setDeptDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault()
                      setDeptDragOver(false)
                      const f = e.dataTransfer.files?.[0]
                      if (f) attachDeptFile(f)
                    }}
                    className={cn(
                      "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-7 text-center transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                      deptDragOver
                        ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                        : deptSelectedFileName
                        ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                        : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                    )}
                  >
                    <Upload
                      className="mb-2 h-6 w-6"
                      style={{ color: deptDragOver || deptSelectedFileName ? "var(--mt-teal)" : undefined }}
                      aria-hidden
                    />
                    <p className="font-mono text-sm font-bold tracking-tight">
                      {deptSelectedFileName ? "File ready" : deptDragOver ? "Drop to attach" : "Drop peak table or click to browse"}
                    </p>
                    <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                      CSV · TSV · JSON
                    </p>
                  </div>
                  <input
                    id="dept-file"
                    ref={deptFileRef}
                    type="file"
                    accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                    className="sr-only"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) {
                        setDeptSelectedFile(f)
                        setDeptSelectedFileName(f.name)
                      } else {
                        setDeptSelectedFile(null)
                        setDeptSelectedFileName(null)
                      }
                    }}
                  />
                  {deptSelectedFileName ? (
                    <div
                      className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                      style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                        <span className="truncate font-mono text-xs">{deptSelectedFileName}</span>
                      </div>
                      <button
                        type="button"
                        onClick={clearDeptFile}
                        className="text-muted-foreground hover:text-foreground"
                        aria-label="Remove selected DEPT file"
                      >
                        <X className="h-3.5 w-3.5" aria-hidden />
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </ModuleCard>

            {/* Step 2 — Run (DEPT) */}
            <ModuleCard
              accent="teal"
              eyebrow="DEPT · Step 2 · Run"
              title="Preview or analyze"
              icon={Zap}
              description="Preview parses the table; Analyze combines it with shared 13C text and solvent."
              className="min-w-0"
            >
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  {/* Preview tile */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        disabled={deptPreviewLoading}
                        onClick={runDeptPreview}
                        className={cn(
                          "group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                          "hover:-translate-y-px hover:shadow-md",
                          deptPreviewLoading
                            ? "cursor-wait opacity-70"
                            : "border-input hover:border-[color:var(--mt-teal)]/40"
                        )}
                        style={{ borderTop: "3px solid var(--mt-teal)" }}
                      >
                        <div className="flex w-full items-center justify-between">
                          <span
                            className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                            style={{ color: "var(--mt-teal)" }}
                          >
                            <Eye className="h-3.5 w-3.5" aria-hidden />
                            Preview
                          </span>
                          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                            Quick parse
                          </span>
                        </div>
                        <span className="font-mono text-base font-bold leading-tight">
                          {deptPreviewLoading ? "Previewing…" : "Inspect peak table"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Parse the uploaded peak table and show DEPT carbon typing.
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                      POST /carbon13/dept/preview
                    </TooltipContent>
                  </Tooltip>

                  {/* Analyze tile (primary) */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        disabled={deptAnalyzeLoading}
                        onClick={runDeptAnalyze}
                        className={cn(
                          "group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                          "hover:-translate-y-px hover:shadow-md",
                          deptAnalyzeLoading
                            ? "cursor-wait opacity-70"
                            : "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]"
                        )}
                        style={{
                          borderTop: "3px solid var(--mt-teal)",
                          backgroundColor: "var(--mt-teal-soft)",
                        }}
                      >
                        <div className="flex w-full items-center justify-between">
                          <span
                            className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                            style={{ color: "var(--mt-teal)" }}
                          >
                            <Sparkles className="h-3.5 w-3.5" aria-hidden />
                            Analyze
                          </span>
                          <span
                            className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                            style={{ color: "var(--mt-teal)" }}
                          >
                            Recommended
                          </span>
                        </div>
                        <span className="font-mono text-base font-bold leading-tight">
                          {deptAnalyzeLoading ? "Analyzing…" : "Run carbon-type evidence"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Combine peak table with shared 13C text + solvent for full carbon multiplicity analysis.
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                      POST /carbon13/dept/analyze
                    </TooltipContent>
                  </Tooltip>
                </div>

                {deptPreviewError && (
                  <AlertCard variant="error" title="Preview failed" description={deptPreviewError} />
                )}
                {deptAnalyzeError && (
                  <AlertCard variant="error" title="Analyze failed" description={deptAnalyzeError} />
                )}
              </div>
            </ModuleCard>

            {/* Loading skeleton */}
            {(deptPreviewLoading || deptAnalyzeLoading) && (
              <Card
                className="overflow-hidden rounded-xl py-0"
                style={{ borderTop: "3px solid var(--mt-teal)" }}
              >
                <CardContent className="flex items-center gap-3 py-5">
                  <div
                    className="h-2 w-2 animate-pulse rounded-full"
                    style={{ backgroundColor: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <p className="font-mono text-sm font-bold tracking-tight">
                    {deptPreviewLoading ? "Previewing DEPT/APT…" : "Analyzing DEPT/APT…"}
                  </p>
                  <p className="text-xs text-muted-foreground">Waiting for API response</p>
                </CardContent>
              </Card>
            )}

            {/* Step 3 — Results (DEPT) */}
            {(deptPreviewResult != null || deptAnalyzeResult != null) &&
              !deptPreviewLoading &&
              !deptAnalyzeLoading && (
                <ModuleCard
                  accent="teal"
                  eyebrow="DEPT · Step 3 · Results"
                  title={deptAnalyzeResult != null ? "DEPT/APT analysis output" : "DEPT/APT preview output"}
                  icon={BarChart3}
                  description={
                    deptAnalyzeResult != null
                      ? "Carbon multiplicities and matching evidence from /carbon13/dept/analyze."
                      : "Parsed peak table preview from /carbon13/dept/preview."
                  }
                  className="min-w-0"
                >
                  <div className="space-y-4">
                    {deptAnalyzeResult != null && (
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
                    )}
                    {deptPreviewResult != null && deptAnalyzeResult == null && (
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
                    )}
                  </div>
                </ModuleCard>
              )}
          </section>

          {/* ── 2D NMR section ──────────────────────────────────────────── */}
          <section className="space-y-6">
            {/* Step 1 — Setup & Upload (2D NMR) */}
            <ModuleCard
              accent="teal"
              eyebrow="2D NMR · Step 1 · Setup"
              title="Configure & upload 2D peak table"
              icon={Network}
              description="Choose the 2D experiment type, set SMILES, and drop a peak table to compare correlations against the candidate structure."
              className="min-w-0"
            >
              <div className="space-y-5">
                {/* Experiment type pill toggle */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Experiment
                  </Label>
                  <div className="inline-flex flex-wrap rounded-lg border border-input bg-background p-0.5">
                    {[
                      { value: "HSQC", label: "HSQC" },
                      { value: "HMBC", label: "HMBC" },
                      { value: "COSY", label: "COSY" },
                      { value: "HMQC", label: "HMQC" },
                    ].map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setNmr2dExperiment(option.value)}
                        className={cn(
                          "rounded-md px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-wide transition-colors",
                          nmr2dExperiment === option.value
                            ? "shadow-sm"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                        style={
                          nmr2dExperiment === option.value
                            ? { backgroundColor: "var(--mt-teal)", color: "#04080F" }
                            : undefined
                        }
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* SMILES */}
                <div className="space-y-1.5">
                  <Label htmlFor="nmr2d-smiles" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    SMILES <span className="ml-1 text-[10px] font-normal text-[color:var(--mt-red)]/80">required</span>
                  </Label>
                  <Input
                    id="nmr2d-smiles"
                    value={nmr2dSmiles}
                    onChange={(e) => setNmr2dSmiles(e.target.value)}
                    placeholder="e.g. CCO"
                    className="font-mono"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 font-mono text-[11px]"
                    onClick={fillSmilesFromCandidates}
                  >
                    <Atom className="mr-1 h-3.5 w-3.5" aria-hidden />
                    Use first candidate SMILES
                  </Button>
                </div>

                {/* Drop-zone for 2D peak table */}
                <div className="space-y-1.5">
                  <Label htmlFor="nmr2d-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    2D peak table file
                  </Label>
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label="Drop 2D peak table or press Enter to browse"
                    onClick={() => nmr2dFileRef.current?.click()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        nmr2dFileRef.current?.click()
                      }
                    }}
                    onDragOver={(e) => {
                      e.preventDefault()
                      setNmr2dDragOver(true)
                    }}
                    onDragLeave={() => setNmr2dDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault()
                      setNmr2dDragOver(false)
                      const f = e.dataTransfer.files?.[0]
                      if (f) attachNmr2dFile(f)
                    }}
                    className={cn(
                      "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-7 text-center transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                      nmr2dDragOver
                        ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                        : nmr2dSelectedFileName
                        ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                        : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                    )}
                  >
                    <Upload
                      className="mb-2 h-6 w-6"
                      style={{ color: nmr2dDragOver || nmr2dSelectedFileName ? "var(--mt-teal)" : undefined }}
                      aria-hidden
                    />
                    <p className="font-mono text-sm font-bold tracking-tight">
                      {nmr2dSelectedFileName ? "File ready" : nmr2dDragOver ? "Drop to attach" : "Drop 2D peak table or click to browse"}
                    </p>
                    <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                      CSV · TSV · JSON
                    </p>
                  </div>
                  <input
                    id="nmr2d-file"
                    ref={nmr2dFileRef}
                    type="file"
                    accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                    className="sr-only"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) {
                        setNmr2dSelectedFile(f)
                        setNmr2dSelectedFileName(f.name)
                      } else {
                        setNmr2dSelectedFile(null)
                        setNmr2dSelectedFileName(null)
                      }
                    }}
                  />
                  {nmr2dSelectedFileName ? (
                    <div
                      className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                      style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                        <span className="truncate font-mono text-xs">{nmr2dSelectedFileName}</span>
                      </div>
                      <button
                        type="button"
                        onClick={clearNmr2dFile}
                        className="text-muted-foreground hover:text-foreground"
                        aria-label="Remove selected 2D file"
                      >
                        <X className="h-3.5 w-3.5" aria-hidden />
                      </button>
                    </div>
                  ) : null}
                </div>

                {/* Contour preview checkbox */}
                <div
                  className="flex items-center gap-2 rounded-md border px-3 py-2"
                  style={{ borderColor: "var(--border)" }}
                >
                  <Checkbox id="nmr2d-contour" checked={nmr2dContour} onCheckedChange={(v) => setNmr2dContour(v === true)} />
                  <Label htmlFor="nmr2d-contour" className="text-xs font-normal text-muted-foreground">
                    Include contour preview (if enabled server-side)
                  </Label>
                </div>

                {/* Advanced — optional DEPT file */}
                <Collapsible open={nmr2dAdvancedOpen} onOpenChange={setNmr2dAdvancedOpen}>
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
                    >
                      <span className="flex items-center gap-2">
                        <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                          Advanced — optional DEPT cross-link
                        </span>
                      </span>
                      <ChevronDown
                        className={cn("h-4 w-4 text-muted-foreground transition-transform", nmr2dAdvancedOpen && "rotate-180")}
                        aria-hidden
                      />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-4 pt-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="nmr2d-dept-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Optional DEPT/APT file
                      </Label>
                      <div
                        role="button"
                        tabIndex={0}
                        aria-label="Drop optional DEPT file for 2D analysis or press Enter to browse"
                        onClick={() => nmr2dDeptFileRef.current?.click()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            nmr2dDeptFileRef.current?.click()
                          }
                        }}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setNmr2dDeptDragOver(true)
                        }}
                        onDragLeave={() => setNmr2dDeptDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setNmr2dDeptDragOver(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) attachNmr2dDeptFile(f)
                        }}
                        className={cn(
                          "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-5 text-center transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                          nmr2dDeptDragOver
                            ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                            : nmr2dDeptSelectedFileName
                            ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                            : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                        )}
                      >
                        <Upload
                          className="mb-1 h-5 w-5"
                          style={{ color: nmr2dDeptDragOver || nmr2dDeptSelectedFileName ? "var(--mt-teal)" : undefined }}
                          aria-hidden
                        />
                        <p className="font-mono text-xs font-bold tracking-tight">
                          {nmr2dDeptSelectedFileName ? "DEPT file ready" : "Drop DEPT file (optional)"}
                        </p>
                      </div>
                      <input
                        id="nmr2d-dept-file"
                        ref={nmr2dDeptFileRef}
                        type="file"
                        accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                        className="sr-only"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) {
                            setNmr2dDeptSelectedFile(f)
                            setNmr2dDeptSelectedFileName(f.name)
                          } else {
                            setNmr2dDeptSelectedFile(null)
                            setNmr2dDeptSelectedFileName(null)
                          }
                        }}
                      />
                      {nmr2dDeptSelectedFileName ? (
                        <div
                          className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                          style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <FileText className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                            <span className="truncate font-mono text-[11px]">{nmr2dDeptSelectedFileName}</span>
                          </div>
                          <button
                            type="button"
                            onClick={clearNmr2dDeptFile}
                            className="text-muted-foreground hover:text-foreground"
                            aria-label="Remove DEPT file from 2D analysis"
                          >
                            <X className="h-3 w-3" aria-hidden />
                          </button>
                        </div>
                      ) : null}
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="nmr2d-dept-experiment" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        DEPT experiment type
                      </Label>
                      <Input
                        id="nmr2d-dept-experiment"
                        value={nmr2dDeptExperiment}
                        onChange={(e) => setNmr2dDeptExperiment(e.target.value)}
                        placeholder="e.g. DEPT135"
                        className="font-mono text-xs"
                      />
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            </ModuleCard>

            {/* Step 2 — Run (2D NMR) */}
            <ModuleCard
              accent="teal"
              eyebrow="2D NMR · Step 2 · Run"
              title="Analyze 2D correlations"
              icon={Zap}
              description="Submit the 2D peak table for HSQC / HMBC / COSY / HMQC correlation analysis against the SMILES candidate."
              className="min-w-0"
            >
              <div className="space-y-4">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      disabled={nmr2dLoading}
                      onClick={runNmr2dAnalyze}
                      className={cn(
                        "group relative flex w-full flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                        "hover:-translate-y-px hover:shadow-md",
                        nmr2dLoading
                          ? "cursor-wait opacity-70"
                          : "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]"
                      )}
                      style={{
                        borderTop: "3px solid var(--mt-teal)",
                        backgroundColor: "var(--mt-teal-soft)",
                      }}
                    >
                      <div className="flex w-full items-center justify-between">
                        <span
                          className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          <Sparkles className="h-3.5 w-3.5" aria-hidden />
                          Analyze
                        </span>
                        <span
                          className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          Recommended
                        </span>
                      </div>
                      <span className="font-mono text-base font-bold leading-tight">
                        {nmr2dLoading ? "Analyzing 2D NMR…" : "Run 2D correlation analysis"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Cross-check uploaded peak table against SMILES candidate using {nmr2dExperiment} predictions.
                      </span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                    POST /nmr2d/analyze
                  </TooltipContent>
                </Tooltip>

                {nmr2dError && <AlertCard variant="error" title="2D NMR analyze failed" description={nmr2dError} />}
              </div>
            </ModuleCard>

            {/* Step 3 — Results (2D NMR) */}
            {(nmr2dResult != null || nmr2dLoading) && (
              <ModuleCard
                accent="teal"
                eyebrow="2D NMR · Step 3 · Results"
                title="2D correlation output"
                icon={BarChart3}
                description={`Correlation evidence from /nmr2d/analyze (${nmr2dExperiment}).`}
                className="min-w-0"
              >
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
              </ModuleCard>
            )}
          </section>
        </TabsContent>

        <TabsContent value="tab-predicted" className="mt-4 space-y-16">
          {/* ── Section 1 · 1H / 13C evidence match ──────────────────────────────────── */}
          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Evidence Match
            </p>

            {/* Step 1 — Setup (uses shared session inputs only) */}
            <ModuleCard
              accent="teal"
              eyebrow="Predicted 1H/13C · Step 1 · Setup"
              title="Inputs from shared session"
              icon={Atom}
              description="This analyzer uses the candidate list, observed 1H / 13C text, sample ID, and solvent from the workspace header — no extra uploads required."
              className="min-w-0"
            >
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div
                    className="rounded-md border px-3 py-2"
                    style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                  >
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                      Candidates
                    </p>
                    <p className="mt-1 truncate font-mono text-xs">
                      {candidatesText.split("\n").filter((l) => l.trim()).length} candidate{candidatesText.split("\n").filter((l) => l.trim()).length === 1 ? "" : "s"} ready
                    </p>
                  </div>
                  <div
                    className="rounded-md border px-3 py-2"
                    style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                  >
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                      NMR text
                    </p>
                    <p className="mt-1 truncate font-mono text-xs">
                      {protonText.trim() ? "1H ✓" : "1H —"} · {carbonText.trim() ? "13C ✓" : "13C —"}
                    </p>
                  </div>
                  <div
                    className="rounded-md border px-3 py-2"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                      Sample ID
                    </p>
                    <p className="mt-1 truncate font-mono text-xs">{sampleId.trim() || "(empty)"}</p>
                  </div>
                  <div
                    className="rounded-md border px-3 py-2"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                      Solvent
                    </p>
                    <p className="mt-1 truncate font-mono text-xs">{solventForApi || "(unset)"}</p>
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Edit any of these in the shared session header above — changes apply to every Predicted analyzer.
                </p>
              </div>
            </ModuleCard>

            {/* Step 2 — Run */}
            <ModuleCard
              accent="teal"
              eyebrow="Predicted 1H/13C · Step 2 · Run"
              title="Match predicted vs observed"
              icon={Zap}
              description="Submit the candidate list with shared 1H / 13C text for predicted-spectrum matching against each structure."
              className="min-w-0"
            >
              <form onSubmit={runNmrEvidence} className="space-y-4">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="submit"
                      disabled={nmrLoading}
                      className={cn(
                        "group relative flex w-full flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                        "hover:-translate-y-px hover:shadow-md",
                        nmrLoading
                          ? "cursor-wait opacity-70"
                          : "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]"
                      )}
                      style={{
                        borderTop: "3px solid var(--mt-teal)",
                        backgroundColor: "var(--mt-teal-soft)",
                      }}
                    >
                      <div className="flex w-full items-center justify-between">
                        <span
                          className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          <Sparkles className="h-3.5 w-3.5" aria-hidden />
                          Match
                        </span>
                        <span
                          className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          Recommended
                        </span>
                      </div>
                      <span className="font-mono text-base font-bold leading-tight">
                        {nmrLoading ? "Matching predicted NMR…" : "Run 1H / 13C evidence match"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Match observed NMR chemical shifts against predicted spectra for each candidate structure.
                      </span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                    POST /prediction/nmr/match/evidence
                  </TooltipContent>
                </Tooltip>
                {nmrError && <AlertCard variant="error" title="Predicted NMR match failed" description={nmrError} />}
              </form>
            </ModuleCard>

            {/* Step 3 — Results */}
            {(nmrResult != null || nmrLoading) && (
              <ModuleCard
                accent="teal"
                eyebrow="Predicted 1H/13C · Step 3 · Results"
                title="1H / 13C match output"
                icon={BarChart3}
                description="Per-candidate evidence from /prediction/nmr/match/evidence."
                className="min-w-0"
              >
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
              </ModuleCard>
            )}
          </section>

          {/* ── Section 2 · Spectral similarity ───────────────────────────────────────── */}
          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Similarity
            </p>

            {/* Step 1 — Setup & Upload (Similarity) */}
            <ModuleCard
              accent="teal"
              eyebrow="Similarity · Step 1 · Setup"
              title="Configure references & 2D pairs"
              icon={Network}
              description="Observed spectra default from shared 1H / 13C text. Optionally add reference spectra or paired 2D files for richer scoring."
              className="min-w-0"
            >
              <div className="space-y-5">
                {/* Reference text inputs */}
                <div className="space-y-1.5">
                  <Label htmlFor="sim-ref-proton" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Reference 1H text <span className="ml-1 text-[10px] font-normal text-muted-foreground">optional</span>
                  </Label>
                  <Textarea
                    id="sim-ref-proton"
                    value={refProton}
                    onChange={(e) => setRefProton(e.target.value)}
                    rows={3}
                    placeholder="Leave empty to score observed-only layers."
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="sim-ref-carbon" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Reference 13C text <span className="ml-1 text-[10px] font-normal text-muted-foreground">optional</span>
                  </Label>
                  <Textarea
                    id="sim-ref-carbon"
                    value={refCarbon}
                    onChange={(e) => setRefCarbon(e.target.value)}
                    rows={3}
                    className="font-mono text-xs"
                  />
                </div>

                {/* Advanced — 2D pairs (collapsible) */}
                <Collapsible open={predictedAdvancedOpen} onOpenChange={setPredictedAdvancedOpen}>
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
                    >
                      <span className="flex items-center gap-2">
                        <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                          Advanced — paired 2D files
                        </span>
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-4 w-4 text-muted-foreground transition-transform",
                          predictedAdvancedOpen && "rotate-180"
                        )}
                        aria-hidden
                      />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-4 pt-4">
                    <p className="text-[11px] text-muted-foreground">
                      2D similarity needs both observed and reference uploads — leave both blank to skip 2D scoring.
                    </p>

                    {/* Observed 2D drop-zone */}
                    <div className="space-y-1.5">
                      <Label htmlFor="sim-obs2d-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Observed 2D file
                      </Label>
                      <div
                        role="button"
                        tabIndex={0}
                        aria-label="Drop observed 2D file or press Enter to browse"
                        onClick={() => obs2dRef.current?.click()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            obs2dRef.current?.click()
                          }
                        }}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setObs2dDragOver(true)
                        }}
                        onDragLeave={() => setObs2dDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setObs2dDragOver(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) {
                            const { attach } = makeAttachClear(obs2dRef, setObs2dSelectedFile, setObs2dSelectedFileName)
                            attach(f)
                          }
                        }}
                        className={cn(
                          "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-5 text-center transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                          obs2dDragOver
                            ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                            : obs2dSelectedFileName
                            ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                            : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                        )}
                      >
                        <Upload
                          className="mb-1 h-5 w-5"
                          style={{ color: obs2dDragOver || obs2dSelectedFileName ? "var(--mt-teal)" : undefined }}
                          aria-hidden
                        />
                        <p className="font-mono text-xs font-bold tracking-tight">
                          {obs2dSelectedFileName ? "Observed 2D ready" : "Drop observed 2D file"}
                        </p>
                      </div>
                      <input
                        id="sim-obs2d-file"
                        ref={obs2dRef}
                        type="file"
                        accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                        className="sr-only"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) {
                            setObs2dSelectedFile(f)
                            setObs2dSelectedFileName(f.name)
                          } else {
                            setObs2dSelectedFile(null)
                            setObs2dSelectedFileName(null)
                          }
                        }}
                      />
                      {obs2dSelectedFileName ? (
                        <div
                          className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                          style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <FileText className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                            <span className="truncate font-mono text-[11px]">{obs2dSelectedFileName}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              const { clear } = makeAttachClear(obs2dRef, setObs2dSelectedFile, setObs2dSelectedFileName)
                              clear()
                            }}
                            className="text-muted-foreground hover:text-foreground"
                            aria-label="Remove observed 2D file"
                          >
                            <X className="h-3 w-3" aria-hidden />
                          </button>
                        </div>
                      ) : null}
                    </div>

                    {/* Reference 2D drop-zone */}
                    <div className="space-y-1.5">
                      <Label htmlFor="sim-ref2d-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Reference 2D file
                      </Label>
                      <div
                        role="button"
                        tabIndex={0}
                        aria-label="Drop reference 2D file or press Enter to browse"
                        onClick={() => ref2dRef.current?.click()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            ref2dRef.current?.click()
                          }
                        }}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setRef2dDragOver(true)
                        }}
                        onDragLeave={() => setRef2dDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setRef2dDragOver(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) {
                            const { attach } = makeAttachClear(ref2dRef, setRef2dSelectedFile, setRef2dSelectedFileName)
                            attach(f)
                          }
                        }}
                        className={cn(
                          "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-5 text-center transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                          ref2dDragOver
                            ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                            : ref2dSelectedFileName
                            ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                            : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                        )}
                      >
                        <Upload
                          className="mb-1 h-5 w-5"
                          style={{ color: ref2dDragOver || ref2dSelectedFileName ? "var(--mt-teal)" : undefined }}
                          aria-hidden
                        />
                        <p className="font-mono text-xs font-bold tracking-tight">
                          {ref2dSelectedFileName ? "Reference 2D ready" : "Drop reference 2D file"}
                        </p>
                      </div>
                      <input
                        id="sim-ref2d-file"
                        ref={ref2dRef}
                        type="file"
                        accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                        className="sr-only"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) {
                            setRef2dSelectedFile(f)
                            setRef2dSelectedFileName(f.name)
                          } else {
                            setRef2dSelectedFile(null)
                            setRef2dSelectedFileName(null)
                          }
                        }}
                      />
                      {ref2dSelectedFileName ? (
                        <div
                          className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                          style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <FileText className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                            <span className="truncate font-mono text-[11px]">{ref2dSelectedFileName}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              const { clear } = makeAttachClear(ref2dRef, setRef2dSelectedFile, setRef2dSelectedFileName)
                              clear()
                            }}
                            className="text-muted-foreground hover:text-foreground"
                            aria-label="Remove reference 2D file"
                          >
                            <X className="h-3 w-3" aria-hidden />
                          </button>
                        </div>
                      ) : null}
                    </div>

                    {/* 2D experiment type */}
                    <div className="space-y-1.5">
                      <Label htmlFor="sim-experiment-type" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        2D experiment type
                      </Label>
                      <Input
                        id="sim-experiment-type"
                        value={simExperimentType}
                        onChange={(e) => setSimExperimentType(e.target.value)}
                        placeholder="HSQC"
                        className="font-mono text-xs"
                      />
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            </ModuleCard>

            {/* Step 2 — Run (Similarity) */}
            <ModuleCard
              accent="teal"
              eyebrow="Similarity · Step 2 · Run"
              title="Score spectral similarity"
              icon={Zap}
              description="Score observed against reference (text + optional 2D pairs). 2D layer requires both observed AND reference uploads."
              className="min-w-0"
            >
              <div className="space-y-4">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      disabled={simLoading}
                      onClick={runSimilarity}
                      className={cn(
                        "group relative flex w-full flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                        "hover:-translate-y-px hover:shadow-md",
                        simLoading
                          ? "cursor-wait opacity-70"
                          : "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]"
                      )}
                      style={{
                        borderTop: "3px solid var(--mt-teal)",
                        backgroundColor: "var(--mt-teal-soft)",
                      }}
                    >
                      <div className="flex w-full items-center justify-between">
                        <span
                          className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          <Sparkles className="h-3.5 w-3.5" aria-hidden />
                          Score
                        </span>
                        <span
                          className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          Recommended
                        </span>
                      </div>
                      <span className="font-mono text-base font-bold leading-tight">
                        {simLoading ? "Scoring similarity…" : "Score spectral similarity"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Combines 1H + 13C text (and 2D pairs if attached) into a single similarity score per layer.
                      </span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                    POST /similarity/score/evidence
                  </TooltipContent>
                </Tooltip>
                {simError && <AlertCard variant="error" title="Similarity scoring failed" description={simError} />}
              </div>
            </ModuleCard>

            {/* Step 3 — Results (Similarity) */}
            {(simResult != null || simLoading) && (
              <ModuleCard
                accent="teal"
                eyebrow="Similarity · Step 3 · Results"
                title="Similarity score output"
                icon={BarChart3}
                description="Per-layer similarity scores from /similarity/score/evidence."
                className="min-w-0"
              >
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
              </ModuleCard>
            )}
          </section>

          {/* ── Section 3 · Candidate compare ─────────────────────────────────────────── */}
          <section className="space-y-6">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Candidate Compare
            </p>

            {/* Step 1 — Setup & Upload (Compare) */}
            <ModuleCard
              accent="teal"
              eyebrow="Compare · Step 1 · Setup"
              title="Optional DEPT + 2D uploads"
              icon={Atom}
              description="Compare uses shared candidates and NMR text. Optionally attach DEPT/APT or 2D peak tables to layer in extra evidence channels."
              className="min-w-0"
            >
              <div className="space-y-5">
                <p
                  className="rounded-md border px-3 py-2 font-mono text-[11px]"
                  style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                >
                  <span className="font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    Tip:
                  </span>{" "}
                  No uploads needed for a baseline comparison — the analyzer already pulls from shared session inputs.
                </p>

                {/* Advanced — DEPT + 2D files */}
                <Collapsible open={compareAdvancedOpen} onOpenChange={setCompareAdvancedOpen}>
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
                    >
                      <span className="flex items-center gap-2">
                        <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                          Advanced — DEPT/APT + 2D peak table
                        </span>
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-4 w-4 text-muted-foreground transition-transform",
                          compareAdvancedOpen && "rotate-180"
                        )}
                        aria-hidden
                      />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-4 pt-4">
                    {/* DEPT/APT drop-zone */}
                    <div className="space-y-1.5">
                      <Label htmlFor="cand-dept" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Optional DEPT / APT file
                      </Label>
                      <div
                        role="button"
                        tabIndex={0}
                        aria-label="Drop DEPT/APT file for candidate compare or press Enter to browse"
                        onClick={() => candDeptRef.current?.click()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            candDeptRef.current?.click()
                          }
                        }}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setCandDeptDragOver(true)
                        }}
                        onDragLeave={() => setCandDeptDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setCandDeptDragOver(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) {
                            const { attach } = makeAttachClear(candDeptRef, setCandDeptSelectedFile, setCandDeptSelectedFileName)
                            attach(f)
                          }
                        }}
                        className={cn(
                          "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-5 text-center transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                          candDeptDragOver
                            ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                            : candDeptSelectedFileName
                            ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                            : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                        )}
                      >
                        <Upload
                          className="mb-1 h-5 w-5"
                          style={{ color: candDeptDragOver || candDeptSelectedFileName ? "var(--mt-teal)" : undefined }}
                          aria-hidden
                        />
                        <p className="font-mono text-xs font-bold tracking-tight">
                          {candDeptSelectedFileName ? "DEPT file ready" : "Drop DEPT / APT file (optional)"}
                        </p>
                      </div>
                      <input
                        id="cand-dept"
                        ref={candDeptRef}
                        type="file"
                        accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                        className="sr-only"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) {
                            setCandDeptSelectedFile(f)
                            setCandDeptSelectedFileName(f.name)
                          } else {
                            setCandDeptSelectedFile(null)
                            setCandDeptSelectedFileName(null)
                          }
                        }}
                      />
                      {candDeptSelectedFileName ? (
                        <div
                          className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                          style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <FileText className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                            <span className="truncate font-mono text-[11px]">{candDeptSelectedFileName}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              const { clear } = makeAttachClear(candDeptRef, setCandDeptSelectedFile, setCandDeptSelectedFileName)
                              clear()
                            }}
                            className="text-muted-foreground hover:text-foreground"
                            aria-label="Remove DEPT file from candidate compare"
                          >
                            <X className="h-3 w-3" aria-hidden />
                          </button>
                        </div>
                      ) : null}
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="cand-dept-experiment" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        DEPT experiment type
                      </Label>
                      <Input
                        id="cand-dept-experiment"
                        value={candDeptExperiment}
                        onChange={(e) => setCandDeptExperiment(e.target.value)}
                        placeholder="e.g. DEPT135"
                        className="font-mono text-xs"
                      />
                    </div>

                    {/* 2D peak table drop-zone */}
                    <div className="space-y-1.5">
                      <Label htmlFor="cand-nmr2d" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Optional 2D peak table
                      </Label>
                      <div
                        role="button"
                        tabIndex={0}
                        aria-label="Drop 2D peak table for candidate compare or press Enter to browse"
                        onClick={() => candNmr2dRef.current?.click()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            candNmr2dRef.current?.click()
                          }
                        }}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setCandNmr2dDragOver(true)
                        }}
                        onDragLeave={() => setCandNmr2dDragOver(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setCandNmr2dDragOver(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) {
                            const { attach } = makeAttachClear(candNmr2dRef, setCandNmr2dSelectedFile, setCandNmr2dSelectedFileName)
                            attach(f)
                          }
                        }}
                        className={cn(
                          "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-5 text-center transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                          candNmr2dDragOver
                            ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                            : candNmr2dSelectedFileName
                            ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                            : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
                        )}
                      >
                        <Upload
                          className="mb-1 h-5 w-5"
                          style={{ color: candNmr2dDragOver || candNmr2dSelectedFileName ? "var(--mt-teal)" : undefined }}
                          aria-hidden
                        />
                        <p className="font-mono text-xs font-bold tracking-tight">
                          {candNmr2dSelectedFileName ? "2D peak table ready" : "Drop 2D peak table (optional)"}
                        </p>
                      </div>
                      <input
                        id="cand-nmr2d"
                        ref={candNmr2dRef}
                        type="file"
                        accept={SPECTRACHECK_TEXT_SPECTRUM_ACCEPT}
                        className="sr-only"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) {
                            setCandNmr2dSelectedFile(f)
                            setCandNmr2dSelectedFileName(f.name)
                          } else {
                            setCandNmr2dSelectedFile(null)
                            setCandNmr2dSelectedFileName(null)
                          }
                        }}
                      />
                      {candNmr2dSelectedFileName ? (
                        <div
                          className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                          style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                        >
                          <div className="flex min-w-0 items-center gap-2">
                            <FileText className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                            <span className="truncate font-mono text-[11px]">{candNmr2dSelectedFileName}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              const { clear } = makeAttachClear(candNmr2dRef, setCandNmr2dSelectedFile, setCandNmr2dSelectedFileName)
                              clear()
                            }}
                            className="text-muted-foreground hover:text-foreground"
                            aria-label="Remove 2D peak table from candidate compare"
                          >
                            <X className="h-3 w-3" aria-hidden />
                          </button>
                        </div>
                      ) : null}
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="cand-nmr2d-experiment" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        2D experiment type
                      </Label>
                      <Input
                        id="cand-nmr2d-experiment"
                        value={candNmr2dExperiment}
                        onChange={(e) => setCandNmr2dExperiment(e.target.value)}
                        placeholder="HSQC"
                        className="font-mono text-xs"
                      />
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            </ModuleCard>

            {/* Step 2 — Run (Compare) */}
            <ModuleCard
              accent="teal"
              eyebrow="Compare · Step 2 · Run"
              title="Compare candidates with full evidence"
              icon={Zap}
              description="Compare each candidate structure against shared NMR text and any optional DEPT/2D channels you attached."
              className="min-w-0"
            >
              <div className="space-y-4">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      disabled={candLoading}
                      onClick={runCandidateCompare}
                      className={cn(
                        "group relative flex w-full flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                        "hover:-translate-y-px hover:shadow-md",
                        candLoading
                          ? "cursor-wait opacity-70"
                          : "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]"
                      )}
                      style={{
                        borderTop: "3px solid var(--mt-teal)",
                        backgroundColor: "var(--mt-teal-soft)",
                      }}
                    >
                      <div className="flex w-full items-center justify-between">
                        <span
                          className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          <Sparkles className="h-3.5 w-3.5" aria-hidden />
                          Compare
                        </span>
                        <span
                          className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          Recommended
                        </span>
                      </div>
                      <span className="font-mono text-base font-bold leading-tight">
                        {candLoading ? "Comparing candidates…" : "Compare candidates (evidence)"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Per-candidate predicted-vs-observed delta with optional DEPT and 2D layers folded in.
                      </span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                    POST /candidates/compare/evidence
                  </TooltipContent>
                </Tooltip>
                {candError && <AlertCard variant="error" title="Candidate compare failed" description={candError} />}
              </div>
            </ModuleCard>

            {/* Step 3 — Results (Compare) */}
            {(candResult != null || candLoading) && (
              <ModuleCard
                accent="teal"
                eyebrow="Compare · Step 3 · Results"
                title="Candidate compare output"
                icon={BarChart3}
                description="Per-candidate evidence from /candidates/compare/evidence."
                className="min-w-0"
              >
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
              </ModuleCard>
            )}
          </section>
        </TabsContent>

        <TabsContent value="tab-ms-evidence" className="mt-4">
          <SpectraCheckMsEvidenceStudio sampleId={sampleId} candidatesText={candidatesText} />
        </TabsContent>

        <TabsContent value="tab-evidence-queue" className="mt-4 space-y-8">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Review Queue
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">AI Evidence Queue</h2>
            <p className="text-sm text-muted-foreground">
              Triage queued spectral evidence, resolve contradictions, and promote items to the Unified Evidence build.
            </p>
          </div>
          <SpectraCheckEvidenceQueuePanel
            sessionId={backendSessionId}
            onSendToUnified={() => setActiveTab("tab-unified")}
          />
        </TabsContent>

        <TabsContent value="tab-unified" className="mt-4 space-y-12">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Unified Evidence
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Cross-modal evidence build</h2>
              <p className="text-sm text-muted-foreground">
                Combine queued evidence across NMR, MS, and predicted layers into a single unified confidence package.
              </p>
            </div>
            <FeedbackButton module="unified_evidence" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
          </div>

          {/* Regulatory impact */}
          <section className="space-y-3">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Unified · Regulatory impact
            </p>
            <SpectraCheckRegulatoryImpactCard sessionId={backendSessionId} evidenceItemIds={regulatoryEvidenceItemIds} />
          </section>

          {/* Evidence queue summary */}
          <section className="space-y-3">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Unified · Queue summary
            </p>
            <SpectraCheckEvidenceQueueUnifiedSummary />
          </section>

          {/* Confidence suite (unified-only) */}
          <section className="space-y-3">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Unified · Confidence build
            </p>
            <SpectraCheckConfidenceSuite
              embedMode="unified-only"
              sampleId={sampleId}
              solvent={solventForApi}
              candidatesText={candidatesText}
              protonText={protonText}
              carbonText={carbonText}
              backendSessionId={backendSessionId}
            />
          </section>

          {/* Review collaboration */}
          <section className="space-y-3">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Unified · Review & collaboration
            </p>
            <SpectraCheckReviewCollaborationPanel sessionId={backendSessionId} />
          </section>
        </TabsContent>

        <TabsContent value="tab-report" className="mt-4 space-y-12">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Spectroscopy · Report
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Reviewer-ready report</h2>
              <p className="text-sm text-muted-foreground">
                Generate, preview, and finalize the SpectraCheck report — ready for downstream review and sign-off.
              </p>
            </div>
            <FeedbackButton module="report" projectId={feedbackProjectId} sessionId={feedbackSessionId} />
          </div>

          {/* Confidence suite (report-only) */}
          <section className="space-y-3">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Report · Build & preview
            </p>
            <SpectraCheckConfidenceSuite
              embedMode="report-only"
              sampleId={sampleId}
              solvent={solventForApi}
              candidatesText={candidatesText}
              protonText={protonText}
              carbonText={carbonText}
              backendSessionId={backendSessionId}
            />
          </section>

          {/* Review collaboration */}
          <section className="space-y-3">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Report · Review & collaboration
            </p>
            <SpectraCheckReviewCollaborationPanel sessionId={backendSessionId} />
          </section>
        </TabsContent>

        <TabsContent value="tab-dev-json" className="mt-4 space-y-8">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Spectroscopy · Developer JSON
            </p>
            <h2 className="inline-flex items-center gap-2 font-mono text-xl font-bold tracking-tight">
              JSON snapshot hub
              <InfoTooltip
                content="Use this for debugging backend response shape, warnings, and raw evidence data."
                label="About Developer JSON hub"
              />
            </h2>
            <p className="text-sm text-muted-foreground">
              Latest payloads from this browser session — including upload previews. Use to verify response shape, warnings, and raw evidence.
            </p>
          </div>

          {/* Snapshot index chips */}
          {(() => {
            const snapshots: { key: string; label: string; available: boolean }[] = [
              { key: "nmr", label: "1H / 13C evidence", available: nmrResult != null },
              { key: "deptPreview", label: "DEPT preview", available: deptPreviewResult != null },
              { key: "deptAnalyze", label: "DEPT analyze", available: deptAnalyzeResult != null },
              { key: "nmr2d", label: "2D NMR", available: nmr2dResult != null },
              { key: "sim", label: "Similarity", available: simResult != null },
              { key: "cand", label: "Candidates compare", available: candResult != null },
              ...Object.keys(devSnapshots).map((k) => ({ key: k, label: k, available: true })),
            ]
            const availableCount = snapshots.filter((s) => s.available).length
            return (
              <ModuleCard
                accent="teal"
                eyebrow="Dev JSON · Step 1 · Index"
                title="Snapshot index"
                icon={Eye}
                description={`${availableCount} of ${snapshots.length} snapshots populated this session.`}
                className="min-w-0"
              >
                <div className="flex flex-wrap gap-2">
                  {snapshots.map((s) => (
                    <span
                      key={s.key}
                      className="rounded-md border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                      style={
                        s.available
                          ? { borderColor: "var(--mt-teal)", color: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }
                          : { borderColor: "var(--border)", color: "var(--muted-foreground)" }
                      }
                    >
                      {s.label} {s.available ? "✓" : "—"}
                    </span>
                  ))}
                </div>
              </ModuleCard>
            )
          })()}

          {/* Snapshot bodies */}
          <ModuleCard
            accent="teal"
            eyebrow="Dev JSON · Step 2 · Payloads"
            title="Raw response payloads"
            icon={FileText}
            description="Each panel below contains a single endpoint's most recent response."
            className="min-w-0"
          >
            <div className="space-y-6">
              {nmrResult != null && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    1H / 13C evidence
                  </p>
                  <DeveloperJsonPanel data={nmrResult} />
                </div>
              )}
              {deptPreviewResult != null && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    DEPT preview
                  </p>
                  <DeveloperJsonPanel data={deptPreviewResult} />
                </div>
              )}
              {deptAnalyzeResult != null && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    DEPT analyze
                  </p>
                  <DeveloperJsonPanel data={deptAnalyzeResult} />
                </div>
              )}
              {nmr2dResult != null && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    2D NMR
                  </p>
                  <DeveloperJsonPanel data={nmr2dResult} />
                </div>
              )}
              {simResult != null && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    Similarity
                  </p>
                  <DeveloperJsonPanel data={simResult} />
                </div>
              )}
              {candResult != null && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    Candidates compare
                  </p>
                  <DeveloperJsonPanel data={candResult} />
                </div>
              )}
              {Object.entries(devSnapshots).map(([k, v]) => (
                <div key={k} className="space-y-2">
                  <p className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
                    {k}
                  </p>
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
                  <div
                    className="rounded-md border-2 border-dashed px-4 py-6 text-center"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <p className="font-mono text-sm font-bold tracking-tight">No snapshots yet</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Run an action in any tab — the response will appear here for inspection.
                    </p>
                  </div>
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
