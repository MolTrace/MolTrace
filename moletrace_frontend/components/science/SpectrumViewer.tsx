"use client"

import dynamic from "next/dynamic"
import React, { useCallback, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"
import {
  ArrowLeft,
  ArrowRight,
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

/** Peak annotations from backend (no frontend picking). */
export type SpectrumPeakAnnotation = {
  ppm: number
  intensity?: number
  label?: string
}

export type SpectrumOverlays = {
  predicted?: {
    x: number[]
    y: number[]
    label?: string
  }
}

export type SpectrumViewerProps = {
  x: number[]
  y: number[]
  peaks?: SpectrumPeakAnnotation[]
  overlays?: SpectrumOverlays
  /** Reserved for titles / accessibility when wiring experiment context */
  nucleus?: "1H" | "13C"
  xLabel?: string
  yLabel?: string
  reversedXAxis?: boolean
  className?: string
}

const DISPLAY_Y_CAP = 1e120

function deriveDisplayY(y: number[], gainSlider01: number): number[] {
  // Slider 0–1 → multiplier ~1 .. ~5e4 via exponential (smooth, very high headroom)
  const mult = Math.exp(gainSlider01 * Math.log(50001))
  return y.map((v) => {
    const raw = v * mult
    if (!Number.isFinite(raw)) return 0
    return Math.min(Math.sign(raw) * Math.min(Math.abs(raw), DISPLAY_Y_CAP), DISPLAY_Y_CAP)
  })
}

function nearestYAtPpm(x: number[], yDisplay: number[], ppm: number): number {
  if (x.length === 0) return 0
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < x.length; i++) {
    const d = Math.abs(x[i] - ppm)
    if (d < bestD) {
      bestD = d
      best = yDisplay[i] ?? 0
    }
  }
  return best
}

export function SpectrumViewer({
  x,
  y,
  peaks = [],
  overlays,
  nucleus,
  xLabel = "ppm",
  yLabel = "Intensity",
  reversedXAxis = true,
  className,
}: SpectrumViewerProps) {
  const [gain01, setGain01] = useState(0.45)
  const [showPeaks, setShowPeaks] = useState(true)
  const [showPredicted, setShowPredicted] = useState(true)
  const [yZoom, setYZoom] = useState(1)

  const displayY = useMemo(() => deriveDisplayY(y, gain01), [y, gain01])
  const displayPred = useMemo(() => {
    if (!overlays?.predicted) return null
    return deriveDisplayY(overlays.predicted.y, gain01)
  }, [overlays, gain01])

  const { xMin, xMax, yMax } = useMemo(() => {
    if (x.length === 0) {
      return { xMin: 0, xMax: 1, yMax: 1 }
    }
    const xi = x.map(Number)
    const ys = displayY
    const localYMax = ys.length ? Math.max(...ys.map((v) => (Number.isFinite(v) ? v : 0))) : 1
    const predY =
      showPredicted && displayPred && displayPred.length
        ? Math.max(...displayPred.map((v) => (Number.isFinite(v) ? v : 0)))
        : 0
    return {
      xMin: Math.min(...xi),
      xMax: Math.max(...xi),
      yMax: Math.max(localYMax, predY, 1) * yZoom,
    }
  }, [x, displayY, displayPred, showPredicted, yZoom])

  const [xRange, setXRange] = useState<[number, number] | null>(null)

  const effectiveXMin = xRange ? xRange[0] : xMin
  const effectiveXMax = xRange ? xRange[1] : xMax

  const data = useMemo(() => {
    if (x.length === 0) return []
    const traces: object[] = [
      {
        type: "scattergl",
        mode: "lines",
        x,
        y: displayY,
        name: "Observed",
        line: { width: 1.2, color: "#2563eb" },
      },
    ]
    if (
      showPredicted &&
      overlays?.predicted &&
      overlays.predicted.x.length === overlays.predicted.y.length &&
      displayPred
    ) {
      traces.push({
        type: "scattergl",
        mode: "lines",
        x: overlays.predicted.x,
        y: displayPred,
        name: overlays.predicted.label ?? "Predicted",
        line: { width: 1, dash: "dash", color: "#c026d3" },
        opacity: 0.85,
      })
    }
    if (showPeaks && peaks.length > 0) {
      const px = peaks.map((p) => p.ppm)
      const py = peaks.map((p) =>
        p.intensity != null ? p.intensity * Math.exp(gain01 * Math.log(50001)) : nearestYAtPpm(x, displayY, p.ppm)
      )
      traces.push({
        type: "scattergl",
        mode: "markers+text",
        x: px,
        y: py,
        text: peaks.map((p) => p.label ?? ""),
        textposition: "top center",
        name: "Peaks",
        marker: { size: 7, color: "#ea580c", line: { width: 0.5, color: "#fff" } },
        textfont: { size: 10 },
      })
    }
    return traces
  }, [x, displayY, displayPred, overlays, peaks, showPeaks, showPredicted, gain01])

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { l: 52, r: 16, t: 28, b: 44 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: Boolean(overlays?.predicted && showPredicted) || (showPeaks && peaks.length > 0),
      xaxis: {
        title: xLabel,
        autorange: reversedXAxis ? "reversed" : true,
        range: xRange ? [effectiveXMin, effectiveXMax] : undefined,
        zeroline: false,
      },
      yaxis: {
        title: yLabel,
        range: [0, yMax],
        zeroline: false,
        fixedrange: false,
      },
      hovermode: "closest",
      uirevision: "spectrum",
    }),
    [xLabel, yLabel, reversedXAxis, xRange, effectiveXMin, effectiveXMax, yMax, overlays, showPredicted, peaks.length, showPeaks]
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
    setYZoom(1)
    setGain01(0.45)
  }, [])

  const fullSpectrum = useCallback(() => {
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

  const placeholder = x.length === 0 || y.length === 0 || x.length !== y.length

  if (placeholder) {
    return (
      <div
        className={cn(
          "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No spectrum loaded</p>
        <p className="mt-1 max-w-md">
          Upload and preview/process on the server to plot ppm vs intensity ({nucleus ?? "1H/13C"}). Display gain only
          scales rendering — source arrays are never modified.
        </p>
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col gap-3", className)} aria-label={`${nucleus ?? "NMR"} spectrum display`}>
      {nucleus && (
        <p className="text-xs text-muted-foreground">
          Nucleus context: <span className="font-mono font-medium text-foreground">{nucleus}</span>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 border-b pb-3">
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={resetZoom}>
          <RotateCcw className="mr-1 h-4 w-4" aria-hidden />
          Reset zoom
        </Button>
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={fullSpectrum}>
          <Expand className="mr-1 h-4 w-4" aria-hidden />
          Full spectrum
        </Button>
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => bumpPeakHeight(1)}>
          <Plus className="mr-1 h-4 w-4" aria-hidden />
          Taller peaks
        </Button>
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => bumpPeakHeight(-1)}>
          <Minus className="mr-1 h-4 w-4" aria-hidden />
          Shorter peaks
        </Button>
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => pan("left")}>
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden />
          Pan left
        </Button>
        <Button type="button" variant="outline" size="sm" className="w-full sm:w-auto" onClick={() => pan("right")}>
          <ArrowRight className="mr-1 h-4 w-4" aria-hidden />
          Pan right
        </Button>
        <Button
          type="button"
          variant={showPeaks ? "secondary" : "outline"}
          size="sm"
          className="w-full sm:w-auto"
          onClick={() => setShowPeaks((v) => !v)}
        >
          {showPeaks ? <Eye className="mr-1 h-4 w-4" /> : <EyeOff className="mr-1 h-4 w-4" />}
          Peak labels
        </Button>
        {overlays?.predicted && (
          <Button
            type="button"
            variant={showPredicted ? "secondary" : "outline"}
            size="sm"
            className="w-full sm:w-auto"
            onClick={() => setShowPredicted((v) => !v)}
          >
            <Layers className="mr-1 h-4 w-4" />
            Predicted overlay
          </Button>
        )}
      </div>

      <div className="space-y-2 px-0.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Label className="text-xs text-muted-foreground">Intensity gain (display only)</Label>
          <span className="font-mono text-xs text-muted-foreground tabular-nums">
            ×{Math.exp(gain01 * Math.log(50001)).toExponential(2)}
          </span>
        </div>
        <Slider value={[gain01 * 100]} min={0} max={100} step={0.5} onValueChange={(v) => setGain01((v[0] ?? 45) / 100)} />
      </div>

      <div className="h-[min(420px,55vh)] min-h-[280px] w-full min-w-0 overflow-hidden rounded-lg border bg-card">
        <Plot
          data={data}
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
        />
      </div>
    </div>
  )
}
