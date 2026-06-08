import { AppShell } from "@/components/app/app-shell"
import { OpsDashboardWorkspace } from "@/components/admin/ops-dashboard-workspace"

export default function AdminOpsPage() {
  return (
    <AppShell>
      <OpsDashboardWorkspace />
    </AppShell>
  )
}
