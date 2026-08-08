"use client"

// Two-person promotion for a dataset version.
//
// A dataset version is the point where curated records start training something,
// so promoting one takes two different people. The whole control is shaped by
// that: there is no approver field to fill in (identity comes from who is signed
// in), progress is a count rather than a tick, and the two ways this can be
// refused are ordinary outcomes of the rule rather than errors.
//
// See `lib/knowledge/corpus-conveyor.ts` §1.

import { useCallback, useEffect, useState } from "react"
import { CheckCircle2, Loader2, ShieldCheck, Users } from "lucide-react"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  APPROVAL_IDENTITY_NOTE,
  APPROVAL_REFUSAL_FALLBACK,
  approvalProgress,
  approveDatasetVersion,
  fetchDatasetVersionApprovals,
  type DatasetVersionApprovalState,
} from "@/lib/knowledge/corpus-conveyor"

function formatWhen(iso: string | undefined | null): string {
  if (!iso?.trim()) return "—"
  const parsed = Date.parse(iso)
  if (Number.isNaN(parsed)) return iso
  return new Date(parsed).toLocaleString()
}

export function KnowledgeDatasetVersionApprovals({
  datasetVersionId,
  onPromoted,
}: {
  datasetVersionId: number
  /** Fires when the version reaches the required approvals, so the list around it can refresh. */
  onPromoted?: () => void
}) {
  const [state, setState] = useState<DatasetVersionApprovalState | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadErr, setLoadErr] = useState("")

  const [comment, setComment] = useState("")
  const [busy, setBusy] = useState(false)
  // A refusal here is the rule working, so it is kept apart from a load failure
  // and rendered in a plain tone rather than as something that went wrong.
  const [refusal, setRefusal] = useState("")
  const [recorded, setRecorded] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      setState(await fetchDatasetVersionApprovals(datasetVersionId))
    } catch (e) {
      setState(null)
      setLoadErr(formatApiError(e, "Could not load the approvals for this dataset version."))
    } finally {
      setLoading(false)
    }
  }, [datasetVersionId])

  useEffect(() => {
    setComment("")
    setRefusal("")
    setRecorded("")
    void load()
  }, [load])

  async function submit() {
    setRefusal("")
    setRecorded("")
    setBusy(true)
    try {
      const next = await approveDatasetVersion(datasetVersionId, comment)
      setState(next)
      setComment("")
      setRecorded(
        next.promoted
          ? "Your approval was recorded, and this version is now approved."
          : "Your approval was recorded.",
      )
      if (next.promoted) onPromoted?.()
    } catch (e) {
      // The service explains each refusal in a full sentence — show that sentence
      // rather than classifying it by matching its wording, which would quietly
      // stop working the moment the wording changed.
      setRefusal(formatApiError(e, APPROVAL_REFUSAL_FALLBACK))
      // The state moved even when your own approval did not: someone else may
      // have approved since this panel loaded.
      void load()
    } finally {
      setBusy(false)
    }
  }

  const progress = approvalProgress(state)
  const approvals = state?.approvals ?? []

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          Approvals
        </CardTitle>
        <CardDescription>
          This version is promoted by two separate people approving it — not by setting its status.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadErr ? <p className="text-sm text-destructive">{loadErr}</p> : null}

        {loading && state == null ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Loading approvals…
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {/* A count, not a tick: "awaiting a second approver" is a different
                  state from "not approved", and a boolean cannot say it. */}
              <Badge
                variant="outline"
                className={
                  progress.promoted
                    ? "gap-1 border-emerald-500/50 text-emerald-700 dark:text-emerald-400"
                    : "gap-1 border-amber-500/60 text-amber-700 dark:text-amber-400"
                }
              >
                {progress.promoted ? (
                  <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden />
                ) : (
                  <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden />
                )}
                {progress.countLabel}
              </Badge>
              <span className="text-sm text-muted-foreground">{progress.statusLabel}</span>
            </div>

            {approvals.length > 0 ? (
              <ul className="space-y-1.5">
                {approvals.map((approval) => (
                  <li key={approval.id} className="rounded-md border bg-muted/20 p-2.5 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-medium">{approval.approver_email || "Approver not recorded"}</span>
                      <span className="text-xs text-muted-foreground">{formatWhen(approval.created_at)}</span>
                    </div>
                    {approval.comment ? (
                      <p className="mt-1 text-sm text-muted-foreground">{approval.comment}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nobody has approved this version yet.</p>
            )}

            {progress.promoted ? null : (
              <div className="space-y-2">
                <Label htmlFor={`dv-approval-comment-${datasetVersionId}`}>Comment (optional)</Label>
                <Textarea
                  id={`dv-approval-comment-${datasetVersionId}`}
                  rows={2}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="What you checked before approving."
                />
                {/* The absence of an approver field is the control being bought,
                    so it is stated rather than left to look like an oversight. */}
                <p className="text-xs text-muted-foreground">{APPROVAL_IDENTITY_NOTE}</p>
                <Button type="button" disabled={busy} onClick={() => void submit()}>
                  {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Record my approval
                </Button>
              </div>
            )}

            {refusal ? (
              <Alert>
                <AlertTitle className="text-sm">Approval not recorded</AlertTitle>
                <AlertDescription className="text-sm">{refusal}</AlertDescription>
              </Alert>
            ) : null}
            {recorded ? <p className="text-sm text-muted-foreground">{recorded}</p> : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}
