"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { KNOWLEDGE_TASK_STATUSES } from "@/components/knowledge/knowledge-constants"
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
import { AlertTriangle, ArrowLeft, ClipboardCheck, Filter, ListChecks, Loader2 } from "lucide-react"

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

const RECORD_TYPE_FILTERS = ["", "reaction", "analytical", "regulatory", "citation", "training_candidate", "benchmark_candidate"] as const

export function KnowledgeReviewWorkspace() {
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [listErr, setListErr] = useState("")

  const [filterStatus, setFilterStatus] = useState<string>("")
  const [filterRecordType, setFilterRecordType] = useState<string>("")

  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)

  const [patchStatus, setPatchStatus] = useState<string>("open")
  const [patchReviewerName, setPatchReviewerName] = useState("")
  const [patchReviewerComment, setPatchReviewerComment] = useState("")
  const [patchBusy, setPatchBusy] = useState(false)
  const [patchErr, setPatchErr] = useState("")
  const [patchOk, setPatchOk] = useState("")

  const loadTasks = useCallback(async () => {
    setLoading(true)
    setListErr("")
    try {
      const params = new URLSearchParams()
      params.set("limit", "500")
      if (filterStatus.trim()) params.set("status", filterStatus.trim())
      if (filterRecordType.trim()) params.set("record_type", filterRecordType.trim())
      const raw = await apiFetch<unknown>(`/knowledge/review-tasks?${params.toString()}`, { method: "GET" })
      setTasks(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setTasks([])
      setListErr(formatApiError(e, "Could not load review tasks."))
    } finally {
      setLoading(false)
    }
  }, [filterStatus, filterRecordType])

  useEffect(() => {
    void loadTasks()
  }, [loadTasks])

  useEffect(() => {
    if (!selected) return
    setPatchStatus(readRecordString(selected, "status") ?? "open")
    setPatchReviewerName(readRecordString(selected, "reviewer_name") ?? "")
    setPatchReviewerComment(readRecordString(selected, "reviewer_comment") ?? "")
  }, [selected])

  async function submitPatch() {
    const tid = selected ? readRecordNumber(selected, "id") : null
    if (tid == null) return
    const name = patchReviewerName.trim()
    const comment = patchReviewerComment.trim()
    if (!name || !comment) {
      setPatchErr("reviewer_name and reviewer_comment are required to update a review task.")
      return
    }
    setPatchErr("")
    setPatchOk("")
    setPatchBusy(true)
    try {
      const updated = await apiFetch<unknown>(`/knowledge/review-tasks/${tid}`, {
        method: "PATCH",
        body: {
          status: patchStatus,
          reviewer_name: name,
          reviewer_comment: comment,
          metadata_json: {},
        },
      })
      setPatchOk("Task updated.")
      setSelected(isRecord(updated) ? updated : null)
      await loadTasks()
    } catch (e) {
      setPatchErr(formatApiError(e, "Update task failed."))
    } finally {
      setPatchBusy(false)
    }
  }

  function recordReviewHref(recordType: string | undefined, extractionRunId: number | null | undefined): string | null {
    if (extractionRunId == null) return null
    const r = (recordType ?? "").toLowerCase()
    if (r === "reaction") return `/knowledge/reactions?run_id=${extractionRunId}`
    if (r === "analytical") return `/knowledge/analytical?run_id=${extractionRunId}`
    if (r === "regulatory") return `/knowledge/regulatory?run_id=${extractionRunId}`
    return null
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/knowledge">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Knowledge Library
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/extractions">Extractions</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/reactions">Reactions</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/analytical">Analytical</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/regulatory">Regulatory</Link>
        </Button>
      </div>

      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-amber)" }}
        >
          MolTrace · Knowledge · Review Queue
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Knowledge review tasks</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Workflow queue for extracted records. Status changes require reviewer identity and rationale.
        </p>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Review queue only</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Completing a task here does not certify scientific accuracy — it tracks operational workflow state.
        </AlertDescription>
      </Alert>

      <ModuleCard
        accent="teal"
        eyebrow="Filters"
        title="Filters"
        icon={Filter}
        description="Filter review tasks by status and record type to focus on the most relevant claims in the curation queue."
      >
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-2">
            <Label>status</Label>
            <Select value={filterStatus || "__all__"} onValueChange={(v) => setFilterStatus(v === "__all__" ? "" : v)}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All</SelectItem>
                {KNOWLEDGE_TASK_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>record_type</Label>
            <Select
              value={filterRecordType || "__all__"}
              onValueChange={(v) => setFilterRecordType(v === "__all__" ? "" : v)}
            >
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All</SelectItem>
                {RECORD_TYPE_FILTERS.filter((x) => x !== "").map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void loadTasks()}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Apply
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Records"
        title="Review tasks"
        icon={ListChecks}
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : listErr ? (
            <p className="text-sm text-destructive">{listErr}</p>
          ) : tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tasks returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>record_type</TableHead>
                  <TableHead className="w-[88px]">record_id</TableHead>
                  <TableHead className="w-[96px]">run_id</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead className="max-w-[200px]">title</TableHead>
                  <TableHead>updated_at</TableHead>
                  <TableHead className="w-[90px]">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const rt = readRecordString(row, "record_type")
                  const rid = readRecordNumber(row, "record_id")
                  const erun = readRecordNumber(row, "extraction_run_id")
                  const href = recordReviewHref(rt, erun)
                  return (
                    <TableRow key={id != null ? `t-${id}` : `t-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{rt ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{rid ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{erun ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                      </TableCell>
                      <TableCell className="max-w-[220px] truncate text-sm">{readRecordString(row, "title") ?? "—"}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at"))}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
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
                          ) : null}
                          {href ? (
                            <Button type="button" size="sm" variant="ghost" className="h-8 px-2 text-xs" asChild>
                              <Link href={href}>Records</Link>
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      {selected ? (
        <ModuleCard
          accent="teal"
          eyebrow="Action"
          title="Update task"
          icon={ClipboardCheck}
          description="Record an expert review decision on this extracted knowledge claim — approve, reject, or flag for further review."
        >
          <div className="space-y-4">
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
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>status</Label>
                <Select value={patchStatus} onValueChange={setPatchStatus}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KNOWLEDGE_TASK_STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="pt-rev-name">reviewer_name</Label>
                <Input id="pt-rev-name" value={patchReviewerName} onChange={(e) => setPatchReviewerName(e.target.value)} />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="pt-rev-comment">reviewer_comment</Label>
                <Textarea
                  id="pt-rev-comment"
                  value={patchReviewerComment}
                  onChange={(e) => setPatchReviewerComment(e.target.value)}
                  rows={4}
                />
              </div>
            </div>
            <Button type="button" disabled={patchBusy} onClick={() => void submitPatch()}>
              {patchBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
              Save task update
            </Button>
            <DeveloperJsonPanel data={selected} />
          </div>
        </ModuleCard>
      ) : null}
    </div>
  )
}
