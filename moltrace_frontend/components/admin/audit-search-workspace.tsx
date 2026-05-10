"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  ChevronDown,
  Database,
  Filter,
  Search,
  ScrollText,
  ServerOff,
} from "lucide-react"

const AUDIT_SEARCH_TOOLTIP =
  "Audit search helps reconstruct who did what, when, and why across projects, sessions, evidence, reviews, reports, and admin actions."

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

function metadataPreview(meta: unknown): string {
  const r = redactDeep(meta)
  const s = JSON.stringify(r)
  if (!s || s === "{}") return "—"
  return s.length > 120 ? `${s.slice(0, 120)}…` : s
}

function parseEventTime(iso: string): number {
  const t = Date.parse(iso)
  return Number.isNaN(t) ? NaN : t
}

function filterByDateRange(
  rows: Record<string, unknown>[],
  dateFrom: string,
  dateTo: string,
): Record<string, unknown>[] {
  let out = rows
  const df = dateFrom.trim()
  const dt = dateTo.trim()
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
  return out
}

/** Maps UI resource IDs to GET /admin/audit/search query params (entity_type, entity_id). */
function resolveEntityParams(
  spectracheckProjectId: string,
  spectracheckSampleId: string,
  moltraceProjectId: string,
): { entity_type?: string; entity_id?: number } {
  const mp = moltraceProjectId.trim()
  const sp = spectracheckProjectId.trim()
  const ss = spectracheckSampleId.trim()
  if (sp) {
    const n = Number(sp)
    if (Number.isFinite(n)) return { entity_type: "spectracheck_project", entity_id: Math.floor(n) }
  }
  if (ss) {
    const n = Number(ss)
    if (Number.isFinite(n)) return { entity_type: "spectracheck_sample", entity_id: Math.floor(n) }
  }
  if (mp) {
    const n = Number(mp)
    if (Number.isFinite(n)) return { entity_type: "project", entity_id: Math.floor(n) }
  }
  return {}
}

export function AuditSearchWorkspace() {
  const [loading, setLoading] = useState(true)
  const [rowsRaw, setRowsRaw] = useState<Record<string, unknown>[]>([])
  const [err, setErr] = useState("")

  const [filterEventType, setFilterEventType] = useState("")
  const [filterActorEmail, setFilterActorEmail] = useState("")
  const [filterSessionId, setFilterSessionId] = useState("")
  const [filterReportId, setFilterReportId] = useState("")
  const [filterSpectracheckProjectId, setFilterSpectracheckProjectId] = useState("")
  const [filterSpectracheckSampleId, setFilterSpectracheckSampleId] = useState("")
  const [filterMoltraceProjectId, setFilterMoltraceProjectId] = useState("")
  const [filterDateFrom, setFilterDateFrom] = useState("")
  const [filterDateTo, setFilterDateTo] = useState("")
  const [filterTextQuery, setFilterTextQuery] = useState("")
  const [filterLimit, setFilterLimit] = useState("100")

  const filtersRef = useRef({
    filterEventType,
    filterActorEmail,
    filterSessionId,
    filterReportId,
    filterSpectracheckProjectId,
    filterSpectracheckSampleId,
    filterMoltraceProjectId,
    filterTextQuery,
    filterLimit,
  })
  filtersRef.current = {
    filterEventType,
    filterActorEmail,
    filterSessionId,
    filterReportId,
    filterSpectracheckProjectId,
    filterSpectracheckSampleId,
    filterMoltraceProjectId,
    filterTextQuery,
    filterLimit,
  }

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")

    const f = filtersRef.current
    const params = new URLSearchParams()
    const lim = Math.min(500, Math.max(1, Math.floor(Number(f.filterLimit) || 100)))
    params.set("limit", String(lim))

    const et = f.filterEventType.trim()
    const actor = f.filterActorEmail.trim()
    if (et) params.set("event_type", et)
    if (actor) params.set("actor_email", actor)

    const ent = resolveEntityParams(f.filterSpectracheckProjectId, f.filterSpectracheckSampleId, f.filterMoltraceProjectId)
    if (ent.entity_type) params.set("entity_type", ent.entity_type)
    if (ent.entity_id != null) params.set("entity_id", String(ent.entity_id))

    const qParts: string[] = []
    const tq = f.filterTextQuery.trim()
    if (tq) qParts.push(tq)
    const sid = f.filterSessionId.trim()
    const rid = f.filterReportId.trim()
    if (sid) qParts.push(sid)
    if (rid) qParts.push(rid)
    const qMerged = qParts.join(" ").trim()
    if (qMerged) params.set("q", qMerged)

    try {
      const path = `/admin/audit/search?${params.toString()}`
      const data = await apiFetch<unknown>(path, { method: "GET" })
      const list = Array.isArray(data) ? data : []
      setRowsRaw(list.filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setErr(formatErr(e, "Could not load /admin/audit/search."))
      setRowsRaw([])
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const rowsDisplayed = useMemo(
    () => filterByDateRange(rowsRaw, filterDateFrom, filterDateTo),
    [rowsRaw, filterDateFrom, filterDateTo],
  )

  const developerBundle = useMemo(() => {
    return rowsDisplayed.map((row) => {
      const copy = { ...row }
      if (isRecord(copy.metadata)) {
        copy.metadata = redactDeep(copy.metadata) as Record<string, unknown>
      }
      return copy
    })
  }, [rowsDisplayed])

  const backendUnreachable = !loading && err && rowsRaw.length === 0

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-slate)" }}
          >
            MolTrace · Admin · Audit Search
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">Audit Search</h1>
            <InfoTooltip content={AUDIT_SEARCH_TOOLTIP} label="About Audit Search" />
          </div>
          <p className="text-sm text-muted-foreground">
            Search the global audit log across all entities, actors, and events for compliance and forensics.
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
          {loading ? "Loading…" : "Search"}
        </Button>
      </div>

      {backendUnreachable ? (
        <AlertCard
          variant="error"
          title="Backend unavailable"
          description="Audit search is not reachable. Verify you're signed in as an administrator and try again."
        />
      ) : null}

      {!backendUnreachable && err ? (
        <AlertCard variant="error" title="Request failed" description={err} />
      ) : null}

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Search summary</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-slate)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Rows from API
              </CardTitle>
              <Database className="h-4 w-4" style={{ color: "var(--mt-slate)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-slate)" }}
              >
                {loading ? "…" : String(rowsRaw.length)}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Before client date filter</p>
            </CardContent>
          </Card>
          <Card
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: "3px solid var(--mt-slate)" }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Rows shown
              </CardTitle>
              <Filter className="h-4 w-4" style={{ color: "var(--mt-slate)" }} aria-hidden />
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: "var(--mt-slate)" }}
              >
                {loading ? "…" : String(rowsDisplayed.length)}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">After date range filter</p>
            </CardContent>
          </Card>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Filters</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Search"
          title="Filters"
          icon={Search}
          description="Narrow audit results by event type, entity, actor email, or free-text search. MolTrace and SpectraCheck projects use distinct entity types — pick whichever matches your investigation. The date range is applied locally after results load."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="moltrace-project">project ID (MolTrace workspace)</Label>
              <Input
                id="moltrace-project"
                inputMode="numeric"
                placeholder="entity_id for entity_type project"
                value={filterMoltraceProjectId}
                onChange={(e) => setFilterMoltraceProjectId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sc-project">project ID (SpectraCheck persistence)</Label>
              <Input
                id="sc-project"
                inputMode="numeric"
                placeholder="entity_id for spectracheck_project"
                value={filterSpectracheckProjectId}
                onChange={(e) => setFilterSpectracheckProjectId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sc-sample">sample ID (SpectraCheck persistence)</Label>
              <Input
                id="sc-sample"
                inputMode="numeric"
                placeholder="entity_id for spectracheck_sample"
                value={filterSpectracheckSampleId}
                onChange={(e) => setFilterSpectracheckSampleId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sess-id">session ID</Label>
              <Input
                id="sess-id"
                placeholder="merged into q"
                value={filterSessionId}
                onChange={(e) => setFilterSessionId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rep-id">report ID</Label>
              <Input
                id="rep-id"
                placeholder="merged into q"
                value={filterReportId}
                onChange={(e) => setFilterReportId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="actor-audit">actor</Label>
              <Input
                id="actor-audit"
                type="email"
                autoComplete="off"
                placeholder="actor_email"
                value={filterActorEmail}
                onChange={(e) => setFilterActorEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ev-type">event type</Label>
              <Input
                id="ev-type"
                placeholder="event_type"
                value={filterEventType}
                onChange={(e) => setFilterEventType(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="from-audit">date range from</Label>
              <Input id="from-audit" type="date" value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="to-audit">date range to</Label>
              <Input id="to-audit" type="date" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} />
            </div>
            <div className="space-y-2 lg:col-span-2">
              <Label htmlFor="q-audit">text query</Label>
              <Input
                id="q-audit"
                placeholder="q (message substring)"
                value={filterTextQuery}
                onChange={(e) => setFilterTextQuery(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lim-audit">limit</Label>
              <Input id="lim-audit" inputMode="numeric" value={filterLimit} onChange={(e) => setFilterLimit(e.target.value)} />
            </div>
            <div className="flex items-end">
              <Button type="button" variant="secondary" size="sm" disabled={loading} onClick={() => void load()}>
                Apply search
              </Button>
            </div>
          </div>
        </ModuleCard>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Audit events</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Audit"
          title="Audit events table"
          icon={ScrollText}
          description="Rows after optional date-range refinement."
        >
          <div>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">event type</TableHead>
                      <TableHead className="text-xs">message</TableHead>
                      <TableHead className="text-xs">actor</TableHead>
                      <TableHead className="text-xs">timestamp</TableHead>
                      <TableHead className="text-xs">resource</TableHead>
                      <TableHead className="text-xs">metadata preview</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rowsDisplayed.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-xs text-muted-foreground">
                          No audit events to display.
                        </TableCell>
                      </TableRow>
                    ) : (
                      rowsDisplayed.map((row, i) => {
                        const meta = row.metadata
                        const hasMeta = meta != null && JSON.stringify(redactDeep(meta)) !== "{}"
                        const resource =
                          [readStr(row, ["entity_type"]), readStr(row, ["entity_id"])].filter(Boolean).join(" · ") || "—"
                        return (
                          <TableRow key={readStr(row, ["id"]) || `audit-${i}`}>
                            <TableCell className="font-mono text-[10px]">{readStr(row, ["event_type"]) || "—"}</TableCell>
                            <TableCell className="max-w-[22rem] text-xs">{readStr(row, ["message"]) || "—"}</TableCell>
                            <TableCell className="max-w-[12rem] truncate text-xs">{readStr(row, ["actor_email"]) || "—"}</TableCell>
                            <TableCell className="whitespace-nowrap font-mono text-[10px] text-muted-foreground">
                              {readStr(row, ["created_at"]) || "—"}
                            </TableCell>
                            <TableCell className="max-w-[14rem] truncate font-mono text-[10px]">{resource}</TableCell>
                            <TableCell className="max-w-[18rem] align-top text-[10px]">
                              {hasMeta ? (
                                <Collapsible className="group rounded border bg-muted/20">
                                  <CollapsibleTrigger className="flex w-full items-center justify-between gap-1 px-2 py-1 text-left font-medium hover:bg-muted/40">
                                    <span className="truncate text-muted-foreground">{metadataPreview(meta)}</span>
                                    <ChevronDown className="h-3 w-3 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
                                  </CollapsibleTrigger>
                                  <CollapsibleContent>
                                    <pre className="max-h-40 overflow-auto border-t p-2 font-mono leading-relaxed">
                                      {JSON.stringify(redactDeep(meta), null, 2)}
                                    </pre>
                                  </CollapsibleContent>
                                </Collapsible>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </ModuleCard>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Developer JSON</h2>
        <Collapsible className="group rounded-md border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
            Raw rows (redacted)
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
