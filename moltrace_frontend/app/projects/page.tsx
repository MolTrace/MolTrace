"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { apiFetch, ApiError } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import {
  formatIsoWhenPresent,
  normalizeProjectListPayload,
  projectsErrorMessage,
  readRecordNumber,
  readRecordString,
} from "@/components/projects/project-workspace-utils"
import { Clock, FileText, FolderOpen, Plus, ServerOff } from "lucide-react"

function projectTitle(item: unknown): string {
  return readRecordString(item, "name") ?? readRecordString(item, "project_name") ?? "—"
}

function projectIdStr(item: unknown): string | undefined {
  const id = readRecordNumber(item, "id")
  if (id != null) return String(id)
  return readRecordString(item, "id")
}

function statusLabel(item: unknown): string {
  return readRecordString(item, "status") ?? "—"
}

export default function ProjectsIndexPage() {
  const [rows, setRows] = useState<unknown[]>([])
  const [rawResponse, setRawResponse] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [unavailable, setUnavailable] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createDescription, setCreateDescription] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    setUnavailable(false)
    setRawResponse(null)
    try {
      const data = await apiFetch<unknown>("/projects", { method: "GET" })
      setRawResponse(data)
      setRows(normalizeProjectListPayload(data))
    } catch (err) {
      setRows([])
      setError(projectsErrorMessage(err, "Could not load projects."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setUnavailable(true)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function submitCreate() {
    const name = createName.trim()
    if (!name) {
      setCreateError("Name is required.")
      return
    }
    setCreateBusy(true)
    setCreateError("")
    try {
      await apiFetch("/projects", {
        method: "POST",
        body: {
          name,
          description: createDescription.trim() || null,
        },
      })
      setCreateOpen(false)
      setCreateName("")
      setCreateDescription("")
      await load()
    } catch (err) {
      setCreateError(projectsErrorMessage(err, "Create project failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  return (
    <div className="min-w-0 space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
          >
            MolTrace · Projects
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Projects</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Manage your analytical projects and collaborations. Each project binds spectroscopy sessions, regulatory dossiers, and reaction campaigns under a single shared sample-id namespace.
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2 self-start sm:self-auto">
              <Plus className="h-4 w-4" />
              Create project
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Create project</DialogTitle>
              <DialogDescription>Add a new project. The backend validates required fields.</DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="proj-name">Name</Label>
                <Input
                  id="proj-name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="proj-desc">Description (optional)</Label>
                <Textarea
                  id="proj-desc"
                  value={createDescription}
                  onChange={(e) => setCreateDescription(e.target.value)}
                  rows={3}
                />
              </div>
              {createError ? <p className="text-sm text-destructive">{createError}</p> : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button type="button" disabled={createBusy} onClick={() => void submitCreate()}>
                {createBusy ? "Creating…" : "Create"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {unavailable && (
        <Card className="border-warning/40 bg-warning/10">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base text-warning">
              <ServerOff className="h-4 w-4" />
              Backend unavailable
            </CardTitle>
            <CardDescription className="text-warning/90">
              We couldn&apos;t load your projects. Try refreshing in a moment, or contact your administrator if this keeps happening.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {error && !loading ? (
        <Card className="border-destructive/40 bg-destructive/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-destructive">Request failed</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading projects…</p>
      ) : !error && rows.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Create your first project to begin saving SpectraCheck sessions.
          </CardContent>
        </Card>
      ) : null}

      {!loading && rows.length > 0 ? (
        <div className="grid min-w-0 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {rows.map((project, index) => {
            const id = projectIdStr(project)
            const href = id != null ? `/projects/${id}` : "#"
            const updated =
              readRecordString(project, "updated_at") ?? readRecordString(project, "updatedAt") ?? undefined
            const sampleCount =
              readRecordNumber(project, "sample_count") ?? readRecordNumber(project, "sampleCount")
            const activeSessions =
              readRecordNumber(project, "active_session_count") ??
              readRecordNumber(project, "active_sessions") ??
              readRecordNumber(project, "activeSessions")
            const reportsReady =
              readRecordNumber(project, "reports_ready") ??
              readRecordNumber(project, "ready_report_count") ??
              readRecordNumber(project, "reportsReady")

            return (
              <Card key={id ?? index} className="min-w-0 transition-shadow hover:shadow-md">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary">
                      <FolderOpen className="h-5 w-5" />
                    </div>
                    <Badge variant="secondary" className="shrink-0">
                      {statusLabel(project)}
                    </Badge>
                  </div>
                  <CardTitle className="mt-3 break-words text-lg">{projectTitle(project)}</CardTitle>
                  <CardDescription className="line-clamp-3">
                    {readRecordString(project, "description") ?? "—"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <FileText className="h-3.5 w-3.5" />
                      Samples: {sampleCount != null ? sampleCount : "—"}
                    </span>
                    <span>Sessions: {activeSessions != null ? activeSessions : "—"}</span>
                    <span>Reports ready: {reportsReady != null ? reportsReady : "—"}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" />
                      Updated {formatIsoWhenPresent(updated)}
                    </span>
                    {id != null ? (
                      <Button variant="outline" size="sm" asChild>
                        <Link href={href}>Open</Link>
                      </Button>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : null}

      {rawResponse != null ? (
        <div className="min-w-0">
          <DeveloperJsonPanel data={rawResponse} />
        </div>
      ) : null}
    </div>
  )
}
