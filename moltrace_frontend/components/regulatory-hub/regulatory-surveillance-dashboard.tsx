"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  trackRegulatorySurveillanceRunStarted,
  trackRegulatoryWatcherCreated,
} from "@/src/lib/analytics/analytics-client"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import type { LucideIcon } from "lucide-react"
import { Loader2, Eye, FolderOpen, Bell, AlertTriangle, ClipboardList, Activity, Plus } from "lucide-react"

const SURVEILLANCE_WARNING =
  "Regulatory surveillance provides change detection and draft impact assessment. Qualified human review is required."

const WATCHER_SOURCE_TYPES = [
  "fda_guidance",
  "ema_guideline",
  "ich_guideline",
  "usp_chapter",
  "pmda_guidance",
  "health_canada_guidance",
  "internal_sop",
  "company_policy",
  "custom_url",
  "uploaded_document",
  "other",
] as const

const CHECK_FREQUENCIES = ["manual", "daily", "weekly", "monthly", "quarterly"] as const

const WATCHER_STATUSES = ["active", "paused", "archived", "error"] as const

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

type JurisdictionRow = { id: number; name: string }

function parseJurisdictions(raw: unknown): JurisdictionRow[] {
  const rows = asArray(raw).filter(isRecord)
  const out: JurisdictionRow[] = []
  for (const row of rows) {
    const id = readRecordNumber(row, "id")
    const name = readRecordString(row, "name")
    if (id != null && name) out.push({ id, name })
  }
  return out
}

function readIntList(row: Record<string, unknown>, key: string): number[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

function SummaryMetricCard({
  title,
  icon: Icon,
  value,
  sub,
  accent,
}: {
  title: string
  icon: LucideIcon
  value: string
  sub: React.ReactNode
  accent: string
}) {
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: `3px solid ${accent}` }}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</CardTitle>
        <Icon className="h-4 w-4" style={{ color: accent }} aria-hidden />
      </CardHeader>
      <CardContent className="pb-5">
        <div
          className="font-mono text-3xl font-bold tabular-nums leading-none"
          style={{ color: accent }}
        >
          {value}
        </div>
        <div className="mt-2">{sub}</div>
      </CardContent>
    </Card>
  )
}

export function RegulatorySurveillanceDashboard() {
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")

  const [watchers, setWatchers] = useState<Record<string, unknown>[]>([])
  const [changes, setChanges] = useState<Record<string, unknown>[]>([])
  const [notifications, setNotifications] = useState<Record<string, unknown>[]>([])
  const [proposalsProposed, setProposalsProposed] = useState<Record<string, unknown>[]>([])

  const [jurisdictions, setJurisdictions] = useState<JurisdictionRow[]>([])

  const [createTitle, setCreateTitle] = useState("")
  const [createSourceType, setCreateSourceType] = useState<string>("other")
  const [createJurisdictionId, setCreateJurisdictionId] = useState<string>("")
  const [createSourceUrl, setCreateSourceUrl] = useState("")
  const [createFrequency, setCreateFrequency] = useState<string>("manual")
  const [createStatus, setCreateStatus] = useState<string>("active")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [runBusyId, setRunBusyId] = useState<number | null>(null)

  const jurisdictionNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const j of jurisdictions) m.set(j.id, j.name)
    return m
  }, [jurisdictions])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const [jRaw, wRaw, cRaw, nRaw, pRaw] = await Promise.all([
        apiFetch<unknown>("/regulatory/jurisdictions", { method: "GET" }).catch(() => []),
        apiFetch<unknown>("/regulatory/surveillance/sources?limit=500", { method: "GET" }),
        apiFetch<unknown>("/regulatory/changes?limit=500", { method: "GET" }),
        apiFetch<unknown>("/regulatory/notifications?limit=200", { method: "GET" }),
        apiFetch<unknown>("/regulatory/rule-update-proposals?limit=500&status=proposed", { method: "GET" }).catch(() => []),
      ])
      setJurisdictions(parseJurisdictions(jRaw))
      setWatchers(asArray(wRaw).filter(isRecord) as Record<string, unknown>[])
      setChanges(asArray(cRaw).filter(isRecord) as Record<string, unknown>[])
      setNotifications(asArray(nRaw).filter(isRecord) as Record<string, unknown>[])
      setProposalsProposed(asArray(pRaw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setLoadErr(formatApiError(e, "Could not load surveillance data."))
      setWatchers([])
      setChanges([])
      setNotifications([])
      setProposalsProposed([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const summary = useMemo(() => {
    const watched = watchers.length
    const changesDetected = changes.filter((r) => readRecordString(r, "change_type") !== "no_change").length
    const highImpact = changes.filter((r) => {
      const s = readRecordString(r, "severity")
      return s === "high" || s === "critical"
    }).length
    const proposals = proposalsProposed.length
    const dossierIds = new Set<number>()
    for (const r of changes) {
      for (const id of readIntList(r, "affected_dossier_ids_json")) {
        dossierIds.add(id)
      }
    }
    return {
      watched,
      changesDetected,
      highImpact,
      proposals,
      dossiersAffected: dossierIds.size,
    }
  }, [watchers, changes, proposalsProposed])

  async function addWatcher() {
    const title = createTitle.trim()
    if (!title) {
      setCreateErr("title is required.")
      return
    }
    setCreateBusy(true)
    setCreateErr("")
    try {
      const body: Record<string, unknown> = {
        title,
        source_type: createSourceType,
        check_frequency: createFrequency,
        status: createStatus,
        metadata_json: {},
      }
      let jurisdictionForAnalytics: number | null = null
      const ju = createJurisdictionId.trim()
      if (ju && ju !== "__none__") {
        const n = Number.parseInt(ju, 10)
        if (Number.isFinite(n) && n >= 1) {
          body.jurisdiction_id = n
          jurisdictionForAnalytics = n
        }
      }
      const url = createSourceUrl.trim()
      if (url) body.source_url = url
      const created = await apiFetch<unknown>("/regulatory/surveillance/sources", { method: "POST", body })
      const rec = isRecord(created) ? created : null
      const newWatcherId = rec ? readRecordNumber(rec, "id") : null
      trackRegulatoryWatcherCreated({
        watcher_id: newWatcherId ?? undefined,
        source_type: createSourceType,
        jurisdiction_id: jurisdictionForAnalytics,
      })
      setCreateTitle("")
      setCreateSourceUrl("")
      setCreateJurisdictionId("")
      setCreateSourceType("other")
      setCreateFrequency("manual")
      setCreateStatus("active")
      await load()
    } catch (e) {
      setCreateErr(formatApiError(e, "Create watcher failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function runSurveillanceCheck(row: Record<string, unknown>) {
    const watcherId = readRecordNumber(row, "id")
    if (watcherId == null) return
    setRunBusyId(watcherId)
    try {
      await apiFetch("/regulatory/surveillance/runs", {
        method: "POST",
        body: { watcher_id: watcherId, run_type: "manual", metadata_json: {} },
      })
      trackRegulatorySurveillanceRunStarted({
        watcher_id: watcherId,
        source_type: readRecordString(row, "source_type"),
        jurisdiction_id: readRecordNumber(row, "jurisdiction_id") ?? null,
      })
      await load()
    } catch (e) {
      setLoadErr(formatApiError(e, "Surveillance run failed."))
    } finally {
      setRunBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-8 p-4 md:p-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-cyan-ink)" }}
        >
          Regulatory · Surveillance
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Regulatory Surveillance</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Track regulatory source versions, detect changes, and assess impact on dossiers, rules, action items, and reports.
        </p>
      </div>

      <AlertCard variant="warning" title="Not legal advice" description={SURVEILLANCE_WARNING} />

      {loadErr ? <AlertCard variant="error" title="Error" description={loadErr} /> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <SummaryMetricCard
          title="Watched sources"
          icon={Eye}
          value={loading ? "—" : String(summary.watched)}
          sub={<p className="text-xs text-muted-foreground">Regulatory sources under active surveillance</p>}
          accent="var(--mt-cyan)"
        />
        <SummaryMetricCard
          title="Changes detected"
          icon={Activity}
          value={loading ? "—" : String(summary.changesDetected)}
          sub={<p className="text-xs text-muted-foreground">Excludes change_type no_change</p>}
          accent="var(--mt-cyan)"
        />
        <SummaryMetricCard
          title="High-impact changes"
          icon={AlertTriangle}
          value={loading ? "—" : String(summary.highImpact)}
          sub={<p className="text-xs text-muted-foreground">severity high or critical</p>}
          accent="var(--mt-amber)"
        />
        <SummaryMetricCard
          title="Rule update proposals"
          icon={ClipboardList}
          value={loading ? "—" : String(summary.proposals)}
          sub={<p className="text-xs text-muted-foreground">status proposed</p>}
          accent="var(--mt-violet)"
        />
        <SummaryMetricCard
          title="Dossiers affected"
          icon={FolderOpen}
          value={loading ? "—" : String(summary.dossiersAffected)}
          sub={<p className="text-xs text-muted-foreground">Union of affected_dossier_ids_json</p>}
          accent="var(--mt-cyan)"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/sources">Open source library</Link>
        </Button>
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/rule-updates">Open rule update proposals</Link>
        </Button>
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/action-queue">Open action queue</Link>
        </Button>
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="Watchlist"
        title="Source watchlist"
        icon={Eye}
        description="Regulatory guidance documents and agency publications under active automated surveillance."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>title</TableHead>
                  <TableHead>source type</TableHead>
                  <TableHead>jurisdiction</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>check frequency</TableHead>
                  <TableHead>last checked</TableHead>
                  <TableHead>last change detected</TableHead>
                  <TableHead className="w-[100px]">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {watchers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-sm text-muted-foreground">
                      No watched sources yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  watchers.map((row, widx) => {
                    const id = readRecordNumber(row, "id")
                    const jid = readRecordNumber(row, "jurisdiction_id")
                    const sourceUrl = readRecordString(row, "source_url")
                    const lastChecked = readRecordString(row, "last_checked_at")
                    const lastChange = readRecordString(row, "last_change_detected_at")
                    return (
                      <TableRow key={id != null ? `w-${id}` : `w-idx-${widx}`}>
                        <TableCell className="max-w-[200px] font-medium">{readRecordString(row, "title") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "source_type") ?? "—"}</TableCell>
                        <TableCell className="text-xs">
                          {jid != null ? jurisdictionNameById.get(jid) ?? `id ${jid}` : "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "check_frequency") ?? "—"}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatWhen(lastChecked)}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatWhen(lastChange)}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-1">
                            {sourceUrl ? (
                              <Button variant="outline" size="sm" className="h-8" asChild>
                                <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                                  Open
                                </a>
                              </Button>
                            ) : (
                              <Button variant="outline" size="sm" className="h-8" asChild>
                                <Link href="/regulatory/sources">Open</Link>
                              </Button>
                            )}
                            {id != null ? (
                              <Button
                                type="button"
                                variant="secondary"
                                size="sm"
                                className="h-8"
                                disabled={loading || runBusyId === id}
                                onClick={() => void runSurveillanceCheck(row)}
                              >
                                {runBusyId === id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                                ) : null}
                                Run check
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="cyan"
        eyebrow="Create"
        title="Add source watcher"
        icon={Plus}
        description="Register a new regulatory source for automated surveillance — agency guidance, pharmacopoeial standards, or jurisdiction-specific publications."
      >
        <div className="space-y-4">
          {createErr ? <AlertCard variant="error" title="Create error" description={createErr} /> : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="rw-title">title</Label>
              <Input
                id="rw-title"
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                placeholder="Watcher label"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label>source type</Label>
              <Select value={createSourceType} onValueChange={setCreateSourceType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WATCHER_SOURCE_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>jurisdiction optional</Label>
              <Select value={createJurisdictionId || "__none__"} onValueChange={(v) => setCreateJurisdictionId(v === "__none__" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None</SelectItem>
                  {jurisdictions.map((j) => (
                    <SelectItem key={j.id} value={String(j.id)}>
                      {j.name} ({j.id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="rw-url">source_url optional</Label>
              <Input
                id="rw-url"
                value={createSourceUrl}
                onChange={(e) => setCreateSourceUrl(e.target.value)}
                placeholder="https://…"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label>check frequency</Label>
              <Select value={createFrequency} onValueChange={setCreateFrequency}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CHECK_FREQUENCIES.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>status</Label>
              <Select value={createStatus} onValueChange={setCreateStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WATCHER_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button type="button" disabled={createBusy} onClick={() => void addWatcher()}>
            {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Add watched source
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="cyan"
        eyebrow="Changes"
        title="Recent changes"
        icon={Activity}
        description="Recently detected regulatory changes across all watched sources — sorted by severity and detection date."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>id</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>change_type</TableHead>
                  <TableHead>severity</TableHead>
                  <TableHead>review_status</TableHead>
                  <TableHead>affected dossiers</TableHead>
                  <TableHead>created_at</TableHead>
                  <TableHead className="w-[90px]">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {changes.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-sm text-muted-foreground">
                      No change events yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  changes.slice(0, 50).map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const dossierCount = readIntList(row, "affected_dossier_ids_json").length
                    return (
                      <TableRow key={id != null ? `ch-${id}` : `ch-idx-${idx}`}>
                        <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                        <TableCell className="max-w-[240px] text-sm">{readRecordString(row, "title") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "change_type") ?? "—"}</TableCell>
                        <TableCell>{readRecordString(row, "severity") ?? "—"}</TableCell>
                        <TableCell>{readRecordString(row, "review_status") ?? "—"}</TableCell>
                        <TableCell className="tabular-nums">{dossierCount}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatWhen(readRecordString(row, "created_at"))}
                        </TableCell>
                        <TableCell>
                          {id != null ? (
                            <Button variant="outline" size="sm" className="h-8" asChild>
                              <Link href={`/regulatory/changes/${id}`}>Open</Link>
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
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="cyan"
        eyebrow="Alerts"
        title="Notifications"
        icon={Bell}
        description="Workflow signals for detected regulatory changes — not legal conclusions. Review each notification and act through the appropriate dossier workflow."
      >
        <div className="space-y-3">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : notifications.length === 0 ? (
            <p className="text-sm text-muted-foreground">No notifications.</p>
          ) : (
            <ul className="space-y-2">
              {notifications.slice(0, 25).map((row, idx) => {
                const id = readRecordNumber(row, "id")
                const did = readRecordNumber(row, "dossier_id")
                const cid = readRecordNumber(row, "change_event_id")
                return (
                  <li
                    key={id != null ? `n-${id}` : `n-idx-${idx}`}
                    className="flex flex-col gap-1 rounded-md border bg-muted/15 px-3 py-2 text-sm sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="font-medium">{readRecordString(row, "title") ?? "—"}</p>
                      <p className="text-xs text-muted-foreground line-clamp-2">{readRecordString(row, "message") ?? ""}</p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <Badge variant="outline">{readRecordString(row, "severity") ?? "—"}</Badge>
                      <Badge variant="secondary">{readRecordString(row, "status") ?? "—"}</Badge>
                      {did != null ? (
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" asChild>
                          <Link href={`/regulatory/dossiers/${did}`}>dossier {did}</Link>
                        </Button>
                      ) : null}
                      {cid != null ? (
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" asChild>
                          <Link href={`/regulatory/changes/${cid}`}>change {cid}</Link>
                        </Button>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </ModuleCard>

      <p className="text-xs text-muted-foreground">
        Surveillance outputs are operational signals from your tenant API — not legal conclusions or agency positions.
      </p>
    </div>
  )
}
