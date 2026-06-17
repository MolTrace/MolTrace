"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import {
  trackRegulatoryActionItemCreated,
  trackRegulatoryActionItemResolved,
} from "@/src/lib/analytics/analytics-client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  formatIsoWhenPresent,
  readRecordNumber,
  readRecordString,
} from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { InfoTooltip } from "@/components/ui/info-tooltip"
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
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { CheckCircle2, Clock, FilterX, Loader2, Play, UserPlus, X } from "lucide-react"

// ── Color tokens for severity + status badges ─────────────────────────────
function severityBadgeStyle(severity: string | null | undefined) {
  const norm = (severity ?? "").toLowerCase()
  if (norm === "critical" || norm === "high") {
    return {
      borderColor: "var(--mt-red)",
      backgroundColor: "color-mix(in oklab, var(--mt-red) 12%, transparent)",
      color: "var(--mt-red)",
    } as const
  }
  if (norm === "medium") {
    return {
      borderColor: "var(--mt-amber)",
      backgroundColor: "color-mix(in oklab, var(--mt-amber) 12%, transparent)",
      color: "var(--mt-amber)",
    } as const
  }
  if (norm === "low") {
    return {
      borderColor: "var(--mt-slate)",
      backgroundColor: "color-mix(in oklab, var(--mt-slate) 10%, transparent)",
      color: "var(--mt-slate)",
    } as const
  }
  if (norm === "info") {
    return {
      borderColor: "var(--mt-cyan)",
      backgroundColor: "color-mix(in oklab, var(--mt-cyan) 10%, transparent)",
      color: "var(--mt-cyan-ink)",
    } as const
  }
  return {
    borderColor: "var(--border)",
    color: "var(--muted-foreground)",
  } as const
}

function statusBadgeStyle(status: string | null | undefined) {
  const norm = (status ?? "").toLowerCase()
  if (norm === "open") {
    return {
      borderColor: "var(--mt-cyan)",
      backgroundColor: "color-mix(in oklab, var(--mt-cyan) 10%, transparent)",
      color: "var(--mt-cyan-ink)",
    } as const
  }
  if (norm === "in_progress") {
    return {
      borderColor: "var(--mt-amber)",
      backgroundColor: "color-mix(in oklab, var(--mt-amber) 12%, transparent)",
      color: "var(--mt-amber)",
    } as const
  }
  if (norm === "resolved") {
    return {
      borderColor: "var(--mt-green)",
      backgroundColor: "color-mix(in oklab, var(--mt-green) 12%, transparent)",
      color: "var(--mt-green)",
    } as const
  }
  if (norm === "deferred") {
    return {
      borderColor: "var(--mt-violet)",
      backgroundColor: "color-mix(in oklab, var(--mt-violet) 10%, transparent)",
      color: "var(--mt-violet-ink)",
    } as const
  }
  if (norm === "dismissed") {
    return {
      borderColor: "var(--mt-slate)",
      backgroundColor: "color-mix(in oklab, var(--mt-slate) 10%, transparent)",
      color: "var(--mt-slate)",
    } as const
  }
  return {
    borderColor: "var(--border)",
    color: "var(--muted-foreground)",
  } as const
}

export const ACTION_QUEUE_TOOLTIP =
  "Regulatory action items are review tasks triggered by thresholds, missing evidence, nitrosamine risk, validation gaps, or jurisdictional differences."

const REGULATORY_ACTION_TYPES = [
  "impurity_reporting",
  "impurity_identification",
  "impurity_qualification",
  "residual_solvent_review",
  "nitrosamine_risk_review",
  "qnmr_validation_gap",
  "ai_governance_gap",
  "jurisdictional_review",
  "source_needed",
  "human_review",
  "other",
] as const

const REGULATORY_ACTION_SEVERITIES = ["info", "warning", "high", "critical"] as const

const REGULATORY_ACTION_STATUSES = ["open", "in_progress", "resolved", "dismissed", "deferred"] as const

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

function labelFromSnake(raw: string | undefined): string {
  if (!raw) return "—"
  return raw.replace(/_/g, " ")
}

function readCitationCount(row: Record<string, unknown>): number {
  const v = row.citation_ids_json
  if (!Array.isArray(v)) return 0
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x)).length
}

export type RegulatoryActionQueueProps = {
  dossierId?: number
  compact?: boolean
}

export function RegulatoryActionQueue({ dossierId, compact }: RegulatoryActionQueueProps) {
  const [items, setItems] = useState<Record<string, unknown>[]>([])
  const [dossiers, setDossiers] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [patchBusyId, setPatchBusyId] = useState<number | null>(null)
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")

  const [filterSeverity, setFilterSeverity] = useState<string>("__all__")
  const [filterStatus, setFilterStatus] = useState<string>("__all__")
  const [filterActionType, setFilterActionType] = useState<string>("__all__")
  const [filterDossierId, setFilterDossierId] = useState<string>("__all__")
  const [filterAssigned, setFilterAssigned] = useState("")

  const [assignOpen, setAssignOpen] = useState(false)
  const [assignTargetId, setAssignTargetId] = useState<number | null>(null)
  const [assignDraft, setAssignDraft] = useState("")

  const [createOpen, setCreateOpen] = useState(false)
  const [createTitle, setCreateTitle] = useState("")
  const [createDescription, setCreateDescription] = useState("")
  const [createActionType, setCreateActionType] = useState<string>("human_review")
  const [createSeverity, setCreateSeverity] = useState<string>("warning")
  const [createStatus, setCreateStatus] = useState<string>("open")
  const [createAssigned, setCreateAssigned] = useState("")

  const dossierTitleById = useMemo(() => {
    const m = new Map<number, string>()
    for (const d of dossiers) {
      const id = readRecordNumber(d, "id")
      const title = readRecordString(d, "title")
      if (id != null && title) m.set(id, title)
    }
    return m
  }, [dossiers])

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const q = dossierId != null && Number.isFinite(dossierId)
        ? `?dossier_id=${dossierId}&limit=200`
        : `?limit=500`
      const raw = await apiFetch<unknown>(`/regulatory/action-items${q}`, { method: "GET" })
      setItems(asArray(raw).filter(isRecord) as Record<string, unknown>[])
      const dRaw = await apiFetch<unknown>("/regulatory/dossiers?limit=500", { method: "GET" })
      setDossiers(asArray(dRaw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setErr(formatApiError(e, "Could not load action items."))
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [dossierId])

  useEffect(() => {
    void load()
  }, [load])

  const filteredItems = useMemo(() => {
    let rows = items
    const sev = filterSeverity === "__all__" ? null : filterSeverity
    const st = filterStatus === "__all__" ? null : filterStatus
    const at = filterActionType === "__all__" ? null : filterActionType
    const did =
      dossierId != null
        ? dossierId
        : filterDossierId === "__all__"
          ? null
          : Number.parseInt(filterDossierId, 10)
    const assignQ = filterAssigned.trim().toLowerCase()

    if (sev) rows = rows.filter((r) => readRecordString(r, "severity") === sev)
    if (st) rows = rows.filter((r) => readRecordString(r, "status") === st)
    if (at) rows = rows.filter((r) => readRecordString(r, "action_type") === at)
    if (did != null && Number.isFinite(did)) {
      rows = rows.filter((r) => readRecordNumber(r, "dossier_id") === did)
    }
    if (assignQ) {
      rows = rows.filter((r) => (readRecordString(r, "assigned_to") ?? "").toLowerCase().includes(assignQ))
    }
    return rows
  }, [items, filterSeverity, filterStatus, filterActionType, filterDossierId, filterAssigned, dossierId])

  const patchStatus = async (id: number, status: string, row: Record<string, unknown>) => {
    setPatchBusyId(id)
    try {
      await apiFetch(`/regulatory/action-items/${id}`, {
        method: "PATCH",
        body: { status },
      })
      await load()
      if (status === "resolved") {
        const did = readRecordNumber(row, "dossier_id")
        trackRegulatoryActionItemResolved({
          dossier_id: did ?? undefined,
          action_type: readRecordString(row, "action_type"),
          severity: readRecordString(row, "severity"),
          status: "resolved",
          has_citations: readCitationCount(row) > 0,
        })
      }
    } catch (e) {
      setErr(formatApiError(e, "Update failed."))
    } finally {
      setPatchBusyId(null)
    }
  }

  const patchAssign = async () => {
    if (assignTargetId == null) return
    const id = assignTargetId
    setPatchBusyId(id)
    try {
      await apiFetch(`/regulatory/action-items/${id}`, {
        method: "PATCH",
        body: { assigned_to: assignDraft.trim() || null },
      })
      setAssignOpen(false)
      setAssignTargetId(null)
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Assign failed."))
    } finally {
      setPatchBusyId(null)
    }
  }

  const createItem = async () => {
    const title = createTitle.trim()
    const description = createDescription.trim()
    if (!title || !description) {
      setCreateErr("title and description are required.")
      return
    }
    setCreateBusy(true)
    setCreateErr("")
    try {
      const body: Record<string, unknown> = {
        title,
        description,
        action_type: createActionType,
        severity: createSeverity,
        status: createStatus,
        citation_ids_json: [],
        metadata_json: {},
      }
      if (dossierId != null && Number.isFinite(dossierId)) body.dossier_id = dossierId
      const at = createAssigned.trim()
      if (at) body.assigned_to = at
      await apiFetch("/regulatory/action-items", { method: "POST", body })
      const didForTrack =
        dossierId != null && Number.isFinite(dossierId) ? dossierId : readRecordNumber(body, "dossier_id") ?? undefined
      trackRegulatoryActionItemCreated({
        dossier_id: didForTrack,
        action_type: createActionType,
        severity: createSeverity,
        status: createStatus,
        has_citations: false,
      })
      setCreateOpen(false)
      setCreateTitle("")
      setCreateDescription("")
      await load()
    } catch (e) {
      setCreateErr(formatApiError(e, "Create failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  return (
    <div className={compact ? "space-y-3" : "space-y-6"}>
      {!compact ? (
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-cyan-ink)" }}
          >
            Regulatory · Action Queue
          </p>
          <h2 className="font-mono text-xl font-bold tracking-tight">Action items</h2>
          <p className="text-sm text-muted-foreground">
            Operational tasks from compliance workflows — not legal advice. Filter by severity, status, type, owner, dossier, or change.
          </p>
        </div>
      ) : null}

      {err ? (
        <Alert variant="destructive">
          <AlertDescription className="text-sm">{err}</AlertDescription>
        </Alert>
      ) : null}

      {!compact || dossierId != null ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
            New action item
          </Button>
        </div>
      ) : null}

      {!compact ? (
        (() => {
          const filtersActive =
            filterSeverity !== "__all__" ||
            filterStatus !== "__all__" ||
            filterActionType !== "__all__" ||
            filterDossierId !== "__all__" ||
            filterAssigned.trim() !== ""
          return (
            <div className="flex flex-wrap items-end justify-between gap-2 pt-2">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan-ink)" }}
              >
                Action Queue · Filters
              </p>
              {filtersActive ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-[11px]"
                  onClick={() => {
                    setFilterSeverity("__all__")
                    setFilterStatus("__all__")
                    setFilterActionType("__all__")
                    setFilterDossierId("__all__")
                    setFilterAssigned("")
                  }}
                >
                  <FilterX className="size-3" aria-hidden />
                  Reset filters
                </Button>
              ) : null}
            </div>
          )
        })()
      ) : null}

      <div
        className={
          compact
            ? "grid gap-2 rounded-lg border bg-muted/20 p-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5"
            : "grid gap-3 rounded-lg border bg-muted/20 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
        }
      >
        <div className="space-y-1.5">
          <Label className="text-xs">severity</Label>
          <Select value={filterSeverity} onValueChange={setFilterSeverity}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All</SelectItem>
              {REGULATORY_ACTION_SEVERITIES.map((s) => (
                <SelectItem key={s} value={s}>
                  {labelFromSnake(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">status</Label>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All</SelectItem>
              {REGULATORY_ACTION_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {labelFromSnake(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">action_type</Label>
          <Select value={filterActionType} onValueChange={setFilterActionType}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All</SelectItem>
              {REGULATORY_ACTION_TYPES.map((s) => (
                <SelectItem key={s} value={s}>
                  {labelFromSnake(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {dossierId == null ? (
          <div className="space-y-1.5">
            <Label className="text-xs">dossier_id</Label>
            <Select value={filterDossierId} onValueChange={setFilterDossierId}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All</SelectItem>
                {dossiers.flatMap((d) => {
                  const id = readRecordNumber(d, "id")
                  if (id == null) return []
                  const title = readRecordString(d, "title") ?? `dossier ${id}`
                  return [
                    <SelectItem key={id} value={String(id)}>
                      {title} ({id})
                    </SelectItem>,
                  ]
                })}
              </SelectContent>
            </Select>
          </div>
        ) : null}
        <div className="space-y-1.5">
          <Label className="text-xs">assigned_to (contains)</Label>
          <Input
            className="h-9"
            value={filterAssigned}
            onChange={(e) => setFilterAssigned(e.target.value)}
            placeholder="Filter"
            autoComplete="off"
          />
        </div>
      </div>
      {dossierId != null ? (
        <p className="text-xs text-muted-foreground">
          GET uses <span className="font-mono">dossier_id={dossierId}</span>; additional filters apply in the browser.
        </p>
      ) : null}

      <div className="table-scroll">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[140px]">title</TableHead>
              <TableHead className="w-[140px]">action_type</TableHead>
              <TableHead className="w-[90px]">severity</TableHead>
              <TableHead className="w-[110px]">status</TableHead>
              <TableHead className="w-[100px]">dossier</TableHead>
              <TableHead className="w-[72px]">batch</TableHead>
              <TableHead className="w-[80px]">compound</TableHead>
              <TableHead className="min-w-[100px]">assigned_to</TableHead>
              <TableHead className="w-[120px]">due_date</TableHead>
              <TableHead className="w-[72px] text-right">citations</TableHead>
              <TableHead className="w-[140px]">updated_at</TableHead>
              <TableHead className="min-w-[220px]">actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={12} className="py-6 text-sm text-muted-foreground">
                  <div className="flex items-center justify-center gap-2">
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    Loading action items…
                  </div>
                </TableCell>
              </TableRow>
            ) : filteredItems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={12} className="py-8">
                  <div className="flex flex-col items-center justify-center gap-2 text-center">
                    <FilterX className="size-5 text-muted-foreground/60" aria-hidden />
                    <p className="font-mono text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
                      No matches
                    </p>
                    <p className="text-sm text-muted-foreground">
                      No action items match the current filters. Try resetting filters or check back after a surveillance run.
                    </p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredItems.map((row) => {
                const id = readRecordNumber(row, "id")
                if (id == null) return null
                const busy = patchBusyId === id
                const did = readRecordNumber(row, "dossier_id")
                const dossierLabel =
                  did != null ? dossierTitleById.get(did) ?? `id ${did}` : "—"
                return (
                  <TableRow key={id}>
                    <TableCell className="max-w-[220px] text-sm">
                      <span className="line-clamp-2" title={readRecordString(row, "title")}>
                        {readRecordString(row, "title") ?? "—"}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-[11px]">
                      {readRecordString(row, "action_type") ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs">
                      {(() => {
                        const sev = readRecordString(row, "severity")
                        if (!sev) return <span className="text-muted-foreground">—</span>
                        return (
                          <Badge
                            variant="outline"
                            className="font-mono text-[10px] font-bold uppercase tracking-wide"
                            style={severityBadgeStyle(sev)}
                          >
                            {sev}
                          </Badge>
                        )
                      })()}
                    </TableCell>
                    <TableCell className="text-xs">
                      {(() => {
                        const st = readRecordString(row, "status")
                        if (!st) return <span className="text-muted-foreground">—</span>
                        return (
                          <Badge
                            variant="outline"
                            className="font-mono text-[10px] font-bold uppercase tracking-wide"
                            style={statusBadgeStyle(st)}
                          >
                            {st.replace(/_/g, " ")}
                          </Badge>
                        )
                      })()}
                    </TableCell>
                    <TableCell className="text-xs">
                      {did != null ? (
                        <Link
                          href={`/regulatory/dossiers/${did}`}
                          className="text-primary underline-offset-4 hover:underline"
                        >
                          {dossierLabel}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-[11px]">
                      {readRecordNumber(row, "batch_id") ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-[11px]">
                      {readRecordNumber(row, "compound_id") ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-[120px] truncate text-xs">
                      {readRecordString(row, "assigned_to") ?? "—"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-[11px] text-muted-foreground">
                      {formatIsoWhenPresent(readRecordString(row, "due_date"))}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{readCitationCount(row)}</TableCell>
                    <TableCell className="whitespace-nowrap text-[11px] text-muted-foreground">
                      {formatIsoWhenPresent(readRecordString(row, "updated_at"))}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1">
                        {busy ? (
                          <Loader2 className="mr-1 size-3 animate-spin text-muted-foreground" aria-hidden />
                        ) : null}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 gap-1 px-2 text-[11px]"
                          aria-label="In progress"
                          title="Mark as in progress"
                          disabled={busy}
                          onClick={() => void patchStatus(id, "in_progress", row)}
                        >
                          <Play className="size-3" aria-hidden />
                          In progress
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 gap-1 px-2 text-[11px]"
                          aria-label="Resolve"
                          title="Mark as resolved"
                          disabled={busy}
                          onClick={() => void patchStatus(id, "resolved", row)}
                          style={{ borderColor: "color-mix(in oklab, var(--mt-green) 40%, var(--border))" }}
                        >
                          <CheckCircle2 className="size-3" style={{ color: "var(--mt-green)" }} aria-hidden />
                          Resolve
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 gap-1 px-2 text-[11px]"
                          aria-label="Dismiss"
                          title="Dismiss this action"
                          disabled={busy}
                          onClick={() => void patchStatus(id, "dismissed", row)}
                        >
                          <X className="size-3" aria-hidden />
                          Dismiss
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 gap-1 px-2 text-[11px]"
                          aria-label="Defer"
                          title="Defer to later"
                          disabled={busy}
                          onClick={() => void patchStatus(id, "deferred", row)}
                        >
                          <Clock className="size-3" aria-hidden />
                          Defer
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 gap-1 px-2 text-[11px]"
                          aria-label="Assign"
                          title="Assign owner"
                          disabled={busy}
                          onClick={() => {
                            setAssignTargetId(id)
                            setAssignDraft(readRecordString(row, "assigned_to") ?? "")
                            setAssignOpen(true)
                          }}
                        >
                          <UserPlus className="size-3" aria-hidden />
                          Assign
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Assign owner</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="assign-to">assigned_to</Label>
            <Input
              id="assign-to"
              value={assignDraft}
              onChange={(e) => setAssignDraft(e.target.value)}
              placeholder="User id or display name"
              autoComplete="off"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => setAssignOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={patchBusyId != null} onClick={() => void patchAssign()}>
              {patchBusyId != null ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>New regulatory action item</DialogTitle>
          </DialogHeader>
          {createErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{createErr}</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-3">
            <div className="space-y-2">
              <Label htmlFor="na-title">title</Label>
              <Input id="na-title" value={createTitle} onChange={(e) => setCreateTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="na-desc">description</Label>
              <Textarea
                id="na-desc"
                rows={4}
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
                className="text-sm"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>action_type</Label>
                <Select value={createActionType} onValueChange={setCreateActionType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REGULATORY_ACTION_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>severity</Label>
                <Select value={createSeverity} onValueChange={setCreateSeverity}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REGULATORY_ACTION_SEVERITIES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
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
                    {REGULATORY_ACTION_STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="na-asg">assigned_to (optional)</Label>
                <Input
                  id="na-asg"
                  value={createAssigned}
                  onChange={(e) => setCreateAssigned(e.target.value)}
                />
              </div>
            </div>
            {dossierId != null ? (
              <p className="text-xs text-muted-foreground">
                <span className="font-mono">dossier_id</span> will be set to {dossierId}.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Leave dossier unscoped unless you add <span className="font-mono">dossier_id</span> via API or create
                from a dossier workspace.
              </p>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={createBusy} onClick={() => void createItem()}>
              {createBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
              POST create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function RegulatoryActionQueueCard({
  dossierId,
  compact = true,
}: {
  dossierId: number
  compact?: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-2">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-lg">Action Items</CardTitle>
            <InfoTooltip label="Regulatory action queue" content={ACTION_QUEUE_TOOLTIP} />
          </div>
          <CardDescription>
            Regulatory action items requiring review or follow-up — update status and add comments as items are resolved.{" "}
            <Link href="/regulatory/action-queue" className="underline-offset-4 hover:underline">
              Open full queue
            </Link>
            .
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <RegulatoryActionQueue dossierId={dossierId} compact={compact} />
      </CardContent>
    </Card>
  )
}
