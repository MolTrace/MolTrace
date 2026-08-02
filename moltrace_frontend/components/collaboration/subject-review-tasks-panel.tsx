"use client"

// Ask a colleague to review this filing or this campaign, and work the queue that
// comes back. One panel serves both — the only difference is which subject it is
// pointed at — because the queue behind it is one endpoint addressed by subject.
//
// Spectroscopy sessions are NOT served here; they keep the richer session-scoped
// review workspace with per-session reviewer roles. `SubjectType` excludes them.
//
// The not-found state is load-bearing: a filing that belongs to another organization
// answers the same way one that never existed does, so the panel says "no longer
// available", never "you do not have permission". See the module comment on
// lib/collaboration/subject-review-tasks.ts.

import { useCallback, useEffect, useState } from "react"
import { ClipboardCheck, Loader2 } from "lucide-react"
import { ModuleCard, type ModuleCardAccent } from "@/components/dashboard/module-card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { StatusBadge } from "@/components/ui/status-badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { statusLabel } from "@/lib/ui/status"
import { formatStableUtcDateTime } from "@/lib/utils"
import {
  REVIEW_TASK_PRIORITIES,
  REVIEW_TASK_STATUSES,
  describeSubjectReviewTaskError,
  isReviewTaskClosed,
  listSubjectReviewTasks,
  openReviewTaskCount,
  raiseSubjectReviewTask,
  sortReviewTasks,
  subjectKindLabel,
  updateSubjectReviewTask,
  type ReviewTaskPriority,
  type ReviewTaskRecord,
  type ReviewTaskStatus,
  type SubjectReviewTaskError,
  type SubjectType,
} from "@/lib/collaboration/subject-review-tasks"

export type SubjectReviewTasksPanelProps = {
  subjectType: SubjectType
  /** Null while the route param is still resolving, or when it is not a number. */
  subjectId: number | null
  accent?: ModuleCardAccent
  eyebrow?: string
}

export function SubjectReviewTasksPanel({
  subjectType,
  subjectId,
  accent = "teal",
  eyebrow = "Review tasks",
}: SubjectReviewTasksPanelProps) {
  const kind = subjectKindLabel(subjectType)

  const [tasks, setTasks] = useState<ReviewTaskRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<SubjectReviewTaskError | null>(null)

  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [assignedTo, setAssignedTo] = useState("")
  const [priority, setPriority] = useState<ReviewTaskPriority>("medium")
  const [raising, setRaising] = useState(false)
  const [raiseError, setRaiseError] = useState("")

  const [savingTaskId, setSavingTaskId] = useState<number | null>(null)
  const [saveError, setSaveError] = useState("")

  const refresh = useCallback(async () => {
    if (subjectId == null) return
    setLoading(true)
    setLoadError(null)
    try {
      setTasks(sortReviewTasks(await listSubjectReviewTasks(subjectType, subjectId)))
    } catch (err) {
      setTasks([])
      setLoadError(describeSubjectReviewTaskError(err, subjectType))
    } finally {
      setLoading(false)
    }
  }, [subjectType, subjectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function raise() {
    if (subjectId == null) return
    const trimmed = title.trim()
    if (!trimmed) {
      setRaiseError("A short title is required so the reviewer knows what to look at.")
      return
    }
    setRaising(true)
    setRaiseError("")
    try {
      await raiseSubjectReviewTask({
        subjectType,
        subjectId,
        title: trimmed,
        description,
        assignedTo,
        priority,
      })
      setTitle("")
      setDescription("")
      setAssignedTo("")
      setPriority("medium")
      await refresh()
    } catch (err) {
      setRaiseError(describeSubjectReviewTaskError(err, subjectType).message)
    } finally {
      setRaising(false)
    }
  }

  async function setStatus(taskId: number, status: ReviewTaskStatus) {
    setSavingTaskId(taskId)
    setSaveError("")
    try {
      await updateSubjectReviewTask(taskId, { status })
      await refresh()
    } catch (err) {
      setSaveError(describeSubjectReviewTaskError(err, subjectType).message)
    } finally {
      setSavingTaskId(null)
    }
  }

  const openCount = openReviewTaskCount(tasks)

  // Deliberately not "anyone on your team": a filing or campaign created without a team
  // stays creator-only, so a team is not something this copy can assume exists. Both
  // states are in the wild.
  const panelDescription =
    `Raise a review task against this ${kind} and track it to a decision. ` +
    `Everyone who can open this ${kind} sees the same queue.`

  return (
    <ModuleCard
      accent={accent}
      eyebrow={eyebrow}
      icon={ClipboardCheck}
      title="Ask someone to review this"
      description={panelDescription}
      badge={
        openCount > 0 ? (
          <Badge variant="secondary">
            {openCount} open
          </Badge>
        ) : null
      }
    >
      <div className="space-y-5">
        {subjectId == null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : loadError ? (
          <Alert variant={loadError.kind === "not_found" ? "default" : "destructive"}>
            <AlertTitle>
              {loadError.kind === "not_found"
                ? `This ${kind} is not available`
                : "Review tasks could not be loaded"}
            </AlertTitle>
            <AlertDescription className="text-sm leading-relaxed">{loadError.message}</AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="srt-title" className="text-sm">
                  What should they look at? <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="srt-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Confirm the nitrosamine limit"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="srt-assignee" className="text-sm">
                  Assign to (optional)
                </Label>
                <Input
                  id="srt-assignee"
                  type="email"
                  value={assignedTo}
                  onChange={(e) => setAssignedTo(e.target.value)}
                  placeholder="reviewer@example.com"
                  autoComplete="email"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="srt-priority" className="text-sm">
                  Priority
                </Label>
                {/* ``value`` stays the stored token; only the label is humanized. */}
                <Select value={priority} onValueChange={(v) => setPriority(v as ReviewTaskPriority)}>
                  <SelectTrigger id="srt-priority" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REVIEW_TASK_PRIORITIES.map((p) => (
                      <SelectItem key={p} value={p}>
                        {statusLabel(p)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="srt-description" className="text-sm">
                  Detail (optional)
                </Label>
                <Textarea
                  id="srt-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  placeholder="Anything the reviewer needs to know before they start."
                />
              </div>
            </div>

            {raiseError ? (
              <Alert variant="destructive">
                <AlertDescription className="text-sm">{raiseError}</AlertDescription>
              </Alert>
            ) : null}

            <Button type="button" variant="outline" size="sm" disabled={raising} onClick={() => void raise()}>
              {raising ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Raise review task
            </Button>

            {saveError ? (
              <Alert variant="destructive">
                <AlertDescription className="text-sm">{saveError}</AlertDescription>
              </Alert>
            ) : null}

            {loading ? (
              <p className="text-sm text-muted-foreground">Loading review tasks…</p>
            ) : tasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No one has been asked to review this {kind} yet.
              </p>
            ) : (
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Task</TableHead>
                      <TableHead>Priority</TableHead>
                      <TableHead>Assigned to</TableHead>
                      <TableHead>Last updated</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tasks.map((task) => {
                      const taskId = Number(task.id)
                      return (
                        <TableRow key={taskId} className={isReviewTaskClosed(task) ? "opacity-60" : undefined}>
                          <TableCell className="max-w-[22rem]">
                            <p className="text-sm font-medium">{task.title}</p>
                            {task.description ? (
                              <p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">
                                {task.description}
                              </p>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            <StatusBadge status={task.priority} />
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {task.assigned_to || "Anyone on the team"}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatStableUtcDateTime(task.updated_at)}
                          </TableCell>
                          <TableCell>
                            <Select
                              value={String(task.status)}
                              disabled={savingTaskId === taskId}
                              onValueChange={(v) => void setStatus(taskId, v as ReviewTaskStatus)}
                            >
                              <SelectTrigger
                                className="w-[9.5rem]"
                                aria-label={`Status of “${task.title}”`}
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {REVIEW_TASK_STATUSES.map((s) => (
                                  <SelectItem key={s} value={s}>
                                    {statusLabel(s)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </>
        )}
      </div>
    </ModuleCard>
  )
}
