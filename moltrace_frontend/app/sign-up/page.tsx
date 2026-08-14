import type { Metadata } from "next"
import { AuthPageLayout } from "@/components/marketing/auth-page-layout"
import { SignUpForm } from "@/components/marketing/sign-up-form"

export const metadata: Metadata = {
  title: "Sign up | MolTrace",
  description: "Create a MolTrace account.",
  // Explicit noindex, belt to robots.txt's braces. A disallow only stops
  // crawling — a page can still be indexed URL-only from external links, and
  // an auth form has no business in a results page either way.
  robots: { index: false, follow: false },
}

export default function SignUpPage() {
  return (
    <AuthPageLayout title="Create your account" description="Join MolTrace to access AI-native scientific intelligence tools.">
      <SignUpForm />
    </AuthPageLayout>
  )
}
