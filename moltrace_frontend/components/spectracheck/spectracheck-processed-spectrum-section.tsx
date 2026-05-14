"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useOptionalSpectraCheckWorkspaceSession } from "@/components/spectracheck/spectracheck-workspace-session-context"
import {
  useProcessedTabState,
  useSpectraCheckTabLink,
} from "@/components/spectracheck/spectracheck-tab-state-context"
import { apiFetch } from "@/lib/api/client"
import { trackFileUploaded } from "@/src/lib/analytics/analytics-client"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { buildAnalysisJobPayload } from "@/src/lib/spectracheck/buildAnalysisJobPayload"
import { normalizeSessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { SPECTRACHECK_PROCESSED_NMR_SPECTRUM_ACCEPT } from "@/src/lib/spectracheck/spectrum-file-formats"
import { useAnalysisJob } from "@/src/lib/spectracheck/useAnalysisJob"
import { SpectrumViewer, type SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import {
  EnrichedPickedPeaksPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  extractNotes,
  extractPeaksFromPayload,
  extractPredictedOverlay,
  extractSpectrumXY,
  extractNumericSummary,
  extractWarnings,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"
import {
  isMissingNmrEndpoint,
  PROCESSED_NMR_BACKEND_MSG,
} from "@/components/spectracheck/spectracheck-nmr-endpoint-messages"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Card, CardContent } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import {
  AlertTriangle,
  BarChart3,
  ChevronDown,
  Eye,
  FileText,
  Hash,
  PlayCircle,
  RotateCcw,
  Settings2,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react"

type Props = {
  sampleId: string
  onSampleIdChange: (value: string) => void
  solvent: string
  candidatesText: string
  registerDev?: (key: string, value: unknown) => void
}

export function SpectraCheckProcessedSpectrumSection({
  sampleId,
  onSampleIdChange,
  solvent,
  candidatesText,
  registerDev,
}: Props) {
  const ws = useOptionalSpectraCheckWorkspaceSession()
  const analysisJob = useAnalysisJob()
  const sendTabLink = useSpectraCheckTabLink()
  const { state, update } = useProcessedTabState()
  const {
    sessionFileIdChoice,
    jobActionError,
    nucleus,
    spectrometerMhz,
    nmrTextOptional,
    candidatesOptional,
    previewResult,
    analyzeResult,
    previewError,
    analyzeError,
    previewLoading,
    analyzeLoading,
    selectedFile,
    selectedFileName,
    advancedOpen,
  } = state

  // Setter shims — keep the rest of the file unchanged while state lives in
  // workspace-level context (survives tab unmount).
  const setSessionFileIdChoice = useCallback(
    (v: string) => update({ sessionFileIdChoice: v }),
    [update],
  )
  const setJobActionError = useCallback((v: string) => update({ jobActionError: v }), [update])
  const setNucleus = useCallback((v: "1H" | "13C") => update({ nucleus: v }), [update])
  const setSpectrometerMhz = useCallback(
    (v: string) => update({ spectrometerMhz: v }),
    [update],
  )
  const setNmrTextOptional = useCallback(
    (v: string) => update({ nmrTextOptional: v }),
    [update],
  )
  const setCandidatesOptional = useCallback(
    (v: string) => update({ candidatesOptional: v }),
    [update],
  )
  const setPreviewResult = useCallback((v: unknown) => update({ previewResult: v }), [update])
  const setAnalyzeResult = useCallback((v: unknown) => update({ analyzeResult: v }), [update])
  const setPreviewError = useCallback((v: string) => update({ previewError: v }), [update])
  const setAnalyzeError = useCallback((v: string) => update({ analyzeError: v }), [update])
  const setPreviewLoading = useCallback(
    (v: boolean) => update({ previewLoading: v }),
    [update],
  )
  const setAnalyzeLoading = useCallback(
    (v: boolean) => update({ analyzeLoading: v }),
    [update],
  )
  const setSelectedFile = useCallback(
    (v: File | null) => update({ selectedFile: v }),
    [update],
  )
  const setSelectedFileName = useCallback(
    (v: string | null) => update({ selectedFileName: v }),
    [update],
  )
  const setAdvancedOpen = useCallback((v: boolean) => update({ advancedOpen: v }), [update])

  const fileRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  // Re-attach persisted File to the input on remount so existing
  // fileRef.current?.files?.[0] consumers keep working after a tab switch.
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

  async function ensureProcessedInputFileId(): Promise<string | null> {
    if (sessionFileIdChoice.trim()) return sessionFileIdChoice.trim()
    const file = getSelectedFile()
    if (!file) return null
    const fd = new FormData()
    fd.append("file", file)
    fd.append("file_kind", "processed_nmr")
    const data = await apiFetch<unknown>("/files/upload", { method: "POST", body: fd })
    const rec = normalizeSessionFileRecord(data)
    trackFileUploaded({
      session_id: ws?.backendSessionId ?? undefined,
      metadata: {
        file_kind: "processed_nmr",
        file_size_bytes: file.size,
        has_sha256: Boolean(rec?.sha256),
      },
    })
    await ws?.refreshSessionFiles()
    return rec?.file_id ?? null
  }

  async function startProcessedPreviewJob() {
    setJobActionError("")
    try {
      const fid = await ensureProcessedInputFileId()
      if (!fid) {
        setJobActionError("Choose a session file or pick a local file.")
        return
      }
      const jid = await analysisJob.createJob(
        buildAnalysisJobPayload({
          sessionId: ws?.backendSessionId ?? null,
          sampleId,
          jobType: "nmr_processed_preview",
          inputFileIds: [fid],
          parameters: {
            solvent,
            nucleus,
            spectrometer_frequency_mhz: Number(spectrometerMhz) || 400,
            ...(nmrTextOptional.trim() ? { nmr_text: nmrTextOptional.trim() } : {}),
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (err) {
      setJobActionError(formatApiError(err, "Could not start preview job"))
    }
  }

  async function startProcessedAnalyzeJob() {
    setJobActionError("")
    try {
      const fid = await ensureProcessedInputFileId()
      if (!fid) {
        setJobActionError("Choose a session file or pick a local file.")
        return
      }
      const cand = candidatesOptional.trim() || candidatesText
      const jid = await analysisJob.createJob(
        buildAnalysisJobPayload({
          sessionId: ws?.backendSessionId ?? null,
          sampleId,
          jobType: "nmr_processed_analyze",
          inputFileIds: [fid],
          parameters: {
            solvent,
            nucleus,
            spectrometer_frequency_mhz: Number(spectrometerMhz) || 400,
            ...(nmrTextOptional.trim() ? { nmr_text: nmrTextOptional.trim() } : {}),
            ...(cand.trim() ? { candidates_text: cand.trim() } : {}),
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (err) {
      setJobActionError(formatApiError(err, "Could not start analyze job"))
    }
  }

  function buildBaseFormData(file: File) {
    const fd = new FormData()
    fd.append("file", file)
    fd.append("sample_id", sampleId)
    fd.append("solvent", solvent)
    fd.append("nucleus", nucleus)
    fd.append("spectrometer_frequency_mhz", spectrometerMhz.trim() || "400")
    const nt = nmrTextOptional.trim()
    if (nt) fd.append("nmr_text", nt)
    return fd
  }

  async function runPreview() {
    const file = getSelectedFile()
    if (!file) {
      setPreviewError("Choose a processed spectrum file.")
      return
    }
    setPreviewLoading(true)
    setPreviewError("")
    setPreviewResult(null)
    setAnalyzeResult(null)
    try {
      const fd = buildBaseFormData(file)
      const data = await apiFetch<unknown>("/nmr/processed/preview", { method: "POST", body: fd })
      setPreviewResult(data)
      pushDev("processed_preview", data)
    } catch (err) {
      if (isMissingNmrEndpoint(err)) setPreviewError(PROCESSED_NMR_BACKEND_MSG)
      else setPreviewError(formatApiError(err, "Processed spectrum preview failed"))
    } finally {
      setPreviewLoading(false)
    }
  }

  async function runAnalyze() {
    const file = getSelectedFile()
    if (!file) {
      setAnalyzeError("Choose a processed spectrum file.")
      return
    }
    setAnalyzeLoading(true)
    setAnalyzeError("")
    setAnalyzeResult(null)
    try {
      const fd = buildBaseFormData(file)
      const cand = candidatesOptional.trim() || candidatesText
      if (cand.trim()) fd.append("candidates_text", cand)
      const data = await apiFetch<unknown>("/nmr/processed/analyze", { method: "POST", body: fd })
      setAnalyzeResult(data)
      pushDev("processed_analyze", data)
    } catch (err) {
      if (isMissingNmrEndpoint(err)) setAnalyzeError(PROCESSED_NMR_BACKEND_MSG)
      else setAnalyzeError(formatApiError(err, "Processed spectrum analyze failed"))
    } finally {
      setAnalyzeLoading(false)
    }
  }

  function clearAll() {
    update({
      previewResult: null,
      analyzeResult: null,
      previewError: "",
      analyzeError: "",
      selectedFile: null,
      selectedFileName: null,
      linkedFromSource: null,
    })
    if (fileRef.current) fileRef.current.value = ""
  }

  const displayPayload = analyzeResult ?? previewResult
  const xy = extractSpectrumXY(displayPayload ?? {})
  const peaks: SpectrumPeakAnnotation[] = extractPeaksFromPayload(displayPayload ?? {})
  const overlays = extractPredictedOverlay(displayPayload ?? {})
  const peakCount = extractNumericSummary(displayPayload ?? {}, ["peak_count", "n_peaks", "peaks_count", "num_peaks"])
  const score = extractNumericSummary(displayPayload ?? {}, [
    "analysis_score",
    "score",
    "overall_score",
    "confidence_score",
  ])
  const warnings = extractWarnings(displayPayload ?? {})
  const notes = extractNotes(displayPayload ?? {})

  /** Build the canonical NMR-text string for the NMR-text tab handoff. */
  const nmrTextFromPeaks = useCallback((): string | null => {
    const rawPeaks = Array.isArray((displayPayload as { peaks?: unknown })?.peaks)
      ? ((displayPayload as { peaks: unknown[] }).peaks as Array<Record<string, unknown>>)
      : []
    if (rawPeaks.length === 0) return null
    const mhzNum = Number(spectrometerMhz)
    const mhz = Number.isFinite(mhzNum) && mhzNum > 0 ? mhzNum : 400
    if (nucleus === "1H") {
      const parts = rawPeaks
        .map((p) => {
          const shift = typeof p.shift_ppm === "number" ? p.shift_ppm : null
          if (shift === null) return null
          const mult = typeof p.multiplicity === "string" ? p.multiplicity : "s"
          const integration = typeof p.integration_h === "number" ? p.integration_h : 1
          const jArr = Array.isArray(p.j_values_hz)
            ? (p.j_values_hz as unknown[]).filter(
                (v): v is number => typeof v === "number" && Number.isFinite(v),
              )
            : []
          const jPart = jArr.length > 0 ? `, J = ${jArr.map((j) => j.toFixed(1)).join(", ")} Hz` : ""
          return `${shift.toFixed(2)} (${mult}${jPart}, ${Math.max(1, Math.round(integration))}H)`
        })
        .filter((s): s is string => s !== null)
      return `1H NMR (${mhz} MHz, ${solvent || "CDCl3"}) δ ${parts.join(", ")}`
    }
    const carbonParts = rawPeaks
      .map((p) => (typeof p.shift_ppm === "number" ? p.shift_ppm.toFixed(1) : null))
      .filter((s): s is string => s !== null)
    return `13C NMR (${Math.round(mhz / 4)} MHz, ${solvent || "CDCl3"}) δ ${carbonParts.join(", ")}.`
  }, [displayPayload, nucleus, solvent, spectrometerMhz])

  return (
    <div className="space-y-6">
      {/* ── Step 1 — Setup & Upload ────────────────────────────────────── */}
      <ModuleCard
        accent="teal"
        eyebrow="Step 1 · Setup"
        title="Configure & upload spectrum"
        icon={Upload}
        description="Set sample metadata, choose nucleus, and drop a processed 1H or 13C NMR spectrum file."
        className="min-w-0"
      >
        <div className="space-y-5">
          {/* Sample ID + Solvent */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="proc-sample" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Sample ID
              </Label>
              <Input
                id="proc-sample"
                value={sampleId}
                onChange={(e) => onSampleIdChange(e.target.value)}
                className="font-mono"
              />
              <p className="text-[11px] text-muted-foreground">Shared with SpectraCheck session.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="proc-solvent" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Solvent <span className="ml-1 text-[10px] font-normal text-muted-foreground/70">(read-only)</span>
              </Label>
              <Input id="proc-solvent" value={solvent} readOnly className="bg-muted/40 font-mono" />
            </div>
          </div>

          {/* Nucleus pill toggle + spectrometer frequency */}
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
              <Label htmlFor="proc-mhz" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Spectrometer frequency
              </Label>
              <div className="flex items-stretch overflow-hidden rounded-md border border-input">
                <Input
                  id="proc-mhz"
                  type="number"
                  inputMode="decimal"
                  step="0.1"
                  min={0}
                  value={spectrometerMhz}
                  onChange={(e) => setSpectrometerMhz(e.target.value)}
                  className="rounded-none border-0 font-mono"
                />
                <span className="flex items-center bg-muted/60 px-3 font-mono text-xs text-muted-foreground">MHz</span>
              </div>
            </div>
          </div>

          {/* Drop-zone file picker */}
          <div className="space-y-1.5">
            <Label htmlFor="proc-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Processed spectrum file
            </Label>
            {/*
              Drop zone is a div + onClick (not a <label>). Reasons:
              - Two <label htmlFor="proc-file"> elements (one above + one wrapping)
                make file-picker activation unreliable across browsers.
              - shadcn <Input> applies h-9 w-full classes that override sr-only.
              We use an explicit fileRef.current?.click() and a plain native input.
            */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Drop processed spectrum file or press Enter to browse"
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
              <Upload
                className="mb-2 h-7 w-7"
                style={{ color: dragOver || selectedFileName ? "var(--mt-teal)" : undefined }}
                aria-hidden
              />
              <p className="font-mono text-sm font-bold tracking-tight">
                {selectedFileName ? "File ready" : dragOver ? "Drop to attach" : "Drop spectrum file or click to browse"}
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                CSV · TSV · TXT · JCAMP-DX · vendor exports
              </p>
            </div>
            {/* Native input — sr-only so shadcn classes don't override the hidden sizing. */}
            <input
              id="proc-file"
              ref={fileRef}
              type="file"
              accept={SPECTRACHECK_PROCESSED_NMR_SPECTRUM_ACCEPT}
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
                <Label htmlFor="proc-session-file" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Reuse session file
                </Label>
                <select
                  id="proc-session-file"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 font-mono text-sm shadow-xs outline-none"
                  value={sessionFileIdChoice}
                  onChange={(e) => setSessionFileIdChoice(e.target.value)}
                >
                  <option value="">— none — use file above</option>
                  {(ws?.sessionFiles ?? []).map((f) => (
                    <option key={f.file_id} value={f.file_id}>
                      {f.filename} ({f.file_kind})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-muted-foreground">
                  Reuse a file already uploaded to <code className="text-[10px]">/files/upload</code> and attached to this session.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="proc-nmr-text" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  NMR text reference
                </Label>
                <Textarea
                  id="proc-nmr-text"
                  value={nmrTextOptional}
                  onChange={(e) => setNmrTextOptional(e.target.value)}
                  rows={3}
                  placeholder="Optional — forwarded as nmr_text when non-empty"
                  className="min-h-0 w-full min-w-0 font-mono text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="proc-cand" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Candidate list (analyze)
                </Label>
                <Textarea
                  id="proc-cand"
                  value={candidatesOptional}
                  onChange={(e) => setCandidatesOptional(e.target.value)}
                  rows={4}
                  placeholder="Leave empty to use shared candidate structures from the session card above"
                  className="min-h-0 w-full min-w-0 font-mono text-xs"
                />
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </ModuleCard>

      {/* ── Step 2 — Run ───────────────────────────────────────────────── */}
      <ModuleCard
        accent="teal"
        eyebrow="Step 2 · Run"
        title="Preview or analyze"
        icon={Zap}
        description="Preview the spectrum to inspect peaks, or run full evidence analysis against candidate structures."
        className="min-w-0"
      >
        <div className="space-y-4">
          {/* Two prominent action tiles */}
          <div className="grid gap-3 sm:grid-cols-2">
            {/* Preview tile */}
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
                      Preview
                    </span>
                    <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                      Quick look
                    </span>
                  </div>
                  <span className="font-mono text-base font-bold leading-tight">
                    {previewLoading ? "Previewing…" : "Inspect spectrum"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Show peaks, intensities, and shape before running evidence matching.
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                POST /nmr/processed/preview
              </TooltipContent>
            </Tooltip>

            {/* Analyze tile (primary) */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled={analyzeLoading}
                  onClick={runAnalyze}
                  className={cn(
                    "group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
                    "hover:-translate-y-px hover:shadow-md",
                    analyzeLoading
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
                    {analyzeLoading ? "Analyzing…" : "Run evidence match"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Detect peaks and match against candidate structures with scoring.
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                POST /nmr/processed/analyze
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
                onClick={() => void startProcessedPreviewJob()}
              >
                Preview
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 font-mono text-[11px]"
                onClick={() => void startProcessedAnalyzeJob()}
              >
                Analyze
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
              evidenceLayer={nucleus === "1H" ? "processed_1h" : "processed_13c"}
              sourceTab="Processed 1H / 13C upload"
            />
          ) : null}

          {previewError && (
            <AlertCard variant="error" title="Preview failed" description={previewError} />
          )}
          {analyzeError && (
            <AlertCard variant="error" title="Analyze failed" description={analyzeError} />
          )}
        </div>
      </ModuleCard>

      {/* ── Loading skeleton ─────────────────────────────────────────── */}
      {(previewLoading || analyzeLoading) && (
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
              {previewLoading ? "Previewing spectrum…" : "Analyzing spectrum…"}
            </p>
            <p className="text-xs text-muted-foreground">Waiting for API response</p>
          </CardContent>
        </Card>
      )}

      {/* ── Step 3 — Results ──────────────────────────────────────────── */}
      {displayPayload != null && !previewLoading && !analyzeLoading && (
        <ModuleCard
          accent="teal"
          eyebrow="Step 3 · Results"
          title={analyzeResult != null ? "Analysis output" : "Preview output"}
          icon={BarChart3}
          description={
            analyzeResult != null
              ? "Spectrum, picked peaks, and matching score from /nmr/processed/analyze."
              : "Spectrum and picked peaks from /nmr/processed/preview."
          }
          className="min-w-0"
        >
          <div className="space-y-4">
            {/* Cross-tab "linked from" banner */}
            {state.linkedFromSource ? (
              <div
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
                style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
                data-testid="processed-linked-from"
              >
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Linked from {state.linkedFromSource}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => update({ linkedFromSource: null })}
                  data-testid="processed-linked-from-dismiss"
                >
                  Dismiss
                </Button>
              </div>
            ) : null}

            {/* KPI tiles */}
            {(peakCount != null || score != null || warnings.length > 0) && (
              <div className="grid gap-3 sm:grid-cols-3">
                {peakCount != null && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <Hash className="h-3 w-3" aria-hidden />
                        Peak count
                      </p>
                      <p
                        className="font-mono text-2xl font-bold leading-none tabular-nums"
                        style={{ color: "var(--mt-teal)" }}
                      >
                        {peakCount}
                      </p>
                    </CardContent>
                  </Card>
                )}
                {score != null && (
                  <Card
                    className="overflow-hidden rounded-xl py-0"
                    style={{
                      borderTop: `3px solid ${
                        score >= 0.8
                          ? "var(--mt-green)"
                          : score >= 0.5
                          ? "var(--mt-amber)"
                          : "var(--mt-red)"
                      }`,
                    }}
                  >
                    <CardContent className="space-y-1 py-3">
                      <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                        <Sparkles className="h-3 w-3" aria-hidden />
                        Analysis score
                      </p>
                      <p
                        className="font-mono text-2xl font-bold leading-none tabular-nums"
                        style={{
                          color:
                            score >= 0.8
                              ? "var(--mt-green)"
                              : score >= 0.5
                              ? "var(--mt-amber)"
                              : "var(--mt-red)",
                        }}
                      >
                        {score.toFixed(2)}
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
                        className="font-mono text-2xl font-bold leading-none tabular-nums"
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
            <div className="min-w-0">
              {xy ? (
                <SpectrumViewer
                  x={xy.x}
                  y={xy.y}
                  peaks={peaks}
                  overlays={overlays}
                  nucleus={nucleus}
                />
              ) : (
                <AlertCard
                  variant="warning"
                  title="Spectrum preview unavailable"
                  description="The preview completed, but no display-ready spectrum points were returned. Try Analyze or inspect the response details below."
                />
              )}
            </div>

            {/* Use Unified Evidence — prominent CTA row right under the spectrum */}
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
                    Add this {analyzeResult != null ? "analysis" : "preview"} to the unified evidence stream.
                  </p>
                </div>
              </div>
              <SpectraCheckUseUnifiedEvidenceButton
                response={displayPayload}
                meta={{
                  layer: nucleus === "1H" ? "processed_1h" : "processed_13c",
                  sourceTab: "Processed 1H / 13C upload",
                  title: analyzeResult != null ? "Processed spectrum analyze" : "Processed spectrum preview",
                  endpoint: analyzeResult != null ? "/nmr/processed/analyze" : "/nmr/processed/preview",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
            </div>

            {/* Cross-tab handoff — send the analyzer's peaks back to the NMR-text tab
                as canonical NMR-string format so the user can hand-edit, then
                re-run text-mode evidence against the same numbers. */}
            {(() => {
              const text = nmrTextFromPeaks()
              if (!text) return null
              return (
                <div
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"
                  style={{
                    borderTop: "3px solid var(--mt-teal)",
                    backgroundColor: "var(--mt-teal-soft)",
                  }}
                  data-testid="processed-send-to-nmr-text"
                >
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
                    <div>
                      <p
                        className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                        style={{ color: "var(--mt-teal)" }}
                      >
                        Cross-tab link
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Push {nucleus} peaks to the NMR text + candidates tab as a hand-editable string.
                      </p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() =>
                      sendTabLink({
                        kind:
                          nucleus === "1H" ? "peaks_to_proton_text" : "peaks_to_carbon_text",
                        sourceLabel: `Processed ${nucleus} · ${selectedFileName ?? "uploaded spectrum"}`,
                        payload: { text, solvent, spectrometerMhz },
                      })
                    }
                    data-testid="processed-send-to-nmr-text-button"
                  >
                    Send peaks to NMR text
                  </Button>
                </div>
              )
            })()}

            {/* Details + Picked peaks — 2-col below the spectrum */}
            <div className="grid min-w-0 gap-4 lg:grid-cols-2">
              {/* Notes / details */}
              {(notes || warnings.length > 0 || (!peakCount && !score)) && (
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <CardContent className="space-y-3 py-3 text-sm">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      Details
                    </p>
                    {notes && (
                      <div>
                        <p className="text-[11px] font-medium text-muted-foreground">Notes</p>
                        <p className="mt-1 leading-snug">{notes}</p>
                      </div>
                    )}
                    {warnings.length > 0 && (
                      <div>
                        <p
                          className="text-[11px] font-medium"
                          style={{ color: "var(--mt-amber)" }}
                        >
                          Solvent / impurity warnings
                        </p>
                        <ul
                          className="mt-1 list-inside list-disc space-y-0.5 text-xs"
                          style={{ color: "var(--mt-amber)" }}
                        >
                          {warnings.map((w, i) => (
                            <li key={i}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {!peakCount && !score && !notes && warnings.length === 0 && (
                      <p className="text-muted-foreground">
                        No structured summary keys detected — see developer JSON below.
                      </p>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Picked peaks — enriched with category, region, impurity match. */}
              <EnrichedPickedPeaksPanel payload={displayPayload} />
            </div>

            {/* Evidence panels — category mix, impurity candidates, labile-H reasoning, predicted vs observed. */}
            <SpectraCheckEvidencePanels payload={displayPayload} />

            {/* Developer JSON — full width at the bottom */}
            <DeveloperJsonPanel data={displayPayload} />
          </div>
        </ModuleCard>
      )}
    </div>
  )
}
