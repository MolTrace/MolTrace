"use client"

/**
 * The dataset queue for the Raw FID tab — drop a folder of experiments (or a handful of
 * archives) and work the whole set, the way an instrument-room chemist does in MestReNova.
 *
 * Presentational on purpose: the runner that actually calls the analyzer lives in the section, so
 * this file can be reasoned about and tested as "given these items, what does the reviewer see".
 *
 * Selecting a row is the spine of the tab. It hands that dataset to the single-spectrum controls
 * and to every existing evidence panel below, so a queue adds a way IN to the analysis surface
 * rather than a second copy of it.
 */

import { useMemo } from "react"
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Clock,
  Layers,
  ListChecks,
  Play,
  RotateCcw,
  Square,
  Trash2,
  X,
} from "lucide-react"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import {
  SpectrumStackViewer,
  stackTraceColor,
  stackTraceDash,
  type SpectrumStackTrace,
} from "@/components/science/SpectrumStackViewer"
import { extractSpectrumXY } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import {
  estimateRemainingMs,
  formatBatchBytes,
  formatBatchDuration,
  isRawFidBatchItemRunnable,
  readRawFidBatchItemFacts,
  summarizeRawFidBatch,
  type RawFidBatchItem,
  type RawFidBatchMode,
  type RawFidBatchStatus,
} from "@/src/lib/spectracheck/raw-fid-batch"
import { cn } from "@/lib/utils"

type Props = {
  items: RawFidBatchItem[]
  mode: RawFidBatchMode
  onModeChange: (mode: RawFidBatchMode) => void
  running: boolean
  /** Progress text while archives are being packaged in the browser. */
  packaging?: string | null
  /** A refusal that ended the whole run rather than one dataset. */
  notice?: string | null
  activeItemId: string | null
  onSelectItem: (id: string) => void
  onRunAll: () => void
  onStop: () => void
  onRunItem: (id: string) => void
  onRemoveItem: (id: string) => void
  onClearAll: () => void
}

const STATUS_PRESENTATION: Record<
  RawFidBatchStatus,
  { label: string; className: string; icon: typeof Clock }
> = {
  queued: { label: "Queued", className: "border-border text-muted-foreground", icon: Clock },
  running: {
    label: "Running",
    className: "border-[color:var(--mt-teal)] text-[color:var(--mt-teal-ink)] bg-[color:var(--mt-teal-soft)]",
    icon: Play,
  },
  done: {
    label: "Done",
    className: "border-[color:var(--mt-green)] text-[color:var(--mt-green-ink)] bg-[color:var(--mt-green-soft)]",
    icon: CheckCircle2,
  },
  failed: { label: "Failed", className: "border-red-500/50 text-red-700 dark:text-red-300", icon: AlertTriangle },
  cancelled: { label: "Stopped", className: "border-border text-muted-foreground", icon: Square },
  blocked: {
    label: "Not accepted",
    className: "border-[color:var(--mt-amber)] text-[color:var(--mt-amber-ink)] bg-[color:var(--mt-amber-soft)]",
    icon: Ban,
  },
  unconfirmed: {
    label: "Unconfirmed",
    className: "border-[color:var(--mt-amber)] text-[color:var(--mt-amber-ink)] bg-[color:var(--mt-amber-soft)]",
    icon: AlertTriangle,
  },
}

function QueueStatusPill({ status }: { status: RawFidBatchStatus }) {
  const presentation = STATUS_PRESENTATION[status]
  const Icon = presentation.icon
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.1em]",
        presentation.className,
      )}
    >
      <Icon className={cn("h-3 w-3", status === "running" && "animate-pulse motion-reduce:animate-none")} aria-hidden />
      {presentation.label}
    </span>
  )
}

/**
 * Traces are derived from the stored analysis, cached against the response object itself.
 *
 * Without the cache every parent re-render would re-extract N spectra and hand the stack viewer
 * fresh arrays, which is exactly the redraw churn the single-spectrum view already works hard to
 * avoid. Keyed on the response object, so a re-run naturally produces a new entry.
 */
const traceCache = new WeakMap<object, { x: number[]; y: number[] } | null>()

function cachedTrace(result: unknown): { x: number[]; y: number[] } | null {
  if (typeof result !== "object" || result === null) return null
  const cached = traceCache.get(result)
  if (cached !== undefined) return cached
  const extracted = extractSpectrumXY(result)
  traceCache.set(result, extracted)
  return extracted
}

export function SpectraCheckRawFidBatch({
  items,
  mode,
  onModeChange,
  running,
  packaging = null,
  notice = null,
  activeItemId,
  onSelectItem,
  onRunAll,
  onStop,
  onRunItem,
  onRemoveItem,
  onClearAll,
}: Props) {
  const counts = useMemo(() => summarizeRawFidBatch(items), [items])
  const remainingMs = useMemo(() => estimateRemainingMs(items), [items])

  const traces = useMemo<SpectrumStackTrace[]>(() => {
    const out: SpectrumStackTrace[] = []
    for (const item of items) {
      if (item.status !== "done") continue
      const xy = cachedTrace(item.result)
      if (!xy || xy.x.length < 2) continue
      const facts = readRawFidBatchItemFacts(item.result)
      out.push({
        id: item.id,
        label: item.label,
        sublabel: facts.nucleus ?? undefined,
        x: xy.x,
        y: xy.y,
      })
    }
    return out
  }, [items])

  /**
   * Colour by position in the DRAWN stack, not by row number.
   *
   * The plot colours its traces by their index among the traces it actually draws, so colouring
   * the table by row index diverged the moment any row was not drawn — a still-queued dataset, a
   * failure, or a finished one whose response carried no usable trace. Colour is the only thing
   * linking a row to a line, so a divergence here does not look like a bug: it silently points
   * the reviewer at the wrong spectrum. One map, derived from the same array the plot receives.
   */
  const tracePenById = useMemo(() => {
    const map = new Map<string, { color: string; dash: string }>()
    traces.forEach((trace, position) =>
      map.set(trace.id, { color: stackTraceColor(position), dash: stackTraceDash(position) }),
    )
    return map
  }, [traces])

  /**
   * The nucleus the stacked AXIS can honestly claim — read back from what each dataset was
   * actually run with, not from the acquisition toggle.
   *
   * That toggle is freely changed to set up the next batch, so passing it through labelled a
   * stack of ¹H traces "¹³C" the moment the reviewer flipped it. And one folder can legitimately
   * hold both nuclei, in which case no single label is true; null makes the axis say "chemical
   * shift" rather than name a nucleus it cannot vouch for.
   */
  const stackNucleus = useMemo<"1H" | "13C" | null>(() => {
    const seen = new Set<string>()
    for (const item of items) {
      if (item.status !== "done") continue
      const reported = readRawFidBatchItemFacts(item.result).nucleus
      if (reported === "1H" || reported === "13C") seen.add(reported)
    }
    if (seen.size !== 1) return null
    return seen.has("13C") ? "13C" : "1H"
  }, [items])

  if (items.length === 0) return null

  const runnableLabel = mode === "process" ? "Process" : "Quick scan"

  /**
   * One sentence describing where the run is, for assistive tech.
   *
   * A batch is minutes of work whose entire progress lived in pill colours and a counter, none of
   * it in a live region — so a screen-reader user had to keep re-reading the table to learn
   * whether anything was still happening. WCAG 2.2 SC 4.1.3 covers exactly this. Deliberately
   * coarse: announcing every row transition on a 64-dataset run would be unusable, so it reports
   * the phase and the tallies that change slowly.
   */
  const runningItem = items.find((item) => item.status === "running")
  const runAnnouncement = running
    ? `Analyzing ${runningItem ? runningItem.label : "datasets"} — ${counts.done} of ${items.length} finished${
        counts.failed > 0 ? `, ${counts.failed} failed` : ""
      }.`
    : counts.done + counts.failed + counts.cancelled + counts.unconfirmed > 0
      ? `Run finished. ${counts.done} done${counts.failed > 0 ? `, ${counts.failed} failed` : ""}${
          counts.unconfirmed > 0 ? `, ${counts.unconfirmed} unconfirmed` : ""
        }${counts.cancelled > 0 ? `, ${counts.cancelled} stopped` : ""}.`
      : ""

  return (
    <ModuleCard
      accent="teal"
      eyebrow="Datasets"
      title={`Dataset queue · ${items.length}`}
      icon={ListChecks}
      description="Every experiment you dropped, run as its own dataset. Pick a row to bring it into the analysis below."
      className="min-w-0"
    >
      <div className="space-y-4" data-testid="raw-fid-queue">
        {/* Always mounted, so the region exists before it has anything to say — a live region
            inserted together with its text is unreliably announced. */}
        <p className="sr-only" role="status" aria-live="polite" data-testid="raw-fid-queue-announcer">
          {runAnnouncement}
        </p>
        {packaging ? (
          <div
            className="flex items-center gap-2 rounded-md border px-3 py-1.5 font-mono text-[11px]"
            style={{
              borderColor: "var(--mt-teal-ink)",
              color: "var(--mt-teal-ink)",
              backgroundColor: "var(--mt-teal-soft)",
            }}
            aria-live="polite"
            data-testid="raw-fid-queue-packaging"
          >
            <span
              className="inline-block h-2 w-2 animate-pulse rounded-full motion-reduce:animate-none"
              style={{ backgroundColor: "var(--mt-teal)" }}
            />
            {packaging}
          </div>
        ) : null}

        {notice ? <AlertCard variant="warning" title="Run stopped" description={notice} /> : null}

        {/* Run controls */}
        <div className="flex flex-wrap items-center gap-3 rounded-xl border p-3" style={{ borderTop: "3px solid var(--mt-teal)" }}>
          {/* A radiogroup, not two plain buttons. This control decides whether twenty datasets
              get the full recipe or a quick scan, and the selection used to be carried by
              background colour alone — invisible to a screen reader and to anyone who cannot
              separate the two shades. Mirrors the Detection engine toggle in gsd-analysis-ui. */}
          <div
            role="radiogroup"
            aria-label="Processing mode"
            className="inline-flex rounded-lg border border-input bg-background p-0.5"
          >
            {(
              [
                { value: "process", label: "Full processing" },
                { value: "scan", label: "Quick scan" },
              ] as const
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={mode === option.value}
                disabled={running}
                onClick={() => onModeChange(option.value)}
                className={cn(
                  "rounded-md px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.1em] transition-colors motion-reduce:transition-none",
                  mode === option.value ? "shadow-sm" : "text-muted-foreground hover:text-foreground",
                  running && "cursor-not-allowed opacity-60",
                )}
                style={mode === option.value ? { backgroundColor: "var(--mt-teal)", color: "#04080F" } : undefined}
                data-testid={`raw-fid-queue-mode-${option.value}`}
              >
                {option.label}
              </button>
            ))}
          </div>

          {running ? (
            <Button type="button" variant="outline" size="sm" onClick={onStop} data-testid="raw-fid-queue-stop">
              <Square className="mr-1 h-3.5 w-3.5" aria-hidden />
              Stop
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              onClick={onRunAll}
              disabled={counts.runnable === 0}
              data-testid="raw-fid-queue-run-all"
            >
              <Play className="mr-1 h-3.5 w-3.5" aria-hidden />
              {runnableLabel} {counts.runnable} dataset{counts.runnable === 1 ? "" : "s"}
            </Button>
          )}

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            <span className="tabular-nums">{counts.done} done</span>
            {counts.failed > 0 ? <span className="tabular-nums text-red-700 dark:text-red-300">{counts.failed} failed</span> : null}
            {counts.blocked > 0 ? (
              <span className="tabular-nums" style={{ color: "var(--mt-amber-ink)" }}>
                {counts.blocked} not accepted
              </span>
            ) : null}
            {running && remainingMs != null ? (
              <span className="tabular-nums">~{formatBatchDuration(remainingMs)} left</span>
            ) : null}
          </div>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto h-7 px-2 font-mono text-[11px] text-muted-foreground"
            onClick={onClearAll}
            disabled={running}
            data-testid="raw-fid-queue-clear"
          >
            <Trash2 className="mr-1 h-3.5 w-3.5" aria-hidden />
            Clear queue
          </Button>
        </div>

        {/* Mode-dependent on purpose: the "full recipe" half of this sentence is only true of
            Process. Saying it while Quick scan is selected would promise phasing and baseline
            correction the run is not doing. */}
        <p className="text-[11px] text-muted-foreground">
          Datasets run one at a time. Running several at once would not make them finish sooner.{" "}
          {mode === "process"
            ? "Each one gets the full processing recipe."
            : "Quick scan reads each archive and produces a fast spectrum — run Process for the full recipe."}
        </p>

        {/* Queue table */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[46rem] border-collapse text-left" data-testid="raw-fid-queue-table">
            <thead>
              <tr className="border-b">
                {["Dataset", "Status", "Analysis", "Vendor", "Points", "Peaks", "Time", ""].map((heading, index) => (
                  <th
                    key={heading || `actions-${index}`}
                    scope="col"
                    className="py-1.5 pr-3 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const facts = readRawFidBatchItemFacts(item.result)
                const isActive = activeItemId === item.id
                return (
                  <tr
                    key={item.id}
                    data-state={isActive ? "selected" : undefined}
                    data-testid={`raw-fid-queue-row-${item.id}`}
                    className={cn(
                      "border-b border-border/60 align-middle transition-colors motion-reduce:transition-none",
                      isActive ? "bg-[color:var(--mt-teal-soft)]" : "hover:bg-muted/30",
                    )}
                  >
                    <td className="py-1.5 pr-3">
                      <button
                        type="button"
                        onClick={() => onSelectItem(item.id)}
                        disabled={item.status !== "done"}
                        aria-pressed={isActive}
                        className={cn(
                          "flex min-h-0 w-full items-center gap-2 rounded px-1 py-1 text-left",
                          item.status === "done" ? "hover:underline" : "cursor-default",
                        )}
                        data-testid={`raw-fid-queue-select-${item.id}`}
                      >
                        {/* Draws the LINE, dash and all — not a dot. Colour alone repeats every
                            8 traces, so a dot made rows 1 and 9 identical here even after the plot
                            and legend learned to tell them apart. Slate bar whenever this dataset
                            has no line at all, including a finished one that returned no trace. */}
                        <svg className="h-2 w-4 shrink-0 overflow-visible" viewBox="0 0 16 2" aria-hidden>
                          <line
                            x1="0"
                            y1="1"
                            x2="16"
                            y2="1"
                            stroke={tracePenById.get(item.id)?.color ?? "var(--mt-slate)"}
                            strokeWidth="2"
                            strokeDasharray={tracePenById.get(item.id)?.dash || undefined}
                          />
                        </svg>
                        <span className="min-w-0">
                          <span className="block truncate font-mono text-xs font-medium">{item.label}</span>
                          <span className="block truncate font-mono text-[10px] text-muted-foreground">
                            {item.uncompressedBytes != null
                              ? `${formatBatchBytes(item.uncompressedBytes)}${item.fileCount != null ? ` · ${item.fileCount} files` : ""}`
                              : formatBatchBytes(item.file.size)}
                            {facts.datasetRoot ? ` · ${facts.datasetRoot}` : ""}
                          </span>
                        </span>
                      </button>
                    </td>
                    <td className="py-1.5 pr-3">
                      <QueueStatusPill status={item.status} />
                    </td>
                    {/* Which analysis actually produced this row. The mode toggle applies to the
                        NEXT run, so a queue can legitimately hold quick-scan and fully processed
                        rows side by side — and the Peaks column invites comparing them directly.
                        Naming each row's analysis is what makes that comparison honest. */}
                    <td className="py-1.5 pr-3 font-mono text-[11px] text-muted-foreground">
                      {item.mode === "process" ? "Full" : item.mode === "scan" ? "Quick scan" : "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-[11px] uppercase text-muted-foreground">
                      {facts.vendorDetected ?? "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-[11px] tabular-nums text-muted-foreground">
                      {facts.pointCount?.toLocaleString() ?? "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-[11px] tabular-nums text-muted-foreground">
                      {facts.peakCount?.toLocaleString() ?? "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-[11px] tabular-nums text-muted-foreground">
                      {formatBatchDuration(item.durationMs)}
                    </td>
                    <td className="py-1.5">
                      <div className="flex items-center justify-end gap-1">
                        {isRawFidBatchItemRunnable(item) && !running ? (
                          <button
                            type="button"
                            onClick={() => onRunItem(item.id)}
                            // The visible word has to appear IN the accessible name (WCAG 2.5.3):
                            // naming this "Process a.zip" while it reads "Retry" left speech-input
                            // users with no control on the page matching what they can see.
                            aria-label={`${item.status === "queued" ? "Run" : "Retry"} ${item.label} — ${runnableLabel}`}
                            className="flex min-h-0 items-center gap-1 rounded border px-1.5 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:text-foreground motion-reduce:transition-none"
                            data-testid={`raw-fid-queue-run-${item.id}`}
                          >
                            {item.status === "queued" ? (
                              <Play className="h-3 w-3" aria-hidden />
                            ) : (
                              <RotateCcw className="h-3 w-3" aria-hidden />
                            )}
                            {item.status === "queued" ? "Run" : "Retry"}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => onRemoveItem(item.id)}
                          disabled={item.status === "running"}
                          aria-label={`Remove ${item.label} from the queue`}
                          className="flex min-h-0 items-center rounded border px-1.5 py-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 motion-reduce:transition-none"
                          data-testid={`raw-fid-queue-remove-${item.id}`}
                        >
                          <X className="h-3 w-3" aria-hidden />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Per-dataset messages, kept out of the table so a long one cannot wreck the row rhythm. */}
        {items.some((item) => item.error) ? (
          <ul className="space-y-1" data-testid="raw-fid-queue-errors">
            {items
              .filter((item) => item.error)
              .map((item) => (
                <li key={item.id} className="flex gap-2 text-[11px]">
                  <span className="shrink-0 font-mono font-medium">{item.label}</span>
                  <span className="text-muted-foreground">{item.error}</span>
                </li>
              ))}
          </ul>
        ) : null}

        {/* Comparison — the reason a queue beats running datasets one by one. */}
        {traces.length >= 2 ? (
          <div className="space-y-2 rounded-xl border p-3" style={{ borderTop: "3px solid var(--mt-teal)" }} data-testid="raw-fid-queue-stack">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p
                className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                <Layers className="h-3 w-3" aria-hidden />
                Stacked comparison · {traces.length} spectra
              </p>
              <p className="text-[11px] text-muted-foreground">
                Each spectrum is scaled to its own tallest peak unless you put them on one scale.
              </p>
            </div>
            <SpectrumStackViewer
              traces={traces}
              nucleus={stackNucleus}
              activeTraceId={activeItemId}
              onSelectTrace={onSelectItem}
              testId="raw-fid-queue-stack-viewer"
            />
          </div>
        ) : null}
      </div>
    </ModuleCard>
  )
}
