import type { Metadata } from "next"
import { AuthPageLayout } from "@/components/marketing/auth-page-layout"
import { SignInForm } from "@/components/marketing/sign-in-form"

export const metadata: Metadata = {
  title: "Sign in | MolTrace",
  description: "Sign in to your MolTrace workspace.",
}

export default function SignInPage() {
  return (
    <AuthPageLayout title="Welcome back" description="Sign in to continue to your scientific intelligence workspace.">
      <SignInForm />
    </AuthPageLayout>
  )
}
