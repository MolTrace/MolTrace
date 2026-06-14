import { redirect } from "next/navigation"

/**
 * `/login` alias → `/sign-in`. The SSO backend hard-codes its failure redirect to
 * `{FRONTEND_BASE_URL}/login?sso_error=1` (not client-configurable), but this app's
 * canonical login route is `/sign-in`. Forward there, preserving the sso_error flag
 * so `/sign-in` can show the non-leaky banner.
 */
export default async function LoginAliasPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  // Strict check, consistent with /sign-in — only the backend's literal `sso_error=1`
  // forwards the flag (a spoofed value never triggers the banner).
  const ssoError = Array.isArray(sp.sso_error) ? sp.sso_error[0] : sp.sso_error
  redirect(ssoError === "1" ? "/sign-in?sso_error=1" : "/sign-in")
}
