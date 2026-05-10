"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  KNOWLEDGE_REVIEW_RECORD_TYPES,
  MODEL_IMPROVEMENT_PRIORITIES,
  MODEL_IMPROVEMENT_SOURCE_TYPES,
  MODEL_IMPROVEMENT_STATUSES,
  MODEL_IMPROVEMENT_TARGET_MODULES,
} from "@/components/knowledge/knowledge-constants"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AlertTriangle, ArrowLeft, Layers, ListChecks, Loader2, Plus } from "lucide-react"

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
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function truncateSummary(s: string, max = 180): string {
  const t = s.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

const QUEUE_TOOLTIP =
  "Model improvement queue collects errors, human overrides, benchmark failures, drift alerts, and low-confidence cases for future model updates."

export function KnowledgeModelImprovementWorkspace() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [listErr, setListErr] = useState("")

  const [filterStatus, setFilterStatus] = useState<string>("")

  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)

  const [patchPriority, setPatchPriority] = useState<string>("medium")
  const [patchStatus, setPatchStatus] = useState<string>("open")
  const [patchSummary, setPatchSummary] = useState("")
  const [patchBusy, setPatchBusy] = useState(false)
  const [patchErr, setPatchErr] = useState("")
  const [patchOk, setPatchOk] = useState("")

  const [actionBusy, setActionBusy] = useState<string>("")

  const [createSourceType, setCreateSourceType] = useState<string>("error_case")
  const [createTarget, setCreateTarget] = useState<string>("spectracheck")
  const [createLinkedType, setCreateLinkedType] = useState<string>("")
  const [createLinkedId, setCreateLinkedId] = useState("")
  const [createPriority, setCreatePriority] = useState<string>("medium")
  const [createSummary, setCreateSummary] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState("")

  const loadRows = useCallback(async () => {
    setLoading(true)
    setListErr("")
    try {
      const params = new URLSearchParams()
      params.set("limit", "500")
      if (filterStatus.trim()) params.set("status", filterStatus.trim())
      const raw = await apiFetch<unknown>(`/knowledge/model-improvement-queue?${params.toString()}`, { method: "GET" })
      setRows(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setRows([])
      setListErr(formatApiError(e, "Could not load model improvement queue."))
    } finally {
      setLoading(false)
    }
  }, [filterStatus])

  useEffect(() => {
    void loadRows()
  }, [loadRows])

  useEffect(() => {
    if (!selected) return
    setPatchPriority(readRecordString(selected, "priority") ?? "medium")
    setPatchStatus(readRecordString(selected, "status") ?? "open")
    setPatchSummary(readRecordString(selected, "summary") ?? "")
  }, [selected])

  async function submitPatch() {
    const id = selected ? readRecordNumber(selected, "id") : null
    if (id == null) return
    const summary = patchSummary.trim()
    if (!summary) {
      setPatchErr("summary is required.")
      return
    }
    setPatchErr("")
    setPatchOk("")
    setPatchBusy(true)
    try {
      const updated = await apiFetch<unknown>(`/knowledge/model-improvement-queue/${id}`, {
        method: "PATCH",
        body: {
          priority: patchPriority,
          status: patchStatus,
          summary,
        },
      })
      setPatchOk("Item updated.")
      setSelected(isRecord(updated) ? updated : null)
      await loadRows()
    } catch (e) {
      setPatchErr(formatApiError(e, "PATCH failed."))
    } finally {
      setPatchBusy(false)
    }
  }

  async function patchStatusOnly(next: "in_review" | "resolved" | "dismissed") {
    const id = selected ? readRecordNumber(selected, "id") : null
    if (id == null) return
    setPatchErr("")
    setPatchOk("")
    setActionBusy(next)
    try {
      const updated = await apiFetch<unknown>(`/knowledge/model-improvement-queue/${id}`, {
        method: "PATCH",
        body: {
          status: next,
        },
      })
      setPatchOk(`status → ${next}`)
      setSelected(isRecord(updated) ? updated : null)
      await loadRows()
    } catch (e) {
      setPatchErr(formatApiError(e, "Status update failed."))
    } finally {
      setActionBusy("")
    }
  }

  async function submitCreate() {
    const summary = createSummary.trim()
    if (!summary) {
      setCreateErr("summary is required.")
      return
    }
    setCreateErr("")
    setCreateOk("")
    setCreateBusy(true)
    try {
      const body: Record<string, unknown> = {
        source_type: createSourceType,
        target_module: createTarget,
        priority: createPriority,
        status: "open",
        summary,
        metadata_json: {},
      }
      const lt = createLinkedType.trim()
      if (lt) body.linked_record_type = lt
      const lidRaw = createLinkedId.trim()
      if (lidRaw) {
        const n = Number.parseInt(lidRaw, 10)
        if (!Number.isFinite(n) || n < 1) {
          setCreateErr("linked_record_id must be a positive integer when set.")
          setCreateBusy(false)
          return
        }
        body.linked_record_id = n
      }
      await apiFetch("/knowledge/model-improvement-queue", { method: "POST", body })
      setCreateOk("Queue item created.")
      setCreateSummary("")
      setCreateLinkedId("")
      setCreateLinkedType("")
      await loadRows()
    } catch (e) {
      setCreateErr(formatApiError(e, "Create failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  const selId = selected ? readRecordNumber(selected, "id") : null

  return (
    <TooltipProvider delayDuration={200}>
      <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/knowledge">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Knowledge Library
            </Link>
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void loadRows()}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Refresh
          </Button>
          <div className="inline-flex items-center gap-1.5">
            <span className="text-sm font-medium">Model improvement queue</span>
            <InfoTooltip content={QUEUE_TOOLTIP} label="About the queue" />
          </div>
        </div>

        <div>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Model improvement queue</h1>
          <p className="text-sm text-muted-foreground">
            Operational backlog for model iteration — prioritized cases flagged for retraining, data augmentation, or review.
          </p>
        </div>

        <Alert>
          <AlertTriangle className="h-4 w-4" aria-hidden />
          <AlertTitle className="text-sm">Workflow metadata</AlertTitle>
          <AlertDescription className="text-sm text-muted-foreground">
            Queue entries summarize cases for prioritization; they do not certify root cause or model defects without
            engineering review.
          </AlertDescription>
        </Alert>

        <ModuleCard
          accent="teal"
          eyebrow="Backlog"
          title="Queue"
          icon={ListChecks}
          description="Improvement queue entries filterable by status — each item captures target module, source type, priority, linked record, and a human-readable summary."
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2">
                <Label>status filter</Label>
                <Select value={filterStatus || "__all"} onValueChange={(v) => setFilterStatus(v === "__all" ? "" : v)}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">All</SelectItem>
                    {MODEL_IMPROVEMENT_STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void loadRows()}>
                Apply
              </Button>
            </div>

            {listErr ? (
              <p className="text-sm text-destructive">{listErr}</p>
            ) : loading ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading…
              </p>
            ) : (
              <div className="table-scroll min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">id</TableHead>
                      <TableHead>target_module</TableHead>
                      <TableHead>source_type</TableHead>
                      <TableHead>priority</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead className="max-w-[260px]">summary</TableHead>
                      <TableHead>linked_record</TableHead>
                      <TableHead>created_at</TableHead>
                      <TableHead className="w-[90px]">open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((row, idx) => {
                      const id = readRecordNumber(row, "id")
                      const sum = readRecordString(row, "summary") ?? ""
                      const lt = readRecordString(row, "linked_record_type")
                      const lid = readRecordNumber(row, "linked_record_id")
                      const linked =
                        lt != null || lid != null
                          ? `${lt ?? "—"} · ${lid != null ? lid : "—"}`
                          : "—"
                      return (
                        <TableRow key={id != null ? `mi-${id}` : `mi-${idx}`}>
                          <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "target_module") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "source_type") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "priority") ?? "—"}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                          </TableCell>
                          <TableCell className="max-w-[260px] truncate text-xs" title={sum}>
                            {sum ? truncateSummary(sum, 120) : "—"}
                          </TableCell>
                          <TableCell className="max-w-[160px] truncate font-mono text-[11px]" title={linked}>
                            {linked}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatWhen(readRecordString(row, "created_at"))}
                          </TableCell>
                          <TableCell>
                            {id != null ? (
                              <Button
                                type="button"
                                size="sm"
                                variant={selected && readRecordNumber(selected, "id") === id ? "secondary" : "outline"}
                                className="h-8"
                                onClick={() => setSelected(row)}
                              >
                                Open
                              </Button>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                {rows.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No rows returned.</p> : null}
              </div>
            )}
          </div>
        </ModuleCard>

        <ModuleCard
          accent="teal"
          eyebrow="Create"
          title="Add queue item"
          icon={Plus}
          description="Add a new model improvement case to the queue — specify source type, target module, priority, linked record, and a summary of the issue."
        >
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label>source_type</Label>
              <Select value={createSourceType} onValueChange={setCreateSourceType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_IMPROVEMENT_SOURCE_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>target_module</Label>
              <Select value={createTarget} onValueChange={setCreateTarget}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_IMPROVEMENT_TARGET_MODULES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>priority</Label>
              <Select value={createPriority} onValueChange={setCreatePriority}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_IMPROVEMENT_PRIORITIES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>linked_record_type</Label>
              <Select value={createLinkedType || "__none__"} onValueChange={(v) => setCreateLinkedType(v === "__none__" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="optional" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {KNOWLEDGE_REVIEW_RECORD_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mi-linked-id">linked_record_id</Label>
              <Input
                id="mi-linked-id"
                className="font-mono"
                value={createLinkedId}
                onChange={(e) => setCreateLinkedId(e.target.value)}
                placeholder="optional"
              />
            </div>
            <div className="space-y-2 md:col-span-3">
              <Label htmlFor="mi-sum">summary</Label>
              <Textarea id="mi-sum" rows={4} value={createSummary} onChange={(e) => setCreateSummary(e.target.value)} />
            </div>
            <div className="md:col-span-3 flex flex-wrap items-center gap-2">
              <Button type="button" disabled={createBusy} onClick={() => void submitCreate()}>
                {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                Create
              </Button>
              {createErr ? <span className="text-sm text-destructive">{createErr}</span> : null}
              {createOk ? <span className="text-sm text-muted-foreground">{createOk}</span> : null}
            </div>
          </div>
        </ModuleCard>

        {selected && selId != null ? (
          <ModuleCard
            accent="teal"
            eyebrow="Edit"
            title={
              <span>
                Item{" "}
                <code className="font-mono text-xs">
                  PATCH /knowledge/model-improvement-queue/{selId}
                </code>
              </span>
            }
            icon={Layers}
            description="Quick actions set status via PATCH; full edit below."
          >
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={actionBusy !== ""}
                  onClick={() => void patchStatusOnly("in_review")}
                >
                  {actionBusy === "in_review" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  In review
                </Button>
                <Button
                  type="button"
                  variant="default"
                  size="sm"
                  disabled={actionBusy !== ""}
                  onClick={() => void patchStatusOnly("resolved")}
                >
                  {actionBusy === "resolved" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Resolve
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={actionBusy !== ""}
                  onClick={() => void patchStatusOnly("dismissed")}
                >
                  {actionBusy === "dismissed" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Dismiss
                </Button>
              </div>

              {patchErr ? (
                <Alert variant="destructive">
                  <AlertDescription className="text-sm">{patchErr}</AlertDescription>
                </Alert>
              ) : null}
              {patchOk ? (
                <Alert>
                  <AlertDescription className="text-sm">{patchOk}</AlertDescription>
                </Alert>
              ) : null}

              <div className="grid gap-3 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>priority</Label>
                  <Select value={patchPriority} onValueChange={setPatchPriority}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MODEL_IMPROVEMENT_PRIORITIES.map((p) => (
                        <SelectItem key={p} value={p}>
                          {p}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>status</Label>
                  <Select value={patchStatus} onValueChange={setPatchStatus}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MODEL_IMPROVEMENT_STATUSES.map((s) => (
                        <SelectItem key={s} value={s}>
                          {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-3">
                  <Label htmlFor="mi-patch-sum">summary</Label>
                  <Textarea id="mi-patch-sum" rows={5} value={patchSummary} onChange={(e) => setPatchSummary(e.target.value)} />
                </div>
              </div>
              <Button type="button" disabled={patchBusy} onClick={() => void submitPatch()}>
                {patchBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                Save PATCH
              </Button>

              <DeveloperJsonPanel data={selected} />
            </div>
          </ModuleCard>
        ) : null}
      </div>
    </TooltipProvider>
  )
}
