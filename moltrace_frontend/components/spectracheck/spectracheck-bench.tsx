"use client"

/**
 * The Evidence Bench — spectrum, tables, and the dataset queue co-visible for the first time.
 *
 * A new VIEW over existing state, not a new copy of it: the rail reads the same
 * `useRawFidTabState()` queue the Raw FID section owns, and selecting a dataset writes the same
 * `batchActiveId` both surfaces highlight. The Bench renders each dataset from its own stored
 * result (`item.result`), so it cannot disagree with the queue about what a row contains — and it
 * deliberately does NOT touch the Raw FID section's single-result display state, which belongs to
 * that section.
 *
 * Layout is three resizable panes (Source rail · Canvas over Recipe rail · Inspector) with the
 * library's APG separator semantics (focusable, arrow-key resize) and F6/Shift+F6 pane cycling
 * added here. Pane sizes persist via `autoSaveId` — additive localStorage, never File handles.
 */

import { useCallback, useMemo, useRef } from "react"
import Link from "next/link"
import { FlaskConical, Layers, ListChecks, PanelsTopLeft } from "lucide-react"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { SpectrumViewer } from "@/components/science/SpectrumViewer"
import {
  EnrichedPickedPeaksPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"
import {
  MetadataKeyValueCard,
  ProcessingParametersCard,
} from "@/components/spectracheck/spectracheck-processing-parameters-card"
import { useRawFidTabState } from "@/components/spectracheck/spectracheck-tab-state-context"
import {
  extractPeaksFromPayload,
  extractSpectrumXY,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"
import {
  readRawFidBatchItemFacts,
  type RawFidBatchItem,
} from "@/src/lib/spectracheck/raw-fid-batch"
import { cn } from "@/lib/utils"

/** A queue row the Bench can actually show: finished, with a plottable trace. */
function benchReady(item: RawFidBatchItem): boolean {
  return item.status === "done" && item.result != null
}

export function SpectraCheckBench() {
  const { state, update } = useRawFidTabState()
  const rootRef = useRef<HTMLDivElement | null>(null)

  const readyItems = useMemo(() => state.batchItems.filter(benchReady), [state.batchItems])

  // The shared selection, falling back to the first finished dataset so the Bench is never
  // deliberately blank while results exist.
  const active =
    readyItems.find((item) => item.id === state.batchActiveId) ?? readyItems[0] ?? null

  const payload = active?.result ?? null
  const xy = useMemo(() => (payload ? extractSpectrumXY(payload) : null), [payload])
  const peaks = useMemo(() => (payload ? extractPeaksFromPayload(payload) : []), [payload])
  const facts = useMemo(
    () => (payload ? readRawFidBatchItemFacts(payload) : null),
    [payload],
  )
  const nucleus = facts?.nucleus === "13C" ? "13C" : facts?.nucleus === "1H" ? "1H" : undefined

  /**
   * F6 / Shift+F6 cycle keyboard focus across the panes — the pane-cycling half of the APG
   * window-splitter pattern the resize handles alone do not provide. The panes are ordinary
   * containers with tabIndex=-1: reachable by this cycle, invisible to the Tab order.
   */
  const cyclePanes = useCallback((event: React.KeyboardEvent) => {
    if (event.key !== "F6") return
    event.preventDefault()
    const panes = Array.from(
      rootRef.current?.querySelectorAll<HTMLElement>("[data-bench-pane]") ?? [],
    )
    if (panes.length === 0) return
    const current = panes.findIndex((pane) => pane.contains(document.activeElement))
    const step = event.shiftKey ? -1 : 1
    const next = panes[(current + step + panes.length) % panes.length]
    next.focus()
  }, [])

  if (readyItems.length === 0) {
    return (
      <div
        className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/20 p-8 text-center"
        data-testid="bench-empty"
      >
        <PanelsTopLeft className="h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">Nothing on the bench yet</p>
        <p className="max-w-md text-sm text-muted-foreground">
          Process raw FID datasets and each finished one appears here — spectrum, picked peaks, and
          evidence side by side.
        </p>
        {/* The ?section= deep-link contract: the workspace reacts to the param in place. */}
        <Link
          href="/spectracheck?section=tab-raw-fid"
          className="font-mono text-xs font-bold uppercase tracking-[0.14em] underline-offset-4 hover:underline"
          style={{ color: "var(--mt-teal-ink)" }}
        >
          Go to Raw FID upload
        </Link>
      </div>
    )
  }

  return (
    <div
      ref={rootRef}
      className="min-w-0"
      onKeyDown={cyclePanes}
      data-testid="spectracheck-bench"
    >
      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        F6 cycles panes · handles are keyboard-resizable
      </p>
      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="moltrace:bench-layout:v1"
        className="min-h-[560px] rounded-lg border bg-card"
      >
        {/* ── Source rail ─────────────────────────────────────────────── */}
        <ResizablePanel defaultSize={22} minSize={12} collapsible>
          <div
            className="flex h-full flex-col gap-1 overflow-y-auto p-2"
            data-bench-pane="sources"
            tabIndex={-1}
            aria-label="Datasets"
          >
            <p className="flex items-center gap-1.5 px-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              <ListChecks className="h-3 w-3" aria-hidden />
              Datasets · {readyItems.length}
            </p>
            {readyItems.map((item) => {
              const rowFacts = readRawFidBatchItemFacts(item.result)
              const selected = item.id === active?.id
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => update({ batchActiveId: item.id })}
                  className={cn(
                    "rounded-md border px-2 py-1.5 text-left transition-colors motion-reduce:transition-none",
                    selected
                      ? "border-[color:var(--mt-teal)] bg-[color:var(--mt-teal-soft)]"
                      : "border-transparent hover:border-border hover:bg-muted/40",
                  )}
                  data-testid={`bench-source-${item.id}`}
                >
                  <span className="block truncate font-mono text-xs font-medium">{item.label}</span>
                  <span className="block truncate font-mono text-[10px] text-muted-foreground">
                    {rowFacts.nucleus ?? "—"} · {rowFacts.peakCount ?? "—"} peaks
                  </span>
                </button>
              )
            })}
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle />

        {/* ── Canvas over the recipe rail ─────────────────────────────── */}
        <ResizablePanel defaultSize={53} minSize={30}>
          <ResizablePanelGroup direction="vertical" autoSaveId="moltrace:bench-canvas:v1">
            <ResizablePanel defaultSize={68} minSize={40}>
              <div
                className="flex h-full min-w-0 flex-col gap-2 overflow-y-auto p-3"
                data-bench-pane="canvas"
                tabIndex={-1}
                aria-label="Spectrum canvas"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Layers className="h-3.5 w-3.5" style={{ color: "var(--mt-teal)" }} aria-hidden />
                  <span className="truncate font-mono text-xs font-bold">{active?.label}</span>
                  {facts?.vendorDetected ? (
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {facts.vendorDetected}
                    </Badge>
                  ) : null}
                  {facts?.datasetRoot ? (
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {facts.datasetRoot}
                    </span>
                  ) : null}
                </div>
                {xy ? (
                  <SpectrumViewer
                    x={xy.x}
                    y={xy.y}
                    peaks={peaks}
                    nucleus={nucleus}
                    renderMode="webgl"
                    rawFidAromaticBaseSmoothing
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    This dataset finished without a display-ready spectrum.
                  </p>
                )}
              </div>
            </ResizablePanel>
            <ResizableHandle withHandle />
            {/* The recipe rail: what produced the numbers above — parameters and provenance,
                never editable here. Collapsible because it is reference, not workflow. */}
            <ResizablePanel defaultSize={32} minSize={12} collapsible>
              <div
                className="grid h-full gap-3 overflow-y-auto p-3 lg:grid-cols-2"
                data-bench-pane="recipe"
                tabIndex={-1}
                aria-label="Processing recipe"
              >
                <ProcessingParametersCard payload={payload} />
                <MetadataKeyValueCard
                  payload={payload}
                  title="Acquisition metadata"
                  field="acquisition_metadata"
                  testId="bench-acquisition-metadata"
                />
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle withHandle />

        {/* ── Inspector ───────────────────────────────────────────────── */}
        <ResizablePanel defaultSize={25} minSize={15} collapsible>
          <div
            className="h-full overflow-y-auto p-2"
            data-bench-pane="inspector"
            tabIndex={-1}
            aria-label="Inspector"
          >
            <Tabs defaultValue="peaks">
              <TabsList className="w-full">
                <TabsTrigger value="peaks" className="flex-1">
                  Peaks
                </TabsTrigger>
                <TabsTrigger value="evidence" className="flex-1">
                  <FlaskConical className="mr-1 h-3 w-3" aria-hidden />
                  Evidence
                </TabsTrigger>
              </TabsList>
              <TabsContent value="peaks" className="mt-2 min-w-0">
                <EnrichedPickedPeaksPanel payload={payload} />
              </TabsContent>
              <TabsContent value="evidence" className="mt-2 min-w-0">
                <SpectraCheckEvidencePanels payload={payload} />
              </TabsContent>
            </Tabs>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
