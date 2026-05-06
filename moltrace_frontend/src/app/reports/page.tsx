import SavedReportsWorkspace from "@/components/reports/saved-reports-workspace"
import { AppShell } from "@/components/app/app-shell"

/**
 * Reports route mirror (`src/app/reports`) — matches documented path next to `app/reports/page.tsx`.
 */
export default function ReportsPageSrcApp() {
  return (
    <AppShell>
      <SavedReportsWorkspace />
    </AppShell>
  )
}
