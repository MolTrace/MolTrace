"use client"

import dynamic from "next/dynamic"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import { Download, Eye, EyeOff, Layers, RotateCcw } from "lucide-react"

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as React.ComponentType<
  Record<string, unknown>
>

export type MsmsMirrorObservedPeak = {
  mz: number
  intensity: number
  label?: string
}

export type MsmsMirrorReferencePeak = {
  mz: number
  intensity: number
  label?: string
}

export type MsmsMirrorFragmentMatch = {
  observed_mz?: number
  theoretical_mz?: number
  label?: string
  score?: number
}

export type MsmsMirrorPlotProps = {
  observedPeaks: MsmsMirrorObservedPeak[]
  referencePeaks?: MsmsMirrorReferencePeak[]
  fragmentMatches?: MsmsMirrorFragmentMatch[]
  title?: string
  precursorMz?: number
  adduct?: string
  toleranceDa?: number
  tolerancePpm?: number
  height?: number
  className?: string
}

function relativeIntensitySeries(peaks: ReadonlyArray<{ intensity: number }>): number[] {
  const vals = peaks.map((p) => (Number.isFinite(p.intensity) ? Math.max(0, p.intensity) : 0))
  const max = Math.max(...vals, 1e-99)
  return vals.map((v) => (v / max) * 100)
}

function mzWithinTol(
  a: number,
  b: number,
  tolDa: number | undefined,
  tolPpm: number | undefined,
  refMz: number | undefined
): boolean {
  const da = Math.abs(a - b)
  if (tolDa != null && Number.isFinite(tolDa) && da <= tolDa) return true
  if (tolPpm != null && Number.isFinite(tolPpm)) {
    const basis = refMz != null && Number.isFinite(refMz) ? refMz : Math.max(Math.abs(a), Math.abs(b), 1)
    const ppmTol = basis * tolPpm * 1e-6
    return da <= ppmTol
  }
  return da <= 0.05
}

/** Qualitative match wording only — exploratory review, not identification. */
function matchInterpretation(score: number | undefined): string {
  if (score == null || !Number.isFinite(score)) return "Requires review"
  if (score < 0) return "Contradiction"
  if (score < 0.35) return "Requires review"
  if (score < 0.65) return "Partial support"
  return "Support"
}

function peakMatchesFragment(
  mz: number,
  frag: MsmsMirrorFragmentMatch,
  tolDa: number | undefined,
  tolPpm: number | undefined,
  precursorMz: number | undefined
): boolean {
  const opts = [frag.observed_mz, frag.theoretical_mz].filter(
    (v): v is number => typeof v === "number" && Number.isFinite(v)
  )
  const ref = precursorMz ?? mz
  return opts.some((c) => mzWithinTol(mz, c, tolDa, tolPpm, ref))
}

function looksLikeNeutralLossLabel(label: string | undefined): boolean {
  if (!label || typeof label !== "string") return false
  const s = label.toLowerCase()
  return s.includes("loss") || s.includes("neutral") || s.includes("−") || s.includes("-")
}

function buildStickXY(rel: number[], peaks: ReadonlyArray<{ mz: number }>, sign: 1 | -1) {
  const x: (number | null)[] = []
  const y: (number | null)[] = []
  for (let i = 0; i < peaks.length; i++) {
    const mz = peaks[i].mz
    const h = rel[i] * sign
    x.push(mz, mz, null)
    y.push(0, h, null)
  }
  return { x, y }
}

function downsamplePeakSeries<T extends { mz: number; intensity: number }>(peaks: T[], maxPoints: number): { peaks: T[]; reduced: boolean } {
  if (peaks.length <= maxPoints) return { peaks: peaks.slice(), reduced: false }
  const step = Math.ceil(peaks.length / maxPoints)
  const out: T[] = []
  for (let i = 0; i < peaks.length; i += step) out.push(peaks[i]!)
  return { peaks: out, reduced: true }
}

export function MsmsMirrorPlot({
  observedPeaks,
  referencePeaks = [],
  fragmentMatches = [],
  title,
  precursorMz,
  adduct,
  toleranceDa,
  tolerancePpm,
  height = 380,
  className,
}: MsmsMirrorPlotProps) {
  const [xRange, setXRange] = useState<[number, number] | null>(null)
  const [showMatchedLabels, setShowMatchedLabels] = useState(true)
  const [showReference, setShowReference] = useState(true)
  const graphDivRef = useRef<HTMLElement | null>(null)
  const isMobile = useIsMobile()
  const [viewportHeight, setViewportHeight] = useState(720)

  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight)
    onResize()
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  useEffect(() => {
    if (isMobile) setShowMatchedLabels(false)
  }, [isMobile])

  const tolDa = toleranceDa
  const tolPpm = tolerancePpm

  const { observedMatched, observedUnmatched } = useMemo(() => {
    const matched: MsmsMirrorObservedPeak[] = []
    const unmatched: MsmsMirrorObservedPeak[] = []
    if (fragmentMatches.length === 0) {
      return { observedMatched: [] as MsmsMirrorObservedPeak[], observedUnmatched: [...observedPeaks] }
    }
    for (const p of observedPeaks) {
      const hit = fragmentMatches.some((f) => peakMatchesFragment(p.mz, f, tolDa, tolPpm, precursorMz))
      if (hit) matched.push(p)
      else unmatched.push(p)
    }
    return { observedMatched: matched, observedUnmatched: unmatched }
  }, [observedPeaks, fragmentMatches, tolDa, tolPpm, precursorMz])
  const dsObservedMatched = useMemo(
    () => downsamplePeakSeries(observedMatched, isMobile ? 1200 : 4000),
    [observedMatched, isMobile],
  )
  const dsObservedUnmatched = useMemo(
    () => downsamplePeakSeries(observedUnmatched, isMobile ? 1200 : 4000),
    [observedUnmatched, isMobile],
  )
  const dsReference = useMemo(
    () => downsamplePeakSeries(referencePeaks, isMobile ? 1200 : 4000),
    [referencePeaks, isMobile],
  )

  const relObsMatched = useMemo(() => relativeIntensitySeries(dsObservedMatched.peaks), [dsObservedMatched.peaks])
  const relObsUnmatched = useMemo(() => relativeIntensitySeries(dsObservedUnmatched.peaks), [dsObservedUnmatched.peaks])
  const relRef = useMemo(() => relativeIntensitySeries(dsReference.peaks), [dsReference.peaks])

  const plotData = useMemo(() => {
    const traces: object[] = []
    if (dsObservedUnmatched.peaks.length > 0) {
      const { x, y } = buildStickXY(relObsUnmatched, dsObservedUnmatched.peaks, 1)
      traces.push({
        type: "scattergl",
        mode: "lines",
        x,
        y,
        name: "Observed",
        line: { width: 1.4, color: "#2563eb" },
        hovertemplate:
          "<b>m/z</b> %{x:.4f}<br><b>Rel. intensity</b> %{y:.1f}<br><extra></extra>",
      })
    }
    if (dsObservedMatched.peaks.length > 0) {
      const { x, y } = buildStickXY(relObsMatched, dsObservedMatched.peaks, 1)
      traces.push({
        type: "scattergl",
        mode: "lines",
        x,
        y,
        name: "Observed (matched)",
        line: { width: 1.6, color: "#ea580c" },
        hovertemplate:
          "<b>m/z</b> %{x:.4f}<br><b>Rel. intensity</b> %{y:.1f}<br><b>Match</b> exploratory<br><extra></extra>",
      })
    }
    if (showReference && dsReference.peaks.length > 0) {
      const { x, y } = buildStickXY(relRef, dsReference.peaks, -1)
      traces.push({
        type: "scattergl",
        mode: "lines",
        x,
        y,
        name: "Reference / library",
        line: { width: 1.4, color: "#a855f7" },
        hovertemplate:
          "<b>m/z</b> %{x:.4f}<br><b>Rel. intensity (mirror)</b> %{y:.1f}<br><extra></extra>",
      })
    }
    return traces
  }, [
    dsObservedMatched.peaks,
    dsObservedUnmatched.peaks,
    relObsMatched,
    relObsUnmatched,
    dsReference.peaks,
    relRef,
    showReference,
  ])

  const annotations = useMemo(() => {
    if (!showMatchedLabels) return []
    const out: object[] = []
    const relAll = relativeIntensitySeries(observedPeaks)

    observedPeaks.forEach((p, idx) => {
      const yTop = relAll[idx] ?? 0
      const lab = p.label?.trim()
      if (lab) {
        out.push({
          x: p.mz,
          y: yTop,
          text: lab,
          showarrow: true,
          arrowhead: 2,
          ax: 0,
          ay: -24,
          font: { size: 10, color: "#0f172a" },
          bgcolor: "rgba(255,255,255,0.75)",
          borderpad: 2,
        })
      }
    })

    for (const frag of fragmentMatches) {
      const mz =
        typeof frag.observed_mz === "number"
          ? frag.observed_mz
          : typeof frag.theoretical_mz === "number"
            ? frag.theoretical_mz
            : null
      if (mz == null) continue
      const obsIdx = observedPeaks.findIndex((op) =>
        peakMatchesFragment(op.mz, frag, tolDa, tolPpm, precursorMz)
      )
      const obsPeak = obsIdx >= 0 ? observedPeaks[obsIdx] : undefined
      const yTop = obsPeak ? relAll[obsIdx] ?? 0 : 8
      const interp = matchInterpretation(frag.score)
      const scoreTxt =
        typeof frag.score === "number" && Number.isFinite(frag.score)
          ? `Score: ${frag.score.toFixed(3)} · ${interp}`
          : interp
      const baseLabel = frag.label?.trim()
      const nl = baseLabel && looksLikeNeutralLossLabel(baseLabel)
      const textLines = [
        scoreTxt,
        nl ? `Neutral-loss note: ${baseLabel}` : baseLabel ? `Label: ${baseLabel}` : "",
      ].filter(Boolean)
      out.push({
        x: mz,
        y: Math.min(yTop + 12, 105),
        text: textLines.join("<br>"),
        showarrow: false,
        font: { size: 9, color: "#334155" },
        bgcolor: "rgba(248,250,252,0.92)",
        borderpad: 3,
        xref: "x",
        yref: "y",
      })
    }

    return out
  }, [
    observedPeaks,
    fragmentMatches,
    showMatchedLabels,
    tolDa,
    tolPpm,
    precursorMz,
  ])

  const shapes = useMemo(() => {
    const list: object[] = []
    if (typeof precursorMz === "number" && Number.isFinite(precursorMz)) {
      list.push({
        type: "line",
        xref: "x",
        yref: "paper",
        x0: precursorMz,
        x1: precursorMz,
        y0: 0,
        y1: 1,
        line: { color: "rgba(100,116,139,0.85)", width: 1.5, dash: "dot" },
        layer: "below",
      })
    }
    return list
  }, [precursorMz])

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { l: 56, r: 18, t: title ? 52 : 36, b: 48 },
      title: title ? { text: title, font: { size: 14 } } : undefined,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: plotData.length > 1,
      xaxis: {
        title: "m/z",
        zeroline: false,
        range: xRange ? [xRange[0], xRange[1]] : undefined,
      },
      yaxis: {
        title: "Relative intensity",
        range: [-110, 110],
        zeroline: true,
        zerolinewidth: 1,
        zerolinecolor: "rgba(15,23,42,0.35)",
      },
      hovermode: "closest" as const,
      annotations,
      shapes,
      uirevision: "msms-mirror",
    }),
    [title, xRange, annotations, shapes, plotData.length]
  )

  const onRelayout = useCallback((ev: Readonly<unknown>) => {
    const raw = ev as Record<string, unknown>
    const xr0 = raw["xaxis.range[0]"]
    const xr1 = raw["xaxis.range[1]"]
    if (typeof xr0 === "number" && typeof xr1 === "number") {
      setXRange([xr0, xr1])
    }
    if (raw["xaxis.autorange"] === true) {
      setXRange(null)
    }
  }, [])

  const resetZoom = useCallback(() => {
    setXRange(null)
  }, [])

  const onInitialized = useCallback((_fig: unknown, graphDiv: HTMLElement) => {
    graphDivRef.current = graphDiv
  }, [])

  const exportImage = useCallback(async () => {
    const el = graphDivRef.current
    if (!el) return
    const Plotly = (await import("plotly.js-dist-min")).default
    await Plotly.downloadImage(el, { format: "png", filename: "msms-mirror", scale: 2 })
  }, [])

  if (observedPeaks.length === 0) {
    return (
      <div
        className={cn(
          "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No MS/MS peak data available yet.</p>
      </div>
    )
  }

  const effectiveHeight = isMobile ? Math.min(Math.max(Math.floor(viewportHeight * 0.42), 260), 420) : height
  const isDisplayDownsampled = dsObservedMatched.reduced || dsObservedUnmatched.reduced || dsReference.reduced

  return (
    <div className={cn("flex min-w-0 max-w-full flex-col gap-3 overflow-x-hidden", className)} aria-label="MS/MS mirror comparison plot">
      <div className="flex flex-wrap items-start justify-end gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <InfoTooltip content="Mirror plots help compare observed MS/MS fragments against reference, predicted, or candidate-derived fragment evidence." />
        </div>
        {(typeof precursorMz === "number" || adduct) && (
          <p className="max-w-full text-xs text-muted-foreground">
            {typeof precursorMz === "number" ? (
              <>
                Precursor m/z <span className="font-mono">{precursorMz.toFixed(5)}</span>
              </>
            ) : null}
            {typeof precursorMz === "number" && adduct ? " · " : null}
            {adduct ? <span>{adduct}</span> : null}
          </p>
        )}
      </div>

      <p className="text-[11px] leading-snug text-muted-foreground">
        Evidence strength is shown as support / partial support / contradiction / requires review — exploratory only,
        not compound identification.
      </p>

      <div className="flex flex-wrap items-center gap-2 border-b pb-3">
        {!isMobile ? (
          <>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={resetZoom}
              aria-label="Reset zoom"
            >
              <RotateCcw className="mr-1 h-4 w-4" aria-hidden />
              Reset zoom
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Reset the m/z axis to the full peak range.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={showMatchedLabels ? "secondary" : "outline"}
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => setShowMatchedLabels((v) => !v)}
              aria-label="Toggle matched labels"
            >
              {showMatchedLabels ? <Eye className="mr-1 h-4 w-4" /> : <EyeOff className="mr-1 h-4 w-4" />}
              Toggle matched labels
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show or hide match annotations and peak labels.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={showReference ? "secondary" : "outline"}
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => setShowReference((v) => !v)}
              aria-label="Toggle reference peaks"
            >
              <Layers className="mr-1 h-4 w-4" aria-hidden />
              Toggle reference peaks
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show or hide the mirrored reference spectrum below the axis.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => void exportImage()}
              aria-label="Export image"
            >
              <Download className="mr-1 h-4 w-4" aria-hidden />
              Export image
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Download the current plot as a PNG image.</p>
          </TooltipContent>
        </Tooltip>
          </>
        ) : (
          <details className="w-full">
            <summary className="cursor-pointer text-xs text-muted-foreground">More controls</summary>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                type="button"
                variant={showMatchedLabels ? "secondary" : "outline"}
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setShowMatchedLabels((v) => !v)}
              >
                Toggle matched labels
              </Button>
              <Button
                type="button"
                variant={showReference ? "secondary" : "outline"}
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setShowReference((v) => !v)}
              >
                Toggle reference peaks
              </Button>
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => void exportImage()}>
                Export image
              </Button>
            </div>
          </details>
        )}
      </div>

      <div
        className="min-h-[280px] w-full min-w-0 overflow-hidden rounded-lg border bg-card"
        style={{ height: effectiveHeight }}
      >
        <Plot
          data={plotData}
          layout={layout}
          config={{
            displayModeBar: true,
            displaylogo: false,
            responsive: true,
            scrollZoom: true,
          }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
          onRelayout={onRelayout}
          onInitialized={onInitialized}
        />
      </div>
      {isDisplayDownsampled ? (
        <p className="text-xs text-muted-foreground">Display downsampled on mobile. Full resolution available on desktop.</p>
      ) : null}
    </div>
  )
}
