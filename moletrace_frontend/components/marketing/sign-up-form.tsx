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
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return fallback
}

export function SignUpForm() {
  const router = useRouter()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const password = formValue(formData, "password", false)
    const passwordConfirm = formValue(formData, "password-confirm", false)

    setMessage(null)
    setError(null)

    if (password !== passwordConfirm) {
      setError("Password confirmation does not match password.")
      return
    }

    setIsSubmitting(true)

    try {
      const data = await apiFetch<AuthPageResponse>("/auth/sign-up", {
        method: "POST",
        body: {
          name: formValue(formData, "name") || undefined,
          email: formValue(formData, "email"),
          password,
          passwordConfirm,
        },
      })

      if (!data.access_token) {
        setMessage(data.detail || "Check your email to verify your account before signing in.")
        return
      }

      storeAuthSession(data)
      setMessage(data.user?.is_admin ? "Account created with admin access." : "Account created.")
      router.push("/dashboard")
    } catch (submitError) {
      setError(authErrorMessage(submitError, "Unable to create account."))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign up</CardTitle>
        <CardDescription>Create an account to get started with MolTrace.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="sign-up-name">Full name</Label>
            <Input
              id="sign-up-name"
              name="name"
              type="text"
              autoComplete="name"
              disabled={isSubmitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sign-up-email">Email</Label>
            <Input
              id="sign-up-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              disabled={isSubmitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sign-up-password">Password</Label>
            <Input
              id="sign-up-password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              disabled={isSubmitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sign-up-password-confirm">Confirm password</Label>
            <Input
              id="sign-up-password-confirm"
              name="password-confirm"
              type="password"
              autoComplete="new-password"
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
            {isSubmitting ? "Creating account..." : "Create account"}
          </Button>
        </form>
      </CardContent>
      <CardFooter className="flex flex-col gap-3 border-t pt-6">
        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/sign-in" className="font-medium text-foreground underline-offset-4 hover:underline">
            Sign in
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
