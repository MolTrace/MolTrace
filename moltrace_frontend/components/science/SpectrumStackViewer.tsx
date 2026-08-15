"use client"

/**
 * Cascade / overlay view of several 1D spectra on one shared ppm axis — the stacked plot a
 * chemist reaches for the moment there is more than one dataset to look at.
 *
 * Interaction follows the MolTrace canvas gesture contract (lib/science/canvas-interaction.ts):
 * hover = crosshair readout | drag = pan when zoomed | shift+drag = zoom to window | wheel while
 * focused = vertical intensity | arrows pan | +/- zoom | 0 and double-click = full range and
 * intensity x1 | Esc cancels the in-progress drag and never resets the view.
 *
 * Deliberately NOT built on `SpectrumViewer`. That component is one trace with its own private
 * zoom state, a fixed 360px height, and a per-instance resize + hover loop, so N of them can
 * neither share an axis nor stay cheap. It is also not built on Plotly: a stack is polylines on a
 * shared axis, and hand-drawn SVG keeps one graph node instead of N WebGL contexts, renders the
 * same in a test as in a browser, and lets the cascade offset be a first-class control.
 *
 * The single spectrum view is unchanged and still authoritative for a selected dataset — this is
 * the comparison surface that sits above it.
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react"
import { Layers, RotateCcw } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  CANVAS_INTENSITY_MAX,
  CANVAS_INTENSITY_MIN,
  canvasKeyAction,
  clampSpanToDomain,
  formatHoverPpm,
  isZoomWindowChord,
  panSpan,
  spanFromDrag,
  wheelIntensityFactor,
  zoomSpanAboutCentre,
} from "@/lib/science/canvas-interaction"

export type SpectrumStackTrace = {
  id: string
  label: string
  x: number[]
  y: number[]
  /** Secondary line under the label — sample id, nucleus, whatever identifies the run. */
  sublabel?: string
}

export type SpectrumStackViewerProps = {
  traces: SpectrumStackTrace[]
  /**
   * Nucleus the AXIS describes. Null when the stack holds more than one, or when nothing reported
   * it — the axis then says "chemical shift" without naming a nucleus it cannot vouch for. Must
   * come from what each trace was actually run with, never from a live acquisition control: that
   * control keeps changing to set up the next batch, and a ¹³C label over ¹H traces is a lie the
   * reviewer has no way to catch.
   */
  nucleus?: "1H" | "13C" | null
  /** Highlighted trace. Everything else dims, so the reviewer can find it in a crowded stack. */
  activeTraceId?: string | null
  onSelectTrace?: (id: string) => void
  className?: string
  testId?: string
}

/**
 * Per-trace colours. Sharing one colour across N traces — as the single-spectrum overlay path
 * does for its predicted trace — would make a stack unreadable, so each gets its own and the
 * legend is the key.
 */
const STACK_TRACE_COLORS = [
  "#2563eb",
  "#ea580c",
  "#16a34a",
  "#a855f7",
  "#e11d48",
  "#0d9488",
  "#ca8a04",
  "#4f46e5",
] as const

export function stackTraceColor(index: number): string {
  return STACK_TRACE_COLORS[index % STACK_TRACE_COLORS.length]
}

/**
 * A SECOND channel that is not colour, so the palette wrapping does not make two datasets
 * indistinguishable.
 *
 * The queue holds up to 64 datasets and there are 8 colours, so trace 9 gets trace 1's blue. When
 * colour is the only link between a legend entry and a line, two identical blue lines are two
 * datasets the reviewer cannot tell apart. Cycling a dash pattern every time the colour wraps
 * gives 8 x 4 distinct pens, and it is also the channel a colour-blind reviewer can actually use.
 */
const STACK_TRACE_DASHES = ["", "7 3", "2 3", "10 3 2 3"] as const

export function stackTraceDash(index: number): string {
  const cycle = Math.floor(index / STACK_TRACE_COLORS.length)
  return STACK_TRACE_DASHES[cycle % STACK_TRACE_DASHES.length]
}

const VIEW_WIDTH = 1000
const VIEW_HEIGHT = 460
const MARGIN = { top: 16, right: 18, bottom: 38, left: 20 } as const
const PLOT_LEFT = MARGIN.left
const PLOT_RIGHT = VIEW_WIDTH - MARGIN.right
const PLOT_TOP = MARGIN.top
const PLOT_BOTTOM = VIEW_HEIGHT - MARGIN.bottom
const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT
const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP

/** Columns of the min/max envelope. One per ~1.5 viewBox units keeps narrow peaks intact. */
const ENVELOPE_COLUMNS = 620

/** Smallest ppm window a drag may select — below this a stray click would zoom to nothing. */
const MIN_PPM_SPAN = 0.02

export type EnvelopePoint = { ppm: number; low: number; high: number }

/**
 * Min/max envelope downsampling.
 *
 * Averaging or striding would drop a narrow doublet outright — the very feature the reviewer is
 * comparing. Keeping BOTH extremes of each column preserves every peak's height and the noise
 * band's thickness at any zoom level, which is what makes a downsampled NMR trace honest.
 */
export function envelopeSampleSpectrum(
  x: readonly number[],
  y: readonly number[],
  range: { min: number; max: number },
  columns = ENVELOPE_COLUMNS,
): EnvelopePoint[] {
  const length = Math.min(x.length, y.length)
  if (length === 0 || columns < 1) return []
  const span = range.max - range.min
  if (!Number.isFinite(span) || span <= 0) return []

  const lows = new Float64Array(columns).fill(Number.POSITIVE_INFINITY)
  const highs = new Float64Array(columns).fill(Number.NEGATIVE_INFINITY)
  const filled = new Uint8Array(columns)

  for (let i = 0; i < length; i++) {
    const ppm = x[i]
    const value = y[i]
    if (!Number.isFinite(ppm) || !Number.isFinite(value)) continue
    if (ppm < range.min || ppm > range.max) continue
    let column = Math.floor(((ppm - range.min) / span) * columns)
    if (column >= columns) column = columns - 1
    if (column < 0) column = 0
    if (value < lows[column]) lows[column] = value
    if (value > highs[column]) highs[column] = value
    filled[column] = 1
  }

  const out: EnvelopePoint[] = []
  for (let column = 0; column < columns; column++) {
    if (!filled[column]) continue
    out.push({
      ppm: range.min + ((column + 0.5) / columns) * span,
      low: lows[column],
      high: highs[column],
    })
  }
  return out
}

type PreparedTrace = {
  trace: SpectrumStackTrace
  color: string
  /** Second, non-colour channel — see `stackTraceDash`. Empty string means a solid line. */
  dash: string
  points: EnvelopePoint[]
  /** Largest value inside the visible window — the trace's own normalisation reference. */
  peak: number
  fullRange: { min: number; max: number } | null
}

function finiteRange(values: readonly number[]): { min: number; max: number } | null {
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY
  for (const value of values) {
    if (!Number.isFinite(value)) continue
    if (value < min) min = value
    if (value > max) max = value
  }
  return Number.isFinite(min) && Number.isFinite(max) && max > min ? { min, max } : null
}

function niceTicks(min: number, max: number, target = 8): number[] {
  const span = max - min
  if (!Number.isFinite(span) || span <= 0) return []
  const rough = span / target
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const normalized = rough / magnitude
  const step = (normalized >= 5 ? 10 : normalized >= 2 ? 5 : normalized >= 1 ? 2 : 1) * magnitude
  const ticks: number[] = []
  for (let tick = Math.ceil(min / step) * step; tick <= max + step * 1e-9; tick += step) {
    ticks.push(Math.abs(tick) < step * 1e-9 ? 0 : tick)
  }
  return ticks
}

function formatPpm(value: number): string {
  const abs = Math.abs(value)
  return abs >= 100 ? value.toFixed(0) : abs >= 10 ? value.toFixed(1) : value.toFixed(2)
}

export function SpectrumStackViewer({
  traces,
  nucleus = null,
  activeTraceId = null,
  onSelectTrace,
  className,
  testId = "spectrum-stack-viewer",
}: SpectrumStackViewerProps) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const clipId = useId().replace(/:/g, "")

  const [cascade, setCascade] = useState(0.45)
  const [sharedScale, setSharedScale] = useState(false)
  const [hidden, setHidden] = useState<Set<string>>(() => new Set())
  const [zoom, setZoom] = useState<{ min: number; max: number } | null>(null)
  /**
   * The in-progress pointer gesture. `window` is the shift+drag zoom selection; `pan` grabs the
   * content so the ppm under the pointer stays under it. Plain drag at full range is neither —
   * there is nothing to pan and zooming is the explicit chord, so it does nothing.
   */
  const [drag, setDrag] = useState<
    | { kind: "window"; from: number; to: number }
    | { kind: "pan"; startViewX: number; startZoom: { min: number; max: number } }
    | null
  >(null)
  const [hoverPpm, setHoverPpm] = useState<number | null>(null)
  /** Wheel-driven display multiplier on trace amplitude. Display-only; the clamp in `pathFor`
   *  still bounds the drawn excursion, so a large gain clips rather than invading neighbours. */
  const [verticalGain, setVerticalGain] = useState(1)

  const visibleTraces = useMemo(
    () => traces.filter((trace) => !hidden.has(trace.id)),
    [traces, hidden],
  )

  /** Full extent across every trace, so hiding one does not shift the axis under the others. */
  const fullRange = useMemo(() => {
    const ranges = traces.map((trace) => finiteRange(trace.x)).filter((r): r is { min: number; max: number } => r != null)
    if (ranges.length === 0) return null
    return {
      min: Math.min(...ranges.map((r) => r.min)),
      max: Math.max(...ranges.map((r) => r.max)),
    }
  }, [traces])

  const range = zoom ?? fullRange

  /** Colour is pinned to a trace's position in the FULL list, so hiding one never recolours the rest. */
  const colorIndexById = useMemo(() => {
    const index = new Map<string, number>()
    traces.forEach((trace, position) => {
      if (!index.has(trace.id)) index.set(trace.id, position)
    })
    return index
  }, [traces])

  const prepared = useMemo<PreparedTrace[]>(() => {
    if (!range) return []
    return visibleTraces.map((trace) => {
      const points = envelopeSampleSpectrum(trace.x, trace.y, range)
      let peak = 0
      for (const point of points) {
        if (point.high > peak) peak = point.high
      }
      // A trace whose visible window holds nothing positive (an empty region, or a spectrum
      // stored inverted) still has to be drawn to scale rather than vanish, so fall back to the
      // largest magnitude present before giving up and using 1.
      if (peak <= 0) {
        for (const point of points) {
          const magnitude = Math.max(Math.abs(point.low), Math.abs(point.high))
          if (magnitude > peak) peak = magnitude
        }
      }
      return {
        trace,
        color: stackTraceColor(colorIndexById.get(trace.id) ?? 0),
        dash: stackTraceDash(colorIndexById.get(trace.id) ?? 0),
        points,
        peak: peak > 0 ? peak : 1,
        fullRange: finiteRange(trace.x),
      }
    })
  }, [visibleTraces, colorIndexById, range])

  const sharedPeak = useMemo(
    () => prepared.reduce((max, item) => Math.max(max, item.peak), 0) || 1,
    [prepared],
  )

  const count = prepared.length
  const offsetSpan = count > 1 ? cascade * PLOT_HEIGHT : 0
  const amplitude = PLOT_HEIGHT - offsetSpan

  const ppmToX = useCallback(
    (ppm: number) => {
      if (!range) return PLOT_LEFT
      // Reversed axis: high ppm on the left, the universal NMR convention.
      const fraction = (range.max - ppm) / (range.max - range.min)
      return PLOT_LEFT + fraction * PLOT_WIDTH
    },
    [range],
  )

  const xToPpm = useCallback(
    (viewX: number) => {
      if (!range) return 0
      const fraction = (viewX - PLOT_LEFT) / PLOT_WIDTH
      return range.max - fraction * (range.max - range.min)
    },
    [range],
  )

  /** Pointer position in viewBox units. Guards the zero-width box a headless render reports. */
  const pointerViewX = useCallback((clientX: number): number | null => {
    const svg = svgRef.current
    if (!svg) return null
    const rect = svg.getBoundingClientRect()
    if (!rect.width) return null
    return ((clientX - rect.left) / rect.width) * VIEW_WIDTH
  }, [])

  const baselineFor = useCallback(
    (index: number) => {
      if (count <= 1) return PLOT_BOTTOM
      // Index 0 sits at the front (bottom); later traces step back and up.
      return PLOT_BOTTOM - (index / (count - 1)) * offsetSpan
    },
    [count, offsetSpan],
  )

  const pathFor = useCallback(
    (item: PreparedTrace, index: number) => {
      const baseline = baselineFor(index)
      const reference = sharedScale ? sharedPeak : item.peak
      const segments: string[] = []
      for (let i = 0; i < item.points.length; i++) {
        const point = item.points[i]
        const px = ppmToX(point.ppm)
        // Clamp the drawn excursion. A saturated solvent peak's negative dispersion lobe can dip
        // many times the analyte height; unclamped it would punch through the trace stacked
        // below it and read as that trace's own signal. Standard NMR display convention.
        const high = Math.min((point.high / reference) * verticalGain, 1.04)
        const low = Math.max((point.low / reference) * verticalGain, -0.16)
        segments.push(
          `${i === 0 ? "M" : "L"}${px.toFixed(2)} ${(baseline - high * amplitude).toFixed(2)}`,
        )
        if (low < high) segments.push(`L${px.toFixed(2)} ${(baseline - low * amplitude).toFixed(2)}`)
      }
      return segments.join(" ")
    },
    [amplitude, baselineFor, ppmToX, sharedPeak, sharedScale, verticalGain],
  )

  const ticks = useMemo(() => (range ? niceTicks(range.min, range.max) : []), [range])

  const toggleHidden = useCallback((id: string) => {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const resetView = useCallback(() => {
    setZoom(null)
    setDrag(null)
    setVerticalGain(1)
  }, [])

  // Wheel = vertical intensity, gated on keyboard focus. Ungated, a full-width chart is a scroll
  // trap in the middle of a long page; focus is the explicit opt-in, and it is the same opt-in
  // the keyboard already requires. Native + non-passive because React's onWheel is passive and
  // preventDefault would be silently ignored.
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (event: WheelEvent) => {
      if (document.activeElement !== el) return
      event.preventDefault()
      setVerticalGain((gain) =>
        Math.min(
          CANVAS_INTENSITY_MAX,
          Math.max(CANVAS_INTENSITY_MIN, gain * wheelIntensityFactor(event.deltaY)),
        ),
      )
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [])

  if (!range || traces.length === 0) {
    return (
      <div
        className={cn(
          "flex h-[220px] items-center justify-center rounded-lg border border-dashed bg-muted/20 text-center",
          className,
        )}
        data-testid={`${testId}-empty`}
      >
        {/* Says "shared ppm axis", not "shared scale": the axis really is common to every trace,
            but intensities are normalised per trace unless the reviewer asks for one scale. A
            stack that implied comparable heights by default would be the wrong claim to make. */}
        <p className="max-w-sm text-xs text-muted-foreground">
          Processed datasets appear here together on a shared ppm axis as each finishes.
        </p>
      </div>
    )
  }

  const windowDrag = drag?.kind === "window" ? drag : null
  const dragFromX = windowDrag ? ppmToX(windowDrag.from) : 0
  const dragToX = windowDrag ? ppmToX(windowDrag.to) : 0
  const zoomed = zoom != null

  return (
    <div className={cn("space-y-2", className)} data-testid={testId}>
      {/* Controls — cascade depth is the one knob that changes how a stack reads, so it is
          in front rather than behind a menu. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            <Layers className="h-3 w-3" aria-hidden />
            Cascade
          </span>
          <input
            type="range"
            min={0}
            max={0.85}
            step={0.05}
            value={cascade}
            onChange={(event) => setCascade(Number(event.target.value))}
            className="h-1 w-28 cursor-pointer accent-[color:var(--mt-teal)]"
            aria-label="Cascade offset — 0 overlays every spectrum on one baseline"
            data-testid={`${testId}-cascade`}
          />
          <span className="w-10 font-mono text-[10px] tabular-nums text-muted-foreground">
            {cascade === 0 ? "overlay" : `${Math.round(cascade * 100)}%`}
          </span>
        </label>

        <label className="flex cursor-pointer items-center gap-1.5">
          <input
            type="checkbox"
            checked={sharedScale}
            onChange={(event) => setSharedScale(event.target.checked)}
            className="h-3 w-3 accent-[color:var(--mt-teal)]"
            data-testid={`${testId}-shared-scale`}
          />
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
            One scale for all
          </span>
        </label>

        {/* Name the scaling actually in force. An unticked checkbox is a weak way to learn that
            trace heights are NOT comparable, and on a stacked spectrum that is the single easiest
            thing to read wrongly. */}
        <span
          className="font-mono text-[10px] text-muted-foreground"
          data-testid={`${testId}-scale-mode`}
        >
          {sharedScale
            ? "Heights comparable — all traces on the tallest peak in view"
            : "Heights not comparable — each trace on its own tallest peak"}
        </span>

        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {zoomed
            ? `${formatPpm(range.max)} – ${formatPpm(range.min)} ppm · drag to pan`
            : "Shift-drag a region to zoom, or focus the plot and use + and the arrows"}
        </span>

        {/* Rendered unconditionally: hiding it until zoomed meant a keyboard user who zoomed via
            the keyboard had no visible way back, and never saw that a reset existed at all. */}
        <button
          type="button"
          onClick={resetView}
          disabled={!zoomed}
          className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 motion-reduce:transition-none"
          data-testid={`${testId}-reset-zoom`}
        >
          <RotateCcw className="h-3 w-3" aria-hidden />
          Full range
        </button>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="w-full touch-none select-none rounded-lg border bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)]"
        role="img"
        tabIndex={0}
        data-testid={`${testId}-plot`}
        data-vertical-gain={verticalGain.toFixed(3)}
        onKeyDown={(event) => {
          // Shared keymap so this canvas and the single-spectrum canvas answer every key the
          // same way. Esc cancels an in-progress drag and NOTHING ELSE — a reflexive Esc must
          // not throw away the zoom a reviewer was working inside (0 resets, deliberately).
          if (event.key === "Escape") {
            if (drag) {
              event.preventDefault()
              setDrag(null)
            }
            return
          }
          const action = canvasKeyAction(event.key)
          if (!action || !fullRange) return
          event.preventDefault()
          if (action.kind === "reset") {
            resetView()
          } else if (action.kind === "pan") {
            const next = panSpan(range, fullRange, action.screenDirection, { reversedX: true })
            if (next) setZoom(next)
          } else {
            setZoom(zoomSpanAboutCentre(range, fullRange, action.factor, MIN_PPM_SPAN))
          }
        }}
        aria-label={`${count} spectra stacked on a shared ${nucleus ? `${nucleus} ` : ""}chemical-shift axis from ${formatPpm(range.max)} to ${formatPpm(range.min)} ppm. Shift-drag to zoom to a region. Arrow keys pan, plus and minus zoom, 0 restores the full range, and the mouse wheel adjusts intensity while the plot is focused.`}
        onPointerDown={(event) => {
          const viewX = pointerViewX(event.clientX)
          if (viewX == null) return
          event.currentTarget.setPointerCapture?.(event.pointerId)
          if (isZoomWindowChord(event)) {
            const ppm = xToPpm(viewX)
            setDrag({ kind: "window", from: ppm, to: ppm })
            return
          }
          // Plain drag pans the zoomed window. At full range there is nothing to pan and zoom is
          // the explicit chord, so a plain drag deliberately does nothing but focus the canvas.
          if (zoom) setDrag({ kind: "pan", startViewX: viewX, startZoom: zoom })
        }}
        onPointerMove={(event) => {
          const viewX = pointerViewX(event.clientX)
          if (viewX == null) return
          setHoverPpm(xToPpm(viewX))
          // Read the gesture from the render closure, not a state updater: a pan writes ZOOM
          // (a different piece of state), and a setState-inside-updater side effect is exactly
          // what StrictMode double-invocation punishes. The closure is fresh enough — every move
          // re-renders through setHoverPpm above.
          if (!drag) return
          if (drag.kind === "window") {
            setDrag({ ...drag, to: xToPpm(viewX) })
            return
          }
          // Content follows the pointer: the shift that keeps the grabbed ppm under the cursor
          // is the pointer's view-space travel expressed in ppm of the WINDOW AT GRAB TIME.
          const span = drag.startZoom.max - drag.startZoom.min
          const deltaPpm = ((viewX - drag.startViewX) / PLOT_WIDTH) * span
          setZoom(
            clampSpanToDomain(
              { min: drag.startZoom.min + deltaPpm, max: drag.startZoom.max + deltaPpm },
              fullRange ?? drag.startZoom,
            ),
          )
        }}
        onPointerUp={() => {
          if (!drag) return
          setDrag(null)
          if (drag.kind !== "window") return
          // A click, not a drag — leave the view alone rather than zooming to a sliver.
          const selected = spanFromDrag(drag.from, drag.to, MIN_PPM_SPAN)
          if (selected) setZoom(selected)
        }}
        onPointerLeave={() => {
          setHoverPpm(null)
          setDrag(null)
        }}
        onDoubleClick={resetView}
      >
        <defs>
          <clipPath id={`stack-clip-${clipId}`}>
            <rect x={PLOT_LEFT} y={PLOT_TOP} width={PLOT_WIDTH} height={PLOT_HEIGHT} />
          </clipPath>
        </defs>

        {/* Axis grid */}
        {ticks.map((tick) => {
          const px = ppmToX(tick)
          if (px < PLOT_LEFT || px > PLOT_RIGHT) return null
          return (
            <g key={tick}>
              <line
                x1={px}
                x2={px}
                y1={PLOT_TOP}
                y2={PLOT_BOTTOM}
                stroke="currentColor"
                strokeWidth={0.5}
                className="text-border"
              />
              <text
                x={px}
                y={PLOT_BOTTOM + 16}
                textAnchor="middle"
                className="fill-muted-foreground font-mono"
                style={{ fontSize: 11 }}
              >
                {formatPpm(tick)}
              </text>
            </g>
          )
        })}
        <line
          x1={PLOT_LEFT}
          x2={PLOT_RIGHT}
          y1={PLOT_BOTTOM}
          y2={PLOT_BOTTOM}
          stroke="currentColor"
          strokeWidth={0.8}
          className="text-border"
        />
        <text
          x={(PLOT_LEFT + PLOT_RIGHT) / 2}
          y={VIEW_HEIGHT - 6}
          textAnchor="middle"
          className="fill-muted-foreground font-mono"
          style={{ fontSize: 11 }}
        >
          {nucleus === "13C"
            ? "¹³C chemical shift (ppm)"
            : nucleus === "1H"
              ? "¹H chemical shift (ppm)"
              : "Chemical shift (ppm)"}
        </text>

        <g clipPath={`url(#stack-clip-${clipId})`}>
          {prepared.map((item, index) => {
            const isActive = activeTraceId === item.trace.id
            const dimmed = activeTraceId != null && !isActive
            return (
              <path
                key={item.trace.id}
                d={pathFor(item, index)}
                fill="none"
                stroke={item.color}
                strokeWidth={isActive ? 1.9 : 1.1}
                strokeLinejoin="round"
                strokeDasharray={item.dash || undefined}
                opacity={dimmed ? 0.32 : 1}
                data-testid={`${testId}-trace-${item.trace.id}`}
                data-active={isActive ? "true" : "false"}
              />
            )
          })}

          {/* Drag-to-zoom band */}
          {windowDrag && Math.abs(dragToX - dragFromX) > 1 ? (
            <rect
              x={Math.min(dragFromX, dragToX)}
              y={PLOT_TOP}
              width={Math.abs(dragToX - dragFromX)}
              height={PLOT_HEIGHT}
              fill="var(--mt-teal)"
              opacity={0.14}
            />
          ) : null}

          {/* Hover readout */}
          {hoverPpm != null && !drag ? (
            <g>
              <line
                x1={ppmToX(hoverPpm)}
                x2={ppmToX(hoverPpm)}
                y1={PLOT_TOP}
                y2={PLOT_BOTTOM}
                stroke="var(--mt-teal)"
                strokeWidth={0.7}
                strokeDasharray="3 3"
              />
              <text
                x={Math.min(ppmToX(hoverPpm) + 6, PLOT_RIGHT - 42)}
                y={PLOT_TOP + 12}
                className="fill-foreground font-mono"
                style={{ fontSize: 11 }}
              >
                {formatHoverPpm(hoverPpm)}
              </text>
            </g>
          ) : null}
        </g>
      </svg>

      {/* Legend — also the selector. Buttons, so the stack is reachable without a pointer. */}
      <div className="flex flex-wrap gap-1.5" data-testid={`${testId}-legend`}>
        {traces.map((trace, index) => {
          const isHidden = hidden.has(trace.id)
          const isActive = activeTraceId === trace.id
          return (
            <div key={trace.id} className="flex items-center">
              <button
                type="button"
                onClick={() => onSelectTrace?.(trace.id)}
                aria-pressed={isActive}
                className={cn(
                  "flex min-h-0 items-center gap-1.5 rounded-l-md border py-1 pl-2 pr-2 text-left transition-colors motion-reduce:transition-none",
                  isActive ? "bg-[color:var(--mt-teal-soft)]" : "hover:bg-muted/40",
                  isHidden && "opacity-45",
                )}
                style={isActive ? { borderColor: "var(--mt-teal)" } : undefined}
                data-testid={`${testId}-legend-${trace.id}`}
              >
                {/* The key has to carry BOTH channels: past 8 traces the colour repeats, and a
                    round dot would show two datasets as the same blue. */}
                <svg className="h-2 w-4 shrink-0 overflow-visible" viewBox="0 0 16 2" aria-hidden>
                  <line
                    x1="0"
                    y1="1"
                    x2="16"
                    y2="1"
                    stroke={stackTraceColor(index)}
                    strokeWidth="2"
                    strokeDasharray={stackTraceDash(index) || undefined}
                  />
                </svg>
                <span className="max-w-[13rem] truncate font-mono text-[11px]">{trace.label}</span>
                {trace.sublabel ? (
                  <span className="hidden font-mono text-[10px] text-muted-foreground sm:inline">
                    {trace.sublabel}
                  </span>
                ) : null}
              </button>
              <button
                type="button"
                onClick={() => toggleHidden(trace.id)}
                aria-pressed={!isHidden}
                aria-label={`${trace.label} shown in the stack`}
                className="flex min-h-0 items-center rounded-r-md border border-l-0 px-1.5 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:text-foreground motion-reduce:transition-none"
                data-testid={`${testId}-toggle-${trace.id}`}
              >
                {isHidden ? "show" : "hide"}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
