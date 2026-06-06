"use client"

import { useEffect, useRef } from "react"
import { createPortal } from "react-dom"
import { AlertTriangle, Hash, Minimize2, Sparkles } from "lucide-react"

import { SpectrumViewer, type SpectrumOverlays, type SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"
import {
  EnrichedPickedPeaksPanel,
  InferredNmrTextPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import type { SpectraCheckUnifiedEvidenceMeta } from "@/src/lib/spectracheck/evidence-enqueue"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

/**
 * Full-screen, in-app view of a PROCESSED 1H / 13C spectrum and its analysis
 * tables.
 *
 * It is a presentational overlay only: it receives the already-computed display
 * data (the very same `xy` / `peaks` / `overlays` / payload the inline Step-3
 * card uses) and re-renders the SAME `SpectrumViewer` + the SAME result-panel
 * components at full viewport width. It performs NO fetching and mutates NO
 * state — so opening / closing it cannot change the spectrum's shape, the
 * analysis results, or any data table. The inline view stays mounted and
 * untouched underneath; this just lets the user inspect everything on the whole
 * screen instead of inside the app-shell column.
 *
 * Rendered through a portal to `document.body` so the app-shell sidebar /
 * workspace width never constrains it.
 */
export type ProcessedSpectrumFullscreenViewProps = {
  open: boolean
  onClose: () => void
  nucleus: "1H" | "13C"
  xy: { x: number[]; y: number[] } | null
  peaks: SpectrumPeakAnnotation[]
  overlays: SpectrumOverlays | undefined
  displayPayload: unknown
  peakCount: number | null
  score: number | null
  warnings: string[]
  notes: string | null
  loading: boolean
  /** Result card title, e.g. "Analysis output" / "Preview output". */
  title: string
  payloadMode: "preview" | "analyze" | null
  sampleId?: string
  fileName?: string | null
  unifiedEvidenceMeta: SpectraCheckUnifiedEvidenceMeta
}

export function ProcessedSpectrumFullscreenView({
  open,
  onClose,
  nucleus,
  xy,
  peaks,
  overlays,
  displayPayload,
  peakCount,
  score,
  warnings,
  notes,
  loading,
  title,
  payloadMode,
  sampleId,
  fileName,
  unifiedEvidenceMeta,
}: ProcessedSpectrumFullscreenViewProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null)

  // While open: close on Escape, lock body scroll, move focus into the dialog,
  // and restore focus to the trigger on close. All effects are gated on `open`
  // and fully cleaned up so the underlying page is left exactly as it was.
  useEffect(() => {
    if (!open) return
    const previouslyFocused = (typeof document !== "undefined" ? document.activeElement : null) as
      | HTMLElement
      | null

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation()
        onClose()
      }
    }
    document.addEventListener("keydown", onKeyDown)

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    dialogRef.current?.focus()

    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus?.()
    }
  }, [open, onClose])

  if (!open || typeof document === "undefined") return null

  const scoreColor =
    score == null
      ? "var(--mt-teal)"
      : score >= 0.8
        ? "var(--mt-green)"
        : score >= 0.5
          ? "var(--mt-amber)"
          : "var(--mt-red)"

  return createPortal(
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Processed ${nucleus} spectrum — full screen`}
      tabIndex={-1}
      className="fixed inset-0 z-[80] flex flex-col bg-background outline-none"
      data-testid="processed-fullscreen-view"
    >
      {/* Header bar — title + context on the left, exit control on the right. */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-card px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
            style={{ color: "var(--mt-teal)" }}
          >
            Full screen · Processed {nucleus}
          </p>
          <h2 className="truncate text-base font-semibold tracking-tight sm:text-lg">
            {title}
            {fileName ? (
              <span className="ml-2 text-sm font-normal text-muted-foreground">· {fileName}</span>
            ) : null}
            {sampleId ? (
              <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">
                {sampleId}
              </span>
            ) : null}
          </h2>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onClose}
          aria-label="Close full screen spectrum view"
          className="shrink-0 gap-1.5"
        >
          <Minimize2 className="h-4 w-4" aria-hidden />
          Exit full screen
        </Button>
      </div>

      {/* Scrollable body — uses the full viewport width (centered, generous cap). */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-[1800px] space-y-5 p-4 sm:p-6">
          {loading ? (
            <div
              className="flex items-center gap-2 rounded-md border px-3 py-1.5 font-mono text-[11px]"
              style={{
                borderColor: "var(--mt-teal)",
                color: "var(--mt-teal)",
                backgroundColor: "var(--mt-teal-soft)",
              }}
              aria-live="polite"
            >
              <span
                className="inline-block h-2 w-2 animate-pulse rounded-full"
                style={{ backgroundColor: "var(--mt-teal)" }}
              />
              {payloadMode === "analyze" ? "Running evidence match…" : "Refreshing preview…"}
            </div>
          ) : null}

          {/* KPI strip */}
          {(peakCount != null || score != null || warnings.length > 0) && (
            <div className="grid gap-3 sm:grid-cols-3">
              {peakCount != null && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <Hash className="h-3 w-3" aria-hidden />
                      Peak count
                    </p>
                    <p
                      className="font-mono text-2xl font-bold leading-none tabular-nums"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {peakCount}
                    </p>
                  </CardContent>
                </Card>
              )}
              {score != null && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: `3px solid ${scoreColor}` }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <Sparkles className="h-3 w-3" aria-hidden />
                      Analysis score
                    </p>
                    <p
                      className="font-mono text-2xl font-bold leading-none tabular-nums"
                      style={{ color: scoreColor }}
                    >
                      {score.toFixed(2)}
                    </p>
                  </CardContent>
                </Card>
              )}
              {warnings.length > 0 && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-amber)" }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <AlertTriangle className="h-3 w-3" aria-hidden />
                      Warnings
                    </p>
                    <p
                      className="font-mono text-2xl font-bold leading-none tabular-nums"
                      style={{ color: "var(--mt-amber)" }}
                    >
                      {warnings.length}
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Spectrum — fills most of the viewport height. Same SpectrumViewer
              component and props as inline; only the height class differs. */}
          <div className="min-w-0">
            {xy ? (
              <SpectrumViewer
                x={xy.x}
                y={xy.y}
                peaks={peaks}
                overlays={overlays}
                nucleus={nucleus}
                heightClassName="h-[min(820px,62vh)]"
              />
            ) : loading ? (
              <div className="flex h-[62vh] min-w-0 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 p-6 text-center">
                <div
                  className="mb-3 h-2 w-2 animate-pulse rounded-full"
                  style={{ backgroundColor: "var(--mt-teal)" }}
                  aria-hidden
                />
                <p className="font-mono text-sm font-bold tracking-tight">
                  Preparing spectrum…
                </p>
              </div>
            ) : (
              <AlertCard
                variant="warning"
                title="Spectrum preview unavailable"
                description="No display-ready spectrum points are available yet. Run Preview or Analyze, then reopen the full-screen view."
              />
            )}
          </div>

          {/* Use Unified Evidence — same CTA as inline. */}
          {displayPayload != null ? (
            <div
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"
              style={{ borderTop: "3px solid var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
            >
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
                <div>
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Use in unified evidence
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Add this {payloadMode === "analyze" ? "analysis" : "preview"} to the unified evidence stream.
                  </p>
                </div>
              </div>
              <SpectraCheckUseUnifiedEvidenceButton response={displayPayload} meta={unifiedEvidenceMeta} />
            </div>
          ) : null}

          {/* Details + Inferred NMR + Picked peaks — same components as inline. */}
          {displayPayload != null ? (
            <div className="grid min-w-0 gap-4 lg:grid-cols-2">
              <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                <CardContent className="space-y-3 py-3 text-sm">
                  <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Details
                  </p>
                  {notes ? (
                    <div>
                      <p className="text-[11px] font-medium text-muted-foreground">Notes</p>
                      <p className="mt-1 leading-snug">{notes}</p>
                    </div>
                  ) : null}
                  {warnings.length > 0 ? (
                    <div>
                      <p className="text-[11px] font-medium" style={{ color: "var(--mt-amber)" }}>
                        Solvent / impurity warnings
                      </p>
                      <ul
                        className="mt-1 list-inside list-disc space-y-0.5 text-xs"
                        style={{ color: "var(--mt-amber)" }}
                      >
                        {warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {!notes && warnings.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      {peakCount != null || score != null
                        ? `No additional details for this ${payloadMode === "analyze" ? "analysis" : "preview"}.`
                        : "No structured summary keys detected — see developer JSON below."}
                    </p>
                  ) : null}
                </CardContent>
              </Card>

              <InferredNmrTextPanel payload={displayPayload} />
              <EnrichedPickedPeaksPanel payload={displayPayload} />
            </div>
          ) : null}

          {/* Evidence panels + developer JSON — identical components to inline. */}
          {displayPayload != null ? <SpectraCheckEvidencePanels payload={displayPayload} /> : null}
          {displayPayload != null ? <DeveloperJsonPanel data={displayPayload} /> : null}
        </div>
      </div>
    </div>,
    document.body,
  )
}
