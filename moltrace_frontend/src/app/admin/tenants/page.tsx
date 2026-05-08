import { AppShell } from "@/components/app/app-shell"
import { TenantAdminWorkspace } from "@/components/admin/tenant-admin-workspace"

/**
 * Tenant Admin route (`src/app/admin/tenants`) — matches `app/admin/tenants/page.tsx`.
 */
export default function TenantAdminPage() {
  return (
    <AppShell>
      <TenantAdminWorkspace />
    </AppShell>
  )
}
