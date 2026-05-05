"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { CheckCircle2, FlaskConical, LineChart, ListChecks, Plus } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
  { value: "multi_objective", label: "multi_objective" },
]

function fmtDate(iso: string): string {
  if (!iso?.trim()) return "—"
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return iso
  return new Date(ms).toLocaleString()
}

function fmtYield(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`
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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {sub}
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
    let bestYield: number | null = null
    for (const p of projects) {
      if (p.status === "active") active += 1
      const c = countsById.get(p.id)
      if (c) {
        experimentsCompleted += c.experimentsCompleted
        pendingReview += c.recommendationsPendingReview
        if (c.bestYieldPercent != null) {
          if (bestYield == null || c.bestYieldPercent > bestYield) bestYield = c.bestYieldPercent
        }
      }
    }
    return { active, experimentsCompleted, pendingReview, bestYield }
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

  const showListUnavailable = !listLoading && listError

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Reaction Optimization</h1>
          <p className="text-muted-foreground">
            Design, track, model, and review reaction-condition experiments.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {showListUnavailable ? (
        <Alert variant="default" className="border-muted bg-muted/30">
          <AlertTitle className="text-sm">Backend unavailable</AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">{listError}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryMetricCard
          title="Active reaction projects"
          icon={<FlaskConical className="h-4 w-4 text-muted-foreground" />}
          value={listLoading ? "…" : fmtInt(aggregate.active)}
          sub={
            <p className="text-xs text-muted-foreground">
              {listLoading ? "Loading…" : "status = active (GET /reaction-projects)."}
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
                ? "Loading…"
                : "Summed from GET …/experiments (status completed)."}
            </p>
          }
        />
        <SummaryMetricCard
          title="Recommendations pending review"
          icon={<ListChecks className="h-4 w-4 text-muted-foreground" />}
          value={listLoading || countsLoading ? "…" : fmtInt(aggregate.pendingReview)}
          sub={
            <p className="text-xs text-muted-foreground">
              {listLoading || countsLoading
                ? "Loading…"
                : "Summed from GET …/recommendations (status proposed)."}
            </p>
          }
        />
        <SummaryMetricCard
          title="Best yield observed"
          icon={<LineChart className="h-4 w-4 text-muted-foreground" />}
          value={listLoading || countsLoading ? "…" : fmtYield(aggregate.bestYield)}
          sub={
            <p className="text-xs text-muted-foreground">
              {listLoading || countsLoading ? "Loading…" : "Max yield_percent from completed experiments."}
            </p>
          }
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Create reaction project</CardTitle>
          <CardDescription>
            POST <code className="text-xs">/reaction-projects</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={(ev) => void handleCreate(ev)}>
            {createError ? (
              <Alert variant="destructive">
                <AlertTitle className="text-sm">Create failed</AlertTitle>
                <AlertDescription className="text-xs">{createError}</AlertDescription>
              </Alert>
            ) : null}
            {createOk ? (
              <Alert>
                <AlertTitle className="text-sm">Project created</AlertTitle>
                <AlertDescription className="text-xs">Reloaded list from GET /reaction-projects.</AlertDescription>
              </Alert>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">Reaction projects</CardTitle>
            <Badge variant="secondary" className="font-normal">
              GET /reaction-projects
            </Badge>
          </div>
          <CardDescription>Columns include linked experiment and recommendation counts when detail endpoints respond.</CardDescription>
        </CardHeader>
        <CardContent>
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
                            <Link href={`/reactions/${p.id}`}>open</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

    </div>
  )
}
