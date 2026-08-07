"use client"

import Link from "next/link"
import { ArrowRight, ArrowUpRight, type LucideIcon } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { knowledgeLabel } from "@/components/knowledge/knowledge-constants"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  BarChart3,
  BookMarked,
  BookText,
  ClipboardCheck,
  Cpu,
  Database,
  FileStack,
  Layers,
  Library,
  Loader2,
  Sparkles,
  Wrench,
} from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

const PENDING_TASK_STATUSES = new Set(["open", "in_review", "needs_changes", "deferred"])
const APPROVED_TASK_STATUS = "accepted"

/**
 * The eleven destinations, grouped by what they are and rendered as cards.
 *
 * The order inside the first three groups is the order the work actually happens
 * in: sources are ingested, extractions come off them, a human reviews those,
 * and the reviewed output becomes records and then dataset candidates. A flat
 * row of buttons threw that away and made "Method registry" look like a peer of
 * "Sources workspace".
 *
 * Each group carries one brand accent, which fills the card's left rule and
 * its icon — so the grid is scannable by colour before it is read.
 *
 * `leavesModule` is not decoration. Those three hrefs go to other modules
 * entirely, and a link that silently relocates you is worse than one that warns
 * you first — especially on a page whose own banner says extracted knowledge is
 * mid-review. They get the outward arrow; in-module cards get a forward one, so
 * the two are distinguishable at a glance rather than by reading the group label.
 */
const KNOWLEDGE_DESTINATIONS: ReadonlyArray<{
  label: string
  accent: string
  ink: string
  leavesModule?: boolean
  items: ReadonlyArray<{ label: string; href: string; desc: string; icon: LucideIcon }>
}> = [
  {
    label: "Ingest and review",
    accent: "var(--mt-teal)",
    ink: "var(--mt-teal-ink)",
    items: [
      { label: "Sources workspace", href: "/knowledge/sources", desc: "Ingested documents and where each one came from.", icon: FileStack },
      { label: "Extractions workspace", href: "/knowledge/extractions", desc: "Extraction runs over those sources, and what each produced.", icon: Layers },
      { label: "Review tasks", href: "/knowledge/review", desc: "Waiting on a human before anything downstream may use it.", icon: ClipboardCheck },
    ],
  },
  {
    label: "Reviewed records",
    accent: "var(--mt-cyan)",
    ink: "var(--mt-cyan-ink)",
    items: [
      { label: "Reaction records", href: "/knowledge/reactions", desc: "Reaction knowledge that has cleared review.", icon: BookText },
      { label: "Analytical records", href: "/knowledge/analytical", desc: "Analytical knowledge that has cleared review.", icon: BarChart3 },
      { label: "Regulatory records", href: "/knowledge/regulatory", desc: "Regulatory knowledge that has cleared review.", icon: BookMarked },
    ],
  },
  {
    label: "What those records feed",
    accent: "var(--mt-violet)",
    ink: "var(--mt-violet-ink)",
    items: [
      { label: "Dataset candidates", href: "/knowledge/datasets", desc: "Training and benchmark splits proposed from reviewed records.", icon: Database },
      { label: "Model improvement", href: "/knowledge/model-improvement", desc: "The queue a model draws from when it is retrained.", icon: Sparkles },
    ],
  },
  {
    label: "Related work",
    accent: "var(--mt-amber)",
    ink: "var(--mt-amber-ink)",
    leavesModule: true,
    items: [
      { label: "ML Model Factory", href: "/ml", desc: "Model training and evaluation.", icon: Cpu },
      { label: "Validation runs", href: "/validation", desc: "Validation execution records.", icon: Library },
      { label: "Method registry", href: "/settings/methods", desc: "Registered analytical methods.", icon: Wrench },
    ],
  },
]

export function KnowledgeLibraryLanding() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  const [sources, setSources] = useState<Record<string, unknown>[]>([])
  const [errSources, setErrSources] = useState("")

  const [runs, setRuns] = useState<Record<string, unknown>[]>([])
  const [errRuns, setErrRuns] = useState("")

  const [reviewTasks, setReviewTasks] = useState<Record<string, unknown>[]>([])
  const [errReview, setErrReview] = useState("")

  const [trainingCandidates, setTrainingCandidates] = useState<Record<string, unknown>[]>([])
  const [errTraining, setErrTraining] = useState("")

  const [benchmarkCandidates, setBenchmarkCandidates] = useState<Record<string, unknown>[]>([])
  const [errBenchmark, setErrBenchmark] = useState("")

  const [modelImprovement, setModelImprovement] = useState<Record<string, unknown>[]>([])
  const [errImprovement, setErrImprovement] = useState("")

  const [datasetVersions, setDatasetVersions] = useState<Record<string, unknown>[]>([])
  const [errDatasetVersions, setErrDatasetVersions] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErrSources("")
    setErrRuns("")
    setErrReview("")
    setErrTraining("")
    setErrBenchmark("")
    setErrImprovement("")
    setErrDatasetVersions("")

    const [s, r, t, tr, bc, mi, dv] = await Promise.all([
      apiFetch<unknown>("/knowledge/sources", { method: "GET" }).catch((e) => {
        setErrSources(formatApiError(e, "Could not load sources."))
        return []
      }),
      apiFetch<unknown>("/knowledge/extractions/runs", { method: "GET" }).catch((e) => {
        setErrRuns(formatApiError(e, "Could not load extraction runs."))
        return []
      }),
      apiFetch<unknown>("/knowledge/review-tasks", { method: "GET" }).catch((e) => {
        setErrReview(formatApiError(e, "Could not load review tasks."))
        return []
      }),
      apiFetch<unknown>("/knowledge/training-dataset-candidates", { method: "GET" }).catch((e) => {
        setErrTraining(formatApiError(e, "Could not load training dataset candidates."))
        return []
      }),
      apiFetch<unknown>("/knowledge/benchmark-dataset-candidates", { method: "GET" }).catch((e) => {
        setErrBenchmark(formatApiError(e, "Could not load benchmark dataset candidates."))
        return []
      }),
      apiFetch<unknown>("/knowledge/model-improvement-queue", { method: "GET" }).catch((e) => {
        setErrImprovement(formatApiError(e, "Could not load model improvement queue."))
        return []
      }),
      apiFetch<unknown>("/knowledge/dataset-versions", { method: "GET" }).catch((e) => {
        setErrDatasetVersions(formatApiError(e, "Could not load dataset versions."))
        return []
      }),
    ])

    setSources(asArray(s).filter(isRecord) as Record<string, unknown>[])
    setRuns(asArray(r).filter(isRecord) as Record<string, unknown>[])
    setReviewTasks(asArray(t).filter(isRecord) as Record<string, unknown>[])
    setTrainingCandidates(asArray(tr).filter(isRecord) as Record<string, unknown>[])
    setBenchmarkCandidates(asArray(bc).filter(isRecord) as Record<string, unknown>[])
    setModelImprovement(asArray(mi).filter(isRecord) as Record<string, unknown>[])
    setDatasetVersions(asArray(dv).filter(isRecord) as Record<string, unknown>[])
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const taskCounts = useMemo(() => {
    let pending = 0
    let accepted = 0
    for (const row of reviewTasks) {
      const st = (readRecordString(row, "status") ?? "").toLowerCase()
      if (st === APPROVED_TASK_STATUS) accepted++
      else if (st && PENDING_TASK_STATUSES.has(st)) pending++
      else if (st === "rejected") {
        /* neither pending nor approved bucket */
      } else if (st) {
        pending++
      }
    }
    return { pending, accepted }
  }, [reviewTasks])

  const approvedDatasetVersions = useMemo(
    () =>
      datasetVersions.filter((row) => (readRecordString(row, "status") ?? "").toLowerCase() === "approved").length,
    [datasetVersions],
  )

  function statValue(count: number | null, errored: boolean): string {
    if (loading) return "…"
    if (errored) return "—"
    if (count === null) return "—"
    return String(count)
  }

  function statSub(opts: { errored: boolean; empty: boolean; label: string }) {
    if (loading) return <p className="text-xs text-muted-foreground">Loading…</p>
    if (opts.errored) return <p className="text-xs text-muted-foreground">Unable to load.</p>
    if (opts.empty) return <p className="text-xs text-muted-foreground">No data yet.</p>
    return <p className="text-xs text-muted-foreground">{opts.label}</p>
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-amber)" }}
          >
            MolTrace · Knowledge Library
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Knowledge Library</h1>
          <p className="text-sm text-muted-foreground">
            Ingest, extract, review, and reuse scientific, analytical, reaction, regulatory, and internal knowledge.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <AlertCard
        variant="warning"
        title="Human review required"
        description="Extracted knowledge requires human review. Citations, provenance, and dataset splits must be preserved before records are used for models or regulatory decisions."
      />

      {/* The destinations, grouped.

          This was twelve identical outline buttons in one wrapping row, which hid
          three separate problems. Refresh is an ACTION and sat among eleven
          navigation links, so the one control that changes nothing about where
          you are looked exactly like the eleven that do. The eight in-module
          links have a real order — a pipeline, then the records it produces,
          then what those records feed — and a flat row showed none of it. And
          three of them leave Knowledge entirely for other modules while looking
          identical to the ones that stay.

          So: Refresh moves out to sit with the section heading, the in-module
          destinations are grouped by what they are, and anything that leaves the
          module says so with an outward arrow rather than looking local. */}
      <section aria-labelledby="knowledge-destinations" className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <h2
            id="knowledge-destinations"
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground"
          >
            Where to go next
          </h2>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={() => setReloadToken((x) => x + 1)}
          >
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Refresh
          </Button>
        </div>

        {KNOWLEDGE_DESTINATIONS.map((group) => (
          <div key={group.label} className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">
              {group.label}
              {group.leavesModule ? (
                // The leading space is not decorative: ml-1.5 separates these
                // visually but leaves the accessible name as "Related work—opens
                // another module", run together for anyone listening to it.
                <span className="ml-1.5 font-normal opacity-70">{" "}— opens another module</span>
              ) : null}
            </p>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative flex h-full min-w-0 flex-col rounded-xl border bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0"
                  /* The 3px left rule carries the group's colour without tinting
                     any text — same signature as the module cards on the home
                     page, so the two read as one system. */
                  style={{ borderLeftWidth: "3px", borderLeftColor: group.accent }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      {/* Icons keep the vivid accent — shapes, not type, so the AA
                          rule that pushes text to the ink tokens does not apply. */}
                      <item.icon className="h-5 w-5 shrink-0" style={{ color: group.accent }} aria-hidden />
                      <h3 className="min-w-0 text-sm font-semibold" style={{ color: group.ink }}>
                        {item.label}
                      </h3>
                    </div>
                    {group.leavesModule ? (
                      <ArrowUpRight
                        className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 motion-reduce:transition-none"
                        aria-hidden
                      />
                    ) : (
                      <ArrowRight
                        className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
                        aria-hidden
                      />
                    )}
                  </div>

                  {/* NO CATEGORY PILL HERE, deliberately. The reference this is
                      modelled on uses one because it has no group headings — the
                      pill is its only grouping signal. This layout does have
                      headings, and they carry what a pill cannot: the order the
                      work happens in, and the warning that a group leaves the
                      module. Repeating the heading on all three cards beneath it
                      would just be the same word three more times. The accent
                      rule and icon already tie each card to its group. */}
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </section>

      {(errSources ||
        errRuns ||
        errReview ||
        errTraining ||
        errBenchmark ||
        errImprovement ||
        errDatasetVersions) && (
        <AlertCard variant="error" title="Some sections could not load">
          <div className="space-y-1 text-xs text-foreground/90">
            {errSources ? <p>Sources: {errSources}</p> : null}
            {errRuns ? <p>Extraction runs: {errRuns}</p> : null}
            {errReview ? <p>Review tasks: {errReview}</p> : null}
            {errTraining ? <p>Training candidates: {errTraining}</p> : null}
            {errBenchmark ? <p>Benchmark candidates: {errBenchmark}</p> : null}
            {errImprovement ? <p>Model improvement queue: {errImprovement}</p> : null}
            {errDatasetVersions ? <p>Dataset versions: {errDatasetVersions}</p> : null}
          </div>
        </AlertCard>
      )}

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Summary cards</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Sources</CardTitle>
              <Library className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errSources ? null : sources.length, Boolean(errSources))}
              </div>
              {statSub({
                errored: Boolean(errSources),
                empty: !errSources && sources.length === 0,
                label: "Registered knowledge sources",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Extraction runs</CardTitle>
              <FileStack className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errRuns ? null : runs.length, Boolean(errRuns))}
              </div>
              {statSub({
                errored: Boolean(errRuns),
                empty: !errRuns && runs.length === 0,
                label: "Extraction runs recorded",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Records needing review</CardTitle>
              <ClipboardCheck className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errReview ? null : taskCounts.pending, Boolean(errReview))}
              </div>
              {statSub({
                errored: Boolean(errReview),
                empty: !errReview && reviewTasks.length === 0,
                label: "Open, in review, needs changes, or deferred",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Approved knowledge records</CardTitle>
              <BookMarked className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errReview ? null : taskCounts.accepted, Boolean(errReview))}
              </div>
              {statSub({
                errored: Boolean(errReview),
                empty: !errReview && taskCounts.accepted === 0,
                label: "Review tasks marked accepted",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Training dataset candidates</CardTitle>
              <Database className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errTraining ? null : trainingCandidates.length, Boolean(errTraining))}
              </div>
              {statSub({
                errored: Boolean(errTraining),
                empty: !errTraining && trainingCandidates.length === 0,
                label: "Nominated for model training",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Benchmark candidates</CardTitle>
              <Layers className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errBenchmark ? null : benchmarkCandidates.length, Boolean(errBenchmark))}
              </div>
              {statSub({
                errored: Boolean(errBenchmark),
                empty: !errBenchmark && benchmarkCandidates.length === 0,
                label: "Nominated for held-out benchmarking",
              })}
            </CardContent>
          </Card>

          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-teal)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Model improvement items</CardTitle>
              <Wrench className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="pb-5">
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>
                {statValue(errImprovement ? null : modelImprovement.length, Boolean(errImprovement))}
              </div>
              {statSub({
                errored: Boolean(errImprovement),
                empty: !errImprovement && modelImprovement.length === 0,
                label: "Items in the improvement queue",
              })}
            </CardContent>
          </Card>
        </div>
      </div>

      <ModuleCard
        accent="teal"
        eyebrow="ML Readiness"
        title="Data science / ML readiness"
        icon={Sparkles}
        description={
          <>
            Approved dataset snapshots ready for ML training — versions in snapshot:{" "}
            <span className="tabular-nums font-medium">{errDatasetVersions ? "—" : String(approvedDatasetVersions)}</span>
          </>
        }
      >
        <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 shrink-0" aria-hidden />
            Training: {trainingCandidates.length} · Benchmark: {benchmarkCandidates.length} · Improvement queue:{" "}
            {modelImprovement.length}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <BarChart3 className="h-4 w-4 shrink-0" aria-hidden />
            Dataset versions listed: {errDatasetVersions ? "—" : datasetVersions.length}
          </span>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Sources"
        title="Source library preview"
        icon={Library}
        description="Scientific literature and structured knowledge sources registered for extraction and review."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading…
            </p>
          ) : errSources ? (
            <p className="text-sm text-muted-foreground">{errSources}</p>
          ) : sources.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <BookText />
                </EmptyMedia>
                <EmptyTitle>No knowledge sources yet</EmptyTitle>
                <EmptyDescription>
                  Add a literature, patent, or document source.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Source type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.slice(0, 12).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `src-${id}` : `src-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="max-w-[240px] truncate text-sm">
                        {readRecordString(row, "title") ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs">{knowledgeLabel(readRecordString(row, "source_type"))}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Extractions"
        title="Recent extraction runs"
        icon={FileStack}
        description="Newest 15, across every registered source."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errRuns ? (
            <p className="text-sm text-muted-foreground">{errRuns}</p>
          ) : runs.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Cpu />
                </EmptyMedia>
                <EmptyTitle>No extraction runs yet</EmptyTitle>
                <EmptyDescription>
                  Runs appear once a source has been extracted.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Extraction type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Records extracted</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.slice(0, 15).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const ec = row["extracted_count"]
                  const ecNum = typeof ec === "number" && Number.isFinite(ec) ? ec : null
                  return (
                    <TableRow key={id != null ? `run-${id}` : `run-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="text-xs">{knowledgeLabel(readRecordString(row, "extraction_type"))}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{ecNum != null ? ecNum : "—"}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Review"
        title="Review queue preview"
        icon={ClipboardCheck}
        description="Extracted claims that still need an expert decision."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errReview ? (
            <p className="text-sm text-muted-foreground">{errReview}</p>
          ) : reviewTasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No review tasks yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Record type</TableHead>
                  <TableHead className="w-[88px]">Record ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reviewTasks.slice(0, 15).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const rid = readRecordNumber(row, "record_id")
                  return (
                    <TableRow key={id != null ? `rt-${id}` : `rt-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="text-xs">{knowledgeLabel(readRecordString(row, "record_type"))}</TableCell>
                      <TableCell className="font-mono text-xs">{rid ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="max-w-[220px] truncate text-sm">
                        {readRecordString(row, "title") ?? "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Training Data"
        title="Training dataset candidates"
        icon={Database}
        description="Reviewed claims nominated for model training."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errTraining ? (
            <p className="text-sm text-muted-foreground">{errTraining}</p>
          ) : trainingCandidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No training dataset candidates yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trainingCandidates.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `tr-${id}` : `tr-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Benchmark Data"
        title="Benchmark dataset candidates"
        icon={Layers}
        description="Held out from training, for evaluation only."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errBenchmark ? (
            <p className="text-sm text-muted-foreground">{errBenchmark}</p>
          ) : benchmarkCandidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No benchmark dataset candidates yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {benchmarkCandidates.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `bc-${id}` : `bc-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Improvement"
        title="Model improvement queue"
        icon={Wrench}
        description="Edge cases, failure modes, and feedback awaiting retraining."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errImprovement ? (
            <p className="text-sm text-muted-foreground">{errImprovement}</p>
          ) : modelImprovement.length === 0 ? (
            <p className="text-sm text-muted-foreground">No model improvement items yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {modelImprovement.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `mi-${id}` : `mi-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Versions"
        title="Dataset versions"
        icon={BookMarked}
        description="Each release pins its records for reproducibility."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errDatasetVersions ? (
            <p className="text-sm text-muted-foreground">{errDatasetVersions}</p>
          ) : datasetVersions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No dataset versions yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datasetVersions.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `dv-${id}` : `dv-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{knowledgeLabel(readRecordString(row, "status"))}</Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <p className="text-xs text-muted-foreground">
        Knowledge Library lists are operational signals from your organization’s own records — not legal conclusions or agency positions.
        See{" "}
        <Link className="font-medium text-primary underline-offset-4 hover:underline" href="/validation">
          Validation
        </Link>{" "}
        for model validation runs.
      </p>
    </div>
  )
}
