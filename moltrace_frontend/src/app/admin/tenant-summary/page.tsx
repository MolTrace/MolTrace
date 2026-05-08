import { AppShell } from "@/components/app/app-shell"
import { MobileTenantSummaryWorkspace } from "@/components/admin/mobile-tenant-summary-workspace"

/**
 * Mobile tenant summary route (`src/app/admin/tenant-summary`) — matches `app/admin/tenant-summary/page.tsx`.
 */
export default function TenantSummaryPage() {
  return (
    <AppShell>
      <MobileTenantSummaryWorkspace />
    </AppShell>
  )
}
