"use client"

// Sign-off decisions on a filing or a campaign: who decided what, and why.
//
// Rendered as a tab of `subject-collaboration-panel.tsx`.
//
// Three things this component is careful about, all of them load-bearing:
//
//   * **The picker is driven by `APPROVAL_DECISIONS`, never by the record type.** The
//     record vocabulary is wider because the same table also stores SpectraCheck
//     structure-elucidation sign-offs; offering one of those here would be refused, and
//     would put structure language on a regulatory filing. See
//     lib/collaboration/subject-approvals.ts.
//   * **Nothing here is labelled "Sign".** A decision is not a §11.70 electronic
//     signature — a signature is created on the e-Signatures workspace and bound to a
//     point-in-time report. Labelling this "Sign" would promise a binding the record does
//     not carry.
//   * **A recorded decision is never edited.** There is no update to offer: changing a
//     decision after the fact would falsify the audit trail, so a change of position is
//     another decision, and the newest one stands.

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { formatStableUtcDateTime } from "@/lib/utils"
import {
  subjectKindLabel,
  type SubjectCollaborationError,
  type SubjectSurfaceBodyProps,
} from "@/lib/collaboration/subject-collaboration"
import {
  APPROVAL_DECISIONS,
  approvalDecisionLabel,
  currentSubjectApproval,
  describeSubjectApprovalError,
  listSubjectApprovals,
  recordSubjectApproval,
  sortSubjectApprovals,
  type SubjectApprovalDecision,
  type SubjectApprovalRecord,
} from "@/lib/collaboration/subject-approvals"

export function SubjectApprovalsBody({ subjectType, subjectId }: SubjectSurfaceBodyProps) {
  const kind = subjectKindLabel(subjectType)

  const [approvals, setApprovals] = useState<SubjectApprovalRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<SubjectCollaborationError | null>(null)

  const [decision, setDecision] = useState<SubjectApprovalDecision>("approved")
  const [rationale, setRationale] = useState("")
  const [approverEmail, setApproverEmail] = useState("")
  const [recording, setRecording] = useState(false)
  const [recordError, setRecordError] = useState("")

  const refresh = useCallback(async () => {
    if (subjectId == null) return
    setLoading(true)
    setLoadError(null)
    try {
      setApprovals(sortSubjectApprovals(await listSubjectApprovals(subjectType, subjectId)))
    } catch (err) {
      setApprovals([])
      setLoadError(describeSubjectApprovalError(err, subjectType))
    } finally {
      setLoading(false)
    }
  }, [subjectType, subjectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function record() {
    if (subjectId == null) return
    const trimmed = rationale.trim()
    if (!trimmed) {
      setRecordError("A reason is required — it is what the decision is read back against.")
      return
    }
    setRecording(true)
    setRecordError("")
    try {
      await recordSubjectApproval({
        subjectType,
        subjectId,
        decision,
        rationale: trimmed,
        approverEmail,
      })
      setRationale("")
      setApproverEmail("")
      await refresh()
    } catch (err) {
      setRecordError(describeSubjectApprovalError(err, subjectType).message)
    } finally {
      setRecording(false)
    }
  }

  const current = currentSubjectApproval(approvals)

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed text-muted-foreground">
        Record who decided what about this {kind}, and why. A decision is never edited — to change
        position, record another one, and the most recent decision is the one that stands.
      </p>

      {subjectId == null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : loadError ? (
        <Alert variant={loadError.kind === "not_found" ? "default" : "destructive"}>
          <AlertTitle>
            {loadError.kind === "not_found"
              ? `This ${kind} is not available`
              : "Decisions could not be loaded"}
          </AlertTitle>
          <AlertDescription className="text-sm leading-relaxed">{loadError.message}</AlertDescription>
        </Alert>
      ) : (
        <>
          {!loading && !current ? (
            <Alert>
              <AlertTitle>No decision recorded yet</AlertTitle>
              <AlertDescription className="text-sm leading-relaxed">
                Nobody has signed off on this {kind}.
              </AlertDescription>
            </Alert>
          ) : null}

          {current ? (
            <div className="rounded-lg border border-border/60 p-3">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Position that stands
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{approvalDecisionLabel(current.decision)}</Badge>
                <span className="text-xs text-muted-foreground">
                  {current.approver_email || "Approver not recorded"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatStableUtcDateTime(current.created_at)}
                </span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm">{current.rationale}</p>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ssa-decision" className="text-sm">
                Decision
              </Label>
              {/* Driven by the create model's vocabulary. The record type is wider — it also
                  carries the SpectraCheck structure decisions — and sending one of those
                  here is refused. ``value`` stays the stored token. */}
              <Select
                value={decision}
                onValueChange={(v) => setDecision(v as SubjectApprovalDecision)}
              >
                <SelectTrigger id="ssa-decision" className="w-full">
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
              <Label htmlFor="ssa-approver" className="text-sm">
                Decided by (optional)
              </Label>
              <Input
                id="ssa-approver"
                type="email"
                value={approverEmail}
                onChange={(e) => setApproverEmail(e.target.value)}
                placeholder="Leave blank to record yourself"
                autoComplete="email"
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="ssa-rationale" className="text-sm">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="ssa-rationale"
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={3}
                placeholder="What this decision rests on."
              />
            </div>
          </div>

          {recordError ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{recordError}</AlertDescription>
            </Alert>
          ) : null}

          {/* Never "Sign": this records a decision, it does not create a signature. */}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={recording}
            onClick={() => void record()}
          >
            {recording ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Record decision
          </Button>

          <p className="text-xs leading-relaxed text-muted-foreground">
            This records a decision. It is not an electronic signature — a signature is applied to a
            point-in-time report on the{" "}
            <Link href="/validation-center/esignatures" className="underline underline-offset-2">
              e-Signatures workspace
            </Link>
            , so that what was signed cannot drift.
          </p>

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading decisions…</p>
          ) : approvals.length === 0 ? null : (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Decision</TableHead>
                    <TableHead>Decided by</TableHead>
                    <TableHead>Recorded</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {approvals.map((approval) => (
                    <TableRow key={Number(approval.id)}>
                      <TableCell className="whitespace-nowrap text-sm font-medium">
                        {approvalDecisionLabel(approval.decision)}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {approval.approver_email || "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatStableUtcDateTime(approval.created_at)}
                      </TableCell>
                      <TableCell className="max-w-[22rem] whitespace-pre-wrap text-xs text-muted-foreground">
                        {approval.rationale}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
