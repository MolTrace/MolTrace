"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  useRawFidTabState,
  useSpectraCheckTabLink,
  type RawFidPreset,
  type RawFidTabState,
  type RawFidVendor,
} from "@/components/spectracheck/spectracheck-tab-state-context"
import { apiFetch, isModuleNotIncludedError } from "@/lib/api/client"
import {
  COMPOUND_CLASS_UNSPECIFIED,
  compoundClassForRequest,
  type CompoundClassValue,
} from "@/src/lib/spectracheck/compound-classes"
import { SPECTRACHECK_RAW_FID_ACCEPT, isRawFidArchiveFilename } from "@/src/lib/spectracheck/spectrum-file-formats"
import { registerSpectraCheckRuntimeReset } from "@/src/lib/spectracheck/spectracheck-runtime-reset"
import {
  dataTransferHasDirectory,
  detectVendorDataset,
  formatBytes,
  splitVendorFolderByExperiment,
  vendorFolderEntriesFromDataTransfer,
  vendorFolderEntriesFromFileList,
  zipVendorFolder,
  type VendorFolderDetection,
} from "@/src/lib/spectracheck/vendor-folder-drop"
import {
  isOfferedNucleus,
  sniffArchiveAcquisition,
  sniffExperimentAcquisition,
  summarizeAcquisition,
  type AcquisitionSummary,
  type VendorAcquisitionFacts,
} from "@/src/lib/spectracheck/vendor-acquisition"
import { SpectraCheckRawFidBatch } from "@/components/spectracheck/spectracheck-raw-fid-batch"
import {
  RAW_FID_BATCH_MAX_ITEMS,
  abortRawFidBatchRun,
  beginRawFidBatchRun,
  classifyRawFidBatchFailure,
  createBlockedRawFidBatchItem,
  createRawFidBatchItem,
  endRawFidBatchRun,
  isRawFidBatchItemRunnable,
  isRawFidBatchRunCurrent,
  isWithdrawnFromRawFidBatchRun,
  preflightRawFidArchive,
  rawFidBatchRun,
  stopRawFidBatchRun,
  withdrawFromRawFidBatchRun,
  type RawFidBatchItem,
  type RawFidBatchMode,
} from "@/src/lib/spectracheck/raw-fid-batch"
import { SpectrumViewer } from "@/components/science/SpectrumViewer"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import {
  EnrichedPickedPeaksPanel,
  InferredNmrTextPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"
import { SpectraCheckFidRunReview } from "@/components/spectracheck/spectracheck-fid-run-review"
import {
  MetadataKeyValueCard,
  ProcessingParametersCard,
} from "@/components/spectracheck/spectracheck-processing-parameters-card"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { SpectrumResultsFullscreen } from "@/components/spectracheck/spectracheck-fullscreen-results"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  describeReferenceMode,
  displayedDatasetName,
  extractPeaksFromPayload,
  extractReferenceReadout,
  extractRawFidArchiveFacts,
  extractSpectrumXY,
  isRecord,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { useStableXY } from "@/components/spectracheck/use-stable-xy"
import { isMissingNmrEndpoint, RAW_FID_BACKEND_MSG } from "@/components/spectracheck/spectracheck-nmr-endpoint-messages"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { SpectraCheckAnalysisPanels } from "@/components/spectracheck/spectracheck-analysis-panels"
import { SpectraCheckRunTile } from "@/components/spectracheck/spectracheck-run-tile"
import {
  DetectionResultsPanel,
  GsdAnalysisControls,
  adaptLegacyRawFidResult,
  type AnalysisBackendChoice,
  type GSDLevel,
  type NMRRawFIDPreviewResponse,
  type SpectrumGSDAnalyzeRequest,
  type SpectrumGSDAnalyzeResult,
} from "@/components/spectracheck/gsd-analysis-ui"
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

/* Every id here must exist in the backend's preset alias table, or the run is
   refused and the user gets no spectrum. "Imported parameters" used to sit in
   this list with no alias behind it — see RawFidPreset for why it is not simply
   aliased to `custom`. */
const PRESETS = [
  { value: "safe_automatic", label: "Safe automatic" },
  { value: "no_baseline_correction", label: "No baseline correction" },
  { value: "no_phase_correction", label: "No phase correction" },
] as const satisfies ReadonlyArray<{ value: RawFidPreset; label: string }>

const EMPTY_SPECTRUM_PEAKS: never[] = []

// Signing out (or a test starting fresh) must not leave a run holding the claim — nothing would
// ever release it, and every later run would decline to start. The run itself lives in
// raw-fid-batch.ts so the workspace can tear it down on unmount without importing this section.
registerSpectraCheckRuntimeReset(abortRawFidBatchRun)

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
    prompt_guidance_unavailable: "Cross-check guidance unavailable",
    active_peak_count_unavailable: "Active peak count unavailable",
    review: "Review",
  }
  return labels[status] ?? status.replaceAll("_", " ")
}

/**
 * Phase/baseline algorithm names arrive as stored tokens ("regions_analysis").
 * Show readable prose; the stored value is never rewritten.
 */
function humanizeMethodName(value: string | null): string {
  const trimmed = value?.trim()
  if (!trimmed) return "Not reported"
  const spaced = trimmed.replaceAll("_", " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
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
  const { state, update, updateWith } = useRawFidTabState()
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
    selectedFile,
    selectedFileName,
    advancedOpen,
    batchItems,
    batchMode,
    batchActiveId,
    batchRunning,
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

  /**
   * Elapsed seconds while a raw-FID read/process is in flight.
   *
   * These two buttons call the SYNCHRONOUS endpoints, and a first-time analysis of a new spectrum
   * genuinely costs ~5-6 s (~12 s once a structure is supplied, measured on localhost). A static
   * "Reading…"/"Processing…" for that long reads as a hang, so show the clock ticking. This is
   * honest feedback only — it does not claim progress toward a known total.
   */
  const rawFidBusy = previewLoading || processLoading
  const [elapsedMs, setElapsedMs] = useState(0)
  useEffect(() => {
    if (!rawFidBusy) {
      setElapsedMs(0)
      return
    }
    const startedAt = Date.now()
    setElapsedMs(0)
    const id = setInterval(() => setElapsedMs(Date.now() - startedAt), 200)
    return () => clearInterval(id)
  }, [rawFidBusy])
  const elapsedLabel = elapsedMs >= 1000 ? ` ${Math.floor(elapsedMs / 1000)}s` : ""
  const setSelectedFile = useCallback((v: File | null) => update({ selectedFile: v }), [update])
  const setSelectedFileName = useCallback(
    (v: string | null) => update({ selectedFileName: v }),
    [update],
  )
  const setAdvancedOpen = useCallback((v: boolean) => update({ advancedOpen: v }), [update])

  // ── GSD-Prompt-3 (experimental, opt-in) — additive only. Default must
  // stay `legacy` so tenants who never touch the selector keep the
  // existing /nmr/raw-fid/process pipeline unchanged.
  /* GSD output, its settings and the instrument readout live in tab state, not
     here: a tab switch unmounts this component while the spectrum survives in
     the provider, so local state left the user looking at their chart with the
     analysis under it gone. */
  const analysisBackend = state.analysisBackend as AnalysisBackendChoice
  const setAnalysisBackend = useCallback(
    (v: AnalysisBackendChoice) => update({ analysisBackend: v }),
    [update],
  )
  const gsdLevel = state.gsdLevel as GSDLevel
  const setGsdLevel = useCallback((v: GSDLevel) => update({ gsdLevel: v }), [update])
  const gsdResult = state.gsdResult as SpectrumGSDAnalyzeResult | null
  const setGsdResult = useCallback(
    (v: SpectrumGSDAnalyzeResult | null) => update({ gsdResult: v }),
    [update],
  )
  const [gsdError, setGsdError] = useState("")
  const [gsdLoading, setGsdLoading] = useState(false)
  // GSD-scoped solvent override, initialized from the session-level
  // solvent prop. Canonicalized against the catalog when it arrives.
  const gsdSolvent = state.gsdSolvent || solvent
  const setGsdSolvent = useCallback((v: string) => update({ gsdSolvent: v }), [update])

  /**
   * A GSD analysis belongs to the dataset it was run on.
   *
   * Moving to another row in the queue swaps the whole results surface, and the experimental GSD
   * panels below it are separate state — left alone, they would keep showing the previous
   * dataset's peaks, multiplets and integrals beside a different spectrum. Attributing one
   * dataset's analysis to another is the worst thing this surface could do, so the GSD output is
   * cleared with the selection and the reviewer re-runs it deliberately.
   */
  /**
   * The payload the current GSD output was actually computed from.
   *
   * Keying the reset on the queue SELECTION was not enough: the results surface also changes when
   * the user attaches another archive and presses Process, which leaves `batchActiveId` untouched.
   * That let dataset A's peak table, multiplets and J-couplings sit under dataset B's spectrum —
   * and the integration panel, which re-fires on a trace change, would post A's peaks against B's
   * trace and print the region integrals beneath B. Identity of the analyzed payload is the thing
   * that actually has to match, so that is what is tracked.
   */
  const gsdSourceRef = useRef<unknown>(null)
  const gsdSourcePayload = processResult ?? previewResult

  /**
   * What the surface is showing RIGHT NOW, tracked during render.
   *
   * The reset effects above only run when something changes; they cannot police a request that is
   * still in the air. An experimental analysis takes seconds, and the reviewer can pick another
   * queue row while it runs — at which point the effects correctly clear, and then the late
   * response arrives and re-binds itself to the dataset that has already left the screen. Nothing
   * fires again after that, because from the effects' point of view nothing has changed since.
   *
   * Assigned in render rather than in an effect so a result can be checked against it the moment
   * it resolves, with no dependency on effect ordering.
   */
  const displayedPayloadRef = useRef<unknown>(gsdSourcePayload)
  displayedPayloadRef.current = gsdSourcePayload

  useEffect(() => {
    if (gsdSourceRef.current === null) return
    if (gsdSourceRef.current === gsdSourcePayload) return
    gsdSourceRef.current = null
    setGsdResult(null)
    setGsdError("")
  }, [gsdSourcePayload])

  // A selection change swaps the surface even when the payload happens to be identical (both
  // null, say), so the selection remains a reset trigger in its own right.
  useEffect(() => {
    gsdSourceRef.current = null
    setGsdResult(null)
    setGsdError("")
  }, [batchActiveId])

  const sendTabLink = useSpectraCheckTabLink()

  // dragOver is purely ephemeral visual state — fine to reset on remount.
  const [dragOver, setDragOver] = useState(false)
  /** Vendor-folder drop: zip client-side so the upload contract stays "one archive". */
  const folderRef = useRef<HTMLInputElement>(null)
  const [folderBusy, setFolderBusy] = useState<string | null>(null)
  const [folderDetection, setFolderDetection] = useState<VendorFolderDetection | null>(null)
  const [folderError, setFolderError] = useState<string | null>(null)

  /**
   * What the instrument recorded, read out of the dropped dataset's own acqus/procpar before
   * anything is uploaded. Null until something readable lands.
   */
  const acquisition = state.acquisition
  const setAcquisition = useCallback(
    (v: AcquisitionSummary | null) => update({ acquisition: v }),
    [update],
  )

  /**
   * Reflect a drop's own acquisition parameters into the setup form.
   *
   * Only the NUCLEUS is written back, and only when every readable experiment agrees on a value
   * the toggle can express. That is not timidity, it is matching the analyzer: `NUC1`/`tn` already
   * override the requested nucleus server-side, so moving the toggle reports a decision that has
   * effectively already been made. The solvent deliberately is NOT written back — there the
   * request wins over the file, so quietly swapping it would make the form disagree with what
   * actually runs. And a folder holding both a 1H and a 13C experiment has no single right answer,
   * so the toggle is left alone and the disagreement is shown instead.
   */
  const applyDetectedAcquisition = useCallback(
    (facts: readonly (VendorAcquisitionFacts | null)[]) => {
      const summary = summarizeAcquisition(facts)
      setAcquisition(summary.readCount > 0 ? summary : null)
      if (isOfferedNucleus(summary.nucleus)) setNucleus(summary.nucleus)
    },
    [setNucleus],
  )
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

  // ── Multi-dataset queue ────────────────────────────────────────────────
  //
  // Every queue write goes through `updateWith`, which derives the patch from the LATEST state.
  // That matters because the runner is a long async loop: this section unmounts whenever the user
  // switches tab (Radix drops inactive tabs), so a loop started before a switch outlives the
  // component that started it. A patch built from that dead render's snapshot would quietly undo
  // whatever happened while it was away.
  const [batchNotice, setBatchNotice] = useState<string | null>(null)

  const patchBatchItem = useCallback(
    (id: string, patch: Partial<RawFidBatchItem>) => {
      updateWith((prev) => ({
        // A dataset removed mid-run simply is not found, and the patch becomes a no-op.
        batchItems: prev.batchItems.map((item) => (item.id === id ? { ...item, ...patch } : item)),
      }))
    },
    [updateWith],
  )

  const addBatchItems = useCallback(
    (created: RawFidBatchItem[]) => {
      if (created.length === 0) return
      updateWith((prev) => {
        const room = RAW_FID_BATCH_MAX_ITEMS - prev.batchItems.length
        if (room <= 0) {
          setFolderError(
            `The queue already holds ${RAW_FID_BATCH_MAX_ITEMS} datasets. Clear some before adding more.`,
          )
          return {}
        }
        const admitted = created.slice(0, room)
        if (admitted.length < created.length) {
          setFolderError(
            `Added ${admitted.length} of ${created.length} datasets — the queue holds ${RAW_FID_BATCH_MAX_ITEMS} at a time.`,
          )
        }
        return { batchItems: [...prev.batchItems, ...admitted] }
      })
    },
    [updateWith],
  )

  /**
   * Bring a finished dataset into the analysis surface below.
   *
   * The queue does not own a second results view — it feeds the one that already exists. Writing
   * the item's response into the ordinary result state lights up every panel (evidence, peaks,
   * multiplets, review) for that dataset, and pointing `selectedFile` at it means the
   * single-dataset controls act on the row the reviewer is looking at.
   */
  const selectionPatchFor = useCallback((prev: RawFidTabState, id: string): Partial<RawFidTabState> => {
    const item = prev.batchItems.find((entry) => entry.id === id)
    if (!item || item.status !== "done") return {}
    const asProcess = item.mode === "process"
    return {
      batchActiveId: id,
      selectedFile: item.file,
      selectedFileName: item.label,
      activeResultMode: asProcess ? "process" : "preview",
      processResult: asProcess ? item.result : null,
      previewResult: asProcess ? null : item.result,
      processError: "",
      previewError: "",
      previewSpectrum: null,
      previewSpectrumError: "",
      previewSpectrumLoading: false,
    }
  }, [])

  const selectBatchItem = useCallback(
    (id: string) => {
      updateWith((prev) => selectionPatchFor(prev, id))
    },
    [selectionPatchFor, updateWith],
  )

  /**
   * Accept a dropped/selected vendor dataset FOLDER (Bruker, Varian/Agilent) the way MestReNova
   * does — except that a folder holding several experiments now becomes several datasets rather
   * than one.
   *
   * That is not just convenience. The analyzer keeps only the single best-scoring dataset in an
   * archive and picks it by path depth and name order, so every other experiment in a combined
   * archive was silently invisible. One archive per experiment is what makes them all real.
   */
  async function attachVendorFolder(entries: Awaited<ReturnType<typeof vendorFolderEntriesFromDataTransfer>>) {
    setFolderError(null)
    setFolderDetection(null)
    if (entries.length === 0) return
    const detection = detectVendorDataset(entries)
    setFolderDetection(detection)
    if (!detection.usable) {
      setFolderError(detection.reason ?? "That folder does not contain a readable dataset.")
      return
    }
    const bundles = splitVendorFolderByExperiment(entries)
    if (bundles.length === 0) {
      setFolderError(detection.reason ?? "That folder does not contain a readable dataset.")
      return
    }
    try {
      const created: RawFidBatchItem[] = []
      const detectedFacts: (VendorAcquisitionFacts | null)[] = []
      for (let index = 0; index < bundles.length; index++) {
        const bundle = bundles[index]
        const label = bundle.dir || bundle.archiveName
        // Read this experiment's own parameter file. Done per bundle rather than once for the
        // folder because the experiments in one folder are routinely different nuclei — reading a
        // single acqus and applying it to all of them is the mistake this exists to prevent.
        const facts = await sniffExperimentAcquisition(bundle.entries)
        detectedFacts.push(facts)
        // Check the size rules BEFORE packaging. Zipping an experiment we already know will be
        // refused wastes the one part of this that is slow, and can be enough to exhaust the tab.
        const preflight = preflightRawFidArchive({
          name: bundle.archiveName,
          size: Math.max(1, bundle.totalBytes),
          uncompressedBytes: bundle.totalBytes,
          fileCount: bundle.fileCount,
        })
        if (!preflight.ok) {
          created.push(
            createBlockedRawFidBatchItem({
              label,
              reason: preflight.reason,
              sourceDir: bundle.dir || null,
              fileCount: bundle.fileCount,
              uncompressedBytes: bundle.totalBytes,
              detected: facts,
            }),
          )
          continue
        }
        setFolderBusy(
          bundles.length > 1
            ? `Packaging ${label} — ${index + 1} of ${bundles.length}…`
            : `Packaging ${bundle.fileCount} files…`,
        )
        // One at a time: a folder of twenty experiments must never have twenty archives being
        // built at once.
        const archive = await zipVendorFolder(bundle.entries, { name: bundle.archiveName })
        created.push(
          createRawFidBatchItem({
            file: archive,
            label,
            sourceDir: bundle.dir || null,
            fileCount: bundle.fileCount,
            uncompressedBytes: bundle.totalBytes,
            detected: facts,
          }),
        )
      }
      addBatchItems(created)
      applyDetectedAcquisition(detectedFacts)
      const firstRunnable = created.find((item) => item.status === "queued")
      if (firstRunnable) attachFile(firstRunnable.file)
    } catch (err) {
      setFolderError(err instanceof Error ? err.message : "Could not package that folder.")
    } finally {
      setFolderBusy(null)
    }
  }

  /** Admit archives picked or dropped directly, one queue row each. */
  const enqueueArchives = useCallback(
    (files: File[]) => {
      if (files.length === 0) return
      const created = files.map((file) => createRawFidBatchItem({ file }))
      addBatchItems(created)
      const firstRunnable = created.find((item) => item.status === "queued")
      if (firstRunnable) {
        attachFile(firstRunnable.file)
      } else {
        // Nothing usable arrived. Leave the picker holding a file the analysis would only
        // refuse — the queue rows already say why each one was turned away.
        clearSelectedFile()
      }

      // Read each archive's parameters AFTER admitting it, not before. Opening a zip is the one
      // slow step here, and making the rows wait on it would trade an instant queue for a stall
      // on a readout that is only a hint. The rows appear now and fill in when the read lands.
      void (async () => {
        const facts = await Promise.all(
          created.map((item) =>
            sniffArchiveAcquisition(item.file).catch(() => null),
          ),
        )
        created.forEach((item, i) => {
          if (facts[i]) patchBatchItem(item.id, { detected: facts[i] })
        })
        // Nothing readable — a folder of .tar.gz, or archives past the sniff ceiling. Leave the
        // form exactly as the chemist set it rather than clearing a readout it never had.
        if (facts.some((f) => f != null)) applyDetectedAcquisition(facts)
      })()
    },
    // attachFile / clearSelectedFile are function declarations in this component body — they are
    // re-created each render but never close over anything that changes their behaviour.
    [addBatchItems, applyDetectedAcquisition, patchBatchItem],
  )

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


  // NOTE: raw-FID BACKGROUND JOBS were removed here. The server registers the
  // nmr_raw_fid_preview/process job types but has no execution adapter for them, so every
  // such job was created already failed — after uploading the entire archive to /files/upload.
  // The direct Preview/Process calls below are the working path. Restore from git history if
  // the backend gains an adapter.

  /**
   * Everything a request carries besides the archive itself.
   *
   * Captured as a value so a queue run can freeze it once at the start: these are read from
   * props and tab state, so a control nudged while twenty datasets are still to go would
   * otherwise apply to some of them and not others, with nothing on screen saying so.
   */
  /* vendor/preset are the wire unions, not bare strings: every raw FID request
     is built here, so widening them back to `string` is what would let a value
     the routes reject reach the wire again. */
  type RawFidRequestSettings = {
    sampleId: string
    solvent: string
    nucleus: "1H" | "13C"
    vendor: RawFidVendor
    preset: RawFidPreset
    compoundClass: CompoundClassValue
    candidatesText: string
    protonText: string
    carbonText: string
  }

  function currentRequestSettings(): RawFidRequestSettings {
    return { sampleId, solvent, nucleus, vendor, preset, compoundClass, candidatesText, protonText, carbonText }
  }

  function appendSharedSessionGuidance(fd: FormData, settings: RawFidRequestSettings = currentRequestSettings()) {
    const ccParam = compoundClassForRequest(settings.compoundClass)
    if (ccParam) fd.append("compound_class", ccParam)
    // Shared session inputs — drives peak enrichment + evidence panels on
    // the response (parity with /nmr/processed/analyze).
    const cand = settings.candidatesText.trim()
    if (cand) fd.append("candidates_text", cand)
    const sharedProton = settings.protonText.trim()
    if (sharedProton) fd.append("proton_nmr_text", sharedProton)
    const sharedCarbon = settings.carbonText.trim()
    if (sharedCarbon) fd.append("carbon13_text", sharedCarbon)
  }

  function buildFormData(
    file: File,
    withProcess: boolean,
    settings: RawFidRequestSettings = currentRequestSettings(),
  ) {
    const fd = new FormData()
    fd.append("file", file)
    fd.append("sample_id", settings.sampleId)
    fd.append("solvent", settings.solvent)
    fd.append("nucleus", settings.nucleus)
    fd.append("vendor", settings.vendor)
    if (withProcess) {
      fd.append("processing_preset", settings.preset)
      fd.append("preserve_raw", "true")
    } else {
      fd.append("processing_preset", "safe_automatic")
      fd.append("include_spectrum", "true")
    }
    appendSharedSessionGuidance(fd, settings)
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

  /**
   * Record a single-tile run on the queue row it came from.
   *
   * Dropping an archive enqueues it, but the Preview/Process tiles used to write only this
   * section's own result state — the queue row sat at "Queued" after a successful run, and the
   * Evidence Bench (which shows DONE queue rows) stayed empty even though the spectrum was
   * processed. Processing must mean the same thing whichever button ran it. File identity is the
   * join: every path that attaches a file created its queue item from the same File object.
   */
  const recordSingleRunOnQueue = useCallback(
    (file: File, mode: RawFidBatchMode, result: unknown, durationMs: number) => {
      updateWith((prev) => {
        const item = prev.batchItems.find((entry) => entry.file === file)
        if (!item) return {}
        return {
          batchItems: prev.batchItems.map((entry) =>
            entry.id === item.id
              ? { ...entry, status: "done" as const, mode, result, error: null, durationMs }
              : entry,
          ),
          // Adopt the row as the shared selection only when nothing is selected — stealing an
          // existing selection would also reset the per-dataset analysis panels.
          ...(prev.batchActiveId == null ? { batchActiveId: item.id } : {}),
        }
      })
    },
    [updateWith],
  )

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
    const startedAt = Date.now()
    try {
      const fd = buildFormData(file, false)
      const data = await apiFetch<unknown>("/nmr/raw-fid/preview", { method: "POST", body: fd })
      setPreviewResult(data)
      // The tile ran the same endpoint the queue's Quick scan mode runs — the row records it.
      recordSingleRunOnQueue(file, "scan", data, Date.now() - startedAt)
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
    const startedAt = Date.now()
    try {
      const fd = buildFormData(file, true)
      const data = await apiFetch<unknown>("/nmr/raw-fid/process", { method: "POST", body: fd })
      setProcessResult(data)
      recordSingleRunOnQueue(file, "process", data, Date.now() - startedAt)
      pushDev("raw_fid_process", data)
    } catch (err) {
      if (isMissingNmrEndpoint(err)) setProcessError(RAW_FID_BACKEND_MSG)
      else setProcessError(formatApiError(err, "Raw FID process failed"))
    } finally {
      setProcessLoading(false)
    }
  }

  /**
   * Work the queue — ONE DATASET AT A TIME.
   *
   * Not a throttle we chose: the analysis runs inline on the server's request loop, so several at
   * once do not overlap. They would queue anyway, hold the whole service while they did, and
   * finish no sooner. Sequential is both the honest shape and the fast one.
   *
   * Settings are frozen for the whole run, each dataset gets its own cancellation handle, and a
   * refusal that would repeat identically for every remaining dataset ends the run instead of
   * failing fifty rows one by one.
   */
  async function runBatchItems(plan: { id: string; file: File }[], mode: RawFidBatchMode) {
    const generation = beginRawFidBatchRun()
    if (generation == null) return
    setBatchNotice(null)
    update({ batchRunning: true })
    // Frozen for the whole run: the plan carries each dataset's own archive, and these settings
    // apply to all of them, so a control nudged halfway through cannot split the batch in two.
    const settings = currentRequestSettings()
    try {
      for (const step of plan) {
        // Also false once this run has been abandoned — the workspace unmounted mid-batch, so
        // every write from here lands in state nobody will ever see. Stop rather than spend the
        // remaining uploads on it.
        if (!isRawFidBatchRunCurrent(generation)) break

        // The plan was fixed when the run started; the queue was not. A dataset removed since
        // then must not be uploaded, because uploading it also vaults it — "removed" has to mean
        // removed, not merely hidden.
        if (isWithdrawnFromRawFidBatchRun(step.id)) continue

        const controller = new AbortController()
        rawFidBatchRun.controller = controller
        const startedAt = Date.now()
        patchBatchItem(step.id, { status: "running", startedAt, durationMs: null, error: null })

        try {
          const data = await apiFetch<unknown>(
            mode === "process" ? "/nmr/raw-fid/process" : "/nmr/raw-fid/preview",
            {
              method: "POST",
              body: buildFormData(step.file, mode === "process", settings),
              signal: controller.signal,
            },
          )
          updateWith((prev) => {
            const next: Partial<RawFidTabState> = {
              batchItems: prev.batchItems.map((item) =>
                item.id === step.id
                  ? {
                      ...item,
                      status: "done" as const,
                      mode,
                      result: data,
                      error: null,
                      durationMs: Date.now() - startedAt,
                    }
                  : item,
              ),
            }
            // Show the reviewer something as soon as there is something to show — but never
            // steal the surface out from under a row they chose themselves.
            if (prev.batchActiveId) return next
            return { ...next, ...selectionPatchFor({ ...prev, ...next } as RawFidTabState, step.id) }
          })
          // One snapshot per dataset. The developer panel cannot drop keys, so a long queue must
          // not keep adding to it.
          pushDev(`raw_fid_batch:${step.id}`, data)
        } catch (err) {
          const message = isMissingNmrEndpoint(err)
            ? RAW_FID_BACKEND_MSG
            : formatApiError(err, "That dataset could not be analyzed.")
          const verdict = classifyRawFidBatchFailure(err, message)
          patchBatchItem(step.id, {
            status: verdict.status,
            error: verdict.message,
            durationMs: Date.now() - startedAt,
          })
          if (verdict.stopsRun || isModuleNotIncludedError(err) || isMissingNmrEndpoint(err)) {
            setBatchNotice(`${verdict.message} The datasets after it were left untouched.`)
            break
          }
        } finally {
          if (rawFidBatchRun.controller === controller) rawFidBatchRun.controller = null
        }
      }
    } finally {
      // BOTH halves are gated on still holding the claim. Releasing the claim without also
      // gating the flag was a half-fix: an abandoned loop finishing late would clear
      // `batchRunning` for the run the user had since started, so the queue would read as idle
      // while it was still working — and the Run button it offered would be declined silently.
      if (endRawFidBatchRun(generation)) update({ batchRunning: false })
    }
  }

  function runBatchAll() {
    void runBatchItems(
      batchItems.filter(isRawFidBatchItemRunnable).map((item) => ({ id: item.id, file: item.file })),
      batchMode,
    )
  }

  function runBatchOne(id: string) {
    const item = batchItems.find((entry) => entry.id === id)
    if (!item || !isRawFidBatchItemRunnable(item)) return
    void runBatchItems([{ id: item.id, file: item.file }], batchMode)
  }

  function stopBatch() {
    stopRawFidBatchRun()
  }

  /**
   * Remove a dataset from the queue — and actually stop it.
   *
   * Dropping the row alone was not enough. The run works from a plan captured when it started, so
   * a removed dataset was still uploaded and analyzed, and both analysis routes vault the archive.
   * The reviewer's "remove" would have silently stored the very data they were withdrawing. The
   * in-flight one is aborted; the rest are skipped by the membership check in the runner.
   */
  function removeBatchItem(id: string) {
    // Tell the RUN, not just the list: the run holds its own plan and outlives this component.
    withdrawFromRawFidBatchRun(id)
    if (batchRunning && batchItems.some((item) => item.id === id && item.status === "running")) {
      rawFidBatchRun.controller?.abort()
    }
    updateWith((prev) => ({
      batchItems: prev.batchItems.filter((item) => item.id !== id),
      ...(prev.batchActiveId === id ? { batchActiveId: null } : {}),
    }))
  }

  function clearBatch() {
    for (const item of batchItems) withdrawFromRawFidBatchRun(item.id)
    stopBatch()
    update({ batchItems: [], batchActiveId: null })
    setBatchNotice(null)
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
    // Which payload this analysis will belong to, worked out the same way the reset effect above
    // derives it. Recorded only on success, so a failed run cannot claim a dataset.
    let analyzedPayload: unknown = processResult ?? previewResult
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
        // The auto-fetch becomes the displayed payload, so it is what this analysis belongs to.
        // The ref is moved here too rather than waiting for the re-render, so the commit check
        // below cannot mistake this run's own write for the surface moving under it.
        if (!processResult) {
          analyzedPayload = previewData
          displayedPayloadRef.current = previewData
        }
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
      // The surface may have moved while this was in the air — the reviewer picked another queue
      // row, or processed a different archive. Storing the result anyway would re-bind it to a
      // dataset that is no longer shown, and the reset effects would never fire again because
      // from their point of view nothing changed. Drop it instead; it belongs to nothing on screen.
      if (displayedPayloadRef.current !== analyzedPayload) {
        pushDev("raw_fid_gsd_analyze_discarded", data)
        return
      }
      // Bind the analysis to the payload it was computed from BEFORE storing it, so the reset
      // effect can tell "still the same dataset" from "the surface moved on".
      gsdSourceRef.current = analyzedPayload
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
    clearBatch()
    setFolderDetection(null)
    setFolderError(null)
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
      ? "Spectrum, processing parameters, and acquisition metadata from the processed FID."
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
  /* Read through the shared reader, which knows the nested shape the response
     models actually declare. These three tiles used to read `raw_file_sha256`,
     `spectral_width_hz` and `time_domain_points` off the top level — names
     `SpectrumPreviewReport` (extra="forbid") does not declare, so they could
     never arrive and all three tiles were permanently blank. */
  const archiveFacts = extractRawFidArchiveFacts(displayPayload)
  const referencing = extractReferenceReadout(displayPayload)
  const sha = archiveFacts.sha
  const vendorDetected =
    meta && (typeof meta.vendor_detected === "string" ? meta.vendor_detected : typeof meta.vendor === "string" ? meta.vendor : null)
  const nucleusMeta = meta && typeof meta.nucleus === "string" ? meta.nucleus : null
  const resolvedNucleus = nucleusMeta === "13C" || nucleusMeta === "1H" ? nucleusMeta : nucleus
  const sw = archiveFacts.sweepWidthHz
  const td = archiveFacts.fidPoints
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
        description="Set sample metadata, choose nucleus and vendor, then drop an instrument folder or archives (.zip / .tar.gz / .tgz). Drop as many as you like — each experiment becomes its own dataset. Every original archive is preserved unchanged."
        className="min-w-0"
      >
        <div className="space-y-5">
          {/* Routine path: nucleus, vendor, preset. Everything else — sample
              identity, the read-only solvent, and the experimental GSD backend
              controls — sits behind a disclosure, so a normal run needs the
              three controls that actually change the result. */}
          {/* Nucleus + Vendor pill toggles */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Nucleus</Label>
              {/* Selection was conveyed by background colour alone — no ARIA
                  state at all, so a screen-reader user could not tell which
                  nucleus was active. */}
              <div role="group" aria-label="Nucleus" className="inline-flex rounded-lg border border-input bg-background p-0.5">
                {(["1H", "13C"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={nucleus === option}
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
              <div role="group" aria-label="Vendor" className="inline-flex flex-wrap rounded-lg border border-input bg-background p-0.5">
                {([
                  { value: "auto", label: "Auto" },
                  { value: "bruker", label: "Bruker" },
                  // Wire value, not a display choice: the routes accept
                  // "agilent_varian" and reject "agilent" outright.
                  { value: "agilent_varian", label: "Agilent / Varian" },
                ] as const satisfies ReadonlyArray<{ value: RawFidVendor; label: string }>).map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={vendor === option.value}
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

          {/* Processing preset — a routine control, not an advanced one. It
              decides what the Process action actually does, so it belongs
              beside nucleus and vendor rather than behind a disclosure. */}
          <div className="space-y-1.5">
            <Label htmlFor="raw-preset" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Processing preset
            </Label>
            <select
              id="raw-preset"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 font-mono text-sm shadow-xs outline-none sm:max-w-sm"
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
              Used for full processing; preview uses the locked quick-spectrum preset.
            </p>
          </div>

          {/* What the instrument itself recorded — read from the dropped dataset, before upload. */}
          {acquisition ? (
            <div
              data-testid="raw-fid-acquisition-readout"
              className="rounded-lg border border-[color:var(--mt-teal)]/30 bg-[color:var(--mt-teal-soft)]/30 px-3 py-2.5"
            >
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Read from the instrument file
                {acquisition.unreadCount > 0 ? (
                  // Say so rather than letting a partial readout look like a complete one.
                  <span className="ml-1 font-normal normal-case tracking-normal">
                    · {acquisition.readCount} of {acquisition.readCount + acquisition.unreadCount}{" "}
                    datasets
                  </span>
                ) : null}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs">
                <span>
                  <span className="text-muted-foreground">Nucleus </span>
                  {acquisition.nuclei.length > 0 ? acquisition.nuclei.join(" + ") : "—"}
                </span>
                <span>
                  <span className="text-muted-foreground">Solvent </span>
                  {acquisition.solvents.length > 0 ? acquisition.solvents.join(" + ") : "not recorded"}
                </span>
                <span>
                  <span className="text-muted-foreground">Vendor </span>
                  {acquisition.vendor === "bruker"
                    ? "Bruker"
                    : acquisition.vendor === "varian"
                    ? "Varian/Agilent"
                    : "mixed"}
                </span>
                {acquisition.fieldMhz != null ? (
                  <span>
                    <span className="text-muted-foreground">Field </span>
                    {acquisition.fieldMhz.toFixed(2)} MHz
                  </span>
                ) : null}
              </div>

              {/*
                Everything below is a DISAGREEMENT between the file and the form. Each one names
                which side the analysis will actually follow, because that differs per field and
                guessing wrong is the whole risk this readout exists to remove.
              */}
              <div className="mt-2 space-y-1 text-[11px] leading-relaxed text-muted-foreground">
                {acquisition.mixedNuclei ? (
                  <p>
                    This drop holds {acquisition.nuclei.join(" and ")} experiments, so the toggle
                    above cannot describe all of them. Each dataset is read with the nucleus
                    recorded in its own file.
                  </p>
                ) : null}

                {acquisition.nucleus && !isOfferedNucleus(acquisition.nucleus) ? (
                  <p>
                    This dataset was acquired on {acquisition.nucleus}. This reader is built for 1H
                    and 13C, so the results may not be interpretable.
                  </p>
                ) : null}

                {/*
                  Solvent is the one field where the FORM wins over the file — re-running an old
                  dataset in a different solvent is a correction, not a contradiction. So this
                  never silently swaps the value; it says which one will be used.
                */}
                {acquisition.solvent && solvent.trim() && acquisition.solvent !== solvent.trim() ? (
                  <p>
                    The instrument recorded {acquisition.solvent}. This session is set to{" "}
                    {solvent.trim()}, and that is what the analysis will use — solvent selects the
                    referencing window and the impurity library, so it is worth confirming.
                  </p>
                ) : null}

                {acquisition.solvent && !solvent.trim() ? (
                  <p>
                    No solvent is set for this session, so the analysis will use the{" "}
                    {acquisition.solvent} recorded in the file.
                  </p>
                ) : null}

                {acquisition.vendor &&
                vendor !== "auto" &&
                vendor !== (acquisition.vendor === "bruker" ? "bruker" : "agilent_varian") ? (
                  <p>
                    Vendor is set to {vendor === "bruker" ? "Bruker" : "Agilent / Varian"}, but these files
                    are{" "}
                    {acquisition.vendor === "bruker" ? "Bruker" : "Varian/Agilent"}. Switch to Auto
                    unless you meant to override it.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          {/* Drop-zone file picker */}
          <div className="space-y-1.5">
            <Label htmlFor="raw-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Raw FID archive
            </Label>
            {/* Drop zone is a div + onClick (see processed section for rationale). */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Drop raw FID archive or instrument folder, or press Enter to browse"
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
                // A dropped DIRECTORY is invisible to dataTransfer.files — it only shows up via
                // webkitGetAsEntry. Probe for one SYNCHRONOUSLY so an ordinary archive drop stays
                // synchronous (no behaviour change); only a real folder takes the async path.
                const dt = e.dataTransfer
                if (dataTransferHasDirectory(dt)) {
                  // A drop can carry folders AND loose archives together. Reading only the
                  // folders silently discarded the archives, under copy that invites dropping
                  // both — so the plain files are captured here before the async folder walk.
                  //
                  // Filtered to things that are actually archives, because `dataTransfer.files`
                  // ALSO lists the dropped directory itself. Taking it verbatim added a bogus
                  // "Not accepted" row for the folder and then cleared the archive the folder
                  // walk had just attached.
                  const alongside = Array.from(dt.files ?? []).filter((file) =>
                    isRawFidArchiveFilename(file.name),
                  )
                  void (async () => {
                    try {
                      const entries = await vendorFolderEntriesFromDataTransfer(dt)
                      if (entries.length > 0) await attachVendorFolder(entries)
                    } catch (err) {
                      setFolderError(
                        err instanceof Error ? err.message : "Could not read that folder.",
                      )
                    }
                    if (alongside.length > 0) enqueueArchives(alongside)
                  })()
                  return
                }
                const dropped = Array.from(dt.files ?? [])
                if (dropped.length > 0) {
                  setFolderDetection(null)
                  setFolderError(null)
                  enqueueArchives(dropped)
                }
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
                {folderBusy
                  ? folderBusy
                  : batchItems.length > 0
                    ? `${batchItems.length} dataset${batchItems.length === 1 ? "" : "s"} ready`
                    : selectedFileName
                      ? "Archive ready"
                      : dragOver
                        ? "Drop to attach"
                        : "Drop instrument folders or archives"}
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Bruker / Varian folders · ZIP · TAR.GZ · TGZ · several at once
              </p>
              <p className="mt-1 text-[10px] text-muted-foreground">
                Packaged in your browser — nothing leaves this machine until you start the analysis.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                disabled={folderBusy != null}
                onClick={() => folderRef.current?.click()}
              >
                Choose folder…
              </Button>
              <span className="text-[10px] text-muted-foreground">
                or click the box above to pick one or more archive files
              </span>
            </div>
            {/* Folder picker — webkitdirectory is the click-to-browse twin of a directory drop. */}
            <input
              id="raw-folder"
              ref={folderRef}
              type="file"
              className="sr-only"
              // @ts-expect-error non-standard but universally supported directory picker attributes
              webkitdirectory=""
              directory=""
              multiple
              onChange={(e) => {
                const files = e.target.files
                if (files && files.length > 0) {
                  void attachVendorFolder(vendorFolderEntriesFromFileList(files))
                }
                // Allow re-picking the same folder.
                e.target.value = ""
              }}
            />
            {folderError ? (
              <p role="alert" className="text-[11px] text-destructive">
                {folderError}
              </p>
            ) : null}
            {folderDetection?.usable ? (
              <div
                className="rounded-md border px-3 py-2 text-[11px]"
                style={{ borderLeft: "3px solid var(--mt-teal)" }}
                role="status"
              >
                <p className="font-medium text-foreground">
                  {folderDetection.kind === "bruker"
                    ? "Bruker dataset"
                    : folderDetection.kind === "varian"
                      ? "Varian/Agilent dataset"
                      : "Vendor dataset"}{" "}
                  · {folderDetection.experiments.length} experiment
                  {folderDetection.experiments.length === 1 ? "" : "s"}
                </p>
                <p className="text-muted-foreground">
                  {folderDetection.fileCount} files · {formatBytes(folderDetection.totalBytes)} ·{" "}
                  {folderDetection.experiments.length === 1
                    ? "packaged as one dataset."
                    : `packaged as ${folderDetection.experiments.length} separate datasets, one per experiment.`}
                </p>
                {folderDetection.experiments.length > 1 ? (
                  <p className="mt-0.5 text-muted-foreground">
                    Contains{" "}
                    <span className="font-mono text-foreground">
                      {folderDetection.experiments
                        .slice(0, 6)
                        .map((x) => x.dir.split("/").pop() || x.dir)
                        .join(", ")}
                      {folderDetection.experiments.length > 6 ? " …" : ""}
                    </span>
                    . Each is queued and analyzed on its own.
                    {folderDetection.experiments.length > RAW_FID_BATCH_MAX_ITEMS
                      ? ` The queue holds ${RAW_FID_BATCH_MAX_ITEMS} at a time, so the rest are left for a second pass.`
                      : ""}
                  </p>
                ) : null}
                {folderDetection.skippedDirs.length > 0 ? (
                  // Named, not merely counted: "2 skipped" leaves the chemist wondering which two.
                  // These are usually 2D experiments (ser, no fid), which this 1D path cannot read.
                  <p className="mt-0.5 text-muted-foreground" data-testid="raw-fid-folder-skipped">
                    Left out —{" "}
                    <span className="font-mono text-foreground">
                      {folderDetection.skippedDirs
                        .slice(0, 6)
                        .map((dir) => dir.split("/").pop() || dir)
                        .join(", ")}
                      {folderDetection.skippedDirs.length > 6 ? " …" : ""}
                    </span>
                    . No readable 1D dataset there; a 2D experiment is the usual reason.
                  </p>
                ) : null}
              </div>
            ) : null}
            {/* Native input — sr-only so shadcn classes don't override hidden sizing. */}
            <input
              id="raw-file"
              ref={fileRef}
              type="file"
              multiple
              accept={SPECTRACHECK_RAW_FID_ACCEPT}
              className="sr-only"
              onChange={(e) => {
                const picked = Array.from(e.target.files ?? [])
                if (picked.length === 0) {
                  setSelectedFile(null)
                  setSelectedFileName(null)
                  return
                }
                setFolderDetection(null)
                setFolderError(null)
                // enqueueArchives points the single-dataset controls at the first admitted
                // archive, so picking exactly one behaves as it always has.
                enqueueArchives(picked)
              }}
            />
            {/* The queue row carries the same name with more beside it, so this chip would only
                repeat it. Shown when nothing has been queued — the single-archive path. */}
            {selectedFileName && batchItems.length === 0 ? (
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
                Processing always operates on a derived copy; the original is always preserved.
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
              {/* "Reuse session raw FID" removed. The select wrote
                  sessionRawFileIdChoice, which no request builder ever read, so
                  choosing an archive here changed nothing while telling the user
                  it would reuse it. Wiring it means resolving a session file id
                  to an archive id and threading it through all five request
                  paths — a feature, and its own change. A control that lies is
                  worse than one that is absent. */}

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
            </CollapsibleContent>
          </Collapsible>
        </div>
      </ModuleCard>

      {/* ── Step 2 — Dataset queue ─────────────────────────────────────────
          Only present once something has been queued, so a single-archive
          upload looks exactly as it always did. */}
      <SpectraCheckRawFidBatch
        items={batchItems}
        mode={batchMode}
        onModeChange={(next) => update({ batchMode: next })}
        running={batchRunning}
        packaging={folderBusy}
        notice={batchNotice}
        activeItemId={batchActiveId}
        onSelectItem={selectBatchItem}
        onRunAll={runBatchAll}
        onStop={stopBatch}
        onRunItem={runBatchOne}
        onRemoveItem={removeBatchItem}
        onClearAll={clearBatch}
      />

      {/* ── Step 3 — Run ───────────────────────────────────────────────── */}
      <ModuleCard
        accent="teal"
        eyebrow="Step 2 · Run"
        title={batchItems.length > 0 ? "Inspect or process the selected dataset" : "Inspect or process"}
        icon={Zap}
        description="Preview archive metadata with an automatic quick spectrum, or process the FID through the full selected recipe."
        className="min-w-0"
      >
        <div className="space-y-4">
          {/* Analysis backend selector — opt-in experimental GSD-Prompt-3.
              Default MUST remain `legacy`; do not silently flip tenants.

              Behind a disclosure because a routine run never touches it, but
              kept HERE rather than moved to Setup: it changes what the Process
              tile below actually does, and a control that redefines a button
              belongs beside that button. It opens itself whenever the
              experimental backend is selected, so the tile can never claim
              "GSD analyze" with the reason why hidden. */}
          <details open={analysisBackend === "gsd_prompt3"}>
            <summary className="cursor-pointer list-none font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground hover:text-foreground">
              Analysis backend
            </summary>
            <div className="pt-3">
              <GsdAnalysisControls
                backend={analysisBackend}
                onBackendChange={setAnalysisBackend}
                level={gsdLevel}
                onLevelChange={setGsdLevel}
                solvent={gsdSolvent}
                onSolventChange={setGsdSolvent}
              />
            </div>
          </details>

          {/* Two run tiles — same shared component, and therefore the same
              geometry and type scale, as the Processed tab's pair. */}
          <div className="grid gap-3 sm:grid-cols-2">
            <SpectraCheckRunTile
              eyebrow="Inspect"
              eyebrowIcon={Eye}
              badge="Metadata + quick FT"
              headline={previewLoading ? `Reading…${elapsedLabel}` : "Preview spectrum"}
              description="Read archive contents, vendor, file hash, and acquisition parameters, then display a quick spectrum."
              tone="secondary"
              loading={previewLoading}
              tooltip="Preview the archive metadata and a quick spectrum."
              onClick={runPreview}
            />
            <SpectraCheckRunTile
              eyebrow={analysisBackend === "gsd_prompt3" ? "GSD analyze" : "Process"}
              eyebrowIcon={analysisBackend === "gsd_prompt3" ? FlaskConical : Sparkles}
              badge={analysisBackend === "gsd_prompt3" ? "Experimental" : "Generates spectrum"}
              headline={
                analysisBackend === "gsd_prompt3"
                  ? gsdLoading
                    ? "Running GSD…"
                    : `Run GSD analysis (level ${gsdLevel})`
                  : processLoading
                    ? `Processing…${elapsedLabel}`
                    : "Process FID"
              }
              description={
                analysisBackend === "gsd_prompt3"
                  ? "Industry-standard peak detection with auto-classification on the FT-processed spectrum."
                  : "Fourier transform + apodization on a derived copy. Generates the displayable spectrum."
              }
              tone={analysisBackend === "gsd_prompt3" ? "experimental" : "primary"}
              loading={processLoading || gsdLoading}
              tooltip={
                analysisBackend === "gsd_prompt3"
                  ? "Run GSD analysis (experimental)"
                  : "Process the FID through the full recipe"
              }
              onClick={analysisBackend === "gsd_prompt3" ? runGSDAnalyze : runProcess}
            />
          </div>

          {/* Background job + clear row */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed bg-muted/20 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <PlayCircle className="h-4 w-4 text-muted-foreground" aria-hidden />
              {/* Background jobs are NOT available for raw FID on this deployment: the job types
                  are registered but the server has no execution adapter for them, so every such
                  job is created already failed — after uploading the whole archive. Rather than
                  offer a control that always fails and wastes a multi-megabyte upload, the entry
                  point is disabled and says so. The buttons above run the analysis directly. */}
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Background job
              </span>
              {/* Stated in visible text, not a `title`: these buttons are disabled, and a
                  disabled control never fires its native tooltip — so the reason was
                  unreachable by mouse, keyboard and touch alike. */}
              <span className="text-[11px] text-muted-foreground">
                Not available for raw FID yet — use the buttons above.
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled
                className="h-7 px-2 font-mono text-[11px]"
              >
                Preview
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled
                className="h-7 px-2 font-mono text-[11px]"
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

          {/* No job-error alert and no job timeline here. Nothing in this file
              calls setJobActionError, startJob or pollJob — background jobs are
              disabled for raw FID (see the row above) — so both surfaces were
              provably unreachable rather than merely unused. */}

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
        subtitle={displayedDatasetName(displayPayload, selectedFileName) ?? undefined}
        tag={sampleId.trim() || undefined}
        testId="raw-fid-fullscreen-view"
      >
      {/* ── Step 4 — Results ──────────────────────────────────────────── */}
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
                // Trace density is derived from the chart's own pixel width
                // (see spectrumPointBudgetForWidth). This surface used to
                // override it to 12_000 points / 24 per pixel to make dd/t/q/m
                // fine structure visible without zooming; measured, that took
                // the sampler past its "source already fits" early return and
                // handed Plotly ~10 vertices per pixel column, which is what
                // rendered peaks as soft blobs on a fuzzy baseline. Fine
                // structure comes from zooming, not from over-drawing.
                <SpectrumViewer
                  x={xy.x}
                  y={xy.y}
                  peaks={viewerPeaks}
                  nucleus={resolvedNucleus}
                  renderMode="webgl"
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
                    The spectrum and processing details will appear here together once processing finishes.
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
                        : "No display-ready spectrum points were returned. Try the quick auto-FT preview again, or Process raw FID."
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
                      sourceLabel: `Raw FID · ${displayedDatasetName(displayPayload, selectedFileName) ?? "uploaded archive"}`,
                      payload: {
                        sample_id: sampleId.trim() || null,
                        nucleus,
                        filename: displayedDatasetName(displayPayload, selectedFileName) ?? undefined,
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
                          "Spectrum was forwarded from the Raw FID tab — it re-runs through the processed-NMR analysis when you press Analyze.",
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
                      {/* Every reported shift depends on how far the axis was
                          moved and what it was anchored on. The wire has both;
                          nothing read them. */}
                      {referencing.shiftPpm != null || referencing.mode != null ? (
                        <div data-testid="raw-fid-referencing-readout">
                          <p className="text-[11px] font-medium text-muted-foreground">
                            Chemical shift reference
                          </p>
                          <p className="mt-1 font-mono text-[11px]">
                            {referencing.shiftPpm != null && referencing.shiftPpm !== 0
                              ? `axis moved ${referencing.shiftPpm > 0 ? "+" : ""}${referencing.shiftPpm.toFixed(4)} ppm`
                              : "axis unchanged"}
                          </p>
                          {describeReferenceMode(referencing.mode) ? (
                            <p className="mt-0.5 text-[11px] text-muted-foreground">
                              {describeReferenceMode(referencing.mode)}
                              {referencing.observedPpm != null && referencing.targetPpm != null
                                ? ` — ${referencing.observedPpm.toFixed(3)} ppm read as ${referencing.targetPpm.toFixed(2)} ppm`
                                : ""}
                            </p>
                          ) : null}
                        </div>
                      ) : null}
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
                          Independent reader cross-check
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
                                  ? "Cross-check unavailable"
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
                            Cross-check peaks
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
                          <p className="text-xs font-medium">{humanizeMethodName(promptSidecarQa.phaseMethod)}</p>
                          <p className="font-mono text-[10px] text-muted-foreground">
                            P0 {formatPromptSidecarNumber(promptSidecarQa.phaseZeroOrderDegrees)}°
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/10 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Baseline
                          </p>
                          <p className="text-xs font-medium">{humanizeMethodName(promptSidecarQa.baselineMethod)}</p>
                          <p className="font-mono text-[10px] text-muted-foreground">
                            order {formatPromptSidecarNumber(promptSidecarQa.baselineOrder)} · RMSE{" "}
                            {formatPromptSidecarPercent(promptSidecarQa.baselineRmseFractionFullScale)}
                          </p>
                        </div>
                        <div className="rounded-md border bg-muted/10 px-2 py-1.5">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Cross-check runtime
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
                        Not used for: plot · peak markers · phase/baseline
                      </p>
                      {promptSidecarConsistency?.message ? (
                        <p className="text-xs text-muted-foreground">{promptSidecarConsistency.message}</p>
                      ) : null}
                      {promptSidecarHasUnexpectedActivation ? (
                        <p className="text-xs font-medium" style={{ color: "var(--mt-amber)" }}>
                          This cross-check appears to be influencing the displayed results; review before relying on it.
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
                          Active peak source: {promptSidecarConsistency.activePeakSource ?? "legacy"} · Cross-check
                          source: {promptSidecarConsistency.recommendedPeakCountSource ?? "independent reader"} ·
                          Tolerance:{" "}
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
                <SpectraCheckEvidencePanels payload={displayPayload} showReferences={false} />
                {/* Review sits after the evidence, on the Raw FID tab because this
                    is where processing runs are produced — no new navigation for a
                    step that belongs to the run you just made. It lists runs rather
                    than binding to this one: the response from processing here
                    carries no run id (NMRRawFIDProcessResponse has no such field
                    and forbids extras), so the run list is the only place the ids
                    exist. See lib/fid/fid-run-review.ts. */}
                <SpectraCheckFidRunReview />
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

      {/* ── Step 4b — GSD-Prompt-3 output (experimental) ──────────────────
          Only renders when the user has run the experimental backend.
          Lives alongside the legacy Step 4 results without replacing them. */}
      <SpectraCheckAnalysisPanels
        gsdResult={gsdResult}
        trace={xy}
        nucleus={nucleus}
        solvent={solvent}
        fieldMhz={extractFieldMhz(processResult) ?? extractFieldMhz(previewResult) ?? 500}
        candidatesText={candidatesText}
        sampleId={sampleId}
        compoundClass={compoundClassForRequest(compoundClass) || undefined}
        displayPayload={displayPayload}
        testIdPrefix="raw-fid"
        resultsExtras={
          legacyDetectionResult ? (
            /* Raw-FID responses expose the same peaks + environments +
               category_counts envelope as GSD, so they render through the same
               component whichever backend produced them. */
            <DetectionResultsPanel
              result={legacyDetectionResult}
              testId="raw-fid-legacy-results-surface"
            />
          ) : null
        }
      />
      </SpectrumResultsFullscreen>
    </div>
  )
}
