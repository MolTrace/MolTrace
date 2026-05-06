import { AppShell } from "@/components/app/app-shell"
import { SystemStatusWorkspace } from "@/components/admin/system-status-workspace"

export default function AdminSystemStatusPage() {
  return (
    <AppShell>
      <SystemStatusWorkspace />
    </AppShell>
  )
}
