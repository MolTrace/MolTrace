import type { Metadata } from "next"
import { AuthPageLayout } from "@/components/marketing/auth-page-layout"
import { SignUpForm } from "@/components/marketing/sign-up-form"

export const metadata: Metadata = {
  title: "Sign up | MolTrace",
  description: "Create a MolTrace account.",
}

export default function SignUpPage() {
  return (
    <AuthPageLayout title="Create your account" description="Join MolTrace to access AI-native scientific intelligence tools.">
      <SignUpForm />
    </AuthPageLayout>
  )
}
