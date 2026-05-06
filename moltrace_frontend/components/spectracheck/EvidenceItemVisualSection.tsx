"use client"

import { useMemo, useState } from "react"
import { ChromatogramViewer } from "@/components/science/ChromatogramViewer"
import { MsmsMirrorPlot } from "@/components/science/MsmsMirrorPlot"
import { SpectrumViewer1D } from "@/components/science/SpectrumViewer1D"
import type { SpectrumViewer1DOverlay } from "@/components/science/SpectrumViewer1D"
import { ArtifactViewerModal, type ArtifactViewerModalRow } from "@/src/components/spectracheck/ArtifactViewerModal"
import { FragmentTreeViewer } from "@/src/components/science/FragmentTreeViewer"
import { Nmr2DViewer } from "@/src/components/science/Nmr2DViewer"
import {
  extractArtifactIdFromEvidence,
  extractChromatogramFeaturesForEvidence,
  extractChromatogramTracesForEvidence,
  extractFragmentationGraphForEvidence,
  extractMsmsMirrorBundleForEvidence,
  extractNmr2dPeaksForEvidence,
  getEvidenceVisualPayload,
  hasSpectrumXyPreview,
  peaks1DFromEvidencePayload,
} from "@/src/lib/spectracheck/evidence-visual-extract"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { apiFetch } from "@/src/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { extractPredictedOverlay, extractSpectrumXY } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { Eye, Layers } from "lucide-react"

const COMPACT_VIZ_H = 200

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

type Props = {
  item: EvidenceItem
  /** When set, artifact viewer can post/list session comments for linked artifacts. */
  spectracheckSessionId?: string | null
}

export function EvidenceItemVisualSection({ item, spectracheckSessionId = null }: Props) {
  const { updateEvidenceItem } = useSpectraCheckEvidence()

  const payload = useMemo(() => getEvidenceVisualPayload(item.response), [item.response])

  const artifactId = useMemo(() => extractArtifactIdFromEvidence(item.response), [item.response])

  const spectrumXy = useMemo(() => extractSpectrumXY(payload ?? {}), [payload])
  const showSpectrum = hasSpectrumXyPreview(payload)
  const peaks1d = useMemo(() => peaks1DFromEvidencePayload(payload ?? {}), [payload])
  const overlays1d = useMemo(() => overlaysFor1D(payload ?? {}), [payload])

  const msmsBundle = useMemo(() => extractMsmsMirrorBundleForEvidence(payload ?? {}), [payload])
  const chromaTraces = useMemo(() => extractChromatogramTracesForEvidence(payload ?? {}), [payload])
  const chromaFeatures = useMemo(() => extractChromatogramFeaturesForEvidence(payload ?? {}), [payload])
  const nmr2dPeaks = useMemo(() => extractNmr2dPeaksForEvidence(payload ?? {}), [payload])
  const fragGraph = useMemo(() => extractFragmentationGraphForEvidence(payload ?? {}), [payload])

  const hasMsmsMirror =
    msmsBundle != null &&
    (msmsBundle.observedPeaks.length > 0 ||
      msmsBundle.referencePeaks.length > 0 ||
      msmsBundle.fragmentMatches.length > 0)

  const showMsmsMirrorPlot = msmsBundle != null && msmsBundle.observedPeaks.length > 0

  const showMsmsFallbackTable =
    msmsBundle != null &&
    msmsBundle.observedPeaks.length === 0 &&
    (msmsBundle.referencePeaks.length > 0 || msmsBundle.fragmentMatches.length > 0)

  const hasChroma = chromaTraces.length > 0
  const hasNmr2d = nmr2dPeaks.length > 0
  const hasFragViewer = fragGraph.nodes.length > 0
  const hasFragEdgesOnly = !hasFragViewer && fragGraph.edges.length > 0

  const showOuter =
    Boolean(artifactId) ||
    showSpectrum ||
    hasMsmsMirror ||
    hasChroma ||
    hasNmr2d ||
    hasFragViewer ||
    hasFragEdgesOnly ||
    Boolean(item.visualReviewed)

  const [artifactOpen, setArtifactOpen] = useState(false)
  const [artifactDetail, setArtifactDetail] = useState<unknown | null>(null)
  const [artifactBusy, setArtifactBusy] = useState(false)
  const [artifactErr, setArtifactErr] = useState("")

  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewComment, setReviewComment] = useState("")

  async function openArtifactModal() {
    if (!artifactId) return
    setArtifactErr("")
    setArtifactBusy(true)
    setArtifactDetail(null)
    try {
      const data = await apiFetch<unknown>(`/artifacts/${encodeURIComponent(artifactId)}`, { method: "GET" })
      setArtifactDetail(data)
      setArtifactOpen(true)
    } catch (err) {
      setArtifactErr(formatApiError(err, "Could not load artifact."))
    } finally {
      setArtifactBusy(false)
    }
  }

  const artifactModalRow: ArtifactViewerModalRow | null = useMemo(() => {
    if (!artifactId) return null
    const r = item.response
    const typ =
      r != null && typeof r === "object" && !Array.isArray(r) && "artifact_type" in r
        ? String((r as Record<string, unknown>).artifact_type ?? "other")
        : "other"
    return {
      artifact_id: artifactId,
      title: item.title,
      artifact_type: typ,
      job_id: null,
      created_at: item.createdAt,
      sha256: item.provenance?.sha256 ?? null,
      download_available: true,
    }
  }, [artifactId, item.createdAt, item.provenance?.sha256, item.response, item.title])

  function submitVisualReview() {
    const c = reviewComment.trim()
    updateEvidenceItem(item.id, {
      visualReviewed: true,
      visualReviewComment: c.length > 0 ? c : undefined,
    })
    setReviewOpen(false)
    setReviewComment("")
  }

  if (!showOuter) return null

  return (
    <div className="mt-3 min-w-0 border-t border-border/40 pt-3">
      <Collapsible className="min-w-0">
        <CollapsibleTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="h-8 w-full justify-between px-2 text-xs">
            <span className="flex items-center gap-2">
              <Layers className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
              Visual previews
            </span>
            {item.visualReviewed ? (
              <Badge variant="secondary" className="text-[10px] font-normal">
                Preview inspected
              </Badge>
            ) : null}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2 min-w-0 space-y-3 data-[state=closed]:hidden">
          <p className="text-[11px] text-muted-foreground">
            Compact plots for quick inspection only; interpretation still requires expert review.
          </p>

          {artifactId ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="h-8"
                disabled={artifactBusy}
                onClick={() => void openArtifactModal()}
              >
                <Eye className="mr-1 h-3.5 w-3.5" aria-hidden />
                {artifactBusy ? "Opening…" : "View artifact"}
              </Button>
              {artifactErr ? <span className="text-xs text-destructive">{artifactErr}</span> : null}
            </div>
          ) : null}

          {showSpectrum && spectrumXy ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  1D spectrum preview
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <div className="max-h-[220px] min-h-0 min-w-0 overflow-hidden">
                  <SpectrumViewer1D
                    className="max-h-[200px]"
                    height={COMPACT_VIZ_H}
                    x={spectrumXy.x}
                    y={spectrumXy.y}
                    peaks={peaks1d.length > 0 ? peaks1d : undefined}
                    overlays={overlays1d}
                    nucleus="1H"
                  />
                </div>
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {showMsmsMirrorPlot && msmsBundle ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  MS/MS mirror preview
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <div className="max-h-[220px] min-w-0 overflow-hidden">
                  <MsmsMirrorPlot
                    className="max-h-[200px]"
                    height={COMPACT_VIZ_H}
                    observedPeaks={msmsBundle.observedPeaks}
                    referencePeaks={msmsBundle.referencePeaks}
                    fragmentMatches={msmsBundle.fragmentMatches}
                    precursorMz={msmsBundle.precursorMz}
                    adduct={msmsBundle.adduct}
                    toleranceDa={msmsBundle.toleranceDa}
                    tolerancePpm={msmsBundle.tolerancePpm}
                  />
                </div>
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {showMsmsFallbackTable && msmsBundle ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  MS/MS peaks / matches (table)
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <ScrollArea className="max-h-48 rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Type</TableHead>
                        <TableHead>m/z</TableHead>
                        <TableHead>Intensity</TableHead>
                        <TableHead>Label</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {msmsBundle.referencePeaks.map((p, i) => (
                        <TableRow key={`ref-${i}`}>
                          <TableCell className="text-xs">Reference</TableCell>
                          <TableCell className="font-mono text-xs">{p.mz.toFixed(4)}</TableCell>
                          <TableCell className="font-mono text-xs">{p.intensity}</TableCell>
                          <TableCell className="text-xs">{p.label ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                      {msmsBundle.fragmentMatches.map((m, i) => (
                        <TableRow key={`fm-${i}`}>
                          <TableCell className="text-xs">Match</TableCell>
                          <TableCell className="font-mono text-xs">
                            {typeof m.observed_mz === "number" && Number.isFinite(m.observed_mz)
                              ? m.observed_mz.toFixed(4)
                              : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {m.score != null && Number.isFinite(m.score) ? m.score.toFixed(3) : "—"}
                          </TableCell>
                          <TableCell className="max-w-[140px] truncate text-xs">{m.label ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {hasChroma ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  LC-MS chromatogram preview
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <ChromatogramViewer
                  className="max-h-[220px]"
                  height={COMPACT_VIZ_H}
                  traces={chromaTraces}
                  features={chromaFeatures.length > 0 ? chromaFeatures : undefined}
                />
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {hasNmr2d ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  2D NMR peak preview
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <Nmr2DViewer className="max-h-[240px]" height={COMPACT_VIZ_H + 20} peaks={nmr2dPeaks} />
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {hasFragViewer ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  Fragmentation tree preview
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <FragmentTreeViewer nodes={fragGraph.nodes} edges={fragGraph.edges} />
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {hasFragEdgesOnly ? (
            <Collapsible defaultOpen={false} className="min-w-0 rounded-md border bg-muted/10">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-full justify-start px-2 text-xs font-medium text-muted-foreground"
                >
                  Fragmentation edges (table)
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="px-2 pb-2">
                <ScrollArea className="max-h-48 rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Source</TableHead>
                        <TableHead>Target</TableHead>
                        <TableHead>Loss</TableHead>
                        <TableHead>Δ m/z</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fragGraph.edges.map((e, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-mono text-xs">{e.source}</TableCell>
                          <TableCell className="font-mono text-xs">{e.target}</TableCell>
                          <TableCell className="text-xs">{e.loss ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {typeof e.delta_mz === "number" && Number.isFinite(e.delta_mz)
                              ? e.delta_mz.toFixed(4)
                              : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {item.visualReviewComment ? (
            <p className="text-[11px] text-muted-foreground">
              <span className="font-medium text-foreground">Inspection note:</span> {item.visualReviewComment}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 border-t border-border/30 pt-2">
            <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => setReviewOpen(true)}>
              Mark visual evidence reviewed
            </Button>
            <p className="text-[10px] text-muted-foreground">
              Records that previews were viewed here — not scientific approval or QC sign-off.
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>

      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Record visual inspection</DialogTitle>
            <DialogDescription>
              This marks that embedded previews were reviewed in the queue. It does not substitute instrument QC,
              data approval, or expert interpretation.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor={`vr-${item.id}`}>Optional note</Label>
            <Textarea
              id={`vr-${item.id}`}
              value={reviewComment}
              onChange={(e) => setReviewComment(e.target.value)}
              placeholder="e.g. verified spectrum shape vs. tab reference"
              rows={3}
              className="text-sm"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => setReviewOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={submitVisualReview}>
              Save inspection record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {artifactModalRow ? (
        <ArtifactViewerModal
          sessionId={spectracheckSessionId?.trim() ? spectracheckSessionId.trim() : null}
          artifact={artifactOpen ? { row: artifactModalRow, detail: artifactDetail } : null}
          open={artifactOpen}
          onOpenChange={(o) => {
            setArtifactOpen(o)
            if (!o) {
              setArtifactDetail(null)
              setArtifactErr("")
            }
          }}
          detailBusy={artifactBusy}
          detailError={artifactErr}
        />
      ) : null}
    </div>
  )
}
