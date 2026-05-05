import { AppShell } from "@/components/app/app-shell"
import { SecurityEventsWorkspace } from "@/components/admin/security-events-workspace"

export default function AdminSecurityEventsPage() {
  return (
    <AppShell>
      <SecurityEventsWorkspace />
    </AppShell>
  )
}
