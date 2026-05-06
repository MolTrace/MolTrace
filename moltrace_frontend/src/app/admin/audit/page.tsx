import { AppShell } from "@/components/app/app-shell"
import { AuditSearchWorkspace } from "@/components/admin/audit-search-workspace"

/**
 * Admin Audit Search route (`src/app/admin/audit`) — matches `app/admin/audit/page.tsx`.
 */
export default function AdminAuditSearchPage() {
  return (
    <AppShell>
      <AuditSearchWorkspace />
    </AppShell>
  )
}
