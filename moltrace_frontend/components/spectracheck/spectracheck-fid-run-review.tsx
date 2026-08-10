"use client"

/**
 * Review panel for FID processing runs.
 *
 * Segregation of duties is the whole point of the surface: a run is signed off by
 * somebody other than the person who produced it. The panel therefore has to make
 * *whose* run this is legible, and has to explain a refusal rather than swallow it
 * — see `selfReviewMessage`.
 *
 * The scope rule lives in `lib/fid/fid-run-review.ts`; the short version is that this
 * lists the caller's own runs plus their team's open review queue — a colleague's run
 * while it still awaits a verdict, and anything the caller has already signed. A user
 * on no team sees only their own runs, which is correct rather than broken: there are
 * no colleagues to review for.
 */

import { useCallback, useEffect, useMemo, useState } from "react"
import { ClipboardCheck, Loader2, RefreshCw } from "lucide-react"

import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  FID_REVIEW_ACTIONS,
  FID_REVIEW_ACTION_LABELS,
  fetchFidRunReviewDecisions,
  fetchFidRuns,
  fidReviewStatusLabel,
  selfReviewMessage,
  submitFidRunReview,
  type FIDReviewAction,
  type FIDRunRecord,
  type FIDRunReviewDecision,
} from "@/lib/fid/fid-run-review"

/** Status → the ink token that carries it. Amber for "needs a human", not red:
 *  awaiting review is the normal resting state of a new run, not a fault. */
const STATUS_INK: Record<string, string> = {
  pending_review: "var(--mt-amber-ink)",
  approved: "var(--mt-teal-ink)",
  rejected: "var(--mt-rose-ink, #b3261e)",
  needs_revision: "var(--mt-amber-ink)",
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className="rounded-md border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em]"
      style={{ borderColor: STATUS_INK[status] ?? "currentColor", color: STATUS_INK[status] }}
      data-testid={`fid-run-status-${status}`}
    >
      {fidReviewStatusLabel(status)}
    </span>
  )
}

function formatWhen(value: string | null | undefined): string {
  if (!value) return "—"
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString()
}

export function SpectraCheckFidRunReview() {
  const [runs, setRuns] = useState<FIDRunRecord[] | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [decisions, setDecisions] = useState<FIDRunReviewDecision[]>([])
  const [decisionsError, setDecisionsError] = useState<string | null>(null)

  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState<FIDReviewAction | null>(null)
  // Held apart from `actionError` because it is not a failure to retry: it is the
  // separation-of-duties rule working as designed, and it reads as an explanation.
  const [selfReview, setSelfReview] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadRuns = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      setRuns(await fetchFidRuns(20))
    } catch (err) {
      setRuns([])
      setListError(formatApiError(err, "Could not load FID runs."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  const loadDecisions = useCallback(async (runId: number) => {
    setDecisionsError(null)
    try {
      setDecisions(await fetchFidRunReviewDecisions(runId))
    } catch (err) {
      setDecisions([])
      setDecisionsError(formatApiError(err, "Could not load the review history for this run."))
    }
  }, [])

  const selectRun = useCallback(
    (runId: number) => {
      const next = selectedId === runId ? null : runId
      setSelectedId(next)
      setSelfReview(null)
      setActionError(null)
      setComment("")
      setDecisions([])
      if (next != null) void loadDecisions(next)
    },
    [loadDecisions, selectedId],
  )

  const act = useCallback(
    async (action: FIDReviewAction) => {
      if (selectedId == null) return
      setSubmitting(action)
      setSelfReview(null)
      setActionError(null)
      try {
        await submitFidRunReview(selectedId, action, comment)
        setComment("")
        await Promise.all([loadDecisions(selectedId), loadRuns()])
      } catch (err) {
        const refusal = selfReviewMessage(err)
        if (refusal) setSelfReview(refusal)
        else setActionError(formatApiError(err, "Could not record that decision."))
      } finally {
        setSubmitting(null)
      }
    },
    [comment, loadDecisions, loadRuns, selectedId],
  )

  const selected = useMemo(
    () => runs?.find((run) => run.id === selectedId) ?? null,
    [runs, selectedId],
  )

  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid="fid-run-review"
    >
      <CardContent className="space-y-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            <ClipboardCheck className="h-3 w-3" aria-hidden />
            FID run review
          </p>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => void loadRuns()}
            disabled={loading}
            data-testid="fid-run-review-refresh"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            )}
            <span className="ml-1.5 text-xs">Refresh</span>
          </Button>
        </div>

        <p className="text-[11px] leading-snug text-muted-foreground">
          A processing run is signed off by someone other than the person who produced it. Select a
          run to see its review history and record a decision.
        </p>

        {listError ? (
          <p className="text-[11px] leading-snug" style={{ color: "var(--mt-amber-ink)" }}>
            {listError}
          </p>
        ) : null}

        {runs != null && runs.length === 0 && !listError ? (
          <p className="text-[11px] text-muted-foreground" data-testid="fid-run-review-empty">
            No processing runs yet. Process a raw FID archive and it will appear here for review.
          </p>
        ) : null}

        {runs != null && runs.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] uppercase tracking-wide">Run</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wide">Sample</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wide">Quality</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wide">Status</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wide">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer"
                    data-testid={`fid-run-row-${run.id}`}
                    data-selected={run.id === selectedId ? "true" : "false"}
                    onClick={() => selectRun(run.id)}
                  >
                    <TableCell className="font-mono text-xs">{run.filename}</TableCell>
                    <TableCell className="text-xs">{run.sample_id || "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{run.quality_label}</TableCell>
                    <TableCell>
                      <StatusBadge status={run.review_status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatWhen(run.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}

        {selected != null ? (
          <div className="space-y-3 rounded-lg border p-3" data-testid="fid-run-review-detail">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
              {selected.filename} · review history
            </p>

            {decisionsError ? (
              <p className="text-[11px] leading-snug" style={{ color: "var(--mt-amber-ink)" }}>
                {decisionsError}
              </p>
            ) : null}

            {decisions.length === 0 && !decisionsError ? (
              <p className="text-[11px] text-muted-foreground" data-testid="fid-run-no-decisions">
                No decisions recorded yet.
              </p>
            ) : null}

            {decisions.length > 0 ? (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[10px] uppercase tracking-wide">Decision</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wide">Moved to</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wide">Comment</TableHead>
                      <TableHead className="text-[10px] uppercase tracking-wide">Recorded</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {decisions.map((decision) => (
                      <TableRow key={decision.id}>
                        <TableCell className="text-xs">
                          {FID_REVIEW_ACTION_LABELS[decision.action as FIDReviewAction] ??
                            decision.action.replace(/_/g, " ")}
                        </TableCell>
                        <TableCell className="text-xs">
                          {fidReviewStatusLabel(decision.new_status)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {decision.comment || "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatWhen(decision.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : null}

            <div className="space-y-1.5">
              <Label htmlFor="fid-review-comment" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Comment
              </Label>
              <Textarea
                id="fid-review-comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                rows={2}
                placeholder="Optional — what did you check?"
                data-testid="fid-review-comment"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {FID_REVIEW_ACTIONS.map((action) => (
                <Button
                  key={action}
                  type="button"
                  size="sm"
                  variant={action === "approve" ? "default" : "outline"}
                  disabled={submitting != null}
                  onClick={() => void act(action)}
                  data-testid={`fid-review-action-${action}`}
                >
                  {submitting === action ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : null}
                  {FID_REVIEW_ACTION_LABELS[action]}
                </Button>
              ))}
            </div>

            {/* The refusal, rendered as the explanation it is. Its own block rather
                than the error slot: nothing here failed, and there is nothing to
                retry — the run simply needs a different reviewer. */}
            {selfReview ? (
              <p
                className="rounded-md border px-2.5 py-2 text-[11px] leading-snug"
                style={{ borderColor: "var(--mt-amber-ink)", color: "var(--mt-amber-ink)" }}
                data-testid="fid-review-self-review"
              >
                {selfReview}
              </p>
            ) : null}

            {actionError ? (
              <p
                className="text-[11px] leading-snug"
                style={{ color: "var(--mt-amber-ink)" }}
                data-testid="fid-review-action-error"
              >
                {actionError}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
