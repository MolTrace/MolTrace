"use client"

import dynamic from "next/dynamic"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Expand,
  Eye,
  EyeOff,
  Layers,
  Minus,
  Plus,
  RotateCcw,
} from "lucide-react"

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as React.ComponentType<
  Record<string, unknown>
>

export type SpectrumViewer1DPeak = {
  id?: string
  x: number
  y?: number
  label?: string
  type?: string
  confidence?: number
}

export type SpectrumViewer1DOverlay = {
  name: string
  x: number[]
  y: number[]
  visible?: boolean
}

export type SpectrumViewer1DProps = {
  x: number[]
  y: number[]
  title?: string
  xLabel?: string
  yLabel?: string
  reversedXAxis?: boolean
  nucleus?: "1H" | "13C" | "MS" | "LCMS" | string
  peaks?: SpectrumViewer1DPeak[]
  overlays?: SpectrumViewer1DOverlay[]
  height?: number
  onPeakClick?: (peak: SpectrumViewer1DPeak) => void
  className?: string
}

const DISPLAY_Y_CAP = 1e120

export function normalizePlotlyXRange(a: number, b: number): [number, number] {
  return a <= b ? [a, b] : [b, a]
}

function hoverFormatForNucleus(nucleus?: string): string {
  return nucleus === "13C" ? ".2f" : ".4f"
}

/** Display-only gain: exponential multiplier with baseline anchored at series minimum (smooth high gain, stable baseline). */
function deriveDisplayY(y: number[], gainSlider01: number): number[] {
  const mult = Math.exp(gainSlider01 * Math.log(50001))
  if (y.length === 0) return []
  let yMin = Infinity
  for (const v of y) {
    if (!Number.isFinite(v)) continue
    if (v < yMin) yMin = v
  }
  if (!Number.isFinite(yMin)) yMin = 0
  return y.map((v) => {
    if (!Number.isFinite(v)) return yMin
    const scaled = yMin + (v - yMin) * mult
    if (!Number.isFinite(scaled)) return yMin
    const mag = Math.abs(scaled)
    const capped = Math.sign(scaled) * Math.min(mag, DISPLAY_Y_CAP)
    return Math.min(Math.max(capped, -DISPLAY_Y_CAP), DISPLAY_Y_CAP)
  })
}

function nearestDisplayYAtX(xArr: number[], yDisp: number[], xTarget: number): number {
  if (xArr.length === 0) return 0
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < xArr.length; i++) {
    const d = Math.abs(xArr[i] - xTarget)
    if (d < bestD) {
      bestD = d
      best = yDisp[i] ?? 0
    }
  }
  return best
}

function downsampleXYDisplay(x: number[], y: number[], maxPoints: number): { x: number[]; y: number[]; reduced: boolean } {
  const len = Math.min(x.length, y.length)
  if (len <= maxPoints) return { x: x.slice(0, len), y: y.slice(0, len), reduced: false }
  const step = Math.ceil(len / maxPoints)
  const dx: number[] = []
  const dy: number[] = []
  for (let i = 0; i < len; i += step) {
    dx.push(x[i]!)
    dy.push(y[i]!)
  }
  return { x: dx, y: dy, reduced: true }
}

export function SpectrumViewer1D({
  x,
  y,
  title,
  xLabel = "ppm",
  yLabel = "Intensity",
  reversedXAxis = true,
  nucleus,
  peaks = [],
  overlays = [],
  height = 360,
  onPeakClick,
  className,
}: SpectrumViewer1DProps) {
  const [gain01, setGain01] = useState(0.45)
  const [showPeakLabels, setShowPeakLabels] = useState(true)
  const [showOverlaysMaster, setShowOverlaysMaster] = useState(true)
  const [yZoom, setYZoom] = useState(1)
  const [xRange, setXRange] = useState<[number, number] | null>(null)
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
    if (isMobile) setShowPeakLabels(false)
  }, [isMobile])

  const displayY = useMemo(() => deriveDisplayY(y, gain01), [y, gain01])
  const displayPrimary = useMemo(
    () => downsampleXYDisplay(x, displayY, isMobile ? 1600 : 5000),
    [x, displayY, isMobile],
  )

  const mismatch =
    x.length > 0 && y.length > 0 && x.length !== y.length
  const empty = x.length === 0 || y.length === 0

  const overlayYs = useMemo(() => {
    return overlays.map((o) => deriveDisplayY(o.y, gain01))
  }, [overlays, gain01])
  const displayOverlays = useMemo(
    () =>
      overlays.map((o, i) => {
        const dy = overlayYs[i] ?? []
        return downsampleXYDisplay(o.x, dy, isMobile ? 1200 : 4000)
      }),
    [overlays, overlayYs, isMobile],
  )

  const { xMin, xMax, yMax } = useMemo(() => {
    if (empty || mismatch) {
      return { xMin: 0, xMax: 1, yMax: 1 }
    }
    const xi = displayPrimary.x.map(Number)
    const ys = displayPrimary.y
    const localYMax = ys.length ? Math.max(...ys.map((v) => (Number.isFinite(v) ? v : 0))) : 1
    let overlayMax = 0
    if (showOverlaysMaster) {
      overlays.forEach((o, i) => {
        if (o.visible === false) return
        const ov = displayOverlays[i]
        if (!ov?.y.length || ov.x.length !== ov.y.length) return
        overlayMax = Math.max(overlayMax, ...ov.y.map((v) => (Number.isFinite(v) ? v : 0)))
      })
    }
    let peakMax = 0
    if (peaks.length > 0) {
      peaks.forEach((p) => {
        const py =
          p.y != null
            ? yMinShiftedGain(p.y, y, gain01)
            : nearestDisplayYAtX(displayPrimary.x, displayPrimary.y, p.x)
        peakMax = Math.max(peakMax, Number.isFinite(py) ? py : 0)
      })
    }
    return {
      xMin: Math.min(...xi),
      xMax: Math.max(...xi),
      yMax: Math.max(localYMax, overlayMax, peakMax, 1) * yZoom,
    }
  }, [
    displayPrimary.x,
    displayPrimary.y,
    empty,
    mismatch,
    overlays,
    displayOverlays,
    peaks,
    showOverlaysMaster,
    yZoom,
    gain01,
  ])

  const effectiveXMin = xRange ? xRange[0] : xMin
  const effectiveXMax = xRange ? xRange[1] : xMax

  const data = useMemo(() => {
    if (empty || mismatch) return []
    const ppmHoverFormat = hoverFormatForNucleus(nucleus)
    const traces: object[] = [
      {
        type: "scattergl",
        mode: "lines",
        x: displayPrimary.x,
        y: displayPrimary.y,
        name: "Spectrum",
        line: { width: 1.2, color: "#2563eb" },
        hovertemplate: `%{x:${ppmHoverFormat}} ppm<br>${yLabel}: %{y:.4g}<extra>Spectrum</extra>`,
      },
    ]
    if (showOverlaysMaster) {
      overlays.forEach((o, i) => {
        if (o.visible === false) return
        const ov = displayOverlays[i]
        if (!ov || ov.x.length !== ov.y.length) return
        traces.push({
          type: "scattergl",
          mode: "lines",
          x: ov.x,
          y: ov.y,
          name: o.name,
          line: { width: 1, dash: "dash", color: "#c026d3" },
          opacity: 0.85,
          hovertemplate: `%{x:${ppmHoverFormat}} ppm<br>${yLabel}: %{y:.4g}<extra>${o.name}</extra>`,
        })
      })
    }
    if (peaks.length > 0) {
      const px = peaks.map((p) => p.x)
      const py = peaks.map((p) =>
        p.y != null
          ? yMinShiftedGain(p.y, y, gain01)
          : nearestDisplayYAtX(displayPrimary.x, displayPrimary.y, p.x)
      )
      traces.push({
        type: "scattergl",
        mode: showPeakLabels ? "markers+text" : "markers",
        x: px,
        y: py,
        text: showPeakLabels ? peaks.map((p) => p.label ?? "") : undefined,
        textposition: "top center",
        name: "Peaks",
        marker: { size: 7, color: "#ea580c", line: { width: 0.5, color: "#fff" } },
        textfont: { size: 10 },
        hovertemplate: `%{x:${ppmHoverFormat}} ppm<br>${yLabel}: %{y:.4g}<extra>Peak</extra>`,
      })
    }
    return traces
  }, [
    x,
    y,
    displayPrimary.x,
    displayPrimary.y,
    empty,
    mismatch,
    overlays,
    displayOverlays,
    peaks,
    showOverlaysMaster,
    showPeakLabels,
    gain01,
    nucleus,
    yLabel,
  ])

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { l: 52, r: 16, t: title ? 40 : 28, b: 44 },
      title: title ? { text: title, font: { size: 14 } } : undefined,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: data.length > 1,
      xaxis: {
        title: xLabel,
        // Plotly's `autorange` overrides `range`. When xRange is set we have
        // to disable autorange and pass the range in display order ([high,
        // low] when reversed) — otherwise pan/zoom updates state but the
        // chart silently snaps back to the full span and the ticks never move.
        ...(xRange
          ? {
              autorange: false as const,
              range: reversedXAxis
                ? [effectiveXMax, effectiveXMin]
                : [effectiveXMin, effectiveXMax],
            }
          : {
              autorange: reversedXAxis ? ("reversed" as const) : true,
            }),
        zeroline: false,
        showgrid: false,
        showspikes: true,
        spikemode: "across" as const,
        spikesnap: "cursor" as const,
        spikecolor: "#0f766e",
        spikethickness: 1,
        spikedash: "solid" as const,
        hoverformat: hoverFormatForNucleus(nucleus),
      },
      yaxis: {
        title: yLabel,
        range: [0, yMax],
        zeroline: false,
        showgrid: false,
        fixedrange: false,
      },
      hovermode: "closest" as const,
      uirevision: "spectrum1d",
    }),
    [title, xLabel, yLabel, reversedXAxis, xRange, effectiveXMin, effectiveXMax, yMax, data.length, nucleus]
  )

  const onRelayout = useCallback((ev: Readonly<unknown>) => {
    const raw = ev as Record<string, unknown>
    const xr0 = raw["xaxis.range[0]"]
    const xr1 = raw["xaxis.range[1]"]
    if (typeof xr0 === "number" && typeof xr1 === "number") {
      setXRange(normalizePlotlyXRange(xr0, xr1))
    }
    if (raw["xaxis.autorange"] === true || raw["xaxis.autorange"] === "reversed") {
      setXRange(null)
    }
  }, [])

  const resetZoom = useCallback(() => {
    setXRange(null)
    setYZoom(1)
  }, [])

  const fullView = useCallback(() => {
    setXRange(null)
  }, [])

  const pan = useCallback(
    (dir: "left" | "right") => {
      const span = effectiveXMax - effectiveXMin || 1
      const step = span * 0.08
      const delta = dir === "left" ? -step : step
      setXRange([effectiveXMin + delta, effectiveXMax + delta])
    },
    [effectiveXMin, effectiveXMax]
  )

  const bumpPeakHeight = useCallback((sign: 1 | -1) => {
    setYZoom((z) => {
      const next = z * (sign === 1 ? 1.12 : 1 / 1.12)
      return Math.min(Math.max(next, 0.25), 20)
    })
  }, [])

  const onInitialized = useCallback((_fig: unknown, graphDiv: HTMLElement) => {
    graphDivRef.current = graphDiv
  }, [])

  const exportImage = useCallback(async () => {
    const el = graphDivRef.current
    if (!el) return
    const Plotly = (await import("plotly.js-dist-min")).default
    await Plotly.downloadImage(el, { format: "png", filename: "spectrum", scale: 2 })
  }, [])

  const peakTraceIndex = useMemo(() => {
    if (peaks.length === 0) return -1
    let n = 1
    if (showOverlaysMaster) {
      overlays.forEach((o, i) => {
        if (o.visible === false) return
        const dy = overlayYs[i]
        if (!dy?.length || o.x.length !== dy.length) return
        n++
      })
    }
    return n
  }, [peaks.length, showOverlaysMaster, overlays, overlayYs])

  const handlePlotClick = useCallback(
    (ev: Readonly<unknown>) => {
      if (!onPeakClick) return
      const raw = ev as { points?: ReadonlyArray<{ curveNumber: number; x: number }> }
      const pt = raw.points?.[0]
      if (!pt || peakTraceIndex < 0 || pt.curveNumber !== peakTraceIndex) return
      const hit = peaks.find((p) => Math.abs(p.x - pt.x) <= 1e-6 * Math.max(1, Math.abs(p.x)))
      if (hit) onPeakClick(hit)
    },
    [onPeakClick, peakTraceIndex, peaks]
  )

  if (empty) {
    return (
      <div
        className={cn(
          "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No spectrum data available yet.</p>
      </div>
    )
  }

  if (mismatch) {
    return (
      <div className={cn("space-y-3", className)}>
        <Alert role="alert">
          <AlertTitle>Warning</AlertTitle>
          <AlertDescription>
            The x and y arrays have different lengths ({x.length} vs {y.length}) and cannot be plotted together.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const hasOverlayRow = overlays.length > 0
  const effectiveHeight = isMobile ? Math.min(Math.max(Math.floor(viewportHeight * 0.42), 260), 420) : height
  const isDisplayDownsampled =
    displayPrimary.reduced || displayOverlays.some((ov) => ov.reduced)

  return (
    <div
      className={cn("flex min-w-0 max-w-full flex-col gap-3 overflow-x-hidden", className)}
      aria-label={`${nucleus ?? "Spectrum"} 1D display`}
    >
      {nucleus ? (
        <p className="text-xs text-muted-foreground">
          Context: <span className="font-mono font-medium text-foreground">{nucleus}</span>
        </p>
      ) : null}

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
            <p className="max-w-xs">Reset the view to the current spectrum range.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={fullView}
              aria-label="Full view"
            >
              <Expand className="mr-1 h-4 w-4" aria-hidden />
              Full view
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show the full x-axis range of the spectrum.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => pan("left")}
              aria-label="Pan left"
            >
              <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
              Pan left
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Shift the x-axis view to lower values.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => pan("right")}
              aria-label="Pan right"
            >
              <ArrowRight className="mr-1 h-4 w-4" aria-hidden />
              Pan right
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Shift the x-axis view to higher values.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => bumpPeakHeight(1)}
              aria-label="Increase peak height"
            >
              <Plus className="mr-1 h-4 w-4" aria-hidden />
              Increase peak height
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Stretch the vertical axis to emphasize peak tops (display only).</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => bumpPeakHeight(-1)}
              aria-label="Decrease peak height"
            >
              <Minus className="mr-1 h-4 w-4" aria-hidden />
              Decrease peak height
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Compress the vertical axis (display only).</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={showPeakLabels ? "secondary" : "outline"}
              size="sm"
              className="w-full sm:w-auto"
              onClick={() => setShowPeakLabels((v) => !v)}
              aria-label="Toggle labels"
            >
              {showPeakLabels ? <Eye className="mr-1 h-4 w-4" /> : <EyeOff className="mr-1 h-4 w-4" />}
              Toggle labels
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show or hide peak annotation labels.</p>
          </TooltipContent>
        </Tooltip>

        {hasOverlayRow ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant={showOverlaysMaster ? "secondary" : "outline"}
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setShowOverlaysMaster((v) => !v)}
                aria-label="Toggle overlays"
              >
                <Layers className="mr-1 h-4 w-4" aria-hidden />
                Toggle overlays
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p className="max-w-xs">Show or hide comparison overlays.</p>
            </TooltipContent>
          </Tooltip>
        ) : null}

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
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={fullView}>
                Full view
              </Button>
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => pan("left")}>
                Pan left
              </Button>
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => pan("right")}>
                Pan right
              </Button>
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => bumpPeakHeight(1)}>
                Increase peak height
              </Button>
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => bumpPeakHeight(-1)}>
                Decrease peak height
              </Button>
              <Button
                type="button"
                variant={showPeakLabels ? "secondary" : "outline"}
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setShowPeakLabels((v) => !v)}
              >
                Toggle labels
              </Button>
              {hasOverlayRow ? (
                <Button
                  type="button"
                  variant={showOverlaysMaster ? "secondary" : "outline"}
                  size="sm"
                  className="w-full sm:w-auto"
                  onClick={() => setShowOverlaysMaster((v) => !v)}
                >
                  Toggle overlays
                </Button>
              ) : null}
              <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => void exportImage()}>
                Export image
              </Button>
            </div>
          </details>
        )}
      </div>

      <div className="space-y-2 px-0.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex cursor-help flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <Label className="text-xs text-muted-foreground" htmlFor="spectrum-viewer-1d-gain">
                Intensity gain (display only)
              </Label>
              <span className="font-mono text-xs text-muted-foreground tabular-nums">
                ×{Math.exp(gain01 * Math.log(50001)).toExponential(2)}
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="top">
            <p className="max-w-xs">
              Display-only intensity gain. This magnifies small peaks visually without changing the original data.
            </p>
          </TooltipContent>
        </Tooltip>
        <Slider
          id="spectrum-viewer-1d-gain"
          value={[gain01 * 100]}
          min={0}
          max={100}
          step={0.5}
          onValueChange={(v) => setGain01((v[0] ?? 45) / 100)}
          aria-label="Intensity gain"
          className="py-2"
        />
      </div>

      <div
        className="min-h-[280px] w-full min-w-0 overflow-hidden rounded-lg border bg-card"
        style={{ height: effectiveHeight }}
      >
        <Plot
          data={data}
          layout={layout}
          config={{
            displayModeBar: true,
            displaylogo: false,
            responsive: true,
            scrollZoom: true,
            toImageButtonOptions: { filename: "spectrum" },
          }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
          onRelayout={onRelayout}
          onInitialized={onInitialized}
          onClick={handlePlotClick}
        />
      </div>
      {isDisplayDownsampled ? (
        <p className="text-xs text-muted-foreground">Display downsampled on mobile. Full resolution available on desktop.</p>
      ) : null}
    </div>
  )
}

function yMinShiftedGain(peakY: number, ySeries: number[], gainSlider01: number): number {
  let yMin = Infinity
  for (const v of ySeries) {
    if (!Number.isFinite(v)) continue
    if (v < yMin) yMin = v
  }
  if (!Number.isFinite(yMin)) yMin = 0
  const mult = Math.exp(gainSlider01 * Math.log(50001))
  const scaled = yMin + (peakY - yMin) * mult
  if (!Number.isFinite(scaled)) return yMin
  const mag = Math.abs(scaled)
  const capped = Math.sign(scaled) * Math.min(mag, DISPLAY_Y_CAP)
  return Math.min(Math.max(capped, -DISPLAY_Y_CAP), DISPLAY_Y_CAP)
}
