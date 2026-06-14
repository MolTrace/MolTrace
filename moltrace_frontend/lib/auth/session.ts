import { AUTH_USER_STORAGE_KEY, clearStoredTokens, writeAuthTokens } from "@/lib/api/client"

/** The minimal authenticated-user shape persisted to localStorage. Matches the
 *  `user` object returned by both `/auth/sign-in` and `/auth/sso/exchange`. */
export type AuthSessionUser = {
  id: number
  email: string
  is_admin: boolean
  is_verified: boolean
}

/**
 * Persist an authenticated session to localStorage — the single writer shared by
 * password sign-in, the SSO callback, and the MFA-login verify routes. Stores the
 * bearer (read back by `apiFetch`), the rotating refresh token + access expiry
 * (drive transparent re-auth), and the user JSON; drops any SpectraCheck
 * evidence-session belonging to the previous user.
 *
 * No-op without a token or outside the browser.
 */
export function storeAuthSession(
  accessToken: string | null | undefined,
  user?: AuthSessionUser | null,
  extras?: { refreshToken?: string | null; accessExpiresAt?: string | null },
) {
  if (!accessToken || typeof window === "undefined") return

  writeAuthTokens(accessToken, extras?.refreshToken ?? null, extras?.accessExpiresAt ?? null)
  if (user) {
    window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user))
  }

  try {
    window.localStorage.removeItem("moltrace:spectracheck:evidence-session")
  } catch {
    // Private-mode / quota — ignore.
  }
}

/** Clear the whole token family + user (hard logout / refresh-reuse). */
export function clearAuthSession() {
  clearStoredTokens()
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem("moltrace:spectracheck:evidence-session")
    } catch {
      // ignore
    }
  }
}
