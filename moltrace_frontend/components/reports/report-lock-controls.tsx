"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { AUTH_USER_STORAGE_KEY } from "@/lib/api/client"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  fetchReportLockRecord,
  fetchSessionApprovals,
  hasApprovedConfirmedForReport,
  lockRecordDisplayStatus,
  postReportLock,
  postReportRelease,
  postReportUnlock,
  type ReportLockDisplayStatus,
} from "@/src/lib/reports/report-lock"

const RELEASE_GATE_TOOLTIP = "Report release requires approved_confirmed human review."

function readStoredUserIsAdmin(): boolean {
  if (typeof window === "undefined") return false
  try {
    const raw = window.localStorage.getItem(AUTH_USER_STORAGE_KEY)
    if (!raw) return false
    const o = JSON.parse(raw) as { is_admin?: boolean }
    return o.is_admin === true
  } catch {
    return false
  }
}

function statusLabel(s: ReportLockDisplayStatus): string {
  switch (s) {
    case "locked":
      return "locked"
    case "released":
      return "released"
    default:
      return "unlocked"
  }
}

export type ReportLockControlsProps = {
  reportId: number
  /** Session id string as returned by the sessions API (for approvals fetch). */
  sessionIdStr: string
  /** Numeric session id for lock/unlock POST bodies when known. */
  sessionNumericId?: number | null
  /** Dense layout for tables. */
  compact?: boolean
  onAfterMutation?: () => void
}

export function ReportLockControls({
  reportId,
  sessionIdStr,
  sessionNumericId = null,
  compact = false,
  onAfterMutation,
}: ReportLockControlsProps) {
  const [lockRecord, setLockRecord] = useState<Record<string, unknown> | null>(null)
  const [approvals, setApprovals] = useState<Record<string, unknown>[]>([])
  const [loadErr, setLoadErr] = useState("")
  const [loadBusy, setLoadBusy] = useState(true)
  const [actionErr, setActionErr] = useState("")
  const [actionBusy, setActionBusy] = useState(false)

  const [lockDialogOpen, setLockDialogOpen] = useState(false)
  const [lockReason, setLockReason] = useState("")

  const [releaseDialogOpen, setReleaseDialogOpen] = useState(false)
  const [releaseRationale, setReleaseRationale] = useState("")
  const [overrideApproval, setOverrideApproval] = useState(false)

  const isAdmin = useMemo(() => readStoredUserIsAdmin(), [])

  const displayStatus = lockRecordDisplayStatus(lockRecord)
  const hasConfirmedApproval = hasApprovedConfirmedForReport(approvals, reportId)

  const sessionIdForPost = useMemo(() => {
    if (sessionNumericId != null && Number.isFinite(sessionNumericId)) return sessionNumericId
    const n = Number(sessionIdStr?.trim())
    return Number.isFinite(n) ? Math.trunc(n) : undefined
  }, [sessionNumericId, sessionIdStr])

  const refresh = useCallback(async () => {
    setLoadErr("")
    setLoadBusy(true)
    try {
      const [lr, appList] = await Promise.all([
        fetchReportLockRecord(reportId),
        fetchSessionApprovals(sessionIdStr).catch(() => [] as Record<string, unknown>[]),
      ])
      setLockRecord(lr)
      setApprovals(appList)
    } catch (err) {
      setLoadErr(formatApiError(err, "Could not load report lock state."))
      setLockRecord(null)
      setApprovals([])
    } finally {
      setLoadBusy(false)
    }
  }, [reportId, sessionIdStr])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const releaseAllowed =
    hasConfirmedApproval || (isAdmin && overrideApproval)
  const releaseDisabledByGate = !releaseAllowed

  async function handleLock() {
    const reason = lockReason.trim()
    if (!reason) {
      setActionErr("Lock reason is required.")
      return
    }
    setActionBusy(true)
    setActionErr("")
    try {
      const body: Parameters<typeof postReportLock>[1] = {
        lock_reason: reason,
      }
      if (sessionIdForPost != null) body.session_id = sessionIdForPost
      const next = await postReportLock(reportId, body)
      setLockRecord(next)
      setLockDialogOpen(false)
      setLockReason("")
      onAfterMutation?.()
      await refresh()
    } catch (err) {
      setActionErr(formatApiError(err, "Lock request failed."))
    } finally {
      setActionBusy(false)
    }
  }

  async function handleUnlock() {
    setActionBusy(true)
    setActionErr("")
    try {
      const body: Parameters<typeof postReportUnlock>[1] = {}
      if (sessionIdForPost != null) body.session_id = sessionIdForPost
      const next = await postReportUnlock(reportId, body)
      setLockRecord(next)
      onAfterMutation?.()
      await refresh()
    } catch (err) {
      setActionErr(formatApiError(err, "Unlock request failed."))
    } finally {
      setActionBusy(false)
    }
  }

  async function handleRelease() {
    const rationale = releaseRationale.trim()
    if (!rationale) {
      setActionErr("Release rationale is required.")
      return
    }
    if (releaseDisabledByGate) {
      setActionErr(RELEASE_GATE_TOOLTIP)
      return
    }
    setActionBusy(true)
    setActionErr("")
    try {
      const next = await postReportRelease(reportId, {
        rationale,
        override_approval_requirement: !hasConfirmedApproval && isAdmin && overrideApproval,
      })
      setLockRecord(next)
      setReleaseDialogOpen(false)
      setReleaseRationale("")
      setOverrideApproval(false)
      onAfterMutation?.()
      await refresh()
    } catch (err) {
      setActionErr(formatApiError(err, "Release request failed."))
    } finally {
      setActionBusy(false)
    }
  }

  const isLocked = displayStatus === "locked"
  const isReleased = displayStatus === "released"

  const lockButton = (
    <Button
      type="button"
      size={compact ? "sm" : "default"}
      variant="outline"
      disabled={actionBusy || loadBusy || isLocked}
      className={compact ? "h-8 text-xs" : undefined}
      onClick={() => {
        setActionErr("")
        setLockReason("")
        setLockDialogOpen(true)
      }}
    >
      Lock report
    </Button>
  )

  const unlockButton = (
    <Button
      type="button"
      size={compact ? "sm" : "default"}
      variant="outline"
      disabled={actionBusy || loadBusy || !isLocked}
      className={compact ? "h-8 text-xs" : undefined}
      onClick={() => void handleUnlock()}
    >
      Unlock report
    </Button>
  )

  const releaseBlockedByGate = releaseDisabledByGate && !isReleased
  const releaseBtnDisabled = actionBusy || loadBusy || isReleased || releaseDisabledByGate

  const releaseButtonEl = (
    <Button
      type="button"
      size={compact ? "sm" : "default"}
      variant="secondary"
      disabled={releaseBtnDisabled}
      className={compact ? "h-8 text-xs" : undefined}
      onClick={() => {
        setActionErr("")
        setReleaseRationale("")
        setOverrideApproval(false)
        setReleaseDialogOpen(true)
      }}
    >
      Release report
    </Button>
  )

  const releaseButton =
    releaseBlockedByGate ? (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex" tabIndex={0}>
            {releaseButtonEl}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs">
          {RELEASE_GATE_TOOLTIP}
        </TooltipContent>
      </Tooltip>
    ) : (
      releaseButtonEl
    )

  return (
    <TooltipProvider delayDuration={300}>
    <div className={compact ? "flex flex-col gap-1.5" : "space-y-3"}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Lock status</span>
        <Badge variant="outline" className="font-normal">
          {loadBusy ? "…" : statusLabel(displayStatus)}
        </Badge>
      </div>
      {loadErr ? <p className="text-xs text-destructive">{loadErr}</p> : null}
      {actionErr ? <p className="text-xs text-destructive">{actionErr}</p> : null}
      <div className={compact ? "flex flex-wrap gap-1" : "flex flex-wrap gap-2"}>
        {lockButton}
        {unlockButton}
        {releaseButton}
      </div>

      {!hasConfirmedApproval && isAdmin ? (
        <p className="text-[11px] text-muted-foreground">
          Platform admins may override the approval gate in the release dialog (recorded on the server).
        </p>
      ) : null}

      <Dialog open={lockDialogOpen} onOpenChange={setLockDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Lock report</DialogTitle>
            <DialogDescription>
              Locking records this report for human review workflows. A lock reason is required.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="report-lock-reason">Lock reason</Label>
            <Textarea
              id="report-lock-reason"
              value={lockReason}
              onChange={(e) => setLockReason(e.target.value)}
              rows={4}
              className="text-sm"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => setLockDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={actionBusy} onClick={() => void handleLock()}>
              {actionBusy ? "Locking…" : "Lock"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={releaseDialogOpen} onOpenChange={setReleaseDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Release report</DialogTitle>
            <DialogDescription>
              Release rationale is required. This control does not substitute documented human review records on file.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {!hasConfirmedApproval && isAdmin ? (
              <label className="flex cursor-pointer items-start gap-2 text-sm">
                <Checkbox
                  checked={overrideApproval}
                  onCheckedChange={(v) => setOverrideApproval(v === true)}
                  className="mt-0.5"
                />
                <span>Override approval requirement (admin)</span>
              </label>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="report-release-rationale">Release rationale</Label>
              <Textarea
                id="report-release-rationale"
                value={releaseRationale}
                onChange={(e) => setReleaseRationale(e.target.value)}
                rows={4}
                className="text-sm"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => setReleaseDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={
                actionBusy ||
                !releaseRationale.trim() ||
                (!hasConfirmedApproval && !(isAdmin && overrideApproval))
              }
              onClick={() => void handleRelease()}
            >
              {actionBusy ? "Releasing…" : "Release"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
    </TooltipProvider>
  )
}
