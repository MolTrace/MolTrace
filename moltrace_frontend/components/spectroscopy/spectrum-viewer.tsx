"use client"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ZoomIn, ZoomOut, RotateCcw, Maximize2, Layers } from "lucide-react"
import { useState } from "react"

export function SpectrumViewer() {
  const [showOverlay, setShowOverlay] = useState(true)

  // Simulated peak data
  const peaks = [
    { ppm: 1.2, intensity: 0.3, label: "CH3" },
    { ppm: 2.4, intensity: 0.5, label: "CH2" },
    { ppm: 3.8, intensity: 0.7, label: "OCH3" },
    { ppm: 6.9, intensity: 0.4, label: "Ar-H" },
    { ppm: 7.2, intensity: 0.6, label: "Ar-H" },
    { ppm: 7.8, intensity: 0.35, label: "NH" },
  ]

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">1H NMR Spectrum</span>
          <Badge variant="outline" className="text-xs">500 MHz</Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <RotateCcw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Maximize2 className="h-4 w-4" />
          </Button>
          <div className="mx-2 h-4 w-px bg-border" />
          <Button
            variant={showOverlay ? "secondary" : "ghost"}
            size="sm"
            className="gap-1 text-xs"
            onClick={() => setShowOverlay(!showOverlay)}
          >
            <Layers className="h-3.5 w-3.5" />
            Overlay
          </Button>
        </div>
      </div>

      {/* Spectrum Area */}
      <div className="relative flex-1 bg-muted/20 p-4">
        <svg className="h-full w-full" viewBox="0 0 800 300" preserveAspectRatio="none">
          {/* Grid lines */}
          {Array.from({ length: 9 }).map((_, i) => (
            <line
              key={`h-${i}`}
              x1={0}
              y1={i * 37.5}
              x2={800}
              y2={i * 37.5}
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          ))}
          {Array.from({ length: 11 }).map((_, i) => (
            <line
              key={`v-${i}`}
              x1={i * 80}
              y1={0}
              x2={i * 80}
              y2={300}
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          ))}

          {/* Baseline */}
          <line
            x1={0}
            y1={280}
            x2={800}
            y2={280}
            stroke="currentColor"
            strokeOpacity={0.3}
            strokeWidth={1}
          />

          {/* Observed spectrum (blue) */}
          <path
            d={`M 0 280 
              Q 40 280, 80 ${280 - peaks[0].intensity * 200}
              Q 120 280, 180 280
              Q 200 280, 220 ${280 - peaks[1].intensity * 200}
              Q 240 280, 320 280
              Q 340 280, 360 ${280 - peaks[2].intensity * 200}
              Q 380 280, 500 280
              Q 540 280, 560 ${280 - peaks[3].intensity * 200}
              Q 580 280, 600 ${280 - peaks[4].intensity * 200}
              Q 620 280, 700 280
              Q 720 280, 740 ${280 - peaks[5].intensity * 200}
              Q 760 280, 800 280`}
            fill="none"
            stroke="hsl(var(--accent))"
            strokeWidth={2}
          />

          {/* Predicted spectrum (dashed, slightly offset) */}
          {showOverlay && (
            <path
              d={`M 0 280 
                Q 40 280, 82 ${280 - peaks[0].intensity * 195}
                Q 122 280, 180 280
                Q 200 280, 222 ${280 - peaks[1].intensity * 205}
                Q 242 280, 320 280
                Q 340 280, 362 ${280 - peaks[2].intensity * 195}
                Q 382 280, 500 280
                Q 540 280, 558 ${280 - peaks[3].intensity * 200}
                Q 578 280, 602 ${280 - peaks[4].intensity * 195}
                Q 622 280, 700 280
                Q 720 280, 738 ${280 - peaks[5].intensity * 205}
                Q 758 280, 800 280`}
              fill="none"
              stroke="hsl(var(--muted-foreground))"
              strokeWidth={1.5}
              strokeDasharray="4 2"
              opacity={0.6}
            />
          )}

          {/* Peak labels */}
          {peaks.map((peak, i) => {
            const x = [80, 220, 360, 560, 600, 740][i]
            const y = 280 - peak.intensity * 200 - 20
            return (
              <g key={i}>
                <circle cx={x} cy={280 - peak.intensity * 200} r={4} fill="hsl(var(--accent))" />
                <text
                  x={x}
                  y={y}
                  textAnchor="middle"
                  className="fill-foreground text-[10px]"
                >
                  {peak.ppm.toFixed(1)}
                </text>
                <text
                  x={x}
                  y={y - 12}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[9px]"
                >
                  {peak.label}
                </text>
              </g>
            )
          })}
        </svg>

        {/* X-axis labels */}
        <div className="absolute bottom-2 left-4 right-4 flex justify-between text-xs text-muted-foreground">
          <span>10</span>
          <span>8</span>
          <span>6</span>
          <span>4</span>
          <span>2</span>
          <span>0 ppm</span>
        </div>

        {/* Legend */}
        <div className="absolute right-4 top-4 flex items-center gap-4 rounded border bg-background/80 px-3 py-1.5 text-xs backdrop-blur">
          <div className="flex items-center gap-1.5">
            <div className="h-0.5 w-4 bg-accent" />
            <span>Observed</span>
          </div>
          {showOverlay && (
            <div className="flex items-center gap-1.5">
              <div className="h-0.5 w-4 border-t-2 border-dashed border-muted-foreground" />
              <span>Predicted</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
