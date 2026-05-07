"use client"

import Link from "next/link"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { AppShell } from "@/components/app/app-shell"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Loader2 } from "lucide-react"
import SavedReportsWorkspace from "@/components/reports/saved-reports-workspace"
import ReviewQueueWorkspace from "@/components/review/review-queue-workspace"

const PROGRAMS = [
  { key: "spectracheck", label: "SpectraCheck" },
  { key: "regulatory_hub", label: "Regulatory Hub" },
  { key: "reaction_optimization", label: "Reaction Optimization" },
] as const

const ACTION_TYPES = [
  "create_dossier",
  "link_evidence",
  "run_regulatory_assessment",
  "create_reaction_constraint",
  "run_reaction_optimization",
  "update_report",
  "review_required",
  "other",
] as const
const SEVERITIES = ["info", "warning", "high", "critical"] as const
const STATUSES = ["open", "in_progress", "resolved", "dismissed", "blocked"] as const

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRows(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) return raw.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(raw)) return []
  if (Array.isArray(raw.items)) return raw.items.filter(isRecord) as Record<string, unknown>[]
  if (Array.isArray(raw.results)) return raw.results.filter(isRecord) as Record<string, unknown>[]
  return []
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function programLabel(key: string): string {
  const m = PROGRAMS.find((p) => p.key === key)
  return m?.label ?? key.replace(/_/g, " ")
}

function programRank(key: string): number {
  const idx = PROGRAMS.findIndex((p) => p.key === key)
  return idx === -1 ? 999 : idx
}

function formatDate(raw: unknown): string {
  const s = readStr(raw)
  if (!s) return "—"
  const t = Date.parse(s)
  if (Number.isNaN(t)) return s
  return new Date(t).toLocaleString()
}

function openHref(programKey: string, resourceType: string, resourceId: number | null): string {
  if (programKey === "spectracheck") return "/spectracheck"
  if (programKey === "regulatory_hub") {
    if (resourceType.includes("dossier") && resourceId != null) return `/regulatory/dossiers/${resourceId}`
    return "/regulatory"
  }
  if (programKey === "reaction_optimization") {
    if (resourceType.includes("project") && resourceId != null) return `/reactions/${resourceId}`
    return "/reactions"
  }
  return "/dashboard"
}

function CrossModuleActionQueueWorkspace() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [busyId, setBusyId] = useState<number | null>(null)
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")

  const [fSource, setFSource] = useState("__all__")
  const [fTarget, setFTarget] = useState("__all__")
  const [fSeverity, setFSeverity] = useState("__all__")
  const [fStatus, setFStatus] = useState("__all__")
  const [fActionType, setFActionType] = useState("__all__")

  const [sourceProgram, setSourceProgram] = useState<string>("spectracheck")
  const [targetProgram, setTargetProgram] = useState<string>("regulatory_hub")
  const [actionType, setActionType] = useState<string>("review_required")
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [severity, setSeverity] = useState<string>("warning")
  const [status, setStatus] = useState<string>("open")
  const [sourceResourceType, setSourceResourceType] = useState("")
  const [sourceResourceId, setSourceResourceId] = useState("")
  const [targetResourceType, setTargetResourceType] = useState("")
  const [targetResourceId, setTargetResourceId] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const raw = await apiFetch<unknown>("/cross-module/action-items", { method: "GET" })
      setRows(asRows(raw))
    } catch (e) {
      setErr(formatApiError(e, "Could not load cross-module action items."))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    let out = rows
    if (fSource !== "__all__") out = out.filter((r) => readStr(r.source_program) === fSource)
    if (fTarget !== "__all__") out = out.filter((r) => readStr(r.target_program) === fTarget)
    if (fSeverity !== "__all__") out = out.filter((r) => readStr(r.severity) === fSeverity)
    if (fStatus !== "__all__") out = out.filter((r) => readStr(r.status) === fStatus)
    if (fActionType !== "__all__") out = out.filter((r) => readStr(r.action_type) === fActionType)
    return [...out].sort((a, b) => {
      const sa = programRank(readStr(a.source_program))
      const sb = programRank(readStr(b.source_program))
      if (sa !== sb) return sa - sb
      const ta = programRank(readStr(a.target_program))
      const tb = programRank(readStr(b.target_program))
      if (ta !== tb) return ta - tb
      const ad = Date.parse(readStr(a.created_at))
      const bd = Date.parse(readStr(b.created_at))
      return (Number.isNaN(bd) ? 0 : bd) - (Number.isNaN(ad) ? 0 : ad)
    })
  }, [rows, fSource, fTarget, fSeverity, fStatus, fActionType])

  async function updateStatus(id: number, nextStatus: string) {
    setBusyId(id)
    setErr("")
    try {
      await apiFetch(`/cross-module/action-items/${id}`, {
        method: "PATCH",
        body: { status: nextStatus },
      })
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Update action item failed."))
    } finally {
      setBusyId(null)
    }
  }

  async function createItem() {
    const t = title.trim()
    const d = description.trim()
    if (!t || !d) {
      setCreateErr("title and description are required.")
      return
    }
    setCreateBusy(true)
    setCreateErr("")
    try {
      const body: Record<string, unknown> = {
        source_program: sourceProgram,
        target_program: targetProgram,
        action_type: actionType,
        title: t,
        description: d,
        severity,
        status,
        source_resource_type: sourceResourceType.trim() || "other",
        source_resource_id: sourceResourceId.trim() || null,
        target_resource_type: targetResourceType.trim() || null,
        target_resource_id: targetResourceId.trim() || null,
        metadata_json: {},
      }
      await apiFetch("/cross-module/action-items", { method: "POST", body })
      setTitle("")
      setDescription("")
      setSourceResourceType("")
      setSourceResourceId("")
      setTargetResourceType("")
      setTargetResourceId("")
      await load()
    } catch (e) {
      setCreateErr(formatApiError(e, "Create action item failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <Alert>
        <AlertTitle className="text-sm">Operational queue</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Cross-module action items are workflow coordination tasks. They are not legal advice.
        </AlertDescription>
      </Alert>

      {err ? (
        <Alert variant="destructive">
          <AlertDescription>{err}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">New action item</CardTitle>
          <CardDescription>POST /cross-module/action-items</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {createErr ? <p className="text-xs text-destructive">{createErr}</p> : null}
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1.5">
              <Label>source program</Label>
              <Select value={sourceProgram} onValueChange={setSourceProgram}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{PROGRAMS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>target program</Label>
              <Select value={targetProgram} onValueChange={setTargetProgram}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{PROGRAMS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>action type</Label>
              <Select value={actionType} onValueChange={setActionType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{ACTION_TYPES.map((a) => <SelectItem key={a} value={a}>{a.replace(/_/g, " ")}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <Label>description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>severity</Label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{SEVERITIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>source resource type</Label>
              <Input value={sourceResourceType} onChange={(e) => setSourceResourceType(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>source resource id</Label>
              <Input value={sourceResourceId} onChange={(e) => setSourceResourceId(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>target resource type</Label>
              <Input value={targetResourceType} onChange={(e) => setTargetResourceType(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>target resource id</Label>
              <Input value={targetResourceId} onChange={(e) => setTargetResourceId(e.target.value)} />
            </div>
          </div>
          <Button type="button" onClick={() => void createItem()} disabled={createBusy}>
            {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Create action item
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Cross-Module Action Queue</CardTitle>
          <CardDescription>
            GET /cross-module/action-items · PATCH /cross-module/action-items/{"{action_item_id}"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 rounded-lg border bg-muted/20 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <div className="space-y-1.5">
              <Label className="text-xs">source program</Label>
              <Select value={fSource} onValueChange={setFSource}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All</SelectItem>
                  {PROGRAMS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">target program</Label>
              <Select value={fTarget} onValueChange={setFTarget}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All</SelectItem>
                  {PROGRAMS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">severity</Label>
              <Select value={fSeverity} onValueChange={setFSeverity}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All</SelectItem>
                  {SEVERITIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">status</Label>
              <Select value={fStatus} onValueChange={setFStatus}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All</SelectItem>
                  {STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">action type</Label>
              <Select value={fActionType} onValueChange={setFActionType}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All</SelectItem>
                  {ACTION_TYPES.map((a) => <SelectItem key={a} value={a}>{a.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>source program</TableHead>
                  <TableHead>target program</TableHead>
                  <TableHead>action type</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>severity</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>linked resource</TableHead>
                  <TableHead>created date</TableHead>
                  <TableHead>open source</TableHead>
                  <TableHead>open target</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow><TableCell colSpan={10} className="text-muted-foreground">Loading…</TableCell></TableRow>
                ) : filtered.length === 0 ? (
                  <TableRow><TableCell colSpan={10} className="text-muted-foreground">No action items.</TableCell></TableRow>
                ) : (
                  filtered.map((row, i) => {
                    const id = readNum(row.id)
                    const srcProgram = readStr(row.source_program)
                    const tgtProgram = readStr(row.target_program)
                    const srcType = readStr(row.source_resource_type)
                    const tgtType = readStr(row.target_resource_type)
                    const srcId = readNum(row.source_resource_id)
                    const tgtId = readNum(row.target_resource_id)
                    const srcHref = openHref(srcProgram, srcType, srcId)
                    const tgtHref = openHref(tgtProgram, tgtType, tgtId)
                    return (
                      <TableRow key={id ?? i}>
                        <TableCell>{programLabel(srcProgram)}</TableCell>
                        <TableCell>{programLabel(tgtProgram)}</TableCell>
                        <TableCell className="font-mono text-xs">{readStr(row.action_type) || "—"}</TableCell>
                        <TableCell className="max-w-[280px]">{readStr(row.title) || "—"}</TableCell>
                        <TableCell><Badge variant="outline">{readStr(row.severity) || "—"}</Badge></TableCell>
                        <TableCell>
                          {id == null ? (
                            <span>{readStr(row.status) || "—"}</span>
                          ) : (
                            <Select
                              value={readStr(row.status) || "open"}
                              onValueChange={(next) => void updateStatus(id, next)}
                              disabled={busyId === id}
                            >
                              <SelectTrigger className="h-8 w-[135px]"><SelectValue /></SelectTrigger>
                              <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                            </Select>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {srcType || "—"}:{srcId ?? "—"} → {tgtType || "—"}:{tgtId ?? "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{formatDate(row.created_at)}</TableCell>
                        <TableCell><Button variant="outline" size="sm" asChild><Link href={srcHref}>Open source</Link></Button></TableCell>
                        <TableCell><Button variant="outline" size="sm" asChild><Link href={tgtHref}>Open target</Link></Button></TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default function CrossModuleActionQueuePage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading action queue…</p>}>
        <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
          <Tabs defaultValue="action_queue" className="space-y-6">
            <TabsList>
              <TabsTrigger value="action_queue">Action Queue</TabsTrigger>
              <TabsTrigger value="reports">Reports</TabsTrigger>
              <TabsTrigger value="review">Review</TabsTrigger>
            </TabsList>
            <TabsContent value="action_queue">
              <CrossModuleActionQueueWorkspace />
            </TabsContent>
            <TabsContent value="reports">
              <SavedReportsWorkspace />
            </TabsContent>
            <TabsContent value="review">
              <ReviewQueueWorkspace />
            </TabsContent>
          </Tabs>
        </div>
      </Suspense>
    </AppShell>
  )
}
