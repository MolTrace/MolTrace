"use client"

import { useMemo } from "react"
import { ChromatogramViewer } from "@/components/science/ChromatogramViewer"
import { FragmentTreeViewer } from "@/src/components/science/FragmentTreeViewer"
import { MsmsMirrorPlot } from "@/components/science/MsmsMirrorPlot"
import { Nmr2DViewer } from "@/components/science/Nmr2DViewer"
import { SpectrumViewer1D } from "@/components/science/SpectrumViewer1D"
import type { SpectrumViewer1DOverlay } from "@/components/science/SpectrumViewer1D"
import { extractPredictedOverlay, extractSpectrumXY } from "@/components/spectracheck/spectracheck-nmr-result-parse"
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
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

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

export type ReportVisualEvidenceInlinePreviewsProps = {
  item: EvidenceItem
  /** Default matches compact queue previews; keep small for Report tab density. */
  plotHeight?: number
}

/**
 * Session-only compact plots for Report Composer — same payload rules as Evidence Queue previews.
 * Compose payloads remain references + placeholders only (no embedded raster).
 */
export function ReportVisualEvidenceInlinePreviews({
  item,
  plotHeight = 150,
}: ReportVisualEvidenceInlinePreviewsProps) {
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

  const showMsmsMirrorPlot = msmsBundle != null && msmsBundle.observedPeaks.length > 0
  const showMsmsFallbackTable =
    msmsBundle != null &&
    msmsBundle.observedPeaks.length === 0 &&
    (msmsBundle.referencePeaks.length > 0 || msmsBundle.fragmentMatches.length > 0)

  const hasChroma = chromaTraces.length > 0
  const hasNmr2d = nmr2dPeaks.length > 0
  const hasFragViewer = fragGraph.nodes.length > 0
  const hasFragEdgesOnly = !hasFragViewer && fragGraph.edges.length > 0

  const hasPlotPayload =
    showSpectrum ||
    showMsmsMirrorPlot ||
    showMsmsFallbackTable ||
    hasChroma ||
    hasNmr2d ||
    hasFragViewer ||
    hasFragEdgesOnly

  if (!hasPlotPayload && artifactId) {
    return (
      <p className="text-[11px] text-muted-foreground">
        Artifact-linked evidence — open the Evidence Queue &quot;Visual previews&quot; or artifact viewer for interactive
        plots. Compose still sends artifact metadata and placeholders only.
      </p>
    )
  }

  if (!hasPlotPayload) {
    return (
      <p className="text-[11px] text-muted-foreground">
        No inline plot payload detected for this row (compose metadata may still list artifact references).
      </p>
    )
  }

  return (
    <div className="grid min-w-0 gap-3 sm:grid-cols-1 lg:grid-cols-2">
      {showSpectrum && spectrumXy ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">1D spectrum</p>
          <div className="max-h-[min(200px,28vh)] min-h-0 min-w-0 overflow-hidden">
            <SpectrumViewer1D
              className="max-h-[min(200px,28vh)]"
              height={plotHeight}
              x={spectrumXy.x}
              y={spectrumXy.y}
              peaks={peaks1d.length > 0 ? peaks1d : undefined}
              overlays={overlays1d}
              nucleus="1H"
            />
          </div>
        </div>
      ) : null}

      {showMsmsMirrorPlot && msmsBundle ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">MS/MS mirror</p>
          <div className="max-h-[min(200px,28vh)] min-w-0 overflow-hidden">
            <MsmsMirrorPlot
              className="max-h-[min(200px,28vh)]"
              height={plotHeight}
              observedPeaks={msmsBundle.observedPeaks}
              referencePeaks={msmsBundle.referencePeaks}
              fragmentMatches={msmsBundle.fragmentMatches}
              precursorMz={msmsBundle.precursorMz}
              adduct={msmsBundle.adduct}
              toleranceDa={msmsBundle.toleranceDa}
              tolerancePpm={msmsBundle.tolerancePpm}
            />
          </div>
        </div>
      ) : null}

      {showMsmsFallbackTable && msmsBundle ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2 lg:col-span-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">MS/MS peaks / matches</p>
          <ScrollArea className="max-h-36 rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">m/z</TableHead>
                  <TableHead className="text-xs">Intensity</TableHead>
                  <TableHead className="text-xs">Label</TableHead>
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
        </div>
      ) : null}

      {hasChroma ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2 lg:col-span-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">Chromatogram</p>
          <ChromatogramViewer
            className="max-h-[min(220px,30vh)]"
            height={plotHeight}
            traces={chromaTraces}
            features={chromaFeatures.length > 0 ? chromaFeatures : undefined}
          />
        </div>
      ) : null}

      {hasNmr2d ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2 lg:col-span-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">2D NMR peaks</p>
          <Nmr2DViewer className="max-h-[min(220px,30vh)]" height={plotHeight + 16} peaks={nmr2dPeaks} />
        </div>
      ) : null}

      {hasFragViewer ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2 lg:col-span-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">Fragmentation tree</p>
          <div className="max-h-48 overflow-auto">
            <FragmentTreeViewer nodes={fragGraph.nodes} edges={fragGraph.edges} />
          </div>
        </div>
      ) : null}

      {hasFragEdgesOnly ? (
        <div className="min-w-0 rounded-md border bg-background/80 p-2 lg:col-span-2">
          <p className="mb-1 text-[10px] font-medium text-muted-foreground">Fragmentation edges</p>
          <ScrollArea className="max-h-36 rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Source</TableHead>
                  <TableHead className="text-xs">Target</TableHead>
                  <TableHead className="text-xs">Loss</TableHead>
                  <TableHead className="text-xs">Δ m/z</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fragGraph.edges.map((e, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs">{e.source}</TableCell>
                    <TableCell className="font-mono text-xs">{e.target}</TableCell>
                    <TableCell className="text-xs">{e.loss ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {typeof e.delta_mz === "number" && Number.isFinite(e.delta_mz) ? e.delta_mz.toFixed(4) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>
      ) : null}
    </div>
  )
}
