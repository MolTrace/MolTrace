"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { apiFetch, ApiError } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import {
  formatIsoWhenPresent,
  normalizeProjectListPayload,
  projectsErrorMessage,
  readRecordNumber,
  readRecordString,
} from "@/components/projects/project-workspace-utils"
import {
  SessionWorkflowRunsSection,
  extractSpectraCheckSessionId,
} from "@/components/projects/session-workflow-runs-section"
import { ProjectAccessSection } from "@/components/projects/project-access-section"
import { ProjectValueSummaryCard } from "@/components/projects/project-value-summary-card"
import { ArrowLeft, Plus, ServerOff, Share2 } from "lucide-react"
import { SecureShareDialog } from "@/src/components/collaboration/SecureShareDialog"

function pickUnknownArray(obj: unknown, key: string): unknown[] {
  if (!obj || typeof obj !== "object") return []
  const v = (obj as Record<string, unknown>)[key]
  return Array.isArray(v) ? v : []
}

export default function ProjectDetailPage() {
  const params = useParams()
  const projectId = typeof params.projectId === "string" ? params.projectId : ""

  const [project, setProject] = useState<unknown>(null)
  const [samples, setSamples] = useState<unknown[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [unavailable, setUnavailable] = useState(false)

  const [sampleOpen, setSampleOpen] = useState(false)
  const [sampleIdField, setSampleIdField] = useState("")
  const [smiles, setSmiles] = useState("")
  const [nmrText, setNmrText] = useState("")
  const [solvent, setSolvent] = useState("")
  const [sampleBusy, setSampleBusy] = useState(false)
  const [sampleError, setSampleError] = useState("")

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError("")
    setUnavailable(false)
    setProject(null)
    setSamples([])
    try {
      const [p, s] = await Promise.all([
        apiFetch<unknown>(`/projects/${encodeURIComponent(projectId)}`, { method: "GET" }),
        apiFetch<unknown>(`/projects/${encodeURIComponent(projectId)}/samples`, { method: "GET" }),
      ])
      setProject(p)
      setSamples(normalizeProjectListPayload(s))
    } catch (err) {
      setError(projectsErrorMessage(err, "Could not load project."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setUnavailable(true)
      }
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  async function submitSample() {
    if (!projectId) return
    setSampleBusy(true)
    setSampleError("")
    try {
      await apiFetch(`/projects/${encodeURIComponent(projectId)}/samples`, {
        method: "POST",
        body: {
          sample_id: sampleIdField.trim() || null,
          smiles: smiles.trim(),
          nmr_text: nmrText.trim(),
          solvent: solvent.trim() || null,
        },
      })
      setSampleOpen(false)
      setSampleIdField("")
      setSmiles("")
      setNmrText("")
      setSolvent("")
      await load()
    } catch (err) {
      setSampleError(projectsErrorMessage(err, "Create sample failed."))
    } finally {
      setSampleBusy(false)
    }
  }

  const projectName =
    project && typeof project === "object"
      ? readRecordString(project, "name") ?? readRecordString(project, "project_name") ?? "—"
      : "—"
  const projectStatus = project && typeof project === "object" ? readRecordString(project, "status") ?? "—" : "—"
  const updatedAt =
    project && typeof project === "object"
      ? readRecordString(project, "updated_at") ?? readRecordString(project, "updatedAt")
      : undefined

  const recentA = pickUnknownArray(project, "recent_spectracheck_sessions")
  const recentB = pickUnknownArray(project, "spectracheck_sessions")
  const recentSessions = recentA.length > 0 ? recentA : recentB
  const sessionIdsForWorkflows = useMemo(() => {
    const ids: string[] = []
    for (const s of recentSessions) {
      const sid = extractSpectraCheckSessionId(s)
      if (sid) ids.push(sid)
    }
    return ids
  }, [recentSessions])
  const reports = pickUnknownArray(project, "reports")
  const auditSummary = project && typeof project === "object" ? (project as Record<string, unknown>).audit_summary : undefined

  const numericProjectIdForShare = useMemo(() => {
    const fromRoute = Number(projectId?.trim())
    if (Number.isFinite(fromRoute) && fromRoute >= 1) return Math.trunc(fromRoute)
    if (project && typeof project === "object") {
      const n = readRecordNumber(project, "id")
      if (n != null && Number.isFinite(n) && n >= 1) return Math.trunc(n)
    }
    return null
  }, [projectId, project])

  return (
    <div className="min-w-0 space-y-8">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/projects" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Projects
          </Link>
        </Button>
      </div>

      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-teal)" }}
        >
          Project · Detail
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Project workspace</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Project metadata, samples, value summary, member access, and connected SpectraCheck / Regulatory / Reaction campaigns.
        </p>
      </div>

      {unavailable && (
        <Card className="border-warning/40 bg-warning/10">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base text-warning">
              <ServerOff className="h-4 w-4" />
              Backend unavailable
            </CardTitle>
            <CardDescription className="text-warning/90">
              We couldn&apos;t load this project. Try refreshing in a moment, or contact your administrator if this keeps happening.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-1">
              <CardTitle className="break-words text-2xl">{projectName}</CardTitle>
              <CardDescription>Project id: {projectId || "—"}</CardDescription>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Badge variant="secondary">{projectStatus}</Badge>
              {numericProjectIdForShare != null ? (
                <SecureShareDialog
                  scope="project"
                  lockScope
                  lockTargetId
                  defaultProjectId={numericProjectIdForShare}
                  trigger={
                    <Button type="button" variant="outline" className="gap-1.5" size="sm">
                      <Share2 className="h-3.5 w-3.5" />
                      Secure share
                    </Button>
                  }
                />
              ) : null}
              <Button asChild>
                <Link href={`/spectracheck?projectId=${encodeURIComponent(projectId)}`}>Open SpectraCheck</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link href={`/spectracheck?projectId=${encodeURIComponent(projectId)}&newSession=1`}>
                  New SpectraCheck Session
                </Link>
              </Button>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">Updated {formatIsoWhenPresent(updatedAt)}</p>
        </CardHeader>
      </Card>

      <ProjectAccessSection projectId={projectId} />

      {projectId ? <ProjectValueSummaryCard projectId={projectId} /> : null}

      {error && !loading ? (
        <Card className="border-destructive/40 bg-destructive/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-destructive">Request failed</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Loading project…</p> : null}

      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-lg">Samples</CardTitle>
            <CardDescription>Samples associated with this project.</CardDescription>
          </div>
          <Dialog open={sampleOpen} onOpenChange={setSampleOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2 self-start sm:self-auto">
                <Plus className="h-4 w-4" />
                Create sample
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create sample</DialogTitle>
                <DialogDescription>
                  Required fields follow the backend schema (<code className="text-xs">smiles</code>,{" "}
                  <code className="text-xs">nmr_text</code>).
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="s-id">sample_id (optional)</Label>
                  <Input id="s-id" value={sampleIdField} onChange={(e) => setSampleIdField(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="s-smiles">smiles</Label>
                  <Input id="s-smiles" value={smiles} onChange={(e) => setSmiles(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="s-nmr">nmr_text</Label>
                  <Textarea id="s-nmr" value={nmrText} onChange={(e) => setNmrText(e.target.value)} rows={4} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="s-solv">solvent (optional)</Label>
                  <Input id="s-solv" value={solvent} onChange={(e) => setSolvent(e.target.value)} />
                </div>
                {sampleError ? <p className="text-sm text-destructive">{sampleError}</p> : null}
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSampleOpen(false)}>
                  Cancel
                </Button>
                <Button type="button" disabled={sampleBusy} onClick={() => void submitSample()}>
                  {sampleBusy ? "Creating…" : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">Sample ID</TableHead>
                <TableHead className="whitespace-nowrap">Solvent</TableHead>
                <TableHead className="whitespace-nowrap">Updated</TableHead>
                <TableHead className="whitespace-nowrap text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {samples.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground">
                    No samples yet.
                  </TableCell>
                </TableRow>
              ) : (
                samples.map((row, i) => {
                  const sid = readRecordNumber(row, "id")
                  const sampleLabel =
                    readRecordString(row, "sample_id") ?? (sid != null ? String(sid) : `sample-${i}`)
                  const solv = readRecordString(row, "solvent") ?? "—"
                  const upd =
                    readRecordString(row, "updated_at") ?? readRecordString(row, "updatedAt") ?? undefined
                  const linkId = sid != null ? String(sid) : readRecordString(row, "sample_id")
                  return (
                    <TableRow key={sid ?? sampleLabel}>
                      <TableCell className="max-w-[12rem] truncate font-mono text-xs">{sampleLabel}</TableCell>
                      <TableCell className="whitespace-nowrap">{solv}</TableCell>
                      <TableCell className="whitespace-nowrap text-muted-foreground">{formatIsoWhenPresent(upd)}</TableCell>
                      <TableCell className="text-right">
                        {linkId ? (
                          <Button variant="outline" size="sm" asChild>
                            <Link href={`/projects/${encodeURIComponent(projectId)}/samples/${encodeURIComponent(linkId)}`}>
                              Open
                            </Link>
                          </Button>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Recent SpectraCheck sessions</CardTitle>
          <CardDescription>Populated when the API includes session lists on the project record.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {recentSessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No session entries returned for this project.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Summary</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentSessions.map((s, i) => (
                  <TableRow key={i}>
                    <TableCell className="max-w-prose font-mono text-xs">
                      <pre className="whitespace-pre-wrap break-words">{JSON.stringify(s, null, 2)}</pre>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <SessionWorkflowRunsSection sessionIds={sessionIdsForWorkflows} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Reports</CardTitle>
          <CardDescription>Populated when the API includes a reports collection.</CardDescription>
        </CardHeader>
        <CardContent>
          {reports.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports returned for this project.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Entry</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-xs">
                        <pre className="whitespace-pre-wrap break-words">{JSON.stringify(r, null, 2)}</pre>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Audit summary</CardTitle>
          <CardDescription>Shown when the API provides audit summary data.</CardDescription>
        </CardHeader>
        <CardContent>
          {auditSummary === undefined || auditSummary === null ? (
            <p className="text-sm text-muted-foreground">No audit summary in the project response.</p>
          ) : (
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-xs">
              {JSON.stringify(auditSummary, null, 2)}
            </pre>
          )}
        </CardContent>
      </Card>

      {project != null ? (
        <div className="min-w-0">
          <DeveloperJsonPanel data={project} />
        </div>
      ) : null}
    </div>
  )
}
