"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { CheckCircle2, FlaskConical, ListChecks, Plus, ShieldCheck } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  enrichProjectsWithCounts,
  parseReactionProjectList,
  type ReactionObjectiveValue,
  type ReactionProjectRow,
  type ProjectCounts,
} from "@/src/lib/reaction-projects/reaction-projects-data"
import { trackReactionProjectCreated } from "@/src/lib/analytics/analytics-client"
import { ReactionValidationReadinessCard } from "@/components/validation/validation-readiness-summary"
import { EvidenceCard } from "@/components/science/evidence-card"
import { DataState, DataStateBadge, type DataStateKind } from "@/components/science/data-state"

function readCreatedReactionProjectId(raw: unknown): number | undefined {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) return undefined
  const id = (raw as Record<string, unknown>).id
  if (typeof id === "number" && Number.isFinite(id)) return id
  if (typeof id === "string" && /^\d+$/.test(id)) return Number.parseInt(id, 10)
  return undefined
}

const OBJECTIVES: { value: ReactionObjectiveValue; label: string }[] = [
  { value: "maximize_yield", label: "maximize_yield" },
  { value: "maximize_selectivity", label: "maximize_selectivity" },
  { value: "minimize_impurity", label: "minimize_impurity" },
  { value: "maximize_conversion", label: "maximize_conversion" },
  { value: "minimize_e_factor", label: "minimize_e_factor" },
  { value: "maximize_atom_economy", label: "maximize_atom_economy" },
  { value: "maximize_green_score", label: "maximize_green_score" },
  { value: "multi_objective", label: "multi_objective" },
]

function fmtDate(iso: string): string {
  return formatStableUtcDateTime(iso)
}

function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  return String(Math.round(n))
}

function SummaryMetricCard({
  title,
  icon,
  value,
  sub,
}: {
  title: string
  icon: React.ReactNode
  value: string
  sub: React.ReactNode
}) {
  return (
    <Card
      className="h-full overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-violet)" }}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {title}
        </CardTitle>
        {icon}
      </CardHeader>
      <CardContent className="pb-5">
        <div
          className="font-mono text-3xl font-bold leading-none tabular-nums"
          style={{ color: "var(--mt-violet-ink)" }}
        >
          {value}
        </div>
        {sub ? <div className="mt-2">{sub}</div> : null}
      </CardContent>
    </Card>
  )
}

export function ReactionOptimizationLanding() {
  const [projects, setProjects] = useState<ReactionProjectRow[]>([])
  const [countsById, setCountsById] = useState<Map<number, ProjectCounts>>(new Map())
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState("")
  const [countsLoading, setCountsLoading] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [objective, setObjective] = useState<ReactionObjectiveValue>("maximize_yield")
  const [targetProductName, setTargetProductName] = useState("")
  const [targetProductSmiles, setTargetProductSmiles] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState("")
  const [createOk, setCreateOk] = useState(false)

  const loadProjects = useCallback(async () => {
    setListLoading(true)
    setListError("")
    try {
      const raw = await apiFetch<unknown>("/reaction-projects", { method: "GET" })
      const parsed = parseReactionProjectList(raw)
      setProjects(parsed)
      setCountsLoading(true)
      const enriched = await enrichProjectsWithCounts(parsed, 6)
      setCountsById(enriched)
    } catch (e) {
      setProjects([])
      setCountsById(new Map())
      setListError(formatApiError(e, "Could not load reaction projects."))
    } finally {
      setListLoading(false)
      setCountsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  const aggregate = useMemo(() => {
    let active = 0
    let experimentsCompleted = 0
    let pendingReview = 0
    for (const p of projects) {
      if (p.status === "active") active += 1
      const c = countsById.get(p.id)
      if (c) {
        experimentsCompleted += c.experimentsCompleted
        pendingReview += c.recommendationsPendingReview
      }
    }
    return { active, experimentsCompleted, pendingReview }
  }, [projects, countsById])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreateError("")
    setCreateOk(false)
    const trimmedName = name.trim()
    if (!trimmedName) {
      setCreateError("Project name is required.")
      return
    }
    setCreateBusy(true)
    try {
      const created = await apiFetch<unknown>("/reaction-projects", {
        method: "POST",
        body: {
          name: trimmedName,
          description: description.trim() || null,
          objective,
          status: "draft",
          target_product_name: targetProductName.trim() || null,
          target_product_smiles: targetProductSmiles.trim() || null,
          metadata_json: {},
        },
      })
      const newId = readCreatedReactionProjectId(created)
      trackReactionProjectCreated({
        reaction_project_id: newId,
        objective,
        status: "draft",
        experiment_count: 0,
      })
      setCreateOk(true)
      setName("")
      setDescription("")
      setObjective("maximize_yield")
      setTargetProductName("")
      setTargetProductSmiles("")
      await loadProjects()
    } catch (err) {
      setCreateOk(false)
      setCreateError(formatApiError(err, "Could not create reaction project."))
    } finally {
      setCreateBusy(false)
    }
  }

  const showListUnavailable = !listLoading && Boolean(listError)
  const reactionDataState: DataStateKind =
    listLoading || countsLoading
      ? "loading"
      : showListUnavailable
        ? "unavailable"
        : projects.length > 0
          ? "live"
          : "empty"

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet-ink)" }}
          >
            MolTrace · Reaction Optimization
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Reaction Optimization</h1>
          <p className="text-sm text-muted-foreground">
            Review next-best-experiment recommendations, constraints, and optimization history.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/reactions?tab=reaction-studio">Open Reaction Studio (program-level)</Link>
          </Button>
          <BackendStatusIndicator />
        </div>
      </div>

      {showListUnavailable ? (
        <AlertCard variant="warning" title="Backend unavailable" description={listError ?? ""} />
      ) : null}

      <AlertCard
        variant="warning"
        title="Chemist approval required"
        description="AI recommendations require chemist approval before execution."
      />

      <section aria-labelledby="campaign-summary-heading" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Reaction · Campaign Summary
            </p>
            <h2 id="campaign-summary-heading" className="font-mono text-xl font-bold tracking-tight">
              Campaign summary
            </h2>
            <p className="text-sm text-muted-foreground">
              Active campaigns, pending recommendations, and experiment throughput across loaded reaction projects.
            </p>
          </div>
          <DataStateBadge state={reactionDataState} />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryMetricCard
            title="Active campaigns"
            icon={<FlaskConical className="h-4 w-4 text-muted-foreground" />}
            value={listLoading ? "…" : fmtInt(aggregate.active)}
            sub={
              <p className="text-xs text-muted-foreground">
                {listLoading ? "Loading campaign list…" : "Loaded campaigns with active status."}
              </p>
            }
          />
          <SummaryMetricCard
            title="Pending recommendations"
            icon={<ListChecks className="h-4 w-4 text-muted-foreground" />}
            value={listLoading || countsLoading ? "…" : fmtInt(aggregate.pendingReview)}
            sub={
              <p className="text-xs text-muted-foreground">
                {listLoading || countsLoading
                  ? "Loading recommendation counts…"
                  : "Recommendations proposed and waiting for review."}
              </p>
            }
          />
          <SummaryMetricCard
            title="Experiments completed"
            icon={<CheckCircle2 className="h-4 w-4 text-muted-foreground" />}
            value={listLoading || countsLoading ? "…" : fmtInt(aggregate.experimentsCompleted)}
            sub={
              <p className="text-xs text-muted-foreground">
                {listLoading || countsLoading
                  ? "Loading experiment counts…"
                  : "Completed experiments across loaded campaigns."}
              </p>
            }
          />
          <SummaryMetricCard
            title="Experiments avoided"
            icon={<ShieldCheck className="h-4 w-4 text-muted-foreground" />}
            value={listLoading || countsLoading ? "…" : "—"}
            sub={<p className="text-xs text-muted-foreground">Not returned by loaded campaign data.</p>}
          />
        </div>
        {reactionDataState === "empty" ? (
          <DataState
            state="empty"
            title="No optimization campaigns yet."
            description="Create or open a reaction project to begin reviewing recommendations."
          />
        ) : null}
        {reactionDataState === "unavailable" ? (
          <DataState
            state="unavailable"
            title="Campaign data unavailable."
            description="Loaded data could not be reached, so no optimization results are shown."
          />
        ) : null}
      </section>

      <section className="space-y-3" aria-label="Validation readiness">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-violet-ink)" }}
        >
          Reaction · Validation Readiness
        </p>
        <ReactionValidationReadinessCard />
      </section>

      <section aria-labelledby="recommendation-evidence-heading" className="space-y-3">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet-ink)" }}
          >
            Reaction · Recommendation Evidence
          </p>
          <h2 id="recommendation-evidence-heading" className="font-mono text-xl font-bold tracking-tight">
            Recommendation evidence
          </h2>
          <p className="text-sm text-muted-foreground">
            Top reaction recommendation card aggregated across loaded campaigns — open the project for full reasoning.
          </p>
        </div>
        <EvidenceCard
          title="Recommendation evidence"
          module="reactions"
          status={
            reactionDataState === "loading" || reactionDataState === "unavailable"
              ? "unavailable"
              : aggregate.pendingReview > 0
                ? "pending_review"
                : "draft"
          }
          risk_level={aggregate.pendingReview > 0 ? "medium" : "unknown"}
          summary={
            reactionDataState === "loading"
              ? "Loading recommendation review evidence from reaction project summaries."
              : reactionDataState === "unavailable"
                ? "Recommendation evidence is unavailable while campaign data cannot be reached."
                : projects.length === 0
                  ? "No optimization campaigns yet."
                  : aggregate.pendingReview > 0
                    ? "One or more optimization recommendations are waiting for human review before experimental action."
                    : "No pending optimization recommendations are loaded from the current project list."
          }
          evidence_items={[
            `Active campaigns: ${listLoading ? "loading" : fmtInt(aggregate.active)}`,
            `Pending recommendations: ${listLoading || countsLoading ? "loading" : fmtInt(aggregate.pendingReview)}`,
            projects.length === 0
              ? "No optimization campaigns yet."
              : "Review recommendations in project-level Reaction Studio before converting them into experiments.",
          ]}
          citations={[]}
          review_status={
            listLoading || countsLoading ? "loading" : aggregate.pendingReview > 0 ? "pending review" : "none pending"
          }
        />
      </section>

      <section className="space-y-3" aria-label="Create reaction project">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet-ink)" }}
          >
            Reaction · Create Project
          </p>
          <h2 className="font-mono text-xl font-bold tracking-tight">Spin up a new reaction project</h2>
          <p className="text-sm text-muted-foreground">
            Bind an objective and target product (SMILES) to a new project record. Variables, experiments, and recommendations land in the project workspace.
          </p>
        </div>
        <ModuleCard
          accent="violet"
          eyebrow="Reaction · Create"
          title="Create reaction project"
          description="Create a project record for optimization review."
        >
          <form className="space-y-4" onSubmit={(ev) => void handleCreate(ev)}>
            {createError ? (
              <AlertCard variant="error" title="Create failed" description={createError} />
            ) : null}
            {createOk ? (
              <AlertCard
                variant="success"
                title="Project created"
                description="Reloaded project list from the server."
              />
            ) : null}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="rxn-project-name">project name</Label>
                <Input
                  id="rxn-project-name"
                  value={name}
                  onChange={(ev) => setName(ev.target.value)}
                  maxLength={240}
                  autoComplete="off"
                  disabled={createBusy}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="rxn-project-desc">description</Label>
                <Textarea
                  id="rxn-project-desc"
                  value={description}
                  onChange={(ev) => setDescription(ev.target.value)}
                  rows={3}
                  disabled={createBusy}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="rxn-objective">objective</Label>
                <Select
                  value={objective}
                  onValueChange={(v) => setObjective(v as ReactionObjectiveValue)}
                  disabled={createBusy}
                >
                  <SelectTrigger id="rxn-objective">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {OBJECTIVES.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="rxn-target-name">target product name</Label>
                <Input
                  id="rxn-target-name"
                  value={targetProductName}
                  onChange={(ev) => setTargetProductName(ev.target.value)}
                  maxLength={240}
                  autoComplete="off"
                  disabled={createBusy}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="rxn-target-smiles">target product SMILES</Label>
                <Input
                  id="rxn-target-smiles"
                  value={targetProductSmiles}
                  onChange={(ev) => setTargetProductSmiles(ev.target.value)}
                  maxLength={10000}
                  autoComplete="off"
                  disabled={createBusy}
                />
              </div>
            </div>
            <Button type="submit" disabled={createBusy}>
              <Plus className="mr-2 h-4 w-4" />
              {createBusy ? "Creating…" : "Create reaction project"}
            </Button>
          </form>
        </ModuleCard>
      </section>

      <section className="space-y-3" aria-label="Reaction projects index">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet-ink)" }}
          >
            Reaction · Project Index
          </p>
          <h2 className="font-mono text-xl font-bold tracking-tight">All reaction projects in this org</h2>
          <p className="text-sm text-muted-foreground">
            Per-project status, linked experiments, and pending recommendation counts — open any row for the full workspace.
          </p>
        </div>
        <ModuleCard
          accent="violet"
          eyebrow="Reaction · Projects"
          title="Reaction projects"
        description="Columns include linked experiment and recommendation counts when project details respond."
        badge={
          <Badge variant="secondary" className="font-normal">
            Project list
          </Badge>
        }
      >
        <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>project name</TableHead>
                  <TableHead>objective</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead className="text-right">experiments</TableHead>
                  <TableHead className="text-right">recommendations</TableHead>
                  <TableHead>updated date</TableHead>
                  <TableHead className="w-[100px]">
                    <span className="sr-only">open</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {listLoading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                      Loading…
                    </TableCell>
                  </TableRow>
                ) : projects.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                      {showListUnavailable ? "No data — backend unavailable." : "No reaction projects yet."}
                    </TableCell>
                  </TableRow>
                ) : (
                  projects.map((p) => {
                    const c = countsById.get(p.id)
                    return (
                      <TableRow key={p.id}>
                        <TableCell className="font-medium">{p.name}</TableCell>
                        <TableCell className="font-mono text-xs">{p.objective}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-normal">
                            {p.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {countsLoading && !c ? "…" : c ? fmtInt(c.experiments) : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {countsLoading && !c ? "…" : c ? fmtInt(c.recommendations) : "—"}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {fmtDate(p.updated_at)}
                        </TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm" asChild>
                            <Link href={`/reactions/${p.id}`}>Open Reaction Studio (project-level)</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </ModuleCard>
      </section>
    </div>
  )
}
