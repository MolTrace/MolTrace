import { AppShell } from "@/components/app/app-shell"
import { DebugBundlesWorkspace } from "@/components/admin/debug-bundles-workspace"

/**
 * Admin Debug Bundles route (`src/app/admin/debug`) — matches `app/admin/debug/page.tsx`.
 */
export default function AdminDebugBundlesPage() {
  return (
    <AppShell>
      <DebugBundlesWorkspace />
    </AppShell>
  )
}
