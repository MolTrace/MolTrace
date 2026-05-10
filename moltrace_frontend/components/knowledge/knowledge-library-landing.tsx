"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
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
  BarChart3,
  BookMarked,
  ClipboardCheck,
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

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

const PENDING_TASK_STATUSES = new Set(["open", "in_review", "needs_changes", "deferred"])
const APPROVED_TASK_STATUS = "accepted"

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
        setErrSources(formatErr(e, "Could not load sources."))
        return []
      }),
      apiFetch<unknown>("/knowledge/extractions/runs", { method: "GET" }).catch((e) => {
        setErrRuns(formatErr(e, "Could not load extraction runs."))
        return []
      }),
      apiFetch<unknown>("/knowledge/review-tasks", { method: "GET" }).catch((e) => {
        setErrReview(formatErr(e, "Could not load review tasks."))
        return []
      }),
      apiFetch<unknown>("/knowledge/training-dataset-candidates", { method: "GET" }).catch((e) => {
        setErrTraining(formatErr(e, "Could not load training dataset candidates."))
        return []
      }),
      apiFetch<unknown>("/knowledge/benchmark-dataset-candidates", { method: "GET" }).catch((e) => {
        setErrBenchmark(formatErr(e, "Could not load benchmark dataset candidates."))
        return []
      }),
      apiFetch<unknown>("/knowledge/model-improvement-queue", { method: "GET" }).catch((e) => {
        setErrImprovement(formatErr(e, "Could not load model improvement queue."))
        return []
      }),
      apiFetch<unknown>("/knowledge/dataset-versions", { method: "GET" }).catch((e) => {
        setErrDatasetVersions(formatErr(e, "Could not load dataset versions."))
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
    if (opts.errored) return <p className="text-xs text-muted-foreground">Unable to load from backend.</p>
    if (opts.empty) return <p className="text-xs text-muted-foreground">No data returned.</p>
    return <p className="text-xs text-muted-foreground">{opts.label}</p>
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
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

      <div className="flex flex-wrap items-center gap-2">
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
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/sources">Sources workspace</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/extractions">Extractions workspace</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/review">Review tasks</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/reactions">Reaction records</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/analytical">Analytical records</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/regulatory">Regulatory records</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/datasets">Dataset candidates</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/model-improvement">Model improvement</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ml">ML Model Factory</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/validation">Validation runs</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/settings/methods">Method registry</Link>
        </Button>
      </div>

      {(errSources ||
        errRuns ||
        errReview ||
        errTraining ||
        errBenchmark ||
        errImprovement ||
        errDatasetVersions) && (
        <AlertCard variant="error" title="Partial load">
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errSources ? null : sources.length, Boolean(errSources))}
              </div>
              {statSub({
                errored: Boolean(errSources),
                empty: !errSources && sources.length === 0,
                label: "GET /knowledge/sources",
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errRuns ? null : runs.length, Boolean(errRuns))}
              </div>
              {statSub({
                errored: Boolean(errRuns),
                empty: !errRuns && runs.length === 0,
                label: "GET /knowledge/extractions/runs",
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errReview ? null : taskCounts.pending, Boolean(errReview))}
              </div>
              {statSub({
                errored: Boolean(errReview),
                empty: !errReview && reviewTasks.length === 0,
                label: "Open / in_review / needs_changes / deferred from review tasks",
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errReview ? null : taskCounts.accepted, Boolean(errReview))}
              </div>
              {statSub({
                errored: Boolean(errReview),
                empty: !errReview && taskCounts.accepted === 0,
                label: "Review tasks with status accepted",
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errTraining ? null : trainingCandidates.length, Boolean(errTraining))}
              </div>
              {statSub({
                errored: Boolean(errTraining),
                empty: !errTraining && trainingCandidates.length === 0,
                label: "GET /knowledge/training-dataset-candidates",
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errBenchmark ? null : benchmarkCandidates.length, Boolean(errBenchmark))}
              </div>
              {statSub({
                errored: Boolean(errBenchmark),
                empty: !errBenchmark && benchmarkCandidates.length === 0,
                label: "GET /knowledge/benchmark-dataset-candidates",
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
              <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
                {statValue(errImprovement ? null : modelImprovement.length, Boolean(errImprovement))}
              </div>
              {statSub({
                errored: Boolean(errImprovement),
                empty: !errImprovement && modelImprovement.length === 0,
                label: "GET /knowledge/model-improvement-queue",
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
            <p className="text-sm text-muted-foreground">No sources returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>source_type</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>updated_at</TableHead>
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
                      <TableCell className="font-mono text-xs">{readRecordString(row, "source_type") ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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
        description="Recent knowledge extraction pipeline runs — source, status, extracted entity count, and run timestamp."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errRuns ? (
            <p className="text-sm text-muted-foreground">{errRuns}</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No extraction runs returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>extraction_type</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead className="text-right">extracted_count</TableHead>
                  <TableHead>updated_at</TableHead>
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
                      <TableCell className="font-mono text-xs">{readRecordString(row, "extraction_type") ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{readRecordString(row, "status") ?? "—"}</Badge>
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
        description="Extracted knowledge claims pending expert review — status, source, and entity type for each queued review task."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errReview ? (
            <p className="text-sm text-muted-foreground">{errReview}</p>
          ) : reviewTasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No review tasks returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>record_type</TableHead>
                  <TableHead className="w-[88px]">record_id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reviewTasks.slice(0, 15).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const rid = readRecordNumber(row, "record_id")
                  return (
                    <TableRow key={id != null ? `rt-${id}` : `rt-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordString(row, "record_type") ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{rid ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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
        description="Reviewed knowledge claims nominated as training data for ML models — type, source, and curation status."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errTraining ? (
            <p className="text-sm text-muted-foreground">{errTraining}</p>
          ) : trainingCandidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No training dataset candidates returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trainingCandidates.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `tr-${id}` : `tr-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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
        description="Knowledge claims nominated as held-out benchmark evaluation data — type, source, and curation status."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errBenchmark ? (
            <p className="text-sm text-muted-foreground">{errBenchmark}</p>
          ) : benchmarkCandidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No benchmark dataset candidates returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {benchmarkCandidates.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `bc-${id}` : `bc-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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
        description="Active model improvement signals — edge cases, failure modes, and feedback items queued for retraining consideration."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errImprovement ? (
            <p className="text-sm text-muted-foreground">{errImprovement}</p>
          ) : modelImprovement.length === 0 ? (
            <p className="text-sm text-muted-foreground">No model improvement items returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {modelImprovement.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `mi-${id}` : `mi-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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
        description="Versioned knowledge dataset snapshots — approval status, entity counts, and provenance for each curated release."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : errDatasetVersions ? (
            <p className="text-sm text-muted-foreground">{errDatasetVersions}</p>
          ) : datasetVersions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No dataset versions returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>updated_at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datasetVersions.slice(0, 10).map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `dv-${id}` : `dv-i-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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
        Knowledge Library lists are operational signals from your tenant API — not legal conclusions or agency positions.
        See{" "}
        <Link className="font-medium text-primary underline-offset-4 hover:underline" href="/validation">
          Validation
        </Link>{" "}
        for model validation runs.
      </p>
    </div>
  )
}
