"use client"

import dynamic from "next/dynamic"
import React, { useCallback, useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { AlertTriangle, Download, Eye, EyeOff, Layers, RotateCcw } from "lucide-react"

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as React.ComponentType<
  Record<string, unknown>
>

export type Nmr2DPeak = {
  f2_ppm: number
  f1_ppm: number
  intensity?: number
  assignment?: string
  label?: string
  status?: string
}

export type Nmr2DViewerProps = {
  peaks: Nmr2DPeak[]
  experiment?: "COSY" | "HSQC" | "HMQC" | "HMBC" | string
  title?: string
  f2Label?: string
  f1Label?: string
  height?: number
  className?: string
}

function filterValidPeaks(peaks: Nmr2DPeak[]): Nmr2DPeak[] {
  return peaks.filter(
    (p) =>
      typeof p.f2_ppm === "number" &&
      typeof p.f1_ppm === "number" &&
      Number.isFinite(p.f2_ppm) &&
      Number.isFinite(p.f1_ppm)
  )
}

/** Heuristic: highlight peaks whose status suggests manual review (not a definitive chemistry judgement). */
function statusSuggestsReview(status?: string): boolean {
  if (status == null || String(status).trim() === "") return false
  const s = String(status).toLowerCase()
  return (
    s.includes("suspicious") ||
    s.includes("conflict") ||
    s.includes("flag") ||
    s.includes("warn") ||
    s.includes("question") ||
    s.includes("review") ||
    s.includes("uncertain")
  )
}

function markerSizes(peaks: Nmr2DPeak[]): number[] {
  const raw = peaks.map((p) => p.intensity)
  const finite = raw.filter((v): v is number => typeof v === "number" && Number.isFinite(v))
  if (finite.length === 0) {
    return peaks.map(() => 9)
  }
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const span = max - min || 1
  return peaks.map((p) => {
    const v = p.intensity
    if (typeof v !== "number" || !Number.isFinite(v)) return 9
    const t = (v - min) / span
    return 6 + t * 12
  })
}

export function Nmr2DViewer({
  peaks,
  experiment,
  title,
  f2Label = "F2 / 1H ppm",
  f1Label = "F1 ppm",
  height = 380,
  className,
}: Nmr2DViewerProps) {
  const [showLabels, setShowLabels] = useState(true)
  const [suspiciousOnly, setSuspiciousOnly] = useState(false)
  const [xRange, setXRange] = useState<[number, number] | null>(null)
  const [yRange, setYRange] = useState<[number, number] | null>(null)
  const graphDivRef = useRef<HTMLElement | null>(null)

  const valid = useMemo(() => filterValidPeaks(peaks), [peaks])

  const displayed = useMemo(() => {
    if (!suspiciousOnly) return valid
    return valid.filter((p) => statusSuggestsReview(p.status))
  }, [valid, suspiciousOnly])

  const empty = valid.length === 0

  const plotEmptyFilter =
    !empty && suspiciousOnly && displayed.length === 0 && valid.length > 0

  const plotData = useMemo(() => {
    if (displayed.length === 0) return []
    const f2 = displayed.map((p) => p.f2_ppm)
    const f1 = displayed.map((p) => p.f1_ppm)
    const sizes = markerSizes(displayed)
    const flagged = displayed.map((p) => statusSuggestsReview(p.status))
    const colors = flagged.map((f) => (f ? "#ea580c" : "#2563eb"))
    const symbols = flagged.map((f) => (f ? "x" : "circle"))
    const labels = displayed.map((p) => {
      const a = p.assignment?.trim()
      const l = p.label?.trim()
      if (a && l) return `${a} (${l})`
      return a ?? l ?? ""
    })
    return [
      {
        type: "scattergl",
        mode: showLabels ? ("markers+text" as const) : ("markers" as const),
        x: f2,
        y: f1,
        text: showLabels ? labels : undefined,
        textposition: "top center",
        name: "Peaks",
        marker: {
          size: sizes,
          color: colors,
          symbol: symbols,
          line: { width: 1, color: "#fff" },
        },
        textfont: { size: 10 },
        hovertemplate: `<b>${f2Label}</b>: %{x:.4f}<br><b>${f1Label}</b>: %{y:.4f}<extra></extra>`,
      },
    ]
  }, [displayed, showLabels, f2Label, f1Label])

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { l: 56, r: 18, t: title ? 52 : 36, b: 48 },
      title: title ? { text: title, font: { size: 14 } } : undefined,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: false,
      xaxis: {
        title: f2Label,
        autorange: "reversed" as const,
        range: xRange ? [xRange[0], xRange[1]] : undefined,
        zeroline: false,
      },
      yaxis: {
        title: f1Label,
        autorange: "reversed" as const,
        range: yRange ? [yRange[0], yRange[1]] : undefined,
        zeroline: false,
      },
      hovermode: "closest" as const,
      uirevision: "nmr2d",
    }),
    [title, f2Label, f1Label, xRange, yRange]
  )

  const onRelayout = useCallback((ev: Readonly<unknown>) => {
    const raw = ev as Record<string, unknown>
    const xr0 = raw["xaxis.range[0]"]
    const xr1 = raw["xaxis.range[1]"]
    const yr0 = raw["yaxis.range[0]"]
    const yr1 = raw["yaxis.range[1]"]
    if (typeof xr0 === "number" && typeof xr1 === "number") {
      setXRange([xr0, xr1])
    }
    if (typeof yr0 === "number" && typeof yr1 === "number") {
      setYRange([yr0, yr1])
    }
    if (raw["xaxis.autorange"] === true) {
      setXRange(null)
    }
    if (raw["yaxis.autorange"] === true) {
      setYRange(null)
    }
  }, [])

  const resetZoom = useCallback(() => {
    setXRange(null)
    setYRange(null)
  }, [])

  const onInitialized = useCallback((_fig: unknown, graphDiv: HTMLElement) => {
    graphDivRef.current = graphDiv
  }, [])

  const exportImage = useCallback(async () => {
    const el = graphDivRef.current
    if (!el) return
    const Plotly = (await import("plotly.js-dist-min")).default
    await Plotly.downloadImage(el, { format: "png", filename: "nmr2d_peaks", scale: 2 })
  }, [])

  if (empty) {
    return (
      <div
        className={cn(
          "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
        data-testid="nmr-2d-viewer-root"
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No 2D NMR peak data available yet.</p>
      </div>
    )
  }

  return (
    <div
      className={cn("flex min-w-0 max-w-full flex-col gap-3 overflow-x-hidden", className)}
      data-testid="nmr-2d-viewer-root"
      aria-label="2D NMR peak viewer"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          {experiment ? (
            <p className="text-xs text-muted-foreground">
              Experiment:{" "}
              <span className="font-mono font-medium text-foreground">{experiment}</span>
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Peak markers reflect reported positions for interpretation support; they do not confirm
            bonds or coupling pathways.
          </p>
        </div>
        <InfoTooltip content="2D NMR peak maps show correlation evidence such as COSY proton-proton links, HSQC/HMQC direct C-H links, and HMBC long-range C-H links." />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b pb-3">
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
            <p className="max-w-xs">Reset axes to the full peak extent.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={showLabels ? "secondary" : "outline"}
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={() => setShowLabels((v) => !v)}
              aria-label="Toggle labels"
            >
              {showLabels ? (
                <Eye className="mr-1 h-4 w-4 shrink-0" aria-hidden />
              ) : (
                <EyeOff className="mr-1 h-4 w-4 shrink-0" aria-hidden />
              )}
              Toggle labels
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">Show or hide assignment and label text on the plot.</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant={suspiciousOnly ? "secondary" : "outline"}
              size="sm"
              className="w-full min-w-0 sm:w-auto"
              onClick={() => setSuspiciousOnly((v) => !v)}
              aria-label="Toggle suspicious only"
            >
              <AlertTriangle className="mr-1 h-4 w-4 shrink-0" aria-hidden />
              Suspicious only
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="max-w-xs">
              Show only peaks whose status suggests further review (heuristic filter).
            </p>
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
      </div>

      <div
        className="min-h-[280px] w-full min-w-0 max-w-full overflow-hidden rounded-lg border bg-card"
        style={{ height }}
      >
        {plotEmptyFilter ? (
          <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-2 px-4 text-center text-sm text-muted-foreground">
            <p>No peaks matched the review-status filter.</p>
            <p className="text-xs">Turn off &quot;Suspicious only&quot; to see the full peak list on the plot.</p>
          </div>
        ) : (
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
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Peak table</p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>F2 (ppm)</TableHead>
              <TableHead>F1 (ppm)</TableHead>
              <TableHead>Intensity</TableHead>
              <TableHead>Assignment</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {valid.map((p, i) => (
              <TableRow
                key={i}
                className={cn(statusSuggestsReview(p.status) && "bg-amber-500/10")}
              >
                <TableCell className="font-mono text-xs">{p.f2_ppm.toFixed(4)}</TableCell>
                <TableCell className="font-mono text-xs">{p.f1_ppm.toFixed(4)}</TableCell>
                <TableCell className="text-xs">
                  {typeof p.intensity === "number" && Number.isFinite(p.intensity)
                    ? p.intensity.toPrecision(4)
                    : "—"}
                </TableCell>
                <TableCell className="max-w-[140px] truncate text-xs" title={p.assignment}>
                  {p.assignment ?? "—"}
                </TableCell>
                <TableCell className="max-w-[120px] truncate text-xs" title={p.label}>
                  {p.label ?? "—"}
                </TableCell>
                <TableCell className="max-w-[160px] truncate text-xs" title={p.status}>
                  {p.status ?? "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
