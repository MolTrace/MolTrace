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
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { extractSpectrumXY, isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { useStableXY } from "@/components/spectracheck/use-stable-xy"
import { isMissingNmrEndpoint, RAW_FID_BACKEND_MSG } from "@/components/spectracheck/spectracheck-nmr-endpoint-messages"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Card, CardContent } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import {
  Activity,
  AlertTriangle,
  Archive,
  BarChart3,
  ChevronDown,
  Eye,
  FileText,
  Hash,
  Lock,
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
  registerDev?: (key: string, value: unknown) => void
}

const PRESETS = [
  { value: "safe_automatic", label: "Safe automatic" },
  { value: "imported_parameters", label: "Imported parameters" },
  { value: "no_baseline_correction", label: "No baseline correction" },
  { value: "no_phase_correction", label: "No phase correction" },
] as const

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

  const ws = useOptionalSpectraCheckWorkspaceSession()
  const analysisJob = useAnalysisJob()
  const sendTabLink = useSpectraCheckTabLink()

  // dragOver is purely ephemeral visual state — fine to reset on remount.
  const [dragOver, setDragOver] = useState(false)

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
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (err) {
      setJobActionError(formatApiError(err, "Could not start raw FID process job"))
    }
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
    }
    const ccParam = compoundClassForRequest(compoundClass)
    if (ccParam) fd.append("compound_class", ccParam)
    return fd
  }

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
        data = await apiFetch<unknown>(`/raw-fid/${encodeURIComponent(safeArchiveId)}/preview`, {
          method: "POST",
          body: fd,
        })
      } else {
        const fd = new FormData()
        fd.append("file", file)
        fd.append("sample_id", sampleId)
        fd.append("solvent", solvent)
        fd.append("nucleus", nucleus)
        fd.append("vendor", vendor)
        fd.append("processing_preset", "safe_automatic")
        fd.append("preserve_raw", "true")
        data = await apiFetch<unknown>("/nmr/raw-fid/process", { method: "POST", body: fd })
      }
      pushDev("raw_fid_preview_spectrum", data)
      const xy = extractSpectrumXY(data)
      if (xy) {
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
                  : "safe_automatic",
          },
          previewSpectrumLoading: false,
        })
      } else {
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
    // when data arrives. [Mnova anti-shake §3]
    update({ previewSpectrumError: "", previewSpectrumLoading: true })
    let shouldGenerateSpectrum = false
    let previewArchiveId: string | null = null
    try {
      const fd = buildFormData(file, false)
      const data = await apiFetch<unknown>("/nmr/raw-fid/preview", { method: "POST", body: fd })
      setPreviewResult(data)
      pushDev("raw_fid_preview", data)
      shouldGenerateSpectrum = true
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
    update({ previewSpectrumError: "" })
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

  function clearAll() {
    update({
      previewResult: null,
      processResult: null,
      previewError: "",
      processError: "",
      previewSpectrum: null,
      previewSpectrumError: "",
      previewSpectrumLoading: false,
      selectedFile: null,
      selectedFileName: null,
    })
    if (fileRef.current) fileRef.current.value = ""
  }

  const displayPayload = processResult ?? previewResult
  const resultsMode =
    processLoading
      ? "process"
      : previewLoading || previewSpectrumLoading
        ? "preview"
        : processResult != null
          ? "process"
          : previewResult != null || previewSpectrum != null
            ? "preview"
            : null
  const hasResultSurface = resultsMode != null
  const payloadMode = processResult != null ? "process" : previewResult != null ? "preview" : resultsMode
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
  // Stabilise the resolved spectrum xy reference across upstream transitions.
  // The preview / process pipelines may hand us the same numeric x / y in
  // back-to-back responses (e.g. re-running ``process`` with the same
  // preset); reusing the previous reference keeps SpectrumViewer's expensive
  // percentile / mask / sampling memos cached and prevents Plotly from
  // redrawing an already-painted line. [Mnova anti-shake §3]
  const xyResolved = xyProcess ?? xyPreview ?? xyAutoPreview
  const xy = useStableXY(xyResolved)
  const xyIsAutoPreview = !xyProcess && !xyPreview && xyAutoPreview != null

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
  const sw = meta && (meta.spectral_width_hz ?? meta.spectral_width ?? meta.sw)
  const td = meta && (meta.time_domain_points ?? meta.td ?? meta.np)
  const procParams = meta && meta.processing_parameters != null ? meta.processing_parameters : meta?.parameters

  const warnings =
    meta && Array.isArray(meta.warnings) ? meta.warnings.map(String) : meta && typeof meta.warnings === "string" ? [meta.warnings] : []

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
                  Used when running <span className="font-mono">/process</span>. Preview ignores this.
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
                      style={{ color: "var(--mt-teal)" }}
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

            {/* Process tile (primary) */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled={processLoading}
                  onClick={runProcess}
                  className={cn(
                    "group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                    "hover:-translate-y-px hover:shadow-md",
                    processLoading
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
                      Process
                    </span>
                    <span
                      className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      Generates spectrum
                    </span>
                  </div>
                  <span className="font-mono text-base font-bold leading-tight">
                    {processLoading ? "Processing…" : "Process FID"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Fourier transform + apodization on a derived copy. Generates the displayable spectrum.
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                POST /nmr/raw-fid/process
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

          {previewError && (
            <AlertCard variant="error" title="Preview failed" description={previewError} />
          )}
          {processError && (
            <AlertCard variant="error" title="Process failed" description={processError} />
          )}
        </div>
      </ModuleCard>

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
                style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
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
                        style={{ color: "var(--mt-teal)" }}
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
                        style={{ color: "var(--mt-teal)" }}
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
                        style={{ color: "var(--mt-teal)" }}
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
                        style={{ color: "var(--mt-teal)" }}
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
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Auto-FT preview · {previewSpectrum?.processingPreset ?? "safe_automatic"}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    Quick Fourier-transformed preview. Run Process FID for full apodization, phasing, and baseline correction.
                  </p>
                </div>
              ) : null}
              {xy ? (
                <SpectrumViewer x={xy.x} y={xy.y} nucleus={nucleus} />
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
                      style={{ color: "var(--mt-teal)" }}
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
                      style={{ color: "var(--mt-teal)" }}
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
                          source_processing_preset:
                            xyIsAutoPreview && previewSpectrum
                              ? previewSpectrum.processingPreset
                              : processResult
                                ? "user-selected"
                                : null,
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
                              style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
                            >
                              Vendor · {vendorDetected}
                            </Badge>
                          )}
                          {nucleusMeta && (
                            <Badge
                              variant="outline"
                              className="font-mono text-[10px]"
                              style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
                            >
                              Nucleus · {nucleusMeta}
                            </Badge>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Processing parameters */}
                {procParams != null && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-2 py-3">
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        Processing parameters
                      </p>
                      <Textarea
                        readOnly
                        value={typeof procParams === "string" ? procParams : JSON.stringify(procParams, null, 2)}
                        rows={6}
                        className="font-mono text-[11px]"
                      />
                    </CardContent>
                  </Card>
                )}

                {/* Acquisition metadata */}
                {meta?.acquisition_metadata != null && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-2 py-3">
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        Acquisition metadata
                      </p>
                      <Textarea
                        readOnly
                        value={
                          typeof meta.acquisition_metadata === "string"
                            ? meta.acquisition_metadata
                            : JSON.stringify(meta.acquisition_metadata, null, 2)
                        }
                        rows={5}
                        className="font-mono text-[11px]"
                      />
                    </CardContent>
                  </Card>
                )}

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

            {/* Developer JSON — full width. */}
            {displayPayload != null ? <DeveloperJsonPanel data={displayPayload} /> : null}
          </div>
          </ModuleCard>
        </div>
      )}
    </div>
  )
}
