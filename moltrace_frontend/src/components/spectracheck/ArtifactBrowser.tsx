"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { QualityAssessmentCard } from "@/src/components/spectracheck/QualityAssessmentCard"
import { QualityFindingsTable } from "@/src/components/spectracheck/QualityFindingsTable"
import { QualityStatusBadge } from "@/src/components/spectracheck/QualityStatusBadge"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError, apiFetch, buildApiPath, readStoredAuthToken } from "@/lib/api/client"
import { parseQualityControlPayload } from "@/src/lib/spectracheck/quality-control-assessment"
import type { EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"
import { extractMethodProvenanceFromUnknown } from "@/src/lib/spectracheck/evidence-method-provenance"
import { extractMlModelProvenanceFromUnknown } from "@/src/lib/ml/model-provenance-extract"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { ArtifactViewerModal } from "@/src/components/spectracheck/ArtifactViewerModal"

const ARTIFACT_TYPE_LABELS = [
  "spectrum_preview",
  "peak_table",
  "processed_spectrum",
  "nmr_metadata",
  "msms_annotation",
  "lcms_feature_table",
  "unified_evidence",
  "report_json",
  "report_html",
  "other",
] as const

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return null
}

function readBool(v: unknown): boolean | null {
  if (typeof v === "boolean") return v
  if (typeof v === "string") {
    const s = v.trim().toLowerCase()
    if (s === "true") return true
    if (s === "false") return false
  }
  return null
}

export type ArtifactListRow = {
  artifact_id: string
  title: string
  artifact_type: string
  job_id: string | null
  created_at: string | null
  sha256: string | null
  /** When false, hide download affordance */
  download_available: boolean
}

function normalizeArtifactListPayload(data: unknown): ArtifactListRow[] {
  const src = Array.isArray(data)
    ? data
    : isRecord(data) && Array.isArray(data.artifacts)
      ? data.artifacts
      : isRecord(data) && Array.isArray(data.items)
        ? data.items
        : isRecord(data) && Array.isArray(data.results)
          ? data.results
          : []
  const out: ArtifactListRow[] = []
  for (const item of src) {
    if (!isRecord(item)) continue
    const artifact_id =
      readStr(item.artifact_id) ??
      readStr(item.id) ??
      readStr(item.artifactId)
    if (!artifact_id) continue
    const artifact_type =
      readStr(item.artifact_type) ??
      readStr(item.type) ??
      readStr(item.kind) ??
      "other"
    const title =
      readStr(item.title) ??
      readStr(item.name) ??
      readStr(item.label) ??
      artifact_id
    const job_id =
      readStr(item.job_id) ?? readStr(item.jobId) ?? readStr(item.analysis_job_id)
    const created_at =
      readStr(item.created_at) ??
      readStr(item.createdAt) ??
      readStr(item.created) ??
      null
    const sha256 =
      readStr(item.sha256) ??
      readStr(item.file_sha256) ??
      readStr(item.checksum_sha256)
    const dlExplicit = readBool(item.download_available ?? item.has_download)
    const download_available = dlExplicit !== false
    out.push({
      artifact_id,
      title,
      artifact_type,
      job_id,
      created_at,
      sha256,
      download_available,
    })
  }
  return out
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

function looksEvidenceLike(json: unknown): boolean {
  if (!isRecord(json)) return false
  const keys = Object.keys(json).map((k) => k.toLowerCase())
  const hints = [
    "evidence",
    "confidence",
    "candidates",
    "peaks",
    "fragments",
    "mz",
    "score",
    "unified",
    "annotations",
    "formula",
    "match",
    "annotation",
    "feature",
    "report",
  ]
  return hints.some((h) => keys.some((k) => k.includes(h)))
}

function artifactTypeToLayer(t: string): EvidenceLayerType {
  const n = t.trim().toLowerCase()
  switch (n) {
    case "spectrum_preview":
    case "processed_spectrum":
    case "peak_table":
    case "nmr_metadata":
      return "processed_1h"
    case "msms_annotation":
      return "msms_annotation"
    case "lcms_feature_table":
      return "lcms_feature_detection"
    case "unified_evidence":
      return "unified_confidence"
    case "report_json":
    case "report_html":
      return "report"
    default:
      return "report"
  }
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

type Props = {
  sessionId: string | null
}

export function ArtifactBrowser({ sessionId }: Props) {
  const { addEvidenceItem } = useSpectraCheckEvidence()
  const [rows, setRows] = useState<ArtifactListRow[]>([])
  const [listBusy, setListBusy] = useState(false)
  const [listError, setListError] = useState("")

  const [open, setOpen] = useState(false)
  const [activeRow, setActiveRow] = useState<ArtifactListRow | null>(null)
  const [detail, setDetail] = useState<unknown>(null)
  const [detailBusy, setDetailBusy] = useState(false)
  const [detailError, setDetailError] = useState("")
  const [downloadBusy, setDownloadBusy] = useState(false)

  const [artifactQcById, setArtifactQcById] = useState<Record<string, unknown>>({})
  const [qcAssessArtifactId, setQcAssessArtifactId] = useState<string | null>(null)
  const [qcViewArtifactId, setQcViewArtifactId] = useState<string | null>(null)
  const qcArtifactFindingsRef = useRef<HTMLDivElement | null>(null)

  const hasSession = Boolean(sessionId?.trim())

  const loadList = useCallback(async () => {
    const sid = sessionId?.trim()
    if (!sid) {
      setRows([])
      return
    }
    setListBusy(true)
    setListError("")
    try {
      const data = await apiFetch<unknown>(
        `/spectracheck/sessions/${encodeURIComponent(sid)}/artifacts`,
        { method: "GET" },
      )
      setRows(normalizeArtifactListPayload(data))
    } catch (err) {
      setListError(formatApiError(err, "Could not load session artifacts."))
      setRows([])
    } finally {
      setListBusy(false)
    }
  }, [sessionId])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const artifactJson = useMemo(() => extractArtifactJson(detail), [detail])

  async function openArtifact(row: ArtifactListRow) {
    setActiveRow(row)
    setDetail(null)
    setDetailError("")
    setOpen(true)
    setDetailBusy(true)
    try {
      const data = await apiFetch<unknown>(`/artifacts/${encodeURIComponent(row.artifact_id)}`, {
        method: "GET",
      })
      setDetail(data)
    } catch (err) {
      setDetailError(formatApiError(err, "Could not load artifact."))
    } finally {
      setDetailBusy(false)
    }
  }

  function handleDownload(row: ArtifactListRow) {
    setDownloadBusy(true)
    void downloadArtifactToDisk(row.artifact_id, `${row.title || row.artifact_id}-artifact.bin`)
      .catch((err) => {
        console.error(formatApiError(err, "Artifact download failed"))
      })
      .finally(() => setDownloadBusy(false))
  }

  function shouldOfferEvidenceQueue(row: ArtifactListRow, json: unknown): boolean {
    if (looksEvidenceLike(json)) return true
    const t = row.artifact_type.trim().toLowerCase()
    return (
      t === "spectrum_preview" ||
      t === "peak_table" ||
      t === "processed_spectrum" ||
      t === "msms_annotation" ||
      t === "lcms_feature_table" ||
      t === "unified_evidence" ||
      t === "report_json" ||
      t === "report_html" ||
      t === "nmr_metadata"
    )
  }

  const runArtifactQcAssess = useCallback(async (artifactId: string) => {
    const aid = artifactId.trim()
    if (!aid) return
    setQcAssessArtifactId(aid)
    try {
      const res = await apiFetch<unknown>(`/quality-control/artifacts/${encodeURIComponent(aid)}/assess`, {
        method: "POST",
        body: {},
      })
      setArtifactQcById((prev) => ({ ...prev, [aid]: res }))
    } catch {
      try {
        const g = await apiFetch<unknown>(`/quality-control/artifacts/${encodeURIComponent(aid)}`, { method: "GET" })
        setArtifactQcById((prev) => ({ ...prev, [aid]: g }))
      } catch {
        // QC optional — browsing artifacts remains available.
      }
    } finally {
      setQcAssessArtifactId(null)
    }
  }, [])

  const loadArtifactQcOnly = useCallback(async (artifactId: string) => {
    const aid = artifactId.trim()
    if (!aid) return
    setQcAssessArtifactId(aid)
    try {
      const g = await apiFetch<unknown>(`/quality-control/artifacts/${encodeURIComponent(aid)}`, { method: "GET" })
      setArtifactQcById((prev) => ({ ...prev, [aid]: g }))
    } catch {
      // ignore
    } finally {
      setQcAssessArtifactId(null)
    }
  }, [])

  const qcArtifactViewPayload = qcViewArtifactId ? artifactQcById[qcViewArtifactId] : undefined
  const qcArtifactViewParsed = useMemo(
    () =>
      qcArtifactViewPayload !== undefined
        ? parseQualityControlPayload(qcArtifactViewPayload, { targetType: "artifact", modality: "spectracheck_artifact" })
        : null,
    [qcArtifactViewPayload],
  )

  function renderArtifactQcCell(row: ArtifactListRow) {
    const raw = artifactQcById[row.artifact_id]
    const parsed =
      raw !== undefined
        ? parseQualityControlPayload(raw, { targetType: "artifact", modality: row.artifact_type })
        : null
    const busy = qcAssessArtifactId === row.artifact_id
    const hasAssessment = raw !== undefined
    return (
      <div className="flex min-w-[200px] max-w-[280px] flex-col gap-1.5">
        <QualityStatusBadge status={parsed?.qcStatus ?? "not_assessed"} />
        <div className="flex flex-wrap gap-1">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8"
            disabled={busy}
            onClick={() => void runArtifactQcAssess(row.artifact_id)}
          >
            {busy ? "Running…" : "Run QC"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            disabled={!hasAssessment}
            onClick={() => setQcViewArtifactId(row.artifact_id)}
          >
            View QC
          </Button>
        </div>
      </div>
    )
  }

  function handleAddEvidence(row: ArtifactListRow, json: unknown) {
    const response = {
      artifact_id: row.artifact_id,
      artifact_type: row.artifact_type,
      artifact_json: json,
    }
    addEvidenceItem({
      layer: artifactTypeToLayer(row.artifact_type),
      title: row.title || row.artifact_id,
      sourceTab: "Session Artifacts",
      status: "ready",
      endpoint: `/artifacts/${row.artifact_id}`,
      response,
      provenance: row.sha256 ? { sha256: row.sha256 } : undefined,
      ...extractMethodProvenanceFromUnknown(json, response),
      ...extractMlModelProvenanceFromUnknown(json, response),
    })
  }

  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Session Artifacts
          <InfoTooltip
            content="Derived outputs from analysis jobs, such as spectrum previews, peak tables, MS/MS annotations, LC-MS feature tables, unified evidence, and reports."
            label="Session Artifacts information"
          />
        </CardTitle>
        <CardDescription>
          Browse artifacts attached to this SpectraCheck session.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!hasSession ? (
          <p className="text-sm text-muted-foreground">Load or save a backend session to list artifacts.</p>
        ) : null}
        {listError ? <p className="text-sm text-destructive">{listError}</p> : null}

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={!hasSession || listBusy} onClick={() => void loadList()}>
            {listBusy ? "Refreshing…" : "Refresh list"}
          </Button>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Job ID</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>SHA-256</TableHead>
                <TableHead>Quality control</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {listBusy ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-sm text-muted-foreground">
                    Loading artifacts…
                  </TableCell>
                </TableRow>
              ) : null}
              {!listBusy && rows.length === 0 && hasSession ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-sm text-muted-foreground">
                    No artifacts for this session.
                  </TableCell>
                </TableRow>
              ) : null}
              {!listBusy &&
                rows.map((row) => (
                  <TableRow key={row.artifact_id}>
                    <TableCell className="max-w-[200px] truncate font-medium">{row.title}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {row.artifact_type}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[120px] truncate font-mono text-xs">{row.job_id ?? "—"}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs">{row.created_at ?? "—"}</TableCell>
                    <TableCell className="max-w-[140px] truncate font-mono text-[10px]">{row.sha256 ?? "—"}</TableCell>
                    <TableCell className="align-top">{renderArtifactQcCell(row)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-1">
                        <Button type="button" variant="secondary" size="sm" onClick={() => void openArtifact(row)}>
                          View
                        </Button>
                        {row.download_available ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={downloadBusy}
                            onClick={() => handleDownload(row)}
                          >
                            Download
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>

        <p className="text-[11px] text-muted-foreground">
          Artifact types include: {ARTIFACT_TYPE_LABELS.join(", ")}.
        </p>
      </CardContent>

      <Dialog open={qcViewArtifactId != null} onOpenChange={(o) => !o && setQcViewArtifactId(null)}>
        <DialogContent className="max-h-[min(90vh,880px)] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Artifact quality assessment</DialogTitle>
            <DialogDescription className="font-mono text-xs">
              {qcViewArtifactId ? (
                <>
                  <span className="text-muted-foreground">artifact id:</span> {qcViewArtifactId}
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          {qcViewArtifactId && qcArtifactViewParsed && qcArtifactViewPayload !== undefined ? (
            <div className="space-y-4">
              <QualityAssessmentCard
                qcStatus={qcArtifactViewParsed.qcStatus}
                readinessLabel={qcArtifactViewParsed.readinessLabel}
                qualityScore={qcArtifactViewParsed.qualityScore}
                targetType={qcArtifactViewParsed.targetType}
                modality={qcArtifactViewParsed.modality}
                warningsCount={qcArtifactViewParsed.warningsCount}
                findingsCount={qcArtifactViewParsed.findingsCount}
                recommendedActions={qcArtifactViewParsed.recommendedActions}
                showOverride={qcArtifactViewParsed.showOverride}
                developerJson={qcArtifactViewPayload}
                runQcBusy={qcAssessArtifactId === qcViewArtifactId}
                onRunQc={() => void runArtifactQcAssess(qcViewArtifactId)}
                onViewFindings={() => qcArtifactFindingsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              />
              <div ref={qcArtifactFindingsRef}>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Findings</p>
                <QualityFindingsTable findings={qcArtifactViewParsed.findings} />
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => qcViewArtifactId && void loadArtifactQcOnly(qcViewArtifactId)}
                disabled={qcAssessArtifactId === qcViewArtifactId}
              >
                Refresh from server
              </Button>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <ArtifactViewerModal
        sessionId={sessionId}
        artifact={activeRow ? { row: activeRow, detail } : null}
        open={open}
        onOpenChange={setOpen}
        detailBusy={detailBusy}
        detailError={detailError}
        onAddToEvidenceQueue={
          activeRow && detail != null && shouldOfferEvidenceQueue(activeRow, artifactJson)
            ? () => handleAddEvidence(activeRow, artifactJson)
            : undefined
        }
      />
    </Card>
  )
}
