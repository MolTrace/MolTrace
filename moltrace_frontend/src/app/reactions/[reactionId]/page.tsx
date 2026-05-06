import { AppShell } from "@/components/app/app-shell"
import { ReactionProjectDetail } from "@/components/reaction-optimization/reaction-project-detail"

/**
 * Mirror path `src/app/reactions/[reactionId]` — Next resolves `app/reactions/[reactionId]` for routing.
 */
export default function ReactionProjectDetailPage() {
  return (
    <AppShell>
      <ReactionProjectDetail />
    </AppShell>
  )
}
