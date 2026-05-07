import { AppShell } from "@/components/app/app-shell"
import { AdminInterfaceWorkspace } from "@/components/admin/admin-interface-workspace"

/**
 * Admin System Status route (`src/app/admin/system`) — matches `app/admin/system/page.tsx`.
 */
export default function AdminSystemStatusPage() {
  return (
    <AppShell>
      <AdminInterfaceWorkspace />
    </AppShell>
  )
}
