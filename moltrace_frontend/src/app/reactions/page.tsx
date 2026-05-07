import { AppShell } from "@/components/app/app-shell"
import { ReactionProgramInterfaceWorkspace } from "@/components/reaction-optimization/reaction-program-interface-workspace"

/**
 * Mirror of `app/reactions/page.tsx` — Reaction Optimization landing (GET/POST /reaction-projects).
 */
export default function ReactionsPage() {
  return (
    <AppShell>
      <ReactionProgramInterfaceWorkspace />
    </AppShell>
  )
}
