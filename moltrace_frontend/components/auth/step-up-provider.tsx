"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import { Fingerprint, KeyRound, Loader2, ShieldCheck } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { PasswordInput } from "@/components/ui/password-input"
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp"
import { Label } from "@/components/ui/label"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  browserSupportsWebAuthn,
  getStepUpOptions,
  stepUpWithPasskey,
  stepUpWithPassword,
  stepUpWithTotp,
  type MfaFactor,
  type StepUpOptions,
} from "@/lib/auth/mfa"

type StepUpContextValue = {
  /** Open the step-up modal; resolves true once the session is re-authenticated,
   *  false if the user cancels. Recovery codes are never accepted for step-up. */
  ensureStepUp: () => Promise<boolean>
}

// Default (no provider mounted — e.g. an isolated render): step-up can't run, so a
// gated 401 surfaces as-is via withStepUp rather than crashing the tree. The
// authenticated app always mounts StepUpProvider in the app shell.
const StepUpContext = createContext<StepUpContextValue>({ ensureStepUp: async () => false })

export function useStepUp(): StepUpContextValue {
  return useContext(StepUpContext)
}

// Strongest-first; recovery is intentionally absent (never valid for step-up).
const FACTOR_ORDER: MfaFactor[] = ["webauthn", "totp", "password"]

function pickFactors(options: StepUpOptions | null): MfaFactor[] {
  const offered = new Set((options?.factors ?? []) as MfaFactor[])
  const usable = FACTOR_ORDER.filter((f) => offered.has(f))
  // If webauthn is offered but this browser can't do it, drop it so the user can
  // still fall back to a weaker offered factor.
  return usable.filter((f) => f !== "webauthn" || browserSupportsWebAuthn())
}

const FACTOR_LABEL: Record<MfaFactor, string> = {
  webauthn: "passkey",
  totp: "authenticator code",
  password: "password",
  recovery: "recovery code",
}

function StepUpDialog({ open, onResolved }: { open: boolean; onResolved: (v: boolean) => void }) {
  const [loading, setLoading] = useState(false)
  const [options, setOptions] = useState<StepUpOptions | null>(null)
  const [factors, setFactors] = useState<MfaFactor[]>([])
  const [active, setActive] = useState<MfaFactor | null>(null)
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError("")
    setCode("")
    setPassword("")
    setOptions(null)
    setActive(null)
    ;(async () => {
      try {
        const opts = await getStepUpOptions()
        if (cancelled) return
        const usable = pickFactors(opts)
        setOptions(opts)
        setFactors(usable)
        setActive(usable[0] ?? null)
      } catch (e) {
        if (!cancelled) setError(formatApiError(e, "Could not start the verification."))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open])

  async function complete(run: () => Promise<{ stepped_up: boolean }>) {
    setBusy(true)
    setError("")
    try {
      const res = await run()
      if (res.stepped_up) {
        onResolved(true)
      } else {
        setError("Verification did not complete. Please try again.")
      }
    } catch (e) {
      setError(formatApiError(e, "Verification failed. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onResolved(false) : undefined)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" aria-hidden />
            Verify it&apos;s you
          </DialogTitle>
          <DialogDescription>
            This action requires re-authentication. Confirm with your strongest second factor.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="py-4 text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden />
            Preparing verification…
          </p>
        ) : error && !active ? (
          <p className="py-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : active ? (
          <div className="space-y-4 py-1">
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}

            {active === "webauthn" && options?.webauthn_options ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Use your passkey or security key to continue.</p>
                <Button
                  type="button"
                  className="w-full"
                  disabled={busy}
                  onClick={() => void complete(() => stepUpWithPasskey(options.webauthn_options!))}
                >
                  {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <Fingerprint className="mr-2 h-4 w-4" aria-hidden />}
                  Verify with passkey
                </Button>
              </div>
            ) : null}

            {active === "totp" ? (
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  void complete(() => stepUpWithTotp(code))
                }}
              >
                <Label htmlFor="stepup-totp">Authenticator code</Label>
                <InputOTP id="stepup-totp" maxLength={6} value={code} onChange={setCode} aria-label="Authenticator code">
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

            {active === "password" ? (
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  void complete(() => stepUpWithPassword(password))
                }}
              >
                <Label htmlFor="stepup-password">Password</Label>
                <PasswordInput
                  id="stepup-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
                <Button type="submit" className="w-full" disabled={busy || !password}>
                  {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Verify
                </Button>
              </form>
            ) : null}

            {factors.length > 1 ? (
              <div className="flex flex-wrap gap-x-3 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
                <span>Use another method:</span>
                {factors
                  .filter((f) => f !== active)
                  .map((f) => (
                    <button
                      key={f}
                      type="button"
                      className="underline-offset-2 hover:underline"
                      onClick={() => {
                        setError("")
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
        ) : (
          <p className="py-2 text-sm text-muted-foreground">No verification method is available for your account.</p>
        )}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onResolved(false)} disabled={busy}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function StepUpProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const resolverRef = useRef<((v: boolean) => void) | null>(null)

  const ensureStepUp = useCallback(
    () =>
      new Promise<boolean>((resolve) => {
        // Abandon any in-flight ceremony (resolve it false) before starting a new
        // one, so an earlier awaiter never hangs on an overwritten resolver.
        resolverRef.current?.(false)
        resolverRef.current = resolve
        setOpen(true)
      }),
    [],
  )

  const onResolved = useCallback((v: boolean) => {
    setOpen(false)
    const resolve = resolverRef.current
    resolverRef.current = null
    resolve?.(v)
  }, [])

  return (
    <StepUpContext.Provider value={{ ensureStepUp }}>
      {children}
      <StepUpDialog open={open} onResolved={onResolved} />
    </StepUpContext.Provider>
  )
}
