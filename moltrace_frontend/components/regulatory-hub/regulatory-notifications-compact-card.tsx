"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Bell, Loader2 } from "lucide-react"

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

type RegulatoryNotificationsCompactCardProps = {
  /** When set, lists notifications filtered to this dossier only. */
  dossierId?: number
}

export function RegulatoryNotificationsCompactCard({ dossierId }: RegulatoryNotificationsCompactCardProps) {
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [rows, setRows] = useState<Record<string, unknown>[]>([])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setErr("")
      try {
        const q =
          dossierId != null && Number.isFinite(dossierId) && dossierId >= 1
            ? `?limit=50&dossier_id=${dossierId}`
            : "?limit=50"
        const raw = await apiFetch<unknown>(`/regulatory/notifications${q}`, { method: "GET" })
        if (!cancelled) setRows(asArray(raw).filter(isRecord) as Record<string, unknown>[])
      } catch (e) {
        if (!cancelled) {
          setErr(formatApiError(e, "Notifications unavailable."))
          setRows([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [dossierId])

  const unreadCount = useMemo(
    () => rows.filter((r) => readRecordString(r, "status") === "unread").length,
    [rows]
  )

  const preview = rows.slice(0, 2)

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-muted-foreground" aria-hidden />
            <CardTitle className="text-base">Regulatory notifications</CardTitle>
          </div>
          {!loading && !err ? (
            <Badge variant={unreadCount > 0 ? "default" : "secondary"}>{unreadCount} unread</Badge>
          ) : null}
        </div>
        <CardDescription>
          Regulatory workflow signals — change alerts, dossier updates, and review triggers. Not legal conclusions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {loading ? (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Loading…
          </p>
        ) : err ? (
          <p className="text-xs text-muted-foreground">{err}</p>
        ) : preview.length === 0 ? (
          <p className="text-xs text-muted-foreground">No notifications in this scope.</p>
        ) : (
          <ul className="space-y-2">
            {preview.map((row, idx) => {
              const id = readRecordNumber(row, "id")
              return (
                <li key={id != null ? `cn-${id}` : `cn-${idx}`} className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{readRecordString(row, "title") ?? "—"}</span>
                  {readRecordString(row, "severity") ? (
                    <Badge variant="outline" className="ml-2 align-middle text-[10px]">
                      {readRecordString(row, "severity")}
                    </Badge>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
        <p>
          <Link className="text-sm font-medium text-primary underline-offset-4 hover:underline" href="/regulatory/notifications">
            Open notifications
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}
