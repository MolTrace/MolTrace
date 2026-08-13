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
 *
 * Because that list is mixed, three things here are driven by the per-request fields
 * rather than by comparing ids client-side:
 *
 * - the filter across the top slices it into all / mine / the queue, server-side;
 * - the "Produced by" column reads `viewer_is_author`, so "mine" and "awaiting me"
 *   are legible at a glance instead of inferred;
 * - `viewer_can_review === false` disables the verdict buttons, which turns the
 *   segregation-of-duties refusal into something you can see before you act rather
 *   than a 409 read back afterwards.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  FID_RUN_SCOPES,
  FID_RUN_SCOPE_LABELS,
  fetchFidRunReviewDecisions,
  fetchFidRuns,
  fidReviewStatusLabel,
  selfReviewMessage,
  submitFidRunReview,
  type FIDReviewAction,
  type FIDRunRecord,
  type FIDRunReviewDecision,
  type FIDRunScope,
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

/** What each filter is showing, said once under the control rather than per row. */
const SCOPE_HINTS: Record<FIDRunScope, string> = {
  all: "Runs you produced, plus your team's runs still open for review.",
  mine: "Runs you produced. Your own work is signed off by someone else.",
  review_queue: "Runs still open for a verdict, from everyone but you.",
}

/**
 * Empty is a real state, and which one it is changes what the reader should do next.
 *
 * The queue wording carries the most: colleagues are resolved through shared
 * organization membership, and an organization is created deliberately — signing up
 * does not put anybody in one. Somebody on no team therefore has a queue that is
 * correctly empty and always will be, and a bare "no runs" would read as a fault
 * instead of as the accurate answer.
 */
const SCOPE_EMPTY_COPY: Record<FIDRunScope, string> = {
  all: "No processing runs yet. Process a raw FID archive and it will appear here for review.",
  mine: "You have not processed any runs yet. Process a raw FID archive and it will appear here.",
  review_queue:
    "No runs are waiting on you. Peer review draws on your organization's members — ask an administrator to add you to one if you expect to see colleagues' runs.",
}

export function SpectraCheckFidRunReview({
  focusRunId = null,
}: {
  /**
   * A run to open on arrival — the one the caller just processed, named by
   * `fid_run_id` on the process response. Applied once per distinct id, so a
   * later refresh or a manual selection is never yanked back.
   */
  focusRunId?: number | null
}) {
  const [scope, setScope] = useState<FIDRunScope>("all")
  const [runs, setRuns] = useState<FIDRunRecord[] | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // The whole record, not just its id. The selected run can legitimately leave the
  // list underneath the reader — approving a colleague's run drops it out of the
  // queue the moment the verdict lands — and deriving the detail panel from the list
  // would blank the evidence at the instant of signing, which for a Part 11 signature
  // is backwards. It is still refreshed from the list whenever it is present there.
  const [selected, setSelected] = useState<FIDRunRecord | null>(null)
  const [decisions, setDecisions] = useState<FIDRunReviewDecision[]>([])
  const [decisionsError, setDecisionsError] = useState<string | null>(null)

  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState<FIDReviewAction | null>(null)
  // Held apart from `actionError` because it is not a failure to retry: it is the
  // separation-of-duties rule working as designed, and it reads as an explanation.
  const [selfReview, setSelfReview] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadRuns = useCallback(async (nextScope: FIDRunScope) => {
    setLoading(true)
    setListError(null)
    try {
      const rows = await fetchFidRuns(20, nextScope)
      setRuns(rows)
      setSelected((current) =>
        current == null ? null : (rows.find((row) => row.id === current.id) ?? current),
      )
    } catch (err) {
      setRuns([])
      setListError(formatApiError(err, "Could not load FID runs."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRuns(scope)
  }, [loadRuns, scope])

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
    (run: FIDRunRecord) => {
      const next = selected?.id === run.id ? null : run
      setSelected(next)
      setSelfReview(null)
      setActionError(null)
      setComment("")
      setDecisions([])
      if (next != null) void loadDecisions(next.id)
    },
    [loadDecisions, selected],
  )

  // Held in state rather than a ref so that arriving on a scope that is *already*
  // "all" still re-runs the resolution below; a ref write alone renders nothing.
  const [pendingFocus, setPendingFocus] = useState<number | null>(null)
  const appliedFocus = useRef<number | null>(null)

  useEffect(() => {
    if (focusRunId == null || appliedFocus.current === focusRunId) return
    appliedFocus.current = focusRunId
    setPendingFocus(focusRunId)
    // The run just processed is the caller's own, so by definition it is not in the
    // review queue. Land on the unfiltered view or the anchor would select nothing.
    setScope("all")
  }, [focusRunId])

  useEffect(() => {
    if (pendingFocus == null || runs == null) return
    const match = runs.find((row) => row.id === pendingFocus)
    // Disarm either way: absent from even the unfiltered page (older than the newest
    // twenty) it should not stay armed to fire on some unrelated later refresh.
    setPendingFocus(null)
    if (!match) return
    setSelected(match)
    setSelfReview(null)
    setActionError(null)
    setComment("")
    setDecisions([])
    void loadDecisions(match.id)
  }, [loadDecisions, pendingFocus, runs])

  const act = useCallback(
    async (action: FIDReviewAction) => {
      const run = selected
      if (run == null) return
      setSubmitting(action)
      setSelfReview(null)
      setActionError(null)
      try {
        await submitFidRunReview(run.id, action, comment)
        setComment("")
        await Promise.all([loadDecisions(run.id), loadRuns(scope)])
      } catch (err) {
        const refusal = selfReviewMessage(err)
        if (refusal) setSelfReview(refusal)
        else setActionError(formatApiError(err, "Could not record that decision."))
      } finally {
        setSubmitting(null)
      }
    },
    [comment, loadDecisions, loadRuns, scope, selected],
  )

  // Only an explicit `false` refuses. A response that omits the field leaves the
  // buttons live and lets the 409 explain: the server is the authority on this, so
  // the failure worth designing against is locking out a reviewer entitled to act,
  // not letting an unentitled one press a button the backend already refuses.
  const cannotReview = selected?.viewer_can_review === false

  // Signed, and gone from the current filter — the queue lapses on completion. Say
  // where it went, rather than leaving an open panel for a row that vanished.
  const selectedOutOfView = useMemo(
    () => selected != null && runs != null && !runs.some((run) => run.id === selected.id),
    [runs, selected],
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
            onClick={() => void loadRuns(scope)}
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

        <div
          className="flex flex-wrap items-center gap-1.5"
          role="group"
          aria-label="Which runs to show"
          data-testid="fid-run-scope"
        >
          {FID_RUN_SCOPES.map((option) => (
            <Button
              key={option}
              type="button"
              size="sm"
              variant={option === scope ? "secondary" : "ghost"}
              aria-pressed={option === scope}
              onClick={() => setScope(option)}
              className="h-7 px-2.5 text-xs"
              data-testid={`fid-run-scope-${option}`}
            >
              {FID_RUN_SCOPE_LABELS[option]}
            </Button>
          ))}
        </div>

        <p className="text-[11px] leading-snug text-muted-foreground" data-testid="fid-run-scope-hint">
          {SCOPE_HINTS[scope]}
        </p>

        {listError ? (
          <p className="text-[11px] leading-snug" style={{ color: "var(--mt-amber-ink)" }}>
            {listError}
          </p>
        ) : null}

        {runs != null && runs.length === 0 && !listError ? (
          <p
            className="text-[11px] leading-snug text-muted-foreground"
            data-testid="fid-run-review-empty"
          >
            {SCOPE_EMPTY_COPY[scope]}
          </p>
        ) : null}

        {runs != null && runs.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] uppercase tracking-wide">Run</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wide">Sample</TableHead>
                  {/* The list is mixed now, so whose run this is has to be readable
                      rather than inferred from an id the reader does not have. */}
                  <TableHead className="text-[10px] uppercase tracking-wide">Produced by</TableHead>
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
                    data-selected={run.id === selected?.id ? "true" : "false"}
                    onClick={() => selectRun(run)}
                  >
                    <TableCell className="font-mono text-xs">{run.filename}</TableCell>
                    <TableCell className="text-xs">{run.sample_id || "—"}</TableCell>
                    <TableCell
                      className="text-xs text-muted-foreground"
                      data-testid={`fid-run-author-${run.id}`}
                    >
                      {run.viewer_is_author ? "You" : "Someone else"}
                    </TableCell>
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

            {selectedOutOfView ? (
              <p
                className="text-[11px] leading-snug text-muted-foreground"
                data-testid="fid-run-out-of-view"
              >
                This run is not in the list under the current filter — a run leaves the queue
                once its review is finished. It stays open here
                {scope === "all" ? "." : `, and “${FID_RUN_SCOPE_LABELS.all}” will find it again.`}
              </p>
            ) : null}

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
                // A comment only ever reaches the record attached to a decision, and
                // this reader cannot record one. Leaving it writable would invite
                // typing into something with nowhere to go.
                disabled={cannotReview}
                data-testid="fid-review-comment"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {/* All four are gated, not just the verdicts: the backend applies the
                  separation rule before the action is even read, so an author is
                  refused adding a comment too. Disabling three and leaving one live
                  would promise something the POST then takes away. */}
              {FID_REVIEW_ACTIONS.map((action) => (
                <Button
                  key={action}
                  type="button"
                  size="sm"
                  variant={action === "approve" ? "default" : "outline"}
                  disabled={submitting != null || cannotReview}
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

            {/* The refusal said up front, so a disabled row of buttons is explained
                rather than merely inert. The 409 block below still exists for the
                case where the server refuses something this pre-flight let through. */}
            {cannotReview ? (
              <p
                className="rounded-md border px-2.5 py-2 text-[11px] leading-snug"
                style={{ borderColor: "var(--mt-amber-ink)", color: "var(--mt-amber-ink)" }}
                data-testid="fid-review-cannot-review"
              >
                You produced this run, so it needs a review from someone else before it can be
                approved.
              </p>
            ) : null}

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
