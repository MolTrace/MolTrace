"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ChevronDown, ServerOff } from "lucide-react"

const SECURITY_EVENTS_TOOLTIP =
  "Security events record authentication, permission, sharing, admin, and suspicious activity signals."

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

const SENSITIVE_KEY = /token|secret|password|api_key|authorization|credential/i

function redactDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactDeep)
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const o = value as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(o)) {
      if (SENSITIVE_KEY.test(k)) {
        out[k] = "[redacted]"
      } else {
        out[k] = redactDeep(v)
      }
    }
    return out
  }
  return value
}

function severityBadgeClass(sev: string): string {
  const s = sev.toLowerCase()
  if (s === "critical") return "border-destructive/50 text-destructive"
  if (s === "error") return "border-destructive/50 text-destructive"
  if (s === "warning") return "border-warning/50 text-warning"
  if (s === "info") return "border-muted-foreground/50 text-muted-foreground"
  return "text-muted-foreground"
}

function parseEventTime(iso: string): number {
  const t = Date.parse(iso)
  return Number.isNaN(t) ? NaN : t
}

function filterEventsClientSide(
  rows: Record<string, unknown>[],
  opts: {
    dateFrom: string
    dateTo: string
    resourceType: string
  },
): Record<string, unknown>[] {
  let out = rows
  const df = opts.dateFrom.trim()
  const dt = opts.dateTo.trim()
  if (df) {
    const start = Date.parse(`${df}T00:00:00.000Z`)
    if (!Number.isNaN(start)) {
      out = out.filter((r) => {
        const ts = parseEventTime(readStr(r, ["created_at"]))
        return !Number.isNaN(ts) && ts >= start
      })
    }
  }
  if (dt) {
    const end = Date.parse(`${dt}T23:59:59.999Z`)
    if (!Number.isNaN(end)) {
      out = out.filter((r) => {
        const ts = parseEventTime(readStr(r, ["created_at"]))
        return !Number.isNaN(ts) && ts <= end
      })
    }
  }
  const rt = opts.resourceType.trim().toLowerCase()
  if (rt) {
    out = out.filter((r) => {
      const v = readStr(r, ["resource_type"]).toLowerCase()
      return v.includes(rt)
    })
  }
  return out
}

export function SecurityEventsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null)
  const [eventsRaw, setEventsRaw] = useState<Record<string, unknown>[]>([])
  const [errSummary, setErrSummary] = useState("")
  const [errEvents, setErrEvents] = useState("")

  const [filterSeverity, setFilterSeverity] = useState("")
  const [filterEventType, setFilterEventType] = useState("")
  const [filterActorEmail, setFilterActorEmail] = useState("")
  const [filterDateFrom, setFilterDateFrom] = useState("")
  const [filterDateTo, setFilterDateTo] = useState("")
  const [filterResourceType, setFilterResourceType] = useState("")
  const [filterLimit, setFilterLimit] = useState("100")

  const filtersRef = useRef({
    filterSeverity,
    filterEventType,
    filterActorEmail,
    filterLimit,
  })
  filtersRef.current = {
    filterSeverity,
    filterEventType,
    filterActorEmail,
    filterLimit,
  }

  const load = useCallback(async () => {
    setLoading(true)
    setErrSummary("")
    setErrEvents("")

    try {
      const s = await apiFetch<Record<string, unknown>>("/security/summary", { method: "GET" })
      setSummary(s ?? null)
    } catch (e) {
      setErrSummary(formatErr(e, "Could not load /security/summary."))
      setSummary(null)
    }

    const f = filtersRef.current
    const params = new URLSearchParams()
    const lim = Math.min(500, Math.max(1, Math.floor(Number(f.filterLimit) || 100)))
    params.set("limit", String(lim))
    const sev = f.filterSeverity.trim()
    const et = f.filterEventType.trim()
    const ac = f.filterActorEmail.trim()
    if (sev) params.set("severity", sev)
    if (et) params.set("event_type", et)
    if (ac) params.set("actor_email", ac)

    try {
      const path = `/security/events?${params.toString()}`
      const data = await apiFetch<unknown>(path, { method: "GET" })
      const list = Array.isArray(data) ? data : []
      setEventsRaw(list.filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setErrEvents(formatErr(e, "Could not load /security/events."))
      setEventsRaw([])
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const eventsDisplayed = useMemo(
    () =>
      filterEventsClientSide(eventsRaw, {
        dateFrom: filterDateFrom,
        dateTo: filterDateTo,
        resourceType: filterResourceType,
      }),
    [eventsRaw, filterDateFrom, filterDateTo, filterResourceType],
  )

  const developerBundle = useMemo(() => {
    const safeSummary = summary ? (redactDeep(summary) as Record<string, unknown>) : null
    const safeEvents = eventsDisplayed.map((ev) => {
      const copy = { ...ev }
      if (isRecord(copy.metadata_json)) {
        copy.metadata_json = redactDeep(copy.metadata_json) as Record<string, unknown>
      }
      return copy
    })
    return { summary: safeSummary, events: safeEvents }
  }, [summary, eventsDisplayed])

  const backendUnreachable = !loading && errSummary && errEvents

  const totalEvents =
    summary && typeof summary.total_events === "number" ? summary.total_events : null
  const openWarnings =
    summary && typeof summary.open_warnings === "number" ? summary.open_warnings : null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">Security Events</h1>
            <InfoTooltip content={SECURITY_EVENTS_TOOLTIP} label="About Security Events" />
          </div>
          <p className="text-muted-foreground">
            Administrative view of security signals returned by the backend.
          </p>
          {!loading && backendUnreachable ? (
            <p className="mt-1 flex items-center gap-1.5 text-xs text-destructive">
              <ServerOff className="h-3.5 w-3.5 shrink-0" aria-hidden />
              Backend unavailable — try again in a moment, or contact your platform administrator.
            </p>
          ) : null}
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>

      {backendUnreachable ? (
        <Alert variant="destructive">
          <AlertTitle>Backend unavailable</AlertTitle>
          <AlertDescription className="text-xs">
            Security event services are not reachable. Verify you&apos;re signed in as an administrator and try again.
          </AlertDescription>
        </Alert>
      ) : null}

      {!backendUnreachable && (errSummary || errEvents) ? (
        <Alert variant="destructive">
          <AlertTitle>Partial load</AlertTitle>
          <AlertDescription className="space-y-1 text-xs">
            {errSummary ? <p>Summary: {errSummary}</p> : null}
            {errEvents ? <p>Events list: {errEvents}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {/* 1. Security summary cards */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Security summary cards</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Total events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {loading ? "…" : totalEvents != null ? String(totalEvents) : "—"}
              </div>
              <p className="text-xs text-muted-foreground">Total security events recorded.</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Open warnings</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold tabular-nums">
                {loading ? "…" : openWarnings != null ? String(openWarnings) : "—"}
              </div>
              <p className="text-xs text-muted-foreground">Unresolved warnings awaiting review.</p>
            </CardContent>
          </Card>
          <Card className="sm:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Counts by severity</CardTitle>
              <CardDescription className="text-xs">counts_by_severity</CardDescription>
            </CardHeader>
            <CardContent className="text-xs">
              {loading ? (
                <p className="text-muted-foreground">Loading…</p>
              ) : summary && isRecord(summary.counts_by_severity as Record<string, unknown>) ? (
                <ul className="flex flex-wrap gap-2">
                  {Object.entries(summary.counts_by_severity as Record<string, unknown>).map(([k, v]) => (
                    <li key={k}>
                      <Badge variant="outline" className={`font-normal ${severityBadgeClass(k)}`}>
                        {k}: {String(v)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>
          <Card className="sm:col-span-2 lg:col-span-4">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Counts by event type</CardTitle>
              <CardDescription className="text-xs">counts_by_type</CardDescription>
            </CardHeader>
            <CardContent className="text-xs">
              {loading ? (
                <p className="text-muted-foreground">Loading…</p>
              ) : summary && isRecord(summary.counts_by_type as Record<string, unknown>) ? (
                <ul className="flex flex-wrap gap-2">
                  {Object.entries(summary.counts_by_type as Record<string, unknown>).map(([k, v]) => (
                    <li key={k}>
                      <Badge variant="outline" className="font-normal">
                        {k}: {String(v)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 2. Event filters */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Event filters</h2>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Filters</CardTitle>
            <CardDescription>
              Severity, event type, actor email, and limit are applied server-side. Date range and resource type narrow the loaded rows in your browser.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="sev-filter">severity</Label>
              <Input
                id="sev-filter"
                placeholder="info, warning, error, critical"
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="etype-filter">event type</Label>
              <Input
                id="etype-filter"
                placeholder="e.g. login_failure"
                value={filterEventType}
                onChange={(e) => setFilterEventType(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="actor-filter">actor email</Label>
              <Input
                id="actor-filter"
                type="email"
                autoComplete="off"
                value={filterActorEmail}
                onChange={(e) => setFilterActorEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="from-filter">date range from</Label>
              <Input
                id="from-filter"
                type="date"
                value={filterDateFrom}
                onChange={(e) => setFilterDateFrom(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="to-filter">date range to</Label>
              <Input id="to-filter" type="date" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rt-filter">resource type</Label>
              <Input
                id="rt-filter"
                placeholder="substring match"
                value={filterResourceType}
                onChange={(e) => setFilterResourceType(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lim-filter">limit</Label>
              <Input
                id="lim-filter"
                inputMode="numeric"
                value={filterLimit}
                onChange={(e) => setFilterLimit(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button type="button" variant="secondary" size="sm" disabled={loading} onClick={() => void load()}>
                Apply server filters
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 3. Security events table */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Security events table</h2>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Events</CardTitle>
            <CardDescription>
              Security events matching the filters above, with the most recent shown first.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : errEvents && eventsRaw.length === 0 ? (
              <p className="text-sm text-destructive">{errEvents}</p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">timestamp</TableHead>
                      <TableHead className="text-xs">severity</TableHead>
                      <TableHead className="text-xs">event type</TableHead>
                      <TableHead className="text-xs">actor</TableHead>
                      <TableHead className="text-xs">resource</TableHead>
                      <TableHead className="text-xs">message</TableHead>
                      <TableHead className="text-xs">IP</TableHead>
                      <TableHead className="text-xs">status / details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {eventsDisplayed.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-xs text-muted-foreground">
                          No events to display.
                        </TableCell>
                      </TableRow>
                    ) : (
                      eventsDisplayed.map((row, i) => {
                        const meta = row.metadata_json
                        const hasMeta = isRecord(meta) && Object.keys(meta).length > 0
                        const rid = readStr(row, ["resource_id"])
                        const rtype = readStr(row, ["resource_type"])
                        const resourceLabel =
                          [rtype, rid].filter(Boolean).join(" / ") || "—"
                        return (
                          <TableRow key={readStr(row, ["id"]) || `ev-${i}`}>
                            <TableCell className="whitespace-nowrap font-mono text-[10px] text-muted-foreground">
                              {readStr(row, ["created_at"]) || "—"}
                            </TableCell>
                            <TableCell className="text-xs">
                              <Badge
                                variant="outline"
                                className={`font-normal ${severityBadgeClass(readStr(row, ["severity"]))}`}
                              >
                                {readStr(row, ["severity"]) || "—"}
                              </Badge>
                            </TableCell>
                            <TableCell className="font-mono text-[10px]">{readStr(row, ["event_type"]) || "—"}</TableCell>
                            <TableCell className="max-w-[10rem] truncate text-xs">{readStr(row, ["actor_email"]) || "—"}</TableCell>
                            <TableCell className="max-w-[12rem] truncate font-mono text-[10px]">{resourceLabel}</TableCell>
                            <TableCell className="max-w-[18rem] text-xs">{readStr(row, ["message"]) || "—"}</TableCell>
                            <TableCell className="font-mono text-[10px]">{readStr(row, ["ip_address"]) || "—"}</TableCell>
                            <TableCell className="max-w-[14rem] align-top text-xs">
                              <div className="space-y-1">
                                <span className="text-muted-foreground">id {readStr(row, ["id"]) || "—"}</span>
                                {hasMeta ? (
                                  <Collapsible className="group rounded border bg-muted/20">
                                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-1 px-2 py-1 text-left text-[10px] font-medium hover:bg-muted/40">
                                      metadata_json
                                      <ChevronDown className="h-3 w-3 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
                                    </CollapsibleTrigger>
                                    <CollapsibleContent>
                                      <pre className="max-h-32 overflow-auto border-t p-2 font-mono text-[10px]">
                                        {JSON.stringify(redactDeep(meta), null, 2)}
                                      </pre>
                                    </CollapsibleContent>
                                  </Collapsible>
                                ) : (
                                  <span className="text-[10px] text-muted-foreground">—</span>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 4. Developer JSON */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Developer JSON</h2>
        <Collapsible className="group rounded-md border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
            Raw responses (redacted)
            <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className="max-h-[24rem] overflow-auto border-t bg-muted/30 p-3 font-mono text-[10px] leading-relaxed">
              {JSON.stringify(developerBundle, null, 2)}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  )
}
