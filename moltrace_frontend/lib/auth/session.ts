import { AUTH_TOKEN_STORAGE_KEY, AUTH_USER_STORAGE_KEY } from "@/lib/api/client"

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
 * password sign-in and the SSO callback. Stores the bearer token (read back by
 * `apiFetch` on every request) and the user JSON (drives the admin badge +
 * `useTenant().isAdmin`), and drops any SpectraCheck evidence-session belonging
 * to the previous user so the next workspace mount falls back to defaults.
 *
 * No-op without a token or outside the browser.
 */
export function storeAuthSession(accessToken: string | null | undefined, user?: AuthSessionUser | null) {
  if (!accessToken || typeof window === "undefined") return

  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, accessToken)
  if (user) {
    window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user))
  }

  try {
    window.localStorage.removeItem("moltrace:spectracheck:evidence-session")
  } catch {
    // Private-mode / quota — ignore.
  }
}
