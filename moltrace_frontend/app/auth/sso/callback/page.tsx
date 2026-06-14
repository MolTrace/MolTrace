"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2 } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { storeAuthSession } from "@/lib/auth/session"
import type { components } from "@/src/lib/api/schema"

type ExchangeResponse = components["schemas"]["AccessTokenResponse"]

/**
 * Headless SSO callback. The backend lands the browser here after validating the
 * IdP round-trip: `{FRONTEND_BASE_URL}/auth/sso/callback?code=<one-time-code>`.
 *
 * We immediately trade the one-time, short-lived (10 min) code for a bearer
 * session and route into the app. The code is single-use and never rendered. Any
 * failure (missing/invalid/expired/already-used code → 400) bounces to
 * `/login?sso_error=1` with a non-leaky banner — the backend deliberately does
 * not disclose the specific reason.
 */
function SsoCallback() {
  const router = useRouter()
  const params = useSearchParams()
  // Guard against React StrictMode's double-invoked effect (dev) re-POSTing the
  // single-use code — the second exchange would 400 and bounce a successful login.
  const exchanged = useRef(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (exchanged.current) return
    exchanged.current = true

    const code = params.get("code")
    if (!code) {
      router.replace("/login?sso_error=1")
      return
    }

    void (async () => {
      try {
        const res = await apiFetch<ExchangeResponse>("/auth/sso/exchange", {
          method: "POST",
          body: { code },
        })
        if (!res?.access_token) {
          router.replace("/login?sso_error=1")
          return
        }
        storeAuthSession(res.access_token, res.user)
        setDone(true)
        router.replace("/dashboard")
      } catch {
        router.replace("/login?sso_error=1")
      }
    })()
  }, [params, router])

  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 text-center">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
        {done ? "Signed in. Redirecting…" : "Completing single sign-on…"}
      </p>
    </main>
  )
}

export default function SsoCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-[60vh] items-center justify-center px-6">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden />
        </main>
      }
    >
      <SsoCallback />
    </Suspense>
  )
}
