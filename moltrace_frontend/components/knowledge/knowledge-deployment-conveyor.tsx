"use client"

// The deployment conveyor for models trained from the curated corpus.
//
// Four things this screen has to keep straight, each of which the obvious
// rendering gets wrong:
//
//  1. A step is only offered when the service will accept it. `status` moves
//     proposed → eligible | blocked → limited rollout → in service, and each
//     step refuses to run without the one before it. A button that always fails
//     presents a governed sequence as a menu.
//  2. A passed check is eligibility, never approval. `requires_human_signoff` is
//     always true, so nothing here may render a cleared check as a promotion.
//  3. Refusal reasons are shown verbatim. Summarising them to "did not improve"
//     throws away the only account of what actually blocked it — and the check
//     fails closed, so a thin-looking reason usually means a measure was absent.
//  4. This is not the model factory's deployment queue. That one governs model
//     artifacts; this one governs what a model was trained on.
//
// See `lib/knowledge/corpus-conveyor.ts` §2–4.

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Loader2,
  Plus,
  Rocket,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  CONVEYOR_SEPARATE_FROM_MODEL_FACTORY_NOTE,
  DEPLOYMENT_STATUSES,
  DEPLOYMENT_STATUS_PRESENTATION,
  GATE_ELIGIBILITY_NOTE,
  GATE_FAILS_CLOSED_NOTE,
  advanceDeploymentCandidate,
  conveyorSteps,
  createDeploymentCandidate,
  fetchDeploymentCandidates,
  metricLabel,
  readDeploymentStatus,
  readGateVerdict,
  stepUnavailableReason,
  type ConveyorAction,
  type DeploymentStatus,
  type KnowledgeDeploymentCandidate,
} from "@/lib/knowledge/corpus-conveyor"

const STATUS_TONE_CLASS: Record<DeploymentStatus, string> = {
  draft: "border-muted-foreground/40 text-muted-foreground",
  gate_passed: "border-emerald-500/50 text-emerald-700 dark:text-emerald-400",
  gate_failed: "border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-400",
  canary: "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  promoted: "border-sky-500/50 text-sky-700 dark:text-sky-400",
}

const STATUS_ICON: Record<DeploymentStatus, typeof CheckCircle2> = {
  draft: CircleDot,
  gate_passed: ShieldCheck,
  gate_failed: XCircle,
  canary: AlertTriangle,
  promoted: Rocket,
}

function DeploymentStatusBadge({ status }: { status: DeploymentStatus }) {
  const presentation = DEPLOYMENT_STATUS_PRESENTATION[status]
  const Icon = STATUS_ICON[status]
  return (
    <Badge
      variant="outline"
      title={presentation.description}
      className={`gap-1 whitespace-nowrap ${STATUS_TONE_CLASS[status]}`}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      {presentation.label}
    </Badge>
  )
}

function formatWhen(iso: string | undefined | null): string {
  if (!iso?.trim()) return "—"
  const parsed = Date.parse(iso)
  if (Number.isNaN(parsed)) return iso
  return new Date(parsed).toLocaleString()
}

function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "not recorded"
  return String(value)
}

type MetricRow = {
  key: string
  name: string
  candidate: string
  incumbent: string
  direction: "higher" | "lower"
}

function emptyMetricRow(index: number): MetricRow {
  return { key: `m${index}`, name: "", candidate: "", incumbent: "", direction: "higher" }
}

/** The gate verdict, read out rather than summarised. */
function GateVerdictPanel({ candidate }: { candidate: KnowledgeDeploymentCandidate }) {
  const verdict = readGateVerdict(candidate.gate_verdict_json)
  if (!verdict.present) {
    return (
      <p className="text-sm text-muted-foreground">
        This candidate has not been checked against the model in service yet.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant="outline"
          className={
            verdict.promotable
              ? "gap-1 border-emerald-500/50 text-emerald-700 dark:text-emerald-400"
              : "gap-1 border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-400"
          }
        >
          {verdict.promotable ? (
            <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden />
          ) : (
            <XCircle className="h-3 w-3 shrink-0" aria-hidden />
          )}
          {verdict.promotable ? "Eligible" : "Blocked"}
        </Badge>
        {verdict.rollbackAvailable ? (
          <span className="text-xs text-muted-foreground">The model in service stays available to roll back to.</span>
        ) : null}
      </div>

      {/* A cleared check is eligibility. Rendering it as a completed promotion is
          the one misreading this panel exists to prevent. */}
      {verdict.requiresHumanSignoff ? (
        <p className="text-xs text-muted-foreground">{GATE_ELIGIBILITY_NOTE}</p>
      ) : null}

      {verdict.blockingMetricName ? (
        <p className="text-sm">
          <span className="text-muted-foreground">Measure treated as the blocking one: </span>
          {metricLabel(verdict.blockingMetricName)}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">No measure was named as the blocking one.</p>
      )}

      {verdict.reasons.length > 0 ? (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Reasons</p>
          {/* Verbatim. Compressing these to "did not improve" would hide, among
              other things, that a measure was missing rather than merely worse. */}
          <ul className="list-inside list-disc space-y-1 text-sm">
            {verdict.reasons.map((reason, i) => (
              <li key={`${i}-${reason.slice(0, 40)}`}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {verdict.excludedMetrics.length > 0 ? (
        <Alert>
          <AlertTitle className="text-sm">Measures left out of the comparison</AlertTitle>
          <AlertDescription className="text-sm">
            {verdict.excludedMetrics.map(metricLabel).join(", ")} — either the candidate did not report
            them, or which direction counts as better was never recorded for them.
          </AlertDescription>
        </Alert>
      ) : null}

      {!verdict.promotable ? (
        <p className="text-xs text-muted-foreground">{GATE_FAILS_CLOSED_NOTE}</p>
      ) : null}
    </div>
  )
}

function MetricComparison({ candidate }: { candidate: KnowledgeDeploymentCandidate }) {
  const names = useMemo(() => {
    const all = new Set([
      ...Object.keys(candidate.metrics_json ?? {}),
      ...Object.keys(candidate.incumbent_metrics_json ?? {}),
    ])
    return Array.from(all).sort()
  }, [candidate])

  if (names.length === 0) {
    return <p className="text-sm text-muted-foreground">No measures were recorded for this candidate.</p>
  }

  return (
    <div className="table-scroll min-w-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Measure</TableHead>
            <TableHead className="text-right">Candidate</TableHead>
            <TableHead className="text-right">In service</TableHead>
            <TableHead>Better when</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {names.map((name) => {
            const direction = (candidate.metric_directions_json ?? {})[name]
            return (
              <TableRow key={name}>
                <TableCell className="text-sm">{metricLabel(name)}</TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {formatNumber((candidate.metrics_json ?? {})[name])}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums">
                  {formatNumber((candidate.incumbent_metrics_json ?? {})[name])}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {direction === "higher"
                    ? "Higher"
                    : direction === "lower"
                      ? "Lower"
                      : "Not recorded"}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

export function KnowledgeDeploymentConveyor() {
  const [rows, setRows] = useState<KnowledgeDeploymentCandidate[]>([])
  const [loading, setLoading] = useState(false)
  const [loadErr, setLoadErr] = useState("")
  const [statusFilter, setStatusFilter] = useState("")
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [actionBusy, setActionBusy] = useState<ConveyorAction | null>(null)
  const [actionErr, setActionErr] = useState("")
  const [actionOk, setActionOk] = useState("")

  const [datasetVersionId, setDatasetVersionId] = useState("")
  const [modelVersion, setModelVersion] = useState("")
  const [metricRows, setMetricRows] = useState<MetricRow[]>([emptyMetricRow(0)])
  const [blockingName, setBlockingName] = useState("")
  const [blockingCandidate, setBlockingCandidate] = useState("")
  const [blockingIncumbent, setBlockingIncumbent] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      setRows(await fetchDeploymentCandidates(statusFilter || undefined))
    } catch (e) {
      setRows([])
      setLoadErr(formatApiError(e, "Could not load deployment candidates."))
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  )
  const selectedStatus = selected ? readDeploymentStatus(selected.status) : "draft"
  const selectedNotes = selected?.notes ?? []
  const steps = conveyorSteps(selectedStatus)

  async function runStep(action: ConveyorAction) {
    if (selected == null) return
    setActionErr("")
    setActionOk("")
    setActionBusy(action)
    try {
      const updated = await advanceDeploymentCandidate(selected.id, action)
      setRows((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
      const nextStatus = readDeploymentStatus(updated.status)
      setActionOk(DEPLOYMENT_STATUS_PRESENTATION[nextStatus].description)
    } catch (e) {
      setActionErr(
        formatApiError(e, "That step could not run. Check that the step before it has completed."),
      )
      void load()
    } finally {
      setActionBusy(null)
    }
  }

  function updateMetricRow(key: string, patch: Partial<MetricRow>) {
    setMetricRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  async function submitCreate() {
    setCreateErr("")
    setCreateOk("")
    const dvId = Number.parseInt(datasetVersionId.trim(), 10)
    if (!Number.isFinite(dvId) || dvId < 1) {
      setCreateErr("Enter the dataset version ID as a positive whole number.")
      return
    }
    const metrics: Record<string, number> = {}
    const incumbent: Record<string, number> = {}
    const directions: Record<string, string> = {}
    for (const row of metricRows) {
      const name = row.name.trim()
      if (!name) continue
      const c = Number.parseFloat(row.candidate)
      const i = Number.parseFloat(row.incumbent)
      if (!Number.isFinite(c) || !Number.isFinite(i)) {
        setCreateErr(`Give ${name} a value for both the candidate and the model in service.`)
        return
      }
      metrics[name] = c
      incumbent[name] = i
      directions[name] = row.direction
    }
    const blocking = blockingName.trim()
    const draft = {
      dataset_version_id: dvId,
      model_version: modelVersion.trim(),
      metrics_json: metrics,
      incumbent_metrics_json: incumbent,
      metric_directions_json: directions,
      ...(blocking ? { blocking_metric_name: blocking } : {}),
      ...(blockingCandidate.trim() && Number.isFinite(Number.parseFloat(blockingCandidate))
        ? { blocking_metric_value: Number.parseFloat(blockingCandidate) }
        : {}),
      ...(blockingIncumbent.trim() && Number.isFinite(Number.parseFloat(blockingIncumbent))
        ? { incumbent_blocking_metric_value: Number.parseFloat(blockingIncumbent) }
        : {}),
    }
    setCreateBusy(true)
    try {
      const created = await createDeploymentCandidate(draft)
      setCreateOk("Candidate proposed. It has not been checked yet.")
      setSelectedId(created.id)
      await load()
    } catch (e) {
      // The commonest refusal here is a dataset version two people have not
      // approved — the conveyor's entry condition, not a malformed request.
      setCreateErr(
        formatApiError(
          e,
          "Could not propose this candidate. A candidate can only be built from a dataset version two people have approved.",
        ),
      )
    } finally {
      setCreateBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{CONVEYOR_SEPARATE_FROM_MODEL_FACTORY_NOTE}</p>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-2">
          <Label>Status filter</Label>
          <Select
            value={statusFilter || "__all"}
            onValueChange={(v) => setStatusFilter(v === "__all" ? "" : v)}
          >
            <SelectTrigger className="w-[220px]">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">All</SelectItem>
              {DEPLOYMENT_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {DEPLOYMENT_STATUS_PRESENTATION[s].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card className="border-dashed">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Propose a candidate</CardTitle>
          <CardDescription>
            Only a dataset version two people have approved can be proposed. Record what the candidate
            scored and what the model in service scores, so the two can be compared.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="dc-dv">Dataset version ID</Label>
              <Input
                id="dc-dv"
                className="font-mono"
                value={datasetVersionId}
                onChange={(e) => setDatasetVersionId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dc-mv">Model version label</Label>
              <Input
                id="dc-mv"
                className="font-mono"
                value={modelVersion}
                onChange={(e) => setModelVersion(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Measures</Label>
            <p className="text-xs text-muted-foreground">
              A candidate has to be no worse on every measure and better on at least one. A measure
              whose direction is not recorded, or that the candidate does not report, is left out of
              the comparison and counts against it.
            </p>
            {metricRows.map((row) => (
              <div key={row.key} className="grid gap-2 sm:grid-cols-[1.4fr_1fr_1fr_1fr_auto]">
                <Input
                  aria-label="Measure name"
                  placeholder="Measure name"
                  className="font-mono text-xs"
                  value={row.name}
                  onChange={(e) => updateMetricRow(row.key, { name: e.target.value })}
                />
                <Input
                  aria-label="Candidate value"
                  placeholder="Candidate"
                  className="font-mono text-xs"
                  value={row.candidate}
                  onChange={(e) => updateMetricRow(row.key, { candidate: e.target.value })}
                />
                <Input
                  aria-label="Value for the model in service"
                  placeholder="In service"
                  className="font-mono text-xs"
                  value={row.incumbent}
                  onChange={(e) => updateMetricRow(row.key, { incumbent: e.target.value })}
                />
                <Select
                  value={row.direction}
                  onValueChange={(v) => updateMetricRow(row.key, { direction: v as "higher" | "lower" })}
                >
                  <SelectTrigger className="text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="higher">Higher is better</SelectItem>
                    <SelectItem value="lower">Lower is better</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Remove this measure"
                  disabled={metricRows.length === 1}
                  onClick={() => setMetricRows((prev) => prev.filter((r) => r.key !== row.key))}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMetricRows((prev) => [...prev, emptyMetricRow(prev.length)])}
            >
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              Add a measure
            </Button>
          </div>

          <div className="space-y-2 rounded-md border p-3">
            <Label>Blocking measure</Label>
            <p className="text-xs text-muted-foreground">
              The one measure that may not slip at all. It is compared as a rate between 0 and 1 — a
              value outside that range, or one that is missing, blocks the candidate rather than being
              skipped.
            </p>
            <div className="grid gap-2 sm:grid-cols-3">
              <Input
                aria-label="Blocking measure name"
                placeholder="Measure name"
                className="font-mono text-xs"
                value={blockingName}
                onChange={(e) => setBlockingName(e.target.value)}
              />
              <Input
                aria-label="Blocking measure, candidate value"
                placeholder="Candidate"
                className="font-mono text-xs"
                value={blockingCandidate}
                onChange={(e) => setBlockingCandidate(e.target.value)}
              />
              <Input
                aria-label="Blocking measure, value for the model in service"
                placeholder="In service"
                className="font-mono text-xs"
                value={blockingIncumbent}
                onChange={(e) => setBlockingIncumbent(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" disabled={createBusy} onClick={() => void submitCreate()}>
              {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
              Propose candidate
            </Button>
            {createErr ? <span className="text-sm text-destructive">{createErr}</span> : null}
            {createOk ? <span className="text-sm text-muted-foreground">{createOk}</span> : null}
          </div>
        </CardContent>
      </Card>

      {loadErr ? (
        <p className="text-sm text-muted-foreground">{loadErr}</p>
      ) : loading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading…
        </p>
      ) : rows.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Rocket />
            </EmptyMedia>
            <EmptyTitle>No deployment candidates</EmptyTitle>
            <EmptyDescription>
              A candidate starts from a dataset version two people have approved.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="table-scroll min-w-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[72px]">ID</TableHead>
                <TableHead>Dataset version</TableHead>
                <TableHead>Model version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Blocking measure</TableHead>
                <TableHead>Human review</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-[90px]">Open</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => {
                const status = readDeploymentStatus(row.status)
                return (
                  <TableRow key={row.id}>
                    <TableCell className="font-mono text-xs">{row.id}</TableCell>
                    <TableCell className="font-mono text-xs">{row.dataset_version_id}</TableCell>
                    <TableCell className="font-mono text-xs">{row.model_version || "—"}</TableCell>
                    <TableCell>
                      <DeploymentStatusBadge status={status} />
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.blocking_metric_name ? metricLabel(row.blocking_metric_name) : "—"}
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.human_review_required ? "Required" : "Not required"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWhen(row.created_at)}
                    </TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        size="sm"
                        variant={selectedId === row.id ? "secondary" : "outline"}
                        className="h-8"
                        onClick={() => {
                          setSelectedId(row.id)
                          setActionErr("")
                          setActionOk("")
                        }}
                      >
                        Open
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {selected ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              Candidate <span className="font-mono text-xs text-muted-foreground">#{selected.id}</span>
              <DeploymentStatusBadge status={selectedStatus} />
            </CardTitle>
            <CardDescription>{DEPLOYMENT_STATUS_PRESENTATION[selectedStatus].description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <p>
                <span className="text-muted-foreground">Dataset version</span>
                <br />
                <span className="font-mono text-xs">{selected.dataset_version_id}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Limited rollout started · promoted</span>
                <br />
                <span className="text-xs">
                  {formatWhen(selected.canary_started_at)} · {formatWhen(selected.promoted_at)}
                </span>
              </p>
            </div>

            {selectedNotes.length > 0 ? (
              <Alert>
                <AlertTitle className="text-sm">Notes</AlertTitle>
                <AlertDescription>
                  <ul className="list-inside list-disc text-sm">
                    {selectedNotes.map((note, i) => (
                      <li key={`${i}-${note.slice(0, 40)}`}>{note}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Comparison against the model in service</p>
              <MetricComparison candidate={selected} />
              <p className="text-sm">
                <span className="text-muted-foreground">Blocking measure: </span>
                {selected.blocking_metric_name ? metricLabel(selected.blocking_metric_name) : "not named"}
                {" — "}
                candidate {formatNumber(selected.blocking_metric_value)}, in service{" "}
                {formatNumber(selected.incumbent_blocking_metric_value)}
              </p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Check result</p>
              <GateVerdictPanel candidate={selected} />
            </div>

            {/* Driven off status: a step the service would refuse is not offered,
                and the reason it is absent is stated so it does not read as broken. */}
            <div className="flex flex-wrap items-center gap-2">
              {steps.canGate ? (
                <Button type="button" disabled={actionBusy != null} onClick={() => void runStep("gate")}>
                  {actionBusy === "gate" ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                  ) : null}
                  {selectedStatus === "draft" ? "Run the check" : "Run the check again"}
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {stepUnavailableReason(selectedStatus, "canGate")}
                </span>
              )}

              {steps.canCanary ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={actionBusy != null}
                  onClick={() => void runStep("canary")}
                >
                  {actionBusy === "canary" ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                  ) : null}
                  Start a limited rollout
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {stepUnavailableReason(selectedStatus, "canCanary")}
                </span>
              )}

              {steps.canPromote ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={actionBusy != null}
                  onClick={() => void runStep("promote")}
                >
                  {actionBusy === "promote" ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                  ) : null}
                  Put into service
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {stepUnavailableReason(selectedStatus, "canPromote")}
                </span>
              )}
            </div>

            {actionErr ? <p className="text-sm text-destructive">{actionErr}</p> : null}
            {actionOk ? <p className="text-sm text-muted-foreground">{actionOk}</p> : null}

            <DeveloperJsonPanel data={selected as unknown as Record<string, unknown>} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
