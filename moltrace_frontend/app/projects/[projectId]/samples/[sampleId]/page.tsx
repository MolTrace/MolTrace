"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { apiFetch, ApiError } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
  SessionWorkflowRunsSection,
  extractSpectraCheckSessionId,
} from "@/components/projects/session-workflow-runs-section"
import { formatIsoWhenPresent, projectsErrorMessage, readRecordString } from "@/components/projects/project-workspace-utils"
import { ArrowLeft, ServerOff } from "lucide-react"

function pickSessions(sample: unknown): unknown[] {
  if (!sample || typeof sample !== "object") return []
  const o = sample as Record<string, unknown>
  const keys = ["spectracheck_sessions", "sessions", "recent_sessions"] as const
  for (const k of keys) {
    const v = o[k]
    if (Array.isArray(v)) return v
  }
  return []
}

export default function ProjectSampleDetailPage() {
  const params = useParams()
  const projectId = typeof params.projectId === "string" ? params.projectId : ""
  const sampleId = typeof params.sampleId === "string" ? params.sampleId : ""

  const [sample, setSample] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [unavailable, setUnavailable] = useState(false)

  const load = useCallback(async () => {
    if (!sampleId) return
    setLoading(true)
    setError("")
    setUnavailable(false)
    setSample(null)
    try {
      const data = await apiFetch<unknown>(`/samples/${encodeURIComponent(sampleId)}`, { method: "GET" })
      setSample(data)
    } catch (err) {
      setError(projectsErrorMessage(err, "Could not load sample."))
      if (err instanceof ApiError && (err.status >= 502 || err.status === 0)) {
        setUnavailable(true)
      }
    } finally {
      setLoading(false)
    }
  }, [sampleId])

  useEffect(() => {
    void load()
  }, [load])

  const headerTitle = useMemo(() => {
    if (!sample || typeof sample !== "object") return "Sample"
    const label =
      readRecordString(sample, "sample_id") ??
      readRecordString(sample, "name") ??
      readRecordString(sample, "title")
    return label?.trim() ? `Sample ${label}` : "Sample"
  }, [sample])

  const sampleIdDisplay =
    sample && typeof sample === "object"
      ? readRecordString(sample, "sample_id") ?? readRecordString(sample, "sample_id".replace("_", ""))
      : undefined
  const solventDisplay =
    sample && typeof sample === "object" ? readRecordString(sample, "solvent") ?? "—" : "—"
  const statusDisplay =
    sample && typeof sample === "object" ? readRecordString(sample, "status") ?? "—" : "—"
  const notesDisplay =
    sample && typeof sample === "object"
      ? readRecordString(sample, "notes") ?? readRecordString(sample, "note") ?? "—"
      : "—"

  const sessionRows = pickSessions(sample)

  const sessionIdsForWorkflows = useMemo(() => {
    const ids: string[] = []
    for (const row of sessionRows) {
      const sid = extractSpectraCheckSessionId(row)
      if (sid) ids.push(sid)
    }
    return ids
  }, [sessionRows])

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/projects/${encodeURIComponent(projectId)}`} className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Project
          </Link>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/projects">All projects</Link>
        </Button>
      </div>

      {unavailable && (
        <Card className="border-warning/40 bg-warning/10">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base text-warning">
              <ServerOff className="h-4 w-4" />
              Backend unavailable
            </CardTitle>
            <CardDescription className="text-warning/90">
              We couldn&apos;t load this sample. Try refreshing in a moment, or contact your administrator if this keeps happening.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <CardTitle className="break-words text-2xl">{headerTitle}</CardTitle>
            <CardDescription>Route sample id: {sampleId || "—"}</CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Badge variant="secondary">{statusDisplay}</Badge>
            <Button asChild>
              <Link
                href={`/spectracheck?projectId=${encodeURIComponent(projectId)}&sampleId=${encodeURIComponent(sampleId)}`}
              >
                Open SpectraCheck
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link
                href={`/spectracheck?projectId=${encodeURIComponent(projectId)}&sampleId=${encodeURIComponent(sampleId)}&newSession=1`}
              >
                New SpectraCheck Session
              </Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Sample ID</p>
            <p className="break-all font-mono text-xs">{sampleIdDisplay ?? sampleId ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Solvent</p>
            <p>{solventDisplay}</p>
          </div>
          <div className="sm:col-span-2">
            <p className="text-xs font-medium text-muted-foreground">Notes</p>
            <p className="whitespace-pre-wrap break-words">{notesDisplay}</p>
          </div>
        </CardContent>
      </Card>

      {error && !loading ? (
        <Card className="border-destructive/40 bg-destructive/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-destructive">Request failed</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Loading sample…</p> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Sessions</CardTitle>
          <CardDescription>
            SpectraCheck sessions linked to this sample when returned by the API (e.g. <code className="text-xs">sessions</code>{" "}
            array).
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {sessionRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No session rows in the sample response. Save workflows may still use SpectraCheck in this browser.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead className="whitespace-nowrap">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessionRows.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell className="max-w-prose font-mono text-xs">
                      <pre className="whitespace-pre-wrap break-words">{JSON.stringify(row, null, 2)}</pre>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatIsoWhenPresent(
                        readRecordString(row, "updated_at") ?? readRecordString(row, "updatedAt"),
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <SessionWorkflowRunsSection sessionIds={sessionIdsForWorkflows} />

      {sample != null ? (
        <div className="min-w-0">
          <DeveloperJsonPanel data={sample} />
        </div>
      ) : null}
    </div>
  )
}
