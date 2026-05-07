import { AppShell } from "@/components/app/app-shell"
import { ReactionStudioWorkspace } from "@/components/reaction-studio/reaction-studio-workspace"

/**
 * Route mirror (`app/reactions/studio`) — matches `src/app/reactions/studio/page.tsx`.
 */
export default function ReactionStudioPageApp() {
  return (
    <AppShell>
      <ReactionStudioWorkspace />
    </AppShell>
  )
}
