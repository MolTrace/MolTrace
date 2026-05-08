import { AppShell } from "@/components/app/app-shell"
import { TenantDetailWorkspace } from "@/components/admin/tenant-detail-workspace"

/**
 * Tenant detail route (`src/app/admin/tenants/[tenantId]`) — matches `app/admin/tenants/[tenantId]/page.tsx`.
 */
export default function TenantDetailPage() {
  return (
    <AppShell>
      <TenantDetailWorkspace />
    </AppShell>
  )
}
