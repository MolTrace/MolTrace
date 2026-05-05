"use client"

import { useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  formatIsoWhenPresent,
  readRecordString,
} from "@/components/projects/project-workspace-utils"
import { fetchSpectraCheckSessionWorkflowRuns } from "@/src/lib/spectracheck/spectracheck-backend-session"
import { normalizeWorkflowRunsList } from "@/src/lib/dashboard/overview-metrics"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function extractSpectraCheckSessionId(row: unknown): string | null {
  if (typeof row === "string" && row.trim()) return row.trim()
  if (!isRecord(row)) return null
  return (
    readRecordString(row, "id") ?? readRecordString(row, "session_id") ?? readRecordString(row, "sessionId")
  )?.trim() || null
}

function runStatus(r: Record<string, unknown>): string {
  const raw =
    readRecordString(r, "status") ??
    readRecordString(r, "workflow_status") ??
    readRecordString(r, "state") ??
    ""
  return raw.trim().toLowerCase() || "—"
}

function runId(r: Record<string, unknown>): string {
  return (
    readRecordString(r, "workflow_run_id") ??
    readRecordString(r, "workflowRunId") ??
    readRecordString(r, "id") ??
    "—"
  )
}

function updatedAt(r: Record<string, unknown>): string | undefined {
  return (
    readRecordString(r, "updated_at") ??
    readRecordString(r, "modified_at") ??
    readRecordString(r, "created_at")
  )
}

export type SessionWorkflowRunsSectionProps = {
  /** SpectraCheck session ids from project/sample payloads */
  sessionIds: string[]
}

export function SessionWorkflowRunsSection({ sessionIds }: SessionWorkflowRunsSectionProps) {
  const dedupedIds = useMemo(() => [...new Set(sessionIds.filter((id) => id.trim()))], [sessionIds])

  const [loading, setLoading] = useState(false)
  const [failedFetch, setFailedFetch] = useState(false)
  const [rows, setRows] = useState<{ sessionId: string; runs: Record<string, unknown>[] }[]>([])

  const key = dedupedIds.join("\0")

  useEffect(() => {
    if (dedupedIds.length === 0) {
      setRows([])
      setFailedFetch(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setFailedFetch(false)
    void (async () => {
      const out: { sessionId: string; runs: Record<string, unknown>[] }[] = []
      let anyFailed = false
      for (const sid of dedupedIds) {
        try {
          const data = await fetchSpectraCheckSessionWorkflowRuns(sid)
          if (cancelled) return
          out.push({ sessionId: sid, runs: normalizeWorkflowRunsList(data) })
        } catch {
          anyFailed = true
          if (cancelled) return
          out.push({ sessionId: sid, runs: [] })
        }
      }
      if (!cancelled) {
        setRows(out)
        setFailedFetch(anyFailed)
        setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [key])

  const flatRuns = useMemo(() => {
    const acc: { sessionId: string; run: Record<string, unknown> }[] = []
    for (const { sessionId, runs } of rows) {
      for (const run of runs) {
        acc.push({ sessionId, run })
      }
    }
    return acc
  }, [rows])

  if (dedupedIds.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Workflow runs</CardTitle>
        <CardDescription>
          From <code className="text-xs">GET /spectracheck/sessions/{"{session_id}"}/workflow-runs</code> when the API
          returns session ids.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? <p className="text-sm text-muted-foreground">Loading workflow runs…</p> : null}
        {failedFetch ? (
          <p className="text-xs text-muted-foreground">One or more session workflow lists could not be loaded.</p>
        ) : null}
        {flatRuns.length === 0 && !loading ? (
          <p className="text-sm text-muted-foreground">No workflow runs returned for linked sessions.</p>
        ) : null}
        {flatRuns.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="whitespace-nowrap">Session</TableHead>
                  <TableHead className="whitespace-nowrap">Run</TableHead>
                  <TableHead className="whitespace-nowrap">Status</TableHead>
                  <TableHead className="whitespace-nowrap">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flatRuns.map(({ sessionId, run }, i) => (
                  <TableRow key={`${sessionId}-${runId(run)}-${i}`}>
                    <TableCell className="max-w-[10rem] truncate font-mono text-xs">{sessionId}</TableCell>
                    <TableCell className="max-w-[12rem] truncate font-mono text-xs">{runId(run)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] font-normal">
                        {runStatus(run)}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatIsoWhenPresent(updatedAt(run))}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
