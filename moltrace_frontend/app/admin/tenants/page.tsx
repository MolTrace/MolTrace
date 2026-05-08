import { AppShell } from "@/components/app/app-shell"
import { TenantAdminWorkspace } from "@/components/admin/tenant-admin-workspace"

export default function TenantAdminPage() {
  return (
    <AppShell>
      <TenantAdminWorkspace />
    </AppShell>
  )
}
