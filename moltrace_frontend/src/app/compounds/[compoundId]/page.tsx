import { AppShell } from "@/components/app/app-shell"
import { CompoundDetailWorkspace } from "@/components/compounds/compound-detail-workspace"

/**
 * Compound detail route (`src/app/compounds/[compoundId]`) — mirror of `app/compounds/[compoundId]/page.tsx`.
 */
export default function CompoundDetailPage() {
  return (
    <AppShell>
      <CompoundDetailWorkspace />
    </AppShell>
  )
}
