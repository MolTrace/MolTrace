"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { fetchProjectRoiSnapshot } from "@/src/lib/dashboard/scoped-roi-snapshot"
import type { RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"

function fmtHours(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 })
}

function fmtInt(n: number | null | undefined, loading: boolean): string {
  if (loading) return "…"
  if (n == null) return "—"
  return String(Math.round(n))
}

export function ProjectValueSummaryCard({ projectId }: { projectId: string }) {
  const [loading, setLoading] = useState(true)
  const [snap, setSnap] = useState<RoiSnapshotData | null>(null)

  useEffect(() => {
    let cancelled = false
    const id = projectId.trim()
    if (!id) {
      setLoading(false)
      setSnap(null)
      return
    }
    setLoading(true)
    void fetchProjectRoiSnapshot(id).then((s) => {
      if (cancelled) return
      setSnap(s)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const live = snap != null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Project Value Summary</CardTitle>
        <CardDescription>
          <code className="text-xs">GET /analytics/projects/{"{project_id}"}/roi</code>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <p className="text-xs text-muted-foreground">hours saved</p>
            <p className="text-2xl font-bold tabular-nums">
              {loading ? "…" : live ? fmtHours(snap.total_hours_saved) : "—"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">tasks automated</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.tasks_automated, loading)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">reports generated</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.reports_generated, loading)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">workflows completed</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.workflows_completed, loading)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">analyses completed</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.analyses_completed, loading)}</p>
          </div>
        </div>
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading project ROI…</p>
        ) : !live ? (
          <p className="text-xs text-muted-foreground">
            Project ROI snapshot unavailable — administrator access may be required, or the backend did not return data.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
