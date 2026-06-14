import {
  startAuthentication,
  startRegistration,
  browserSupportsWebAuthn,
} from "@simplewebauthn/browser"
import { apiFetch, ApiError } from "@/lib/api/client"
import { storeAuthSession, type AuthSessionUser } from "@/lib/auth/session"
import type { components } from "@/src/lib/api/schema"

// ── Types ────────────────────────────────────────────────────────────────
export type MfaStatus = components["schemas"]["MfaStatusResponse"]
export type StepUpResult = components["schemas"]["StepUpResult"]
export type StepUpOptions = components["schemas"]["StepUpOptionsResponse"]
export type TotpEnroll = components["schemas"]["TotpEnrollResponse"]
export type TotpConfirm = components["schemas"]["TotpConfirmResponse"]
export type RecoveryRegenerate = components["schemas"]["RecoveryRegenerateResponse"]
export type WebAuthnCredential = components["schemas"]["WebAuthnCredentialPublic"]
export type WebAuthnCredentialList = components["schemas"]["WebAuthnCredentialList"]
export type MfaPolicy = components["schemas"]["MfaPolicyResponse"]
export type MfaPolicyUpdate = components["schemas"]["MfaPolicyUpdate"]
export type AccessTokenResponse = components["schemas"]["AccessTokenResponse"]

export type MfaFactor = "webauthn" | "totp" | "recovery" | "password"

/** The 202 body returned by /auth/{login,sign-in,token} when a 2nd factor is
 *  required. NOT a typed OpenAPI component (the 202 isn't declared) — shape per
 *  the backend handoff. `apiFetch` returns this body for the 202 like any 2xx. */
export type MfaChallenge = {
  mfa_required: true
  mfa_token: string
  factors: MfaFactor[]
  webauthn_options?: Record<string, unknown> | null
  enrollment_required?: boolean
}

// The backend returns opaque WebAuthn option dicts; @simplewebauthn/browser
// consumes them as its `optionsJSON`. Derive those param types from the lib so
// we never hand-maintain the base64url option shapes.
type WebAuthnGetOptions = Parameters<typeof startAuthentication>[0]["optionsJSON"]
type WebAuthnCreateOptions = Parameters<typeof startRegistration>[0]["optionsJSON"]

/** Detail string the backend uses on a 401 when the session must re-authenticate
 *  before a privileged (signing / admin) action. Distinct from a normal auth 401. */
export const STEP_UP_REQUIRED = "step_up_required"

export { browserSupportsWebAuthn }

function errorDetail(err: unknown): string {
  if (err instanceof ApiError && err.data && typeof err.data === "object") {
    const d = (err.data as { detail?: unknown }).detail
    if (typeof d === "string") return d
  }
  return ""
}

/** True when a 401 means "re-authenticate" (step-up), not "not signed in". */
export function isStepUpRequired(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401 && errorDetail(err) === STEP_UP_REQUIRED
}

/** Discriminate the 202 MFA-challenge body from a normal token response. */
export function isMfaChallenge(body: unknown): body is MfaChallenge {
  return Boolean(body) && typeof body === "object" && (body as { mfa_required?: unknown }).mfa_required === true
}

// ── MFA-at-login verification (mfa_token is NOT a bearer) ───────────────────
function persist(res: AccessTokenResponse) {
  storeAuthSession(res.access_token, res.user as AuthSessionUser | null, {
    refreshToken: res.refresh_token,
    accessExpiresAt: res.expires_at,
  })
  return res
}

export async function loginWithTotp(mfaToken: string, code: string) {
  return persist(
    await apiFetch<AccessTokenResponse>("/auth/mfa/login/totp", {
      method: "POST",
      body: { mfa_token: mfaToken, code: code.trim() },
    }),
  )
}

export async function loginWithRecovery(mfaToken: string, code: string) {
  return persist(
    await apiFetch<AccessTokenResponse>("/auth/mfa/login/recovery", {
      method: "POST",
      body: { mfa_token: mfaToken, code: code.trim() },
    }),
  )
}

export async function loginWithPasskey(mfaToken: string, options: Record<string, unknown>) {
  // The backend returns a PublicKeyCredentialRequestOptionsJSON-shaped dict (opaque
  // to the schema); @simplewebauthn validates it at runtime.
  const assertion = await startAuthentication({ optionsJSON: options as unknown as WebAuthnGetOptions })
  return persist(
    await apiFetch<AccessTokenResponse>("/auth/mfa/login/webauthn", {
      method: "POST",
      body: { mfa_token: mfaToken, assertion },
    }),
  )
}

// ── Step-up ceremony ────────────────────────────────────────────────────────
export async function getStepUpOptions() {
  return apiFetch<StepUpOptions>("/auth/step-up/options", { method: "POST" })
}

export async function stepUpWithPasskey(options: Record<string, unknown>) {
  const assertion = await startAuthentication({ optionsJSON: options as unknown as WebAuthnGetOptions })
  return apiFetch<StepUpResult>("/auth/step-up/webauthn", { method: "POST", body: { assertion } })
}

export async function stepUpWithTotp(code: string) {
  return apiFetch<StepUpResult>("/auth/step-up/totp", { method: "POST", body: { code: code.trim() } })
}

export async function stepUpWithPassword(password: string) {
  return apiFetch<StepUpResult>("/auth/step-up/password", { method: "POST", body: { password } })
}

// ── Status ──────────────────────────────────────────────────────────────────
export async function getMfaStatus() {
  return apiFetch<MfaStatus>("/auth/mfa/status", { method: "GET" })
}

// ── TOTP enrollment / management ──────────────────────────────────────────────
export async function enrollTotp() {
  return apiFetch<TotpEnroll>("/auth/mfa/totp/enroll", { method: "POST" })
}

export async function confirmTotp(code: string) {
  return apiFetch<TotpConfirm>("/auth/mfa/totp/confirm", { method: "POST", body: { code: code.trim() } })
}

export async function deleteTotp() {
  return apiFetch<unknown>("/auth/mfa/totp", { method: "DELETE" })
}

// ── Passkey (WebAuthn) registration / management ──────────────────────────────
export async function registerPasskey(nickname?: string) {
  const options = await apiFetch<WebAuthnCreateOptions>("/auth/mfa/webauthn/register/options", { method: "POST" })
  const credential = await startRegistration({ optionsJSON: options })
  return apiFetch<WebAuthnCredential>("/auth/mfa/webauthn/register/verify", {
    method: "POST",
    body: { credential, nickname: nickname?.trim() || null },
  })
}

export async function listPasskeys() {
  const res = await apiFetch<WebAuthnCredentialList>("/auth/mfa/webauthn/credentials", { method: "GET" })
  return Array.isArray(res?.credentials) ? res.credentials : []
}

export async function renamePasskey(credentialPk: number, nickname: string) {
  return apiFetch<WebAuthnCredential>(`/auth/mfa/webauthn/credentials/${credentialPk}`, {
    method: "PATCH",
    body: { nickname: nickname.trim() },
  })
}

export async function deletePasskey(credentialPk: number) {
  return apiFetch<unknown>(`/auth/mfa/webauthn/credentials/${credentialPk}`, { method: "DELETE" })
}

// ── Recovery codes ────────────────────────────────────────────────────────────
export async function regenerateRecoveryCodes() {
  return apiFetch<RecoveryRegenerate>("/auth/mfa/recovery/regenerate", { method: "POST" })
}

// ── Admin: per-tenant policy ──────────────────────────────────────────────────
export async function getMfaPolicy(organizationId: number | string) {
  return apiFetch<MfaPolicy>(`/admin/mfa/policy/${encodeURIComponent(String(organizationId))}`, { method: "GET" })
}

export async function setMfaPolicy(organizationId: number | string, body: MfaPolicyUpdate) {
  return apiFetch<MfaPolicy>(`/admin/mfa/policy/${encodeURIComponent(String(organizationId))}`, {
    method: "PUT",
    body,
  })
}
