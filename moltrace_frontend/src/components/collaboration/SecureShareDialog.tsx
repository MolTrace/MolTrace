"use client"

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { apiFetch } from "@/lib/api/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"

export type ShareScope = "project" | "session" | "report"

const PERMISSIONS = ["view", "comment", "review"] as const

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

/** Build user-facing link text from API record — never uses token_hash. */
export function pickShareLinkDisplay(row: Record<string, unknown>): string | null {
  for (const k of ["share_url", "url", "link", "redeem_url"] as const) {
    const v = row[k]
    if (typeof v === "string" && v.trim()) return v.trim()
  }
  const token = row.token
  if (typeof token === "string" && token.trim()) return token.trim()
  return null
}

export type SecureShareDialogProps = {
  trigger?: ReactNode
  /** Share target kind */
  scope: ShareScope
  /** When true, scope cannot be changed */
  lockScope?: boolean
  defaultProjectId?: number | null
  defaultSessionId?: number | null
  defaultReportId?: number | null
  /** When true, target id field is read-only */
  lockTargetId?: boolean
  /** Disable opening (e.g. no session loaded) */
  disabled?: boolean
}

export function SecureShareDialog({
  trigger,
  scope: scopeProp,
  lockScope = false,
  defaultProjectId = null,
  defaultSessionId = null,
  defaultReportId = null,
  lockTargetId = false,
  disabled = false,
}: SecureShareDialogProps) {
  const [open, setOpen] = useState(false)
  const [scope, setScope] = useState<ShareScope>(scopeProp)

  const [projectIdStr, setProjectIdStr] = useState(() =>
    defaultProjectId != null ? String(defaultProjectId) : "",
  )
  const [sessionIdStr, setSessionIdStr] = useState(() =>
    defaultSessionId != null ? String(defaultSessionId) : "",
  )
  const [reportIdStr, setReportIdStr] = useState(() =>
    defaultReportId != null ? String(defaultReportId) : "",
  )

  const [permission, setPermission] = useState<string>("view")
  const [expiresLocal, setExpiresLocal] = useState("")

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [lastRecord, setLastRecord] = useState<Record<string, unknown> | null>(null)
  const [revokeBusy, setRevokeBusy] = useState(false)

  useEffect(() => {
    setScope(scopeProp)
  }, [scopeProp])

  useEffect(() => {
    if (defaultProjectId != null) setProjectIdStr(String(defaultProjectId))
  }, [defaultProjectId])

  useEffect(() => {
    if (defaultSessionId != null) setSessionIdStr(String(defaultSessionId))
  }, [defaultSessionId])

  useEffect(() => {
    if (defaultReportId != null) setReportIdStr(String(defaultReportId))
  }, [defaultReportId])

  const shareLinkText = useMemo(
    () => (lastRecord ? pickShareLinkDisplay(lastRecord) : null),
    [lastRecord],
  )

  const shareNumericId = useMemo(() => {
    if (!lastRecord) return null
    const id = lastRecord.id
    const n = typeof id === "number" ? id : Number(id)
    return Number.isFinite(n) ? Math.trunc(n) : null
  }, [lastRecord])

  const parsePositiveInt = (s: string): number | null => {
    const t = s.trim()
    if (!t) return null
    const n = Number(t)
    if (!Number.isFinite(n) || n < 1) return null
    return Math.trunc(n)
  }

  const buildCreateBody = useCallback((): Record<string, unknown> => {
    const body: Record<string, unknown> = {
      permission,
      metadata_json: {},
    }
    if (scope === "project") {
      const pid = parsePositiveInt(projectIdStr)
      if (pid != null) body.project_id = pid
    } else if (scope === "session") {
      const sid = parsePositiveInt(sessionIdStr)
      if (sid != null) body.session_id = sid
    } else {
      const rid = parsePositiveInt(reportIdStr)
      if (rid != null) body.report_id = rid
    }
    if (expiresLocal.trim()) {
      const d = new Date(expiresLocal)
      if (!Number.isNaN(d.getTime())) body.expires_at = d.toISOString()
    }
    return body
  }, [scope, projectIdStr, sessionIdStr, reportIdStr, permission, expiresLocal])

  const validateBody = useCallback((): string | null => {
    const b = buildCreateBody()
    if (b.project_id == null && b.session_id == null && b.report_id == null) {
      return "Choose a share target and enter a valid id."
    }
    return null
  }, [buildCreateBody])

  async function handleCreate() {
    const v = validateBody()
    if (v) {
      setError(v)
      return
    }
    setBusy(true)
    setError("")
    try {
      const body = buildCreateBody()
      const data = await apiFetch<unknown>("/share-links", {
        method: "POST",
        body,
      })
      setLastRecord(isRecord(data) ? data : null)
    } catch (err) {
      setError(formatApiError(err, "Could not create share link."))
      setLastRecord(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleRevoke() {
    if (shareNumericId == null) return
    setRevokeBusy(true)
    setError("")
    try {
      const data = await apiFetch<unknown>(
        `/share-links/${encodeURIComponent(String(shareNumericId))}/revoke`,
        { method: "POST" },
      )
      setLastRecord(isRecord(data) ? data : null)
    } catch (err) {
      setError(formatApiError(err, "Could not revoke share link."))
    } finally {
      setRevokeBusy(false)
    }
  }

  async function copyLink() {
    if (!shareLinkText) return
    try {
      await navigator.clipboard.writeText(shareLinkText)
    } catch {
      setError("Clipboard unavailable.")
    }
  }

  const scopeSelectDisabled = lockScope || disabled
  const targetReadOnly = lockTargetId || disabled

  const defaultTrigger = (
    <Button type="button" variant="outline" size="sm" disabled={disabled}>
      Secure share
    </Button>
  )

  const revoked = Boolean(lastRecord && lastRecord.revoked === true)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger ?? defaultTrigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Secure share link</DialogTitle>
          <DialogDescription>
            Create a scoped collaboration link. Only fields supported by the backend are sent.
          </DialogDescription>
        </DialogHeader>

        <Alert className="border-muted bg-muted/30">
          <AlertDescription className="text-xs text-muted-foreground">
            Only share with authorized collaborators. Shared access is audited.
          </AlertDescription>
        </Alert>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Share target</Label>
            {lockScope ? (
              <p className="text-sm capitalize text-muted-foreground">{scope}</p>
            ) : (
              <Select
                value={scope}
                onValueChange={(v) => setScope(v as ShareScope)}
                disabled={scopeSelectDisabled}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="project">Project</SelectItem>
                  <SelectItem value="session">Session</SelectItem>
                  <SelectItem value="report">Report</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>

          {scope === "project" ? (
            <div className="space-y-1.5">
              <Label htmlFor="ss-project-id" className="text-xs">
                project_id
              </Label>
              <Input
                id="ss-project-id"
                className="font-mono text-xs"
                value={projectIdStr}
                onChange={(e) => setProjectIdStr(e.target.value)}
                readOnly={targetReadOnly}
                inputMode="numeric"
              />
            </div>
          ) : null}

          {scope === "session" ? (
            <div className="space-y-1.5">
              <Label htmlFor="ss-session-id" className="text-xs">
                session_id
              </Label>
              <Input
                id="ss-session-id"
                className="font-mono text-xs"
                value={sessionIdStr}
                onChange={(e) => setSessionIdStr(e.target.value)}
                readOnly={targetReadOnly}
                inputMode="numeric"
              />
            </div>
          ) : null}

          {scope === "report" ? (
            <div className="space-y-1.5">
              <Label htmlFor="ss-report-id" className="text-xs">
                report_id
              </Label>
              <Input
                id="ss-report-id"
                className="font-mono text-xs"
                value={reportIdStr}
                onChange={(e) => setReportIdStr(e.target.value)}
                readOnly={targetReadOnly}
                inputMode="numeric"
              />
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label className="text-xs">permission</Label>
            <Select value={permission} onValueChange={setPermission} disabled={disabled}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERMISSIONS.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ss-expires" className="text-xs">
              expires_at (optional)
            </Label>
            <Input
              id="ss-expires"
              type="datetime-local"
              value={expiresLocal}
              onChange={(e) => setExpiresLocal(e.target.value)}
              disabled={disabled}
            />
          </div>
        </div>

        {error ? <p className="text-xs text-destructive">{error}</p> : null}

        {lastRecord ? (
          <div className="space-y-2 rounded-md border bg-muted/20 p-3">
            <p className="text-xs font-medium text-muted-foreground">Generated link</p>
            {shareLinkText ? (
              <p className="break-all font-mono text-[11px] leading-relaxed">{shareLinkText}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Link was created; the server did not return a display URL or token in this response.
              </p>
            )}
            {revoked ? (
              <p className="text-xs text-amber-800 dark:text-amber-200">This share link is revoked.</p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={!shareLinkText || revoked}
                onClick={() => void copyLink()}
              >
                Copy link
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={revokeBusy || shareNumericId == null || revoked}
                onClick={() => void handleRevoke()}
              >
                {revokeBusy ? "Revoking…" : "Revoke"}
              </Button>
            </div>
          </div>
        ) : null}

        <DialogFooter className="gap-2 sm:justify-end">
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            Close
          </Button>
          <Button type="button" disabled={busy || disabled} onClick={() => void handleCreate()}>
            {busy ? "Creating…" : "Create link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
