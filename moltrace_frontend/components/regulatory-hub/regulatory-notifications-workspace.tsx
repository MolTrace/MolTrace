"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { trackRegulatoryNotificationResolved } from "@/src/lib/analytics/analytics-client"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AlertTriangle, ArrowLeft, Bell, Loader2 } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function formatWhen(iso: string | undefined): string {
  return formatStableUtcDateTime(iso)
}

export function RegulatoryNotificationsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [patchBusyId, setPatchBusyId] = useState<number | null>(null)
  const [patchErr, setPatchErr] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const raw = await apiFetch<unknown>("/regulatory/notifications?limit=500", { method: "GET" })
      setRows(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setLoadErr(formatApiError(e, "Could not load notifications."))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function patchStatus(
    id: number,
    status: "read" | "dismissed" | "resolved",
    analytics?: { severity?: string },
  ) {
    setPatchErr("")
    setPatchBusyId(id)
    try {
      await apiFetch(`/regulatory/notifications/${id}`, {
        method: "PATCH",
        body: { status },
      })
      if (status === "resolved") {
        trackRegulatoryNotificationResolved({
          severity: analytics?.severity,
          status: "resolved",
        })
      }
      await load()
    } catch (e) {
      setPatchErr(formatApiError(e, "Update failed."))
    } finally {
      setPatchBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/spectracheck?program=regulatory_hub">
            <ArrowLeft className="mr-2 h-4 w-4" />
            ComplianceCore
          </Link>
        </Button>
      </div>

      <header className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-cyan)" }}
        >
          Regulatory · Notifications
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Regulatory Notifications</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Operational signals from your tenant API — not final legal determinations.
        </p>
      </header>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle>Decision support only</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Notifications summarize surveillance and impact workflow state. They are not legal advice or agency
          conclusions.
        </AlertDescription>
      </Alert>

      <ModuleCard
        accent="cyan"
        eyebrow="Signals"
        title="Notifications"
        icon={Bell}
        description="Regulatory workflow signals — change alerts, dossier updates, and review triggers. Mark notifications as read after review."
      >
        <div className="space-y-4">
          {patchErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{patchErr}</AlertDescription>
            </Alert>
          ) : null}
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading…
            </p>
          ) : loadErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{loadErr}</AlertDescription>
            </Alert>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No notifications returned.</p>
          ) : (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>severity</TableHead>
                    <TableHead>title</TableHead>
                    <TableHead>message</TableHead>
                    <TableHead>linked change</TableHead>
                    <TableHead>linked dossier / action item</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>created date</TableHead>
                    <TableHead className="min-w-[200px]">actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const busy = id != null && patchBusyId === id
                    const st = readRecordString(row, "status") ?? ""
                    const cid = readRecordNumber(row, "change_event_id")
                    const did = readRecordNumber(row, "dossier_id")
                    const aid = readRecordNumber(row, "action_item_id")
                    return (
                      <TableRow key={id != null ? `n-${id}` : `idx-${idx}`}>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "severity") ?? "—"}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[180px] text-sm font-medium">
                          {readRecordString(row, "title") ?? "—"}
                        </TableCell>
                        <TableCell className="max-w-[260px] text-xs text-muted-foreground">
                          <span className="line-clamp-3">{readRecordString(row, "message") ?? "—"}</span>
                        </TableCell>
                        <TableCell className="text-xs">
                          {cid != null ? (
                            <Button variant="outline" size="sm" className="h-8" asChild>
                              <Link href={`/regulatory/changes/${cid}`}>change {cid}</Link>
                            </Button>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="space-y-1 text-xs">
                          {did != null ? (
                            <div>
                              <Button variant="ghost" size="sm" className="h-7 px-2" asChild>
                                <Link href={`/regulatory/dossiers/${did}`}>dossier {did}</Link>
                              </Button>
                            </div>
                          ) : null}
                          {aid != null ? (
                            <div>
                              <Button variant="ghost" size="sm" className="h-7 px-2" asChild>
                                <Link href="/regulatory/action-queue">action_item {aid}</Link>
                              </Button>
                            </div>
                          ) : null}
                          {did == null && aid == null ? "—" : null}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{st || "—"}</Badge>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatWhen(readRecordString(row, "created_at") ?? undefined)}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8"
                              disabled={busy || st === "read" || st === "dismissed" || st === "resolved"}
                              onClick={() => id != null && void patchStatus(id, "read")}
                            >
                              mark read
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8"
                              disabled={busy || st === "dismissed" || st === "resolved"}
                              onClick={() => id != null && void patchStatus(id, "dismissed")}
                            >
                              dismiss
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8"
                              disabled={busy || st === "resolved"}
                              onClick={() =>
                                id != null &&
                                void patchStatus(id, "resolved", { severity: readRecordString(row, "severity") })
                              }
                            >
                              resolve
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </ModuleCard>
    </div>
  )
}
