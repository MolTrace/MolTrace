"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useOptionalSpectraCheckWorkspaceSession } from "@/components/spectracheck/spectracheck-workspace-session-context"
import {
  useRawFidTabState,
  useSpectraCheckTabLink,
} from "@/components/spectracheck/spectracheck-tab-state-context"
import { apiFetch } from "@/lib/api/client"
import { trackFileUploaded } from "@/src/lib/analytics/analytics-client"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { buildAnalysisJobPayload } from "@/src/lib/spectracheck/buildAnalysisJobPayload"
import {
  COMPOUND_CLASS_UNSPECIFIED,
  compoundClassForRequest,
  type CompoundClassValue,
} from "@/src/lib/spectracheck/compound-classes"
import type { SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { normalizeSessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { SPECTRACHECK_RAW_FID_ACCEPT, isRawFidArchiveFilename } from "@/src/lib/spectracheck/spectrum-file-formats"
import { useAnalysisJob } from "@/src/lib/spectracheck/useAnalysisJob"
import { SpectrumViewer } from "@/components/science/SpectrumViewer"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import {
  EnrichedPickedPeaksPanel,
  InferredNmrTextPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"
import {
  MetadataKeyValueCard,
  ProcessingParametersCard,
} from "@/components/spectracheck/spectracheck-processing-parameters-card"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { SpectrumResultsFullscreen } from "@/components/spectracheck/spectracheck-fullscreen-results"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  extractPeaksFromPayload,
  extractSpectrumXY,
  isRecord,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { useStableXY } from "@/components/spectracheck/use-stable-xy"
import { isMissingNmrEndpoint, RAW_FID_BACKEND_MSG } from "@/components/spectracheck/spectracheck-nmr-endpoint-messages"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Card, CardContent } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  DetectionResultsPanel,
  GsdAnalysisControls,
  GsdResultsPanel,
  adaptLegacyRawFidResult,
  type AnalysisBackendChoice,
  type GSDLevel,
  type NMRRawFIDPreviewResponse,
  type SpectrumGSDAnalyzeRequest,
  type SpectrumGSDAnalyzeResult,
} from "@/components/spectracheck/gsd-analysis-ui"
import { GsdMultipletPanel } from "@/components/spectracheck/gsd-multiplet-panel"
import { GsdJCouplingPanel } from "@/components/spectracheck/gsd-jcoupling-panel"
import { GsdIntegrationPanel } from "@/components/spectracheck/gsd-integration-panel"
import { ShiftPredictionPanel } from "@/components/spectracheck/shift-prediction-panel"
import { SpectrumRetrievePanel } from "@/components/spectracheck/spectrum-retrieve-panel"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
// Textarea import removed: processing-parameters + acquisition-metadata
// cards now use ProcessingParametersCard / MetadataKeyValueCard.
import { cn } from "@/lib/utils"
import {
  Activity,
  AlertTriangle,
  Archive,
  BarChart3,
  ChevronDown,
  Eye,
  FileText,
  FlaskConical,
  Hash,
  Lock,
  Maximize2,
  PlayCircle,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  Waves,
  X,
  Zap,
} from "lucide-react"

type Props = {
  sampleId: string
  onSampleIdChange: (value: string) => void
  solvent: string
  /**
   * Compound-class hint from the shared session. Forwarded to every preview /
   * process request as ``compound_class`` so backend processing & downstream
   * candidate scoring can apply class-specific priors.
   */
  compoundClass?: CompoundClassValue
  /**
   * Shared session-card values from the NMR text + candidates tab. Forwarded
   * to ``/nmr/raw-fid/process`` so the backend can:
   *   - Parse the first SMILES from ``candidatesText`` → enrich picked peaks
   *     with category/region/labile_hint/impurity_match (same as the
   *     Processed 1H/13C analyze pipeline).
   *   - Mark whether 1H / 13C reference texts were supplied (audit trail).
   * Default to empty strings so existing call sites that don't pass them
   * still work and the FormData simply omits the param.
   */
  candidatesText?: string
  protonText?: string
  carbonText?: string
  registerDev?: (key: string, value: unknown) => void
}

const PRESETS = [
  { value: "safe_automatic", label: "Safe automatic" },
  { value: "imported_parameters", label: "Imported parameters" },
  { value: "no_baseline_correction", label: "No baseline correction" },
  { value: "no_phase_correction", label: "No phase correction" },
] as const

const EMPTY_SPECTRUM_PEAKS: never[] = []

type PromptSidecarConsistencySummary = {
  status: string
  message: string | null
  activePeakCount: number | null
  activePeakSource: string | null
  recommendedPeakCount: number | null
  recommendedPeakCountSource: string | null
  peakCountDelta: number | null
  acceptanceTolerance: number | null
  withinPromptAcceptance: boolean | null
  usedForPlot: boolean
  usedForPeakMarkers: boolean
  usedForPhaseOrBaseline: boolean
}

type PromptSidecarQaSummary = {
  consistency: PromptSidecarConsistencySummary | null
  role: string | null
  available: boolean | null
  active: boolean | null
  activeVisiblePipeline: string | null
  promptPipelineActive: boolean | null
  safeToActivate: boolean | null
  safeToUseForAnalysisMetadata: boolean | null
  readerDiagnosticsAvailable: boolean
  preprocessDiagnosticsAvailable: boolean
  readerSource: string | null
  preprocessSource: string | null
  nucleus: string | null
  solvent: string | null
  fieldMhz: number | null
  pointCount: number | null
  runtimeMs: number | null
  fingerprintHash: string | null
  phaseMethod: string | null
  phaseZeroOrderDegrees: number | null
  baselineMethod: string | null
  baselineOrder: number | null
  baselineRmseFractionFullScale: number | null
  validationStatus: string | null
  validationVersion: string | null
}

function readFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function readStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function readBooleanValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null
}

function firstRecordValue(...values: unknown[]): Record<string, unknown> | null {
  for (const value of values) {
    if (isRecord(value)) return value
  }
  return null
}

function firstStringValue(...values: unknown[]): string | null {
  for (const value of values) {
    const parsed = readStringValue(value)
    if (parsed) return parsed
  }
  return null
}

function firstNumberValue(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = readFiniteNumber(value)
    if (parsed != null) return parsed
  }
  return null
}

function firstBooleanValue(...values: unknown[]): boolean | null {
  for (const value of values) {
    const parsed = readBooleanValue(value)
    if (parsed != null) return parsed
  }
  return null
}

function rawFidGuidanceRecord(metadata: Record<string, unknown>): Record<string, unknown> | null {
  return firstRecordValue(metadata.raw_fid_peak_guidance, metadata.context_guidance)
}

function getPromptSidecarConsistency(payload: unknown): PromptSidecarConsistencySummary | null {
  if (!isRecord(payload) || !isRecord(payload.metadata)) return null
  const metadata = payload.metadata
  const rawGuidance = rawFidGuidanceRecord(metadata)
  const consistency =
    rawGuidance && isRecord(rawGuidance.prompt_sidecar_consistency)
      ? rawGuidance.prompt_sidecar_consistency
      : null

  if (!consistency) return null

  return {
    status: readStringValue(consistency.status) ?? "review",
    message: readStringValue(consistency.message),
    activePeakCount: readFiniteNumber(consistency.active_peak_count),
    activePeakSource: readStringValue(consistency.active_peak_source),
    recommendedPeakCount: readFiniteNumber(consistency.recommended_peak_count),
    recommendedPeakCountSource: readStringValue(consistency.recommended_peak_count_source),
    peakCountDelta: readFiniteNumber(consistency.peak_count_delta),
    acceptanceTolerance: readFiniteNumber(consistency.acceptance_tolerance),
    withinPromptAcceptance: readBooleanValue(consistency.within_prompt_acceptance),
    usedForPlot: readBooleanValue(consistency.used_for_plot) ?? false,
    usedForPeakMarkers: readBooleanValue(consistency.used_for_peak_markers) ?? false,
    usedForPhaseOrBaseline: readBooleanValue(consistency.used_for_phase_or_baseline) ?? false,
  }
}

function getPromptSidecarQa(payload: unknown): PromptSidecarQaSummary | null {
  if (!isRecord(payload) || !isRecord(payload.metadata)) return null
  const metadata = payload.metadata
  const sidecar = firstRecordValue(metadata.prompt_pipeline_sidecar)
  const rawGuidance = rawFidGuidanceRecord(metadata)
  const guidance = firstRecordValue(
    sidecar?.analysis_guidance,
    rawGuidance?.prompt_sidecar_guidance,
  )
  const validation = firstRecordValue(sidecar?.validation_report)
  const reader = firstRecordValue(sidecar?.reader_diagnostics)
  const preprocess = firstRecordValue(sidecar?.preprocess_diagnostics)
  const phase = firstRecordValue(sidecar?.phase)
  const baseline = firstRecordValue(sidecar?.baseline)
  const consistency = getPromptSidecarConsistency(payload)

  if (!sidecar && !guidance && !validation && !consistency) return null

  return {
    consistency,
    role: firstStringValue(sidecar?.role),
    available: firstBooleanValue(sidecar?.available),
    active: firstBooleanValue(sidecar?.active),
    activeVisiblePipeline: firstStringValue(
      guidance?.active_visible_pipeline,
      validation?.active_visible_pipeline,
      reader?.active_visible_pipeline,
      preprocess?.active_visible_pipeline,
    ),
    promptPipelineActive: firstBooleanValue(
      guidance?.prompt_pipeline_active,
      validation?.prompt_pipeline_active,
      reader?.prompt_pipeline_active,
      preprocess?.prompt_pipeline_active,
      sidecar?.active,
    ),
    safeToActivate: firstBooleanValue(validation?.safe_to_activate),
    safeToUseForAnalysisMetadata: firstBooleanValue(guidance?.safe_to_use_for_analysis_metadata),
    readerDiagnosticsAvailable:
      Boolean(reader) || firstBooleanValue(guidance?.reader_diagnostics_available) === true,
    preprocessDiagnosticsAvailable:
      Boolean(preprocess) || firstBooleanValue(guidance?.preprocess_diagnostics_available) === true,
    readerSource: firstStringValue(reader?.source),
    preprocessSource: firstStringValue(preprocess?.source),
    nucleus: firstStringValue(guidance?.nucleus, sidecar?.nucleus, reader?.nucleus),
    solvent: firstStringValue(guidance?.solvent, sidecar?.solvent, reader?.solvent),
    fieldMhz: firstNumberValue(guidance?.field_mhz, sidecar?.field_mhz, reader?.field_mhz),
    pointCount: firstNumberValue(guidance?.point_count, sidecar?.point_count, reader?.point_count),
    runtimeMs: firstNumberValue(guidance?.prompt_runtime_ms, sidecar?.runtime_ms),
    fingerprintHash: firstStringValue(guidance?.fingerprint_hash, sidecar?.fingerprint_hash, reader?.fingerprint_hash),
    phaseMethod: firstStringValue(preprocess?.phase_method, phase?.method),
    phaseZeroOrderDegrees: firstNumberValue(preprocess?.phase_zero_order_degrees),
    baselineMethod: firstStringValue(preprocess?.baseline_method, sidecar?.baseline_method, baseline?.method),
    baselineOrder: firstNumberValue(preprocess?.baseline_order, sidecar?.baseline_order, baseline?.order),
    baselineRmseFractionFullScale: firstNumberValue(preprocess?.baseline_rmse_fraction_full_scale),
    validationStatus: firstStringValue(validation?.status, guidance?.validation_status),
    validationVersion: firstStringValue(validation?.version, guidance?.validation_version),
  }
}

function humanizePromptSidecarStatus(status: string): string {
  const labels: Record<string, string> = {
    consistent: "Consistent",
    review_peak_count_delta: "Review peak-count delta",
    prompt_guidance_unavailable: "Prompt guidance unavailable",
    active_peak_count_unavailable: "Active peak count unavailable",
    review: "Review",
  }
  return labels[status] ?? status.replaceAll("_", " ")
}

function formatPromptSidecarNumber(value: number | null): string {
  return value == null ? "—" : Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatPromptSidecarRuntime(value: number | null): string {
  return value == null ? "—" : `${Math.max(0, value).toFixed(0)} ms`
}

function formatPromptSidecarPercent(value: number | null): string {
  return value == null ? "—" : `${(value * 100).toFixed(3)}%`
}

function shortPromptSidecarHash(value: string | null): string {
  if (!value) return "—"
  return value.length > 14 ? `${value.slice(0, 10)}…${value.slice(-4)}` : value
}

function extractRawArchiveId(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  const meta = isRecord(payload.metadata) ? payload.metadata : null
  const candidates = [
    payload.raw_archive_id,
    meta?.raw_archive_id,
    payload.raw_sha256,
    payload.sha256,
    meta?.sha256,
  ]
  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return null
}

export function SpectraCheckRawFidSection({
  sampleId,
  onSampleIdChange,
  solvent,
  compoundClass = COMPOUND_CLASS_UNSPECIFIED,
  candidatesText = "",
  protonText = "",
  carbonText = "",
  registerDev,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const { state, update } = useRawFidTabState()
  const {
    nucleus,
    vendor,
    preset,
    previewResult,
    processResult,
    previewError,
    processError,
    previewLoading,
    processLoading,
    previewSpectrum,
    previewSpectrumLoading,
    previewSpectrumError,
    activeResultMode,
    sessionRawFileIdChoice,
    jobActionError,
    selectedFile,
    selectedFileName,
    advancedOpen,
  } = state

  // Setter shims keep the rest of the JSX/handler code untouched while the
  // underlying state lives in workspace-level context (survives tab unmount).
  const setNucleus = useCallback((v: "1H" | "13C") => update({ nucleus: v }), [update])
  const setVendor = useCallback((v: string) => update({ vendor: v as typeof state.vendor }), [update, state.vendor])
  const setPreset = useCallback(
    (v: (typeof PRESETS)[number]["value"]) => update({ preset: v }),
    [update],
  )
  const setPreviewResult = useCallback((v: unknown) => update({ previewResult: v }), [update])
  const setProcessResult = useCallback((v: unknown) => update({ processResult: v }), [update])
  const setPreviewError = useCallback((v: string) => update({ previewError: v }), [update])
  const setProcessError = useCallback((v: string) => update({ processError: v }), [update])
  const setPreviewLoading = useCallback((v: boolean) => update({ previewLoading: v }), [update])
  const setProcessLoading = useCallback((v: boolean) => update({ processLoading: v }), [update])
  const setSessionRawFileIdChoice = useCallback(
    (v: string) => update({ sessionRawFileIdChoice: v }),
    [update],
  )
  const setJobActionError = useCallback((v: string) => update({ jobActionError: v }), [update])
  const setSelectedFile = useCallback((v: File | null) => update({ selectedFile: v }), [update])
  const setSelectedFileName = useCallback(
    (v: string | null) => update({ selectedFileName: v }),
    [update],
  )
  const setAdvancedOpen = useCallback((v: boolean) => update({ advancedOpen: v }), [update])

  // ── GSD-Prompt-3 (experimental, opt-in) — additive only. Default must
  // stay `legacy` so tenants who never touch the selector keep the
  // existing /nmr/raw-fid/process pipeline unchanged.
  const [analysisBackend, setAnalysisBackend] = useState<AnalysisBackendChoice>("legacy")
  const [gsdLevel, setGsdLevel] = useState<GSDLevel>(2)
  const [gsdResult, setGsdResult] = useState<SpectrumGSDAnalyzeResult | null>(null)
  const [gsdError, setGsdError] = useState("")
  const [gsdLoading, setGsdLoading] = useState(false)
  // GSD-scoped solvent override, initialized from the session-level
  // solvent prop. Canonicalized against the catalog when it arrives.
  const [gsdSolvent, setGsdSolvent] = useState(solvent)

  const ws = useOptionalSpectraCheckWorkspaceSession()
  const analysisJob = useAnalysisJob()
  const sendTabLink = useSpectraCheckTabLink()

  // dragOver is purely ephemeral visual state — fine to reset on remount.
  const [dragOver, setDragOver] = useState(false)
  // Local state for the collapsible "Processing parameters" panel at the
  // bottom of the results. Reference data the reviewer only opens when they
  // need to audit the FID processing knobs, so the default is closed.
  const [processingParamsOpen, setProcessingParamsOpen] = useState(false)
  // Opt-in, default-closed: opens the in-app full-screen spectrum + tables view.
  // Closed by default so the inline view and all existing behavior are untouched.
  const [rawFullscreenOpen, setRawFullscreenOpen] = useState(false)

  // Re-attach the persisted File to the (possibly remounted) <input> via DataTransfer
  // so existing fileRef.current?.files?.[0] callsites continue to work after tab switches.
  useEffect(() => {
    if (!selectedFile) return
    if (!fileRef.current || typeof DataTransfer === "undefined") return
    if (fileRef.current.files && fileRef.current.files[0] === selectedFile) return
    try {
      const dt = new DataTransfer()
      dt.items.add(selectedFile)
      fileRef.current.files = dt.files
    } catch {
      // Test environments may forbid assigning FileList.
    }
  }, [selectedFile])

  function attachFile(file: File) {
    setSelectedFile(file)
    setSelectedFileName(file.name)

    if (fileRef.current && typeof DataTransfer !== "undefined") {
      try {
        const dt = new DataTransfer()
        dt.items.add(file)
        fileRef.current.files = dt.files
      } catch {
        // Some browsers/test environments do not allow assigning FileList.
      }
    }
  }

  function getSelectedFile() {
    return fileRef.current?.files?.[0] ?? selectedFile
  }

  function clearSelectedFile() {
    if (fileRef.current) fileRef.current.value = ""
    setSelectedFile(null)
    setSelectedFileName(null)
  }

  const pushDev = useCallback(
    (key: string, value: unknown) => {
      registerDev?.(key, value)
    },
    [registerDev]
  )

  const rawSessionFileOptions = (ws?.sessionFiles ?? []).filter(
    (f: SessionFileRecord) =>
      (f.file_kind === "raw_fid" || f.file_kind === "spectrum_archive") && isRawFidArchiveFilename(f.filename),
  )

  async function ensureRawFidInputFileId(): Promise<string | null> {
    if (sessionRawFileIdChoice.trim()) return sessionRawFileIdChoice.trim()
    const file = getSelectedFile()
    if (!file) return null
    const fd = new FormData()
    fd.append("file", file)
    fd.append("file_kind", "raw_fid")
    const data = await apiFetch<unknown>("/files/upload", { method: "POST", body: fd })
    const rec = normalizeSessionFileRecord(data)
    trackFileUploaded({
      session_id: ws?.backendSessionId ?? undefined,
      metadata: {
        file_kind: "raw_fid",
        file_size_bytes: file.size,
        has_sha256: Boolean(rec?.sha256),
      },
    })
    await ws?.refreshSessionFiles()
    return rec?.file_id ?? null
  }

  async function startRawPreviewJob() {
    setJobActionError("")
    try {
      const fid = await ensureRawFidInputFileId()
      if (!fid) {
        setJobActionError("Choose a session raw FID archive or pick a local archive.")
        return
      }
      const ccParam = compoundClassForRequest(compoundClass)
      const jid = await analysisJob.createJob(
        buildAnalysisJobPayload({
          sessionId: ws?.backendSessionId ?? null,
          sampleId,
          jobType: "nmr_raw_fid_preview",
          inputFileIds: [fid],
          parameters: {
            solvent,
            nucleus,
            vendor,
            ...(ccParam ? { compound_class: ccParam } : {}),
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (err) {
      setJobActionError(formatApiError(err, "Could not start raw FID preview job"))
    }
  }

  async function startRawProcessJob() {
    setJobActionError("")
    try {
      const fid = await ensureRawFidInputFileId()
      if (!fid) {
        setJobActionError("Choose a session raw FID archive or pick a local archive.")
        return
      }
      const ccParam = compoundClassForRequest(compoundClass)
      const cand = candidatesText.trim()
      const sharedProton = protonText.trim()
      const sharedCarbon = carbonText.trim()
      const jid = await analysisJob.createJob(
        buildAnalysisJobPayload({
          sessionId: ws?.backendSessionId ?? null,
          sampleId,
          jobType: "nmr_raw_fid_process",
          inputFileIds: [fid],
          parameters: {
            solvent,
            nucleus,
            vendor,
            processing_preset: preset,
            preserve_raw: true,
            ...(ccParam ? { compound_class: ccParam } : {}),
            ...(cand ? { candidates_text: cand } : {}),
            ...(sharedProton ? { proton_nmr_text: sharedProton } : {}),
            ...(sharedCarbon ? { carbon13_text: sharedCarbon } : {}),
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (err) {
      setJobActionError(formatApiError(err, "Could not start raw FID process job"))
    }
  }

  function appendSharedSessionGuidance(fd: FormData) {
    const ccParam = compoundClassForRequest(compoundClass)
    if (ccParam) fd.append("compound_class", ccParam)
    // Shared session inputs — drives peak enrichment + evidence panels on
    // the response (parity with /nmr/processed/analyze).
    const cand = candidatesText.trim()
    if (cand) fd.append("candidates_text", cand)
    const sharedProton = protonText.trim()
    if (sharedProton) fd.append("proton_nmr_text", sharedProton)
    const sharedCarbon = carbonText.trim()
    if (sharedCarbon) fd.append("carbon13_text", sharedCarbon)
  }

  function buildFormData(file: File, withProcess: boolean) {
    const fd = new FormData()
    fd.append("file", file)
    fd.append("sample_id", sampleId)
    fd.append("solvent", solvent)
    fd.append("nucleus", nucleus)
    fd.append("vendor", vendor)
    if (withProcess) {
      fd.append("processing_preset", preset)
      fd.append("preserve_raw", "true")
    } else {
      fd.append("processing_preset", "safe_automatic")
      fd.append("include_spectrum", "true")
    }
    appendSharedSessionGuidance(fd)
    return fd
  }

  const applyPreviewSpectrumPayload = useCallback(
    (data: unknown, fallbackPreset = "balanced") => {
      const xy = extractSpectrumXY(data)
      if (!xy) return false
      const rec = isRecord(data) ? data : {}
      const processingMetadata = isRecord(rec.processing_metadata) ? rec.processing_metadata : null
      update({
        previewSpectrum: {
          x: xy.x,
          y: xy.y,
          xLabel: typeof rec.x_label === "string" ? rec.x_label : "ppm",
          yLabel: typeof rec.y_label === "string" ? rec.y_label : "intensity",
          reversedXAxis: rec.reversed_x_axis !== false,
          processingPreset:
            typeof rec.processing_preset === "string"
              ? rec.processing_preset
              : typeof processingMetadata?.selected_preset === "string"
                ? processingMetadata.selected_preset
                : fallbackPreset,
        },
        previewSpectrumError: "",
        previewSpectrumLoading: false,
      })
      return true
    },
    [update],
  )

  async function runPreviewSpectrum(file: File, archiveId?: string | null) {
    // Quick auto-FT so the user sees an actual spectrum alongside metadata —
    // mirrors the processed-1H/13C "preview shows spectrum" UX. The user can
    // still refine with the full "Process FID" action below.
    //
    // Hold onto the previous auto-FT spectrum while the new one fetches —
    // clearing previewSpectrum here was an unmount source for SpectrumViewer.
    update({ previewSpectrumLoading: true, previewSpectrumError: "" })
    try {
      let data: unknown
      const safeArchiveId = archiveId?.trim()
      if (safeArchiveId) {
        const fd = new FormData()
        fd.append("sample_id", sampleId)
        fd.append("solvent", solvent)
        fd.append("nucleus", nucleus)
        fd.append("selected_preset", "safe_automatic")
        fd.append("processing_preset", "safe_automatic")
        fd.append("save_run", "false")
        appendSharedSessionGuidance(fd)
        data = await apiFetch<unknown>(`/raw-fid/${encodeURIComponent(safeArchiveId)}/preview`, {
          method: "POST",
          body: fd,
        })
      } else {
        data = await apiFetch<unknown>("/nmr/raw-fid/preview", {
          method: "POST",
          body: buildFormData(file, false),
        })
      }
      pushDev("raw_fid_preview_spectrum", data)
      if (!applyPreviewSpectrumPayload(data, "balanced")) {
        update({
          previewSpectrumError: "Auto-FT preview ran but returned no display-ready points.",
          previewSpectrumLoading: false,
        })
      }
    } catch (err) {
      const msg = isMissingNmrEndpoint(err)
        ? RAW_FID_BACKEND_MSG
        : formatApiError(err, "Auto-FT preview failed")
      update({ previewSpectrumError: msg, previewSpectrumLoading: false })
    }
  }

  async function runPreview() {
    const file = getSelectedFile()
    if (!file) {
      setPreviewError("Choose a raw FID archive (.zip / .tar.gz / .tgz).")
      return
    }
    setPreviewLoading(true)
    setPreviewError("")
    // Keep prior chart on screen while the new preview/process runs. Mark
    // ``previewSpectrumLoading`` so the badge shows "Generating preview
    // spectrum…" but the SpectrumViewer is not unmounted. Clearing
    // previewSpectrum/processResult here is what produced the analyze-mode
    // flash. The user sees the OLD chart smoothly replaced by the new one
    // when data arrives. (NMR-display anti-shake convention.)
    update({ previewSpectrumError: "", previewSpectrumLoading: true, activeResultMode: "preview" })
    let shouldGenerateSpectrum = false
    let previewArchiveId: string | null = null
    try {
      const fd = buildFormData(file, false)
      const data = await apiFetch<unknown>("/nmr/raw-fid/preview", { method: "POST", body: fd })
      setPreviewResult(data)
      pushDev("raw_fid_preview", data)
      shouldGenerateSpectrum = !applyPreviewSpectrumPayload(data, "balanced")
      previewArchiveId = extractRawArchiveId(data)
    } catch (err) {
      if (isMissingNmrEndpoint(err)) setPreviewError(RAW_FID_BACKEND_MSG)
      else setPreviewError(formatApiError(err, "Raw FID preview failed"))
    } finally {
      setPreviewLoading(false)
    }
    if (shouldGenerateSpectrum) {
      void runPreviewSpectrum(file, previewArchiveId)
    } else {
      // Preview metadata failed → flip the auto-FT loader off so the badge
      // doesn't get stuck.
      update({ previewSpectrumLoading: false })
    }
  }

  async function runPreviewSpectrumFromSelection() {
    const file = getSelectedFile()
    if (!file) {
      update({ previewSpectrumError: "Choose a raw FID archive first." })
      return
    }
    await runPreviewSpectrum(file, extractRawArchiveId(previewResult))
  }

  async function runProcess() {
    const file = getSelectedFile()
    if (!file) {
      setProcessError("Choose a raw FID archive (.zip / .tar.gz / .tgz).")
      return
    }
    setProcessLoading(true)
    setProcessError("")
    // Keep the prior chart (auto-FT preview spectrum, if any) on screen
    // while the full process runs. ``processLoading`` drives the badge.
    // Clearing here was the source of the analyze-mode flash.
    update({ previewSpectrumError: "", activeResultMode: "process" })
    try {
      const fd = buildFormData(file, true)
      const data = await apiFetch<unknown>("/nmr/raw-fid/process", { method: "POST", body: fd })
      setProcessResult(data)
      pushDev("raw_fid_process", data)
    } catch (err) {
      if (isMissingNmrEndpoint(err)) setProcessError(RAW_FID_BACKEND_MSG)
      else setProcessError(formatApiError(err, "Raw FID process failed"))
    } finally {
      setProcessLoading(false)
    }
  }

  /**
   * Safely pull `field_mhz` from a preview/process response payload.
   * Both NMRRawFIDPreviewResponse and NMRRawFIDProcessResponse carry it
   * as `number | null | undefined` (set by the backend from vendor
   * metadata: Bruker SFO1/BF1 or Varian sfrq/reffrq). Returns null when
   * the field is missing, null, NaN, or non-positive.
   */
  function extractFieldMhz(payload: unknown): number | null {
    if (!isRecord(payload)) return null
    const v = payload.field_mhz
    if (typeof v !== "number") return null
    if (!Number.isFinite(v) || v <= 0) return null
    return v
  }

  // ── GSD-Prompt-3 (experimental) analyze path for raw FID ──────────────
  // Picks the best available ppm/intensity trace in priority order:
  //   1. processResult (full /nmr/raw-fid/process output — best quality)
  //   2. previewResult (preview archive payload, may carry an auto-FT trace)
  //   3. previewSpectrum (cached auto-FT from a prior Preview spectrum click)
  // If none are available, runs /nmr/raw-fid/preview with the safe-automatic
  // preset to produce a trace before calling GSD. Leaves the legacy
  // processResult / previewResult state alone.
  async function runGSDAnalyze() {
    const file = fileRef.current?.files?.[0] ?? selectedFile
    if (!file) {
      setGsdError("Choose a raw FID archive (.zip / .tar.gz / .tgz).")
      return
    }
    setGsdLoading(true)
    setGsdError("")
    try {
      let trace: { x: number[]; y: number[] } | null = null
      if (processResult) trace = extractSpectrumXY(processResult)
      if (!trace && previewResult) trace = extractSpectrumXY(previewResult)
      if (!trace && previewSpectrum) trace = { x: previewSpectrum.x, y: previewSpectrum.y }
      if (!trace) {
        // Auto-fetch a quick preview so the user doesn't need a separate
        // click. Uses the safe-automatic preset, parity with runPreview().
        const previewData = await apiFetch<unknown>("/nmr/raw-fid/preview", {
          method: "POST",
          body: buildFormData(file, false),
        })
        pushDev("raw_fid_gsd_autopreview", previewData)
        update({ previewResult: previewData, previewError: "" })
        trace = extractSpectrumXY(previewData)
      }
      if (!trace || trace.x.length < 16) {
        setGsdError(
          trace == null
            ? "Could not derive a spectrum trace from the raw FID. Run Preview spectrum or Process FID first."
            : `GSD requires ≥16 samples; trace has ${trace.x.length}.`,
        )
        return
      }
      // field_mhz cascade: prefer values the backend FT'd from the actual
      // FID's vendor metadata (Bruker SFO1/BF1 or Varian sfrq/reffrq),
      // fall back to 500 only when neither response surfaced a usable
      // value (unknown vendor or pre-Phase-8 response).
      const fieldMhz =
        extractFieldMhz(processResult) ?? extractFieldMhz(previewResult) ?? 500
      const body: SpectrumGSDAnalyzeRequest = {
        ppm_axis: trace.x,
        intensity: trace.y,
        nucleus,
        solvent: gsdSolvent.trim(),
        field_mhz: fieldMhz,
        level: gsdLevel,
      }
      const data = await apiFetch<SpectrumGSDAnalyzeResult>(
        "/spectrum/analyze/gsd",
        { method: "POST", body },
      )
      setGsdResult(data)
      pushDev("raw_fid_gsd_analyze", data)
    } catch (err) {
      setGsdError(formatApiError(err, "GSD analysis failed"))
    } finally {
      setGsdLoading(false)
    }
  }

  function clearAll() {
    update({
      previewResult: null,
      processResult: null,
      previewError: "",
      processError: "",
      previewSpectrum: null,
      previewSpectrumError: "",
      previewSpectrumLoading: false,
      activeResultMode: null,
      selectedFile: null,
      selectedFileName: null,
    })
    if (fileRef.current) fileRef.current.value = ""
    setGsdResult(null)
    setGsdError("")
    setGsdSolvent(solvent)
  }

  const resultsMode =
    processLoading
      ? "process"
      : previewLoading || previewSpectrumLoading
        ? "preview"
        : activeResultMode === "process" && processResult != null
          ? "process"
          : activeResultMode === "preview" && (previewResult != null || previewSpectrum != null)
            ? "preview"
            : processResult != null
              ? "process"
              : previewResult != null || previewSpectrum != null
                ? "preview"
                : null
  const hasResultSurface = resultsMode != null
  const displayPayload =
    resultsMode === "process" ? processResult : resultsMode === "preview" ? previewResult : null
  /**
   * Dense 13C heuristic: warn the user up-front when /nmr/raw-fid/process
   * is going to take up to a few minutes. Empirical threshold and
   * runtime after the Phase 12d backend perf pass:
   *   - 98,304-pt ¹³C (nmrshiftdb2_60000006) → 3.6 min worst case
   *   - 64K+ ¹³C generally → <40 s after Phase 12d
   *   - under 64K → tens of seconds (no warning)
   * We read `point_count` from whichever response we have so the hint
   * persists across the whole flow.
   */
  const HEAVY_13C_POINT_THRESHOLD = 65536
  const heavyPointCount = (() => {
    const src = processResult ?? previewResult
    if (!src || typeof src !== "object") return null
    const v = (src as { point_count?: unknown }).point_count
    return typeof v === "number" && v > 0 ? v : null
  })()
  const showHeavy13CWarning =
    nucleus === "13C" && heavyPointCount != null && heavyPointCount > HEAVY_13C_POINT_THRESHOLD

  /**
   * Adapt the raw-FID preview/process response (post Phase 11 envelope:
   * `peaks` + `environments` + `category_counts`) into the unified
   * detection shape the shared `<DetectionResultsPanel>` consumes. We
   * defensively guard on `peaks` being an array — older cached
   * responses from before the parity work may not have the envelope.
   */
  const legacyDetectionResult = useMemo(() => {
    const src = processResult ?? previewResult
    if (!src || typeof src !== "object") return null
    const r = src as Partial<NMRRawFIDPreviewResponse>
    if (!Array.isArray(r.peaks) || r.peaks.length === 0) return null
    return adaptLegacyRawFidResult(r as NMRRawFIDPreviewResponse, "legacy")
  }, [processResult, previewResult])

  const promptSidecarConsistency = useMemo(
    () => getPromptSidecarConsistency(displayPayload),
    [displayPayload],
  )
  const promptSidecarQa = useMemo(
    () => getPromptSidecarQa(displayPayload),
    [displayPayload],
  )
  const payloadMode = resultsMode
  const resultTitle = resultsMode === "process" ? "Processed FID output" : "Raw archive metadata"
  const resultDescription =
    resultsMode === "process"
      ? "Spectrum, processing parameters, and acquisition metadata from /nmr/raw-fid/process."
      : "Archive metadata, vendor, SHA-256 hash, and an automatic quick spectrum from Preview."

  // Memoise xy extraction against the source result. Without this the
  // extractor produces fresh ``{x, y}`` arrays on every parent re-render
  // (e.g. typing the Sample ID field), which forces Plotly to redraw and
  // makes the chart shake/blink during unrelated interactions.
  const xyProcess = useMemo(
    () => (processResult ? extractSpectrumXY(processResult) : null),
    [processResult],
  )
  const xyPreview = useMemo(
    () => (previewResult ? extractSpectrumXY(previewResult) : null),
    [previewResult],
  )
  // previewSpectrum is the auto-FT result chained from Preview — used when the
  // full Process step hasn't run yet so the user still sees a spectrum.
  const xyAutoPreview = useMemo(
    () => (previewSpectrum ? { x: previewSpectrum.x, y: previewSpectrum.y } : null),
    [previewSpectrum],
  )
  const processPeaks = useMemo(
    () => (processResult ? extractPeaksFromPayload(processResult) : []),
    [processResult],
  )
  // Stabilise the resolved spectrum xy reference across upstream transitions.
  // The preview / process pipelines may hand us the same numeric x / y in
  // back-to-back responses (e.g. re-running ``process`` with the same
  // preset); reusing the previous reference keeps SpectrumViewer's expensive
  // percentile / mask / sampling memos cached and prevents Plotly from
  // redrawing an already-painted line. (NMR-display anti-shake convention.)
  const xyResolved =
    resultsMode === "process"
      ? processResult
        ? xyProcess
        : xyProcess ?? xyPreview ?? xyAutoPreview
      : xyPreview ?? xyAutoPreview
  const xy = useStableXY(xyResolved)
  const viewerPeaks = resultsMode === "process" ? processPeaks : EMPTY_SPECTRUM_PEAKS

  const xyIsAutoPreview = resultsMode === "preview" && (xyPreview != null || xyAutoPreview != null)
  const autoPreviewPreset = useMemo(() => {
    if (previewSpectrum?.processingPreset) return previewSpectrum.processingPreset
    if (previewResult && isRecord(previewResult) && typeof previewResult.processing_preset === "string") {
      return previewResult.processing_preset
    }
    return "safe_automatic"
  }, [previewResult, previewSpectrum])

  const meta = displayPayload && isRecord(displayPayload) ? displayPayload : null
  const sha =
    meta &&
    (typeof meta.raw_file_sha256 === "string"
      ? meta.raw_file_sha256
      : typeof meta.sha256 === "string"
        ? meta.sha256
        : typeof meta.checksum_sha256 === "string"
          ? meta.checksum_sha256
          : null)
  const vendorDetected =
    meta && (typeof meta.vendor_detected === "string" ? meta.vendor_detected : typeof meta.vendor === "string" ? meta.vendor : null)
  const nucleusMeta = meta && typeof meta.nucleus === "string" ? meta.nucleus : null
  const resolvedNucleus = nucleusMeta === "13C" || nucleusMeta === "1H" ? nucleusMeta : nucleus
  const sw = meta && (meta.spectral_width_hz ?? meta.spectral_width ?? meta.sw)
  const td = meta && (meta.time_domain_points ?? meta.td ?? meta.np)
  // procParams derivation removed — ProcessingParametersCard reads
  // ``payload.processing_parameters`` directly with its own type guards.

  const warnings =
    meta && Array.isArray(meta.warnings) ? meta.warnings.map(String) : meta && typeof meta.warnings === "string" ? [meta.warnings] : []
  const promptSidecarHasUnexpectedActivation = Boolean(
    promptSidecarQa &&
      (promptSidecarQa.active === true ||
        promptSidecarQa.promptPipelineActive === true ||
        promptSidecarConsistency?.usedForPlot ||
        promptSidecarConsistency?.usedForPeakMarkers ||
        promptSidecarConsistency?.usedForPhaseOrBaseline),
  )
  const promptSidecarAccent =
    promptSidecarConsistency?.withinPromptAcceptance === false ||
    promptSidecarQa?.safeToActivate === true ||
    promptSidecarHasUnexpectedActivation
      ? "var(--mt-amber)"
      : "var(--mt-teal)"

  return (
    <div className="space-y-6">
      {/* ── Step 1 — Setup & Upload ────────────────────────────────────── */}
      <ModuleCard
        accent="teal"
        eyebrow="Step 1 · Setup"
        title="Configure & upload raw FID archive"
        icon={Upload}
        description="Set sample metadata, choose nucleus and vendor, then drop a raw FID archive (.zip / .tar.gz / .tgz). The original archive is preserved unchanged."
        className="min-w-0"
      >
        <div className="space-y-5">
          {/* Sample ID + Solvent */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="raw-sample" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Sample ID
              </Label>
              <Input
                id="raw-sample"
                value={sampleId}
                onChange={(e) => onSampleIdChange(e.target.value)}
                className="font-mono"
              />
              <p className="text-[11px] text-muted-foreground">Shared with SpectraCheck session.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="raw-solvent" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Solvent <span className="ml-1 text-[10px] font-normal text-muted-foreground/70">(read-only)</span>
              </Label>
              <Input id="raw-solvent" value={solvent} readOnly className="bg-muted/40 font-mono" />
            </div>
          </div>

          {/* Nucleus + Vendor pill toggles */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Nucleus</Label>
              <div className="inline-flex rounded-lg border border-input bg-background p-0.5">
                {(["1H", "13C"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setNucleus(option)}
                    className={cn(
                      "rounded-md px-4 py-1.5 font-mono text-sm font-bold transition-colors",
                      nucleus === option
                        ? "shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                    style={
                      nucleus === option
                        ? { backgroundColor: "var(--mt-teal)", color: "#04080F" }
                        : undefined
                    }
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Vendor</Label>
              <div className="inline-flex flex-wrap rounded-lg border border-input bg-background p-0.5">
                {[
                  { value: "auto", label: "Auto" },
                  { value: "bruker", label: "Bruker" },
                  { value: "agilent", label: "Agilent" },
                ].map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setVendor(option.value)}
                    className={cn(
                      "rounded-md px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-wide transition-colors",
                      vendor === option.value
                        ? "shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                    style={
                      vendor === option.value
                        ? { backgroundColor: "var(--mt-teal)", color: "#04080F" }
                        : undefined
                    }
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Drop-zone file picker */}
          <div className="space-y-1.5">
            <Label htmlFor="raw-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Raw FID archive
            </Label>
            {/* Drop zone is a div + onClick (see processed section for rationale). */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Drop raw FID archive or press Enter to browse"
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  fileRef.current?.click()
                }
              }}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                const file = e.dataTransfer.files?.[0]
                if (file) attachFile(file)
              }}
              className={cn(
                "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2",
                dragOver
                  ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                  : selectedFileName
                  ? "border-[color:var(--mt-teal)]/40 bg-[color:var(--mt-teal-soft)]/40"
                  : "border-input hover:border-[color:var(--mt-teal)]/60 hover:bg-muted/30"
              )}
            >
              <Archive
                className="mb-2 h-7 w-7"
                style={{ color: dragOver || selectedFileName ? "var(--mt-teal)" : undefined }}
                aria-hidden
              />
              <p className="font-mono text-sm font-bold tracking-tight">
                {selectedFileName ? "Archive ready" : dragOver ? "Drop to attach" : "Drop raw FID archive or click to browse"}
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                ZIP · TAR.GZ · TGZ
              </p>
            </div>
            {/* Native input — sr-only so shadcn classes don't override hidden sizing. */}
            <input
              id="raw-file"
              ref={fileRef}
              type="file"
              accept={SPECTRACHECK_RAW_FID_ACCEPT}
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) {
                  setSelectedFile(file)
                  setSelectedFileName(file.name)
                } else {
                  setSelectedFile(null)
                  setSelectedFileName(null)
                }
              }}
            />
            {selectedFileName ? (
              <div
                className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <FileText className="h-4 w-4 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                  <span className="truncate font-mono text-xs">{selectedFileName}</span>
                </div>
                <button
                  type="button"
                  onClick={clearSelectedFile}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Remove selected file"
                >
                  <X className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
            ) : null}
          </div>

          {/* Preserve-raw badge (replaces the disabled checkbox) */}
          <div
            className="flex items-center gap-2 rounded-md border px-3 py-2"
            style={{ borderColor: "var(--mt-green)", backgroundColor: "var(--mt-green-soft)" }}
          >
            <Lock className="h-4 w-4 shrink-0" style={{ color: "var(--mt-green)" }} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[11px] font-bold uppercase tracking-[0.14em]" style={{ color: "var(--mt-green)" }}>
                Original FID preserved
              </p>
              <p className="text-xs text-muted-foreground">
                Processing always operates on a derived copy. <span className="font-mono">preserve_raw=true</span> is locked on.
              </p>
            </div>
          </div>

          {/* Advanced — collapsible */}
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
              >
                <span className="flex items-center gap-2">
                  <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                  <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                    Advanced options
                  </span>
                </span>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 text-muted-foreground transition-transform",
                    advancedOpen && "rotate-180"
                  )}
                  aria-hidden
                />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-4">
              <div className="space-y-1.5">
                <Label htmlFor="raw-session-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Reuse session raw FID
                </Label>
                <select
                  id="raw-session-file"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 font-mono text-sm shadow-xs outline-none"
                  value={sessionRawFileIdChoice}
                  onChange={(e) => setSessionRawFileIdChoice(e.target.value)}
                >
                  <option value="">— none — use archive above</option>
                  {rawSessionFileOptions.map((f) => (
                    <option key={f.file_id} value={f.file_id}>
                      {f.filename} ({f.file_kind})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-muted-foreground">
                  Reuse a raw FID archive already attached to this session.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="raw-preset" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Processing preset
                </Label>
                <select
                  id="raw-preset"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 font-mono text-sm shadow-xs outline-none"
                  value={preset}
                  onChange={(e) => setPreset(e.target.value as (typeof PRESETS)[number]["value"])}
                >
                  {PRESETS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-muted-foreground">
                  Used for full <span className="font-mono">/process</span>; preview uses the locked quick-spectrum preset.
                </p>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </ModuleCard>

      {/* ── Step 2 — Run ───────────────────────────────────────────────── */}
      <ModuleCard
        accent="teal"
        eyebrow="Step 2 · Run"
        title="Inspect or process"
        icon={Zap}
        description="Preview archive metadata with an automatic quick spectrum, or process the FID through the full selected recipe."
        className="min-w-0"
      >
        <div className="space-y-4">
          {/* Analysis backend selector — opt-in experimental GSD-Prompt-3.
              Default MUST remain `legacy`; do not silently flip tenants. */}
          <GsdAnalysisControls
            backend={analysisBackend}
            onBackendChange={setAnalysisBackend}
            level={gsdLevel}
            onLevelChange={setGsdLevel}
            solvent={gsdSolvent}
            onSolventChange={setGsdSolvent}
          />

          {/* Two prominent action tiles */}
          <div className="grid gap-3 sm:grid-cols-2">
            {/* Inspect (preview) tile */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled={previewLoading}
                  onClick={runPreview}
                  className={cn(
                    "group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                    "hover:-translate-y-px hover:shadow-md",
                    previewLoading
                      ? "cursor-wait opacity-70"
                      : "border-input hover:border-[color:var(--mt-teal)]/40"
                  )}
                  style={{
                    borderTop: "3px solid var(--mt-teal)",
                  }}
                >
                  <div className="flex w-full items-center justify-between">
                    <span
                      className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      <Eye className="h-3.5 w-3.5" aria-hidden />
                      Inspect
                    </span>
                    <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                      Metadata + quick FT
                    </span>
                  </div>
                  <span className="font-mono text-base font-bold leading-tight">
                    {previewLoading ? "Reading…" : "Preview spectrum"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Read archive contents, vendor, file hash, and acquisition parameters, then display a quick spectrum.
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                POST /nmr/raw-fid/preview
              </TooltipContent>
            </Tooltip>

            {/* Process tile (primary) — routes to legacy or GSD backend
                based on the Analysis backend selector above. */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled={processLoading || gsdLoading}
                  onClick={analysisBackend === "gsd_prompt3" ? runGSDAnalyze : runProcess}
                  className={cn(
                    "group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                    "hover:-translate-y-px hover:shadow-md",
                    (processLoading || gsdLoading)
                      ? "cursor-wait opacity-70"
                      : analysisBackend === "gsd_prompt3"
                        ? "border-amber-500/40 hover:border-amber-600"
                        : "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]"
                  )}
                  style={{
                    borderTop: analysisBackend === "gsd_prompt3" ? "3px solid #D97706" : "3px solid var(--mt-teal)",
                    backgroundColor: analysisBackend === "gsd_prompt3" ? "rgb(254 243 199 / 0.5)" : "var(--mt-teal-soft)",
                  }}
                >
                  <div className="flex w-full items-center justify-between">
                    <span
                      className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                      style={{ color: analysisBackend === "gsd_prompt3" ? "#B45309" : "var(--mt-teal-ink)" }}
                    >
                      {analysisBackend === "gsd_prompt3" ? (
                        <FlaskConical className="h-3.5 w-3.5" aria-hidden />
                      ) : (
                        <Sparkles className="h-3.5 w-3.5" aria-hidden />
                      )}
                      {analysisBackend === "gsd_prompt3" ? "GSD analyze" : "Process"}
                    </span>
                    <span
                      className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                      style={{ color: analysisBackend === "gsd_prompt3" ? "#B45309" : "var(--mt-teal-ink)" }}
                    >
                      {analysisBackend === "gsd_prompt3" ? "Experimental" : "Generates spectrum"}
                    </span>
                  </div>
                  <span className="font-mono text-base font-bold leading-tight">
                    {analysisBackend === "gsd_prompt3"
                      ? (gsdLoading ? "Running GSD…" : `Run GSD analysis (level ${gsdLevel})`)
                      : (processLoading ? "Processing…" : "Process FID")}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {analysisBackend === "gsd_prompt3"
                      ? "Industry-standard peak detection with auto-classification on the FT-processed spectrum."
                      : "Fourier transform + apodization on a derived copy. Generates the displayable spectrum."}
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                {analysisBackend === "gsd_prompt3"
                  ? "POST /spectrum/analyze/gsd (experimental)"
                  : "POST /nmr/raw-fid/process"}
              </TooltipContent>
            </Tooltip>
          </div>

          {/* Background job + clear row */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed bg-muted/20 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <PlayCircle className="h-4 w-4 text-muted-foreground" aria-hidden />
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Background job
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 font-mono text-[11px]"
                onClick={() => void startRawPreviewJob()}
              >
                Preview
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 font-mono text-[11px]"
                onClick={() => void startRawProcessJob()}
              >
                Process
              </Button>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 font-mono text-[11px] text-muted-foreground"
              onClick={clearAll}
            >
              <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden />
              Clear
            </Button>
          </div>

          {jobActionError ? (
            <AlertCard variant="warning" title="Job error" description={jobActionError} />
          ) : null}

          {analysisJob.jobId ? (
            <AnalysisJobTimeline
              job={analysisJob}
              variant="compact"
              evidenceLayer={nucleus === "1H" ? "raw_fid_1h" : "raw_fid_13c"}
              sourceTab="Raw FID upload"
            />
          ) : null}

          {showHeavy13CWarning && (
            <AlertCard
              variant="info"
              title={processLoading ? "Processing dense ¹³C spectrum…" : "Dense ¹³C spectrum"}
              description={
                processLoading
                  ? `This may take up to ~4 minutes (${heavyPointCount?.toLocaleString()} points).`
                  : `This spectrum has ${heavyPointCount?.toLocaleString()} points. Running Process FID may take up to ~4 minutes.`
              }
            />
          )}
          {previewError && (
            <AlertCard variant="error" title="Preview failed" description={previewError} />
          )}
          {processError && (
            <AlertCard variant="error" title="Process failed" description={processError} />
          )}
          {gsdError && (
            <AlertCard variant="error" title="GSD analyze failed" description={gsdError} />
          )}
        </div>
      </ModuleCard>

      {/* In-place full-screen view of the ENTIRE results region (spectrum +
          every analysis panel below — GSD, multiplets, J-couplings, region
          integrals, shift prediction, legacy detector peak picks). The same
          live subtree renders inline when closed and full-screen when open, so
          nothing re-fetches and the spectrum keeps its exact shape/state. */}
      <SpectrumResultsFullscreen
        open={rawFullscreenOpen}
        onClose={() => setRawFullscreenOpen(false)}
        eyebrow={`Full screen · Raw FID ${resolvedNucleus}`}
        title={resultTitle}
        subtitle={selectedFileName ?? undefined}
        tag={sampleId.trim() || undefined}
        testId="raw-fid-fullscreen-view"
      >
      {/* ── Step 3 — Results ──────────────────────────────────────────── */}
      {/*
        Show this surface as soon as Preview or Process starts. The result
        card is the loading surface and the final surface, so it does not
        get replaced by a different card once the server answers.
      */}
      {hasResultSurface && (
        <div className="min-w-0" data-stable-results-surface="">
          <ModuleCard
            accent="teal"
            eyebrow="Step 3 · Results"
            title={resultTitle}
            icon={BarChart3}
            description={resultDescription}
            className="min-w-0 overflow-visible shadow-none"
          >
          <div className="space-y-4">
            {/* In-card loading badge — replaces the "hide whole card"
                gate so the SpectrumViewer stays mounted while the
                fetch runs (no flash). */}
            {(previewLoading || processLoading) ? (
              <div
                className="flex items-center gap-2 rounded-md border px-3 py-1.5 font-mono text-[11px]"
                style={{ borderColor: "var(--mt-teal-ink)", color: "var(--mt-teal-ink)", backgroundColor: "var(--mt-teal-soft)" }}
                data-testid="raw-fid-results-loading-badge"
                aria-live="polite"
              >
                <span
                  className="inline-block h-2 w-2 animate-pulse rounded-full"
                  style={{ backgroundColor: "var(--mt-teal)" }}
                />
                {processLoading ? "Processing FID…" : "Refreshing preview…"}
              </div>
            ) : null}
            {/* KPI tiles — only shown when meaningful values are returned */}
            {(vendorDetected || sw != null || td != null || warnings.length > 0) && (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {vendorDetected && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <ShieldCheck className="h-3 w-3" aria-hidden />
                        Vendor
                      </p>
                      <p
                        className="font-mono text-base font-bold leading-tight uppercase tracking-wide"
                        style={{ color: "var(--mt-teal-ink)" }}
                      >
                        {vendorDetected}
                      </p>
                    </CardContent>
                  </Card>
                )}
                {nucleusMeta && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <Waves className="h-3 w-3" aria-hidden />
                        Nucleus
                      </p>
                      <p
                        className="font-mono text-base font-bold leading-tight"
                        style={{ color: "var(--mt-teal-ink)" }}
                      >
                        {nucleusMeta}
                      </p>
                    </CardContent>
                  </Card>
                )}
                {sw != null && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <Activity className="h-3 w-3" aria-hidden />
                        Spectral width
                      </p>
                      <p
                        className="font-mono text-base font-bold leading-tight tabular-nums"
                        style={{ color: "var(--mt-teal-ink)" }}
                      >
                        {String(sw)}
                      </p>
                    </CardContent>
                  </Card>
                )}
                {td != null && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <Hash className="h-3 w-3" aria-hidden />
                        TD points
                      </p>
                      <p
                        className="font-mono text-base font-bold leading-tight tabular-nums"
                        style={{ color: "var(--mt-teal-ink)" }}
                      >
                        {String(td)}
                      </p>
                    </CardContent>
                  </Card>
                )}
                {warnings.length > 0 && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-amber)" }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <AlertTriangle className="h-3 w-3" aria-hidden />
                        Warnings
                      </p>
                      <p
                        className="font-mono text-base font-bold leading-tight tabular-nums"
                        style={{ color: "var(--mt-amber)" }}
                      >
                        {warnings.length}
                      </p>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}

            {/* Spectrum toolbar — opt-in full-screen trigger. Inline view below
                is unchanged; this only opens a presentational overlay. */}
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Spectrum
              </span>
              {!rawFullscreenOpen ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setRawFullscreenOpen(true)}
                  disabled={!xy}
                  data-testid="raw-fid-open-fullscreen"
                  aria-haspopup="dialog"
                  className="gap-1.5"
                >
                  <Maximize2 className="h-4 w-4" aria-hidden />
                  Full screen
                </Button>
              ) : null}
            </div>

            {/* Spectrum — full page width */}
            <div className="min-w-0 space-y-2">
              {xyIsAutoPreview ? (
                <div
                  className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
                  style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                >
                  <Sparkles className="h-3.5 w-3.5" style={{ color: "var(--mt-teal)" }} aria-hidden />
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                    style={{ color: "var(--mt-teal-ink)" }}
                  >
                    Auto-FT preview · {autoPreviewPreset}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    Quick Fourier-transformed preview. Run Process FID for full apodization, phasing, and baseline correction.
                  </p>
                </div>
              ) : null}
              {xy ? (
                // Raw FID needs a denser Plotly trace than processed uploads
                // so dd/t/q/m fine structure is visible without zooming. The
                // aromatic cleanup is display-only and peak-preserving; it
                // does not touch the evidence trace or processed spectra.
                <SpectrumViewer
                  x={xy.x}
                  y={xy.y}
                  peaks={viewerPeaks}
                  nucleus={resolvedNucleus}
                  renderMode="webgl"
                  rawFidAromaticBaseSmoothing
                  maxObservedPoints={12_000}
                  observedPointsPerPixel={24}
                />
              ) : processLoading || previewLoading || previewSpectrumLoading ? (
                <div
                  className="flex h-[360px] min-w-0 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 p-6 text-center"
                  data-testid="raw-fid-results-pending-spectrum"
                >
                  <div
                    className="mb-3 h-2 w-2 animate-pulse rounded-full"
                    style={{ backgroundColor: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <p className="font-mono text-sm font-bold tracking-tight">
                    {processLoading
                      ? "Processing FID spectrum…"
                      : previewSpectrumLoading
                        ? "Generating quick spectrum…"
                        : "Reading raw FID metadata…"}
                  </p>
                  <p className="mt-1 max-w-md text-xs text-muted-foreground">
                    The spectrum and processing details will populate here together when the server response is ready.
                  </p>
                </div>
              ) : previewSpectrumError ? (
                <AlertCard
                  variant="warning"
                  title="Preview spectrum unavailable"
                  description={previewSpectrumError}
                />
              ) : (
                <div className="space-y-2">
                  <AlertCard
                    variant="warning"
                    title="Raw spectrum not generated yet"
                    description={
                      processResult
                        ? "Processing completed, but no display-ready spectrum points were returned. Review the response details below."
                        : "Preview completed, but no display-ready spectrum points were returned yet. Generate the quick auto-FT preview again, or run Process raw FID for the full selected recipe."
                    }
                  />
                  {!processResult ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void runPreviewSpectrumFromSelection()}
                      disabled={previewSpectrumLoading}
                      data-testid="raw-fid-show-preview-spectrum"
                    >
                      <Sparkles className="mr-1 h-3.5 w-3.5" aria-hidden />
                      {previewSpectrumLoading ? "Generating preview spectrum…" : "Show preview spectrum (auto-FT)"}
                    </Button>
                  ) : null}
                </div>
              )}
            </div>

            {/* Use Unified Evidence — prominent CTA row right under the spectrum */}
            {displayPayload != null ? (
              <div
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"
                style={{
                  borderTop: "3px solid var(--mt-teal)",
                  backgroundColor: "var(--mt-teal-soft)",
                }}
              >
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
                  <div>
                    <p
                      className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      Use in unified evidence
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Add this {payloadMode === "process" ? "processed FID" : "metadata preview"} to the unified evidence stream.
                    </p>
                  </div>
                </div>
                <SpectraCheckUseUnifiedEvidenceButton
                  response={displayPayload}
                  meta={{
                    layer: nucleus === "1H" ? "raw_fid_1h" : "raw_fid_13c",
                    sourceTab: "Raw FID upload",
                    title: payloadMode === "process" ? "Raw FID process" : "Raw FID preview",
                    endpoint: payloadMode === "process" ? "/nmr/raw-fid/process" : "/nmr/raw-fid/preview",
                    sampleId: sampleId.trim() || undefined,
                  }}
                />
              </div>
            ) : null}

            {/* Cross-tab handoff — push this FID spectrum into the Processed analyzer
                so the user doesn't have to re-upload it as a CSV/JCAMP. */}
            {xy ? (
              <div
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"
                style={{
                  borderTop: "3px solid var(--mt-teal)",
                  backgroundColor: "var(--mt-teal-soft)",
                }}
                data-testid="raw-fid-send-to-processed"
              >
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
                  <div>
                    <p
                      className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      Cross-tab link
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Send this FID-derived spectrum to the Processed analyzer — no re-upload needed.
                    </p>
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  onClick={() =>
                    sendTabLink({
                      kind: "raw_fid_to_processed",
                      sourceLabel: `Raw FID · ${selectedFileName ?? "uploaded archive"}`,
                      payload: {
                        sample_id: sampleId.trim() || null,
                        nucleus,
                        filename: selectedFileName ?? undefined,
                        point_count: xy.x.length,
                        x: xy.x,
                        y: xy.y,
                        x_label: "ppm",
                        y_label: "intensity",
                        reversed_x_axis: true,
                        metadata: {
                          linked_from: "raw_fid_to_processed",
                          source_filename: selectedFileName ?? null,
                          source_processing_preset: xyIsAutoPreview ? autoPreviewPreset : processResult ? "user-selected" : null,
                        },
                        warnings: warnings,
                        notes: [
                          "Spectrum was forwarded from the Raw FID tab — re-runs against /nmr/processed/analyze when you press the Analyze action.",
                        ],
                      },
                    })
                  }
                  data-testid="raw-fid-send-to-processed-button"
                >
                  Send to Processed analyzer
                </Button>
              </div>
            ) : null}

            {/* Identity / processing / metadata / warnings — 2-col grid below */}
            {displayPayload != null ? (
              <div className="grid min-w-0 gap-4 lg:grid-cols-2">
                {/* Identity card (SHA-256 + badges) */}
                {(sha || vendorDetected || nucleusMeta) && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-3 py-3">
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        Identity
                      </p>
                      {sha && (
                        <div>
                          <p className="text-[11px] font-medium text-muted-foreground">Raw file SHA-256</p>
                          <p className="mt-1 break-all font-mono text-[10px]">{sha}</p>
                        </div>
                      )}
                      {(vendorDetected || nucleusMeta) && (
                        <div className="flex flex-wrap gap-1.5">
                          {vendorDetected && (
                            <Badge
                              variant="outline"
                              className="font-mono text-[10px]"
                              style={{ borderColor: "var(--mt-teal-ink)", color: "var(--mt-teal-ink)" }}
                            >
                              Vendor · {vendorDetected}
                            </Badge>
                          )}
                          {nucleusMeta && (
                            <Badge
                              variant="outline"
                              className="font-mono text-[10px]"
                              style={{ borderColor: "var(--mt-teal-ink)", color: "var(--mt-teal-ink)" }}
                            >
                              Nucleus · {nucleusMeta}
                            </Badge>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Processing parameters moved to a collapsible at the bottom
                    of the results (just above Developer JSON) so reviewers
                    aren't forced to scroll past the processing knobs to see
                    the picked-peaks / evidence panels that drive the analysis. */}

                {/* Acquisition metadata — friendly flat key/value grid
                    matching the processing-parameters card style. Previously
                    a JSON-textarea dump. */}
                <MetadataKeyValueCard
                  payload={displayPayload}
                  title="Acquisition metadata"
                  field="acquisition_metadata"
                  testId="acquisition-metadata-card"
                />

                {promptSidecarQa ? (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: `3px solid ${promptSidecarAccent}` }}
                    data-testid="prompt-sidecar-consistency-card"
                  >
                    <CardContent className="space-y-3 py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p
                          className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                          style={{ color: promptSidecarAccent }}
                        >
                          <ShieldCheck className="h-3 w-3" aria-hidden />
                          Prompt reader sidecar
                        </p>
                        <Badge
                          variant="outline"
                          className="font-mono text-[10px]"
                          style={{ borderColor: promptSidecarAccent, color: promptSidecarAccent }}
                        >
                          Review-only metadata
                        </Badge>
                      </div>

                      <div className="grid gap-2 sm:grid-cols-4">
                        <div className="rounded-md border bg-muted/20 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Status
                          </p>
                          <p className="text-xs font-medium">
                            {promptSidecarConsistency
                              ? humanizePromptSidecarStatus(promptSidecarConsistency.status)
                              : promptSidecarQa.validationStatus
                                ? humanizePromptSidecarStatus(promptSidecarQa.validationStatus)
                                : promptSidecarQa.available === false
                                  ? "Sidecar unavailable"
                                  : "Metadata available"}
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/20 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Active peaks
                          </p>
                          <p className="font-mono text-xs font-medium tabular-nums">
                            {formatPromptSidecarNumber(promptSidecarConsistency?.activePeakCount ?? null)}
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/20 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Prompt peaks
                          </p>
                          <p className="font-mono text-xs font-medium tabular-nums">
                            {formatPromptSidecarNumber(promptSidecarConsistency?.recommendedPeakCount ?? null)}
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/20 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Delta
                          </p>
                          <p className="font-mono text-xs font-medium tabular-nums">
                            {formatPromptSidecarNumber(promptSidecarConsistency?.peakCountDelta ?? null)}
                          </p>
                        </div>
                      </div>

                      <div
                        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
                        data-testid="prompt-sidecar-qa-details"
                      >
                        <div className="rounded-md border bg-muted/10 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Reader
                          </p>
                          <p className="text-xs font-medium">
                            {promptSidecarQa.readerDiagnosticsAvailable ? "Available" : "Not reported"}
                          </p>
                          {promptSidecarQa.nucleus || promptSidecarQa.fieldMhz != null ? (
                            <p className="font-mono text-[10px] text-muted-foreground">
                              {promptSidecarQa.nucleus ?? "nucleus —"} ·{" "}
                              {promptSidecarQa.fieldMhz != null
                                ? `${promptSidecarQa.fieldMhz.toFixed(1)} MHz`
                                : "field —"}
                            </p>
                          ) : null}
                        </div>
                        <div className="rounded-md border bg-muted/10 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Phase
                          </p>
                          <p className="text-xs font-medium">{promptSidecarQa.phaseMethod ?? "Not reported"}</p>
                          <p className="font-mono text-[10px] text-muted-foreground">
                            P0 {formatPromptSidecarNumber(promptSidecarQa.phaseZeroOrderDegrees)}°
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/10 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Baseline
                          </p>
                          <p className="text-xs font-medium">{promptSidecarQa.baselineMethod ?? "Not reported"}</p>
                          <p className="font-mono text-[10px] text-muted-foreground">
                            order {formatPromptSidecarNumber(promptSidecarQa.baselineOrder)} · RMSE{" "}
                            {formatPromptSidecarPercent(promptSidecarQa.baselineRmseFractionFullScale)}
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/10 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Sidecar runtime
                          </p>
                          <p className="font-mono text-xs font-medium tabular-nums">
                            {formatPromptSidecarRuntime(promptSidecarQa.runtimeMs)}
                          </p>
                          <p className="font-mono text-[10px] text-muted-foreground">
                            {shortPromptSidecarHash(promptSidecarQa.fingerprintHash)}
                          </p>
                        </div>
                      </div>

                      <p className="text-xs text-muted-foreground">
                        Legacy spectrum, peak markers, phase, and baseline remain authoritative.
                      </p>
                      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                        Not used for plot · Not used for peak markers · Not used for phase/baseline
                      </p>
                      {promptSidecarConsistency?.message ? (
                        <p className="text-xs text-muted-foreground">{promptSidecarConsistency.message}</p>
                      ) : null}
                      {promptSidecarHasUnexpectedActivation ? (
                        <p className="text-xs font-medium" style={{ color: "var(--mt-amber)" }}>
                          Unexpected activation flag present; review before enabling any Prompt 1/2 pipeline output.
                        </p>
                      ) : null}
                      {(promptSidecarQa.activeVisiblePipeline ||
                        promptSidecarQa.validationVersion ||
                        promptSidecarQa.safeToUseForAnalysisMetadata != null) ? (
                        <p className="break-words font-mono text-[10px] text-muted-foreground">
                          Active pipeline: {promptSidecarQa.activeVisiblePipeline ?? "legacy"} · Validation:{" "}
                          {promptSidecarQa.validationVersion ?? "not reported"} · Analysis metadata:{" "}
                          {promptSidecarQa.safeToUseForAnalysisMetadata === true ? "available" : "guarded"}
                        </p>
                      ) : null}
                      {promptSidecarConsistency &&
                      (promptSidecarConsistency.activePeakSource ||
                        promptSidecarConsistency.recommendedPeakCountSource ||
                        promptSidecarConsistency.acceptanceTolerance != null) ? (
                        <p className="break-words font-mono text-[10px] text-muted-foreground">
                          Source: {promptSidecarConsistency.activePeakSource ?? "legacy"} · Prompt:{" "}
                          {promptSidecarConsistency.recommendedPeakCountSource ?? "sidecar"} · Tolerance:{" "}
                          {formatPromptSidecarNumber(promptSidecarConsistency.acceptanceTolerance)}
                        </p>
                      ) : null}
                    </CardContent>
                  </Card>
                ) : null}

                {/* Warnings card */}
                {warnings.length > 0 && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-amber)" }}
                  >
                    <CardContent className="space-y-2 py-3">
                      <p
                        className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                        style={{ color: "var(--mt-amber)" }}
                      >
                        <AlertTriangle className="h-3 w-3" aria-hidden />
                        Warnings
                      </p>
                      <ul
                        className="list-inside list-disc space-y-0.5 text-xs"
                        style={{ color: "var(--mt-amber)" }}
                      >
                        {warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                )}
              </div>
            ) : null}

            {/* Enriched picked peaks + evidence panels — parity with the
                Processed 1H/13C tab. ``/nmr/raw-fid/process`` now returns
                the same shape (peaks with category/region, plus
                peak_category_summary, labile_hydrogen_summary,
                proton_inventory, impurity_candidates), so the same panels
                light up here automatically. */}
            {resultsMode === "process" && displayPayload != null ? (
              <>
                {/* Inferred NMR prose summary — same panel as the processed
                    1H/13C tab so the deconvolution + reference-guided
                    multiplicity output is visible on both upload paths. */}
                <InferredNmrTextPanel payload={displayPayload} />
                <EnrichedPickedPeaksPanel payload={displayPayload} />
                <SpectraCheckEvidencePanels payload={displayPayload} />
              </>
            ) : null}

            {/* Processing parameters — collapsible, second-to-last on the
                page so reviewers see picked peaks + evidence first and only
                expand the processing knobs when auditing. Defaults to closed. */}
            {displayPayload != null ? (
              <Collapsible
                open={processingParamsOpen}
                onOpenChange={setProcessingParamsOpen}
                data-testid="processing-parameters-collapsible"
              >
                <CollapsibleTrigger asChild>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
                    data-testid="processing-parameters-collapsible-trigger"
                  >
                    <span className="flex items-center gap-2">
                      <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                      <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                        Processing parameters
                      </span>
                    </span>
                    <ChevronDown
                      className={cn(
                        "h-4 w-4 text-muted-foreground transition-transform",
                        processingParamsOpen && "rotate-180",
                      )}
                      aria-hidden
                    />
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent
                  className="pt-3"
                  data-testid="processing-parameters-collapsible-content"
                >
                  <ProcessingParametersCard payload={displayPayload} />
                </CollapsibleContent>
              </Collapsible>
            ) : null}

            {/* Developer JSON — full width. */}
            {displayPayload != null ? <DeveloperJsonPanel data={displayPayload} /> : null}
          </div>
          </ModuleCard>
        </div>
      )}

      {/* ── Step 3b — GSD-Prompt-3 output (experimental) ──────────────────
          Only renders when the user has run the experimental backend.
          Lives alongside the legacy Step 3 results without replacing them. */}
      <GsdResultsPanel result={gsdResult} testId="raw-fid-gsd-results-surface" />

      {/* ── Step 3c — Multiplet analysis (Phase 26) ───────────────────────
          Chained automatically off the GSD result — peaks above S/N>3
          forwarded to /spectrum/analyze/multiplets for first-order +
          complex multiplet detection. */}
      <GsdMultipletPanel gsdResult={gsdResult} testId="raw-fid-multiplet-results-surface" />

      {/* ── Step 3d — Candidate J-agreement (Phase 26b / v0.7.1) ──────────
          Same panel as the processed section; shares the multiplet
          WeakMap cache so the multiplet POST fires once per gsdResult. */}
      <GsdJCouplingPanel
        gsdResult={gsdResult}
        candidatesText={candidatesText}
        sampleId={sampleId}
        compoundClass={compoundClassForRequest(compoundClass) || undefined}
        testId="raw-fid-jcoupling-results-surface"
      />

      {/* ── Step 3e — Region integration (Prompt 5) ───────────────────────
          Integrate each detected multiplet range on the FT-processed
          trace. field_mhz pulled from the vendor metadata (same cascade
          as the GSD call); shares the multiplet WeakMap cache. */}
      <GsdIntegrationPanel
        gsdResult={gsdResult}
        trace={xy}
        nucleus={nucleus}
        solvent={solvent}
        fieldMhz={extractFieldMhz(processResult) ?? extractFieldMhz(previewResult) ?? 500}
        testId="raw-fid-integration-results-surface"
      />

      {/* ── Candidate tool — per-atom shift prediction (v0.7.8) ──────────
          Structure-derived; predicts ¹H/¹³C shifts from a candidate
          SMILES. Self-gates on the candidate list. */}
      <ShiftPredictionPanel
        candidatesText={candidatesText}
        testId="raw-fid-shift-prediction-surface"
      />

      {/* ── Candidate tool — spectral-similarity retrieval ──────────────
          Encodes a candidate SMILES and queries the server-configured
          similarity index for nearest reference spectra. Self-gates on
          the candidate list. */}
      <SpectrumRetrievePanel
        candidatesText={candidatesText}
        testId="raw-fid-spectrum-retrieve-surface"
      />

      {/* ── Step 3c — Legacy detection summary (unified panel) ──────────
          Post-Phase-11 the raw-FID responses expose the same envelope
          (`peaks` + `environments` + `category_counts`) as GSD. Render
          them through the same component so users get a consistent
          summary view regardless of which backend they chose. The
          existing Step 3 evidence-detail rendering above is untouched. */}
      {legacyDetectionResult ? (
        <DetectionResultsPanel
          result={legacyDetectionResult}
          testId="raw-fid-legacy-results-surface"
        />
      ) : null}
      </SpectrumResultsFullscreen>
    </div>
  )
}
