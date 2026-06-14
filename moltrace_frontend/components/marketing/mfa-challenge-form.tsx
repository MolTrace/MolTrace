"use client"

import { useState } from "react"
import { Fingerprint, KeyRound, Loader2, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  browserSupportsWebAuthn,
  loginWithPasskey,
  loginWithRecovery,
  loginWithTotp,
  type MfaChallenge,
  type MfaFactor,
} from "@/lib/auth/mfa"

// Login allows recovery (unlike step-up). Strongest-first.
const FACTOR_ORDER: MfaFactor[] = ["webauthn", "totp", "recovery"]
const FACTOR_LABEL: Record<MfaFactor, string> = {
  webauthn: "passkey",
  totp: "authenticator code",
  recovery: "recovery code",
  password: "password",
}

export function MfaChallengeForm({ challenge, onSuccess }: { challenge: MfaChallenge; onSuccess: () => void }) {
  const usable = FACTOR_ORDER.filter(
    (f) =>
      challenge.factors.includes(f) &&
      (f !== "webauthn" || (browserSupportsWebAuthn() && Boolean(challenge.webauthn_options))),
  )
  const [active, setActive] = useState<MfaFactor>(usable[0] ?? "totp")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function run(call: () => Promise<unknown>) {
    setBusy(true)
    setError("")
    try {
      await call()
      onSuccess()
    } catch (e) {
      setError(formatApiError(e, "Verification failed. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4" role="group" aria-label="Two-factor verification">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className="h-4 w-4" aria-hidden />
        Two-factor verification
      </div>
      <p className="text-sm text-muted-foreground">Confirm your second factor to finish signing in.</p>

      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {active === "webauthn" && challenge.webauthn_options ? (
        <Button
          type="button"
          className="w-full"
          disabled={busy}
          onClick={() => void run(() => loginWithPasskey(challenge.mfa_token, challenge.webauthn_options!))}
        >
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <Fingerprint className="mr-2 h-4 w-4" aria-hidden />}
          Verify with passkey
        </Button>
      ) : null}

      {active === "totp" ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            void run(() => loginWithTotp(challenge.mfa_token, code))
          }}
        >
          <Label htmlFor="mfa-totp">Authenticator code</Label>
          <InputOTP id="mfa-totp" maxLength={6} value={code} onChange={setCode} aria-label="Authenticator code">
            <InputOTPGroup>
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <InputOTPSlot key={i} index={i} />
              ))}
            </InputOTPGroup>
          </InputOTP>
          <Button type="submit" className="w-full" disabled={busy || code.length < 6}>
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Verify
          </Button>
        </form>
      ) : null}

      {active === "recovery" ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            void run(() => loginWithRecovery(challenge.mfa_token, code))
          }}
        >
          <Label htmlFor="mfa-recovery">Recovery code</Label>
          <Input
            id="mfa-recovery"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="xxxxx-xxxxx"
            autoComplete="one-time-code"
            spellCheck={false}
          />
          <Button type="submit" className="w-full" disabled={busy || !code.trim()}>
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Verify
          </Button>
        </form>
      ) : null}

      {usable.length > 1 ? (
        <div className="flex flex-wrap gap-x-3 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
          <span>Use another method:</span>
          {usable
            .filter((f) => f !== active)
            .map((f) => (
              <button
                key={f}
                type="button"
                className="underline-offset-2 hover:underline"
                onClick={() => {
                  setError("")
                  setCode("")
                  setActive(f)
                }}
              >
                <KeyRound className="mr-1 inline h-3 w-3" aria-hidden />
                {FACTOR_LABEL[f]}
              </button>
            ))}
        </div>
      ) : null}
    </div>
  )
}
