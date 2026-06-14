"use client"

import { useCallback, useEffect, useState } from "react"
import { Check, Copy, KeyRound, Loader2, RefreshCw, ShieldOff, Trash2, TriangleAlert } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { components } from "@/src/lib/api/schema"

type ScimTokenInfo = components["schemas"]["ScimTokenInfo"]
type ScimTokenIssueResponse = components["schemas"]["ScimTokenIssueResponse"]

// SCIM service-provider base URL = {API_ORIGIN}/scim/v2. Shown for the IdP admin
// to paste into Okta/Entra; exact when NEXT_PUBLIC_SSO_API_ORIGIN is configured.
const SSO_API_ORIGIN = (process.env.NEXT_PUBLIC_SSO_API_ORIGIN || "").trim().replace(/\/$/, "")
const SCIM_BASE_URL = SSO_API_ORIGIN ? `${SSO_API_ORIGIN}/scim/v2` : ""
const SCIM_BASE_PLACEHOLDER = "https://<your-api-origin>/scim/v2"

/** Trim an ISO timestamp to a readable, deterministic "YYYY-MM-DD HH:MM UTC". */
function fmtDate(s: string | null | undefined): string {
  if (!s) return "—"
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(s)
  return m ? `${m[1]} ${m[2]} UTC` : s
}

function CopyRow({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string
  value: string
  copied: boolean
  onCopy: () => void
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <Button type="button" size="sm" variant="ghost" onClick={onCopy} aria-label={`Copy ${label}`}>
          {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
          <span className="ml-1.5 text-xs">{copied ? "Copied" : "Copy"}</span>
        </Button>
      </div>
      <code className="block break-all rounded border bg-background px-2 py-1 font-mono text-xs">{value}</code>
    </div>
  )
}

export function ScimProvisioningSection({ connectionId, enabled }: { connectionId: number; enabled: boolean }) {
  const [info, setInfo] = useState<ScimTokenInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [issued, setIssued] = useState<ScimTokenIssueResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<"token" | "url" | null>(null)

  const path = `/auth/sso/connections/${connectionId}/scim-token`

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const res = await apiFetch<ScimTokenInfo>(path, { method: "GET" })
      setInfo(res)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setInfo(null) // no live token — expected
      } else {
        setErr(formatApiError(e, "Could not load SCIM token status."))
        setInfo(null)
      }
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    setIssued(null)
    void load()
  }, [enabled, load])

  async function issue() {
    setBusy(true)
    setErr("")
    try {
      // POST mints, or rotates (revoke-then-issue) when one already exists. A rapid
      // re-issue can return 409 ("just issued; retry") — surfaced via formatApiError.
      const res = await apiFetch<ScimTokenIssueResponse>(path, { method: "POST" })
      setIssued(res)
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Could not issue the SCIM token."))
    } finally {
      setBusy(false)
    }
  }

  async function revoke() {
    if (
      typeof window !== "undefined" &&
      !window.confirm("Revoke this SCIM token? The IdP will stop provisioning users until a new token is issued.")
    ) {
      return
    }
    setBusy(true)
    setErr("")
    let revoked = true
    try {
      await apiFetch(path, { method: "DELETE" })
    } catch (e) {
      // 404 = no live token (already revoked, e.g. by a concurrent admin / another
      // tab) — that is the desired end state, not an error. Mirror load()'s 404
      // handling; only a real failure keeps the current token shown.
      if (!(e instanceof ApiError && e.status === 404)) {
        setErr(formatApiError(e, "Could not revoke the SCIM token."))
        revoked = false
      }
    }
    if (revoked) {
      // Token is gone (200) or was already gone (404) — clear optimistically; no
      // reload needed, a GET would just 404. A real failure keeps the token shown.
      setIssued(null)
      setInfo(null)
    }
    setBusy(false)
  }

  async function copy(kind: "token" | "url", text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      // clipboard unavailable — value stays visible to copy manually
    }
  }

  if (!enabled) {
    return (
      <AlertCard
        variant="info"
        icon={ShieldOff}
        title="SCIM provisioning is disabled"
        description="Enable this SSO connection to issue or manage a SCIM token. Disabling the connection also disables SCIM."
      />
    )
  }

  return (
    <div className="space-y-3">
      {err ? <AlertCard variant="error" title="SCIM token error" description={err} /> : null}

      {/* One-time plaintext token — shown exactly once at issue time. */}
      {issued ? (
        <div className="space-y-2 rounded-lg border border-warning/40 bg-muted/20 p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-warning">
            <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
            Copy this token now — it won&apos;t be shown again.
          </div>
          <CopyRow label="Bearer token" value={issued.token} copied={copied === "token"} onCopy={() => void copy("token", issued.token)} />
          <CopyRow
            label="SCIM base URL"
            value={SCIM_BASE_URL || SCIM_BASE_PLACEHOLDER}
            copied={copied === "url"}
            onCopy={() => void copy("url", SCIM_BASE_URL || SCIM_BASE_PLACEHOLDER)}
          />
          <p className="text-xs text-muted-foreground">
            Paste both into the SCIM provisioning settings of your IdP (Okta, Entra ID, …).
            {SCIM_BASE_URL ? null : " Set NEXT_PUBLIC_SSO_API_ORIGIN to display the exact SCIM base URL."}
          </p>
          <Button type="button" size="sm" variant="outline" onClick={() => setIssued(null)}>
            Done — I&apos;ve copied it
          </Button>
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden />
          Loading SCIM token status…
        </p>
      ) : info ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="border-success/50 font-normal text-success">
              token active
            </Badge>
            <code className="font-mono text-xs">{info.token_prefix}…</code>
          </div>
          <dl className="grid gap-3 text-xs sm:grid-cols-3">
            <div>
              <dt className="font-medium uppercase tracking-wide text-muted-foreground">issued</dt>
              <dd className="mt-0.5 font-mono">{fmtDate(info.created_at)}</dd>
            </div>
            <div>
              <dt className="font-medium uppercase tracking-wide text-muted-foreground">last sync</dt>
              <dd className="mt-0.5 font-mono">{fmtDate(info.last_used_at)}</dd>
            </div>
            <div>
              <dt className="font-medium uppercase tracking-wide text-muted-foreground">expires</dt>
              <dd className="mt-0.5 font-mono">{fmtDate(info.expires_at)}</dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => void issue()} disabled={busy}>
              {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-1.5 h-4 w-4" aria-hidden />}
              Rotate
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void revoke()} disabled={busy}>
              <Trash2 className="mr-1.5 h-4 w-4 text-destructive" aria-hidden />
              Revoke
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">Rotating issues a new token and invalidates the current one immediately.</p>
        </div>
      ) : !issued ? (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            No SCIM token. Generate one to let your identity provider auto-provision and deprovision users for this organization.
          </p>
          <Button type="button" size="sm" onClick={() => void issue()} disabled={busy}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <KeyRound className="mr-1.5 h-4 w-4" aria-hidden />}
            Generate SCIM token
          </Button>
        </div>
      ) : null}
    </div>
  )
}
