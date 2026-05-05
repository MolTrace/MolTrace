import { AppShell } from "@/components/app/app-shell"
import { ValidationDashboardWorkspace } from "@/components/validation/validation-dashboard-workspace"

/**
 * Validation route mirror (`src/app/validation`) — matches documented path next to `app/validation/page.tsx`.
 */
export default function ValidationDashboardPageSrcApp() {
  return (
    <AppShell>
      <ValidationDashboardWorkspace />
    </AppShell>
  )
}
