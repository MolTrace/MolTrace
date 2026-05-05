import { AppShell } from "@/components/app/app-shell"
import { ValidationRunDetailWorkspace } from "@/components/validation/validation-run-detail-workspace"

/**
 * Validation run detail mirror (`src/app/validation/[validationRunId]`) — canonical route is `app/validation/[validationRunId]/page.tsx`.
 */
export default function ValidationRunDetailPageSrcApp() {
  return (
    <AppShell>
      <ValidationRunDetailWorkspace />
    </AppShell>
  )
}
