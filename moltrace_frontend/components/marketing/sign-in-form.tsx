"use client"

import type { FormEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  ApiError,
  AUTH_TOKEN_STORAGE_KEY,
  AUTH_USER_STORAGE_KEY,
  apiFetch,
} from "@/lib/api/client"

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

function formValue(formData: FormData, key: string, trim = true) {
  const value = formData.get(key)
  if (typeof value !== "string") return ""
  return trim ? value.trim() : value
}

function storeAuthSession(data: AuthPageResponse) {
  if (!data.access_token) return

  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, data.access_token)
  if (data.user) {
    window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(data.user))
  }
}

function authErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.status === 401) return SIGN_IN_FAILURE_MESSAGE
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return fallback
}

export function SignInForm() {
  const router = useRouter()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    setIsSubmitting(true)
    setMessage(null)
    setError(null)

    try {
      const data = await apiFetch<AuthPageResponse>("/auth/sign-in", {
        method: "POST",
        body: {
          email: formValue(formData, "email"),
          password: formValue(formData, "password", false),
        },
      })

      if (!data.access_token) {
        setMessage(data.detail || "Check your email to finish signing in.")
        return
      }

      storeAuthSession(data)
      setMessage(data.user?.is_admin ? "Signed in with admin access." : "Signed in.")
      router.push("/dashboard")
    } catch (submitError) {
      setError(authErrorMessage(submitError, "Unable to sign in."))
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
      <CardContent>
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
            <Input
              id="sign-in-password"
              name="password"
              type="password"
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
