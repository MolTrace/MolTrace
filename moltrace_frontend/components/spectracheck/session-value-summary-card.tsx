"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { fetchSessionRoiSnapshot } from "@/src/lib/dashboard/scoped-roi-snapshot"
import type { RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"

function fmtMinutes(n: number | null | undefined, loading: boolean): string {
  if (loading) return "…"
  if (n == null) return "—"
  const rounded = Math.round(n * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

function fmtInt(n: number | null | undefined, loading: boolean): string {
  if (loading) return "…"
  if (n == null) return "—"
  return String(Math.round(n))
}

function fmtEvidence(n: number | null | undefined, loading: boolean): string {
  if (loading) return "…"
  if (n == null) return "—"
  return String(Math.round(n))
}

export function SessionValueSummaryCard({ sessionId }: { sessionId: string | null }) {
  const [loading, setLoading] = useState(false)
  const [snap, setSnap] = useState<RoiSnapshotData | null>(null)

  const sid = sessionId?.trim() ?? ""

  useEffect(() => {
    if (!sid) {
      setSnap(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    void fetchSessionRoiSnapshot(sid).then((s) => {
      if (cancelled) return
      setSnap(s)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [sid])

  if (!sid) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Session Value Summary</CardTitle>
          <CardDescription>
            Tasks automated, time saved, and reports produced for this session.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Save or load a session to track session-level value.</p>
        </CardContent>
      </Card>
    )
  }

  const live = snap != null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Session Value Summary</CardTitle>
        <CardDescription>
          Session-level automation and value metrics for the active analysis session.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <p className="text-xs text-muted-foreground">tasks automated in this session</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.tasks_automated, loading)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">estimated minutes saved</p>
            <p className="text-2xl font-bold tabular-nums">
              {fmtMinutes(live ? snap?.total_minutes_saved : null, loading)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">reports generated</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.reports_generated, loading)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">evidence items generated</p>
            <p className="text-2xl font-bold tabular-nums">{fmtEvidence(snap?.evidence_items_generated, loading)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">workflows completed</p>
            <p className="text-2xl font-bold tabular-nums">{fmtInt(snap?.workflows_completed, loading)}</p>
          </div>
        </div>
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading session ROI…</p>
        ) : !live ? (
          <p className="text-xs text-muted-foreground">
            Session ROI snapshot unavailable — administrator access may be required, or the backend did not return data.
          </p>
        ) : snap.evidence_items_generated == null ? (
          <p className="text-xs text-muted-foreground">
            Evidence item counts appear when provided in snapshot metadata (evidence_items_generated).
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
