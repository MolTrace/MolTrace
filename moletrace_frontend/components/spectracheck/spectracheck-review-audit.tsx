"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { fetchSessionAudit, fetchSessionReview, postSessionReview } from "@/src/lib/spectracheck/spectracheck-backend-session"

const REVIEW_STATUSES = [
  "unreviewed",
  "needs_changes",
  "approved_plausible",
  "approved_confirmed",
  "rejected",
  "deferred",
] as const

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function pickStr(o: Record<string, unknown>, keys: string[]): string | undefined {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string") return v
  }
  return undefined
}

function parseReviewForm(data: unknown): {
  reviewer_name: string
  reviewer_comment: string
  review_status: string
  reviewed_at: string
} {
  if (!isRecord(data)) {
    return { reviewer_name: "", reviewer_comment: "", review_status: "unreviewed", reviewed_at: "" }
  }
  return {
    reviewer_name: pickStr(data, ["reviewer_name", "reviewerName"]) ?? "",
    reviewer_comment: pickStr(data, ["reviewer_comment", "reviewerComment"]) ?? "",
    review_status: pickStr(data, ["review_status", "reviewStatus"]) ?? "unreviewed",
    reviewed_at: pickStr(data, ["reviewed_at", "reviewedAt"]) ?? "",
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

function eventField(ev: unknown, keys: string[]): string {
  if (!isRecord(ev)) return "—"
  for (const k of keys) {
    const v = ev[k]
    if (typeof v === "string" && v.trim()) return v
    if (typeof v === "number") return String(v)
  }
  return "—"
}

function metadataPreview(meta: unknown): string {
  if (meta == null) return "—"
  try {
    const s = JSON.stringify(meta)
    if (s.length <= 96) return s
    return `${s.slice(0, 96)}…`
  } catch {
    return "—"
  }
}

function reportReadinessMessage(reviewStatus: string): string {
  if (reviewStatus === "approved_confirmed") {
    return "Report can be marked approved for release."
  }
  return "Report is draft/review required."
}

export function SpectraCheckSavedSessionReviewAudit({ backendSessionId }: { backendSessionId: string | null }) {
  const [reviewerName, setReviewerName] = useState("")
  const [reviewerComment, setReviewerComment] = useState("")
  const [reviewStatus, setReviewStatus] = useState<string>("unreviewed")
  const [reviewedAt, setReviewedAt] = useState("")
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState("")
  const [reviewSaved, setReviewSaved] = useState(false)

  const [auditRaw, setAuditRaw] = useState<unknown>(null)
  const [auditError, setAuditError] = useState("")
  const [auditOpen, setAuditOpen] = useState(false)
  const [showAllAudit, setShowAllAudit] = useState(false)

  const loadReview = useCallback(async () => {
    if (!backendSessionId?.trim()) return
    setReviewError("")
    try {
      const data = await fetchSessionReview(backendSessionId.trim())
      const p = parseReviewForm(data)
      setReviewerName(p.reviewer_name)
      setReviewerComment(p.reviewer_comment)
      setReviewStatus(REVIEW_STATUSES.includes(p.review_status as (typeof REVIEW_STATUSES)[number]) ? p.review_status : "unreviewed")
      setReviewedAt(p.reviewed_at)
      setReviewSaved(false)
    } catch (err) {
      setReviewError(formatApiError(err, "Could not load review."))
      if (err instanceof ApiError && err.status === 404) {
        setReviewerName("")
        setReviewerComment("")
        setReviewStatus("unreviewed")
        setReviewedAt("")
      }
    }
  }, [backendSessionId])

  const loadAudit = useCallback(async () => {
    if (!backendSessionId?.trim()) return
    setAuditError("")
    try {
      const data = await fetchSessionAudit(backendSessionId.trim())
      setAuditRaw(data)
    } catch (err) {
      setAuditError(formatApiError(err, "Could not load audit trail."))
      setAuditRaw(null)
    }
  }, [backendSessionId])

  useEffect(() => {
    setShowAllAudit(false)
    void loadReview()
    void loadAudit()
  }, [loadReview, loadAudit])

  async function saveReviewDecision() {
    if (!backendSessionId?.trim()) return
    setReviewBusy(true)
    setReviewError("")
    setReviewSaved(false)
    try {
      await postSessionReview(backendSessionId.trim(), {
        reviewer_name: reviewerName.trim(),
        reviewer_comment: reviewerComment.trim(),
        review_status: reviewStatus,
      })
      await loadReview()
      await loadAudit()
      setReviewSaved(true)
    } catch (err) {
      setReviewError(formatApiError(err, "Save review failed."))
    } finally {
      setReviewBusy(false)
    }
  }

  const allEvents = useMemo(() => normalizeAuditEvents(auditRaw), [auditRaw])
  const latestFive = useMemo(() => allEvents.slice(0, 5), [allEvents])
  const restEvents = useMemo(() => allEvents.slice(5), [allEvents])

  const noSession = !backendSessionId?.trim()

  return (
    <div className="space-y-4">
      <Card className="min-w-0 border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Review gate</CardTitle>
          <CardDescription>
            Human review for this saved SpectraCheck session. POST{" "}
            <code className="text-xs">/spectracheck/sessions/{"{session_id}"}/review</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {noSession ? (
            <p className="text-sm text-muted-foreground">
              Connect a backend session (Session card above) to save review decisions.
            </p>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="sc-r-name">Reviewer name</Label>
                  <Input
                    id="sc-r-name"
                    value={reviewerName}
                    onChange={(e) => setReviewerName(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sc-r-status">Review status</Label>
                  <select
                    id="sc-r-status"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                    value={reviewStatus}
                    onChange={(e) => setReviewStatus(e.target.value)}
                  >
                    {REVIEW_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="sc-r-comment">Reviewer comment</Label>
                <Textarea
                  id="sc-r-comment"
                  value={reviewerComment}
                  onChange={(e) => setReviewerComment(e.target.value)}
                  rows={3}
                />
              </div>
              {reviewedAt ? (
                <p className="text-xs text-muted-foreground">
                  Reviewed at: <span className="font-mono">{reviewedAt}</span>
                </p>
              ) : null}
              {reviewError ? <p className="text-sm text-destructive">{reviewError}</p> : null}
              {reviewSaved ? <p className="text-xs text-muted-foreground">Review decision saved.</p> : null}
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" disabled={reviewBusy} onClick={() => void saveReviewDecision()}>
                  {reviewBusy ? "Saving…" : "Save review decision"}
                </Button>
              </div>
              <div className="border-t pt-3">
                <p className="text-sm text-muted-foreground">{reportReadinessMessage(reviewStatus)}</p>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Collapsible open={auditOpen} onOpenChange={setAuditOpen} className="rounded-lg border">
        <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-muted/40">
          <span>Audit trail</span>
          <span className="text-xs font-normal text-muted-foreground">{auditOpen ? "Hide" : "Show"}</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="border-t px-4 pb-4">
          {noSession ? (
            <p className="py-2 text-sm text-muted-foreground">Connect a backend session to load audit events.</p>
          ) : auditError ? (
            <p className="py-2 text-sm text-destructive">{auditError}</p>
          ) : allEvents.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">No audit events returned.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="whitespace-nowrap">Event type</TableHead>
                      <TableHead className="whitespace-nowrap">Message</TableHead>
                      <TableHead className="whitespace-nowrap">Actor</TableHead>
                      <TableHead className="whitespace-nowrap">Timestamp</TableHead>
                      <TableHead>Metadata preview</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(showAllAudit ? allEvents : latestFive).map((ev, i) => (
                      <TableRow key={i}>
                        <TableCell className="max-w-[8rem] truncate font-mono text-xs">
                          {eventField(ev, ["event_type", "eventType", "type"])}
                        </TableCell>
                        <TableCell className="max-w-[14rem] truncate text-sm">
                          {eventField(ev, ["message", "msg", "detail"])}
                        </TableCell>
                        <TableCell className="max-w-[10rem] truncate text-sm">
                          {eventField(ev, ["actor", "user", "actor_id"])}
                        </TableCell>
                        <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                          {eventField(ev, ["timestamp", "created_at", "time"])}
                        </TableCell>
                        <TableCell className="max-w-[12rem] truncate font-mono text-[10px] text-muted-foreground">
                          {metadataPreview(isRecord(ev) ? ev.metadata ?? ev.meta ?? ev.payload : null)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {restEvents.length > 0 && !showAllAudit ? (
                <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => setShowAllAudit(true)}>
                  View all audit events
                </Button>
              ) : null}
              {showAllAudit && restEvents.length > 0 ? (
                <Button type="button" variant="ghost" size="sm" className="mt-2" onClick={() => setShowAllAudit(false)}>
                  Show latest 5 only
                </Button>
              ) : null}
              <div className="mt-4 min-w-0">
                <DeveloperJsonPanel data={auditRaw} />
              </div>
            </>
          )}
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
