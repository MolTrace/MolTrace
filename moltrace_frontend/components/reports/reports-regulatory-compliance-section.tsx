"use client"

import Link from "next/link"
import { ShieldCheck } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import {
  asArray,
  findDossierBySpectraCheckSessionId,
  isOpenRegulatoryAction,
  isRecord,
  labelStatus,
} from "@/src/lib/regulatory/regulatory-compliance-helpers"
import type { SavedReportRow } from "@/src/lib/reports/saved-reports"

const DESC =
  "Uses GET /regulatory/dossiers and GET /regulatory/action-items, plus latest-row GETs for status labels when a report session matches dossier spectracheck_session_id. Workflow signals only."

type Props = {
  reportRows: SavedReportRow[]
  /** When false (demo / no sessions), section stays minimal. */
  live: boolean
}

export function ReportsRegulatoryComplianceSection({ reportRows, live }: Props) {
  const sessionNums = useMemo(() => {
    const s = new Set<number>()
    for (const r of reportRows) {
      if (r.sessionNumericId != null && Number.isFinite(r.sessionNumericId)) s.add(r.sessionNumericId)
    }
    return [...s]
  }, [reportRows])

  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState("")
  const [lines, setLines] = useState<
    {
      sessionId: number
      dossierId: number
      title: string
      actionOpen: number
      qnmr: string
      method: string
      aiGov: string
      jurMap: string
    }[]
  >([])

  const load = useCallback(async () => {
    if (!live || sessionNums.length === 0) {
      setLines([])
      return
    }
    setLoading(true)
    setErr("")
    try {
      const dRaw = await apiFetch<unknown>("/regulatory/dossiers?limit=500", { method: "GET" })
      const dossiers = asArray(dRaw).filter(isRecord) as Record<string, unknown>[]
      const out: typeof lines = []

      for (const sn of sessionNums) {
        const d = findDossierBySpectraCheckSessionId(dossiers, sn)
        const did = d ? readRecordNumber(d, "id") : null
        if (d == null || did == null) continue

        const [actRaw, qRaw, mvRaw, agRaw, jmRaw] = await Promise.all([
          apiFetch<unknown>(`/regulatory/action-items?dossier_id=${did}&limit=200`, { method: "GET" }).catch(() => []),
          apiFetch<unknown>(`/regulatory/dossiers/${did}/qnmr-compliance`, { method: "GET" }).catch(() => []),
          apiFetch<unknown>(`/regulatory/dossiers/${did}/method-validation-profile`, { method: "GET" }).catch(() => []),
          apiFetch<unknown>(`/regulatory/dossiers/${did}/ai-governance-record`, { method: "GET" }).catch(() => []),
          apiFetch<unknown>(`/regulatory/dossiers/${did}/jurisdictional-map`, { method: "GET" }).catch(() => []),
        ])

        const actions = asArray(actRaw).filter(isRecord) as Record<string, unknown>[]
        const actionOpen = actions.filter(isOpenRegulatoryAction).length

        const qRows = asArray(qRaw).filter(isRecord) as Record<string, unknown>[]
        const qStatus = qRows[0] ? readRecordString(qRows[0], "validation_status") : undefined
        const mvRows = asArray(mvRaw).filter(isRecord) as Record<string, unknown>[]
        const mvStatus = mvRows[0] ? readRecordString(mvRows[0], "validation_status") : undefined
        const agRows = asArray(agRaw).filter(isRecord) as Record<string, unknown>[]
        const agLatest = agRows[0]
        const agStatus = agLatest ? readRecordString(agLatest, "governance_status") : undefined
        const jmRows = asArray(jmRaw).filter(isRecord) as Record<string, unknown>[]
        const jmLatest = jmRows[0]
        const jmStatus = jmLatest ? readRecordString(jmLatest, "overall_status") : undefined

        out.push({
          sessionId: sn,
          dossierId: did,
          title: readRecordString(d, "title") ?? `dossier ${did}`,
          actionOpen,
          qnmr: qStatus ? labelStatus(qStatus) : "—",
          method: mvStatus ? labelStatus(mvStatus) : "—",
          aiGov: agStatus ? labelStatus(agStatus) : "—",
          jurMap: jmStatus ? labelStatus(jmStatus) : "—",
        })
      }
      setLines(out)
    } catch (e) {
      setErr(formatApiError(e, "Could not load regulatory compliance links."))
      setLines([])
    } finally {
      setLoading(false)
    }
  }, [live, sessionNums])

  useEffect(() => {
    void load()
  }, [load])

  if (!live) {
    return (
      <Card className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Regulatory Compliance Links</CardTitle>
          <CardDescription>{DESC}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Available when live sessions and reports are loaded. Demo mode has no regulatory linkage.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-muted">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Regulatory Compliance Links</CardTitle>
        <CardDescription>{DESC}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {loading ? <p className="text-xs text-muted-foreground">Loading…</p> : null}
        {err ? <p className="text-xs text-destructive">{err}</p> : null}
        {!loading && lines.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <ShieldCheck />
              </EmptyMedia>
              <EmptyTitle>No linked dossiers</EmptyTitle>
              <EmptyDescription>
                None of your listed reports share a session with a regulatory dossier yet. Link a dossier from
                SpectraCheck or create one from a report session when the backend supports it.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}
        {lines.map((row) => (
          <div key={`${row.sessionId}-${row.dossierId}`} className="rounded-md border bg-muted/15 px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link
                href={`/regulatory/dossiers/${row.dossierId}`}
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                {row.title}
              </Link>
              <Badge variant="outline" className="font-mono text-[11px]">
                dossier {row.dossierId} · session {row.sessionId}
              </Badge>
            </div>
            <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">action items (open)</dt>
                <dd className="font-mono tabular-nums">{row.actionOpen}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">qNMR / method validation status</dt>
                <dd>
                  {row.qnmr} · {row.method}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">AI governance status</dt>
                <dd>{row.aiGov}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">jurisdiction map status</dt>
                <dd>{row.jurMap}</dd>
              </div>
            </dl>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
