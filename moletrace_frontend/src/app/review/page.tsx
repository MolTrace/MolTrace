import ReviewQueueWorkspace from "@/components/review/review-queue-workspace"
import { AppShell } from "@/components/app/app-shell"

/**
 * Review Queue route mirror (`src/app/review`) — matches `app/review/page.tsx`.
 */
export default function ReviewQueuePageSrcApp() {
  return (
    <AppShell>
      <ReviewQueueWorkspace />
    </AppShell>
  )
}
