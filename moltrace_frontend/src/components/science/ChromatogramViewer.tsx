"use client"

import dynamic from "next/dynamic"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import { Download, Expand, Eye, EyeOff, Layers, RotateCcw } from "lucide-react"

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as React.ComponentType<
  Record<string, unknown>
>

export type ChromatogramTrace = {
  name: string
  rt: number[]
  intensity: number[]
  type?: "TIC" | "BPC" | "XIC" | "EIC"
  mz?: number
}

export type ChromatogramFeature = {
  id?: string
  mz?: number
  rtStart?: number
  rtApex?: number
  rtEnd?: number
  label?: string
  purityLabel?: string
}

export type ChromatogramViewerProps = {
  traces: ChromatogramTrace[]
  features?: ChromatogramFeature[]
  title?: string
  xLabel?: string
  yLabel?: string
  height?: number
  className?: string
}

const TRACE_COLORS = ["#2563eb", "#ea580c", "#16a34a", "#a855f7", "#e11d48", "#0d9488"]

function filterValidTraces(traces: ChromatogramTrace[]): ChromatogramTrace[] {
  return traces.filter(
    (t) =>
      Array.isArray(t.rt) &&
      Array.isArray(t.intensity) &&
      t.rt.length > 0 &&
      t.rt.length === t.intensity.length
  )
}

function intervalOverlap(
  a: readonly [number, number],
  b: readonly [number, number]
): boolean {
  const [a0, a1] = a[0] <= a[1] ? a : [a[1], a[0]]
  const [b0, b1] = b[0] <= b[1] ? b : [b[1], b[0]]
  return Math.max(a0, b0) < Math.min(a1, b1)
}

function featureRtWindow(f: ChromatogramFeature): [number, number] | null {
  if (
    typeof f.rtStart === "number" &&
    typeof f.rtEnd === "number" &&
    Number.isFinite(f.rtStart) &&
    Number.isFinite(f.rtEnd) &&
    f.rtStart !== f.rtEnd
  ) {
    return f.rtStart <= f.rtEnd ? [f.rtStart, f.rtEnd] : [f.rtEnd, f.rtStart]
  }
  return null
}

function coelutionWarnings(features: ChromatogramFeature[]): string[] {
  const rows = features.map((f, i) => ({ f, i }))
  const warnings: string[] = []
  for (let a = 0; a < rows.length; a++) {
    for (let b = a + 1; b < rows.length; b++) {
      const wa = featureRtWindow(rows[a].f)
      const wb = featureRtWindow(rows[b].f)
      if (!wa || !wb) continue
      if (!intervalOverlap(wa, wb)) continue
      const idA = rows[a].f.id ?? rows[a].f.label ?? `feature ${rows[a].i + 1}`
      const idB = rows[b].f.id ?? rows[b].f.label ?? `feature ${rows[b].i + 1}`
      warnings.push(
        `Possible coelution: RT windows for ${String(idA)} and ${String(idB)} overlap (review chromatography context).`
      )
    }
  }
  return warnings
}

function interpolateIntensityAtRt(
  rt: number[],
  intensity: number[],
  rtTarget: number
): number {
  if (rt.length === 0) return 0
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < rt.length; i++) {
    const d = Math.abs(rt[i] - rtTarget)
    if (d < bestD) {
      bestD = d
      best = intensity[i] ?? 0
    }
  }
  return Number.isFinite(best) ? best : 0
}

function downsampleTraceDisplay(trace: ChromatogramTrace, maxPoints: number): { trace: ChromatogramTrace; reduced: boolean } {
  const len = Math.min(trace.rt.length, trace.intensity.length)
  if (len <= maxPoints) {
    return {
      trace: { ...trace, rt: trace.rt.slice(0, len), intensity: trace.intensity.slice(0, len) },
      reduced: false,
    }
  }
  const step = Math.ceil(len / maxPoints)
  const rt: number[] = []
  const intensity: number[] = []
  for (let i = 0; i < len; i += step) {
    rt.push(trace.rt[i]!)
    intensity.push(trace.intensity[i]!)
  }
  return { trace: { ...trace, rt, intensity }, reduced: true }
}

export function ChromatogramViewer({
  traces,
  features = [],
  title,
  xLabel = "Retention time",
  yLabel = "Intensity",
  height = 380,
  className,
}: ChromatogramViewerProps) {
  const [xRange, setXRange] = useState<[number, number] | null>(null)
  const [showTraces, setShowTraces] = useState(true)
  const [showFeatureWindows, setShowFeatureWindows] = useState(true)
  const graphDivRef = useRef<HTMLElement | null>(null)
  const isMobile = useIsMobile()
  const [viewportHeight, setViewportHeight] = useState(720)

  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight)
    onResize()
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  const validTraces = useMemo(() => filterValidTraces(traces), [traces])
  const displayTracesState = useMemo(
    () => validTraces.map((t) => downsampleTraceDisplay(t, isMobile ? 1600 : 6000)),
    [validTraces, isMobile],
  )
  const displayTraces = useMemo(() => displayTracesState.map((x) => x.trace), [displayTracesState])
  const empty = validTraces.length === 0

  const yMax = useMemo(() => {
    let m = 1
    displayTraces.forEach((t) => {
      t.intensity.forEach((v) => {
        if (Number.isFinite(v) && v > m) m = v
      })
    })
    return m
  }, [displayTraces])

  const plotData = useMemo(() => {
    const out: object[] = []
    displayTraces.forEach((t, idx) => {
      const legend =
        t.type != null
          ? `${t.name} (${t.type}${typeof t.mz === "number" ? `, m/z ${t.mz.toFixed(5)}` : ""})`
          : t.name
      out.push({
        type: "scattergl",
        mode: "lines",
        x: t.rt,
        y: t.intensity,
        name: legend,
        visible: showTraces,
        line: { width: 1.4, color: TRACE_COLORS[idx % TRACE_COLORS.length] },
        hovertemplate: `<b>${t.type ?? "Trace"}</b><br>${xLabel}: %{x:.4f}<br>${yLabel}: %{y:.4g}<extra></extra>`,
      })
    })

    if (showFeatureWindows && features.length > 0) {
      const primary = displayTraces[0]
      features.forEach((f, fi) => {
        if (typeof f.rtApex !== "number" || !Number.isFinite(f.rtApex)) return
        const iy = primary
          ? interpolateIntensityAtRt(primary.rt, primary.intensity, f.rtApex)
          : yMax * 0.5
        out.push({
          type: "scattergl",
          mode: "markers",
          x: [f.rtApex],
          y: [iy],
          name: f.label ? `Apex: ${f.label}` : `Apex ${fi + 1}`,
          visible: showFeatureWindows,
          marker: {
            size: 11,
            symbol: "diamond",
            color: "#0f172a",
            line: { width: 1, color: "#fff" },
          },
          hovertemplate:
            `<b>Apex</b><br>${xLabel}: %{x:.4f}<br>${yLabel}: %{y:.4g}<extra></extra>`,
        })
      })
    }

    return out
  }, [displayTraces, features, showTraces, showFeatureWindows, xLabel, yLabel, yMax])

  const shapes = useMemo(() => {
    if (!showFeatureWindows) return []
    const list: object[] = []
    features.forEach((f, fi) => {
      const w = featureRtWindow(f)
      if (!w) return
      list.push({
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: w[0],
        x1: w[1],
        y0: 0,
        y1: 1,
        fillcolor: `hsla(${(fi * 47) % 360}, 70%, 45%, 0.12)`,
        line: { width: 1, color: `hsla(${(fi * 47) % 360}, 70%, 35%, 0.45)` },
        layer: "below",
      })
      if (typeof f.rtApex === "number" && Number.isFinite(f.rtApex)) {
        list.push({
          type: "line",
          xref: "x",
          yref: "paper",
          x0: f.rtApex,
          x1: f.rtApex,
          y0: 0,
          y1: 1,
          line: { color: "rgba(15,23,42,0.35)", width: 1, dash: "dot" },
          layer: "below",
        })
      }
    })
    return list
  }, [features, showFeatureWindows])

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { l: 56, r: 18, t: title ? 52 : 36, b: 48 },
      title: title ? { text: title, font: { size: 14 } } : undefined,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: plotData.length > 0,
      xaxis: {
        title: xLabel,
        zeroline: false,
        range: xRange ? [xRange[0], xRange[1]] : undefined,
      },
      yaxis: {
        title: yLabel,
        rangemode: "tozero" as const,
        zeroline: false,
      },
      hovermode: "closest" as const,
      shapes,
      uirevision: "chromatogram",
    }),
    [title, xLabel, yLabel, xRange, shapes, plotData.length]
  )

  const coelutionLines = useMemo(() => coelutionWarnings(features), [features])

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

  const fullRtRange = useCallback(() => {
    setXRange(null)
  }, [])

  const onInitialized = useCallback((_fig: unknown, graphDiv: HTMLElement) => {
    graphDivRef.current = graphDiv
  }, [])

  const exportImage = useCallback(async () => {
    const el = graphDivRef.current
    if (!el) return
    const Plotly = (await import("plotly.js-dist-min")).default
    await Plotly.downloadImage(el, { format: "png", filename: "chromatogram", scale: 2 })
  }, [])

  if (empty) {
    return (
      <div
        className={cn(
          "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
        data-testid="chromatogram-viewer-root"
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No chromatogram or XIC data available yet.</p>
      </div>
    )
  }

  const effectiveHeight = isMobile ? Math.min(Math.max(Math.floor(viewportHeight * 0.42), 260), 420) : height
  const isDisplayDownsampled = displayTracesState.some((s) => s.reduced)

  return (
    <div
      className={cn("flex min-w-0 max-w-full flex-col gap-3 overflow-x-hidden", className)}
      data-testid="chromatogram-viewer-root"
      aria-label="LC-MS chromatogram viewer"
    >
      <div className="flex flex-wrap items-start justify-end gap-2">
        <InfoTooltip content="XIC/EIC traces show whether an m/z signal forms a coherent chromatographic feature and whether it may coelute with other ions." />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b pb-3">
        {!isMobile ? (
          <>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={resetZoom}
              aria-label="Reset zoom"
            >
              <RotateCcw className="mr-1 h-4 w-4 shrink-0" aria-hidden />
              Reset zoom
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Reset axes to the full data range.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={fullRtRange}
              aria-label="Full retention time range"
            >
              <Expand className="mr-1 h-4 w-4 shrink-0" aria-hidden />
              Full RT range
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show the full retention-time span of the traces.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={showTraces ? "secondary" : "outline"}
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={() => setShowTraces((v) => !v)}
              aria-label="Toggle traces"
            >
              {showTraces ? <Eye className="mr-1 h-4 w-4 shrink-0" /> : <EyeOff className="mr-1 h-4 w-4 shrink-0" />}
              Toggle traces
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show or hide chromatogram line traces.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={showFeatureWindows ? "secondary" : "outline"}
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={() => setShowFeatureWindows((v) => !v)}
              aria-label="Toggle feature windows"
            >
              <Layers className="mr-1 h-4 w-4 shrink-0" aria-hidden />
              Toggle feature windows
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show or hide feature RT bands and apex markers.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={() => void exportImage()}
              aria-label="Export image"
            >
              <Download className="mr-1 h-4 w-4 shrink-0" aria-hidden />
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
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={fullRtRange}>
                Full RT range
              </Button>
              <Button
                type="button"
                variant={showTraces ? "secondary" : "outline"}
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setShowTraces((v) => !v)}
              >
                Toggle traces
              </Button>
              <Button
                type="button"
                variant={showFeatureWindows ? "secondary" : "outline"}
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setShowFeatureWindows((v) => !v)}
              >
                Toggle feature windows
              </Button>
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => void exportImage()}>
                Export image
              </Button>
            </div>
          </details>
        )}
      </div>

      <div
        className="min-h-[280px] w-full min-w-0 max-w-full overflow-hidden rounded-lg border bg-card"
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
          style={{ width: "100%", height: "100%", minWidth: 0 }}
          useResizeHandler
          onRelayout={onRelayout}
          onInitialized={onInitialized}
        />
      </div>
      {isDisplayDownsampled ? (
        <p className="text-xs text-muted-foreground">Display downsampled on mobile. Full resolution available on desktop.</p>
      ) : null}

      {features.length > 0 ? (
        <div className="flex min-w-0 max-w-full flex-wrap gap-2">
          {features.map((f, i) => {
            const parts: string[] = []
            if (f.label) parts.push(f.label)
            if (typeof f.mz === "number" && Number.isFinite(f.mz)) parts.push(`m/z ${f.mz.toFixed(5)}`)
            if (f.purityLabel) parts.push(`Purity: ${f.purityLabel}`)
            const text = parts.length > 0 ? parts.join(" · ") : `Feature ${i + 1}`
            return (
              <Badge
                key={f.id != null ? `${f.id}-${i}` : `pf-${i}`}
                variant="secondary"
                className="max-w-full min-w-0 truncate font-normal"
              >
                {text}
              </Badge>
            )
          })}
        </div>
      ) : null}

      {coelutionLines.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-amber-900 dark:text-amber-200">
          {coelutionLines.map((line, i) => (
            <li key={`co-${i}`}>{line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
