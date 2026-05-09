"use client"

import { useCallback, useRef, useState } from "react"
import { useOptionalSpectraCheckWorkspaceSession } from "@/components/spectracheck/spectracheck-workspace-session-context"
import { apiFetch } from "@/lib/api/client"
import { trackFileUploaded } from "@/src/lib/analytics/analytics-client"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { buildAnalysisJobPayload } from "@/src/lib/spectracheck/buildAnalysisJobPayload"
import { normalizeSessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { useAnalysisJob } from "@/src/lib/spectracheck/useAnalysisJob"
import { SpectrumViewer, type SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"

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
  const [sessionFileIdChoice, setSessionFileIdChoice] = useState("")
  const [jobActionError, setJobActionError] = useState("")

  const fileRef = useRef<HTMLInputElement>(null)
  const [nucleus, setNucleus] = useState<"1H" | "13C">("1H")
  const [spectrometerMhz, setSpectrometerMhz] = useState("400")
  const [nmrTextOptional, setNmrTextOptional] = useState("")
  const [candidatesOptional, setCandidatesOptional] = useState("")

  const [previewResult, setPreviewResult] = useState<unknown>(null)
  const [analyzeResult, setAnalyzeResult] = useState<unknown>(null)
  const [previewError, setPreviewError] = useState("")
  const [analyzeError, setAnalyzeError] = useState("")
  const [previewLoading, setPreviewLoading] = useState(false)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)

  const pushDev = useCallback(
    (key: string, value: unknown) => {
      registerDev?.(key, value)
    },
    [registerDev]
  )

  async function ensureProcessedInputFileId(): Promise<string | null> {
    if (sessionFileIdChoice.trim()) return sessionFileIdChoice.trim()
    const file = fileRef.current?.files?.[0]
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
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setPreviewError("Choose a processed spectrum file.")
      return
    }
    setPreviewLoading(true)
    setPreviewError("")
    setPreviewResult(null)
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
    const file = fileRef.current?.files?.[0]
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
    setPreviewResult(null)
    setAnalyzeResult(null)
    setPreviewError("")
    setAnalyzeError("")
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

  return (
    <div className="space-y-6">
      <ModuleCard
        accent="teal"
        eyebrow="Spectroscopy · Processed Upload"
        title="Processed 1H / 13C Spectrum Upload"
        description="Upload a processed 1H or 13C NMR spectrum for peak preview and quantitative chemical-shift analysis."
        className="min-w-0"
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="proc-sample">Sample ID</Label>
              <Input
                id="proc-sample"
                value={sampleId}
                onChange={(e) => onSampleIdChange(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Uses SpectraCheck shared session sample ID.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="proc-solvent">Solvent</Label>
              <Input id="proc-solvent" value={solvent} readOnly className="bg-muted/40" />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="proc-nucleus">Nucleus</Label>
              <select
                id="proc-nucleus"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={nucleus}
                onChange={(e) => setNucleus(e.target.value as "1H" | "13C")}
              >
                <option value="1H">1H</option>
                <option value="13C">13C</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="proc-mhz">Spectrometer frequency (MHz)</Label>
              <Input
                id="proc-mhz"
                type="number"
                inputMode="decimal"
                step="0.1"
                min={0}
                value={spectrometerMhz}
                onChange={(e) => setSpectrometerMhz(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="proc-file">Processed spectrum file</Label>
            <Input
              id="proc-file"
              ref={fileRef}
              type="file"
              accept=".csv,.tsv,.txt,.jcamp,.jdx,.dx"
              className="w-full min-w-0"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="proc-session-file">Session file (optional)</Label>
            <select
              id="proc-session-file"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
              value={sessionFileIdChoice}
              onChange={(e) => setSessionFileIdChoice(e.target.value)}
            >
              <option value="">— none — use file input above</option>
              {(ws?.sessionFiles ?? []).map((f) => (
                <option key={f.file_id} value={f.file_id}>
                  {f.filename} ({f.file_kind})
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Reuse a file already uploaded to <code className="text-xs">/files/upload</code> and attached to this session.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="proc-nmr-text">Optional NMR text reference</Label>
            <Textarea
              id="proc-nmr-text"
              value={nmrTextOptional}
              onChange={(e) => setNmrTextOptional(e.target.value)}
              rows={3}
              placeholder="Optional — forwarded as nmr_text when non-empty"
              className="min-h-0 w-full min-w-0"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="proc-cand">Optional candidate list (analyze)</Label>
            <Textarea
              id="proc-cand"
              value={candidatesOptional}
              onChange={(e) => setCandidatesOptional(e.target.value)}
              rows={4}
              placeholder="Leave empty to use shared candidate structures from the session card above"
              className="min-h-0 w-full min-w-0"
            />
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex w-full sm:w-auto">
                  <Button type="button" variant="secondary" className="w-full sm:w-auto" disabled={previewLoading} onClick={runPreview}>
                    {previewLoading ? "Previewing…" : "Preview processed spectrum"}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                Preview uploaded processed spectrum data before running evidence analysis.
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex w-full sm:w-auto">
                  <Button type="button" className="w-full sm:w-auto" disabled={analyzeLoading} onClick={runAnalyze}>
                    {analyzeLoading ? "Analyzing…" : "Analyze processed spectrum"}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                Run backend peak detection and evidence matching on the uploaded processed spectrum.
              </TooltipContent>
            </Tooltip>
            <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={clearAll}>
              Clear processed spectrum
            </Button>
          </div>

          <div className="space-y-3 border-t pt-4">
            <p className="text-xs font-medium text-muted-foreground">Analysis jobs (run in the background)</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => void startProcessedPreviewJob()}>
                Start as job (preview)
              </Button>
              <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => void startProcessedAnalyzeJob()}>
                Start as job (analyze)
              </Button>
            </div>
            {jobActionError ? (
              <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{jobActionError}</div>
            ) : null}
          </div>

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

      {(previewLoading || analyzeLoading) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{previewLoading ? "Preview…" : "Analyze…"}</CardTitle>
            <CardDescription>Waiting for API response</CardDescription>
          </CardHeader>
        </Card>
      )}

      {displayPayload != null && !previewLoading && !analyzeLoading && (
        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
          <div className="min-w-0 space-y-4">
            <SpectrumViewer
              x={xy?.x ?? []}
              y={xy?.y ?? []}
              peaks={peaks}
              overlays={overlays}
              nucleus={nucleus}
            />
            <div className="flex flex-wrap gap-2">
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
            <DeveloperJsonPanel data={displayPayload} />
          </div>

          <div className="min-w-0 space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {peakCount != null && (
                  <div className="flex justify-between gap-2 border-b pb-2">
                    <span className="text-muted-foreground">Peak count</span>
                    <span className="font-mono font-medium">{peakCount}</span>
                  </div>
                )}
                {score != null && (
                  <div className="flex justify-between gap-2 border-b pb-2">
                    <span className="text-muted-foreground">Analysis score</span>
                    <span className="font-mono font-medium">{score.toFixed(2)}</span>
                  </div>
                )}
                {notes && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">Notes</p>
                    <p className="mt-1 leading-snug">{notes}</p>
                  </div>
                )}
                {warnings.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-warning">Solvent / impurity warnings</p>
                    <ul className="mt-1 list-inside list-disc text-xs text-warning">
                      {warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {!peakCount && !score && !notes && warnings.length === 0 && (
                  <p className="text-muted-foreground">No structured summary keys detected — see developer JSON.</p>
                )}
              </CardContent>
            </Card>

            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Picked peaks</CardTitle>
                <CardDescription>Populated when the API returns a peak table</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                {peaks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No peaks in response payload.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>δ (ppm)</TableHead>
                        <TableHead>Intensity</TableHead>
                        <TableHead>Label</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {peaks.slice(0, 200).map((p, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-mono">{p.ppm.toFixed(4)}</TableCell>
                          <TableCell className="font-mono">{p.intensity != null ? p.intensity.toExponential(3) : "—"}</TableCell>
                          <TableCell>{p.label ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {peaks.length > 200 && (
                  <p className="mt-2 text-xs text-muted-foreground">Showing first 200 peaks.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
