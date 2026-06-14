"use client"

import type { FormEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { ApiError, apiFetch, buildApiPath } from "@/lib/api/client"
import { storeAuthSession } from "@/lib/auth/session"
import { isMfaChallenge, type MfaChallenge } from "@/lib/auth/mfa"
import { MfaChallengeForm } from "@/components/marketing/mfa-challenge-form"

type AuthUser = {
  id: number
  email: string
  is_admin: boolean
  is_verified: boolean
}

type AuthPageResponse = {
  access_token: string | null
  token_type?: string | null
  expires_at?: string | null
  user: AuthUser | null
  requires_email_verification?: boolean
  detail?: string
}

const SIGN_IN_FAILURE_MESSAGE =
  "We couldn't sign you in. Check your email and password, then try again."

// The backend strips the specific enforce-SSO detail at the proxy (401/403 bodies
// are sanitized), but the 403 status survives — and on the login endpoint a 403
// means SSO is required (a bad password is 401). We supply the user-facing copy.
const SSO_REQUIRED_MESSAGE =
  "Single sign-on is required for your organization. Please sign in through your identity provider."

const SSO_ERROR_MESSAGE =
  "SSO sign-in could not be completed — please try again, or use your password."

type SignInFormProps = {
  /** `?sso_error=1` arrived on the URL (backend bounced a failed SSO round-trip). */
  ssoError?: boolean
  /** `?sso=<slug>` deep link — pre-fills the organization SSO sign-in ID. */
  ssoSlug?: string
}

function formValue(formData: FormData, key: string, trim = true) {
  const value = formData.get(key)
  if (typeof value !== "string") return ""
  return trim ? value.trim() : value
}

function authErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.status === 401) return SIGN_IN_FAILURE_MESSAGE
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return fallback
}

export function SignInForm({ ssoError = false, ssoSlug = "" }: SignInFormProps) {
  const router = useRouter()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ssoRequired, setSsoRequired] = useState(false)
  const [slug, setSlug] = useState(ssoSlug)
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null)

  function startSso(orgSlug: string) {
    const clean = orgSlug.trim().toLowerCase()
    if (!clean) return
    // Full-page navigation (NOT fetch): the backend 302s into the IdP authorize
    // chain, which only works as a top-level browser navigation. Same-origin proxy
    // path — the proxy forwards the 302 verbatim for /auth/sso/*.
    window.location.assign(buildApiPath(`/auth/sso/${encodeURIComponent(clean)}/login`))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    setIsSubmitting(true)
    setMessage(null)
    setError(null)
    setSsoRequired(false)

    try {
      const data = await apiFetch<AuthPageResponse>("/auth/sign-in", {
        method: "POST",
        body: {
          email: formValue(formData, "email"),
          password: formValue(formData, "password", false),
        },
      })

      // 202 second-factor challenge: apiFetch returns the body for any 2xx, so
      // detect the challenge by shape (the mfa_token is NOT a bearer).
      if (isMfaChallenge(data)) {
        setChallenge(data)
        return
      }

      if (!data.access_token) {
        setMessage(data.detail || "Check your email to finish signing in.")
        return
      }

      storeAuthSession(data.access_token, data.user)
      setMessage(data.user?.is_admin ? "Signed in with admin access." : "Signed in.")
      router.push("/dashboard")
    } catch (submitError) {
      // A 403 on the login endpoint = this org enforces SSO; steer to SSO instead
      // of showing a generic "wrong password" error.
      if (submitError instanceof ApiError && submitError.status === 403) {
        setSsoRequired(true)
      } else {
        setError(authErrorMessage(submitError, "Unable to sign in."))
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>Enter your email and password to access your workspace.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {challenge ? (
          <MfaChallengeForm challenge={challenge} onSuccess={() => router.push("/dashboard")} />
        ) : (
          <>
        {ssoError ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{SSO_ERROR_MESSAGE}</AlertDescription>
          </Alert>
        ) : null}
        {ssoRequired ? (
          <Alert role="alert">
            <AlertDescription>{SSO_REQUIRED_MESSAGE}</AlertDescription>
          </Alert>
        ) : null}

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="sign-in-email">Email</Label>
            <Input
              id="sign-in-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              disabled={isSubmitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sign-in-password">Password</Label>
            <PasswordInput
              id="sign-in-password"
              name="password"
              autoComplete="current-password"
              required
              disabled={isSubmitting}
            />
          </div>
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="text-sm text-muted-foreground" role="status">
              {message}
            </p>
          ) : null}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign In"}
          </Button>
        </form>

        <div className="flex items-center gap-3" aria-hidden>
          <span className="h-px flex-1 bg-border" />
          <span className="text-xs uppercase tracking-wide text-muted-foreground">or</span>
          <span className="h-px flex-1 bg-border" />
        </div>

        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            startSso(slug)
          }}
        >
          <p className="text-sm font-medium">Single sign-on</p>
          <div className="flex gap-2">
            <Input
              id="sso-slug"
              name="sso-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="organization ID"
              autoComplete="organization"
              spellCheck={false}
              aria-label="Organization sign-in ID"
            />
            <Button type="submit" variant="outline" disabled={!slug.trim()}>
              Sign in with SSO
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Enter your organization&apos;s sign-in ID, or use the SSO link your administrator provided.
          </p>
        </form>
          </>
        )}
      </CardContent>
      <CardFooter className="flex flex-col gap-3 border-t pt-6">
        <p className="text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link href="/sign-up" className="font-medium text-foreground underline-offset-4 hover:underline">
            Sign up
          </Link>
        </p>
        <p className="text-center text-xs text-muted-foreground">
          <Link href="/dashboard" className="underline-offset-4 hover:underline">
            Continue to dashboard
          </Link>{" "}
          (demo)
        </p>
      </CardFooter>
    </Card>
  )
}
