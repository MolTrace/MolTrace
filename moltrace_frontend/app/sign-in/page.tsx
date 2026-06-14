import type { Metadata } from "next"
import { AuthPageLayout } from "@/components/marketing/auth-page-layout"
import { SignInForm } from "@/components/marketing/sign-in-form"

export const metadata: Metadata = {
  title: "Sign in | MolTrace",
  description: "Sign in to your MolTrace workspace.",
}

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const ssoError = firstParam(sp.sso_error) === "1"
  const ssoSlug = firstParam(sp.sso) ?? ""
  const sessionReset = firstParam(sp.session_reset)

  return (
    <AuthPageLayout title="Welcome back" description="Sign in to continue to your scientific intelligence workspace.">
      <SignInForm ssoError={ssoError} ssoSlug={ssoSlug} sessionReset={sessionReset} />
    </AuthPageLayout>
  )
}
