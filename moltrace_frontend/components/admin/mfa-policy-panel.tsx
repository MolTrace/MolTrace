"use client"

import { useCallback, useEffect, useState } from "react"
import { Loader2, ShieldCheck } from "lucide-react"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Checkbox } from "@/components/ui/checkbox"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { useStepUp } from "@/components/auth/step-up-provider"
import { withStepUp } from "@/lib/auth/with-step-up"
import { getMfaPolicy, setMfaPolicy } from "@/lib/auth/mfa"

const ALLOWED_FACTORS = ["totp", "webauthn"] as const

export function MfaPolicyPanel({ organizationId }: { organizationId: string | number }) {
  const { ensureStepUp } = useStepUp()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [msg, setMsg] = useState("")

  const [mfaRequired, setMfaRequired] = useState(false)
  const [gracePeriodDays, setGracePeriodDays] = useState("7")
  const [factors, setFactors] = useState<string[]>(["totp", "webauthn"])
  const [enforceForSso, setEnforceForSso] = useState(false)
  const [requireStepUpForSigning, setRequireStepUpForSigning] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const p = await getMfaPolicy(organizationId)
      setMfaRequired(p.mfa_required)
      setGracePeriodDays(String(p.grace_period_days))
      setFactors(Array.isArray(p.allowed_factors) && p.allowed_factors.length ? p.allowed_factors : ["totp", "webauthn"])
      setEnforceForSso(p.enforce_for_sso)
      setRequireStepUpForSigning(p.require_step_up_for_signing)
    } catch (e) {
      setError(formatApiError(e, "Could not load the MFA policy."))
    } finally {
      setLoading(false)
    }
  }, [organizationId])

  useEffect(() => {
    void load()
  }, [load])

  function toggleFactor(f: string, on: boolean) {
    setFactors((prev) => (on ? Array.from(new Set([...prev, f])) : prev.filter((x) => x !== f)))
  }

  async function save() {
    setSaving(true)
    setError("")
    setMsg("")
    const grace = Number(gracePeriodDays)
    if (!Number.isInteger(grace) || grace < 0) {
      setError("Grace period must be a non-negative whole number of days.")
      setSaving(false)
      return
    }
    try {
      // PUT is admin + step-up gated; withStepUp runs the ceremony + retries on 401.
      await withStepUp(
        () =>
          setMfaPolicy(organizationId, {
            mfa_required: mfaRequired,
            grace_period_days: grace,
            allowed_factors: factors,
            enforce_for_sso: enforceForSso,
            require_step_up_for_signing: requireStepUpForSigning,
          }),
        ensureStepUp,
      )
      setMsg("MFA policy saved.")
      await load()
    } catch (e) {
      setError(formatApiError(e, "Could not save the MFA policy."))
    } finally {
      setSaving(false)
    }
  }

  return (
    <ModuleCard
      accent="violet"
      eyebrow="Admin · Authentication"
      title={
        <span className="inline-flex items-center gap-2">
          <ShieldCheck className="h-4 w-4" aria-hidden />
          MFA policy
        </span>
      }
      description="Per-organization multi-factor requirements. Saving requires a step-up re-authentication."
    >
      {error ? <AlertCard variant="error" title="MFA policy" description={error} /> : null}
      {msg ? <AlertCard variant="success" title={msg} /> : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden />
          Loading policy…
        </p>
      ) : (
        <div className="space-y-4">
          <label className="flex items-center justify-between gap-3 rounded-md border p-3" htmlFor="mfa-required">
            <span>
              <span className="block text-sm font-medium">Require MFA</span>
              <span className="block text-xs text-muted-foreground">All members must enrol a second factor.</span>
            </span>
            <Switch id="mfa-required" checked={mfaRequired} onCheckedChange={setMfaRequired} />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="mfa-grace">Grace period (days)</Label>
              <Input
                id="mfa-grace"
                inputMode="numeric"
                value={gracePeriodDays}
                onChange={(e) => setGracePeriodDays(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Days new members may sign in before enrolment is enforced.</p>
            </div>
            <div className="space-y-1.5">
              <Label>Allowed factors</Label>
              <div className="flex flex-col gap-2 pt-1">
                {ALLOWED_FACTORS.map((f) => (
                  <label key={f} className="flex items-center gap-2 text-sm" htmlFor={`mfa-factor-${f}`}>
                    <Checkbox
                      id={`mfa-factor-${f}`}
                      checked={factors.includes(f)}
                      onCheckedChange={(v) => toggleFactor(f, v === true)}
                    />
                    {f === "totp" ? "Authenticator app (TOTP)" : "Passkey (WebAuthn)"}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <label className="flex items-center justify-between gap-3 rounded-md border p-3" htmlFor="mfa-enforce-sso">
            <span>
              <span className="block text-sm font-medium">Enforce for SSO users</span>
              <span className="block text-xs text-muted-foreground">Require MFA even for users who sign in via SSO.</span>
            </span>
            <Switch id="mfa-enforce-sso" checked={enforceForSso} onCheckedChange={setEnforceForSso} />
          </label>

          <label className="flex items-center justify-between gap-3 rounded-md border p-3" htmlFor="mfa-stepup-signing">
            <span>
              <span className="block text-sm font-medium">Step-up before signing</span>
              <span className="block text-xs text-muted-foreground">
                Require re-authentication before e-signatures and other privileged actions.
              </span>
            </span>
            <Switch id="mfa-stepup-signing" checked={requireStepUpForSigning} onCheckedChange={setRequireStepUpForSigning} />
          </label>

          <Button type="button" onClick={() => void save()} disabled={saving}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Save policy
          </Button>
        </div>
      )}
    </ModuleCard>
  )
}
