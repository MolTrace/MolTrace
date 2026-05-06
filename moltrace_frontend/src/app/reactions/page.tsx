import { AppShell } from "@/components/app/app-shell"
import { ReactionOptimizationLanding } from "@/components/reaction-optimization/reaction-optimization-landing"

/**
 * Mirror of `app/reactions/page.tsx` — Reaction Optimization landing (GET/POST /reaction-projects).
 */
export default function ReactionsPage() {
  return (
    <AppShell>
      <ReactionOptimizationLanding />
    </AppShell>
  )
}
