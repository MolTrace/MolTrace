import { AppShell } from "@/components/app/app-shell"
import { SystemStatusWorkspace } from "@/components/admin/system-status-workspace"

/**
 * Admin System Status route (`src/app/admin/system`) — matches `app/admin/system/page.tsx`.
 */
export default function AdminSystemStatusPage() {
  return (
    <AppShell>
      <SystemStatusWorkspace />
    </AppShell>
  )
}
