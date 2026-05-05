import { AppShell } from "@/components/app/app-shell"
import { SecurityEventsWorkspace } from "@/components/admin/security-events-workspace"

/**
 * Admin Security Events route (`src/app/admin/security`) — matches `app/admin/security/page.tsx`.
 */
export default function AdminSecurityEventsPage() {
  return (
    <AppShell>
      <SecurityEventsWorkspace />
    </AppShell>
  )
}
