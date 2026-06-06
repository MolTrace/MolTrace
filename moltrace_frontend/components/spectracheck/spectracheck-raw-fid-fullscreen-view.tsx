"use client"

import { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  Hash,
  Minimize2,
  Settings2,
  ShieldCheck,
  Sparkles,
  Waves,
} from "lucide-react"

import { SpectrumViewer, type SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"
import {
  EnrichedPickedPeaksPanel,
  InferredNmrTextPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"
import {
  MetadataKeyValueCard,
  ProcessingParametersCard,
} from "@/components/spectracheck/spectracheck-processing-parameters-card"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import {
  DetectionResultsPanel,
  GsdResultsPanel,
  type SpectrumGSDAnalyzeResult,
  type UnifiedDetectionResult,
} from "@/components/spectracheck/gsd-analysis-ui"
import { GsdMultipletPanel } from "@/components/spectracheck/gsd-multiplet-panel"
import type { SpectraCheckUnifiedEvidenceMeta } from "@/src/lib/spectracheck/evidence-enqueue"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

/**
 * Full-screen, in-app view of a RAW FID spectrum and its analysis tables.
 *
 * Like the Processed 1H/13C full-screen view, this is a presentational overlay
 * only: it receives the already-computed display data (the very same
 * `xy` / `viewerPeaks` / `displayPayload` / `gsdResult` the inline Step-3 card
 * uses) and re-renders the SAME `SpectrumViewer` + result-panel components at
 * full viewport width. It performs NO fetching of its own and mutates NO parent
 * state — so opening / closing it cannot change the spectrum's shape, the
 * analysis results, or any data table. The inline view stays mounted and
 * untouched underneath.
 *
 * Scope note — only surfaces that are safe to render a SECOND time are mirrored:
 *   - Purely presentational panels (Identity, acquisition metadata, inferred
 *     NMR text, enriched picked peaks, evidence, processing parameters, legacy
 *     detection summary, developer JSON).
 *   - `GsdResultsPanel` (telemetry summary is module-level cached + in-flight
 *     deduped) and `GsdMultipletPanel` (multiplet POST is WeakMap-cached per
 *     `gsdResult` identity) — a second mount reuses the cache, never re-POSTs.
 * The independently-fetching, interactive candidate tools (J-coupling,
 * integration, shift prediction, spectral retrieval) and the run/upload
 * controls deliberately stay inline-only so the overlay never triggers a
 * duplicate request or a diverging second copy of an interactive surface.
 *
 * Rendered through a portal to `document.body` so the app-shell sidebar /
 * workspace width never constrains it.
 */
export type RawFidSpectrumFullscreenViewProps = {
  open: boolean
  onClose: () => void
  /** Resolved nucleus used by the SpectrumViewer + header label. */
  nucleus: "1H" | "13C"
  xy: { x: number[]; y: number[] } | null
  viewerPeaks: SpectrumPeakAnnotation[]
  displayPayload: unknown
  gsdResult: SpectrumGSDAnalyzeResult | null
  legacyDetectionResult: UnifiedDetectionResult | null
  loading: boolean
  payloadMode: "preview" | "process" | null
  /** Result card title, e.g. "Processed FID output" / "Raw archive metadata". */
  title: string
  fileName?: string | null
  sampleId?: string
  vendorDetected?: string | null
  nucleusMeta?: string | null
  sw?: unknown
  td?: unknown
  sha?: string | null
  warnings: string[]
  unifiedEvidenceMeta: SpectraCheckUnifiedEvidenceMeta
}

export function RawFidSpectrumFullscreenView({
  open,
  onClose,
  nucleus,
  xy,
  viewerPeaks,
  displayPayload,
  gsdResult,
  legacyDetectionResult,
  loading,
  payloadMode,
  title,
  fileName,
  sampleId,
  vendorDetected,
  nucleusMeta,
  sw,
  td,
  sha,
  warnings,
  unifiedEvidenceMeta,
}: RawFidSpectrumFullscreenViewProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const [processingParamsOpen, setProcessingParamsOpen] = useState(false)

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

  return createPortal(
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Raw FID ${nucleus} spectrum — full screen`}
      tabIndex={-1}
      className="fixed inset-0 z-[80] flex flex-col bg-background outline-none"
      data-testid="raw-fid-fullscreen-view"
    >
      {/* Header bar — title + context on the left, exit control on the right. */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-card px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
            style={{ color: "var(--mt-teal)" }}
          >
            Full screen · Raw FID {nucleus}
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
              {payloadMode === "process" ? "Processing FID…" : "Refreshing preview…"}
            </div>
          ) : null}

          {/* KPI strip */}
          {(vendorDetected || nucleusMeta || sw != null || td != null || warnings.length > 0) && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {vendorDetected && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <ShieldCheck className="h-3 w-3" aria-hidden />
                      Vendor
                    </p>
                    <p
                      className="font-mono text-base font-bold uppercase leading-tight tracking-wide"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {vendorDetected}
                    </p>
                  </CardContent>
                </Card>
              )}
              {nucleusMeta && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <Waves className="h-3 w-3" aria-hidden />
                      Nucleus
                    </p>
                    <p className="font-mono text-base font-bold leading-tight" style={{ color: "var(--mt-teal)" }}>
                      {nucleusMeta}
                    </p>
                  </CardContent>
                </Card>
              )}
              {sw != null && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <Activity className="h-3 w-3" aria-hidden />
                      Spectral width
                    </p>
                    <p
                      className="font-mono text-base font-bold leading-tight tabular-nums"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {String(sw)}
                    </p>
                  </CardContent>
                </Card>
              )}
              {td != null && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                  <CardContent className="space-y-1 py-3">
                    <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      <Hash className="h-3 w-3" aria-hidden />
                      TD points
                    </p>
                    <p
                      className="font-mono text-base font-bold leading-tight tabular-nums"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {String(td)}
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
                      className="font-mono text-base font-bold leading-tight tabular-nums"
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
              component and (raw-FID-specific) props as inline; only the height
              class differs. */}
          <div className="min-w-0">
            {xy ? (
              <SpectrumViewer
                x={xy.x}
                y={xy.y}
                peaks={viewerPeaks}
                nucleus={nucleus}
                renderMode="webgl"
                rawFidAromaticBaseSmoothing
                maxObservedPoints={12_000}
                observedPointsPerPixel={24}
                heightClassName="h-[min(820px,62vh)]"
              />
            ) : loading ? (
              <div className="flex h-[62vh] min-w-0 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 p-6 text-center">
                <div
                  className="mb-3 h-2 w-2 animate-pulse rounded-full"
                  style={{ backgroundColor: "var(--mt-teal)" }}
                  aria-hidden
                />
                <p className="font-mono text-sm font-bold tracking-tight">Preparing spectrum…</p>
              </div>
            ) : (
              <AlertCard
                variant="warning"
                title="Spectrum preview unavailable"
                description="No display-ready spectrum points are available yet. Run Preview or Process FID, then reopen the full-screen view."
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
                    Add this {payloadMode === "process" ? "processed FID" : "metadata preview"} to the unified evidence stream.
                  </p>
                </div>
              </div>
              <SpectraCheckUseUnifiedEvidenceButton response={displayPayload} meta={unifiedEvidenceMeta} />
            </div>
          ) : null}

          {/* Identity + acquisition metadata — same presentational cards as inline. */}
          {displayPayload != null ? (
            <div className="grid min-w-0 gap-4 lg:grid-cols-2">
              {(sha || vendorDetected || nucleusMeta) && (
                <Card className="overflow-hidden rounded-xl py-0" style={{ borderTop: "3px solid var(--mt-teal)" }}>
                  <CardContent className="space-y-3 py-3">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      Identity
                    </p>
                    {sha && (
                      <div>
                        <p className="text-[11px] font-medium text-muted-foreground">Raw file SHA-256</p>
                        <p className="mt-1 break-all font-mono text-[10px]">{sha}</p>
                      </div>
                    )}
                    {(vendorDetected || nucleusMeta) && (
                      <div className="flex flex-wrap gap-1.5">
                        {vendorDetected && (
                          <Badge
                            variant="outline"
                            className="font-mono text-[10px]"
                            style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
                          >
                            Vendor · {vendorDetected}
                          </Badge>
                        )}
                        {nucleusMeta && (
                          <Badge
                            variant="outline"
                            className="font-mono text-[10px]"
                            style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
                          >
                            Nucleus · {nucleusMeta}
                          </Badge>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              <MetadataKeyValueCard
                payload={displayPayload}
                title="Acquisition metadata"
                field="acquisition_metadata"
                testId="raw-fid-fs-acquisition-metadata-card"
              />
            </div>
          ) : null}

          {/* Inferred NMR text + enriched picked peaks + evidence — process-mode
              only, exactly as inline (these light up on /nmr/raw-fid/process). */}
          {payloadMode === "process" && displayPayload != null ? (
            <>
              <InferredNmrTextPanel payload={displayPayload} />
              <EnrichedPickedPeaksPanel payload={displayPayload} />
              <SpectraCheckEvidencePanels payload={displayPayload} />
            </>
          ) : null}

          {/* GSD results + multiplet table — gated on a present gsdResult so the
              telemetry / multiplet hooks never mount (and never fetch) when there
              is no experimental result to show. Both reuse module-level caches,
              so this second mount cannot trigger a duplicate request. */}
          {gsdResult ? (
            <GsdResultsPanel result={gsdResult} testId="raw-fid-fs-gsd-results-surface" />
          ) : null}
          {gsdResult ? (
            <GsdMultipletPanel gsdResult={gsdResult} testId="raw-fid-fs-multiplet-results-surface" />
          ) : null}

          {/* Legacy detection summary — presentational; self-gates on null. */}
          <DetectionResultsPanel result={legacyDetectionResult} testId="raw-fid-fs-legacy-results-surface" />

          {/* Processing parameters — collapsible (default closed), same as inline. */}
          {displayPayload != null ? (
            <Collapsible open={processingParamsOpen} onOpenChange={setProcessingParamsOpen}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-left transition-colors hover:bg-muted/30"
                >
                  <span className="flex items-center gap-2">
                    <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                    <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                      Processing parameters
                    </span>
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 text-muted-foreground transition-transform",
                      processingParamsOpen && "rotate-180",
                    )}
                    aria-hidden
                  />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="pt-3">
                <ProcessingParametersCard payload={displayPayload} />
              </CollapsibleContent>
            </Collapsible>
          ) : null}

          {/* Developer JSON — identical component to inline. */}
          {displayPayload != null ? <DeveloperJsonPanel data={displayPayload} /> : null}
        </div>
      </div>
    </div>,
    document.body,
  )
}
