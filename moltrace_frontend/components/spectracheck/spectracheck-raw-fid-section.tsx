"use client"

import { useCallback, useRef, useState } from "react"
import { useOptionalSpectraCheckWorkspaceSession } from "@/components/spectracheck/spectracheck-workspace-session-context"
import { apiFetch } from "@/lib/api/client"
import { trackFileUploaded } from "@/src/lib/analytics/analytics-client"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { buildAnalysisJobPayload } from "@/src/lib/spectracheck/buildAnalysisJobPayload"
import type { SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { normalizeSessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { useAnalysisJob } from "@/src/lib/spectracheck/useAnalysisJob"
import { SpectrumViewer } from "@/components/science/SpectrumViewer"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { extractSpectrumXY, isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { isMissingNmrEndpoint, RAW_FID_BACKEND_MSG } from "@/components/spectracheck/spectracheck-nmr-endpoint-messages"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

type Props = {
  sampleId: string
  onSampleIdChange: (value: string) => void
  solvent: string
  registerDev?: (key: string, value: unknown) => void
}

const PRESETS = [
  { value: "safe_automatic", label: "Safe automatic" },
  { value: "imported_parameters", label: "Imported parameters" },
  { value: "no_baseline_correction", label: "No baseline correction" },
  { value: "no_phase_correction", label: "No phase correction" },
] as const

export function SpectraCheckRawFidSection({ sampleId, onSampleIdChange, solvent, registerDev }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [nucleus, setNucleus] = useState<"1H" | "13C">("1H")
  const [vendor, setVendor] = useState("auto")
  const [preset, setPreset] = useState<(typeof PRESETS)[number]["value"]>("safe_automatic")

  const [previewResult, setPreviewResult] = useState<unknown>(null)
  const [processResult, setProcessResult] = useState<unknown>(null)
  const [previewError, setPreviewError] = useState("")
  const [processError, setProcessError] = useState("")
  const [previewLoading, setPreviewLoading] = useState(false)
  const [processLoading, setProcessLoading] = useState(false)

  const ws = useOptionalSpectraCheckWorkspaceSession()
  const analysisJob = useAnalysisJob()
  const [sessionRawFileIdChoice, setSessionRawFileIdChoice] = useState("")
  const [jobActionError, setJobActionError] = useState("")

  const pushDev = useCallback(
    (key: string, value: unknown) => {
      registerDev?.(key, value)
    },
    [registerDev]
  )

  const rawSessionFileOptions = (ws?.sessionFiles ?? []).filter(
    (f: SessionFileRecord) => f.file_kind === "raw_fid" || /\.(zip|tgz)$/i.test(f.filename),
  )

  async function ensureRawFidInputFileId(): Promise<string | null> {
    if (sessionRawFileIdChoice.trim()) return sessionRawFileIdChoice.trim()
    const file = fileRef.current?.files?.[0]
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
        setJobActionError("Choose a session raw FID file or pick a local archive.")
        return
      }
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
        setJobActionError("Choose a session raw FID file or pick a local archive.")
        return
      }
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
    return fd
  }

  async function runPreview() {
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setPreviewError("Choose a raw FID archive (.zip / .tar.gz).")
      return
    }
    setPreviewLoading(true)
    setPreviewError("")
    setPreviewResult(null)
    try {
      const fd = buildFormData(file, false)
      const data = await apiFetch<unknown>("/nmr/raw-fid/preview", { method: "POST", body: fd })
      setPreviewResult(data)
      pushDev("raw_fid_preview", data)
    } catch (err) {
      if (isMissingNmrEndpoint(err)) setPreviewError(RAW_FID_BACKEND_MSG)
      else setPreviewError(formatApiError(err, "Raw FID preview failed"))
    } finally {
      setPreviewLoading(false)
    }
  }

  async function runProcess() {
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setProcessError("Choose a raw FID archive (.zip / .tar.gz).")
      return
    }
    setProcessLoading(true)
    setProcessError("")
    setProcessResult(null)
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
    setPreviewResult(null)
    setProcessResult(null)
    setPreviewError("")
    setProcessError("")
    if (fileRef.current) fileRef.current.value = ""
  }

  const displayPayload = processResult ?? previewResult

  const xyProcess = processResult ? extractSpectrumXY(processResult) : null
  const xyPreview = previewResult ? extractSpectrumXY(previewResult) : null
  const xy = xyProcess ?? xyPreview

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
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>Raw FID Upload / Non-destructive Processing</CardTitle>
          <CardDescription>
            POST <code className="text-xs">/nmr/raw-fid/preview</code> and{" "}
            <code className="text-xs">/nmr/raw-fid/process</code> — multipart FormData.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="raw-sample">Sample ID</Label>
              <Input id="raw-sample" value={sampleId} onChange={(e) => onSampleIdChange(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="raw-solvent">Solvent</Label>
              <Input id="raw-solvent" value={solvent} readOnly className="bg-muted/40" />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="raw-nucleus">Nucleus</Label>
              <select
                id="raw-nucleus"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={nucleus}
                onChange={(e) => setNucleus(e.target.value as "1H" | "13C")}
              >
                <option value="1H">1H</option>
                <option value="13C">13C</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="raw-vendor">Vendor</Label>
              <select
                id="raw-vendor"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
              >
                <option value="auto">Auto-detect</option>
                <option value="bruker">Bruker</option>
                <option value="agilent">Agilent / Varian</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="raw-file">Raw FID archive</Label>
            <Input id="raw-file" ref={fileRef} type="file" accept=".zip,.tar.gz,.tgz,application/gzip,application/x-gzip" className="w-full min-w-0" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="raw-session-file">Session raw FID (optional)</Label>
            <select
              id="raw-session-file"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
              value={sessionRawFileIdChoice}
              onChange={(e) => setSessionRawFileIdChoice(e.target.value)}
            >
              <option value="">— none — use file input above</option>
              {rawSessionFileOptions.map((f) => (
                <option key={f.file_id} value={f.file_id}>
                  {f.filename} ({f.file_kind})
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">Use a raw FID archive already attached to this session.</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="raw-preset">Processing preset (process)</Label>
            <select
              id="raw-preset"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
              value={preset}
              onChange={(e) => setPreset(e.target.value as (typeof PRESETS)[number]["value"])}
            >
              {PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-start gap-2 rounded-md border border-dashed p-3">
            <Checkbox id="raw-preserve" checked disabled />
            <div>
              <Label htmlFor="raw-preserve" className="font-medium">
                Preserve raw data as immutable source
              </Label>
              <p className="text-xs text-muted-foreground">Always sent as preserve_raw=true on process (recommended).</p>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex w-full sm:w-auto">
                  <Button type="button" variant="secondary" className="w-full sm:w-auto" disabled={previewLoading} onClick={runPreview}>
                    {previewLoading ? "Reading…" : "Preview raw metadata"}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                Inspect raw FID archive metadata and file hash before processing.
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex w-full sm:w-auto">
                  <Button type="button" className="w-full sm:w-auto" disabled={processLoading} onClick={runProcess}>
                    {processLoading ? "Processing…" : "Process raw FID"}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                Process a derived copy of the raw FID. The original raw file should remain unchanged.
              </TooltipContent>
            </Tooltip>
            <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={clearAll}>
              Clear raw FID
            </Button>
          </div>

          <div className="space-y-3 border-t pt-4">
            <p className="text-xs font-medium text-muted-foreground">Analysis jobs (run in the background)</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => void startRawPreviewJob()}>
                Start as job (preview)
              </Button>
              <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => void startRawProcessJob()}>
                Start as job (process)
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
              evidenceLayer={nucleus === "1H" ? "raw_fid_1h" : "raw_fid_13c"}
              sourceTab="Raw FID upload"
            />
          ) : null}

          {previewError && (
            <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{previewError}</div>
          )}
          {processError && (
            <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{processError}</div>
          )}
        </CardContent>
      </Card>

      {(previewLoading || processLoading) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{previewLoading ? "Preview…" : "Processing…"}</CardTitle>
          </CardHeader>
        </Card>
      )}

      {displayPayload != null && !previewLoading && !processLoading && (
        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
          <div className="min-w-0 space-y-4">
            <SpectrumViewer x={xy?.x ?? []} y={xy?.y ?? []} nucleus={nucleus} />
            {!xy && (
              <p className="text-sm text-muted-foreground">
                No processed preview spectrum in this response — metadata shown alongside.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <SpectraCheckUseUnifiedEvidenceButton
                response={displayPayload}
                meta={{
                  layer: nucleus === "1H" ? "raw_fid_1h" : "raw_fid_13c",
                  sourceTab: "Raw FID upload",
                  title: processResult != null ? "Raw FID process" : "Raw FID preview",
                  endpoint: processResult != null ? "/nmr/raw-fid/process" : "/nmr/raw-fid/preview",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
            </div>
            <DeveloperJsonPanel data={displayPayload} />
          </div>

          <div className="min-w-0 space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Acquisition &amp; processing</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {sha && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">Raw file SHA-256</p>
                    <p className="mt-1 break-all font-mono text-xs">{sha}</p>
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  {vendorDetected && <Badge variant="secondary">Vendor: {vendorDetected}</Badge>}
                  {nucleusMeta && <Badge variant="outline">Nucleus: {nucleusMeta}</Badge>}
                </div>
                {sw != null && (
                  <div className="flex justify-between gap-2 border-b pb-2">
                    <span className="text-muted-foreground">Spectral width</span>
                    <span className="font-mono">{String(sw)}</span>
                  </div>
                )}
                {td != null && (
                  <div className="flex justify-between gap-2 border-b pb-2">
                    <span className="text-muted-foreground">Time-domain points</span>
                    <span className="font-mono">{String(td)}</span>
                  </div>
                )}
                {procParams != null && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">Processing parameters</p>
                    <Textarea
                      readOnly
                      value={typeof procParams === "string" ? procParams : JSON.stringify(procParams, null, 2)}
                      rows={8}
                      className="font-mono text-xs"
                    />
                  </div>
                )}
                {meta?.acquisition_metadata != null && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">Acquisition metadata</p>
                    <Textarea
                      readOnly
                      value={
                        typeof meta.acquisition_metadata === "string"
                          ? meta.acquisition_metadata
                          : JSON.stringify(meta.acquisition_metadata, null, 2)
                      }
                      rows={6}
                      className="font-mono text-xs"
                    />
                  </div>
                )}
                {warnings.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-warning">Warnings</p>
                    <ul className="mt-1 list-inside list-disc text-xs text-warning">
                      {warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
