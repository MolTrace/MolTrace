"use client"

import { useCallback, useEffect, useState } from "react"
import { QRCodeSVG } from "qrcode.react"
import { Check, Copy, Download, Fingerprint, Loader2, Plus, ShieldCheck, Smartphone, Trash2, TriangleAlert } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp"
import { AlertCard } from "@/components/dashboard/alert-card"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { useStepUp } from "@/components/auth/step-up-provider"
import { withStepUp } from "@/lib/auth/with-step-up"
import {
  browserSupportsWebAuthn,
  confirmTotp,
  deletePasskey,
  deleteTotp,
  enrollTotp,
  getMfaStatus,
  listPasskeys,
  regenerateRecoveryCodes,
  registerPasskey,
  renamePasskey,
  type MfaStatus,
  type WebAuthnCredential,
} from "@/lib/auth/mfa"

function otpauthSecret(uri: string): string {
  try {
    return new URL(uri).searchParams.get("secret") ?? ""
  } catch {
    return ""
  }
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—"
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(s)
  return m ? m[1] : s
}

export function MfaManagementWorkspace() {
  const { ensureStepUp } = useStepUp()
  const [status, setStatus] = useState<MfaStatus | null>(null)
  const [passkeys, setPasskeys] = useState<WebAuthnCredential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState<string | null>(null)

  // TOTP enrollment flow
  const [enrollUri, setEnrollUri] = useState<string | null>(null)
  const [totpCode, setTotpCode] = useState("")

  // One-time recovery-codes display (after first factor confirm or regenerate)
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [copied, setCopied] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [s, pk] = await Promise.all([getMfaStatus(), listPasskeys().catch(() => [])])
      setStatus(s)
      setPasskeys(pk)
    } catch (e) {
      setError(formatApiError(e, "Could not load your security settings."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** Run a step-up-gated mutation (proactive ensureStepUp + reactive 401 retry). */
  async function gated(key: string, run: () => Promise<void>) {
    setBusy(key)
    setError("")
    try {
      await withStepUp(run, ensureStepUp)
    } catch (e) {
      setError(formatApiError(e, "That action could not be completed."))
    } finally {
      setBusy(null)
    }
  }

  async function beginTotp() {
    await gated("totp-enroll", async () => {
      const res = await enrollTotp()
      setEnrollUri(res.otpauth_uri)
      setTotpCode("")
    })
  }

  async function confirmTotpCode() {
    await gated("totp-confirm", async () => {
      const res = await confirmTotp(totpCode)
      if (!res.confirmed) throw new Error("That code was not accepted.")
      setEnrollUri(null)
      setTotpCode("")
      if (res.recovery_codes && res.recovery_codes.length > 0) setRecoveryCodes(res.recovery_codes)
      await load()
    })
  }

  async function removeTotp() {
    if (typeof window !== "undefined" && !window.confirm("Remove the authenticator app from your account?")) return
    await gated("totp-delete", async () => {
      await deleteTotp()
      await load()
    })
  }

  async function addPasskey() {
    await gated("passkey-add", async () => {
      const nickname = typeof window !== "undefined" ? window.prompt("Name this passkey (optional):") ?? undefined : undefined
      await registerPasskey(nickname)
      await load()
    })
  }

  async function rename(pk: WebAuthnCredential) {
    const next = typeof window !== "undefined" ? window.prompt("Rename passkey:", pk.nickname ?? "") : null
    if (next == null) return
    await gated(`passkey-rename-${pk.id}`, async () => {
      await renamePasskey(pk.id, next)
      await load()
    })
  }

  async function removePasskey(pk: WebAuthnCredential) {
    if (typeof window !== "undefined" && !window.confirm(`Remove passkey "${pk.nickname || "unnamed"}"?`)) return
    await gated(`passkey-del-${pk.id}`, async () => {
      await deletePasskey(pk.id)
      await load()
    })
  }

  async function regenerate() {
    if (
      typeof window !== "undefined" &&
      !window.confirm("Regenerate recovery codes? Your existing codes will stop working immediately.")
    ) {
      return
    }
    await gated("recovery", async () => {
      const res = await regenerateRecoveryCodes()
      setRecoveryCodes(res.recovery_codes)
      await load()
    })
  }

  function copyRecovery() {
    if (!recoveryCodes) return
    navigator.clipboard
      .writeText(recoveryCodes.join("\n"))
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => {})
  }

  function downloadRecovery() {
    if (!recoveryCodes || typeof document === "undefined") return
    const blob = new Blob([`MolTrace recovery codes\n\n${recoveryCodes.join("\n")}\n`], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "moltrace-recovery-codes.txt"
    a.click()
    URL.revokeObjectURL(url)
  }

  const totpOn = status?.totp_confirmed === true

  return (
    <div className="space-y-6">
      {/* Org-requires-MFA banner */}
      {status?.org_mfa_required && status.factors.length === 0 ? (
        <AlertCard
          variant={status.in_grace ? "warning" : "error"}
          icon={TriangleAlert}
          title="Your organization requires multi-factor authentication"
          description={
            status.in_grace
              ? "You're in the grace period — set up a second factor now to keep access."
              : "Set up a second factor now to restore full access."
          }
        />
      ) : null}

      {error ? <AlertCard variant="error" title="Security settings" description={error} /> : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden />
          Loading…
        </p>
      ) : (
        <>
          {/* Authenticator app (TOTP) */}
          <section className="rounded-lg border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Smartphone className="h-4 w-4" aria-hidden />
                <h3 className="text-sm font-semibold">Authenticator app (TOTP)</h3>
                <Badge variant="outline" className={totpOn ? "border-success/50 text-success" : "text-muted-foreground"}>
                  {totpOn ? "enabled" : "not set up"}
                </Badge>
              </div>
              {totpOn ? (
                <Button type="button" size="sm" variant="ghost" onClick={() => void removeTotp()} disabled={busy === "totp-delete"}>
                  {busy === "totp-delete" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Trash2 className="mr-1.5 h-4 w-4 text-destructive" aria-hidden />}
                  Remove
                </Button>
              ) : enrollUri ? null : (
                <Button type="button" size="sm" onClick={() => void beginTotp()} disabled={busy === "totp-enroll"}>
                  {busy === "totp-enroll" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Plus className="mr-1.5 h-4 w-4" aria-hidden />}
                  Set up
                </Button>
              )}
            </div>

            {enrollUri ? (
              <div className="mt-4 flex flex-col gap-4 sm:flex-row">
                <div className="rounded-md border bg-white p-3">
                  <QRCodeSVG value={enrollUri} size={160} />
                </div>
                <div className="flex-1 space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Scan the QR with your authenticator app, or enter this key manually, then confirm the 6-digit code.
                  </p>
                  <code className="block break-all rounded border bg-muted/30 px-2 py-1 font-mono text-xs">
                    {otpauthSecret(enrollUri) || "—"}
                  </code>
                  <div className="space-y-2">
                    <Label htmlFor="totp-confirm">Verification code</Label>
                    <InputOTP id="totp-confirm" maxLength={6} value={totpCode} onChange={setTotpCode} aria-label="Verification code">
                      <InputOTPGroup>
                        {[0, 1, 2, 3, 4, 5].map((i) => (
                          <InputOTPSlot key={i} index={i} />
                        ))}
                      </InputOTPGroup>
                    </InputOTP>
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" size="sm" onClick={() => void confirmTotpCode()} disabled={busy === "totp-confirm" || totpCode.length < 6}>
                      {busy === "totp-confirm" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : null}
                      Confirm
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setEnrollUri(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          {/* Passkeys (WebAuthn) */}
          <section className="rounded-lg border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Fingerprint className="h-4 w-4" aria-hidden />
                <h3 className="text-sm font-semibold">Passkeys</h3>
                <Badge variant="outline" className="text-muted-foreground">
                  {passkeys.length}
                </Badge>
              </div>
              <Button
                type="button"
                size="sm"
                onClick={() => void addPasskey()}
                disabled={busy === "passkey-add" || !browserSupportsWebAuthn()}
                title={browserSupportsWebAuthn() ? undefined : "This browser doesn't support passkeys"}
              >
                {busy === "passkey-add" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Plus className="mr-1.5 h-4 w-4" aria-hidden />}
                Add passkey
              </Button>
            </div>
            {passkeys.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">No passkeys registered.</p>
            ) : (
              <ul className="mt-3 divide-y rounded-md border">
                {passkeys.map((pk) => (
                  <li key={pk.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{pk.nickname || pk.device_type || "Passkey"}</div>
                      <div className="text-xs text-muted-foreground">
                        added {fmtDate(pk.created_at)} · last used {fmtDate(pk.last_used_at)}
                        {pk.backed_up ? " · synced" : ""}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <Button type="button" size="sm" variant="ghost" onClick={() => void rename(pk)} disabled={busy === `passkey-rename-${pk.id}`}>
                        Rename
                      </Button>
                      <Button type="button" size="sm" variant="ghost" onClick={() => void removePasskey(pk)} disabled={busy === `passkey-del-${pk.id}`}>
                        {busy === `passkey-del-${pk.id}` ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Trash2 className="h-4 w-4 text-destructive" aria-hidden />}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Recovery codes */}
          <section className="rounded-lg border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4" aria-hidden />
                <h3 className="text-sm font-semibold">Recovery codes</h3>
                <Badge variant="outline" className="text-muted-foreground">
                  {status?.recovery_remaining ?? 0} remaining
                </Badge>
              </div>
              <Button type="button" size="sm" variant="outline" onClick={() => void regenerate()} disabled={busy === "recovery"}>
                {busy === "recovery" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : null}
                Regenerate
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              One-time codes to sign in if you lose your other factors. Regenerating invalidates the old set.
            </p>
          </section>
        </>
      )}

      {/* One-time recovery-codes modal */}
      <Dialog open={recoveryCodes != null} onOpenChange={(o) => (!o ? setRecoveryCodes(null) : undefined)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TriangleAlert className="h-4 w-4 text-warning" aria-hidden />
              Save your recovery codes
            </DialogTitle>
            <DialogDescription>
              These are shown only once. Store them somewhere safe — each can be used once if you lose your other factors.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-2 rounded-md border bg-muted/20 p-3 font-mono text-sm">
            {(recoveryCodes ?? []).map((c, i) => (
              <span key={i} className="break-all">
                {c}
              </span>
            ))}
          </div>
          <DialogFooter className="sm:justify-between">
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="outline" onClick={copyRecovery}>
                {copied ? <Check className="mr-1.5 h-4 w-4" aria-hidden /> : <Copy className="mr-1.5 h-4 w-4" aria-hidden />}
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={downloadRecovery}>
                <Download className="mr-1.5 h-4 w-4" aria-hidden />
                Download
              </Button>
            </div>
            <Button type="button" size="sm" onClick={() => setRecoveryCodes(null)}>
              I&apos;ve saved them
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
