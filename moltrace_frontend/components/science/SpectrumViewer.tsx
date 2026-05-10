"use client"

import dynamic from "next/dynamic"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"
import {
  ArrowLeft,
  ArrowRight,
  Expand,
  Eye,
  EyeOff,
  GripHorizontal,
  Hand,
  Layers,
  Minus,
  MousePointer2,
  Plus,
  RotateCcw,
  ZoomIn,
  ZoomOut,
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

/** Exponential mapping: slider 0..1 → multiplier 1..50000. */
function gainMultiplier(gainSlider01: number): number {
  return Math.exp(gainSlider01 * Math.log(50001))
}

/**
 * Scale source y-array by combined gain × yZoom for display.
 * Both controls multiply the peak heights — this is what users see grow
 * vertically when they drag the slider or click "Taller peaks".
 */
function deriveDisplayY(y: number[], gainSlider01: number, yZoom: number): number[] {
  const total = gainMultiplier(gainSlider01) * yZoom
  return y.map((v) => {
    const raw = v * total
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
  // Default gain01 = 0 → multiplier 1×, so the entire spectrum fits within the
  // chart's baseline y-axis on initial render and after a Full-spectrum reset.
  const [gain01, setGain01] = useState(0)
  const [showPeaks, setShowPeaks] = useState(true)
  const [showPredicted, setShowPredicted] = useState(true)
  // yZoom is a discrete-step companion to gain01. Both multiply displayY (so peaks visibly grow).
  const [yZoom, setYZoom] = useState(1)
  // Drag mode for the chart canvas:
  //  - "zoom" (default) → drag selects a zoom box (Plotly default).
  //  - "pan"            → drag moves the visible window around (free-look mode).
  // Toggleable from the floating toolbar; reset on "Full spectrum".
  const [dragMode, setDragMode] = useState<"zoom" | "pan">("zoom")
  // Floating draggable toolbar offset (relative to default top-right corner).
  // Drag persists per session in component state.
  const [toolbarOffset, setToolbarOffset] = useState({ x: 0, y: 0 })

  const displayY = useMemo(() => deriveDisplayY(y, gain01, yZoom), [y, gain01, yZoom])
  const displayPred = useMemo(() => {
    if (!overlays?.predicted) return null
    return deriveDisplayY(overlays.predicted.y, gain01, yZoom)
  }, [overlays, gain01, yZoom])

  /**
   * yMax is anchored to the BASELINE (un-scaled) source data. This is the
   * critical fix: when gain or yZoom go up, displayY values increase but
   * yMax stays fixed, so the rendered peaks visibly grow taller within the
   * plot area (instead of the y-axis just rescaling its labels).
   * Tall peaks may clip at the top — that's standard NMR display behavior.
   */
  const { xMin, xMax, yMax } = useMemo(() => {
    if (x.length === 0) {
      return { xMin: 0, xMax: 1, yMax: 1 }
    }
    const xi = x.map(Number)
    const obsBaseline = y.length ? Math.max(...y.map((v) => (Number.isFinite(v) ? Math.abs(v) : 0))) : 1
    const predBaseline =
      showPredicted && overlays?.predicted && overlays.predicted.y.length
        ? Math.max(...overlays.predicted.y.map((v) => (Number.isFinite(v) ? Math.abs(v) : 0)))
        : 0
    return {
      xMin: Math.min(...xi),
      xMax: Math.max(...xi),
      yMax: Math.max(obsBaseline, predBaseline, 1),
    }
  }, [x, y, overlays, showPredicted])

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
      const totalScale = gainMultiplier(gain01) * yZoom
      const px = peaks.map((p) => p.ppm)
      const py = peaks.map((p) =>
        p.intensity != null ? p.intensity * totalScale : nearestYAtPpm(x, displayY, p.ppm)
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
  }, [x, displayY, displayPred, overlays, peaks, showPeaks, showPredicted, gain01, yZoom])

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { l: 52, r: 16, t: 28, b: 44 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: Boolean(overlays?.predicted && showPredicted) || (showPeaks && peaks.length > 0),
      // dragmode: "zoom" → drag to select a zoom box (default).
      //          "pan"  → drag to move the visible window around freely.
      dragmode: dragMode,
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
    [xLabel, yLabel, reversedXAxis, xRange, effectiveXMin, effectiveXMax, yMax, overlays, showPredicted, peaks.length, showPeaks, dragMode]
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

  /**
   * Full reset — restores every interactive setting to its first-preview state:
   *   • xRange   → null (Plotly autorange shows the full data span)
   *   • yZoom    → 1× (no peak height bumping)
   *   • gain01   → 0 (multiplier 1×; whole spectrum fits inside the y-axis)
   *   • dragMode → "zoom" (default Plotly drag-to-zoom-box behavior)
   * Both "Reset zoom" and "Full spectrum" route through this so they always
   * restore the exact view the user saw on first preview.
   */
  const resetAll = useCallback(() => {
    setXRange(null)
    setYZoom(1)
    setGain01(0)
    setDragMode("zoom")
  }, [])

  const resetZoom = resetAll
  const fullSpectrum = resetAll

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

  /** X-axis zoom in/out — narrows or widens the visible range around its center. */
  const zoom = useCallback(
    (dir: "in" | "out") => {
      const span = effectiveXMax - effectiveXMin || 1
      const center = (effectiveXMin + effectiveXMax) / 2
      const nextSpan = dir === "in" ? span * 0.7 : span * 1.4
      setXRange([center - nextSpan / 2, center + nextSpan / 2])
    },
    [effectiveXMin, effectiveXMax],
  )

  // ── Non-passive wheel handler for the gain rail ─────────────────────────
  // React's onWheel is passive by default in modern browsers, so calling
  // preventDefault inside it is silently ignored and the page scrolls anyway.
  // Attach a native non-passive listener so wheel scrolling on the rail
  // adjusts gain WITHOUT scrolling the surrounding page.
  const gainRailRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = gainRailRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const delta = -e.deltaY * 0.0008
      setGain01((g) => Math.min(1, Math.max(0, g + delta)))
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [])

  // ── Floating-toolbar pointer drag ───────────────────────────────────────
  const chartContainerRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<{
    pointerId: number
    startClientX: number
    startClientY: number
    startOffsetX: number
    startOffsetY: number
  } | null>(null)

  const startDrag = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      // Only start drag on primary button (left mouse / single touch).
      if (e.button !== 0) return
      const target = e.currentTarget
      target.setPointerCapture(e.pointerId)
      dragStateRef.current = {
        pointerId: e.pointerId,
        startClientX: e.clientX,
        startClientY: e.clientY,
        startOffsetX: toolbarOffset.x,
        startOffsetY: toolbarOffset.y,
      }
    },
    [toolbarOffset],
  )

  const onDragMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragStateRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    const dx = e.clientX - drag.startClientX
    const dy = e.clientY - drag.startClientY
    // Clamp panel so it stays inside the chart container's bounds.
    const container = chartContainerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    // Toolbar is anchored to top-right; positive X offset moves it LEFT, positive Y moves it DOWN.
    // Use raw deltas: dx becomes -newOffsetX (panel moves with cursor), dy becomes newOffsetY.
    const nextX = drag.startOffsetX - dx
    const nextY = drag.startOffsetY + dy
    // Allow movement within a reasonable margin (0..rect.width-100 on x, 0..rect.height-60 on y).
    const clampedX = Math.max(0, Math.min(rect.width - 100, nextX))
    const clampedY = Math.max(0, Math.min(rect.height - 60, nextY))
    setToolbarOffset({ x: clampedX, y: clampedY })
  }, [])

  const endDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragStateRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // pointer may have already been released; ignore.
    }
    dragStateRef.current = null
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

      {/*
        Sticky spectrum container — pins to the top of the scrolling main panel
        so spectrum operations (gain, zoom, drag, etc.) stay in view while the
        user scrolls through Step 3 details (KPIs, picked peaks, etc.) below.
      */}
      <div
        ref={chartContainerRef}
        className="group sticky top-4 z-10 h-[min(560px,70vh)] min-h-[320px] w-full min-w-0 overflow-hidden rounded-lg border bg-card"
      >
        <Plot
          data={data}
          layout={layout}
          config={{
            // Hide Plotly's built-in modebar — we provide a draggable, hover-revealed
            // floating toolbar below that covers the same actions plus our app-specific toggles.
            displayModeBar: false,
            displaylogo: false,
            responsive: true,
            scrollZoom: true,
          }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
          onRelayout={onRelayout}
        />

        {/*
          Floating, draggable, hover-revealed toolbar.
          - Defaults to the top-right corner of the chart.
          - User can grab the GripHorizontal handle and drag it anywhere within
            the chart bounds (clamped in onDragMove).
          - Hover-revealed via group-hover so it doesn't block the chart on idle.
          - All button functions preserved from the previous static toolbar.
        */}
        <div
          className={cn(
            "absolute z-20 select-none rounded-lg",
            "border border-border/40 bg-background/90 shadow-md backdrop-blur-md",
            "opacity-0 transition-opacity duration-200",
            "group-hover:opacity-100 group-focus-within:opacity-100 hover:opacity-100",
          )}
          style={{
            top: 12 + toolbarOffset.y,
            right: 12 + toolbarOffset.x,
          }}
        >
          {/* Drag handle — pointer events here move the panel. */}
          <div
            role="toolbar"
            aria-label="Spectrum controls (drag to reposition)"
            onPointerDown={startDrag}
            onPointerMove={onDragMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            className="flex cursor-grab items-center justify-center gap-1 border-b border-border/40 px-2 py-1 text-muted-foreground active:cursor-grabbing"
          >
            <GripHorizontal className="h-3 w-3" aria-hidden />
            <span className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]">
              Controls
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1 p-1.5">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={fullSpectrum}
              title="Full spectrum (reset to first-preview view)"
            >
              <Expand className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Full spectrum</span>
            </Button>
            {/*
              Drag-mode toggle:
              - When OFF (zoom): drag = box-zoom (Plotly default).
              - When ON  (pan):  drag = move the spectrum around freely.
              The icon swaps to communicate which mode is currently active.
            */}
            <Button
              type="button"
              variant={dragMode === "pan" ? "secondary" : "outline"}
              size="icon"
              className="h-7 w-7"
              onClick={() => setDragMode((m) => (m === "pan" ? "zoom" : "pan"))}
              title={
                dragMode === "pan"
                  ? "Move mode ON — drag the spectrum to pan. Click to switch back to zoom-box."
                  : "Move mode OFF — drag the spectrum to zoom-box. Click to switch to pan."
              }
              aria-pressed={dragMode === "pan"}
            >
              {dragMode === "pan" ? (
                <Hand className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <MousePointer2 className="h-3.5 w-3.5" aria-hidden />
              )}
              <span className="sr-only">
                {dragMode === "pan" ? "Pan mode active (drag spectrum to move)" : "Zoom mode active (drag spectrum to box-zoom)"}
              </span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => zoom("in")}
              title="Zoom in (x-axis)"
            >
              <ZoomIn className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Zoom in</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => zoom("out")}
              title="Zoom out (x-axis)"
            >
              <ZoomOut className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Zoom out</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => pan("left")}
              title="Pan left"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Pan left</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => pan("right")}
              title="Pan right"
            >
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Pan right</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => bumpPeakHeight(1)}
              title="Taller peaks"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Taller peaks</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => bumpPeakHeight(-1)}
              title="Shorter peaks"
            >
              <Minus className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Shorter peaks</span>
            </Button>
            <Button
              type="button"
              variant={showPeaks ? "secondary" : "outline"}
              size="icon"
              className="h-7 w-7"
              onClick={() => setShowPeaks((v) => !v)}
              title={showPeaks ? "Hide peak labels" : "Show peak labels"}
            >
              {showPeaks ? <Eye className="h-3.5 w-3.5" aria-hidden /> : <EyeOff className="h-3.5 w-3.5" aria-hidden />}
              <span className="sr-only">{showPeaks ? "Hide" : "Show"} peak labels</span>
            </Button>
            {overlays?.predicted && (
              <Button
                type="button"
                variant={showPredicted ? "secondary" : "outline"}
                size="icon"
                className="h-7 w-7"
                onClick={() => setShowPredicted((v) => !v)}
                title={showPredicted ? "Hide predicted overlay" : "Show predicted overlay"}
              >
                <Layers className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">{showPredicted ? "Hide" : "Show"} predicted overlay</span>
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={resetZoom}
              title="Reset zoom"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Reset zoom</span>
            </Button>
          </div>
        </div>

        {/*
          Modern vertical intensity gain rail.
          - Anchored to the right edge of the (sticky) chart container — never
            scrolls away with the page.
          - Hidden until hover/focus on the chart; opacity transition.
          - Wheel scroll on the rail adjusts gain (non-passive listener attached
            via useEffect so preventDefault actually blocks page scroll).
          - Vertical Radix slider — drag thumb with mouse / touchpad / touch.
          - ArrowUp / ArrowDown for keyboard control when slider is focused.
        */}
        <div
          ref={gainRailRef}
          className={cn(
            "absolute top-3 right-3 bottom-3 z-10 flex w-11 flex-col items-center gap-2 rounded-lg",
            "border border-border/40 bg-background/85 px-1.5 py-3 shadow-sm backdrop-blur-md",
            "opacity-0 transition-opacity duration-200",
            "group-hover:opacity-100 group-focus-within:opacity-100 hover:opacity-100",
          )}
          aria-label="Intensity gain"
        >
          <span
            className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground"
            aria-hidden
          >
            Gain
          </span>
          <Slider
            orientation="vertical"
            value={[gain01 * 100]}
            min={0}
            max={100}
            step={0.5}
            onValueChange={(v) => setGain01((v[0] ?? 0) / 100)}
            className="flex-1"
            aria-label="Intensity gain (display only)"
          />
          <span
            className="font-mono text-[9px] tabular-nums text-muted-foreground"
            title={`Total scale = gain × yZoom. yZoom=${yZoom.toFixed(2)}`}
          >
            ×{(gainMultiplier(gain01) * yZoom).toExponential(1)}
          </span>
        </div>
      </div>
    </div>
  )
}
