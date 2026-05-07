"use client"

import React, { useCallback, useEffect, useMemo, useState } from "react"
import {
  ChromatogramViewer,
  type ChromatogramFeature,
  type ChromatogramTrace,
} from "@/components/science/ChromatogramViewer"
import { MsmsMirrorPlot } from "@/components/science/MsmsMirrorPlot"
import type {
  MsmsMirrorFragmentMatch,
  MsmsMirrorObservedPeak,
  MsmsMirrorReferencePeak,
} from "@/components/science/MsmsMirrorPlot"
import { SpectrumViewer1D } from "@/components/science/SpectrumViewer1D"
import type { SpectrumViewer1DOverlay, SpectrumViewer1DPeak } from "@/components/science/SpectrumViewer1D"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  extractPeaksFromPayload,
  extractPredictedOverlay,
  extractSpectrumXY,
  extractWarnings,
  extractNotes,
  isRecord,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { summarizeResult } from "@/components/spectracheck/spectracheck-summary"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ApiError, buildApiPath, readStoredAuthToken } from "@/lib/api/client"
import {
  fetchSessionComments,
  pickCommentText,
  pickCommentType,
  postSessionComment,
  sessionCommentMatchesArtifact,
  SESSION_COMMENT_TYPES,
} from "@/src/lib/spectracheck/spectracheck-session-comments"

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return null
}

function coerceNumArray(v: unknown): number[] | null {
  if (!Array.isArray(v)) return null
  const out = v.map((x) => Number(x)).filter((n) => Number.isFinite(n))
  return out.length === v.length ? out : null
}

function extractArtifactJson(detail: unknown): unknown {
  if (!isRecord(detail)) return null
  return (
    detail.artifact_json ??
    detail.payload ??
    detail.data ??
    detail.content ??
    detail.result ??
    detail
  )
}

function extractPeakTableForDisplay(json: unknown): {
  columns: string[]
  rows: Record<string, unknown>[]
} | null {
  if (!isRecord(json)) return null
  const raw =
    json.rows ??
    json.peak_rows ??
    json.peaks ??
    json.peak_table ??
    json.table ??
    json.records
  if (!Array.isArray(raw) || raw.length === 0) return null
  const rows = raw.filter(isRecord) as Record<string, unknown>[]
  if (rows.length === 0) return null
  const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 24)
  return { columns, rows: rows.slice(0, 500) }
}

function overlaysFor1D(payload: unknown): SpectrumViewer1DOverlay[] | undefined {
  const o = extractPredictedOverlay(payload)
  if (!o?.predicted) return undefined
  return [
    {
      name: o.predicted.label ?? "Predicted",
      x: o.predicted.x,
      y: o.predicted.y,
    },
  ]
}

function peaks1DFromPayload(payload: unknown): SpectrumViewer1DPeak[] {
  const raw = extractPeaksFromPayload(payload)
  return raw.map((p) => ({
    x: p.ppm,
    y: p.intensity,
    label: p.label,
  }))
}

function extractChromatogramTraces(json: unknown): ChromatogramTrace[] {
  if (!isRecord(json)) return []
  const candidates: unknown[] = [
    json.chromatogram_traces,
    json.traces,
    json.chromatograms,
    json.xics,
    isRecord(json.lcms) ? json.lcms.traces : undefined,
    isRecord(json.feature_summary) ? json.feature_summary.traces : undefined,
  ].filter(Boolean) as unknown[]

  for (const c of candidates) {
    if (!Array.isArray(c) || c.length === 0) continue
    const traces: ChromatogramTrace[] = []
    for (const item of c) {
      if (!isRecord(item)) continue
      const name = String(item.name ?? item.label ?? item.id ?? "trace")
      const rt = coerceNumArray(item.rt ?? item.time ?? item.retention_time ?? item.rt_min)
      const intensity = coerceNumArray(item.intensity ?? item.i ?? item.y ?? item.intensities)
      if (!rt || !intensity || rt.length === 0 || rt.length !== intensity.length) continue
      const typeRaw = item.type ?? item.trace_type
      const type =
        typeof typeRaw === "string" && ["TIC", "BPC", "XIC", "EIC"].includes(typeRaw.toUpperCase())
          ? (typeRaw.toUpperCase() as ChromatogramTrace["type"])
          : undefined
      const mzNum = Number(item.mz ?? item.m_z ?? item.precursor_mz)
      traces.push({
        name,
        rt,
        intensity,
        type,
        mz: Number.isFinite(mzNum) ? mzNum : undefined,
      })
    }
    if (traces.length > 0) return traces
  }
  return []
}

function extractChromatogramFeatures(json: unknown): ChromatogramFeature[] {
  if (!isRecord(json)) return []
  const raw =
    json.features ??
    json.feature_list ??
    json.lcms_features ??
    (isRecord(json.lcms) ? json.lcms.features : undefined)
  if (!Array.isArray(raw)) return []
  const out: ChromatogramFeature[] = []
  for (const f of raw) {
    if (!isRecord(f)) continue
    const rtStart = Number(f.rt_start ?? f.rtStart ?? f.start_rt)
    const rtEnd = Number(f.rt_end ?? f.rtEnd ?? f.end_rt)
    const rtApex = Number(f.rt_apex ?? f.rtApex ?? f.apex_rt)
    const mzNum = Number(f.mz ?? f.m_z ?? f.precursor_mz)
    out.push({
      id: readStr(f.id) ?? undefined,
      mz: Number.isFinite(mzNum) ? mzNum : undefined,
      rtStart: Number.isFinite(rtStart) ? rtStart : undefined,
      rtEnd: Number.isFinite(rtEnd) ? rtEnd : undefined,
      rtApex: Number.isFinite(rtApex) ? rtApex : undefined,
      label: readStr(f.label ?? f.name) ?? undefined,
      purityLabel: readStr(f.purity_label ?? f.purity) ?? undefined,
    })
  }
  return out
}

function coerceMzIntensityPeaks(raw: unknown): MsmsMirrorObservedPeak[] {
  if (!Array.isArray(raw)) return []
  const out: MsmsMirrorObservedPeak[] = []
  for (const p of raw) {
    if (!isRecord(p)) continue
    const mz = Number(p.mz ?? p.m_z ?? p.mass)
    const intensity = Number(p.intensity ?? p.i ?? p.rel_abundance ?? p.relative_intensity ?? p.height)
    if (!Number.isFinite(mz)) continue
    out.push({
      mz,
      intensity: Number.isFinite(intensity) ? intensity : 1,
      label: readStr(p.label) ?? undefined,
    })
  }
  return out
}

function extractMsmsMirrorBundle(json: unknown): {
  observedPeaks: MsmsMirrorObservedPeak[]
  referencePeaks: MsmsMirrorReferencePeak[]
  fragmentMatches: MsmsMirrorFragmentMatch[]
  precursorMz?: number
  adduct?: string
  toleranceDa?: number
  tolerancePpm?: number
} | null {
  if (!isRecord(json)) return null
  const root = isRecord(json.msms) ? json.msms : isRecord(json.annotation) ? json.annotation : json

  const obsRaw =
    root.observed_peaks ??
    root.experimental_peaks ??
    root.peaks_observed ??
    root.observed ??
    json.observed_peaks
  const refRaw =
    root.reference_peaks ??
    root.theoretical_peaks ??
    root.synthetic_peaks ??
    json.reference_peaks

  const observedPeaks = coerceMzIntensityPeaks(obsRaw)
  const referencePeaks: MsmsMirrorReferencePeak[] = coerceMzIntensityPeaks(refRaw).map((p) => ({
    mz: p.mz,
    intensity: p.intensity,
    label: p.label,
  }))

  const fragRaw =
    root.fragment_matches ??
    root.annotations ??
    root.matches ??
    json.fragment_matches
  let fragmentMatches: MsmsMirrorFragmentMatch[] = []
  if (Array.isArray(fragRaw)) {
    fragmentMatches = fragRaw.filter(isRecord).map((m) => ({
      observed_mz: Number(m.observed_mz ?? m.obs_mz ?? m.mz),
      theoretical_mz: Number(m.theoretical_mz ?? m.theo_mz ?? m.expected_mz),
      label: readStr(m.label ?? m.ion ?? m.formula) ?? undefined,
      score: typeof m.score === "number" ? m.score : Number(m.score),
    }))
  }

  const precursorMz = Number(
    root.precursor_mz ?? root.precursor_m_z ?? json.precursor_mz ?? json.precursorMz,
  )
  const adduct = readStr(root.adduct ?? json.adduct) ?? undefined
  const toleranceDa = Number(root.tolerance_da ?? root.mass_tolerance_da)
  const tolerancePpm = Number(root.tolerance_ppm ?? root.msms_ppm_tolerance ?? json.msms_ppm_tolerance)

  if (observedPeaks.length === 0 && referencePeaks.length === 0 && fragmentMatches.length === 0) {
    return null
  }

  return {
    observedPeaks: observedPeaks.length > 0 ? observedPeaks : coerceMzIntensityPeaks(json.peaks),
    referencePeaks,
    fragmentMatches,
    precursorMz: Number.isFinite(precursorMz) ? precursorMz : undefined,
    adduct,
    toleranceDa: Number.isFinite(toleranceDa) ? toleranceDa : undefined,
    tolerancePpm: Number.isFinite(tolerancePpm) ? tolerancePpm : undefined,
  }
}

function extractAnnotationRowsForTable(json: unknown): { columns: string[]; rows: Record<string, unknown>[] } | null {
  if (!isRecord(json)) return null
  const raw =
    json.annotations ??
    json.fragment_annotations ??
    json.peak_assignments ??
    json.msms_table
  if (Array.isArray(raw) && raw.length > 0) {
    const rows = raw.filter(isRecord) as Record<string, unknown>[]
    const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 24)
    return { columns, rows: rows.slice(0, 300) }
  }
  return extractPeakTableForDisplay(json)
}

function sanitizeReportHtml(html: string): string {
  return html.replace(/<script\b[\s\S]*?<\/script>/gi, "")
}

function extractReportHtmlString(json: unknown, detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim().startsWith("<")) return sanitizeReportHtml(detail)
  if (!isRecord(json)) return null
  const h =
    json.html ??
    json.report_html ??
    json.body_html ??
    json.content_html ??
    (typeof json.body === "string" ? json.body : null)
  if (typeof h === "string" && h.trim()) return sanitizeReportHtml(h)
  return null
}

function extractMetadataEntries(json: unknown): { key: string; value: string }[] {
  if (!isRecord(json)) return []
  const skip = new Set([
    "artifact_json",
    "payload",
    "rows",
    "peaks",
    "x",
    "y",
    "spectrum",
    "warnings",
    "notes",
  ])
  const out: { key: string; value: string }[] = []
  for (const [k, v] of Object.entries(json)) {
    if (skip.has(k)) continue
    if (v == null) continue
    if (typeof v === "object") continue
    out.push({ key: k, value: String(v) })
  }
  return out.slice(0, 40)
}

async function downloadArtifactToDisk(artifactId: string, fallbackName: string) {
  const headers = new Headers()
  const token = readStoredAuthToken()
  if (token) headers.set("authorization", `Bearer ${token}`)
  const path = `/artifacts/${encodeURIComponent(artifactId)}/download`
  const response = await fetch(buildApiPath(path), {
    method: "GET",
    headers,
    cache: "no-store",
  })
  if (!response.ok) {
    const data = await response.json().catch(() => response.text())
    throw new ApiError(response.status, data, `Download failed (${response.status})`)
  }
  const blob = await response.blob()
  const cd = response.headers.get("content-disposition") || ""
  const m = /filename\*?=(?:UTF-8'')?["']?([^"';]+)/i.exec(cd)
  const name = m?.[1]?.trim() || fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  a.rel = "noopener"
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Matches ArtifactListRow from ArtifactBrowser (duplicated here to avoid circular imports). */
export type ArtifactViewerModalRow = {
  artifact_id: string
  title: string
  artifact_type: string
  job_id: string | null
  created_at: string | null
  sha256: string | null
  download_available: boolean
}

export type ArtifactViewerModalArtifact = {
  row: ArtifactViewerModalRow
  detail: unknown | null
}

export type ArtifactViewerModalProps = {
  artifact: ArtifactViewerModalArtifact | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onAddToEvidenceQueue?: () => void
  detailBusy?: boolean
  detailError?: string
  /** When set, users can list and add session comments linked to this artifact. */
  sessionId?: string | null
}

export function ArtifactViewerModal({
  artifact,
  open,
  onOpenChange,
  onAddToEvidenceQueue,
  detailBusy = false,
  detailError = "",
  sessionId = null,
}: ArtifactViewerModalProps) {
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState("")
  const sid = sessionId?.trim() ?? ""

  const [artifactCommentRows, setArtifactCommentRows] = useState<Record<string, unknown>[]>([])
  const [artifactCommentsBusy, setArtifactCommentsBusy] = useState(false)
  const [artifactCommentsErr, setArtifactCommentsErr] = useState("")
  const [artifactCommentType, setArtifactCommentType] = useState<string>(SESSION_COMMENT_TYPES[0])
  const [artifactCommentDraft, setArtifactCommentDraft] = useState("")
  const [artifactCommentPostBusy, setArtifactCommentPostBusy] = useState(false)
  const [artifactCommentPostErr, setArtifactCommentPostErr] = useState("")
  const [isMobile, setIsMobile] = useState(false)
  const [viewportHeight, setViewportHeight] = useState(720)

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      setIsMobile(false)
      return
    }
    const mq = window.matchMedia("(max-width: 640px)")
    const apply = () => setIsMobile(mq.matches)
    apply()
    mq.addEventListener("change", apply)
    const onResize = () => setViewportHeight(window.innerHeight)
    onResize()
    window.addEventListener("resize", onResize)
    return () => {
      mq.removeEventListener("change", apply)
      window.removeEventListener("resize", onResize)
    }
  }, [])

  const loadArtifactComments = useCallback(async () => {
    if (!sid || !artifact?.row?.artifact_id) {
      setArtifactCommentRows([])
      setArtifactCommentsErr("")
      return
    }
    const aid = artifact.row.artifact_id
    setArtifactCommentsBusy(true)
    setArtifactCommentsErr("")
    try {
      const all = await fetchSessionComments(sid)
      const filtered = all.filter((r) => sessionCommentMatchesArtifact(r, aid))
      setArtifactCommentRows(filtered)
    } catch (err) {
      setArtifactCommentsErr(formatApiError(err, "Could not load comments."))
      setArtifactCommentRows([])
    } finally {
      setArtifactCommentsBusy(false)
    }
  }, [sid, artifact?.row?.artifact_id])

  useEffect(() => {
    setDownloadError("")
  }, [artifact?.row?.artifact_id, open])

  useEffect(() => {
    if (!open || !sid) {
      setArtifactCommentRows([])
      setArtifactCommentsErr("")
      setArtifactCommentDraft("")
      setArtifactCommentPostErr("")
      return
    }
    void loadArtifactComments()
  }, [open, sid, artifact?.row?.artifact_id, loadArtifactComments])

  const row = artifact?.row ?? null
  const detail = artifact?.detail ?? null

  const artifactJson = useMemo(() => extractArtifactJson(detail), [detail])
  const artifactType = (row?.artifact_type ?? "other").trim().toLowerCase()

  const spectrumXY = useMemo(() => extractSpectrumXY(artifactJson ?? {}), [artifactJson])
  const peaks1d = useMemo(() => peaks1DFromPayload(artifactJson ?? {}), [artifactJson])
  const overlays1d = useMemo(() => overlaysFor1D(artifactJson ?? {}), [artifactJson])
  const peakGrid = useMemo(() => extractPeakTableForDisplay(artifactJson ?? {}), [artifactJson])
  const parsedPeaksDisplay = extractPeaksFromPayload(artifactJson ?? {})
  const warningsPayload = useMemo(() => extractWarnings(artifactJson ?? {}), [artifactJson])
  const notesPayload = extractNotes(artifactJson ?? {})
  const summary = useMemo(() => summarizeResult(artifactJson ?? {}), [artifactJson])

  const chromaTraces = useMemo(() => extractChromatogramTraces(artifactJson ?? {}), [artifactJson])
  const chromaFeatures = useMemo(() => extractChromatogramFeatures(artifactJson ?? {}), [artifactJson])

  const msmsBundle = useMemo(() => extractMsmsMirrorBundle(artifactJson ?? {}), [artifactJson])
  const msmsAnnotationTable = useMemo(() => extractAnnotationRowsForTable(artifactJson ?? {}), [artifactJson])

  const reportHtml = useMemo(
    () => extractReportHtmlString(artifactJson ?? {}, detail),
    [artifactJson, detail],
  )

  const metadataEntries = useMemo(() => extractMetadataEntries(artifactJson ?? {}), [artifactJson])

  const showSpectrum1D =
    spectrumXY != null && spectrumXY.x.length > 0 && spectrumXY.y.length > 0
  const mobileViewerHeight = isMobile ? Math.min(Math.max(Math.floor(viewportHeight * 0.38), 240), 380) : 360

  const handleDownload = () => {
    if (!row) return
    setDownloadError("")
    setDownloadBusy(true)
    void downloadArtifactToDisk(row.artifact_id, `${row.title || row.artifact_id}-artifact.bin`)
      .catch((err) => setDownloadError(formatApiError(err, "Download failed")))
      .finally(() => setDownloadBusy(false))
  }

  async function submitArtifactSessionComment() {
    if (!sid || !row?.artifact_id) return
    const comment = artifactCommentDraft.trim()
    if (!comment) {
      setArtifactCommentPostErr("Comment is required.")
      return
    }
    setArtifactCommentPostBusy(true)
    setArtifactCommentPostErr("")
    try {
      await postSessionComment(sid, {
        comment_type: artifactCommentType,
        comment,
        artifact_id: row.artifact_id,
      })
      setArtifactCommentDraft("")
      await loadArtifactComments()
    } catch (err) {
      setArtifactCommentPostErr(formatApiError(err, "Could not post comment."))
    } finally {
      setArtifactCommentPostBusy(false)
    }
  }

  function renderVisualization() {
    if (detailBusy || detail == null) return null

    switch (artifactType) {
      case "spectrum_preview":
      case "processed_spectrum":
        return showSpectrum1D ? (
          <div className="min-h-0 min-w-0 max-h-[420px] overflow-hidden rounded-md border bg-muted/10 p-2">
            <SpectrumViewer1D
              className="max-h-[400px]"
              x={spectrumXY!.x}
              y={spectrumXY!.y}
              peaks={peaks1d.length > 0 ? peaks1d : undefined}
              overlays={overlays1d}
              nucleus="1H"
              title={row?.title}
              height={mobileViewerHeight}
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No spectrum x/y arrays found in this artifact.</p>
        )

      case "peak_table":
        return (
          <div className="space-y-3">
            {showSpectrum1D ? (
              <div className="min-h-0 min-w-0 max-h-[360px] overflow-hidden rounded-md border bg-muted/10 p-2">
                <SpectrumViewer1D
                  className="max-h-[340px]"
                  x={spectrumXY!.x}
                  y={spectrumXY!.y}
                  peaks={peaks1d.length > 0 ? peaks1d : undefined}
                  overlays={overlays1d}
                  nucleus="1H"
                  height={mobileViewerHeight}
                />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No embedded spectrum series for this peak table.</p>
            )}
          </div>
        )

      case "nmr_metadata":
        return (
          <p className="text-sm text-muted-foreground">
            Metadata fields are listed in the summary and tables below (no spectrum graphic for this type).
          </p>
        )

      case "msms_annotation":
        return msmsBundle && msmsBundle.observedPeaks.length > 0 ? (
          <div className="min-h-0 min-w-0 overflow-hidden rounded-md border bg-muted/10 p-2">
            <MsmsMirrorPlot
              className="max-h-[400px]"
              observedPeaks={msmsBundle.observedPeaks}
              referencePeaks={msmsBundle.referencePeaks}
              fragmentMatches={msmsBundle.fragmentMatches}
              precursorMz={msmsBundle.precursorMz}
              adduct={msmsBundle.adduct}
              toleranceDa={msmsBundle.toleranceDa}
              tolerancePpm={msmsBundle.tolerancePpm}
              title={row?.title}
              height={mobileViewerHeight}
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No observed MS/MS peak list found in this payload (see tables / JSON for raw content).
          </p>
        )

      case "lcms_feature_table":
        return chromaTraces.length > 0 ? (
          <ChromatogramViewer
            className="max-h-[440px]"
            traces={chromaTraces}
            features={chromaFeatures.length > 0 ? chromaFeatures : undefined}
            title={row?.title}
            height={mobileViewerHeight}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            No chromatogram traces found; feature rows are shown in the tables section.
          </p>
        )

      case "unified_evidence":
      case "report_json":
        return (
          <div className="grid gap-2 sm:grid-cols-2">
            {summary.panels.showBestCandidate ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Best candidate (summary)</CardTitle>
                  <CardDescription className="text-xs">Qualitative extraction for review only.</CardDescription>
                </CardHeader>
                <CardContent className="text-sm">{summary.bestCandidate}</CardContent>
              </Card>
            ) : null}
            {summary.confidence != null ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Confidence hint</CardTitle>
                </CardHeader>
                <CardContent className="text-sm">{summary.confidence.toFixed(1)}%</CardContent>
              </Card>
            ) : null}
          </div>
        )

      case "report_html":
        return reportHtml ? (
          <iframe
            sandbox=""
            title="Report HTML preview"
            srcDoc={reportHtml}
            className="min-h-[320px] w-full min-w-0 rounded-md border bg-background"
          />
        ) : (
          <p className="text-sm text-muted-foreground">No HTML body found on this artifact.</p>
        )

      default:
        return (
          <p className="text-sm text-muted-foreground">
            No dedicated renderer for this artifact type; see tables and developer JSON.
          </p>
        )
    }
  }

  function renderTablesSection() {
    if (detailBusy || detail == null) return null

    const blocks: React.ReactNode[] = []

    if (peakGrid != null && peakGrid.rows.length > 0 && artifactType !== "report_html") {
      const gridTitle =
        artifactType === "lcms_feature_table" ? "LC-MS feature table" : "Peak / feature table"
      blocks.push(
        <div key="peak-grid" className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">{gridTitle}</p>
          <ScrollArea className="max-h-64 rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  {peakGrid.columns.map((c) => (
                    <TableHead key={c} className="whitespace-nowrap">
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {peakGrid.rows.map((r, i) => (
                  <TableRow key={i}>
                    {peakGrid.columns.map((c) => (
                      <TableCell key={c} className="max-w-[220px] truncate font-mono text-xs">
                        {r[c] != null ? String(r[c]) : "—"}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>,
      )
    }

    if (
      parsedPeaksDisplay.length > 0 &&
      !(peakGrid != null && peakGrid.rows.length > 0) &&
      ["spectrum_preview", "processed_spectrum", "peak_table"].includes(artifactType)
    ) {
      blocks.push(
        <div key="parsed-peaks" className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Parsed peaks</p>
          <ScrollArea className="max-h-64 rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>δ (ppm)</TableHead>
                  <TableHead>Intensity</TableHead>
                  <TableHead>Label</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {parsedPeaksDisplay.slice(0, 300).map((p, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs">{p.ppm.toFixed(4)}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {p.intensity != null ? p.intensity.toExponential(3) : "—"}
                    </TableCell>
                    <TableCell className="text-xs">{p.label ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>,
      )
    }

    if (artifactType === "nmr_metadata" && metadataEntries.length > 0) {
      blocks.push(
        <div key="meta" className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Metadata</p>
          <ScrollArea className="max-h-56 rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {metadataEntries.map((e) => (
                  <TableRow key={e.key}>
                    <TableCell className="font-mono text-xs">{e.key}</TableCell>
                    <TableCell className="max-w-[280px] truncate text-xs">{e.value}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>,
      )
    }

    if (artifactType === "msms_annotation" && msmsAnnotationTable != null && msmsAnnotationTable.rows.length > 0) {
      blocks.push(
        <div key="msms-ann" className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Annotation table</p>
          <ScrollArea className="max-h-64 rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  {msmsAnnotationTable.columns.map((c) => (
                    <TableHead key={c} className="whitespace-nowrap">
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {msmsAnnotationTable.rows.map((r, i) => (
                  <TableRow key={i}>
                    {msmsAnnotationTable.columns.map((c) => (
                      <TableCell key={c} className="max-w-[220px] truncate font-mono text-xs">
                        {r[c] != null ? String(r[c]) : "—"}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>,
      )
    }

    if (artifactType === "unified_evidence" || artifactType === "report_json") {
      if (summary.rankedCandidates.length > 0) {
        blocks.push(
          <div key="ranked" className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Ranked candidates (subset)</p>
            <ScrollArea className="max-h-56 rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>Label</TableHead>
                    <TableHead>Score</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.rankedCandidates.slice(0, 50).map((c, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-xs">{i + 1}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs">
                        {String(c.name ?? c.label ?? c.formula ?? c.id ?? "—")}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {typeof c.score === "number" ? c.score : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          </div>,
        )
      }
    }

    if (blocks.length === 0) return null
    return <div className="space-y-4">{blocks}</div>
  }

  const warnNotes: string[] = []
  if (notesPayload) warnNotes.push(notesPayload)
  warnNotes.push(...warningsPayload)
  if (summary.warnings.length > 0) warnNotes.push(...summary.warnings)
  if (summary.contradictions.length > 0) warnNotes.push(...summary.contradictions.map((c) => `Contradiction note: ${c}`))
  if (summary.notes.length > 0) warnNotes.push(...summary.notes.map((n) => `Note: ${n}`))

  const tablesSection = renderTablesSection()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[min(90vh,880px)] w-[95vw] max-w-4xl overflow-x-hidden overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="pr-8">{row?.title ?? "Artifact"}</DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {row ? (
              <>
                <span className="text-muted-foreground">artifact id:</span> {row.artifact_id}
                {row.job_id ? (
                  <>
                    {" "}
                    · <span className="text-muted-foreground">job:</span> {row.job_id}
                  </>
                ) : null}
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {detailBusy ? <p className="text-sm text-muted-foreground">Loading artifact…</p> : null}
        {detailError ? <p className="text-sm text-destructive">{detailError}</p> : null}
        {downloadError ? <p className="text-sm text-destructive">{downloadError}</p> : null}

        {row && detail != null && !detailBusy ? (
          <div className="space-y-6">
            <section className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Summary</p>
              <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 px-3 py-2 text-sm">
                <Badge variant="outline" className="font-mono text-[10px]">
                  {row.artifact_type}
                </Badge>
                <span className="text-muted-foreground">Created:</span>
                <span className="font-mono text-xs">{row.created_at ?? "—"}</span>
              </div>
            </section>

            <section className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Visualization</p>
              {renderVisualization()}
            </section>

            {tablesSection ? (
              <section className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Tables</p>
                {tablesSection}
              </section>
            ) : null}

            {warnNotes.length > 0 ? (
              <section className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Warnings / notes</p>
                <ul className="list-disc space-y-1 pl-5 text-xs text-amber-900 dark:text-amber-200">
                  {warnNotes.slice(0, 24).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Provenance</p>
              <div className="rounded-md border px-3 py-2 text-xs">
                <div className="grid gap-1 sm:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground">Job ID</span>
                    <div className="font-mono">{row.job_id ?? "—"}</div>
                  </div>
                  <div>
                    <span className="text-muted-foreground">SHA-256</span>
                    <div className="break-all font-mono text-[10px]">{row.sha256 ?? "—"}</div>
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-3">
              <p className="text-xs font-medium text-muted-foreground">Comments</p>
              {!sid ? (
                <p className="text-xs text-muted-foreground">
                  Connect a saved SpectraCheck session to view and add comments linked to this artifact.
                </p>
              ) : (
                <>
                  {artifactCommentsErr ? <p className="text-xs text-destructive">{artifactCommentsErr}</p> : null}
                  {artifactCommentsBusy ? <p className="text-xs text-muted-foreground">Loading comments…</p> : null}
                  <div>
                    <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">View linked comments</p>
                    <div className="overflow-x-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Type</TableHead>
                            <TableHead className="text-xs">Comment</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {artifactCommentRows.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={2} className="text-xs text-muted-foreground">
                                No comments linked to this artifact yet.
                              </TableCell>
                            </TableRow>
                          ) : (
                            artifactCommentRows.map((cr, i) => (
                              <TableRow
                                key={String((cr as { id?: unknown }).id ?? (cr as { comment_id?: unknown }).comment_id ?? `ac-${i}`)}
                              >
                                <TableCell className="align-top text-xs">
                                  <Badge variant="outline" className="font-normal">
                                    {pickCommentType(cr as Record<string, unknown>)}
                                  </Badge>
                                </TableCell>
                                <TableCell className="max-w-prose align-top text-xs whitespace-pre-wrap break-words">
                                  {pickCommentText(cr as Record<string, unknown>) || "—"}
                                </TableCell>
                              </TableRow>
                            ))
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                  <div className="space-y-2 rounded-md border bg-muted/10 px-3 py-2">
                    <p className="text-[11px] font-medium text-muted-foreground">Add comment</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label className="text-xs">Comment type</Label>
                        <Select value={artifactCommentType} onValueChange={setArtifactCommentType}>
                          <SelectTrigger className="h-8 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {SESSION_COMMENT_TYPES.map((t) => (
                              <SelectItem key={t} value={t} className="text-xs">
                                {t}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="artifact-modal-comment" className="text-xs">
                        Comment
                      </Label>
                      <Textarea
                        id="artifact-modal-comment"
                        value={artifactCommentDraft}
                        onChange={(e) => setArtifactCommentDraft(e.target.value)}
                        rows={3}
                        className="text-sm"
                      />
                    </div>
                    {artifactCommentPostErr ? (
                      <p className="text-xs text-destructive">{artifactCommentPostErr}</p>
                    ) : null}
                    <Button
                      type="button"
                      size="sm"
                      disabled={artifactCommentPostBusy || artifactCommentsBusy}
                      onClick={() => void submitArtifactSessionComment()}
                    >
                      {artifactCommentPostBusy ? "Posting…" : "Post comment"}
                    </Button>
                  </div>
                </>
              )}
            </section>

            <section className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Developer JSON</p>
              <DeveloperJsonPanel data={detail} />
            </section>

            <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-start">
              {row.download_available ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={downloadBusy}
                  onClick={() => void handleDownload()}
                >
                  {downloadBusy ? "Downloading…" : "Download artifact"}
                </Button>
              ) : null}
              {onAddToEvidenceQueue ? (
                <Button type="button" size="sm" onClick={onAddToEvidenceQueue}>
                  Add to Evidence Queue
                </Button>
              ) : null}
              <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                Close
              </Button>
            </DialogFooter>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
