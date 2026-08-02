"use client"

// Reviewer nominations on a filing or a campaign: who is expected to look at it.
//
// Rendered as a tab of `subject-collaboration-panel.tsx`.
//
// **The copy here is the feature.** A nomination records an expectation; it does not grant
// access. So nothing on this surface says "share", "invite" or "give access to" — it says
// "request review from". Nominating someone outside the owning team succeeds and lets them
// in nowhere, which is deliberate, so the panel says that out loud rather than leaving a
// reader to read the silence as a bug and retry.
//
// The asymmetry with SpectraCheck is real: on a *session*, a reviewer row does confer a
// session role. The session copy is not a model for this one.
//
// There is no update call — re-nominating the same person updates their row in place, so
// changing a status is another nomination.

import { useCallback, useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { statusLabel } from "@/lib/ui/status"
import { formatStableUtcDateTime } from "@/lib/utils"
import {
  subjectKindLabel,
  type SubjectCollaborationError,
  type SubjectSurfaceBodyProps,
} from "@/lib/collaboration/subject-collaboration"
import {
  NOMINATION_DOES_NOT_GRANT_ACCESS,
  REVIEWER_STATUSES,
  describeSubjectReviewerError,
  isReviewerNominationClosed,
  listSubjectReviewers,
  nominateSubjectReviewer,
  pendingReviewerCount,
  setSubjectReviewerStatus,
  sortSubjectReviewers,
  type ReviewerStatus,
  type SubjectReviewerRecord,
} from "@/lib/collaboration/subject-reviewers"

export function SubjectReviewersBody({
  subjectType,
  subjectId,
  onAttentionCountChange,
}: SubjectSurfaceBodyProps) {
  const kind = subjectKindLabel(subjectType)

  const [reviewers, setReviewers] = useState<SubjectReviewerRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<SubjectCollaborationError | null>(null)

  const [email, setEmail] = useState("")
  const [nominating, setNominating] = useState(false)
  const [nominateError, setNominateError] = useState("")

  const [savingEmail, setSavingEmail] = useState<string | null>(null)
  const [saveError, setSaveError] = useState("")

  const refresh = useCallback(async () => {
    if (subjectId == null) return
    setLoading(true)
    setLoadError(null)
    try {
      setReviewers(sortSubjectReviewers(await listSubjectReviewers(subjectType, subjectId)))
    } catch (err) {
      setReviewers([])
      setLoadError(describeSubjectReviewerError(err, subjectType))
    } finally {
      setLoading(false)
    }
  }, [subjectType, subjectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const pending = pendingReviewerCount(reviewers)

  useEffect(() => {
    onAttentionCountChange?.(pending)
  }, [pending, onAttentionCountChange])

  async function nominate() {
    if (subjectId == null) return
    const trimmed = email.trim()
    if (!trimmed) {
      setNominateError("Enter the email address of the person you want to look at this.")
      return
    }
    setNominating(true)
    setNominateError("")
    try {
      await nominateSubjectReviewer({ subjectType, subjectId, reviewerEmail: trimmed })
      setEmail("")
      await refresh()
    } catch (err) {
      setNominateError(describeSubjectReviewerError(err, subjectType).message)
    } finally {
      setNominating(false)
    }
  }

  async function setStatus(reviewerEmail: string, status: ReviewerStatus) {
    if (subjectId == null) return
    setSavingEmail(reviewerEmail)
    setSaveError("")
    try {
      await setSubjectReviewerStatus(subjectType, subjectId, reviewerEmail, status)
      await refresh()
    } catch (err) {
      setSaveError(describeSubjectReviewerError(err, subjectType).message)
    } finally {
      setSavingEmail(null)
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed text-muted-foreground">
        Record who is expected to look at this {kind}.
      </p>

      {subjectId == null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : loadError ? (
        <Alert variant={loadError.kind === "not_found" ? "default" : "destructive"}>
          <AlertTitle>
            {loadError.kind === "not_found"
              ? `This ${kind} is not available`
              : "Reviewers could not be loaded"}
          </AlertTitle>
          <AlertDescription className="text-sm leading-relaxed">{loadError.message}</AlertDescription>
        </Alert>
      ) : (
        <>
          {/* Said before anyone nominates, not after they wonder why nothing happened. */}
          <Alert>
            <AlertTitle>A nomination is a request, not access</AlertTitle>
            <AlertDescription className="text-sm leading-relaxed">
              {NOMINATION_DOES_NOT_GRANT_ACCESS}
            </AlertDescription>
          </Alert>

          <div className="space-y-2 sm:max-w-sm">
            <Label htmlFor="ssr-email" className="text-sm">
              Request review from <span className="text-destructive">*</span>
            </Label>
            <Input
              id="ssr-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="reviewer@example.com"
              autoComplete="email"
            />
          </div>

          {nominateError ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{nominateError}</AlertDescription>
            </Alert>
          ) : null}

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={nominating}
            onClick={() => void nominate()}
          >
            {nominating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Nominate reviewer
          </Button>

          {saveError ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{saveError}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading reviewers…</p>
          ) : reviewers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No one has been asked to review this {kind} yet.
            </p>
          ) : (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Reviewer</TableHead>
                    <TableHead>Nominated by</TableHead>
                    <TableHead>Last updated</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reviewers.map((reviewer) => {
                    const reviewerEmail = String(reviewer.reviewer_email)
                    return (
                      <TableRow
                        key={Number(reviewer.id)}
                        className={isReviewerNominationClosed(reviewer) ? "opacity-60" : undefined}
                      >
                        <TableCell className="text-sm font-medium">{reviewerEmail}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {reviewer.assigned_by || "—"}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatStableUtcDateTime(reviewer.updated_at)}
                        </TableCell>
                        <TableCell>
                          {/* No update call exists — this re-nominates the same person with a
                              new status, which updates their row in place. */}
                          <Select
                            value={String(reviewer.status)}
                            disabled={savingEmail === reviewerEmail}
                            onValueChange={(v) => void setStatus(reviewerEmail, v as ReviewerStatus)}
                          >
                            <SelectTrigger
                              className="w-[9.5rem]"
                              aria-label={`Status of ${reviewerEmail}`}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {REVIEWER_STATUSES.map((s) => (
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
  )
}
