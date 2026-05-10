"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  AlertCircle,
  AlertTriangle,
  ClipboardCheck,
  ClipboardList,
  FileCheck2,
  FlaskConical,
  Layers3,
  ListChecks,
  Plus,
  Wrench,
  XCircle,
} from "lucide-react"

type Row = Record<string, unknown>

type ValidationProjectRow = {
  id: string
  title: string
  scope: string
  validation_type: string
  status: string
  owner: string
  qa_reviewer: string
  updated_date: string
  requirements_count: number
  open_risks_count: number
  test_cases_count: number
  failed_tests_count: number
  controlled_records_count: number
  open_deviations_count: number
  capa_items_count: number
}

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return Math.max(0, Math.floor(v))
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.max(0, Math.floor(Number(v)))
  return 0
}

function extractRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  const keys = ["items", "results", "projects", "validation_projects", "rows", "data"]
  for (const key of keys) {
    const value = payload[key]
    if (Array.isArray(value)) return value.filter(isRecord)
  }
  return []
}

function parseProjectRow(row: Row): ValidationProjectRow | null {
  const id = readStr(row.id ?? row.project_id ?? row.validation_project_id)
  if (!id) return null
  return {
    id,
    title: readStr(row.title) || "—",
    scope: readStr(row.scope) || "—",
    validation_type: readStr(row.validation_type) || "—",
    status: readStr(row.status) || "—",
    owner: readStr(row.owner ?? row.owner_name) || "—",
    qa_reviewer: readStr(row.qa_reviewer ?? row.qa_reviewer_name) || "—",
    updated_date: readStr(row.updated_date ?? row.updated_at) || "—",
    requirements_count: readNum(row.requirements_count),
    open_risks_count: readNum(row.open_risks_count),
    test_cases_count: readNum(row.test_cases_count),
    failed_tests_count: readNum(row.failed_tests_count),
    controlled_records_count: readNum(row.controlled_records_count),
    open_deviations_count: readNum(row.open_deviations_count),
    capa_items_count: readNum(row.capa_items_count),
  }
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

export function ValidationCenterWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [projects, setProjects] = useState<ValidationProjectRow[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState("")

  const [title, setTitle] = useState("")
  const [scope, setScope] = useState("")
  const [validationType, setValidationType] = useState("")
  const [intendedUse, setIntendedUse] = useState("")
  const [regulatedContext, setRegulatedContext] = useState("")
  const [ownerName, setOwnerName] = useState("")
  const [qaReviewerName, setQaReviewerName] = useState("")
  const [createBusy, setCreateBusy] = useState(false)

  const loadProjects = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/validation-center/projects", { method: "GET" })
      const rows = extractRows(payload).map(parseProjectRow).filter((row): row is ValidationProjectRow => row != null)
      setProjects(rows)
      if (!selectedProjectId && rows.length > 0) setSelectedProjectId(rows[0]!.id)
    } catch (e) {
      setError(formatErr(e, "Could not load validation projects."))
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [selectedProjectId])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  async function createValidationProject() {
    setCreateBusy(true)
    setError("")
    try {
      await apiFetch("/validation-center/projects", {
        method: "POST",
        body: {
          title: title.trim(),
          scope: scope.trim(),
          validation_type: validationType.trim(),
          intended_use: intendedUse.trim(),
          regulated_context: regulatedContext.trim(),
          owner_name: ownerName.trim(),
          qa_reviewer_name: qaReviewerName.trim(),
        },
      })
      setTitle("")
      setScope("")
      setValidationType("")
      setIntendedUse("")
      setRegulatedContext("")
      setOwnerName("")
      setQaReviewerName("")
      await loadProjects()
    } catch (e) {
      setError(formatErr(e, "Could not create validation project."))
    } finally {
      setCreateBusy(false)
    }
  }

  const summary = useMemo(() => {
    const validationProjects = projects.length
    const requirements = projects.reduce((sum, p) => sum + p.requirements_count, 0)
    const openRisks = projects.reduce((sum, p) => sum + p.open_risks_count, 0)
    const testCases = projects.reduce((sum, p) => sum + p.test_cases_count, 0)
    const failedTests = projects.reduce((sum, p) => sum + p.failed_tests_count, 0)
    const controlledRecords = projects.reduce((sum, p) => sum + p.controlled_records_count, 0)
    const openDeviations = projects.reduce((sum, p) => sum + p.open_deviations_count, 0)
    const capaItems = projects.reduce((sum, p) => sum + p.capa_items_count, 0)
    return {
      validationProjects,
      requirements,
      openRisks,
      testCases,
      failedTests,
      controlledRecords,
      openDeviations,
      capaItems,
    }
  }, [projects])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-cyan)" }}
          >
            MolTrace · Validation Center
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Validation Center</h1>
          <p className="text-sm text-muted-foreground">
            Build validation projects, risk assessments, traceability matrices, test evidence, e-signatures, controlled
            records, and inspection-ready packages.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <AlertCard
        variant="warning"
        title="Internal readiness only"
        description="Validation Center supports internal validation readiness and evidence packaging. It does not represent FDA approval, Annex 11 certification, or legal compliance by itself."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-cyan)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Validation projects</CardTitle>
            <FlaskConical className="h-4 w-4" style={{ color: "var(--mt-cyan)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-cyan)" }}
            >
              {summary.validationProjects}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-cyan)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Requirements</CardTitle>
            <ListChecks className="h-4 w-4" style={{ color: "var(--mt-cyan)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-cyan)" }}
            >
              {summary.requirements}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-amber)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Open risks</CardTitle>
            <AlertTriangle className="h-4 w-4" style={{ color: "var(--mt-amber)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-amber)" }}
            >
              {summary.openRisks}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-cyan)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Test cases</CardTitle>
            <ClipboardCheck className="h-4 w-4" style={{ color: "var(--mt-cyan)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-cyan)" }}
            >
              {summary.testCases}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-red)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Failed tests</CardTitle>
            <XCircle className="h-4 w-4" style={{ color: "var(--mt-red)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-red)" }}
            >
              {summary.failedTests}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-cyan)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Controlled records</CardTitle>
            <FileCheck2 className="h-4 w-4" style={{ color: "var(--mt-cyan)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-cyan)" }}
            >
              {summary.controlledRecords}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-amber)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Open deviations</CardTitle>
            <AlertCircle className="h-4 w-4" style={{ color: "var(--mt-amber)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-amber)" }}
            >
              {summary.openDeviations}
            </div>
          </CardContent>
        </Card>

        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-violet)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">CAPA items</CardTitle>
            <Wrench className="h-4 w-4" style={{ color: "var(--mt-violet)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div
              className="font-mono text-3xl font-bold tabular-nums leading-none"
              style={{ color: "var(--mt-violet)" }}
            >
              {summary.capaItems}
            </div>
          </CardContent>
        </Card>
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="Module Order"
        title="Module readiness"
        icon={Layers3}
        description="Global module order and readiness coverage."
      >
        <div className="space-y-2 text-sm">
          <div className="rounded-md border bg-muted/20 px-3 py-2">1. SpectraCheck</div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">2. Regulatory Hub</div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">3. Reaction Optimization</div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">4. Cross-module/system</div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="cyan"
        eyebrow="Projects"
        title="Validation projects"
        icon={ClipboardList}
        description="All validation projects for this tenant — title, scope, validation type, status, owner, and QA reviewer."
      >
        <div className="space-y-3">
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          {loading ? <p className="text-sm text-muted-foreground">Loading validation projects…</p> : null}
          {!loading ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>title</TableHead>
                    <TableHead>scope</TableHead>
                    <TableHead>validation type</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>owner</TableHead>
                    <TableHead>QA reviewer</TableHead>
                    <TableHead>updated date</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {projects.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-xs text-muted-foreground">
                        No validation projects returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    projects.map((project) => (
                      <TableRow key={project.id}>
                        <TableCell className="text-xs">{project.title}</TableCell>
                        <TableCell className="text-xs">{project.scope}</TableCell>
                        <TableCell className="text-xs">{project.validation_type}</TableCell>
                        <TableCell className="text-xs">{project.status}</TableCell>
                        <TableCell className="text-xs">{project.owner}</TableCell>
                        <TableCell className="text-xs">{project.qa_reviewer}</TableCell>
                        <TableCell className="text-xs">{project.updated_date}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedProjectId === project.id ? "secondary" : "outline"}
                            asChild
                          >
                            <Link href={`/validation-center/projects/${encodeURIComponent(project.id)}`}>Open</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="cyan"
        eyebrow="Create"
        title="Create validation project"
        icon={Plus}
        description="Create a new validation project — specify title, scope, validation type, owner, and QA reviewer to open the project workspace."
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="validation-center-title">title</Label>
              <Input id="validation-center-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="validation-center-scope">scope</Label>
              <Input id="validation-center-scope" value={scope} onChange={(e) => setScope(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="validation-center-type">validation type</Label>
              <Input
                id="validation-center-type"
                value={validationType}
                onChange={(e) => setValidationType(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="validation-center-owner-name">owner name</Label>
              <Input
                id="validation-center-owner-name"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="validation-center-qa-reviewer-name">QA reviewer name</Label>
              <Input
                id="validation-center-qa-reviewer-name"
                value={qaReviewerName}
                onChange={(e) => setQaReviewerName(e.target.value)}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="validation-center-intended-use">intended use</Label>
              <Textarea
                id="validation-center-intended-use"
                value={intendedUse}
                onChange={(e) => setIntendedUse(e.target.value)}
                rows={3}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="validation-center-regulated-context">regulated context</Label>
              <Textarea
                id="validation-center-regulated-context"
                value={regulatedContext}
                onChange={(e) => setRegulatedContext(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={createBusy} onClick={() => void createValidationProject()}>
              {createBusy ? "Creating…" : "Create validation project"}
            </Button>
            <Button type="button" variant="outline" disabled={loading} onClick={() => void loadProjects()}>
              Refresh projects
            </Button>
          </div>
        </div>
      </ModuleCard>
    </div>
  )
}
