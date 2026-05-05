import { AppShell } from "@/components/app/app-shell"
import { BatchRegistryWorkspace } from "@/components/batches/batch-registry-workspace"

/**
 * Batches route (`src/app/batches`) — mirror of `app/batches/page.tsx`.
 */
export default function BatchesPage() {
  return (
    <AppShell>
      <BatchRegistryWorkspace />
    </AppShell>
  )
}
