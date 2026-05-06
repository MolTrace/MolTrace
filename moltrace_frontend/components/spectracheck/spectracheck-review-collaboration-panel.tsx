"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch, AUTH_USER_STORAGE_KEY } from "@/lib/api/client"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { fetchSessionAudit } from "@/src/lib/spectracheck/spectracheck-backend-session"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Separator } from "@/components/ui/separator"
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

const COMMENT_TYPES = ["note", "question", "concern", "contradiction", "approval_note"] as const
const APPROVAL_DECISIONS = [
  "approved_plausible",
  "approved_confirmed",
  "rejected",
  "needs_changes",
  "deferred",
] as const

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

function normalizeRows(data: unknown, keys: string[]): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of keys) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function formatApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    if (isRecord(d) && typeof d.message === "string") return d.message
    return err.message
  }
  if (err instanceof Error) return err.message
  return fallback
}

function readStoredUserEmail(): string {
  if (typeof window === "undefined") return ""
  try {
    const raw = window.localStorage.getItem(AUTH_USER_STORAGE_KEY)
    if (!raw) return ""
    const j = JSON.parse(raw) as unknown
    if (!isRecord(j)) return ""
    const em = readStr(j, ["email", "user_email", "userEmail"])
    return em
  } catch {
    return ""
  }
}

/** Display label; avoids implying structural confirmation unless approved_confirmed. */
function approvalDecisionLabel(decision: string): string {
  const d = decision.trim().toLowerCase()
  switch (d) {
    case "approved_plausible":
      return "Approved (plausible)"
    case "approved_confirmed":
      return "Approved (confirmed)"
    case "rejected":
      return "Rejected"
    case "needs_changes":
      return "Needs changes"
    case "deferred":
      return "Deferred"
    default:
      return decision || "—"
  }
}

function normalizeAuditEvents(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (isRecord(data)) {
    if (Array.isArray(data.events)) return data.events
    if (Array.isArray(data.items)) return data.items
    if (Array.isArray(data.audit_events)) return data.audit_events
  }
  return []
}

export type SpectraCheckReviewCollaborationPanelProps = {
  sessionId: string | null
}

export function SpectraCheckReviewCollaborationPanel({ sessionId }: SpectraCheckReviewCollaborationPanelProps) {
  const sid = sessionId?.trim() ?? ""
  const { evidenceItems } = useSpectraCheckEvidence()

  const [panelOpen, setPanelOpen] = useState(true)

  const [reviewers, setReviewers] = useState<Record<string, unknown>[]>([])
  const [comments, setComments] = useState<Record<string, unknown>[]>([])
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([])
  const [approvals, setApprovals] = useState<Record<string, unknown>[]>([])
  const [loadErr, setLoadErr] = useState("")
  const [busy, setBusy] = useState(false)

  const [reviewerEmail, setReviewerEmail] = useState("")
  const [reviewerBusy, setReviewerBusy] = useState(false)
  const [reviewerErr, setReviewerErr] = useState("")

  const [commentType, setCommentType] = useState<string>(COMMENT_TYPES[0])
  const [commentText, setCommentText] = useState("")
  const [commentEvidenceId, setCommentEvidenceId] = useState<string>("")
  const [commentBusy, setCommentBusy] = useState(false)
  const [commentErr, setCommentErr] = useState("")

  const [editCommentId, setEditCommentId] = useState<string | null>(null)
  const [editCommentDraft, setEditCommentDraft] = useState("")
  const [editCommentBusy, setEditCommentBusy] = useState(false)
  const [editCommentErr, setEditCommentErr] = useState("")

  const [taskTitle, setTaskTitle] = useState("")
  const [taskDescription, setTaskDescription] = useState("")
  const [taskBusy, setTaskBusy] = useState(false)
  const [taskErr, setTaskErr] = useState("")

  const [taskPatchBusyId, setTaskPatchBusyId] = useState<string | null>(null)
  const [taskPatchErr, setTaskPatchErr] = useState("")

  const [approvalDecision, setApprovalDecision] = useState<string>(APPROVAL_DECISIONS[0])
  const [approvalRationale, setApprovalRationale] = useState("")
  const [approvalName, setApprovalName] = useState("")
  const [approvalEmail, setApprovalEmail] = useState("")
  const [approvalBusy, setApprovalBusy] = useState(false)
  const [approvalErr, setApprovalErr] = useState("")

  const [auditSummary, setAuditSummary] = useState<{ count: number; preview: string } | null>(null)
  const [auditErr, setAuditErr] = useState("")

  const refresh = useCallback(async () => {
    if (!sid) return
    setBusy(true)
    setLoadErr("")
    try {
      const [r, c, t, a] = await Promise.all([
        apiFetch<unknown>(`/spectracheck/sessions/${encodeURIComponent(sid)}/reviewers`, { method: "GET" }),
        apiFetch<unknown>(`/spectracheck/sessions/${encodeURIComponent(sid)}/comments`, { method: "GET" }),
        apiFetch<unknown>(`/spectracheck/sessions/${encodeURIComponent(sid)}/review-tasks`, { method: "GET" }),
        apiFetch<unknown>(`/spectracheck/sessions/${encodeURIComponent(sid)}/approvals`, { method: "GET" }),
      ])
      setReviewers(normalizeRows(r, ["reviewers", "items", "results"]))
      setComments(normalizeRows(c, ["comments", "items", "results"]))
      setTasks(normalizeRows(t, ["tasks", "review_tasks", "items", "results"]))
      setApprovals(normalizeRows(a, ["approvals", "items", "results"]))
    } catch (err) {
      setLoadErr(formatApiError(err, "Could not load review data."))
    } finally {
      setBusy(false)
    }
  }, [sid])

  useEffect(() => {
    if (!sid) {
      setReviewers([])
      setComments([])
      setTasks([])
      setApprovals([])
      setLoadErr("")
      return
    }
    void refresh()
  }, [sid, refresh])

  useEffect(() => {
    const em = readStoredUserEmail()
    if (em) setApprovalEmail(em)
  }, [sid])

  useEffect(() => {
    if (!sid) {
      setAuditSummary(null)
      return
    }
    let cancelled = false
    setAuditErr("")
    void (async () => {
      try {
        const raw = await fetchSessionAudit(sid)
        if (cancelled) return
        const ev = normalizeAuditEvents(raw)
        const count = ev.length
        let preview = ""
        const last = ev[0]
        if (last && isRecord(last)) {
          preview = readStr(last, ["message", "action", "event_type", "type"]) || JSON.stringify(last).slice(0, 120)
        }
        setAuditSummary({ count, preview })
      } catch (err) {
        if (!cancelled) setAuditErr(formatApiError(err, "Audit summary unavailable."))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [sid])

  async function submitReviewer() {
    if (!sid) return
    const email = reviewerEmail.trim()
    if (!email) {
      setReviewerErr("Email is required.")
      return
    }
    setReviewerBusy(true)
    setReviewerErr("")
    try {
      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/reviewers`, {
        method: "POST",
        body: { email },
      })
      setReviewerEmail("")
      await refresh()
    } catch (err) {
      setReviewerErr(formatApiError(err, "Assign reviewer failed."))
    } finally {
      setReviewerBusy(false)
    }
  }

  async function submitComment() {
    if (!sid) return
    const comment = commentText.trim()
    if (!comment) {
      setCommentErr("Comment text is required.")
      return
    }
    setCommentBusy(true)
    setCommentErr("")
    try {
      const body: Record<string, unknown> = {
        comment_type: commentType,
        comment,
      }
      if (commentEvidenceId.trim()) body.evidence_id = commentEvidenceId.trim()

      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/comments`, {
        method: "POST",
        body,
      })
      setCommentText("")
      setCommentEvidenceId("")
      await refresh()
    } catch (err) {
      setCommentErr(formatApiError(err, "Add comment failed."))
    } finally {
      setCommentBusy(false)
    }
  }

  async function saveEditedComment(commentId: string) {
    if (!sid) return
    const comment = editCommentDraft.trim()
    if (!comment) {
      setEditCommentErr("Comment text is required.")
      return
    }
    setEditCommentBusy(true)
    setEditCommentErr("")
    try {
      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/comments/${encodeURIComponent(commentId)}`, {
        method: "PATCH",
        body: { comment },
      })
      setEditCommentId(null)
      setEditCommentDraft("")
      await refresh()
    } catch (err) {
      setEditCommentErr(formatApiError(err, "Update comment failed."))
    } finally {
      setEditCommentBusy(false)
    }
  }

  async function submitTask() {
    if (!sid) return
    const title = taskTitle.trim()
    if (!title) {
      setTaskErr("Title is required.")
      return
    }
    setTaskBusy(true)
    setTaskErr("")
    try {
      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/review-tasks`, {
        method: "POST",
        body: {
          title,
          description: taskDescription.trim() || null,
        },
      })
      setTaskTitle("")
      setTaskDescription("")
      await refresh()
    } catch (err) {
      setTaskErr(formatApiError(err, "Create task failed."))
    } finally {
      setTaskBusy(false)
    }
  }

  async function resolveTask(taskId: string) {
    if (!sid) return
    setTaskPatchBusyId(taskId)
    setTaskPatchErr("")
    try {
      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/review-tasks/${encodeURIComponent(taskId)}`, {
        method: "PATCH",
        body: { status: "resolved" },
      })
      await refresh()
    } catch (err) {
      setTaskPatchErr(formatApiError(err, "Update task failed."))
    } finally {
      setTaskPatchBusyId(null)
    }
  }

  async function submitApproval() {
    if (!sid) return
    const rationale = approvalRationale.trim()
    if (!rationale) {
      setApprovalErr("Rationale is required.")
      return
    }
    setApprovalBusy(true)
    setApprovalErr("")
    try {
      const body: Record<string, unknown> = {
        decision: approvalDecision,
        rationale,
      }
      const an = approvalName.trim()
      const ae = approvalEmail.trim()
      if (an) body.approver_name = an
      if (ae) body.approver_email = ae

      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/approvals`, {
        method: "POST",
        body,
      })
      setApprovalRationale("")
      await refresh()
    } catch (err) {
      setApprovalErr(formatApiError(err, "Record approval failed."))
    } finally {
      setApprovalBusy(false)
    }
  }

  const humanReviewRequired = useMemo(() => sid.length > 0 && !busy && approvals.length === 0 && !loadErr, [sid, busy, approvals.length, loadErr])

  const evidenceOptions = useMemo(
    () =>
      evidenceItems
        .filter((i) => i.backendEvidenceId != null)
        .map((i) => ({
          id: String(i.backendEvidenceId),
          label: i.title?.trim() || i.layer || i.id,
        })),
    [evidenceItems],
  )

  if (!sid) {
    return (
      <Card className="min-w-0 border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Review & Collaboration</CardTitle>
          <CardDescription>
            Connect a saved SpectraCheck session (Session card) to assign reviewers, comments, tasks, and approvals.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card className="min-w-0 border-muted">
      <Collapsible open={panelOpen} onOpenChange={setPanelOpen}>
        <CardHeader className="pb-2">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 text-left hover:opacity-90">
            <div className="min-w-0 space-y-1">
              <CardTitle className="text-base">Review & Collaboration</CardTitle>
              <CardDescription>
                Session-linked review workflow for this SpectraCheck workspace (requires backend endpoints).
              </CardDescription>
            </div>
            <ChevronDown
              className={cn("h-4 w-4 shrink-0 transition-transform", panelOpen && "rotate-180")}
              aria-hidden
            />
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="space-y-8 pt-0">
            {loadErr ? (
              <Alert variant="destructive">
                <AlertTitle>Load</AlertTitle>
                <AlertDescription>{loadErr}</AlertDescription>
              </Alert>
            ) : null}

            {humanReviewRequired ? (
              <Alert>
                <AlertTitle>Human review required</AlertTitle>
                <AlertDescription>No approval decision is recorded for this session yet.</AlertDescription>
              </Alert>
            ) : null}

            {busy ? <p className="text-xs text-muted-foreground">Loading review data…</p> : null}

            <div className="space-y-3">
              <h3 className="text-sm font-medium">Assigned reviewers</h3>
              {reviewerErr ? <p className="text-xs text-destructive">{reviewerErr}</p> : null}
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="min-w-0 flex-1 space-y-2">
                  <Label htmlFor="sc-rc-reviewer-email">Email</Label>
                  <Input
                    id="sc-rc-reviewer-email"
                    type="email"
                    value={reviewerEmail}
                    onChange={(e) => setReviewerEmail(e.target.value)}
                    autoComplete="email"
                  />
                </div>
                <Button type="button" size="sm" disabled={reviewerBusy} onClick={() => void submitReviewer()}>
                  {reviewerBusy ? "Assigning…" : "Assign reviewer"}
                </Button>
              </div>
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Email</TableHead>
                      <TableHead className="text-xs">Role</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reviewers.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-xs text-muted-foreground">
                          No reviewers assigned.
                        </TableCell>
                      </TableRow>
                    ) : (
                      reviewers.map((row, i) => (
                        <TableRow key={readStr(row, ["id", "reviewer_id"]) || String(i)}>
                          <TableCell className="max-w-[14rem] font-mono text-[10px] break-all">
                            {readStr(row, ["email", "user_email", "reviewer_email"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">{readStr(row, ["role"]) || "—"}</TableCell>
                          <TableCell className="text-xs">{readStr(row, ["status"]) || "—"}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            <Separator />

            <div className="space-y-3">
              <h3 className="text-sm font-medium">Evidence comments</h3>
              {commentErr ? <p className="text-xs text-destructive">{commentErr}</p> : null}
              {editCommentErr ? <p className="text-xs text-destructive">{editCommentErr}</p> : null}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Comment type</Label>
                  <Select value={commentType} onValueChange={setCommentType}>
                    <SelectTrigger id="sc-rc-comment-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {COMMENT_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sc-rc-evidence-link">Linked evidence item (optional)</Label>
                  <Select value={commentEvidenceId || "__none__"} onValueChange={(v) => setCommentEvidenceId(v === "__none__" ? "" : v)}>
                    <SelectTrigger id="sc-rc-evidence-link">
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {evidenceOptions.map((o) => (
                        <SelectItem key={o.id} value={o.id}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="sc-rc-comment-text">Comment</Label>
                <Textarea
                  id="sc-rc-comment-text"
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  rows={3}
                />
              </div>
              <Button type="button" size="sm" disabled={commentBusy} onClick={() => void submitComment()}>
                {commentBusy ? "Adding…" : "Add comment"}
              </Button>

              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Type</TableHead>
                      <TableHead className="text-xs">Text</TableHead>
                      <TableHead className="text-xs text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {comments.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-xs text-muted-foreground">
                          No comments yet.
                        </TableCell>
                      </TableRow>
                    ) : (
                      comments.map((row, i) => {
                        const cid = readStr(row, ["id", "comment_id"])
                        const editing = editCommentId === cid
                        const txt = readStr(row, ["text", "comment", "body"]) || ""
                        return (
                          <TableRow key={cid || String(i)}>
                            <TableCell className="align-top text-xs">
                              <Badge variant="outline" className="font-normal">
                                {readStr(row, ["comment_type", "type"]) || "—"}
                              </Badge>
                            </TableCell>
                            <TableCell className="max-w-prose align-top text-xs">
                              {editing ? (
                                <Textarea
                                  value={editCommentDraft}
                                  onChange={(e) => setEditCommentDraft(e.target.value)}
                                  rows={2}
                                  className="text-xs"
                                />
                              ) : (
                                <span className="whitespace-pre-wrap break-words">{txt}</span>
                              )}
                            </TableCell>
                            <TableCell className="align-top text-right">
                              {cid ? (
                                editing ? (
                                  <div className="flex flex-wrap justify-end gap-1">
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      disabled={editCommentBusy}
                                      onClick={() => void saveEditedComment(cid)}
                                    >
                                      Save
                                    </Button>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => {
                                        setEditCommentId(null)
                                        setEditCommentDraft("")
                                      }}
                                    >
                                      Cancel
                                    </Button>
                                  </div>
                                ) : (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                      setEditCommentId(cid)
                                      setEditCommentDraft(txt)
                                    }}
                                  >
                                    Edit
                                  </Button>
                                )
                              ) : null}
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            <Separator />

            <div className="space-y-3">
              <h3 className="text-sm font-medium">Review tasks</h3>
              {taskErr ? <p className="text-xs text-destructive">{taskErr}</p> : null}
              {taskPatchErr ? <p className="text-xs text-destructive">{taskPatchErr}</p> : null}
              <div className="space-y-2">
                <Label htmlFor="sc-rc-task-title">Title</Label>
                <Input id="sc-rc-task-title" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sc-rc-task-desc">Description (optional)</Label>
                <Textarea id="sc-rc-task-desc" value={taskDescription} onChange={(e) => setTaskDescription(e.target.value)} rows={2} />
              </div>
              <Button type="button" size="sm" disabled={taskBusy} onClick={() => void submitTask()}>
                {taskBusy ? "Creating…" : "Create task"}
              </Button>

              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Title</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tasks.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-xs text-muted-foreground">
                          No tasks yet.
                        </TableCell>
                      </TableRow>
                    ) : (
                      tasks.map((row, i) => {
                        const tid = readStr(row, ["id", "task_id"])
                        const st = readStr(row, ["status"]) || "—"
                        return (
                          <TableRow key={tid || String(i)}>
                            <TableCell className="max-w-[12rem] text-xs">{readStr(row, ["title", "summary"]) || "—"}</TableCell>
                            <TableCell className="text-xs">{st}</TableCell>
                            <TableCell className="text-right">
                              {tid ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  disabled={taskPatchBusyId === tid || st === "resolved"}
                                  onClick={() => void resolveTask(tid)}
                                >
                                  {taskPatchBusyId === tid ? "Updating…" : "Mark resolved"}
                                </Button>
                              ) : null}
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            <Separator />

            <div className="space-y-3">
              <h3 className="text-sm font-medium">Approval decisions</h3>
              <p className="text-xs text-muted-foreground">
                Recorded decisions use labels such as &quot;Approved (plausible)&quot; or &quot;Approved (confirmed)&quot; only when the
                stored decision matches <code className="text-[10px]">approved_confirmed</code>.
              </p>
              {approvalErr ? <p className="text-xs text-destructive">{approvalErr}</p> : null}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Decision</Label>
                  <Select value={approvalDecision} onValueChange={setApprovalDecision}>
                    <SelectTrigger id="sc-rc-approval-decision">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {APPROVAL_DECISIONS.map((d) => (
                        <SelectItem key={d} value={d}>
                          {approvalDecisionLabel(d)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sc-rc-approver-name">Approver name (optional)</Label>
                  <Input id="sc-rc-approver-name" value={approvalName} onChange={(e) => setApprovalName(e.target.value)} />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="sc-rc-approver-email">Approver email (optional)</Label>
                  <Input
                    id="sc-rc-approver-email"
                    type="email"
                    value={approvalEmail}
                    onChange={(e) => setApprovalEmail(e.target.value)}
                    autoComplete="email"
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="sc-rc-rationale">Rationale (required)</Label>
                  <Textarea
                    id="sc-rc-rationale"
                    value={approvalRationale}
                    onChange={(e) => setApprovalRationale(e.target.value)}
                    rows={4}
                  />
                </div>
              </div>
              <Button type="button" size="sm" disabled={approvalBusy} onClick={() => void submitApproval()}>
                {approvalBusy ? "Recording…" : "Record approval"}
              </Button>

              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Decision</TableHead>
                      <TableHead className="text-xs">Rationale</TableHead>
                      <TableHead className="text-xs">When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {approvals.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-xs text-muted-foreground">
                          No approvals recorded.
                        </TableCell>
                      </TableRow>
                    ) : (
                      approvals.map((row, i) => {
                        const dec = readStr(row, ["decision", "approval_decision"]) || "—"
                        return (
                          <TableRow key={readStr(row, ["id", "approval_id"]) || String(i)}>
                            <TableCell className="align-top text-xs font-medium">
                              {approvalDecisionLabel(dec)}
                            </TableCell>
                            <TableCell className="max-w-prose align-top text-xs">
                              <span className="whitespace-pre-wrap break-words">
                                {readStr(row, ["rationale", "reason", "comment"]) || "—"}
                              </span>
                            </TableCell>
                            <TableCell className="whitespace-nowrap align-top text-[10px] text-muted-foreground">
                              {readStr(row, ["created_at", "createdAt", "recorded_at"]) || "—"}
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            <Separator />

            <div className="space-y-2">
              <h3 className="text-sm font-medium">Audit trail</h3>
              {auditErr ? <p className="text-xs text-destructive">{auditErr}</p> : null}
              {auditSummary ? (
                <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                  <p>
                    <span className="font-medium text-foreground">{auditSummary.count}</span> audit event(s) on file for this
                    session.
                  </p>
                  {auditSummary.preview ? (
                    <p className="mt-1 line-clamp-2 font-mono text-[10px]">Latest: {auditSummary.preview}</p>
                  ) : null}
                  <p className="mt-2 text-[11px]">
                    Full session review and audit tables remain available under the Overview tab (
                    <span className="text-foreground">Review gate</span> / <span className="text-foreground">Audit trail</span>
                    ) when connected to the same session.
                  </p>
                </div>
              ) : !auditErr ? (
                <p className="text-xs text-muted-foreground">Loading audit summary…</p>
              ) : null}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
